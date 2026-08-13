"""Adversarial checks for the schema-2.3 deterministic interpretation layer."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta

import pytest

from pipeline.config import ConfigValidationError, load_config_bundle, validate_config_bundle
from pipeline.contracts import (
    ContractValidationError,
    INTERPRETED_P0_METRIC_IDS,
    validate_publication,
    validate_snapshot,
)
from pipeline.interpretation import (
    _anchored_observations,
    _confirmation_context,
    _cross_check_context,
    _data_state,
    _fed_assets,
    _on_rrp,
    _sofr_spread,
    _srf,
    _tga_flow_state,
    build_metric_interpretations,
    expanding_change_context,
    expanding_level_context,
    nearest_rank,
)
from pipeline.release import build_release
from pipeline.tests.test_release1 import NOW, fixture_collectors


def points(values, *, start=date(2020, 1, 1)):
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "value": value}
        for index, value in enumerate(values)
    ]


@pytest.fixture()
def publication(tmp_path):
    return build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=fixture_collectors(),
    )


def test_nearest_rank_is_one_indexed_and_ties_are_not_percentile_rules():
    assert nearest_rank([1, 2, 3, 4], 0.75) == 3
    assert nearest_rank([1, 1, 1, 9], 0.75) == 1
    with pytest.raises(ValueError):
        nearest_rank([1], 1.01)


def test_tied_nearest_rank_classifiers_use_threshold_values(publication):
    bundle = load_config_bundle()
    statistics = bundle.interpretation_rules["statistics"]
    confirmation = _confirmation_context(
        publication.snapshot["metrics"]["effr_iorb_spread_bp"],
        points([0.0] * 55 + [10.0] * 5 + [0.0]),
        statistics,
    )
    assert confirmation["thresholds"][0.8] == 0.0
    assert confirmation["thresholds"][0.95] == 10.0
    assert confirmation["state"] == "ELEVATED"

    cross = _cross_check_context(
        points([0.0] * 105),
        points([1.0] * 105),
        minimum_samples=104,
        q80=0.8,
        q95=0.95,
    )
    assert cross["percentile"] == 1.0
    assert cross["state"] == "ALIGNED"


def test_expanding_level_excludes_endpoint_and_hard_cuts_at_60_samples():
    history = list(range(60))
    insufficient = expanding_level_context(
        points(history[:59] + [100]), minimum_samples=60, quantiles=(0.8,)
    )
    sufficient = expanding_level_context(
        points(history + [100]), minimum_samples=60, quantiles=(0.8,)
    )
    assert insufficient["sample_size"] == 59
    assert insufficient["percentile"] is None
    assert sufficient["sample_size"] == 60
    assert sufficient["thresholds"][0.8] == 47
    assert sufficient["percentile"] == 1
    # A future point cannot alter the already-computed prefix endpoint.
    assert expanding_level_context(
        points(history + [100]), minimum_samples=60, quantiles=(0.8,)
    ) == sufficient


def test_expanding_weekly_change_excludes_endpoint_and_hard_cuts_at_104():
    insufficient = expanding_change_context(
        points(range(108)), lag=4, minimum_samples=104, quantiles=(0.25, 0.75)
    )
    sufficient = expanding_change_context(
        points(range(109)), lag=4, minimum_samples=104, quantiles=(0.25, 0.75)
    )
    assert insufficient["sample_size"] == 103
    assert insufficient["percentile"] is None
    assert sufficient["sample_size"] == 104
    assert sufficient["value"] == 4


def test_change_and_slope_windows_count_valid_observations_across_null_gaps(publication):
    context = expanding_change_context(
        points([0.0, 1.0, None, 2.0, 3.0, 4.0, 5.0]),
        lag=2,
        minimum_samples=3,
        quantiles=(0.5,),
    )
    assert context["value"] == 2.0
    assert context["sample_size"] == 3

    statistics = deepcopy(load_config_bundle().interpretation_rules["statistics"])
    statistics["daily_min_history_samples"] = 1
    confirmation = _confirmation_context(
        publication.snapshot["metrics"]["effr_iorb_spread_bp"],
        points([1.0, 2.0, None, 3.0, 4.0, 5.0]),
        statistics,
    )
    assert confirmation["slope"] == 1.0


def test_endpoint_anchor_rejects_trailing_null_and_date_or_value_mismatch():
    metric = {"value": 2.0, "observation_date": "2026-01-02"}
    series = points([1.0, 2.0], start=date(2026, 1, 1))
    assert _anchored_observations(metric, series) == series
    assert _anchored_observations(
        metric,
        series + [{"date": "2026-01-03", "value": 999_999.0}],
    ) == series
    assert _anchored_observations(
        {"value": None, "observation_date": "2026-01-03"},
        series + [{"date": "2026-01-03", "value": None}],
    ) == []
    assert _anchored_observations({**metric, "observation_date": "2026-01-03"}, series) == []
    assert _anchored_observations({**metric, "value": 3.0}, series) == []


def test_on_rrp_prior_window_is_exactly_19_vs_20_and_statistical_basis(publication):
    bundle = load_config_bundle()
    metric = deepcopy(publication.snapshot["metrics"]["on_rrp_accepted"])
    rule = bundle.interpretation_by_id["on_rrp_accepted"]
    metric.update(value=1.0, observation_date="2026-01-21")
    metric["changes"]["five_observations"] = -5.0
    nineteen = _on_rrp(rule, metric, points(range(20, 0, -1)), bundle.interpretation_rules["statistics"])
    twenty = _on_rrp(rule, metric, points(range(21, 0, -1)), bundle.interpretation_rules["statistics"])
    assert nineteen["state"] == "INSUFFICIENT_HISTORY"
    assert nineteen["views"][0]["sample_size"] == 19
    assert twenty["views"][0]["sample_size"] == 20
    assert twenty["views"][0]["basis"] == "STATISTICAL_BAND"
    assert twenty["rule_basis"] == ["CONTEXT_ONLY", "STATISTICAL_BAND"]


def test_on_rrp_uses_last_20_valid_prior_values_and_tied_floor_threshold(publication):
    bundle = load_config_bundle()
    metric = deepcopy(publication.snapshot["metrics"]["on_rrp_accepted"])
    metric.update(value=1.0, observation_date="2020-01-26")
    metric["changes"]["five_observations"] = 0.0
    prior = [1.0] * 20 + [None] * 5
    result = _on_rrp(
        bundle.interpretation_by_id["on_rrp_accepted"],
        metric,
        points(prior + [1.0]),
        bundle.interpretation_rules["statistics"],
    )
    view = result["views"][0]
    assert view["sample_size"] == 20
    assert view["percentile"] == 1.0
    assert result["state"] == "NEAR_FLOOR"


def test_red_spread_leg_is_not_red_without_reserve_confirmation(publication):
    bundle = load_config_bundle()
    metric = deepcopy(publication.snapshot["metrics"]["sofr_iorb_spread_bp"])
    metric["value"] = 4.0
    metric["statistics"]["positive_streak"] = 3
    result = _sofr_spread(
        bundle.interpretation_by_id["sofr_iorb_spread_bp"],
        metric,
        video_config=bundle.alert_rules["alerts"]["video_p0_model"],
        reserve_value=3_000.0,
        breadth={
            "kind": "BREADTH_COUNTER", "label": "B", "count": 0,
            "total": 3, "state": "NO_CONFIRMATION", "members": [],
            "basis": "STATISTICAL_BAND",
        },
    )
    assert result["state"] == "RED_SPREAD_LEG"
    assert result["severity"] == "YELLOW"
    full_route = next(row for row in result["views"][0]["rows"] if row["label"] == "FULL RED ROUTE A")
    assert full_route["threshold"] is None and full_route["upper_threshold"] is None
    assert full_route["unit"] == "route condition"
    assert "bp / USD bn" not in full_route["unit"]


def test_srf_persistent_nontechnical_use_precedes_latest_technical_exercise(publication):
    bundle = load_config_bundle()
    metric = deepcopy(publication.snapshot["metrics"]["srf_accepted"])
    metric["value"] = 0.0
    series = [
        {"date": "2026-01-01", "value": 1.0, "classification_complete": True,
         "alert_eligible_accepted_amount_usd_bn": 1.0, "technical_exercise": False},
        {"date": "2026-01-02", "value": 1.0, "classification_complete": True,
         "alert_eligible_accepted_amount_usd_bn": 1.0, "technical_exercise": False},
        {"date": "2026-01-03", "value": 0.0, "classification_complete": True,
         "alert_eligible_accepted_amount_usd_bn": 0.0, "technical_exercise": True},
    ]
    result = _srf(
        bundle.interpretation_by_id["srf_accepted"], metric, series,
        video_config=bundle.alert_rules["alerts"]["video_p0_model"],
    )
    assert result["state"] == "PERSISTENT_USE"
    assert result["severity"] == "RED"


def test_tga_and_fed_assets_classify_against_actual_nearest_rank_thresholds(publication):
    assert _tga_flow_state(
        {"value": 1.0, "percentile": 1.0, "thresholds": {0.75: 1.0, 0.9: 1.0}},
        0.75, 0.9,
    ) == "LARGE_DRAIN"
    bundle = load_config_bundle()
    metric = deepcopy(publication.snapshot["metrics"]["fed_total_assets"])
    values = [float(index) for index in range(109)]
    metric.update(value=108.0, observation_date="2020-04-18")
    result = _fed_assets(
        bundle.interpretation_by_id["fed_total_assets"], metric, points(values),
        bundle.interpretation_rules["statistics"],
    )
    # All historical 4W impulses equal 4; equality belongs to BROADLY_FLAT.
    assert result["state"] == "BROADLY_FLAT"


def test_exact_17_membership_and_every_other_metric_is_explicit_null(publication):
    metrics = publication.snapshot["metrics"]
    assert {
        metric_id for metric_id, metric in metrics.items()
        if metric["interpretation"] is not None
    } == INTERPRETED_P0_METRIC_IDS
    assert all("interpretation" in metric for metric in metrics.values())
    assert metrics["reserve_balances"]["interpretation"]["rule_basis"] == [
        "VIDEO_SOURCE_RULE", "DASHBOARD_OPERATIONALIZATION", "STATISTICAL_BAND",
    ]


def test_data_state_reconciles_health_and_freshness():
    def metric(status, freshness, value=1.0):
        return {"value": value, "quality": {"status": status, "freshness": freshness}}

    assert _data_state(metric("OK", "FRESH")) == "CURRENT"
    assert _data_state(metric("OK", "LATE")) == "LAST_GOOD"
    assert _data_state(metric("OK", "STALE")) == "STALE"
    assert _data_state(metric("NOT_RELEASED_YET", "LATE")) == "LAST_GOOD"
    assert _data_state(metric("ERROR", "UNKNOWN")) == "UNKNOWN"
    assert _data_state(metric("OK", "FRESH", None)) == "UNKNOWN"


def test_config_locks_exact_metric_semantics():
    bundle = load_config_bundle()
    rules = deepcopy(bundle.interpretation_rules)
    next(item for item in rules["metrics"] if item["metric_id"] == "sofr")["role"] = "CROSS_CHECK"
    with pytest.raises(ConfigValidationError, match="contract is invalid"):
        validate_config_bundle(replace(bundle, interpretation_rules=rules))


def test_primary_view_and_direction_window_are_live_config_inputs(publication):
    bundle = load_config_bundle()
    records = deepcopy(publication.snapshot["metrics"])
    series = {
        key: value["observations"] for key, value in publication.series_by_id.items()
    }
    rules = deepcopy(bundle.interpretation_rules)
    by_id = {item["metric_id"]: item for item in rules["metrics"]}
    by_id["sofr"]["primary_view"] = "PERCENTILE_GAUGE"
    with pytest.raises(ValueError, match="primary view"):
        build_metric_interpretations(
            metric_records=records,
            series_by_id=series,
            rules=rules,
            alert_rules=bundle.alert_rules,
        )

    rules = deepcopy(bundle.interpretation_rules)
    by_id = {item["metric_id"]: item for item in rules["metrics"]}
    by_id["sofr"]["direction_window"] = "FIVE_OBSERVATIONS"
    records["sofr"]["changes"]["one_observation"] = -1.0
    records["sofr"]["changes"]["five_observations"] = 1.0
    result = build_metric_interpretations(
        metric_records=records,
        series_by_id=series,
        rules=rules,
        alert_rules=bundle.alert_rules,
    )
    assert result["sofr"]["numeric_direction"] == "RISING"
    assert result["sofr"]["views"][0]["change"] == 1.0


@pytest.mark.parametrize("mutation", [
    lambda snapshot: snapshot["metrics"]["sofr"].pop("interpretation"),
    lambda snapshot: snapshot["metrics"]["sofr"].update(interpretation=None),
    lambda snapshot: snapshot["metrics"]["gamma_flip"].update(
        interpretation=deepcopy(snapshot["metrics"]["sofr"]["interpretation"])
    ),
    lambda snapshot: snapshot["metrics"]["sofr"]["interpretation"].update(role="ARBITRARY"),
    lambda snapshot: snapshot["metrics"]["sofr"]["interpretation"].update(extra="x"),
    lambda snapshot: snapshot["metrics"]["sofr"]["interpretation"].update(
        rule_basis=["VALIDATED_SIGNAL"]
    ),
    lambda snapshot: snapshot["metrics"]["sofr"]["interpretation"]["views"][0].update(
        basis="VALIDATED_SIGNAL"
    ),
    lambda snapshot: snapshot["metrics"]["reserve_balances"]["interpretation"].update(
        rule_basis=["VIDEO_SOURCE_RULE", "STATISTICAL_BAND"]
    ),
    lambda snapshot: snapshot["metrics"]["reserve_balances"]["interpretation"].update(
        rule_basis=["VIDEO_SOURCE_RULE", "DASHBOARD_OPERATIONALIZATION", "STATISTICAL_BAND", "CONTEXT_ONLY"]
    ),
    lambda snapshot: snapshot["metrics"]["sofr_iorb_spread_bp"]["interpretation"]["views"][1]["members"].reverse(),
    lambda snapshot: snapshot["metrics"]["sofr_iorb_spread_bp"]["interpretation"]["views"][1]["members"][0].update(
        metric_id="obfr_iorb_spread_bp"
    ),
])
def test_snapshot_strict_interpretation_contract_fails_closed(publication, mutation):
    snapshot = deepcopy(publication.snapshot)
    mutation(snapshot)
    with pytest.raises(ContractValidationError):
        validate_snapshot(snapshot)


@pytest.mark.parametrize("mutation", [
    lambda snapshot: snapshot["metrics"]["sofr"]["interpretation"].update(
        headline="Non-empty tampered headline"
    ),
    lambda snapshot: snapshot["metrics"]["sofr_iorb_spread_bp"]["interpretation"].update(
        state="TAMPERED"
    ),
    lambda snapshot: snapshot["metrics"]["sofr_iorb_spread_bp"]["interpretation"].update(
        next_boundary=None
    ),
    lambda snapshot: snapshot["metrics"]["sofr_iorb_spread_bp"]["interpretation"]["views"][1]["members"][0].update(
        state="TAMPERED"
    ),
])
def test_publication_semantically_recomputes_interpretation(publication, mutation):
    snapshot = deepcopy(publication.snapshot)
    mutation(snapshot)
    with pytest.raises(ContractValidationError, match="interpretation does not reconcile"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


def test_interpretation_builder_cannot_mutate_alert_or_formula_truth(publication):
    snapshot = deepcopy(publication.snapshot)
    alerts = deepcopy(snapshot["alerts"])
    formula_truth = {
        key: value["triggered"]
        for key, value in snapshot["decision_models"]["p0_video_liquidity"]["formulas"].items()
    }
    bundle = load_config_bundle()
    build_metric_interpretations(
        metric_records=snapshot["metrics"],
        series_by_id={key: value["observations"] for key, value in publication.series_by_id.items()},
        rules=bundle.interpretation_rules,
        alert_rules=bundle.alert_rules,
    )
    assert snapshot["alerts"] == alerts
    assert {
        key: value["triggered"]
        for key, value in snapshot["decision_models"]["p0_video_liquidity"]["formulas"].items()
    } == formula_truth
