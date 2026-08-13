from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from pipeline.config import ConfigValidationError, load_config_bundle, validate_config_bundle
from pipeline.contracts import VIDEO_P0_NOTATION_KEYS
from pipeline.rules.p0_video_model import evaluate_video_p0_model


NOW = "2026-08-13T01:23:03Z"
METRIC_IDS = (
    "sofr_iorb_spread_bp",
    "reserve_balances",
    "tga_daily",
    "srf_accepted",
)


def video_config() -> dict:
    return copy.deepcopy(
        load_config_bundle().alert_rules["alerts"]["video_p0_model"]
    )


def quality(
    *,
    overrides: dict[str, tuple[str, str]] | None = None,
) -> dict[str, dict]:
    dates = {
        "sofr_iorb_spread_bp": "2026-08-11",
        "reserve_balances": "2026-08-06",
        "tga_daily": "2026-08-11",
        "srf_accepted": "2026-08-11",
    }
    output = {}
    for metric_id in METRIC_IDS:
        status, freshness = (overrides or {}).get(metric_id, ("OK", "FRESH"))
        output[metric_id] = {
            "status": status,
            "freshness": freshness,
            "observation_date": dates[metric_id],
            "released_at": "2026-08-12T20:30:00Z",
        }
    return output


def srf_day(
    operation_date: str,
    *,
    eligible: float = 0.0,
    exercise: float = 0.0,
) -> dict:
    technical_only = exercise > 0 and eligible == 0
    return {
        "date": operation_date,
        "accepted_amount_usd_bn": eligible + exercise,
        "alert_eligible_accepted_amount_usd_bn": eligible,
        "exercise_accepted_amount_usd_bn": exercise,
        "has_technical_exercise": exercise > 0,
        "technical_exercise": technical_only,
        "classification_complete": True,
    }


def zero_srf() -> list[dict]:
    return [
        srf_day("2026-08-07"),
        srf_day("2026-08-10"),
        srf_day("2026-08-11"),
    ]


def evaluate(**overrides: object) -> dict:
    arguments: dict[str, object] = {
        "latest_sofr_iorb_bp": -1.0,
        "positive_streak": 0,
        "reserve_balance_usd_bn": 3000.0,
        "reserve_change_4w_usd_bn": 40.0,
        "reserve_trailing_5y_p10_usd_bn": -90.0,
        "tga_daily_usd_bn": 900.0,
        "srf_recent_operation_days": zero_srf(),
        "metric_quality": quality(),
        "technical_flags": (),
        "crisis_context": None,
        "config": video_config(),
        "evaluated_at": NOW,
    }
    arguments.update(overrides)
    return evaluate_video_p0_model(**arguments)  # type: ignore[arg-type]


def clause(model: dict, formula: str, clause_id: str) -> dict:
    return next(
        item
        for item in model["formulas"][formula]["clauses"]
        if item["clause_id"] == clause_id
    )


def audited_context(status: str) -> dict:
    if status == "UNKNOWN":
        return {
            "status": status,
            "as_of": None,
            "reviewed_at": None,
            "reviewer": None,
            "note": None,
        }
    return {
        "status": status,
        "as_of": "2026-08-12",
        "reviewed_at": "2026-08-13T00:15:00Z",
        "reviewer": "release-reviewer",
        "note": "Reviewed against the version-controlled public evidence note.",
    }


def test_config_loads_exact_audited_video_model_and_reserve_zones():
    bundle = load_config_bundle()
    model = bundle.alert_rules["alerts"]["video_p0_model"]
    source = model["source"]

    assert bundle.alert_rules["schema_version"] == "2.3.0"
    assert model["yellow"] == {
        "spread_positive_bp": 0,
        "positive_streak_observations": 3,
        "reserve_below_usd_tn": 2.9,
        "require_negative_reserve_change_4w": True,
        "tga_near_1t_floor_usd_tn": 0.95,
        "tga_source_target_usd_tn": 1.0,
    }
    assert model["red"] == {
        "sofr_iorb_bp": 3.0,
        "reserve_below_usd_tn": 2.8,
        "srf_window_completed_operation_days": 3,
        "srf_positive_days_latest_3": 2,
        "exclude_technical_exercises": True,
    }
    assert model["extreme"] == {
        "reserve_below_usd_tn": 2.5,
        "rapid_decline_rule": "trailing_5y_p10",
        "crisis_context_required": True,
    }
    assert [item["segment_id"] for item in source["segments"]] == [
        "yellow_red",
        "reserve_exit_1",
        "reserve_exit_2",
    ]
    assert source["author"] == "一个狠人"
    assert source["title"].endswith("二波打法五步三開關全套交付")
    assert bundle.alert_rules["alerts"]["reserve_balances"][
        "reference_zones_usd_tn"
    ] == [2.9, 2.8, 2.5]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda rules: rules["alerts"]["video_p0_model"]["yellow"].__setitem__(
                "spread_positive_bp", float("nan")
            ),
            "spread_positive_bp must be a finite number",
        ),
        (
            lambda rules: rules["alerts"]["video_p0_model"]["yellow"].__setitem__(
                "tga_near_1t_floor_usd_tn", 1.0
            ),
            "TGA floor must be below",
        ),
        (
            lambda rules: rules["alerts"]["video_p0_model"]["red"].__setitem__(
                "srf_positive_days_latest_3", 1
            ),
            "must be exactly 2",
        ),
        (
            lambda rules: rules["alerts"]["video_p0_model"]["source"][
                "segments"
            ][0].__setitem__("start_seconds", 1379),
            "audited source segment",
        ),
        (
            lambda rules: rules["alerts"]["reserve_balances"].__setitem__(
                "reference_zones_usd_tn", [2.95, 2.8, 2.5]
            ),
            "must equal reserve_balances reference zones",
        ),
    ],
)
def test_config_validation_rejects_threshold_or_source_drift(mutate, message):
    bundle = load_config_bundle()
    rules = copy.deepcopy(bundle.alert_rules)
    mutate(rules)
    with pytest.raises(ConfigValidationError, match=message):
        validate_config_bundle(replace(bundle, alert_rules=rules))


@pytest.mark.parametrize(
    "context",
    [
        {
            "status": "UNKNOWN",
            "as_of": "2026-08-12",
            "reviewed_at": None,
            "reviewer": None,
            "note": None,
        },
        {
            "status": "NO_MAJOR_CRISIS",
            "as_of": "2026-08-12",
            "reviewed_at": "2026-08-12T23:00:00+00:00",
            "reviewer": "reviewer",
            "note": "evidence",
        },
        {
            "status": "NO_MAJOR_CRISIS",
            "as_of": "2026-08-12",
            "reviewed_at": "2026-08-13T00:00:00Z",
            "reviewer": "",
            "note": "evidence",
        },
        {
            "status": "FALSE",
            "as_of": None,
            "reviewed_at": None,
            "reviewer": None,
            "note": None,
        },
    ],
)
def test_config_validation_fails_closed_on_unaudited_crisis_context(context):
    bundle = load_config_bundle()
    rules = copy.deepcopy(bundle.alert_rules)
    rules["alerts"]["video_p0_model"]["crisis_context"] = context
    with pytest.raises(ConfigValidationError):
        validate_config_bundle(replace(bundle, alert_rules=rules))


def test_green_model_is_json_serializable_and_every_clause_has_dual_provenance():
    model = evaluate()

    assert model["status"] == "GREEN"
    assert model["data_status"] == "CURRENT"
    assert model["confidence"] == "HIGH"
    assert model["evaluated_at"] == NOW
    assert model["thresholds"]["yellow"]["spread_positive_bp"] == 0
    assert set(model) == {
        "model_id",
        "label",
        "enabled",
        "status",
        "data_status",
        "confidence",
        "availability_reason",
        "evaluated_at",
        "source",
        "thresholds",
        "operationalizations",
        "crisis_context",
        "notation",
        "formulas",
        "technical_flags",
        "notes",
    }
    json.dumps(model, ensure_ascii=False)

    for formula in model["formulas"].values():
        for item in formula["clauses"]:
            kinds = {basis["kind"] for basis in item["basis"]}
            assert "VIDEO_SOURCE_RULE" in kinds
            assert (
                "MANUAL_CONTEXT" in kinds
                if item["metric_id"] is None
                else "DASHBOARD_OPERATIONALIZATION" in kinds
            )


def test_formula_presentation_has_three_top_level_tex_blocks_and_complete_notation():
    model = evaluate()

    assert tuple(item["key"] for item in model["notation"]) == VIDEO_P0_NOTATION_KEYS
    assert len({item["key"] for item in model["notation"]}) == 24
    assert {
        item["source_kind"] for item in model["notation"]
    } == {
        "MATHEMATICAL_NOTATION",
        "VIDEO_SOURCE_RULE",
        "DASHBOARD_OPERATIONALIZATION",
        "MANUAL_CONTEXT",
    }
    for formula_id in ("yellow", "red", "extreme"):
        formula = model["formulas"][formula_id]
        assert formula["display_tex"].startswith(r"\begin{aligned}")
        assert formula["display_tex"].endswith(r"\end{aligned}")
        assert formula["plain_language"].strip()
    assert "數值候選：" in model["formulas"]["extreme"]["plain_language"]
    assert "\n完整確認：" in model["formulas"]["extreme"]["plain_language"]
    assert set(model["formulas"]["red"]["routes"][0]) == {
        "route_id", "label", "expression", "triggered", "clauses"
    }
    assert set(model["formulas"]["red"]["routes"][1]) == {
        "route_id", "label", "expression", "triggered", "clauses"
    }


def test_config_threshold_mutation_propagates_to_clauses_text_tex_and_notation():
    config = video_config()
    config["yellow"].update(
        positive_streak_observations=4,
        reserve_below_usd_tn=2.85,
        tga_near_1t_floor_usd_tn=0.93,
        tga_source_target_usd_tn=0.99,
    )
    config["red"].update(
        sofr_iorb_bp=4.25,
        reserve_below_usd_tn=2.75,
        srf_window_completed_operation_days=4,
        srf_positive_days_latest_3=3,
    )
    config["extreme"]["reserve_below_usd_tn"] = 2.45
    model = evaluate(
        config=config,
        srf_recent_operation_days=[srf_day("2026-08-06"), *zero_srf()],
    )
    formulas = model["formulas"]
    notation = {item["key"]: item for item in model["notation"]}

    assert clause(model, "yellow", "sofr_positive_streak")["threshold"] == 4
    assert clause(model, "yellow", "reserve_below_yellow")["threshold"] == 2850
    assert clause(model, "yellow", "tga_near_1t")["threshold"] == 930
    assert clause(model, "red", "sofr_spread_above_red")["threshold"] == 4.25
    assert clause(model, "red", "reserve_below_red")["threshold"] == 2750
    assert clause(model, "red", "srf_positive_days")["threshold"] == 3
    assert clause(model, "extreme", "reserve_below_extreme")["threshold"] == 2450

    assert "POSITIVE STREAK ≥ 4" in formulas["yellow"]["expression"]
    assert "RESERVES < 2.85T" in formulas["yellow"]["expression"]
    assert r"n_t^{+}\ge 4" in formulas["yellow"]["display_tex"]
    assert r"r_t<2.85" in formulas["yellow"]["display_tex"]
    assert r"g_t\ge 0.93" in formulas["yellow"]["display_tex"]
    assert "+4.25 bp" in formulas["red"]["plain_language"]
    assert r"s_t>4.25" in formulas["red"]["display_tex"]
    assert r"r_t<2.75" in formulas["red"]["display_tex"]
    assert r"u_t\ge 3" in formulas["red"]["display_tex"]
    assert "LATEST 4 DAYS" in formulas["red"]["routes"][1]["expression"]
    assert r"r_t<2.45" in formulas["extreme"]["display_tex"]

    assert notation["source_reserves_yellow"]["symbol_tex"] == "r_t<2.85"
    assert notation["source_spread_red"]["symbol_tex"] == r"s_t>4.25\,\mathrm{bp}"
    assert notation["source_tga_target"]["symbol_tex"] == r"g_t\to 0.99"
    assert notation["op_positive_streak"]["symbol_tex"] == r"n_t^{+}\ge 4"
    assert notation["op_tga_floor"]["symbol_tex"] == r"g_t\ge 0.93"
    assert notation["op_srf_2_of_3"]["symbol_tex"] == r"u_t\ge 3"
    assert "最近 4 個" in notation["op_srf_2_of_3"]["definition"]


def test_yellow_formula_and_strict_boundaries():
    yellow = evaluate(
        latest_sofr_iorb_bp=1.0,
        positive_streak=3,
        reserve_balance_usd_bn=2899.0,
        reserve_change_4w_usd_bn=-1.0,
        tga_daily_usd_bn=950.0,
    )
    assert yellow["status"] == "YELLOW"
    assert yellow["formulas"]["yellow"]["triggered"] is True

    cases = [
        {"positive_streak": 2},
        {"reserve_balance_usd_bn": 2900.0},
        {"reserve_change_4w_usd_bn": 0.0},
        {"tga_daily_usd_bn": 949.0},
    ]
    for override in cases:
        inputs = {
            "latest_sofr_iorb_bp": 1.0,
            "positive_streak": 3,
            "reserve_balance_usd_bn": 2899.0,
            "reserve_change_4w_usd_bn": -1.0,
            "tga_daily_usd_bn": 950.0,
            **override,
        }
        result = evaluate(**inputs)
        assert result["formulas"]["yellow"]["triggered"] is False
        assert result["status"] == "GREEN"


@pytest.mark.parametrize(
    ("spread", "reserves", "expected"),
    [
        (3.1, 2799.0, True),
        (3.0, 2799.0, False),
        (3.1, 2800.0, False),
        (5.0, 2900.0, False),
        (-1.0, 2700.0, False),
    ],
)
def test_red_spread_and_reserve_route_boundaries(spread, reserves, expected):
    model = evaluate(
        latest_sofr_iorb_bp=spread,
        reserve_balance_usd_bn=reserves,
        crisis_context=audited_context("MAJOR_CRISIS_PRESENT"),
    )
    route = model["formulas"]["red"]["routes"][0]
    assert route["triggered"] is expected
    assert (model["status"] == "RED") is expected


def test_srf_route_counts_two_of_three_and_excludes_technical_only_use():
    red = evaluate(
        srf_recent_operation_days=[
            srf_day("2026-08-07", eligible=1.0),
            srf_day("2026-08-10"),
            srf_day("2026-08-11", eligible=2.0),
        ]
    )
    assert red["status"] == "RED"
    assert red["formulas"]["red"]["routes"][1]["triggered"] is True

    technical = evaluate(
        srf_recent_operation_days=[
            srf_day("2026-08-07", exercise=0.001),
            srf_day("2026-08-10", exercise=0.001),
            srf_day("2026-08-11", eligible=1.0),
        ]
    )
    assert clause(technical, "red", "srf_positive_days")["current_value"] == 1
    assert technical["formulas"]["red"]["routes"][1]["triggered"] is False


def test_srf_mixed_day_uses_only_alert_eligible_nontechnical_amount():
    model = evaluate(
        srf_recent_operation_days=[
            srf_day("2026-08-07", eligible=1.5, exercise=0.001),
            srf_day("2026-08-10", exercise=0.001),
            srf_day("2026-08-11", eligible=0.5),
        ]
    )
    assert model["status"] == "RED"
    assert clause(model, "red", "srf_positive_days")["current_value"] == 2


def test_srf_duplicate_dates_or_missing_classification_fail_closed():
    duplicate = zero_srf()
    duplicate[1] = {**duplicate[1], "date": duplicate[0]["date"]}
    with pytest.raises(ValueError, match="duplicate SRF operation day"):
        evaluate(srf_recent_operation_days=duplicate)

    incomplete = zero_srf()
    incomplete[0].pop("classification_complete")
    model = evaluate(srf_recent_operation_days=incomplete)
    srf = clause(model, "red", "srf_positive_days")
    assert srf["met"] is None
    assert srf["evaluation_state"] == "MISSING"
    assert model["status"] == "UNAVAILABLE"


def test_fewer_than_three_completed_srf_days_is_unknown_not_false():
    model = evaluate(srf_recent_operation_days=zero_srf()[:2])
    srf = clause(model, "red", "srf_positive_days")
    assert srf["current_value"] == 0
    assert srf["met"] is None
    assert srf["evaluation_state"] == "MISSING"
    assert model["status"] == "UNAVAILABLE"


def test_tri_state_and_resolves_false_but_unknown_can_block_true():
    stale_spread = quality(
        overrides={"sofr_iorb_spread_bp": ("STALE", "STALE")}
    )
    resolved_false = evaluate(
        reserve_balance_usd_bn=3000.0,
        metric_quality=stale_spread,
        crisis_context=audited_context("MAJOR_CRISIS_PRESENT"),
    )
    assert clause(resolved_false, "red", "sofr_spread_above_red")["met"] is None
    assert resolved_false["formulas"]["red"]["routes"][0]["triggered"] is False
    assert resolved_false["status"] == "GREEN"
    assert resolved_false["data_status"] == "PARTIAL"

    unresolved = evaluate(
        reserve_balance_usd_bn=2799.0,
        metric_quality=stale_spread,
        crisis_context=audited_context("MAJOR_CRISIS_PRESENT"),
    )
    assert unresolved["formulas"]["red"]["routes"][0]["triggered"] is None
    assert unresolved["status"] == "UNAVAILABLE"


def test_tri_state_or_true_route_overrides_unknown_other_route():
    stale_spread = quality(
        overrides={"sofr_iorb_spread_bp": ("STALE", "STALE")}
    )
    model = evaluate(
        reserve_balance_usd_bn=2799.0,
        metric_quality=stale_spread,
        srf_recent_operation_days=[
            srf_day("2026-08-07", eligible=1.0),
            srf_day("2026-08-10"),
            srf_day("2026-08-11", eligible=1.0),
        ],
        crisis_context=audited_context("MAJOR_CRISIS_PRESENT"),
    )
    assert model["formulas"]["red"]["routes"][0]["triggered"] is None
    assert model["formulas"]["red"]["routes"][1]["triggered"] is True
    assert model["status"] == "RED"


def test_extreme_context_gate_and_priority_are_explicit():
    common = {
        "latest_sofr_iorb_bp": 4.0,
        "reserve_balance_usd_bn": 2490.0,
        "reserve_change_4w_usd_bn": -100.0,
        "reserve_trailing_5y_p10_usd_bn": -90.0,
    }
    unknown = evaluate(**common, crisis_context=audited_context("UNKNOWN"))
    assert unknown["status"] == "EXTREME_CONTEXT_REQUIRED"
    assert unknown["formulas"]["extreme"]["candidate"] is True
    assert unknown["formulas"]["extreme"]["triggered"] is None
    assert unknown["formulas"]["extreme"]["context_required"] is True

    confirmed = evaluate(
        **common, crisis_context=audited_context("NO_MAJOR_CRISIS")
    )
    assert confirmed["status"] == "EXTREME_CONFIRMED"
    assert confirmed["formulas"]["extreme"]["triggered"] is True

    crisis = evaluate(
        **common, crisis_context=audited_context("MAJOR_CRISIS_PRESENT")
    )
    assert crisis["formulas"]["extreme"]["triggered"] is False
    assert crisis["status"] == "RED"


def test_major_crisis_false_gate_skips_unknown_extreme_candidate_and_falls_through():
    model = evaluate(
        reserve_balance_usd_bn=2490.0,
        reserve_change_4w_usd_bn=-100.0,
        reserve_trailing_5y_p10_usd_bn=None,
        crisis_context=audited_context("MAJOR_CRISIS_PRESENT"),
    )
    assert model["formulas"]["extreme"]["candidate"] is None
    assert model["formulas"]["extreme"]["triggered"] is False
    assert model["status"] == "GREEN"


def test_extreme_strict_level_and_p10_equality_boundaries():
    level_equal = evaluate(
        reserve_balance_usd_bn=2500.0,
        reserve_change_4w_usd_bn=-90.0,
        reserve_trailing_5y_p10_usd_bn=-90.0,
    )
    assert level_equal["formulas"]["extreme"]["candidate"] is False

    p10_equal = evaluate(
        reserve_balance_usd_bn=2490.0,
        reserve_change_4w_usd_bn=-90.0,
        reserve_trailing_5y_p10_usd_bn=-90.0,
    )
    assert p10_equal["formulas"]["extreme"]["candidate"] is True


def test_not_released_yet_uses_last_good_but_stale_or_missing_is_unknown():
    nr = evaluate(
        latest_sofr_iorb_bp=1.0,
        positive_streak=3,
        reserve_balance_usd_bn=2899.0,
        reserve_change_4w_usd_bn=-1.0,
        tga_daily_usd_bn=950.0,
        metric_quality=quality(
            overrides={"tga_daily": ("NOT_RELEASED_YET", "LATE")}
        ),
    )
    assert nr["status"] == "YELLOW"
    assert nr["data_status"] == "LAST_GOOD"
    assert nr["confidence"] == "MEDIUM"
    assert clause(nr, "yellow", "tga_near_1t")["evaluation_state"] == "LAST_GOOD"

    stale = evaluate(
        metric_quality=quality(
            overrides={"reserve_balances": ("STALE", "STALE")}
        )
    )
    assert stale["status"] == "UNAVAILABLE"
    assert clause(stale, "yellow", "reserve_below_yellow")["met"] is None

    missing = evaluate(
        latest_sofr_iorb_bp=4.0,
        positive_streak=3,
        reserve_balance_usd_bn=None,
        reserve_change_4w_usd_bn=-1.0,
        tga_daily_usd_bn=950.0,
    )
    assert missing["status"] == "UNAVAILABLE"
    assert clause(missing, "yellow", "reserve_below_yellow")["evaluation_state"] == "MISSING"


def test_disabled_model_is_valid_config_and_returns_a_disabled_evidence_envelope():
    bundle = load_config_bundle()
    rules = copy.deepcopy(bundle.alert_rules)
    rules["alerts"]["video_p0_model"]["enabled"] = False
    validate_config_bundle(replace(bundle, alert_rules=rules))

    model = evaluate(config=rules["alerts"]["video_p0_model"])
    assert model["enabled"] is False
    assert model["status"] == "UNAVAILABLE"
    assert model["data_status"] == "UNAVAILABLE"
    assert model["confidence"] == "UNKNOWN"
    assert model["availability_reason"] == "DISABLED"
    assert model["technical_flags"] == []
    assert model["notes"] == []
    assert model["formulas"]["yellow"]["triggered"] is None
    assert model["formulas"]["red"]["triggered"] is None
    assert model["formulas"]["extreme"]["candidate"] is None
    assert model["formulas"]["extreme"]["triggered"] is None
    assert model["formulas"]["extreme"]["context_required"] is False
    assert all(
        item["met"] is None and item["evaluation_state"] == "DISABLED"
        for formula in model["formulas"].values()
        for item in formula["clauses"]
    )


def test_technical_flags_only_downgrade_confidence_and_never_suppress_formula():
    common = {
        "latest_sofr_iorb_bp": 1.0,
        "positive_streak": 3,
        "reserve_balance_usd_bn": 2899.0,
        "reserve_change_4w_usd_bn": -1.0,
        "tga_daily_usd_bn": 950.0,
    }
    plain = evaluate(**common)
    technical = evaluate(
        **common, technical_flags=["quarter_end", "MONTH_END", "quarter_end"]
    )
    assert plain["status"] == technical["status"] == "YELLOW"
    assert plain["confidence"] == "HIGH"
    assert technical["confidence"] == "MEDIUM"
    assert technical["technical_flags"] == ["MONTH_END", "QUARTER_END"]
