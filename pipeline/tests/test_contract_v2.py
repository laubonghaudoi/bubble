import copy
import json
from pathlib import Path

import pytest

from pipeline.config import (
    CANONICAL_P0_METRIC_IDS,
    ConfigValidationError,
    SourceNotNetworkEligible,
    assert_metric_network_eligible,
    assert_source_network_eligible,
    effective_metric_state,
    load_config_bundle,
    validate_config_bundle,
)
from pipeline.contracts import (
    METHODOLOGY_FIELDS,
    ContractValidationError,
    validate_manifest,
    validate_alerts_file,
    validate_events_file,
    validate_publication,
    validate_series_file,
    validate_snapshot,
)
from pipeline.rules.p0_video_model import build_video_p0_formula_presentation


FIXTURE = Path(__file__).parent / "fixtures" / "snapshot_v2_minimal.json"
P3_IDS = {
    "hyperscaler_aggregate_cash_capex",
    "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
    "ai_upstream_orders_backlog",
    "customer_prepayments_contract_commitments",
    "take_or_pay_commitments",
}


def fixture_snapshot():
    """Expand the compact JSON seed into the complete locked P1/P2 roster."""

    snapshot = json.loads(FIXTURE.read_text())
    template = snapshot["metrics"]["spx_0dte_share"]
    p1_held_ids = {
        "vix_vix3m_term_structure_proxy",
        "cboe_skew_tail_risk_proxy",
        "crypto_funding_btc",
        "crypto_funding_eth",
        "trend_following_positioning_proxy",
        "cross_asset_correlation",
    }
    for metric_id in p1_held_ids:
        metric = copy.deepcopy(template)
        metric["metric_id"] = metric_id
        metric["label"] = metric_id
        metric["availability"] = "UNAVAILABLE_FREE"
        snapshot["metrics"][metric_id] = metric

    p2_held_ids = {
        "gamma_flip",
        "spx_0dte_share",
        "finra_margin_debt",
        "spy_holdings_top10_weight_proxy",
        "m2_nasdaq_divergence",
        "ndx_forward_pe",
    }
    for metric_id in p2_held_ids:
        metric = copy.deepcopy(template)
        metric["metric_id"] = metric_id
        metric["label"] = metric_id
        metric["availability"] = "UNAVAILABLE_FREE"
        metric["source"]["source_id"] = None
        snapshot["metrics"][metric_id] = metric

    cftc_ids = {
        "cftc_e_mini_sp500_asset_manager_net_pct_oi": "ACTIVE_FREE",
        "cftc_e_mini_sp500_leveraged_funds_net_pct_oi": "ACTIVE_PROXY",
        "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi": "ACTIVE_FREE",
        "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi": "ACTIVE_PROXY",
    }
    for metric_id, availability in cftc_ids.items():
        metric = copy.deepcopy(template)
        metric.update(
            {
                "metric_id": metric_id,
                "label": metric_id,
                "availability": availability,
                "unit": "percent_open_interest",
                "frequency": "weekly",
                "updated_at": snapshot["generated_at"],
            }
        )
        metric["quality"].update(
            {
                "status": "ERROR",
                "freshness": "UNKNOWN",
                "last_attempt_at": snapshot["generated_at"],
                "failure_reason": "Fixture has no CFTC observations.",
                "sample_size": 0,
            }
        )
        metric["statistics"] = {
            "sample_size": 0,
            "net_position": None,
            "open_interest": None,
            "net_percent_open_interest": None,
            "change_8_weeks": None,
            "change_12_weeks": None,
            "z_score_3_year": None,
            "z_score_3_year_sample_size": 0,
        }
        metric["source"] = {
            "source_id": "cftc_pre",
            "name": "CFTC PRE",
            "url": "https://publicreporting.cftc.gov/",
            "tier": "OFFICIAL",
            "retrieved_at": snapshot["generated_at"],
            "rights_note": "Official CFTC data.",
        }
        is_proxy = availability == "ACTIVE_PROXY"
        metric["context"]["is_proxy"] = is_proxy
        metric["context"]["direction"] = "UNKNOWN"
        metric["methodology"]["proxy_disclosure"] = (
            "CFTC category is a proxy, not every CTA." if is_proxy else ""
        )
        snapshot["metrics"][metric_id] = metric
    snapshot["sources"]["cftc_tff_futures_only"] = {
        "collector_id": "cftc_tff_futures_only",
        "name": "CFTC PRE",
        "url": "https://publicreporting.cftc.gov/",
        "tier": "OFFICIAL",
        "rights_note": "Official CFTC data.",
        "status": "ERROR",
        "freshness": "UNKNOWN",
        "observation_date": None,
        "released_at": None,
        "updated_at": snapshot["generated_at"],
        "last_success_at": None,
        "last_attempt_at": snapshot["generated_at"],
        "expected_next_update": None,
        "failure_reason": "Fixture has no CFTC observations.",
    }
    snapshot["source_health"]["error"] += 1

    macro = copy.deepcopy(template)
    macro.update(
        {
            "metric_id": "nonfinancial_equities_gdp_proxy",
            "label": "Nonfinancial corporate equities / GDP proxy",
            "availability": "ACTIVE_PROXY",
            "unit": "percent",
            "frequency": "quarterly",
            "updated_at": snapshot["generated_at"],
        }
    )
    macro["changes"]["one_quarter"] = None
    macro["statistics"] = {
        "equity_usd_bn": None,
        "gdp_usd_bn": None,
        "qoq_percent_change": None,
        "yoy_percent_change": None,
        "percentile_10y": None,
        "percentile_10y_sample_size": 0,
    }
    macro["quality"].update(
        {
            "status": "ERROR",
            "freshness": "UNKNOWN",
            "last_attempt_at": snapshot["generated_at"],
            "failure_reason": "Fixture has no P2 macro observations.",
            "sample_size": 0,
        }
    )
    macro["context"].update(
        {
            "is_proxy": True,
            "equity_observation_date": None,
            "gdp_observation_date": None,
            "common_quarter": None,
        }
    )
    macro["source"] = {
        "source_id": "fred_government",
        "name": "FRED government-origin series",
        "url": "https://fred.stlouisfed.org/",
        "tier": "OFFICIAL_DISTRIBUTOR",
        "retrieved_at": snapshot["generated_at"],
        "rights_note": "Government-origin series distributed by FRED.",
    }
    macro["methodology"]["proxy_disclosure"] = (
        "This stock-to-flow ratio is context only and is not public-market capitalization."
    )
    snapshot["metrics"][macro["metric_id"]] = macro

    form4 = copy.deepcopy(template)
    form4.update(
        {
            "metric_id": "sec_form4_nonderivative_ps_count_ratio_20d",
            "label": "SEC Form 4 reported P/S count ratio · 20D proxy",
            "availability": "ACTIVE_PROXY",
            "unit": "ratio",
            "frequency": "business_daily",
            "updated_at": snapshot["generated_at"],
        }
    )
    form4["statistics"] = {
        "ratio_5d": None,
        "count_ratio_20d": None,
        "purchase_count_5d": 0,
        "sale_count_5d": 0,
        "purchase_count_20d": 0,
        "sale_count_20d": 0,
        "dollar_ratio_5d": None,
        "dollar_ratio_20d": None,
        "dollar_coverage_rate_5d": None,
        "dollar_coverage_rate_20d": None,
        "ex_explicit_false_count_ratio_5d": None,
        "ex_explicit_false_count_ratio_20d": None,
        "ex_explicit_false_coverage_5d": None,
        "ex_explicit_false_coverage_20d": None,
        "eligible_transaction_count_20d": 0,
        "priced_transaction_count_20d": 0,
        "unique_accessions_20d": 0,
        "unique_issuers_20d": 0,
        "filings_processed_20d": 0,
        "form4_count_20d": 0,
        "form4a_count_20d": 0,
        "amendments_linked_20d": 0,
        "amendments_review_count_20d": 0,
        "parse_failures_20d": 0,
        "tenb5_true_filings_20d": 0,
        "tenb5_false_filings_20d": 0,
        "tenb5_unknown_filings_20d": 0,
    }
    form4["quality"].update(
        {
            "status": "ERROR",
            "freshness": "UNKNOWN",
            "last_attempt_at": snapshot["generated_at"],
            "failure_reason": "Fixture has no SEC Form 4 completed index day.",
            "sample_size": 0,
        }
    )
    form4["context"].update(
        {
            "is_proxy": True,
            "window_start_5d": None,
            "window_end_5d": None,
            "window_start_20d": None,
            "window_end_20d": None,
            "dollar_status_5d": "INSUFFICIENT_DAYS",
            "dollar_status_20d": "INSUFFICIENT_DAYS",
            "ex_10b5_scope": "EXPLICIT_FALSE_ONLY",
        }
    )
    form4["source"] = {
        "source_id": "sec_edgar",
        "name": "SEC EDGAR daily index and Form 4 filings",
        "url": "https://www.sec.gov/Archives/edgar/daily-index/",
        "tier": "OFFICIAL",
        "retrieved_at": snapshot["generated_at"],
        "rights_note": "Official public filing records.",
    }
    form4["methodology"]["proxy_disclosure"] = (
        "P/S counts include qualifying open-market or private Form 4 transactions."
    )
    snapshot["metrics"][form4["metric_id"]] = form4

    for collector_id, metric in (
        ("fred_nonfinancial_equities_gdp", macro),
        ("sec_form4_daily_index", form4),
    ):
        snapshot["sources"][collector_id] = {
            "collector_id": collector_id,
            "name": metric["source"]["name"],
            "url": metric["source"]["url"],
            "tier": metric["source"]["tier"],
            "rights_note": metric["source"]["rights_note"],
            "status": metric["quality"]["status"],
            "freshness": metric["quality"]["freshness"],
            "observation_date": metric["observation_date"],
            "released_at": metric["released_at"],
            "updated_at": metric["updated_at"],
            "last_success_at": metric["quality"]["last_success_at"],
            "last_attempt_at": metric["quality"]["last_attempt_at"],
            "expected_next_update": metric["expected_next_update"],
            "failure_reason": metric["quality"]["failure_reason"],
        }
    p3_statistics = {
        "aggregate_cash_capex_usd_bn": None,
        "qoq_percent_change": None,
        "yoy_percent_change": None,
        "qoq_acceleration_pp": None,
        "yoy_acceleration_pp": None,
        "company_breadth": 0,
        "company_total": 4,
        "company_breadth_ratio": None,
        "finance_lease_disclosure_breadth": 0,
        "manual_review_count": 0,
        "quarter_count": 0,
    }
    p3_details = {
        "fundamental": {
            "aggregate_direction": "UNKNOWN",
            "company_breadth": 0,
            "company_total": 4,
            "companies": [],
            "caveats": ["No last-good P3 Company Facts observations are available."],
        }
    }
    for metric_id, unit in (
        ("hyperscaler_aggregate_cash_capex", "USD bn"),
        (
            "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
            "percentage_points",
        ),
    ):
        metric = copy.deepcopy(template)
        metric.update(
            {
                "metric_id": metric_id,
                "label": metric_id,
                "availability": "ACTIVE_FREE",
                "unit": unit,
                "frequency": "quarterly",
                "updated_at": snapshot["generated_at"],
                "expected_next_update": None,
                "statistics": copy.deepcopy(p3_statistics),
                "details": copy.deepcopy(p3_details),
            }
        )
        metric["changes"] = {
            "one_observation": None,
            "five_observations": None,
            "twenty_observations": None,
            "eight_weeks": None,
            "twelve_weeks": None,
            "one_quarter": None,
        }
        metric["quality"].update(
            {
                "status": "ERROR",
                "freshness": "UNKNOWN",
                "last_attempt_at": snapshot["generated_at"],
                "last_success_at": None,
                "failure_reason": "Fixture has no SEC Company Facts observations.",
                "sample_size": 0,
            }
        )
        metric["context"].update(
            {"is_proxy": False, "direction": "UNKNOWN", "technical_flags": []}
        )
        metric["source"] = {
            "source_id": "sec_edgar",
            "name": "SEC EDGAR APIs and filing data",
            "url": "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
            "tier": "OFFICIAL",
            "retrieved_at": snapshot["generated_at"],
            "rights_note": "Cite the filing and accession; do not republish long issuer-authored passages.",
        }
        metric["methodology"]["proxy_disclosure"] = ""
        metric["provenance"] = [copy.deepcopy(metric["source"])]
        metric["unavailability_reason"] = None
        snapshot["metrics"][metric_id] = metric
    for metric_id in (
        "ai_upstream_orders_backlog",
        "customer_prepayments_contract_commitments",
        "take_or_pay_commitments",
    ):
        metric = copy.deepcopy(template)
        metric.update(
            {
                "metric_id": metric_id,
                "label": metric_id,
                "availability": "MANUAL_READY",
                "unit": "mixed",
                "frequency": "quarterly",
                "observation_date": None,
                "released_at": None,
                "updated_at": None,
                "expected_next_update": None,
                "statistics": {},
            }
        )
        metric["changes"]["one_quarter"] = None
        metric["changes"]["twenty_observations"] = None
        metric["quality"].update(
            {
                "status": "NOT_APPLICABLE",
                "freshness": "UNKNOWN",
                "last_attempt_at": None,
                "last_success_at": None,
                "failure_reason": "Reviewed manual filing evidence is not yet available.",
                "sample_size": None,
            }
        )
        metric["context"].update(
            {"is_proxy": False, "direction": "UNKNOWN", "technical_flags": []}
        )
        metric["source"] = {
            "source_id": "manual_public_filings",
            "name": "Human-reviewed public filings",
            "url": "https://www.sec.gov/search-filings",
            "tier": "OFFICIAL",
            "retrieved_at": None,
            "rights_note": "Publish short factual paraphrases with filing URLs and accessions.",
        }
        metric["methodology"]["proxy_disclosure"] = ""
        metric["provenance"] = [copy.deepcopy(metric["source"])]
        metric["unavailability_reason"] = (
            "Disclosure definitions require human review."
        )
        snapshot["metrics"][metric_id] = metric
    snapshot["sources"]["sec_companyfacts_capex"] = {
        "collector_id": "sec_companyfacts_capex",
        "name": "SEC EDGAR APIs and filing data",
        "url": "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
        "tier": "OFFICIAL",
        "rights_note": "Cite the filing and accession; do not republish long issuer-authored passages.",
        "status": "ERROR",
        "freshness": "UNKNOWN",
        "observation_date": None,
        "released_at": None,
        "updated_at": snapshot["generated_at"],
        "last_success_at": None,
        "last_attempt_at": snapshot["generated_at"],
        "expected_next_update": None,
        "failure_reason": "Fixture has no SEC Company Facts observations.",
    }
    snapshot["switches"]["fundamental_exit"] = {
        "mode": "EVIDENCE_ONLY",
        "assessment": None,
        "available_blocks": 0,
        "total_blocks": 4,
        "confidence": "UNKNOWN",
        "evidence_blocks": [
            {
                "id": "aggregate_capex_acceleration",
                "label": "Aggregate CapEx acceleration",
                "available": False,
                "triggered": None,
                "status": "UNAVAILABLE",
                "direction": "UNKNOWN",
                "confidence": "UNKNOWN",
                "summary": "Fixture has no SEC Company Facts observations.",
            },
            {
                "id": "orders_backlog",
                "label": "Orders / backlog",
                "available": False,
                "triggered": None,
                "status": "MANUAL_READY",
                "direction": "UNKNOWN",
                "confidence": "UNKNOWN",
                "summary": "No reviewed manual row.",
            },
            {
                "id": "prepayments_commitments",
                "label": "Prepayments / commitments",
                "available": False,
                "triggered": None,
                "status": "MANUAL_READY",
                "direction": "UNKNOWN",
                "confidence": "UNKNOWN",
                "summary": "No reviewed manual row.",
            },
            {
                "id": "company_breadth",
                "label": "Company breadth",
                "available": False,
                "triggered": None,
                "status": "UNAVAILABLE",
                "direction": "UNKNOWN",
                "confidence": "UNKNOWN",
                "summary": "Fixture has no company breadth.",
            },
        ],
        "summary": "Evidence only.",
    }
    snapshot["sources"].pop("manual_spx_0dte", None)
    p0_source = snapshot["sources"].pop("nyfed_markets")
    for collector_id in (
        "nyfed_rates",
        "fred_iorb",
        "fred_h41",
        "treasury_tga",
        "nyfed_on_rrp",
        "nyfed_srf",
        "treasury_auctions",
    ):
        source = copy.deepcopy(p0_source)
        source["collector_id"] = collector_id
        snapshot["sources"][collector_id] = source
    snapshot.update(
        {
            "active_free_count": 5,
            "active_proxy_count": 4,
            "manual_ready_count": 3,
            "unavailable_free_count": 12,
        }
    )
    snapshot["source_health"] = {
        "ok": 7,
        "stale": 0,
        "error": 4,
        "not_released_yet": 0,
        "not_applicable": 0,
    }
    # The compact fixture is for the pre-video metric/switch contract.  Build a
    # deliberately disabled required 2.2 decision model so those tests can keep
    # exercising their original axis while the model itself has dedicated
    # rule/contract tests.
    metric_template = snapshot["metrics"]["on_rrp_accepted"]
    unknown_clause_specs = (
        ("sofr_positive_streak", 1, "sofr_iorb_spread_bp", ">=", 3, "observations"),
        ("reserve_below_yellow", 2, "reserve_balances", "<", 2900, "USD bn"),
        ("reserve_change_4w_negative", 3, "reserve_balances", "<", 0, "USD bn"),
        ("tga_near_1t", 4, "tga_daily", ">=", 950, "USD bn"),
        ("sofr_spread_above_red", 1, "sofr_iorb_spread_bp", ">", 3, "bp"),
        ("reserve_below_red", 2, "reserve_balances", "<", 2800, "USD bn"),
        ("srf_positive_days", 3, "srf_accepted", ">=", 2, "days in latest 3 completed days"),
        ("reserve_below_extreme", 1, "reserve_balances", "<", 2500, "USD bn"),
        ("reserve_rapid_decline", 2, "reserve_balances", "<=", None, "USD bn"),
        ("no_major_crisis", 3, None, "=", "NO_MAJOR_CRISIS", None),
    )
    clauses = {}
    for clause_id, order, metric_id, operator, threshold, threshold_unit in unknown_clause_specs:
        clauses[clause_id] = {
            "clause_id": clause_id,
            "order": order,
            "label": clause_id,
            "metric_id": metric_id,
            "operator": operator,
            "threshold": threshold,
            "threshold_unit": threshold_unit,
            "current_value": None,
            "current_unit": threshold_unit,
            "met": None,
            "observation_date": None,
            "released_at": None,
            "quality_status": "NOT_APPLICABLE",
            "freshness": "UNKNOWN",
            "evaluation_state": "DISABLED",
            "basis": [
                {"kind": "VIDEO_SOURCE_RULE", "label": "Cited rule", "source_segment_id": "yellow_red", "note": "Disabled fixture."},
                {"kind": "MANUAL_CONTEXT" if metric_id is None else "DASHBOARD_OPERATIONALIZATION", "label": "Disabled", "source_segment_id": "yellow_red", "note": "Disabled fixture."},
            ],
            "note": "",
        }
    yellow = [clauses[key] for key in ("sofr_positive_streak", "reserve_below_yellow", "reserve_change_4w_negative", "tga_near_1t")]
    red = [clauses[key] for key in ("sofr_spread_above_red", "reserve_below_red", "srf_positive_days")]
    extreme = [clauses[key] for key in ("reserve_below_extreme", "reserve_rapid_decline", "no_major_crisis")]
    presentation = build_video_p0_formula_presentation(
        streak_required=3,
        yellow_reserve_tn=2.9,
        red_reserve_tn=2.8,
        extreme_reserve_tn=2.5,
        tga_floor_tn=0.95,
        tga_target_tn=1.0,
        spread_threshold=3.0,
        srf_required=2,
        srf_window=3,
    )
    video_url = "https://www.youtube.com/watch?v=MrnjBdgQPLU"
    snapshot["decision_models"] = {"p0_video_liquidity": {
        "model_id": "henren778_p0_liquidity", "label": "影片 P0 黃／紅流動性警報",
        "enabled": False, "status": "UNAVAILABLE", "data_status": "UNAVAILABLE",
        "confidence": "UNKNOWN", "availability_reason": "DISABLED",
        "evaluated_at": snapshot["generated_at"],
        "source": {"title": "一個月前全網喊AI泡沫要崩，我說鬼故事是洗盤不是葬禮，二波窗口鎖死7月底8月初！對賭：納指洗完近一成，道指標普齊創新高，美光單日暴拉18.4%！復盤釘死，二波打法五步三開關全套交付", "display_title": "一個月前全網喊 AI 泡沫要崩", "author": "一个狠人", "url": video_url, "segments": [
            {"segment_id": "yellow_red", "label": "Yellow / Red", "start_seconds": 1380, "end_seconds": 1440, "timestamp_url": f"{video_url}&t=1380s"},
            {"segment_id": "reserve_exit_1", "label": "Reserve I", "start_seconds": 1140, "end_seconds": 1200, "timestamp_url": f"{video_url}&t=1140s"},
            {"segment_id": "reserve_exit_2", "label": "Reserve II", "start_seconds": 1560, "end_seconds": 1620, "timestamp_url": f"{video_url}&t=1560s"},
        ]},
        "thresholds": {
            "yellow": {"spread_positive_bp": 0, "positive_streak_observations": 3, "reserve_usd_bn": 2900, "reserve_change_4w_usd_bn": 0, "tga_operational_floor_usd_bn": 950},
            "red": {"spread_bp": 3, "reserve_usd_bn": 2800, "srf_positive_days_required": 2, "srf_window_completed_days": 3},
            "extreme": {"reserve_usd_bn": 2500, "decline_percentile": "TRAILING_5Y_P10"},
            "tga_source_target_usd_bn": 1000,
        },
        "operationalizations": {"exclude_technical_srf_exercises": True},
        "crisis_context": {"status": "UNKNOWN", "as_of": None, "reviewed_at": None, "reviewer": None, "note": None},
        "notation": presentation["notation"],
        "formulas": {
            "yellow": {"expression": presentation["yellow"]["expression"], "display_tex": presentation["yellow"]["display_tex"], "plain_language": presentation["yellow"]["plain_language"], "triggered": None, "clauses": yellow},
            "red": {"expression": presentation["red"]["expression"], "display_tex": presentation["red"]["display_tex"], "plain_language": presentation["red"]["plain_language"], "triggered": None, "clauses": red, "routes": [
                {"route_id": "spread_and_reserves", "label": "Route A", "expression": presentation["red"]["route_a_expression"], "triggered": None, "clauses": red[:2]},
                {"route_id": "srf_2_of_3", "label": "Route B", "expression": presentation["red"]["route_b_expression"], "triggered": None, "clauses": red[2:]},
            ]},
            "extreme": {"expression": presentation["extreme"]["expression"], "display_tex": presentation["extreme"]["display_tex"], "plain_language": presentation["extreme"]["plain_language"], "triggered": None, "candidate": None, "context_required": False, "clauses": extreme},
        },
        "technical_flags": [], "notes": ["Disabled fixture."],
    }}
    return snapshot


def test_loads_schema_2_registry_bundle_and_canonical_p0_ids():
    bundle = load_config_bundle()
    assert bundle.metric_registry["schema_version"] == "2.2.0"
    assert bundle.source_registry["schema_version"] == "2.2.0"
    assert CANONICAL_P0_METRIC_IDS <= bundle.metrics_by_id.keys()


def test_every_registry_metric_has_locked_methodology_contract():
    bundle = load_config_bundle()
    for metric in bundle.metrics_by_id.values():
        methodology = metric["methodology"]
        assert METHODOLOGY_FIELDS <= methodology.keys()
        assert isinstance(methodology["confirm_with"], list)
        assert methodology["proxy_disclosure"] == metric["proxy_disclosure"]


def test_release_four_marks_all_phases_implemented_with_manual_interfaces_network_disabled():
    bundle = load_config_bundle()
    assert all(metric["implemented"] for metric in bundle.metrics_by_id.values())
    p3 = {
        metric_id: metric
        for metric_id, metric in bundle.metrics_by_id.items()
        if metric["phase"] == "P3"
    }
    assert {
        metric_id for metric_id, metric in p3.items() if metric["network_enabled"]
    } == {
        "hyperscaler_aggregate_cash_capex",
        "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
    }
    assert all(
        not p3[metric_id]["network_enabled"]
        for metric_id in {
            "ai_upstream_orders_backlog",
            "customer_prepayments_contract_commitments",
            "take_or_pay_commitments",
        }
    )


def test_snapshot_v2_contract_preserves_null_and_zero_distinction():
    snapshot = fixture_snapshot()
    validate_snapshot(snapshot)
    assert snapshot["metrics"]["spx_0dte_share"]["value"] is None

    zero_snapshot = copy.deepcopy(snapshot)
    zero_snapshot["metrics"]["on_rrp_accepted"]["value"] = 0
    validate_snapshot(zero_snapshot)
    assert zero_snapshot["metrics"]["on_rrp_accepted"]["value"] == 0

    invalid = copy.deepcopy(snapshot)
    invalid["metrics"]["spx_0dte_share"]["value"] = 0
    with pytest.raises(ContractValidationError, match="must be null"):
        validate_snapshot(invalid)


def test_contract_axes_reject_legacy_or_conflated_states():
    snapshot = fixture_snapshot()
    snapshot["metrics"]["on_rrp_accepted"]["quality"]["status"] = "missing"
    with pytest.raises(ContractValidationError, match="quality.status"):
        validate_snapshot(snapshot)


def test_statistics_are_numeric_or_null_and_attempt_time_is_utc():
    snapshot = fixture_snapshot()
    snapshot["metrics"]["on_rrp_accepted"]["statistics"]["optional"] = None
    validate_snapshot(snapshot)

    invalid_statistic = copy.deepcopy(snapshot)
    invalid_statistic["metrics"]["on_rrp_accepted"]["statistics"]["trend"] = "down"
    with pytest.raises(ContractValidationError, match="statistics.trend"):
        validate_snapshot(invalid_statistic)

    invalid_attempt = copy.deepcopy(snapshot)
    invalid_attempt["metrics"]["on_rrp_accepted"]["quality"]["last_attempt_at"] = (
        "2026-08-11T14:15:00-04:00"
    )
    with pytest.raises(ContractValidationError, match="must use UTC"):
        validate_snapshot(invalid_attempt)


def test_publication_contract_hard_cuts_v1_and_cross_checks_all_metric_ids():
    snapshot = fixture_snapshot()
    manifest = {
        "schema_version": "2.2.0",
        "generated_at": snapshot["generated_at"],
        "metrics": [
            {
                "metric_id": metric_id,
                "label": metric["label"],
                "unit": metric["unit"],
                "frequency": metric["frequency"],
                    "layer": (
                        "liquidity_fuel"
                        if metric_id == "on_rrp_accepted"
                        else "fundamental_exit"
                        if metric_id
                        in {
                            "hyperscaler_aggregate_cash_capex",
                            "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
                            "ai_upstream_orders_backlog",
                            "customer_prepayments_contract_commitments",
                            "take_or_pay_commitments",
                        }
                        else "market_ignition"
                    ),
                    "phase": (
                        "P0"
                        if metric_id == "on_rrp_accepted"
                        else "P3"
                        if metric_id
                        in {
                            "hyperscaler_aggregate_cash_capex",
                            "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
                            "ai_upstream_orders_backlog",
                            "customer_prepayments_contract_commitments",
                            "take_or_pay_commitments",
                        }
                        else "P2"
                    ),
                "role": "evidence",
                "availability": metric["availability"],
                "series_path": f"data/series/{metric_id}.json",
            }
            for metric_id, metric in snapshot["metrics"].items()
        ],
    }
    series = {
        metric_id: {
            "schema_version": "2.2.0",
            "metric_id": metric_id,
            "label": metric["label"],
            "unit": metric["unit"],
            "frequency": metric["frequency"],
            "availability": metric["availability"],
            "quality": metric["quality"],
            "observation_date": metric["observation_date"],
            "released_at": metric["released_at"],
                "updated_at": metric["updated_at"],
                "expected_next_update": metric["expected_next_update"],
                "source": metric["source"],
            "observations": metric["short_series"],
        }
        for metric_id, metric in snapshot["metrics"].items()
    }

    validate_manifest(manifest)
    for value in series.values():
        validate_series_file(value)
    validate_publication(snapshot, manifest, series)

    legacy = copy.deepcopy(manifest)
    legacy["schema_version"] = "1.0.0"
    with pytest.raises(ContractValidationError, match="schema_version"):
        validate_manifest(legacy)

    incomplete = dict(series)
    incomplete.pop("spx_0dte_share")
    with pytest.raises(ContractValidationError, match="must match exactly"):
        validate_publication(snapshot, manifest, incomplete)


def test_series_contract_requires_sorted_unique_real_dates():
    snapshot = fixture_snapshot()
    metric = snapshot["metrics"]["on_rrp_accepted"]
    series = {
        "schema_version": "2.2.0",
        "metric_id": metric["metric_id"],
        "label": metric["label"],
        "unit": metric["unit"],
        "frequency": metric["frequency"],
        "availability": metric["availability"],
        "quality": metric["quality"],
        "observation_date": metric["observation_date"],
        "released_at": metric["released_at"],
                "updated_at": metric["updated_at"],
                "expected_next_update": metric["expected_next_update"],
                "source": metric["source"],
        "observations": list(reversed(metric["short_series"])),
    }
    with pytest.raises(ContractValidationError, match="strictly increasing"):
        validate_series_file(series)


def test_publication_cross_checks_contract_critical_metric_fields():
    snapshot = fixture_snapshot()
    manifest = {
        "schema_version": "2.2.0",
        "generated_at": snapshot["generated_at"],
        "metrics": [],
    }
    series = {}
    for metric_id, metric in snapshot["metrics"].items():
        manifest["metrics"].append(
            {
                "metric_id": metric_id,
                "label": metric["label"],
                "unit": metric["unit"],
                "frequency": metric["frequency"],
                "layer": "fundamental_exit" if metric_id in P3_IDS else "liquidity_fuel" if metric_id == "on_rrp_accepted" else "market_ignition",
                "phase": "P3" if metric_id in P3_IDS else "P0" if metric_id == "on_rrp_accepted" else "P2",
                "role": "evidence",
                "availability": metric["availability"],
                "series_path": f"data/series/{metric_id}.json",
            }
        )
        series[metric_id] = {
            "schema_version": "2.2.0",
            "metric_id": metric_id,
            "label": metric["label"],
            "unit": metric["unit"],
            "frequency": metric["frequency"],
            "availability": metric["availability"],
            "quality": metric["quality"],
            "observation_date": metric["observation_date"],
            "released_at": metric["released_at"],
                "updated_at": metric["updated_at"],
                "expected_next_update": metric["expected_next_update"],
                "source": metric["source"],
            "observations": metric["short_series"],
        }
    series["on_rrp_accepted"] = {
        **series["on_rrp_accepted"],
        "unit": "percent",
    }
    with pytest.raises(ContractValidationError, match="unit must match"):
        validate_publication(snapshot, manifest, series)

    series["on_rrp_accepted"] = {
        **series["on_rrp_accepted"],
        "unit": snapshot["metrics"]["on_rrp_accepted"]["unit"],
        "observations": [
            *series["on_rrp_accepted"]["observations"][:-1],
            {
                **series["on_rrp_accepted"]["observations"][-1],
                "value": 999_999,
            },
        ],
    }
    with pytest.raises(ContractValidationError, match="short_series must match"):
        validate_publication(snapshot, manifest, series)


def test_publication_rejects_internally_mixed_switches_and_timestamps():
    snapshot = fixture_snapshot()
    manifest = {
        "schema_version": "2.2.0",
        "generated_at": snapshot["generated_at"],
        "metrics": [],
    }
    series = {}
    for metric_id, metric in snapshot["metrics"].items():
        manifest["metrics"].append(
            {
                "metric_id": metric_id,
                "label": metric["label"],
                "unit": metric["unit"],
                "frequency": metric["frequency"],
                "layer": "fundamental_exit" if metric_id in P3_IDS else "liquidity_fuel" if metric_id == "on_rrp_accepted" else "market_ignition",
                "phase": "P3" if metric_id in P3_IDS else "P0" if metric_id == "on_rrp_accepted" else "P2",
                "role": "evidence",
                "availability": metric["availability"],
                "series_path": f"data/series/{metric_id}.json",
            }
        )
        series[metric_id] = {
            "schema_version": "2.2.0",
            "metric_id": metric_id,
            "label": metric["label"],
            "unit": metric["unit"],
            "frequency": metric["frequency"],
            "availability": metric["availability"],
            "quality": metric["quality"],
            "observation_date": metric["observation_date"],
            "released_at": metric["released_at"],
            "updated_at": metric["updated_at"],
            "source": metric["source"],
            "observations": metric["short_series"],
        }

    bad_count = copy.deepcopy(snapshot)
    bad_count["switches"]["liquidity_fuel"]["available_blocks"] = 0
    with pytest.raises(ContractValidationError, match="available_blocks must equal"):
        validate_publication(bad_count, manifest, series)

    bad_overall = copy.deepcopy(snapshot)
    bad_overall["overall_assessment"] = "STRESS"
    with pytest.raises(ContractValidationError, match="overall_assessment must equal"):
        validate_publication(bad_overall, manifest, series)

    bad_timestamp = copy.deepcopy(manifest)
    bad_timestamp["generated_at"] = "2000-01-01T00:00:00Z"
    with pytest.raises(ContractValidationError, match="generated_at must match"):
        validate_publication(snapshot, bad_timestamp, series)


def test_standalone_alerts_and_events_require_v2_shapes():
    with pytest.raises(ContractValidationError, match="schema_version"):
        validate_alerts_file({"garbage": True})
    with pytest.raises(ContractValidationError, match="events must be a list"):
        validate_events_file(
            {
                "schema_version": "2.2.0",
                "generated_at": "2026-08-12T20:00:00Z",
                "events": "not-a-list",
            }
        )


def test_rights_held_sources_are_not_network_eligible():
    bundle = load_config_bundle()
    for source_id in (
        "fred_third_party",
        "finra_margin",
        "cboe",
        "ssga_spy",
        "coinbase_market_data",
        "bybit_market_data",
        "licensed_provider",
    ):
        source = bundle.sources_by_id[source_id]
        assert source["enabled"] is False
        assert source["network_eligible"] is False
        assert source["rights"]["status"] == "HOLD"
        with pytest.raises(SourceNotNetworkEligible):
            assert_source_network_eligible(bundle, source_id)


def test_metric_rights_gate_prevents_held_source_network_access():
    bundle = load_config_bundle()
    with pytest.raises(SourceNotNetworkEligible):
        assert_metric_network_eligible(bundle, "finra_margin_debt")
    with pytest.raises(SourceNotNetworkEligible):
        assert_metric_network_eligible(bundle, "vix_vix3m_term_structure_proxy")


def test_metric_rights_gate_allows_nyfed_p0_metrics():
    bundle = load_config_bundle()
    sources = assert_metric_network_eligible(bundle, "on_rrp_accepted")
    assert [source["source_id"] for source in sources] == ["nyfed_markets"]


def test_every_canonical_p0_metric_passes_static_rights_gate():
    bundle = load_config_bundle()
    for metric_id in CANONICAL_P0_METRIC_IDS:
        assert assert_metric_network_eligible(bundle, metric_id)


def test_rights_held_p1_interface_stays_null_after_implementation():
    bundle = load_config_bundle()
    metric = bundle.metrics_by_id["vix_vix3m_term_structure_proxy"]
    assert metric["availability"] == "UNAVAILABLE_FREE"
    assert metric["implemented"] is True
    with pytest.raises(SourceNotNetworkEligible):
        assert_metric_network_eligible(bundle, metric["metric_id"])
    state = effective_metric_state(metric)
    assert state.availability.value == "UNAVAILABLE_FREE"
    assert state.health.value == "NOT_APPLICABLE"
    assert state.freshness.value == "UNKNOWN"
    assert state.value is None


def test_implemented_active_metric_defers_quality_to_collector():
    bundle = load_config_bundle()
    state = effective_metric_state(bundle.metrics_by_id["on_rrp_accepted"])
    assert state.availability.value == "ACTIVE_FREE"
    assert state.health is None
    assert state.freshness is None


def test_fred_government_series_are_allowlisted_and_third_party_is_rejected():
    bundle = load_config_bundle()
    assert_metric_network_eligible(bundle, "iorb")
    assert_metric_network_eligible(bundle, "reserve_balances")
    source = bundle.sources_by_id["fred_government"]
    assert source["auth"]["required_env"] == "FRED_API_KEY"
    with pytest.raises(SourceNotNetworkEligible, match="not allowlisted"):
        assert_source_network_eligible(
            bundle, "fred_government", series_ids=["SP500"]
        )


def test_rights_hold_cannot_be_enabled_by_configuration_drift():
    bundle = load_config_bundle()
    source = bundle.sources_by_id["cboe"]
    source["enabled"] = True
    source["network_eligible"] = True
    with pytest.raises(ConfigValidationError, match="rights-held source cboe"):
        validate_config_bundle(bundle)


def test_operational_readiness_calendar_uses_explicit_official_entries():
    bundle = load_config_bundle()
    entries = bundle.nyfed_operational_readiness["exercises"]
    assert {(entry["operation_date"], entry["operation_type"]) for entry in entries} == {
        ("2026-05-13", "ON_RRP"),
        ("2026-05-27", "SRF"),
    }
    assert all(entry["technical_exercise"] is True for entry in entries)
    srf = next(entry for entry in entries if entry["operation_type"] == "SRF")
    assert srf["operation_id"] == "RP 052726 99"

    invalid = copy.deepcopy(bundle)
    invalid_srf = next(
        entry
        for entry in invalid.nyfed_operational_readiness["exercises"]
        if entry["operation_type"] == "SRF"
    )
    invalid_srf.pop("operation_id")
    with pytest.raises(ConfigValidationError, match="requires operation_id"):
        validate_config_bundle(invalid)


def test_alert_and_tax_config_use_locked_sample_and_window_rules():
    bundle = load_config_bundle()
    rules = bundle.alert_rules["alerts"]["technical_context"]
    assert rules["large_treasury_settlement_min_nonzero_samples"] == 60
    assert rules["tax_window_business_days_before"] == 1
    assert rules["tax_window_business_days_after"] == 1
    assert all(
        event["reviewed"] is True
        for event in bundle.us_tax_dates["tax_dates"]
    )
