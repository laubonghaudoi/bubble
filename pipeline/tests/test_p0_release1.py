import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from pipeline.rules.p0 import liquidity_alert_rule, weakest_input_status
from pipeline.transforms.p0 import (
    add_large_settlement_context,
    aggregate_srf_operations,
    aggregate_treasury_settlements,
    build_iorb_spreads,
    h41_change_4w_context,
    h41_weekly_stats,
    observation_period_end_flags,
    on_rrp_near_floor_context,
    reviewed_tax_window_events,
    srf_nontechnical_positive_use_streak,
    spread_observation_stats,
)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_backward_asof_iorb_spreads_do_not_interpolate():
    rates = {
        metric_id: [
            {"date": "2026-08-07", "value": 5.31},
            {"date": "2026-08-10", "value": 5.33},
        ]
        for metric_id in ("sofr", "effr", "obfr", "tgcr", "bgcr")
    }
    spreads = build_iorb_spreads(
        rates,
        [
            {"date": "2026-08-07", "value": 5.30},
            {"date": "2026-08-11", "value": 5.35},
        ],
    )

    assert set(spreads) == {
        "sofr_iorb_spread_bp",
        "effr_iorb_spread_bp",
        "obfr_iorb_spread_bp",
        "tgcr_iorb_spread_bp",
        "bgcr_iorb_spread_bp",
    }
    monday = spreads["sofr_iorb_spread_bp"][-1]
    assert monday == {
        "date": "2026-08-10",
        "value": 3.0,
        "market_rate_pct": 5.33,
        "iorb_pct": 5.3,
        "iorb_observation_date": "2026-08-07",
    }


def test_spread_stats_use_effective_observations_and_true_contiguous_streaks():
    stats = spread_observation_stats(
        [
            {"date": "2026-08-01", "value": 8.0},
            {"date": "2026-08-02", "value": -1.0},
            {"date": "2026-08-03", "value": 0.0},
            {"date": "2026-08-04", "value": 1.0},
            {"date": "2026-08-05", "value": 2.0},
            {"date": "2026-08-06", "value": None},
            {"date": "2026-08-07", "value": 4.0},
        ]
    )

    assert stats == {
        "latest": 4.0,
        "change_1obs": 2.0,
        "change_5obs": -4.0,
        "mean_5obs": 1.2,
        "slope_5obs_bp_per_obs": 1.2,
        "positive_streak": 3,
        "above_3bp_streak": 1,
        "observations_used": 5,
    }


def test_h41_stats_are_weekly_observation_changes():
    observations = [
        {"date": f"2026-07-{day:02d}", "value": value}
        for day, value in zip((2, 9, 16, 23, 30), (3000, 2990, 2985, 2970, 2960))
    ]
    assert h41_weekly_stats(observations) == {
        "level": 2960.0,
        "change_1w": -10.0,
        "change_4w": -40.0,
        "observations_used": 5,
    }


def test_h41_four_week_context_uses_prior_trailing_five_year_changes():
    observations = [
        {
            "date": (date(2025, 1, 2) + timedelta(days=7 * index)).isoformat(),
            "value": float(value),
        }
        for index, value in enumerate((100, 99, 98, 97, 96, 94, 93, 91, 90, 85))
    ]
    context = h41_change_4w_context(observations)
    assert context["change_4w"] == -9.0
    assert context["trailing_sample_size"] == 5
    assert context["trailing_5y_p10"] == -6.0


def test_srf_aggregation_dedupes_and_excludes_only_reviewed_operation_ids():
    daily = aggregate_srf_operations(
        fixture("p0_srf_operations.json"),
        exercise_operation_ids={"2026-08-11-AM-READINESS"},
    )

    assert len(daily) == 2
    exercise, ordinary = daily
    assert exercise["date"] == "2026-08-10"
    assert exercise["accepted_amount_usd_bn"] == 0.001
    assert exercise["alert_eligible_accepted_amount_usd_bn"] == 0.0
    assert exercise["exercise_accepted_amount_usd_bn"] == 0.001
    assert exercise["technical_exercise"] is True

    assert ordinary["date"] == "2026-08-11"
    assert ordinary["submitted_amount_usd_bn"] == 3.0
    assert ordinary["accepted_amount_usd_bn"] == 2.0
    assert ordinary["alert_eligible_accepted_amount_usd_bn"] == 2.0
    assert ordinary["operation_count"] == 1
    assert ordinary["exercise_operation_count"] == 0
    assert ordinary["has_technical_exercise"] is False
    assert ordinary["technical_exercise"] is False
    assert ordinary["breakdown"]["agency_mbs"]["accepted_amount_usd_bn"] == 0.5


def test_srf_conflicting_duplicate_fails_closed():
    operations = fixture("p0_srf_operations.json")[:1] * 2
    operations[1] = {**operations[1], "accepted_amount_usd_bn": 0.0}
    with pytest.raises(ValueError, match="conflicting duplicate"):
        aggregate_srf_operations(operations, exercise_operation_ids=set())


def test_srf_operation_allowlist_preserves_regular_use_on_same_day():
    operations = [
        {
            "operation_id": "RP 052726 99",
            "operation_date": "2026-05-27",
            "collateral_type": "treasury",
            "submitted_amount_usd_bn": 0.001,
            "accepted_amount_usd_bn": 0.001,
            "rate_pct": 4.5,
        },
        {
            "operation_id": "RP 052726 REGULAR",
            "operation_date": "2026-05-27",
            "collateral_type": "treasury",
            "submitted_amount_usd_bn": 2.0,
            "accepted_amount_usd_bn": 1.5,
            "rate_pct": 4.5,
        },
    ]
    row = aggregate_srf_operations(
        operations,
        exercise_operation_ids={"RP 052726 99"},
    )[0]
    assert row["accepted_amount_usd_bn"] == 1.501
    assert row["exercise_accepted_amount_usd_bn"] == 0.001
    assert row["alert_eligible_accepted_amount_usd_bn"] == 1.5
    assert row["has_technical_exercise"] is True
    assert row["technical_exercise"] is False


def test_srf_nontechnical_positive_streak_skips_exercises_and_zero_resets():
    observations = [
        {"date": "2026-08-07", "value": 1.0, "technical_exercise": False},
        {"date": "2026-08-10", "value": 0.001, "technical_exercise": True},
        {"date": "2026-08-11", "value": 2.0, "technical_exercise": False},
    ]
    assert srf_nontechnical_positive_use_streak(observations) == 2

    observations.extend(
        [
            {"date": "2026-08-12", "value": 0.0, "technical_exercise": False},
            {"date": "2026-08-13", "value": 0.5, "technical_exercise": False},
        ]
    )
    assert srf_nontechnical_positive_use_streak(observations) == 1


def test_on_rrp_near_floor_is_history_relative_and_requires_twenty_samples():
    insufficient = [
        {"date": (date(2026, 7, 1) + timedelta(days=index)).isoformat(), "value": 20 - index}
        for index in range(19)
    ]
    context = on_rrp_near_floor_context(insufficient)
    assert context["sample_size"] == 19
    assert context["near_floor"] is None

    sufficient = [
        {"date": (date(2026, 7, 1) + timedelta(days=index)).isoformat(), "value": 20 - index}
        for index in range(20)
    ]
    context = on_rrp_near_floor_context(sufficient)
    assert context == {
        "method": "TRAILING_20_OBSERVATION_PERCENTILE",
        "sample_size": 20,
        "percentile_rank": 0.025,
        "near_floor": True,
        "threshold_rule": "BOTTOM_DECILE_WHEN_SAMPLE_SUFFICIENT",
        "interpretation": (
            "History-relative context only, not a danger signal. Falling ON RRP "
            "may cushion QT or TGA growth, or simply reflect more attractive "
            "bill and repo returns."
        ),
    }


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("2026-05-29", ["MONTH_END"]),
        ("2026-06-30", ["MONTH_END", "QUARTER_END"]),
        ("2026-12-31", ["MONTH_END", "QUARTER_END", "YEAR_END"]),
    ],
)
def test_period_end_flags_use_next_actual_observation(target, expected):
    calendar = [
        "2026-05-29",
        "2026-06-01",
        "2026-06-30",
        "2026-07-01",
        "2026-12-31",
        "2027-01-04",
    ]
    assert observation_period_end_flags(target, calendar) == expected


def test_treasury_settlements_dedupe_sum_and_use_trailing_nonzero_p90():
    aggregated = aggregate_treasury_settlements(fixture("p0_treasury_auctions.json"))
    assert aggregated[0] == {
        "date": "2026-08-13",
        "treasury_settlement_usd_bn": 100.0,
        "security_count": 2,
        "auction_keys": [
            ["912797AB1", "2026-08-10", "2026-08-13"],
            ["912797AC9", "2026-08-10", "2026-08-13"],
        ],
    }

    current = date(2026, 8, 13)
    history = [
        {
            "date": (current - timedelta(days=14 * (60 - index))).isoformat(),
            "treasury_settlement_usd_bn": float(index + 1),
        }
        for index in range(60)
    ]
    history.insert(
        0,
        {
            "date": (current - timedelta(days=900)).isoformat(),
            "treasury_settlement_usd_bn": 0.0,
        },
    )
    contextual = add_large_settlement_context(
        [*history, aggregated[0]],
        minimum_nonzero_samples=60,
    )[-1]
    assert contextual["trailing_nonzero_sample_size"] == 60
    assert contextual["trailing_p90_usd_bn"] == 54.1
    assert contextual["large_treasury_settlement"] is True
    assert "LARGE_TREASURY_SETTLEMENT" in contextual["flags"]


def test_tax_windows_require_review_and_use_adjacent_business_days():
    events = reviewed_tax_window_events(
        fixture("p0_tax_dates.json"),
        ["2026-01-30", "2026-02-02", "2026-02-03"],
    )
    assert [item["date"] for item in events] == ["2026-01-30", "2026-02-02", "2026-02-03"]
    assert all(item["flags"] == ["TAX_WINDOW"] for item in events)

    unreviewed = [{**fixture("p0_tax_dates.json")[0], "reviewed": False}]
    with pytest.raises(ValueError, match="explicitly reviewed"):
        reviewed_tax_window_events(unreviewed, ["2026-02-02"])


def test_weakest_status_propagates_deterministically():
    assert weakest_input_status(["ok", "not_released"]) == "NOT_RELEASED_YET"
    assert weakest_input_status(["ok", "stale", "error"]) == "ERROR"
    assert weakest_input_status(["ok", "missing", "stale"]) == "MISSING"
    with pytest.raises(ValueError, match="unsupported input status"):
        weakest_input_status(["ok", "mystery"])

    unavailable = liquidity_alert_rule(
        latest_sofr_iorb_bp=4.0,
        positive_streak=3,
        funding_confirmation_stats={
            "effr": {"change_5obs": 1.0, "slope_5obs_bp_per_obs": 0.2},
        },
        srf_recent_operation_days=[],
        reserve_change_4w=None,
        reserve_trailing_5y_p10=None,
        input_statuses=["OK", "ERROR"],
    )
    assert unavailable["quality_status"] == "ERROR"
    assert unavailable["level"] == "UNAVAILABLE"
    assert unavailable["confidence"] == "LOW"

    for unavailable_status in ("STALE", "NOT_RELEASED_YET"):
        result = liquidity_alert_rule(
            latest_sofr_iorb_bp=-2.0,
            positive_streak=0,
            funding_confirmation_stats={},
            srf_recent_operation_days=[],
            reserve_change_4w=None,
            reserve_trailing_5y_p10=None,
            input_statuses=["OK", unavailable_status],
        )
        assert result["quality_status"] == unavailable_status
        assert result["level"] == "UNAVAILABLE"
        assert result["confidence"] == "LOW"
        assert result["watch_triggered"] is False


def test_alert_rules_are_exact_and_technical_context_only_downgrades_confidence():
    plain = liquidity_alert_rule(
        latest_sofr_iorb_bp=4.0,
        positive_streak=1,
        funding_confirmation_stats={},
        srf_recent_operation_days=[],
        reserve_change_4w=None,
        reserve_trailing_5y_p10=None,
    )
    technical = liquidity_alert_rule(
        latest_sofr_iorb_bp=4.0,
        positive_streak=1,
        funding_confirmation_stats={},
        srf_recent_operation_days=[],
        reserve_change_4w=None,
        reserve_trailing_5y_p10=None,
        technical_flags=["QUARTER_END"],
    )
    assert plain["level"] == technical["level"] == "WATCH"
    assert plain["confidence"] == "HIGH"
    assert technical["confidence"] == "MEDIUM"
    assert technical["watch_triggered"] is True


def test_elevated_and_stress_require_their_independent_evidence_blocks():
    elevated = liquidity_alert_rule(
        latest_sofr_iorb_bp=4.0,
        positive_streak=1,
        funding_confirmation_stats={
            "effr": {"change_5obs": 1.0, "slope_5obs_bp_per_obs": 0.2},
            "tgcr": {"change_5obs": 1.0, "slope_5obs_bp_per_obs": 0.0},
        },
        srf_recent_operation_days=[],
        reserve_change_4w=None,
        reserve_trailing_5y_p10=None,
    )
    assert elevated["level"] == "ELEVATED"

    stress = liquidity_alert_rule(
        latest_sofr_iorb_bp=4.0,
        positive_streak=3,
        funding_confirmation_stats={
            "effr": {"change_5obs": 1.0, "slope_5obs_bp_per_obs": 0.2},
            "tgcr": {"change_5obs": 2.0, "slope_5obs_bp_per_obs": 0.3},
            "bgcr": {"change_5obs": 3.0, "slope_5obs_bp_per_obs": 0.4},
        },
        srf_recent_operation_days=[],
        reserve_change_4w=None,
        reserve_trailing_5y_p10=None,
    )
    assert stress["level"] == "STRESS"
    assert stress["stress_reasons"] == ["MULTIPLE_FUNDING_SPREADS_UP"]

    unconfirmed = liquidity_alert_rule(
        latest_sofr_iorb_bp=4.0,
        positive_streak=0,
        funding_confirmation_stats={},
        srf_recent_operation_days=[
            {"date": "2026-08-08", "accepted_amount_usd_bn": 1.0, "technical_exercise": False},
            {"date": "2026-08-09", "accepted_amount_usd_bn": 1.0, "technical_exercise": False},
        ],
        reserve_change_4w=-100.0,
        reserve_trailing_5y_p10=-50.0,
    )
    assert unconfirmed["level"] == "WATCH"
    assert unconfirmed["stress_triggered"] is False


def test_stress_accepts_srf_two_of_latest_three_but_excludes_technical_days():
    common = {
        "latest_sofr_iorb_bp": 4.0,
        "positive_streak": 0,
        "funding_confirmation_stats": {
            "effr": {"change_5obs": 1.0, "slope_5obs_bp_per_obs": 0.2},
        },
        "reserve_change_4w": None,
        "reserve_trailing_5y_p10": None,
    }
    stress = liquidity_alert_rule(
        **common,
        srf_recent_operation_days=[
            {"date": "2026-08-07", "accepted_amount_usd_bn": 1.0, "technical_exercise": False},
            {"date": "2026-08-10", "accepted_amount_usd_bn": 0.0, "technical_exercise": False},
            {"date": "2026-08-11", "accepted_amount_usd_bn": 2.0, "technical_exercise": False},
        ],
    )
    assert stress["level"] == "STRESS"
    assert stress["srf_positive_operation_days_latest_3"] == 2

    technical = liquidity_alert_rule(
        **common,
        srf_recent_operation_days=[
            {"date": "2026-08-07", "accepted_amount_usd_bn": 1.0, "technical_exercise": True},
            {"date": "2026-08-10", "accepted_amount_usd_bn": 0.0, "technical_exercise": False},
            {"date": "2026-08-11", "accepted_amount_usd_bn": 2.0, "technical_exercise": False},
        ],
    )
    assert technical["level"] == "ELEVATED"
    assert technical["srf_positive_operation_days_latest_3"] == 1


def test_stress_accepts_reserve_change_at_or_below_trailing_five_year_p10():
    result = liquidity_alert_rule(
        latest_sofr_iorb_bp=4.0,
        positive_streak=0,
        funding_confirmation_stats={
            "effr": {"change_5obs": 1.0, "slope_5obs_bp_per_obs": 0.2},
        },
        srf_recent_operation_days=[],
        reserve_change_4w=-50.0,
        reserve_trailing_5y_p10=-50.0,
    )
    assert result["level"] == "STRESS"
    assert result["reserve_4w_at_or_below_trailing_5y_p10"] is True


def test_obfr_cannot_be_used_as_confirmation():
    with pytest.raises(ValueError, match="unsupported funding confirmations"):
        liquidity_alert_rule(
            latest_sofr_iorb_bp=4.0,
            positive_streak=0,
            funding_confirmation_stats={
                "obfr": {"change_5obs": 1.0, "slope_5obs_bp_per_obs": 0.2},
            },
            srf_recent_operation_days=[],
            reserve_change_4w=None,
            reserve_trailing_5y_p10=None,
        )
