"""Schema 2.3.0 enums and validation helpers for the data-pipeline contract.

This module is intentionally independent of collectors and snapshot builders so
future releases can adopt the contract incrementally without mutating v1 data.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
import math
import re
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "2.3.0"
INTERPRETED_P0_METRIC_IDS = frozenset(
    {
        "sofr", "iorb", "sofr_iorb_spread_bp", "effr",
        "effr_iorb_spread_bp", "obfr", "obfr_iorb_spread_bp", "tgcr",
        "tgcr_iorb_spread_bp", "bgcr", "bgcr_iorb_spread_bp", "tga_daily",
        "on_rrp_accepted", "srf_accepted", "reserve_balances",
        "fed_total_assets", "tga_weekly_h41",
    }
)
INTERPRETATION_ROLES = frozenset(
    {
        "PRIMARY_FUNDING_PRICE", "POLICY_RATE_ANCHOR",
        "POLICY_ANCHORED_MARKET_RATE", "CONFIRMATION_SPREAD",
        "TREASURY_CASH_FLOW", "LIQUIDITY_BUFFER", "BACKSTOP_FACILITY",
        "RESERVE_STOCK", "BALANCE_SHEET_DRIVER", "CROSS_CHECK",
    }
)
INTERPRETATION_CLASSIFICATIONS = frozenset(
    {
        "NO_HARD_THRESHOLD", "SOURCE_PLUS_OPERATIONAL",
        "SOURCE_PLUS_STATISTICAL", "ROLLING_PERCENTILE", "EVENT_TRIGGER",
        "DIRECTIONAL", "CROSS_CHECK",
    }
)
INTERPRETATION_DATA_STATES = frozenset(
    {"CURRENT", "LAST_GOOD", "STALE", "UNKNOWN"}
)
INTERPRETATION_DIRECTIONS = frozenset(
    {"RISING", "FALLING", "FLAT", "UNKNOWN"}
)
INTERPRETATION_IMPACTS = frozenset(
    {"EASING", "TIGHTENING", "NEUTRAL", "AMBIGUOUS", "POLICY_ANCHOR", "UNKNOWN"}
)
INTERPRETATION_SEVERITIES = frozenset(
    {"NORMAL", "WATCH", "YELLOW", "RED", "EXTREME", "CONTEXT_ONLY", "UNKNOWN"}
)
INTERPRETATION_CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})
INTERPRETATION_RULE_BASES = frozenset(
    {"VIDEO_SOURCE_RULE", "DASHBOARD_OPERATIONALIZATION", "STATISTICAL_BAND", "CONTEXT_ONLY"}
)
INTERPRETATION_BREADTH_METRIC_IDS = (
    "effr_iorb_spread_bp",
    "tgcr_iorb_spread_bp",
    "bgcr_iorb_spread_bp",
)
P1_BLOCK_IDS = (
    "volatility_term_structure",
    "trend_positioning",
    "options_tail_risk",
    "crypto_cross_asset",
)
P1_DIRECTIONS = frozenset(
    {"MORE_NET_LONG", "MORE_NET_SHORT", "FLAT", "MIXED", "UNKNOWN"}
)
P1_CFTC_METRICS = {
    "cftc_e_mini_sp500_asset_manager_net_pct_oi": "ACTIVE_FREE",
    "cftc_e_mini_sp500_leveraged_funds_net_pct_oi": "ACTIVE_PROXY",
    "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi": "ACTIVE_FREE",
    "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi": "ACTIVE_PROXY",
}
P1_CFTC_IDENTITIES = {
    "cftc_e_mini_sp500_asset_manager_net_pct_oi": ("13874A", "E-MINI S&P 500", "asset_manager"),
    "cftc_e_mini_sp500_leveraged_funds_net_pct_oi": ("13874A", "E-MINI S&P 500", "leveraged_funds"),
    "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi": ("20974+", "NASDAQ-100 Consolidated", "asset_manager"),
    "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi": ("20974+", "NASDAQ-100 Consolidated", "leveraged_funds"),
}
P1_CFTC_EXCHANGES = {
    "13874A": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
    "20974+": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
}
P1_HELD_METRICS = frozenset(
    {
        "vix_vix3m_term_structure_proxy",
        "cboe_skew_tail_risk_proxy",
        "crypto_funding_btc",
        "crypto_funding_eth",
        "trend_following_positioning_proxy",
        "cross_asset_correlation",
    }
)

P2_ACTIVE_METRICS = {
    "nonfinancial_equities_gdp_proxy": ("ACTIVE_PROXY", "percent", "quarterly"),
    "sec_form4_nonderivative_ps_count_ratio_20d": (
        "ACTIVE_PROXY",
        "ratio",
        "business_daily",
    ),
}
P2_HELD_METRICS = frozenset(
    {
        "gamma_flip",
        "spx_0dte_share",
        "finra_margin_debt",
        "spy_holdings_top10_weight_proxy",
        "m2_nasdaq_divergence",
        "ndx_forward_pe",
    }
)
P2_RETIRED_METRICS = frozenset(
    {
        "buffett_indicator_proxy",
        "insider_buy_sell_proxy",
        "insider_ratio_proxy",
        "put_call_vol_skew",
        "sp500_top10_weight",
    }
)
P2_MACRO_STATISTICS = frozenset(
    {
        "equity_usd_bn",
        "gdp_usd_bn",
        "qoq_percent_change",
        "yoy_percent_change",
        "percentile_10y",
        "percentile_10y_sample_size",
    }
)
P2_FORM4_STATISTICS = frozenset(
    {
        "ratio_5d",
        "count_ratio_20d",
        "purchase_count_5d",
        "sale_count_5d",
        "purchase_count_20d",
        "sale_count_20d",
        "dollar_ratio_5d",
        "dollar_ratio_20d",
        "dollar_coverage_rate_5d",
        "dollar_coverage_rate_20d",
        "ex_explicit_false_count_ratio_5d",
        "ex_explicit_false_count_ratio_20d",
        "ex_explicit_false_coverage_5d",
        "ex_explicit_false_coverage_20d",
        "eligible_transaction_count_20d",
        "priced_transaction_count_20d",
        "unique_accessions_20d",
        "unique_issuers_20d",
        "filings_processed_20d",
        "form4_count_20d",
        "form4a_count_20d",
        "amendments_linked_20d",
        "amendments_review_count_20d",
        "parse_failures_20d",
        "tenb5_true_filings_20d",
        "tenb5_false_filings_20d",
        "tenb5_unknown_filings_20d",
    }
)
P2_COLLECTOR_SOURCES = {
    "fred_nonfinancial_equities_gdp": (
        "nonfinancial_equities_gdp_proxy",
        "fred_government",
    ),
    "sec_form4_daily_index": (
        "sec_form4_nonderivative_ps_count_ratio_20d",
        "sec_edgar",
    ),
}

P3_AUTOMATED_METRICS = {
    "hyperscaler_aggregate_cash_capex": ("USD bn", "quarterly"),
    "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp": (
        "percentage_points",
        "quarterly",
    ),
}
P3_MANUAL_METRICS = frozenset(
    {
        "ai_upstream_orders_backlog",
        "customer_prepayments_contract_commitments",
        "take_or_pay_commitments",
    }
)
P3_RETIRED_METRICS = frozenset(
    {
        "hyperscaler_capex",
        "capex_acceleration",
        "upstream_backlog",
        "prepayments",
        "take_or_pay",
    }
)
P3_BLOCK_IDS = (
    "aggregate_capex_acceleration",
    "orders_backlog",
    "prepayments_commitments",
    "company_breadth",
)
P3_FUNDAMENTAL_DIRECTIONS = frozenset(
    {"ACCELERATING", "DECELERATING", "FLAT", "UNKNOWN"}
)
P3_MANUAL_DIRECTIONS = frozenset({"UP", "DOWN", "FLAT", "MIXED", "UNKNOWN"})
P3_AUTOMATED_STATISTICS = frozenset(
    {
        "aggregate_cash_capex_usd_bn",
        "qoq_percent_change",
        "yoy_percent_change",
        "qoq_acceleration_pp",
        "yoy_acceleration_pp",
        "company_breadth",
        "company_total",
        "company_breadth_ratio",
        "finance_lease_disclosure_breadth",
        "manual_review_count",
        "quarter_count",
    }
)
P3_COMPANIES = {
    "alphabet": (
        "GOOGL",
        "0001652044",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ),
    "amazon": ("AMZN", "0001018724", "PaymentsToAcquireProductiveAssets"),
    "meta": (
        "META",
        "0001326801",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ),
    "microsoft": (
        "MSFT",
        "0000789019",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ),
}
P3_COMPANY_FISCAL_YEAR_END = {
    "alphabet": (12, 31),
    "amazon": (12, 31),
    "meta": (12, 31),
    "microsoft": (6, 30),
}
P3_COMPANY_FIELDS = frozenset(
    {
        "date",
        "company_id",
        "ticker",
        "cik",
        "fiscal_quarter",
        "calendar_period_end",
        "cash_capex_usd_bn",
        "qoq_percent_change",
        "yoy_percent_change",
        "qoq_acceleration_pp",
        "yoy_acceleration_pp",
        "direction",
        "tag",
        "namespace",
        "unit",
        "accession",
        "form",
        "filed_at",
        "accepted_at",
        "filing_url",
        "frame",
        "context_start",
        "context_end",
        "quarterization_method",
        "manual_review_required",
        "finance_lease_additions_usd_bn",
        "finance_lease_tag",
        "finance_lease_accession",
        "finance_lease_quarterization_method",
    }
)
P3_METRIC_BASE_FIELDS = frozenset(
    {
        "metric_id",
        "label",
        "availability",
        "value",
        "unit",
        "frequency",
        "observation_date",
        "released_at",
        "updated_at",
        "expected_next_update",
        "changes",
        "statistics",
        "quality",
        "context",
        "source",
        "methodology",
        "short_series",
        "interpretation",
        "provenance",
        "unavailability_reason",
    }
)
P3_SWITCH_FIELDS = frozenset(
    {
        "mode",
        "assessment",
        "available_blocks",
        "total_blocks",
        "confidence",
        "summary",
        "evidence_blocks",
    }
)
P3_EVIDENCE_BLOCK_FIELDS = frozenset(
    {
        "id",
        "label",
        "available",
        "triggered",
        "status",
        "summary",
        "direction",
        "confidence",
    }
)
P3_QUALITY_FIELDS = frozenset(
    {
        "status",
        "freshness",
        "last_success_at",
        "last_attempt_at",
        "failure_reason",
        "sample_size",
    }
)
P3_CONTEXT_FIELDS = frozenset(
    {"is_proxy", "confidence", "direction", "technical_flags"}
)
P3_SOURCE_FIELDS = frozenset(
    {"source_id", "name", "url", "tier", "retrieved_at", "rights_note"}
)
P3_FUNDAMENTAL_FIELDS = frozenset(
    {"aggregate_direction", "company_breadth", "company_total", "companies", "caveats"}
)
P3_MANIFEST_FIELDS = frozenset(
    {
        "metric_id",
        "label",
        "unit",
        "frequency",
        "layer",
        "phase",
        "role",
        "availability",
        "series_path",
    }
)
P3_SERIES_FIELDS = frozenset(
    {
        "schema_version",
        "metric_id",
        "label",
        "unit",
        "frequency",
        "availability",
        "quality",
        "observation_date",
        "released_at",
        "updated_at",
        "expected_next_update",
        "source",
        "observations",
    }
)
P3_COLLECTOR_SOURCE_FIELDS = frozenset(
    {
        "collector_id",
        "name",
        "url",
        "tier",
        "rights_note",
        "status",
        "freshness",
        "observation_date",
        "released_at",
        "updated_at",
        "last_success_at",
        "last_attempt_at",
        "expected_next_update",
        "failure_reason",
    }
)
P3_MANUAL_RECORD_FIELDS = frozenset(
    {
        "company_id",
        "period_end",
        "metric_id",
        "direction",
        "value",
        "unit",
        "yoy_pct",
        "comparable",
        "source_type",
        "source_url",
        "filing_accession",
        "filing_accepted_at",
        "as_of",
        "reviewer",
        "reviewed_at",
        "paraphrase",
        "review_note",
    }
)
CANONICAL_COLLECTOR_IDS = frozenset(
    {
        "nyfed_rates",
        "fred_iorb",
        "fred_h41",
        "treasury_tga",
        "nyfed_on_rrp",
        "nyfed_srf",
        "treasury_auctions",
        "cftc_tff_futures_only",
        "fred_nonfinancial_equities_gdp",
        "sec_form4_daily_index",
        "sec_companyfacts_capex",
    }
)
P3_QUARTERIZATION_METHODS = {
    "1": "Q1_YTD",
    "2": "H1_MINUS_Q1",
    "3": "9M_MINUS_H1",
    "4": "FY_MINUS_9M",
}
P3_AUTOMATED_FORMS = frozenset({"10-Q", "10-Q/A", "10-K", "10-K/A"})
P3_AUTOMATED_FORMS_BY_QUARTER = {
    1: frozenset({"10-Q", "10-Q/A"}),
    2: frozenset({"10-Q", "10-Q/A"}),
    3: frozenset({"10-Q", "10-Q/A"}),
    4: frozenset({"10-K", "10-K/A"}),
}
P3_MANUAL_SOURCE_TYPES = frozenset(
    {"10-Q", "10-Q/A", "10-K", "10-K/A", "8-K", "8-K/A", "DEF 14A"}
)
P3_MANUAL_VALUE_UNITS = frozenset(
    {
        "USD",
        "USD mn",
        "USD bn",
        "count",
        "units",
        "percent",
        "percentage_points",
        "ratio",
        "MW",
        "GW",
    }
)
P3_MANUAL_HOST_SUFFIXES = {
    "microsoft": ("sec.gov", "microsoft.com"),
    "alphabet": ("sec.gov", "abc.xyz", "alphabet.com"),
    "amazon": ("sec.gov", "amazon.com", "aboutamazon.com"),
    "meta": ("sec.gov", "meta.com"),
}
P3_MANUAL_MAX_AGE_DAYS = 120
P3_SEC_SOURCE_METADATA = {
    "source_id": "sec_edgar",
    "name": "SEC EDGAR APIs and filing data",
    "url": "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
    "tier": "OFFICIAL",
    "rights_note": "Cite the filing and accession; do not republish long issuer-authored passages.",
}
P3_MANUAL_SOURCE_METADATA = {
    "source_id": "manual_public_filings",
    "name": "Human-reviewed public filings",
    "url": "https://www.sec.gov/search-filings",
    "tier": "OFFICIAL",
    "rights_note": "Publish short factual paraphrases with filing URLs and accessions.",
}


def _p1_direction(change: Any) -> str:
    if change is None:
        return "UNKNOWN"
    if change > 0:
        return "MORE_NET_LONG"
    if change < 0:
        return "MORE_NET_SHORT"
    return "FLAT"


def _same_nullable_number(left: Any, right: Any, *, tolerance: float = 1e-12) -> bool:
    if left is None or right is None:
        return left is right
    return (
        not isinstance(left, bool)
        and not isinstance(right, bool)
        and isinstance(left, (int, float))
        and isinstance(right, (int, float))
        and math.isfinite(float(left))
        and math.isfinite(float(right))
        and abs(float(left) - float(right)) <= tolerance
    )


def _cftc_statistics_from_points(
    points: list[Mapping[str, Any]],
) -> dict[str, int | float | None]:
    if not points:
        return {
            "sample_size": 0,
            "net_position": None,
            "open_interest": None,
            "net_percent_open_interest": None,
            "change_8_weeks": None,
            "change_12_weeks": None,
            "z_score_3_year": None,
            "z_score_3_year_sample_size": 0,
        }
    values = [float(point["net_percent_open_interest_raw"]) for point in points]
    window = values[-156:]
    mean = sum(window) / len(window)
    variance = sum((value - mean) ** 2 for value in window) / len(window)
    deviation = math.sqrt(variance)
    z_score = (
        round((window[-1] - mean) / deviation, 6)
        if len(window) == 156 and deviation != 0
        else None
    )
    return {
        "sample_size": len(points),
        "net_position": points[-1]["net_position"],
        "open_interest": points[-1]["open_interest"],
        "net_percent_open_interest": values[-1],
        "change_8_weeks": (
            round(values[-1] - values[-9], 6) if len(values) > 8 else None
        ),
        "change_12_weeks": (
            round(values[-1] - values[-13], 6) if len(values) > 12 else None
        ),
        "z_score_3_year": z_score,
        "z_score_3_year_sample_size": min(len(points), 156),
    }


def _p2_macro_quarter(value: Any, *, path: str) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ContractValidationError(f"{path} must be YYYY-Q1 through YYYY-Q4")
    match = re.fullmatch(r"(\d{4})-Q([1-4])", value)
    if match is None:
        raise ContractValidationError(f"{path} must be YYYY-Q1 through YYYY-Q4")
    return int(match.group(1)), int(match.group(2))


def _p2_macro_quarter_ordinal(value: tuple[int, int]) -> int:
    return value[0] * 4 + value[1] - 1


def _p2_macro_quarter_end(value: tuple[int, int]) -> str:
    year, quarter = value
    return date(year, quarter * 3, (31, 30, 30, 31)[quarter - 1]).isoformat()


def _p2_macro_source_date(value: Any, *, path: str) -> tuple[str, tuple[int, int]]:
    _validate_optional_date(value, path)
    if not isinstance(value, str):
        raise ContractValidationError(f"{path} must be an ISO date")
    parsed = date.fromisoformat(value)
    return value, (parsed.year, (parsed.month - 1) // 3 + 1)


def _p2_macro_percent_change(
    current: float | None, previous: float | None
) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current / previous - 1) * 100, 6)


def _p2_macro_midrank(values: list[float], current: float) -> float:
    below = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return round((below + 0.5 * equal) / len(values) * 100, 6)


def _validate_p2_macro_artifacts(
    snapshot_metric: Mapping[str, Any], series: Mapping[str, Any]
) -> None:
    """Recompute every published macro statistic from the full series.

    These checks deliberately use only the serialized artifact.  A matching
    manifest hash or snapshot suffix cannot make a tampered component value,
    rolling statistic, or source-quarter label authoritative.
    """

    points = series["observations"]
    required_fields = {
        "quarter",
        "equity_usd_bn",
        "gdp_usd_bn",
        "change_1_quarter_pp",
        "qoq_percent_change",
        "yoy_percent_change",
        "percentile_10y",
        "percentile_10y_sample_size",
        "equities_source_date",
        "gdp_source_date",
        "equities_realtime_start",
        "equities_realtime_end",
        "gdp_realtime_start",
        "gdp_realtime_end",
    }
    by_ordinal: dict[int, float | None] = {}
    latest: Mapping[str, Any] | None = None
    for index, point in enumerate(points):
        path = f"nonfinancial_equities_gdp_proxy.observations[{index}]"
        missing = required_fields - point.keys()
        if missing:
            raise ContractValidationError(
                f"{path} is missing fields: " + ", ".join(sorted(missing))
            )
        quarter = _p2_macro_quarter(point["quarter"], path=f"{path}.quarter")
        ordinal = _p2_macro_quarter_ordinal(quarter)
        if ordinal in by_ordinal:
            raise ContractValidationError(
                "nonfinancial equities/GDP full series has duplicate quarters"
            )
        if point["date"] != _p2_macro_quarter_end(quarter):
            raise ContractValidationError(
                f"{path}.date must be the labelled calendar-quarter end"
            )
        for field in ("equities_source_date", "gdp_source_date"):
            _, source_quarter = _p2_macro_source_date(
                point[field], path=f"{path}.{field}"
            )
            if source_quarter != quarter:
                raise ContractValidationError(
                    f"{path}.{field} must belong to the exact common quarter"
                )
        for prefix in ("equities", "gdp"):
            start_field = f"{prefix}_realtime_start"
            end_field = f"{prefix}_realtime_end"
            start, _ = _p2_macro_source_date(
                point[start_field], path=f"{path}.{start_field}"
            )
            end, _ = _p2_macro_source_date(
                point[end_field], path=f"{path}.{end_field}"
            )
            if end < start:
                raise ContractValidationError(
                    f"{path} {prefix} realtime interval is inverted"
                )

        numeric_fields = (
            "equity_usd_bn",
            "gdp_usd_bn",
            "change_1_quarter_pp",
            "qoq_percent_change",
            "yoy_percent_change",
            "percentile_10y",
        )
        for field in numeric_fields:
            _validate_nullable_number(point[field], f"{path}.{field}")
        equity = point["equity_usd_bn"]
        gdp = point["gdp_usd_bn"]
        if equity is not None and equity < 0:
            raise ContractValidationError(f"{path}.equity_usd_bn cannot be negative")
        if gdp is not None and gdp < 0:
            raise ContractValidationError(f"{path}.gdp_usd_bn cannot be negative")
        expected_ratio = (
            round(equity / gdp * 100, 6)
            if equity is not None and gdp not in (None, 0)
            else None
        )
        if not _same_nullable_number(point["value"], expected_ratio, tolerance=0.000001):
            raise ContractValidationError(f"{path}.value does not reconcile to components")

        previous_quarter = by_ordinal.get(ordinal - 1)
        previous_year = by_ordinal.get(ordinal - 4)
        current = point["value"]
        expected_change = (
            round(current - previous_quarter, 6)
            if current is not None and previous_quarter is not None
            else None
        )
        if not _same_nullable_number(
            point["change_1_quarter_pp"], expected_change, tolerance=0.000002
        ):
            raise ContractValidationError(
                f"{path}.change_1_quarter_pp does not match the prior exact quarter"
            )
        expected_qoq = _p2_macro_percent_change(current, previous_quarter)
        expected_yoy = _p2_macro_percent_change(current, previous_year)
        if not _same_nullable_number(
            point["qoq_percent_change"], expected_qoq, tolerance=0.000002
        ):
            raise ContractValidationError(f"{path}.qoq_percent_change does not reconcile")
        if not _same_nullable_number(
            point["yoy_percent_change"], expected_yoy, tolerance=0.000002
        ):
            raise ContractValidationError(f"{path}.yoy_percent_change does not reconcile")

        by_ordinal[ordinal] = current
        trailing = [
            value
            for candidate, value in by_ordinal.items()
            if ordinal - 39 <= candidate <= ordinal and value is not None
        ]
        sample_size = point["percentile_10y_sample_size"]
        if (
            isinstance(sample_size, bool)
            or not isinstance(sample_size, int)
            or sample_size != len(trailing)
        ):
            raise ContractValidationError(
                f"{path}.percentile_10y_sample_size does not match the trailing window"
            )
        expected_percentile = (
            _p2_macro_midrank(trailing, current)
            if current is not None and trailing
            else None
        )
        if not _same_nullable_number(
            point["percentile_10y"], expected_percentile, tolerance=0.000002
        ):
            raise ContractValidationError(f"{path}.percentile_10y does not reconcile")
        latest = point

    expected_statistics: dict[str, int | float | None] = {
        "equity_usd_bn": latest["equity_usd_bn"] if latest else None,
        "gdp_usd_bn": latest["gdp_usd_bn"] if latest else None,
        "qoq_percent_change": latest["qoq_percent_change"] if latest else None,
        "yoy_percent_change": latest["yoy_percent_change"] if latest else None,
        "percentile_10y": latest["percentile_10y"] if latest else None,
        "percentile_10y_sample_size": (
            latest["percentile_10y_sample_size"] if latest else 0
        ),
    }
    for field, expected in expected_statistics.items():
        if not _same_nullable_number(
            snapshot_metric["statistics"].get(field), expected, tolerance=0.000002
        ):
            raise ContractValidationError(
                f"nonfinancial_equities_gdp_proxy.statistics.{field} "
                "must match the full-series endpoint"
            )
    expected_change = latest["change_1_quarter_pp"] if latest else None
    if not _same_nullable_number(
        snapshot_metric["changes"].get("one_quarter"),
        expected_change,
        tolerance=0.000002,
    ):
        raise ContractValidationError(
            "nonfinancial_equities_gdp_proxy.changes.one_quarter must match "
            "the full-series endpoint"
        )
    expected_context = {
        "equity_observation_date": latest["equities_source_date"] if latest else None,
        "gdp_observation_date": latest["gdp_source_date"] if latest else None,
        "common_quarter": latest["quarter"] if latest else None,
    }
    if any(
        snapshot_metric["context"].get(field) != expected
        for field, expected in expected_context.items()
    ):
        raise ContractValidationError(
            "nonfinancial_equities_gdp_proxy context must match the full-series endpoint"
        )
    expected_sample_size = sum(point["value"] is not None for point in points)
    if snapshot_metric["quality"].get("sample_size") != expected_sample_size:
        raise ContractValidationError(
            "nonfinancial_equities_gdp_proxy quality.sample_size must match "
            "non-null full-series observations"
        )


def _validate_p2_collector_sources(
    snapshot: Mapping[str, Any],
    metrics: Mapping[str, Any],
    sources: Mapping[str, Any],
) -> None:
    for collector_id, (metric_id, expected_source_id) in P2_COLLECTOR_SOURCES.items():
        if collector_id not in sources:
            raise ContractValidationError(
                f"snapshot.sources.{collector_id} is required for P2"
            )
        source = _require_mapping(
            sources[collector_id], f"snapshot.sources.{collector_id}"
        )
        metric = _require_mapping(metrics[metric_id], f"snapshot.metrics.{metric_id}")
        metric_source = _require_mapping(
            metric.get("source"), f"snapshot.metrics.{metric_id}.source"
        )
        quality = _require_mapping(
            metric.get("quality"), f"snapshot.metrics.{metric_id}.quality"
        )
        if source.get("collector_id") != collector_id:
            raise ContractValidationError(
                f"snapshot.sources.{collector_id}.collector_id must match its key"
            )
        if metric_source.get("source_id") != expected_source_id:
            raise ContractValidationError(
                f"{metric_id}.source.source_id must be {expected_source_id}"
            )
        if metric_source.get("retrieved_at") != quality.get("last_attempt_at"):
            raise ContractValidationError(
                f"{metric_id}.source.retrieved_at must match quality.last_attempt_at"
            )
        for field in ("name", "url", "tier", "rights_note"):
            if source.get(field) != metric_source.get(field):
                raise ContractValidationError(
                    f"snapshot.sources.{collector_id}.{field} must match metric provenance"
                )
        expected_updated = (
            quality.get("last_attempt_at")
            if quality.get("last_attempt_at") == snapshot.get("generated_at")
            else metric.get("updated_at")
        )
        expected_fields = {
            "status": quality.get("status"),
            "freshness": quality.get("freshness"),
            "observation_date": metric.get("observation_date"),
            "released_at": metric.get("released_at"),
            "updated_at": expected_updated,
            "last_success_at": quality.get("last_success_at"),
            "last_attempt_at": quality.get("last_attempt_at"),
            "expected_next_update": metric.get("expected_next_update"),
            "failure_reason": quality.get("failure_reason"),
        }
        if any(
            source.get(field) != expected
            for field, expected in expected_fields.items()
        ):
            raise ContractValidationError(
                f"snapshot.sources.{collector_id} state/provenance must match {metric_id}"
            )


def _p3_direction(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if value > 0:
        return "ACCELERATING"
    if value < 0:
        return "DECELERATING"
    return "FLAT"


def _p3_common_direction(values: list[str]) -> str:
    if not values or "UNKNOWN" in values:
        return "UNKNOWN"
    return values[0] if len(set(values)) == 1 else "MIXED"


def _validate_p3_company(
    value: Any,
    path: str,
    *,
    expected_date: str,
    generated_at: str | None = None,
) -> Mapping[str, Any]:
    company = _require_mapping(value, path)
    if set(company) != P3_COMPANY_FIELDS:
        raise ContractValidationError(f"{path} must use the exact P3 company fields")
    company_id = _require_nonempty_string(company.get("company_id"), f"{path}.company_id")
    if company_id not in P3_COMPANIES:
        raise ContractValidationError(f"{path}.company_id is not a reviewed hyperscaler")
    ticker, cik, tag = P3_COMPANIES[company_id]
    expected = {
        "date": expected_date,
        "ticker": ticker,
        "cik": cik,
        "tag": tag,
        "namespace": "us-gaap",
        "unit": "USD",
        "calendar_period_end": expected_date,
        "context_end": expected_date,
        "manual_review_required": False,
    }
    if any(company.get(field) != expected_value for field, expected_value in expected.items()):
        raise ContractValidationError(f"{path} identity, tag, unit, or period does not match P3 contract")
    for field in (
        "cash_capex_usd_bn",
        "qoq_percent_change",
        "yoy_percent_change",
        "qoq_acceleration_pp",
        "yoy_acceleration_pp",
        "finance_lease_additions_usd_bn",
    ):
        _validate_nullable_number(company.get(field), f"{path}.{field}")
    if company.get("cash_capex_usd_bn") is None or company["cash_capex_usd_bn"] < 0:
        raise ContractValidationError(f"{path}.cash_capex_usd_bn must be non-negative")
    finance_value = company.get("finance_lease_additions_usd_bn")
    if finance_value is not None and finance_value < 0:
        raise ContractValidationError(f"{path}.finance_lease_additions_usd_bn must be non-negative")
    direction = company.get("direction")
    if direction not in P3_FUNDAMENTAL_DIRECTIONS or direction != _p3_direction(
        company.get("yoy_acceleration_pp")
    ):
        raise ContractValidationError(f"{path}.direction must match YoY acceleration")
    for field in (
        "fiscal_quarter",
        "accession",
        "form",
        "filing_url",
        "quarterization_method",
    ):
        _require_nonempty_string(company.get(field), f"{path}.{field}")
    fiscal_quarter = re.fullmatch(r"FY(\d{4})Q([1-4])", company["fiscal_quarter"])
    if fiscal_quarter is None:
        raise ContractValidationError(f"{path}.fiscal_quarter is invalid")
    calendar_end = date.fromisoformat(expected_date)
    quarter_days = {3: 31, 6: 30, 9: 30, 12: 31}
    if (
        calendar_end.month not in quarter_days
        or calendar_end.day != quarter_days[calendar_end.month]
    ):
        raise ContractValidationError(f"{path}.calendar_period_end is not a quarter end")
    if P3_COMPANY_FISCAL_YEAR_END[company_id] == (12, 31):
        expected_fiscal_year = calendar_end.year
        expected_fiscal_quarter = calendar_end.month // 3
    else:
        expected_fiscal_year = (
            calendar_end.year + 1 if calendar_end.month > 6 else calendar_end.year
        )
        expected_fiscal_quarter = {9: 1, 12: 2, 3: 3, 6: 4}.get(
            calendar_end.month
        )
    if (
        expected_fiscal_quarter is None
        or int(fiscal_quarter.group(1)) != expected_fiscal_year
        or int(fiscal_quarter.group(2)) != expected_fiscal_quarter
    ):
        raise ContractValidationError(
            f"{path}.fiscal_quarter does not match issuer fiscal calendar"
        )
    expected_quarterization = P3_QUARTERIZATION_METHODS[
        str(expected_fiscal_quarter)
    ]
    if company["form"] not in P3_AUTOMATED_FORMS:
        raise ContractValidationError(f"{path}.form is not an allowed Company Facts filing")
    if company["form"] not in P3_AUTOMATED_FORMS_BY_QUARTER[
        expected_fiscal_quarter
    ]:
        raise ContractValidationError(f"{path}.form does not match fiscal_quarter")
    if company["quarterization_method"] != expected_quarterization:
        raise ContractValidationError(
            f"{path}.quarterization_method does not match fiscal_quarter"
        )
    if re.fullmatch(r"\d{10}-\d{2}-\d{6}", company["accession"]) is None:
        raise ContractValidationError(f"{path}.accession must use canonical SEC form")
    _validate_optional_date(company.get("filed_at"), f"{path}.filed_at")
    _validate_required_utc_datetime(company.get("accepted_at"), f"{path}.accepted_at")
    _validate_optional_date(company.get("context_start"), f"{path}.context_start")
    if not isinstance(company.get("filed_at"), str) or not isinstance(
        company.get("context_start"), str
    ):
        raise ContractValidationError(f"{path} filing and context dates are required")
    filed_day = date.fromisoformat(company["filed_at"])
    accepted_day = date.fromisoformat(company["accepted_at"][:10])
    if (
        filed_day < calendar_end
        or accepted_day < calendar_end
        or abs((filed_day - accepted_day).days) > 1
    ):
        raise ContractValidationError(
            f"{path} filing/acceptance must follow context end and remain within one source-date day"
        )
    expected_context_start = (
        f"{expected_fiscal_year}-01-01"
        if P3_COMPANY_FISCAL_YEAR_END[company_id] == (12, 31)
        else f"{expected_fiscal_year - 1}-07-01"
    )
    if company["context_start"] != expected_context_start:
        raise ContractValidationError(
            f"{path}.context_start does not match the fiscal YTD context"
        )
    if generated_at is not None and datetime.fromisoformat(
        company["accepted_at"].replace("Z", "+00:00")
    ) > datetime.fromisoformat(generated_at.replace("Z", "+00:00")):
        raise ContractValidationError(f"{path}.accepted_at must not be future-dated")
    _validate_p3_sec_filing_url(
        company.get("filing_url"),
        f"{path}.filing_url",
        company_id=company_id,
        accession=company["accession"],
    )
    _validate_optional_string(company.get("frame"), f"{path}.frame")
    for field in (
        "finance_lease_tag",
        "finance_lease_accession",
        "finance_lease_quarterization_method",
    ):
        _validate_optional_string(company.get(field), f"{path}.{field}")
    if finance_value is None:
        if any(
            company.get(field) is not None
            for field in (
                "finance_lease_tag",
                "finance_lease_accession",
                "finance_lease_quarterization_method",
            )
        ):
            raise ContractValidationError(f"{path} finance-lease metadata requires a value")
    else:
        if company.get("finance_lease_tag") != "RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability":
            raise ContractValidationError(f"{path}.finance_lease_tag is not reviewed")
        accession = company.get("finance_lease_accession")
        if not isinstance(accession, str) or re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) is None:
            raise ContractValidationError(f"{path}.finance_lease_accession is invalid")
        _require_nonempty_string(
            company.get("finance_lease_quarterization_method"),
            f"{path}.finance_lease_quarterization_method",
        )
        if company["finance_lease_quarterization_method"] != expected_quarterization:
            raise ContractValidationError(
                f"{path}.finance_lease_quarterization_method does not match fiscal_quarter"
            )
        if accession != company["accession"]:
            raise ContractValidationError(
                f"{path}.finance_lease_accession must match the cash filing accession"
            )
    return company


def _validate_p3_sec_filing_url(
    value: Any,
    path: str,
    *,
    company_id: str,
    accession: str,
) -> None:
    source_url = _require_nonempty_string(value, path)
    try:
        parsed = urlsplit(source_url)
        port = parsed.port
    except ValueError as exc:
        raise ContractValidationError(f"{path} is not a valid public URL") from exc
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
        or parsed.path in {"", "/"}
    ):
        raise ContractValidationError(
            f"{path} must be a document-level public HTTPS URL"
        )
    if hostname != "www.sec.gov":
        raise ContractValidationError(f"{path} is not an allowlisted official source")
    accession_digits = accession.replace("-", "")
    decoded_path = unquote(parsed.path)
    cik = P3_COMPANIES[company_id][1]
    archive_prefix = f"/Archives/edgar/data/{int(cik)}/{accession_digits}/"
    if (
        parsed.query
        or decoded_path != parsed.path
        or any(segment in {".", ".."} for segment in decoded_path.split("/"))
        or re.fullmatch(
            re.escape(archive_prefix) + r"[^/]+\.html?",
            decoded_path,
            flags=re.IGNORECASE,
        )
        is None
    ):
        raise ContractValidationError(
            f"{path} must be a direct SEC filing document matching accession and issuer CIK"
        )


def _validate_p3_manual_source_url(
    value: Any,
    path: str,
    *,
    company_id: str,
    accession: str,
) -> None:
    _validate_p3_sec_filing_url(
        value,
        path,
        company_id=company_id,
        accession=accession,
    )


def _validate_p3_fundamental_details(
    metric: Mapping[str, Any],
    path: str,
    *,
    generated_at: str,
) -> Mapping[str, Any]:
    details = _require_mapping(metric.get("details"), f"{path}.details")
    if set(details) != {"fundamental"}:
        raise ContractValidationError(f"{path}.details must contain only fundamental")
    fundamental = _require_mapping(details["fundamental"], f"{path}.details.fundamental")
    if set(fundamental) != P3_FUNDAMENTAL_FIELDS:
        raise ContractValidationError(
            f"{path}.details.fundamental must use the exact P3 fields"
        )
    direction = fundamental.get("aggregate_direction")
    if direction not in P3_FUNDAMENTAL_DIRECTIONS:
        raise ContractValidationError(f"{path}.details.fundamental.aggregate_direction is invalid")
    breadth = fundamental.get("company_breadth")
    if isinstance(breadth, bool) or not isinstance(breadth, int) or not 0 <= breadth <= 4:
        raise ContractValidationError(f"{path}.details.fundamental.company_breadth is invalid")
    if fundamental.get("company_total") != 4:
        raise ContractValidationError(f"{path}.details.fundamental.company_total must be 4")
    companies = fundamental.get("companies")
    if not isinstance(companies, list):
        raise ContractValidationError(f"{path}.details.fundamental.companies must be a list")
    if metric.get("value") is None:
        if companies or direction != "UNKNOWN" or breadth != 0:
            raise ContractValidationError(f"{path} failed/empty fundamental details must remain unknown")
    else:
        if len(companies) != 4 or {company.get("company_id") for company in companies if isinstance(company, Mapping)} != set(P3_COMPANIES):
            raise ContractValidationError(f"{path} must expose exactly four company records")
        day = metric.get("observation_date")
        if not isinstance(day, str):
            raise ContractValidationError(f"{path}.observation_date is required")
        validated = [
            _validate_p3_company(
                company,
                f"{path}.details.fundamental.companies[{index}]",
                expected_date=day,
                generated_at=generated_at,
            )
            for index, company in enumerate(companies)
        ]
        expected_direction = _p3_direction(metric["statistics"].get("yoy_acceleration_pp"))
        expected_breadth = sum(
            company.get("direction") == expected_direction
            for company in validated
            if company.get("direction") != "UNKNOWN"
        ) if expected_direction != "UNKNOWN" else 0
        if direction != expected_direction or breadth != expected_breadth:
            raise ContractValidationError(f"{path} aggregate direction/breadth does not reconcile")
    caveats = fundamental.get("caveats")
    _validate_string_list(caveats, f"{path}.details.fundamental.caveats")
    return fundamental


def _validate_p3_manual_record(
    value: Any,
    path: str,
    *,
    metric_id: str,
    point_date: str,
    generated_at: str,
) -> Mapping[str, Any]:
    record = _require_mapping(value, path)
    if set(record) != P3_MANUAL_RECORD_FIELDS:
        raise ContractValidationError(f"{path} must use the exact 17-field manual contract")
    if record.get("metric_id") != metric_id or record.get("company_id") not in P3_COMPANIES:
        raise ContractValidationError(f"{path} manual metric/company identity is invalid")
    for field in ("period_end", "as_of"):
        _validate_optional_date(record.get(field), f"{path}.{field}")
        if record.get(field) is None:
            raise ContractValidationError(f"{path}.{field} is required")
    if record["as_of"] > point_date:
        raise ContractValidationError(f"{path}.as_of must not follow its aggregate point")
    for field in ("filing_accepted_at", "reviewed_at"):
        _validate_required_utc_datetime(record.get(field), f"{path}.{field}")
    if not (record["period_end"] <= record["filing_accepted_at"][:10] <= record["as_of"] <= record["reviewed_at"][:10]):
        raise ContractValidationError(f"{path} manual chronology is invalid")
    if datetime.fromisoformat(record["filing_accepted_at"].replace("Z", "+00:00")) > datetime.fromisoformat(
        record["reviewed_at"].replace("Z", "+00:00")
    ):
        raise ContractValidationError(f"{path} review cannot predate filing acceptance")
    generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    if any(
        datetime.fromisoformat(record[field].replace("Z", "+00:00")) > generated
        for field in ("filing_accepted_at", "reviewed_at")
    ):
        raise ContractValidationError(f"{path} manual timestamps must not be future-dated")
    direction = record.get("direction")
    if direction not in {"UP", "DOWN", "FLAT", "UNKNOWN"}:
        raise ContractValidationError(f"{path}.direction is invalid")
    if not isinstance(record.get("comparable"), bool):
        raise ContractValidationError(f"{path}.comparable must be boolean")
    for field in ("value", "yoy_pct"):
        _validate_nullable_number(record.get(field), f"{path}.{field}")
    if record.get("value") is not None and record["value"] < 0:
        raise ContractValidationError(f"{path}.value must be non-negative")
    _validate_optional_string(record.get("unit"), f"{path}.unit")
    if (record.get("value") is None) != (record.get("unit") is None):
        raise ContractValidationError(f"{path}.value and unit must be jointly present or null")
    if record.get("unit") is not None and record["unit"] not in P3_MANUAL_VALUE_UNITS:
        raise ContractValidationError(f"{path}.unit is not allowlisted")
    if not record["comparable"] and record.get("yoy_pct") is not None:
        raise ContractValidationError(f"{path}.yoy_pct requires comparable=true")
    for field in (
        "source_type",
        "source_url",
        "filing_accession",
        "reviewer",
        "paraphrase",
        "review_note",
    ):
        _require_nonempty_string(record.get(field), f"{path}.{field}")
    if re.fullmatch(r"\d{10}-\d{2}-\d{6}", record["filing_accession"]) is None:
        raise ContractValidationError(f"{path}.filing_accession is invalid")
    if record["source_type"] not in P3_MANUAL_SOURCE_TYPES:
        raise ContractValidationError(f"{path}.source_type is not allowlisted")
    _validate_p3_manual_source_url(
        record["source_url"],
        f"{path}.source_url",
        company_id=record["company_id"],
        accession=record["filing_accession"],
    )
    for field, maximum in (("reviewer", 80), ("paraphrase", 280), ("review_note", 500)):
        if len(record[field]) > maximum:
            raise ContractValidationError(f"{path}.{field} exceeds the reviewed limit")
    return record


def _p3_manual_direction(records: list[Mapping[str, Any]]) -> str:
    directions = [record["direction"] for record in records if record["comparable"]]
    if not directions or "UNKNOWN" in directions:
        return "UNKNOWN"
    return directions[0] if len(set(directions)) == 1 else "MIXED"


def _validate_p3_snapshot(
    snapshot: Mapping[str, Any],
    metrics: Mapping[str, Any],
    sources: Mapping[str, Any],
) -> None:
    if set(sources) != CANONICAL_COLLECTOR_IDS:
        missing = sorted(CANONICAL_COLLECTOR_IDS - set(sources))
        extra = sorted(set(sources) - CANONICAL_COLLECTOR_IDS)
        raise ContractValidationError(
            f"snapshot.sources must use the exact automated collector set; missing={missing}, extra={extra}"
        )
    p3_collector = _require_mapping(
        sources["sec_companyfacts_capex"],
        "snapshot.sources.sec_companyfacts_capex",
    )
    if set(p3_collector) != P3_COLLECTOR_SOURCE_FIELDS:
        raise ContractValidationError(
            "sec_companyfacts_capex must use the exact collector source fields"
        )
    required_ids = set(P3_AUTOMATED_METRICS) | set(P3_MANUAL_METRICS)
    missing = required_ids - metrics.keys()
    if missing:
        raise ContractValidationError(
            "snapshot is missing canonical P3 metrics: " + ", ".join(sorted(missing))
        )
    retired = P3_RETIRED_METRICS & metrics.keys()
    if retired:
        raise ContractValidationError(
            "snapshot contains retired P3 metric IDs: " + ", ".join(sorted(retired))
        )
    for metric_id in required_ids:
        metric = _require_mapping(metrics[metric_id], f"snapshot.metrics.{metric_id}")
        expected_fields = set(P3_METRIC_BASE_FIELDS)
        if metric_id in P3_AUTOMATED_METRICS or metric.get("availability") == "ACTIVE_FREE":
            expected_fields.add("details")
        if set(metric) != expected_fields:
            raise ContractValidationError(
                f"{metric_id} must use the exact P3 metric fields"
            )
        for nested_name, expected_nested_fields in (
            ("quality", P3_QUALITY_FIELDS),
            ("context", P3_CONTEXT_FIELDS),
            ("source", P3_SOURCE_FIELDS),
            ("methodology", METHODOLOGY_FIELDS),
        ):
            nested = _require_mapping(
                metric.get(nested_name), f"snapshot.metrics.{metric_id}.{nested_name}"
            )
            if set(nested) != set(expected_nested_fields):
                raise ContractValidationError(
                    f"{metric_id}.{nested_name} must use the exact P3 fields"
                )
        if metric.get("provenance") != [metric.get("source")]:
            raise ContractValidationError(
                f"{metric_id}.provenance must contain exactly its reviewed source"
            )

    automated: dict[str, Mapping[str, Any]] = {}
    fundamentals: dict[str, Mapping[str, Any]] = {}
    for metric_id, (unit, frequency) in P3_AUTOMATED_METRICS.items():
        metric = _require_mapping(metrics[metric_id], f"snapshot.metrics.{metric_id}")
        automated[metric_id] = metric
        if (
            metric.get("availability") != "ACTIVE_FREE"
            or metric.get("unit") != unit
            or metric.get("frequency") != frequency
            or metric.get("expected_next_update") is not None
            or metric.get("source", {}).get("source_id") != "sec_edgar"
            or metric.get("context", {}).get("technical_flags") != []
        ):
            raise ContractValidationError(f"{metric_id} does not match the P3 automated contract")
        if any(
            metric.get("source", {}).get(field) != expected
            for field, expected in P3_SEC_SOURCE_METADATA.items()
        ):
            raise ContractValidationError(
                f"{metric_id} SEC source metadata does not match the registry"
            )
        stats = _require_mapping(metric.get("statistics"), f"{metric_id}.statistics")
        if set(stats) != P3_AUTOMATED_STATISTICS:
            raise ContractValidationError(f"{metric_id}.statistics must use the exact P3 fields")
        for field in (
            "company_breadth",
            "company_total",
            "finance_lease_disclosure_breadth",
            "manual_review_count",
            "quarter_count",
        ):
            value = stats[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractValidationError(f"{metric_id}.statistics.{field} must be a non-negative integer")
        if stats["company_total"] != 4 or stats["company_breadth"] > 4 or stats["finance_lease_disclosure_breadth"] > 4:
            raise ContractValidationError(f"{metric_id} company counts exceed the four-company contract")
        ratio = stats["company_breadth_ratio"]
        if ratio is not None and not 0 <= ratio <= 1:
            raise ContractValidationError(f"{metric_id}.statistics.company_breadth_ratio is invalid")
        if metric_id == "hyperscaler_aggregate_cash_capex":
            expected_value = stats["aggregate_cash_capex_usd_bn"]
        else:
            expected_value = stats["yoy_acceleration_pp"]
        if not _same_nullable_number(metric.get("value"), expected_value, tolerance=0.000002):
            raise ContractValidationError(f"{metric_id}.value must match its endpoint statistic")
        expected_direction = _p3_direction(stats["yoy_acceleration_pp"])
        expected_confidence = (
            "HIGH"
            if metric["quality"].get("status") == "OK"
            else "MEDIUM"
            if metric.get("value") is not None
            else "UNKNOWN"
        )
        if (
            metric["context"].get("direction") != expected_direction
            or metric["context"].get("confidence") != expected_confidence
            or metric["context"].get("is_proxy") is not False
        ):
            raise ContractValidationError(
                f"{metric_id} context direction/confidence must match its evidence state"
            )
        fundamentals[metric_id] = _validate_p3_fundamental_details(
            metric,
            f"snapshot.metrics.{metric_id}",
            generated_at=str(snapshot["generated_at"]),
        )
        generated = datetime.fromisoformat(
            str(snapshot["generated_at"]).replace("Z", "+00:00")
        )
        timestamp_fields = [
            metric.get("updated_at"),
            metric["quality"].get("last_success_at"),
            metric["quality"].get("last_attempt_at"),
            metric["source"].get("retrieved_at"),
        ]
        if any(
            datetime.fromisoformat(value.replace("Z", "+00:00")) > generated
            for value in timestamp_fields
            if isinstance(value, str)
        ):
            raise ContractValidationError(
                f"{metric_id} state timestamps must not follow generated_at"
            )
        if metric["source"].get("retrieved_at") != metric["quality"].get(
            "last_attempt_at"
        ):
            raise ContractValidationError(
                f"{metric_id} source.retrieved_at must equal quality.last_attempt_at"
            )
        success = metric["quality"].get("last_success_at")
        attempt = metric["quality"].get("last_attempt_at")
        if isinstance(success, str) and (
            not isinstance(attempt, str)
            or datetime.fromisoformat(success.replace("Z", "+00:00"))
            > datetime.fromisoformat(attempt.replace("Z", "+00:00"))
        ):
            raise ContractValidationError(
                f"{metric_id} last_success_at must not follow last_attempt_at"
            )
        if metric["quality"].get("status") == "OK":
            if (
                metric["quality"].get("failure_reason") is not None
                or success is None
                or success != attempt
                or success != metric.get("updated_at")
                or success != metric["source"].get("retrieved_at")
            ):
                raise ContractValidationError(
                    f"{metric_id} successful automated state must share one success timestamp and no failure"
                )
        elif not isinstance(metric["quality"].get("failure_reason"), str) or not metric[
            "quality"
        ]["failure_reason"]:
            raise ContractValidationError(
                f"{metric_id} unsuccessful automated state must disclose its failure"
            )
    capex = automated["hyperscaler_aggregate_cash_capex"]
    acceleration = automated[
        "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp"
    ]
    if capex["statistics"] != acceleration["statistics"] or capex.get("details") != acceleration.get("details"):
        raise ContractValidationError("P3 automated metrics must share statistics and fundamental details")
    for field in ("observation_date", "released_at", "updated_at", "expected_next_update"):
        if capex.get(field) != acceleration.get(field):
            raise ContractValidationError(f"P3 automated metrics must share {field}")
    for field in (
        "status",
        "freshness",
        "last_success_at",
        "last_attempt_at",
        "failure_reason",
    ):
        if capex["quality"].get(field) != acceleration["quality"].get(field):
            raise ContractValidationError(
                f"P3 automated metrics must share quality.{field}"
            )
    if capex["context"].get("confidence") != acceleration["context"].get(
        "confidence"
    ):
        raise ContractValidationError(
            "P3 automated metrics must share context.confidence"
        )

    manual_details: dict[str, Mapping[str, Any] | None] = {}
    manual_healthy: dict[str, bool] = {}
    for metric_id in P3_MANUAL_METRICS:
        metric = _require_mapping(metrics[metric_id], f"snapshot.metrics.{metric_id}")
        if metric.get("unit") != "mixed" or metric.get("frequency") != "quarterly" or metric.get("value") is not None:
            raise ContractValidationError(f"{metric_id} must be a null-valued quarterly mixed-unit manual metric")
        if metric.get("source", {}).get("source_id") != "manual_public_filings":
            raise ContractValidationError(f"{metric_id} source must be manual_public_filings")
        if any(
            metric.get("source", {}).get(field) != expected
            for field, expected in P3_MANUAL_SOURCE_METADATA.items()
        ):
            raise ContractValidationError(
                f"{metric_id} manual source metadata does not match the registry"
            )
        if metric.get("expected_next_update") is not None or metric.get("context", {}).get("technical_flags") != []:
            raise ContractValidationError(f"{metric_id} cannot invent a schedule or technical flags")
        expected_manual_changes = {
            "one_observation": None,
            "five_observations": None,
            "twenty_observations": None,
            "eight_weeks": None,
            "twelve_weeks": None,
            "one_quarter": None,
        }
        if metric.get("changes") != expected_manual_changes:
            raise ContractValidationError(
                f"{metric_id}.changes must remain null for mixed-unit manual evidence"
            )
        availability = metric.get("availability")
        details = metric.get("details")
        if availability == "MANUAL_READY":
            if (
                metric.get("statistics") != {}
                or metric.get("observation_date") is not None
                or metric.get("released_at") is not None
                or metric.get("updated_at") is not None
                or metric.get("short_series") != []
                or metric.get("quality", {}).get("status") != "NOT_APPLICABLE"
                or metric.get("quality", {}).get("freshness") != "UNKNOWN"
                or metric.get("quality", {}).get("last_success_at") is not None
                or metric.get("quality", {}).get("last_attempt_at") is not None
                or metric.get("source", {}).get("retrieved_at") is not None
                or details is not None
                or metric.get("context", {}).get("direction") != "UNKNOWN"
                or metric.get("context", {}).get("confidence") != "UNKNOWN"
            ):
                raise ContractValidationError(f"{metric_id} MANUAL_READY state must remain empty and null")
            manual_details[metric_id] = None
            manual_healthy[metric_id] = False
            continue
        if availability != "ACTIVE_FREE":
            raise ContractValidationError(f"{metric_id} availability must be MANUAL_READY or ACTIVE_FREE")
        wrapped = _require_mapping(details, f"{metric_id}.details")
        if set(wrapped) != {"manual_evidence"}:
            raise ContractValidationError(f"{metric_id}.details must contain only manual_evidence")
        detail = _require_mapping(wrapped["manual_evidence"], f"{metric_id}.details.manual_evidence")
        expected_keys = {
            "source_id", "network_enabled", "observation_date", "direction",
            "record_count", "company_count", "comparable_count",
            "latest_filing_accepted_at", "latest_reviewed_at", "records",
        }
        if set(detail) != expected_keys or detail.get("source_id") != "manual_public_filings" or detail.get("network_enabled") is not False:
            raise ContractValidationError(f"{metric_id}.manual_evidence shape is invalid")
        records = detail.get("records")
        if not isinstance(records, list) or not records:
            raise ContractValidationError(f"{metric_id}.manual_evidence.records must be non-empty")
        observation_date = detail.get("observation_date")
        _validate_optional_date(observation_date, f"{metric_id}.manual_evidence.observation_date")
        if not isinstance(observation_date, str):
            raise ContractValidationError(f"{metric_id}.manual_evidence.observation_date is required")
        validated = [
            _validate_p3_manual_record(
                record,
                f"{metric_id}.manual_evidence.records[{index}]",
                metric_id=metric_id,
                point_date=observation_date,
                generated_at=str(snapshot["generated_at"]),
            )
            for index, record in enumerate(records)
        ]
        if len({record["company_id"] for record in validated}) != len(validated):
            raise ContractValidationError(f"{metric_id} manual evidence must retain one latest row per company")
        expected_direction = _p3_manual_direction(validated)
        expected_fields = {
            "record_count": len(validated),
            "company_count": len({record["company_id"] for record in validated}),
            "comparable_count": sum(bool(record["comparable"]) for record in validated),
            "direction": expected_direction,
            "observation_date": max(record["as_of"] for record in validated),
            "latest_filing_accepted_at": max(record["filing_accepted_at"] for record in validated),
            "latest_reviewed_at": max(record["reviewed_at"] for record in validated),
        }
        if any(detail.get(field) != expected for field, expected in expected_fields.items()):
            raise ContractValidationError(f"{metric_id}.manual_evidence does not reconcile its records")
        if metric.get("statistics") != {
            "record_count": expected_fields["record_count"],
            "company_count": expected_fields["company_count"],
            "comparable_count": expected_fields["comparable_count"],
        }:
            raise ContractValidationError(f"{metric_id}.statistics must match manual evidence")
        quality = metric["quality"]
        if quality.get("status") not in {"OK", "STALE"} or quality.get("freshness") not in {"FRESH", "STALE"}:
            raise ContractValidationError(f"{metric_id} active manual quality is invalid")
        if (quality.get("status") == "OK") != (quality.get("freshness") == "FRESH"):
            raise ContractValidationError(f"{metric_id} active manual health/freshness must align")
        generated_at = datetime.fromisoformat(
            str(snapshot["generated_at"]).replace("Z", "+00:00")
        ).astimezone(ZoneInfo("America/New_York"))
        age_days = (
            generated_at.date() - date.fromisoformat(expected_fields["observation_date"])
        ).days
        if age_days < 0:
            raise ContractValidationError(f"{metric_id} manual evidence is future-dated")
        expected_health = "STALE" if age_days > P3_MANUAL_MAX_AGE_DAYS else "OK"
        expected_freshness = "STALE" if age_days > P3_MANUAL_MAX_AGE_DAYS else "FRESH"
        if (
            quality.get("status") != expected_health
            or quality.get("freshness") != expected_freshness
            or quality.get("failure_reason") is not None
        ):
            raise ContractValidationError(
                f"{metric_id} manual quality must match its 120-day evidence age"
            )
        if (
            metric.get("observation_date") != expected_fields["observation_date"]
            or metric.get("released_at") != expected_fields["latest_filing_accepted_at"]
            or metric.get("updated_at") != expected_fields["latest_reviewed_at"]
            or quality.get("last_success_at") != expected_fields["latest_reviewed_at"]
            or quality.get("last_attempt_at") != expected_fields["latest_reviewed_at"]
            or quality.get("sample_size") != expected_fields["record_count"]
            or metric.get("source", {}).get("retrieved_at") != expected_fields["latest_reviewed_at"]
            or metric.get("context", {}).get("direction") != expected_direction
            or metric.get("context", {}).get("confidence")
            != ("MEDIUM" if expected_health == "OK" else "UNKNOWN")
        ):
            raise ContractValidationError(f"{metric_id} active manual timestamps/state do not reconcile")
        manual_details[metric_id] = detail
        manual_healthy[metric_id] = quality.get("status") == "OK" and quality.get("freshness") == "FRESH"

    switch = _require_mapping(
        snapshot["switches"]["fundamental_exit"],
        "snapshot.switches.fundamental_exit",
    )
    if set(switch) != P3_SWITCH_FIELDS:
        raise ContractValidationError(
            "fundamental_exit must use the exact evidence-only switch fields"
        )
    blocks = switch["evidence_blocks"]
    if any(set(block) != P3_EVIDENCE_BLOCK_FIELDS for block in blocks):
        raise ContractValidationError(
            "fundamental_exit blocks must use the exact evidence-only fields"
        )
    if switch.get("mode") != "EVIDENCE_ONLY" or switch.get("assessment") is not None:
        raise ContractValidationError("fundamental_exit must remain evidence-only with null assessment")
    if tuple(block["id"] for block in blocks) != P3_BLOCK_IDS:
        raise ContractValidationError("fundamental_exit evidence block IDs/order do not match P3 contract")
    if any(block.get("triggered") is not None for block in blocks):
        raise ContractValidationError("fundamental_exit evidence triggered must remain null")
    automated_available = all(
        metric["quality"]["status"] == "OK"
        and metric["quality"]["freshness"] == "FRESH"
        and metric["value"] is not None
        and metric["statistics"]["quarter_count"] >= 12
        for metric in automated.values()
    )
    aggregate_direction = fundamentals["hyperscaler_aggregate_cash_capex"]["aggregate_direction"] if automated_available else "UNKNOWN"
    companies = fundamentals["hyperscaler_aggregate_cash_capex"]["companies"]
    breadth_direction = _p3_common_direction([company["direction"] for company in companies]) if automated_available else "UNKNOWN"
    orders = "ai_upstream_orders_backlog"
    orders_available = manual_details[orders] is not None and manual_healthy[orders]
    commitment_ids = (
        "customer_prepayments_contract_commitments",
        "take_or_pay_commitments",
    )
    active_commitments = [
        metric_id for metric_id in commitment_ids if manual_details[metric_id] is not None
    ]
    commitments_available = bool(active_commitments) and all(
        manual_healthy[metric_id] for metric_id in active_commitments
    )
    expected = [
        (automated_available, aggregate_direction, aggregate_direction if automated_available else "UNAVAILABLE"),
        (orders_available, manual_details[orders]["direction"] if orders_available else "UNKNOWN", "MANUAL_READY" if manual_details[orders] is None else "STALE" if not orders_available else manual_details[orders]["direction"]),
        (commitments_available, _p3_common_direction([manual_details[metric_id]["direction"] for metric_id in active_commitments]) if commitments_available else "UNKNOWN", "MANUAL_READY" if not active_commitments else "STALE" if not commitments_available else _p3_common_direction([manual_details[metric_id]["direction"] for metric_id in active_commitments])),
        (automated_available, breadth_direction, breadth_direction if automated_available else "UNAVAILABLE"),
    ]
    for index, block in enumerate(blocks):
        available, direction, status = expected[index]
        if (
            block.get("available") != available
            or block.get("direction") != direction
            or block.get("status") != status
            or block.get("confidence") != ("MEDIUM" if available else "UNKNOWN")
        ):
            raise ContractValidationError(f"fundamental_exit block {block['id']} does not match P3 evidence")
    available_count = sum(item[0] for item in expected)
    expected_confidence = "UNKNOWN" if available_count == 0 else "LOW" if available_count <= 2 else "MEDIUM"
    if switch.get("available_blocks") != available_count or switch.get("total_blocks") != 4 or switch.get("confidence") != expected_confidence:
        raise ContractValidationError("fundamental_exit coverage/confidence does not match P3 evidence")

    if "manual_public_filings" in sources:
        raise ContractValidationError("manual_public_filings must not count as an automated collector")
    collector_id = "sec_companyfacts_capex"
    if collector_id not in sources:
        raise ContractValidationError("snapshot.sources.sec_companyfacts_capex is required")
    source = _require_mapping(sources[collector_id], f"snapshot.sources.{collector_id}")
    if source.get("collector_id") != collector_id:
        raise ContractValidationError("sec_companyfacts_capex collector_id is invalid")
    metric_sources = [metric["source"] for metric in automated.values()]
    if any(metric_source.get("source_id") != "sec_edgar" for metric_source in metric_sources):
        raise ContractValidationError("P3 automated metrics must use sec_edgar")
    if any(
        source.get(field) != metric_source.get(field)
        for metric_source in metric_sources
        for field in ("name", "url", "tier", "rights_note")
    ):
        raise ContractValidationError("P3 collector provenance must match both metrics")
    health_rank = {"NOT_APPLICABLE": -1, "OK": 0, "NOT_RELEASED_YET": 1, "STALE": 2, "ERROR": 3}
    freshness_rank = {"FRESH": 0, "LATE": 1, "STALE": 2, "UNKNOWN": 3}
    qualities = [metric["quality"] for metric in automated.values()]
    attempts = [quality["last_attempt_at"] for quality in qualities if quality["last_attempt_at"]]
    successes = [quality["last_success_at"] for quality in qualities if quality["last_success_at"]]
    failures = list(dict.fromkeys(quality["failure_reason"] for quality in qualities if quality["failure_reason"]))
    updates = [metric["updated_at"] for metric in automated.values() if metric["updated_at"]]
    expected_attempt = max(attempts, default=None)
    expected_source = {
        "status": max((quality["status"] for quality in qualities), key=health_rank.__getitem__),
        "freshness": max((quality["freshness"] for quality in qualities), key=freshness_rank.__getitem__),
        "observation_date": max((metric["observation_date"] for metric in automated.values() if metric["observation_date"]), default=None),
        "released_at": max((metric["released_at"] for metric in automated.values() if metric["released_at"]), default=None),
        "updated_at": expected_attempt if expected_attempt == snapshot.get("generated_at") else max(updates, default=None),
        "last_success_at": min(successes) if successes and all(quality["status"] == "OK" for quality in qualities) else max(successes, default=None),
        "last_attempt_at": expected_attempt,
        "expected_next_update": None,
        "failure_reason": "; ".join(failures) if failures else None,
    }
    if any(source.get(field) != expected_value for field, expected_value in expected_source.items()):
        raise ContractValidationError("sec_companyfacts_capex state/provenance must match both metrics")


def _p3_percent_change(current: Any, previous: Any) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((float(current) / float(previous) - 1) * 100, 6)


def _validate_p3_publication(
    snapshot: Mapping[str, Any],
    manifest_by_id: Mapping[str, Mapping[str, Any]],
    series_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    canonical_p3_ids = set(P3_AUTOMATED_METRICS) | set(P3_MANUAL_METRICS)
    declared_p3_ids = {
        metric_id
        for metric_id, metric in manifest_by_id.items()
        if metric.get("phase") == "P3" or metric.get("layer") == "fundamental_exit"
    }
    if declared_p3_ids != canonical_p3_ids:
        raise ContractValidationError(
            "manifest must declare exactly the five canonical P3 metrics"
        )
    for metric_id in canonical_p3_ids:
        manifest_metric = manifest_by_id[metric_id]
        series_metric = series_by_id[metric_id]
        if set(manifest_metric) != P3_MANIFEST_FIELDS:
            raise ContractValidationError(
                f"{metric_id} manifest must use the exact P3 fields"
            )
        if set(series_metric) != P3_SERIES_FIELDS:
            raise ContractValidationError(
                f"{metric_id} series must use the exact P3 envelope"
            )
        if set(series_metric["quality"]) != P3_QUALITY_FIELDS:
            raise ContractValidationError(
                f"{metric_id} series quality must use the exact P3 fields"
            )
        if set(series_metric["source"]) != P3_SOURCE_FIELDS:
            raise ContractValidationError(
                f"{metric_id} series source must use the exact P3 fields"
            )
        if manifest_metric.get("phase") != "P3" or manifest_metric.get("layer") != "fundamental_exit":
            raise ContractValidationError(f"{metric_id} manifest phase/layer must be P3 fundamental_exit")

    capex_id = "hyperscaler_aggregate_cash_capex"
    acceleration_id = "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp"
    capex_series = series_by_id[capex_id]
    acceleration_series = series_by_id[acceleration_id]
    capex_points = capex_series["observations"]
    acceleration_points = acceleration_series["observations"]
    if len(capex_points) != len(acceleration_points) or len(capex_points) not in {0} and len(capex_points) < 12:
        raise ContractValidationError("P3 automated series must be empty together or contain at least 12 quarters")
    point_fields = {
        "date", "value", "aggregate_cash_capex_usd_bn", "qoq_percent_change",
        "yoy_percent_change", "qoq_acceleration_pp", "yoy_acceleration_pp",
        "aggregate_direction", "company_breadth", "company_total",
        "company_breadth_ratio", "finance_lease_disclosure_breadth",
        "manual_review_count", "companies",
    }
    previous: Mapping[str, Any] | None = None
    by_ordinal: dict[int, Mapping[str, Any]] = {}
    company_by_ordinal: dict[str, dict[int, Mapping[str, Any]]] = {
        company_id: {} for company_id in P3_COMPANIES
    }
    for index, (capex_point, acceleration_point) in enumerate(
        zip(capex_points, acceleration_points, strict=True)
    ):
        path = f"{capex_id}.observations[{index}]"
        if set(capex_point) != point_fields or set(acceleration_point) != point_fields:
            raise ContractValidationError(f"{path} must use the exact P3 point fields")
        if any(
            capex_point.get(field) != acceleration_point.get(field)
            for field in point_fields - {"value"}
        ):
            raise ContractValidationError(f"{path} and acceleration series must share one base point")
        day = capex_point["date"]
        parsed = date.fromisoformat(day)
        quarter_days = {3: 31, 6: 30, 9: 30, 12: 31}
        if parsed.month not in quarter_days or parsed.day != quarter_days[parsed.month]:
            raise ContractValidationError(f"{path}.date must be a calendar quarter end")
        ordinal = parsed.year * 4 + (parsed.month - 1) // 3
        if previous is not None and ordinal != max(by_ordinal) + 1:
            raise ContractValidationError("P3 automated observations must be consecutive quarters")
        companies = capex_point.get("companies")
        if not isinstance(companies, list) or len(companies) != 4:
            raise ContractValidationError(f"{path}.companies must contain four records")
        validated = [
            _validate_p3_company(
                company,
                f"{path}.companies[{company_index}]",
                expected_date=day,
                generated_at=str(snapshot["generated_at"]),
            )
            for company_index, company in enumerate(companies)
        ]
        if {company["company_id"] for company in validated} != set(P3_COMPANIES):
            raise ContractValidationError(f"{path}.companies identities are incomplete")
        for company in validated:
            company_path = f"{path}.companies[{company['company_id']}]"
            history = company_by_ordinal[company["company_id"]]
            prior_company = history.get(ordinal - 1)
            year_ago_company = history.get(ordinal - 4)
            if prior_company is not None:
                expected_company_qoq = _p3_percent_change(
                    company["cash_capex_usd_bn"],
                    prior_company["cash_capex_usd_bn"],
                )
                if not _same_nullable_number(
                    company.get("qoq_percent_change"),
                    expected_company_qoq,
                    tolerance=0.000002,
                ):
                    raise ContractValidationError(
                        f"{company_path}.qoq_percent_change does not reconcile"
                    )
                expected_company_qoq_acceleration = (
                    round(
                        float(expected_company_qoq)
                        - float(prior_company["qoq_percent_change"]),
                        6,
                    )
                    if expected_company_qoq is not None
                    and prior_company.get("qoq_percent_change") is not None
                    else None
                )
                if not _same_nullable_number(
                    company.get("qoq_acceleration_pp"),
                    expected_company_qoq_acceleration,
                    tolerance=0.000002,
                ):
                    raise ContractValidationError(
                        f"{company_path}.qoq_acceleration_pp does not reconcile"
                    )
            elif (
                company.get("qoq_percent_change") is not None
                or company.get("qoq_acceleration_pp") is not None
            ):
                raise ContractValidationError(
                    f"{company_path} leading QoQ fields require visible prior-quarter provenance"
                )
            if year_ago_company is not None:
                expected_company_yoy = _p3_percent_change(
                    company["cash_capex_usd_bn"],
                    year_ago_company["cash_capex_usd_bn"],
                )
                if not _same_nullable_number(
                    company.get("yoy_percent_change"),
                    expected_company_yoy,
                    tolerance=0.000002,
                ):
                    raise ContractValidationError(
                        f"{company_path}.yoy_percent_change does not reconcile"
                    )
                expected_company_yoy_acceleration = (
                    round(
                        float(expected_company_yoy)
                        - float(prior_company["yoy_percent_change"]),
                        6,
                    )
                    if expected_company_yoy is not None
                    and prior_company is not None
                    and prior_company.get("yoy_percent_change") is not None
                    else None
                )
                if not _same_nullable_number(
                    company.get("yoy_acceleration_pp"),
                    expected_company_yoy_acceleration,
                    tolerance=0.000002,
                ):
                    raise ContractValidationError(
                        f"{company_path}.yoy_acceleration_pp does not reconcile"
                    )
            elif (
                company.get("yoy_percent_change") is not None
                or company.get("yoy_acceleration_pp") is not None
            ):
                raise ContractValidationError(
                    f"{company_path} leading YoY fields require visible year-ago provenance"
                )
            history[ordinal] = company
        aggregate = round(sum(float(company["cash_capex_usd_bn"]) for company in validated), 6)
        prior_quarter = previous.get("aggregate_cash_capex_usd_bn") if previous else None
        year_ago = by_ordinal.get(ordinal - 4)
        expected_qoq = _p3_percent_change(aggregate, prior_quarter)
        expected_yoy = _p3_percent_change(
            aggregate,
            year_ago.get("aggregate_cash_capex_usd_bn") if year_ago else None,
        )
        expected_qoq_acceleration = (
            round(expected_qoq - float(previous["qoq_percent_change"]), 6)
            if expected_qoq is not None and previous is not None and previous.get("qoq_percent_change") is not None
            else None
        )
        expected_yoy_acceleration = (
            round(expected_yoy - float(previous["yoy_percent_change"]), 6)
            if expected_yoy is not None and previous is not None and previous.get("yoy_percent_change") is not None
            else None
        )
        expected_direction = _p3_direction(expected_yoy_acceleration)
        known_directions = [company["direction"] for company in validated if company["direction"] != "UNKNOWN"]
        expected_breadth = sum(direction == expected_direction for direction in known_directions) if expected_direction != "UNKNOWN" else 0
        expected_breadth_ratio = (
            round(expected_breadth / len(known_directions), 6)
            if expected_direction != "UNKNOWN" and known_directions
            else None
        )
        expected_values = {
            "aggregate_cash_capex_usd_bn": aggregate,
            "qoq_percent_change": expected_qoq,
            "yoy_percent_change": expected_yoy,
            "qoq_acceleration_pp": expected_qoq_acceleration,
            "yoy_acceleration_pp": expected_yoy_acceleration,
            "aggregate_direction": expected_direction,
            "company_breadth": expected_breadth,
            "company_total": 4,
            "company_breadth_ratio": expected_breadth_ratio,
            "finance_lease_disclosure_breadth": sum(company["finance_lease_additions_usd_bn"] is not None for company in validated),
            "manual_review_count": 0,
        }
        for field, expected_value in expected_values.items():
            actual = capex_point.get(field)
            if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
                if not _same_nullable_number(actual, expected_value, tolerance=0.000002):
                    raise ContractValidationError(f"{path}.{field} does not reconcile")
            elif actual != expected_value:
                raise ContractValidationError(f"{path}.{field} does not reconcile")
        if not _same_nullable_number(capex_point.get("value"), aggregate, tolerance=0.000002):
            raise ContractValidationError(f"{path}.value must equal aggregate cash CapEx")
        if not _same_nullable_number(
            acceleration_point.get("value"), expected_yoy_acceleration, tolerance=0.000002
        ):
            raise ContractValidationError(f"{acceleration_id}.observations[{index}].value must equal YoY acceleration")
        by_ordinal[ordinal] = capex_point
        previous = capex_point

    latest = capex_points[-1] if capex_points else None
    expected_statistics = {
        field: latest.get(field) if latest else None
        for field in P3_AUTOMATED_STATISTICS - {"quarter_count"}
    }
    if latest is None:
        expected_statistics.update(
            {
                "company_breadth": 0,
                "company_total": 4,
                "finance_lease_disclosure_breadth": 0,
                "manual_review_count": 0,
            }
        )
    expected_statistics["quarter_count"] = len(capex_points)
    for metric_id in (capex_id, acceleration_id):
        metric = snapshot["metrics"][metric_id]
        for field, expected_value in expected_statistics.items():
            if not _same_nullable_number(metric["statistics"].get(field), expected_value, tolerance=0.000002):
                raise ContractValidationError(f"{metric_id}.statistics.{field} must match full series")
        observations = series_by_id[metric_id]["observations"]
        values = [point["value"] for point in observations if point["value"] is not None]
        expected_change = (
            round(float(values[-1]) - float(values[-2]), 6)
            if len(values) >= 2
            else None
        )
        expected_changes = {
            "one_observation": expected_change,
            "five_observations": (
                round(float(values[-1]) - float(values[-6]), 6)
                if len(values) >= 6
                else None
            ),
            "twenty_observations": (
                round(float(values[-1]) - float(values[-21]), 6)
                if len(values) >= 21
                else None
            ),
            "eight_weeks": None,
            "twelve_weeks": None,
            "one_quarter": expected_change,
        }
        if set(metric["changes"]) != set(expected_changes) or any(
            not _same_nullable_number(
                metric["changes"].get(field),
                expected_value,
                tolerance=0.000002,
            )
            for field, expected_value in expected_changes.items()
        ):
            raise ContractValidationError(
                f"{metric_id}.changes must match its full quarterly series"
            )
        expected_sample = sum(point["value"] is not None for point in observations)
        if metric["quality"].get("sample_size") != expected_sample:
            raise ContractValidationError(f"{metric_id}.quality.sample_size must match full series")
    if latest:
        expected_release = max(company["accepted_at"] for company in latest["companies"])
        if capex_series.get("released_at") != expected_release or acceleration_series.get("released_at") != expected_release:
            raise ContractValidationError("P3 automated released_at must match latest company filings")
        for metric_id in (capex_id, acceleration_id):
            fundamental = snapshot["metrics"][metric_id]["details"]["fundamental"]
            if (
                fundamental["aggregate_direction"] != latest["aggregate_direction"]
                or fundamental["company_breadth"] != latest["company_breadth"]
                or fundamental["company_total"] != 4
                or fundamental["companies"] != latest["companies"]
            ):
                raise ContractValidationError(f"{metric_id}.details must match full-series endpoint")

    for metric_id in P3_MANUAL_METRICS:
        metric = snapshot["metrics"][metric_id]
        series = series_by_id[metric_id]
        observations = series["observations"]
        if metric["availability"] == "MANUAL_READY":
            if observations:
                raise ContractValidationError(f"{metric_id} MANUAL_READY series must be empty")
            continue
        validated_points: list[tuple[Mapping[str, Any], list[Mapping[str, Any]]]] = []
        record_versions: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        records_by_identity: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        latest_point: Mapping[str, Any] | None = None
        for index, point in enumerate(observations):
            path = f"{metric_id}.observations[{index}]"
            expected_fields = {
                "date", "value", "direction", "record_count",
                "company_count", "comparable_count", "records",
            }
            if set(point) != expected_fields or point.get("value") is not None:
                raise ContractValidationError(f"{path} must use the exact null-valued manual point shape")
            records = point.get("records")
            if not isinstance(records, list) or not records:
                raise ContractValidationError(f"{path}.records must be non-empty")
            validated = [
                _validate_p3_manual_record(
                    record,
                    f"{path}.records[{record_index}]",
                    metric_id=metric_id,
                    point_date=point["date"],
                    generated_at=str(snapshot["generated_at"]),
                )
                for record_index, record in enumerate(records)
            ]
            if len({record["company_id"] for record in validated}) != len(validated):
                raise ContractValidationError(f"{path} must contain one latest record per company")
            expected_direction = _p3_manual_direction(validated)
            expected_counts = {
                "record_count": len(validated),
                "company_count": len({record["company_id"] for record in validated}),
                "comparable_count": sum(bool(record["comparable"]) for record in validated),
                "direction": expected_direction,
            }
            if any(point.get(field) != value for field, value in expected_counts.items()):
                raise ContractValidationError(f"{path} counts/direction do not reconcile")
            for record in validated:
                identity = (
                    record["company_id"],
                    record["period_end"],
                    record["metric_id"],
                    record["filing_accession"],
                )
                existing_identity = records_by_identity.get(identity)
                if existing_identity is not None and existing_identity != record:
                    raise ContractValidationError(
                        f"{path} redefines one manual CSV record identity"
                    )
                records_by_identity[identity] = record
                version_key = (
                    record["company_id"],
                    record["as_of"],
                    record["period_end"],
                    record["filing_accepted_at"],
                    record["reviewed_at"],
                    record["filing_accession"],
                )
                existing = record_versions.get(version_key)
                if existing is not None and existing != record:
                    raise ContractValidationError(
                        f"{path} contains conflicting versions of one reviewed record"
                    )
                record_versions[version_key] = record
            validated_points.append((point, validated))
            latest_point = point
        if latest_point is None:
            raise ContractValidationError(f"{metric_id} ACTIVE_FREE series must be non-empty")
        record_pool = list(record_versions.values())
        expected_point_dates = sorted({record["as_of"] for record in record_pool})
        actual_point_dates = [point["date"] for point, _ in validated_points]
        if actual_point_dates != expected_point_dates:
            raise ContractValidationError(
                f"{metric_id} manual points must equal the reviewed as-of dates"
            )
        for point, _ in validated_points:
            point_day = date.fromisoformat(point["date"])
            latest_by_company: dict[str, Mapping[str, Any]] = {}
            for record in record_pool:
                record_day = date.fromisoformat(record["as_of"])
                if (
                    record_day > point_day
                    or (point_day - record_day).days > P3_MANUAL_MAX_AGE_DAYS
                ):
                    continue
                current = latest_by_company.get(record["company_id"])
                record_key = (
                    record["as_of"],
                    record["period_end"],
                    record["filing_accepted_at"],
                    record["reviewed_at"],
                    record["filing_accession"],
                )
                current_key = (
                    current["as_of"],
                    current["period_end"],
                    current["filing_accepted_at"],
                    current["reviewed_at"],
                    current["filing_accession"],
                ) if current is not None else None
                if current_key is None or record_key > current_key:
                    latest_by_company[record["company_id"]] = record
            expected_records = [
                latest_by_company[company_id]
                for company_id in sorted(latest_by_company)
            ]
            if point["records"] != expected_records:
                raise ContractValidationError(
                    f"{metric_id} manual point {point['date']} does not use cumulative latest evidence"
                )
        detail = metric["details"]["manual_evidence"]
        if (
            detail["records"] != latest_point["records"]
            or detail["observation_date"] != latest_point["date"]
            or detail["direction"] != latest_point["direction"]
            or detail["record_count"] != latest_point["record_count"]
            or detail["company_count"] != latest_point["company_count"]
            or detail["comparable_count"] != latest_point["comparable_count"]
        ):
            raise ContractValidationError(f"{metric_id}.manual_evidence must match full-series endpoint")


METHODOLOGY_FIELDS = frozenset(
    {
        "question",
        "definition",
        "why_it_matters",
        "direction",
        "calculation",
        "frequency_and_lag",
        "common_misreads",
        "technical_distortions",
        "confirm_with",
        "cannot_infer",
        "source_and_license_note",
        "proxy_disclosure",
    }
)


class Availability(StrEnum):
    ACTIVE_FREE = "ACTIVE_FREE"
    ACTIVE_PROXY = "ACTIVE_PROXY"
    MANUAL_READY = "MANUAL_READY"
    UNAVAILABLE_FREE = "UNAVAILABLE_FREE"


class Health(StrEnum):
    OK = "OK"
    STALE = "STALE"
    ERROR = "ERROR"
    NOT_RELEASED_YET = "NOT_RELEASED_YET"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Freshness(StrEnum):
    FRESH = "FRESH"
    LATE = "LATE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ContractValidationError(ValueError):
    """Raised when a schema 2.3.0 record violates the canonical contract."""


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{path} must be an object")
    return value


def _require_nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{path} must be a non-empty string")
    return value


def _require_enum(enum_type: type[StrEnum], value: Any, path: str) -> StrEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ContractValidationError(f"{path} must be one of: {allowed}") from exc


def _validate_optional_date(value: Any, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ContractValidationError(f"{path} must be an ISO date or null")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ContractValidationError(f"{path} must be an ISO date") from exc


def _validate_optional_datetime(value: Any, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ContractValidationError(f"{path} must be an ISO-8601 datetime or null")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractValidationError(f"{path} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ContractValidationError(f"{path} must include a timezone")


def _validate_required_datetime(value: Any, path: str) -> None:
    if value is None:
        raise ContractValidationError(f"{path} must be an ISO-8601 datetime")
    _validate_optional_datetime(value, path)


def _validate_optional_utc_datetime(value: Any, path: str) -> None:
    _validate_optional_datetime(value, path)
    if value is None:
        return
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContractValidationError(f"{path} must use UTC")


def _validate_required_utc_datetime(value: Any, path: str) -> None:
    if value is None:
        raise ContractValidationError(f"{path} must be an ISO-8601 UTC datetime")
    _validate_optional_utc_datetime(value, path)


def _validate_nullable_number(value: Any, path: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractValidationError(f"{path} must be numeric or null")
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractValidationError(f"{path} must be finite")


def _validate_optional_string(value: Any, path: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ContractValidationError(f"{path} must be a string or null")


def _validate_string_list(value: Any, path: str) -> None:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ContractValidationError(f"{path} must be a string list")


def _validate_point(value: Any, path: str) -> None:
    point = _require_mapping(value, path)
    _validate_optional_date(point.get("date"), f"{path}.date")
    if point.get("date") is None:
        raise ContractValidationError(f"{path}.date must be an ISO date")
    _validate_nullable_number(point.get("value"), f"{path}.value")


def _validate_srf_point(value: Any, path: str) -> None:
    point = _require_mapping(value, path)
    _validate_point(point, path)
    for field in (
        "accepted_amount_usd_bn",
        "alert_eligible_accepted_amount_usd_bn",
        "exercise_accepted_amount_usd_bn",
    ):
        amount = point.get(field)
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(float(amount))
            or amount < 0
        ):
            raise ContractValidationError(f"{path}.{field} must be finite and non-negative")
    for field in ("has_technical_exercise", "technical_exercise"):
        if not isinstance(point.get(field), bool):
            raise ContractValidationError(f"{path}.{field} must be boolean")
    if point.get("classification_complete") is not True:
        raise ContractValidationError(f"{path}.classification_complete must be true")
    accepted = float(point["accepted_amount_usd_bn"])
    eligible = float(point["alert_eligible_accepted_amount_usd_bn"])
    exercise = float(point["exercise_accepted_amount_usd_bn"])
    if point.get("value") != point.get("accepted_amount_usd_bn"):
        raise ContractValidationError(f"{path}.value must equal accepted amount")
    if abs((eligible + exercise) - accepted) > 1e-9:
        raise ContractValidationError(f"{path} eligible and exercise amounts must reconcile")
    if point["technical_exercise"] and (
        not point["has_technical_exercise"] or eligible != 0
    ):
        raise ContractValidationError(
            f"{path} technical-only classification does not reconcile"
        )


VIDEO_P0_STATUS = frozenset(
    {
        "GREEN",
        "YELLOW",
        "RED",
        "EXTREME_CONTEXT_REQUIRED",
        "EXTREME_CONFIRMED",
        "UNAVAILABLE",
    }
)
VIDEO_P0_DATA_STATUS = frozenset(
    {"CURRENT", "LAST_GOOD", "PARTIAL", "UNAVAILABLE"}
)
VIDEO_P0_CONFIDENCE = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})
VIDEO_P0_EVALUATION_STATES = frozenset(
    {"CURRENT", "LAST_GOOD", "STALE", "MISSING", "DISABLED", "REVIEW_REQUIRED"}
)
VIDEO_P0_OPERATORS = frozenset({">", ">=", "<", "<=", "="})
VIDEO_P0_CLAUSE_IDS = {
    "yellow": (
        "sofr_positive_streak",
        "reserve_below_yellow",
        "reserve_change_4w_negative",
        "tga_near_1t",
    ),
    "red": (
        "sofr_spread_above_red",
        "reserve_below_red",
        "srf_positive_days",
    ),
    "extreme": (
        "reserve_below_extreme",
        "reserve_rapid_decline",
        "no_major_crisis",
    ),
}
VIDEO_P0_NOTATION_KEYS = (
    "evaluation_time",
    "spread",
    "positive_streak",
    "reserves",
    "reserve_change_4w",
    "tga",
    "srf_positive_days",
    "reserve_decline_p10",
    "crisis_context",
    "logical_and",
    "logical_or",
    "logical_iff",
    "extreme_candidate",
    "extreme_confirmed",
    "source_spread_red",
    "source_reserves_yellow",
    "source_reserves_red",
    "source_reserves_extreme",
    "source_tga_target",
    "op_positive_streak",
    "op_tga_floor",
    "op_srf_2_of_3",
    "op_rapid_decline",
    "manual_crisis_context",
)
VIDEO_P0_NOTATION_KINDS = {
    **{key: "MATHEMATICAL_NOTATION" for key in VIDEO_P0_NOTATION_KEYS[:14]},
    **{key: "VIDEO_SOURCE_RULE" for key in VIDEO_P0_NOTATION_KEYS[14:19]},
    **{
        key: "DASHBOARD_OPERATIONALIZATION"
        for key in VIDEO_P0_NOTATION_KEYS[19:23]
    },
    "manual_crisis_context": "MANUAL_CONTEXT",
}
VIDEO_P0_SOURCE_URL = "https://www.youtube.com/watch?v=MrnjBdgQPLU"
VIDEO_P0_SOURCE_TITLE = (
    "一個月前全網喊AI泡沫要崩，我說鬼故事是洗盤不是葬禮，二波窗口鎖死7月底8月初！"
    "對賭：納指洗完近一成，道指標普齊創新高，美光單日暴拉18.4%！復盤釘死，"
    "二波打法五步三開關全套交付"
)


def _require_exact_fields(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], path: str
) -> None:
    actual = set(value)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ContractValidationError(f"{path} fields are invalid: {'; '.join(details)}")


def _validate_formula_scalar(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ContractValidationError(
            f"{path} must be a finite number, string, boolean, or null"
        )


def _tri_and(values: list[bool | None]) -> bool | None:
    if False in values:
        return False
    return None if None in values else True


def _tri_or(values: list[bool | None]) -> bool | None:
    if True in values:
        return True
    return None if None in values else False


def _same_scalar(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(float(left)) and math.isfinite(float(right)) and math.isclose(
            float(left), float(right), abs_tol=1e-9
        )
    return left == right


def _evaluate_operator(left: Any, operator: str, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        if operator != "=":
            raise ContractValidationError("boolean formula values only support =")
        return left is right
    if operator == "=":
        return left == right
    if (
        not isinstance(left, (int, float))
        or isinstance(left, bool)
        or not isinstance(right, (int, float))
        or isinstance(right, bool)
    ):
        raise ContractValidationError("ordered formula comparison requires numeric values")
    return {
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }[operator]


def _validate_video_source(model: Mapping[str, Any]) -> None:
    source = _require_mapping(model.get("source"), "decision model.source")
    _require_exact_fields(
        source, {"title", "display_title", "author", "url", "segments"},
        "decision model.source",
    )
    if (
        source.get("title") != VIDEO_P0_SOURCE_TITLE
        or source.get("author") != "一个狠人"
        or source.get("url") != VIDEO_P0_SOURCE_URL
        or not isinstance(source.get("display_title"), str)
        or not source["display_title"].strip()
    ):
        raise ContractValidationError("decision model source does not match the audited video")
    expected_segments = (
        ("yellow_red", 1380, 1440),
        ("reserve_exit_1", 1140, 1200),
        ("reserve_exit_2", 1560, 1620),
    )
    segments = source.get("segments")
    if not isinstance(segments, list) or len(segments) != len(expected_segments):
        raise ContractValidationError("decision model source.segments must contain three entries")
    for index, (segment, expected) in enumerate(zip(segments, expected_segments, strict=True)):
        path = f"decision model.source.segments[{index}]"
        segment = _require_mapping(segment, path)
        _require_exact_fields(
            segment,
            {"segment_id", "label", "start_seconds", "end_seconds", "timestamp_url"},
            path,
        )
        segment_id, start, end = expected
        if (
            segment.get("segment_id") != segment_id
            or segment.get("start_seconds") != start
            or segment.get("end_seconds") != end
            or segment.get("timestamp_url") != f"{VIDEO_P0_SOURCE_URL}&t={start}s"
            or not isinstance(segment.get("label"), str)
            or not segment["label"].strip()
        ):
            raise ContractValidationError(f"{path} does not match the audited segment")


def _formula_metric_expectations(
    metrics: Mapping[str, Any],
) -> dict[str, tuple[str | None, str, Any, str | None, Any]]:
    spread = _require_mapping(metrics.get("sofr_iorb_spread_bp"), "spread metric")
    reserve = _require_mapping(metrics.get("reserve_balances"), "reserve metric")
    tga = _require_mapping(metrics.get("tga_daily"), "TGA metric")
    srf = _require_mapping(metrics.get("srf_accepted"), "SRF metric")
    reserve_stats = _require_mapping(reserve.get("statistics"), "reserve statistics")
    spread_stats = _require_mapping(spread.get("statistics"), "spread statistics")
    srf_stats = _require_mapping(srf.get("statistics"), "SRF statistics")
    return {
        "sofr_positive_streak": (
            "sofr_iorb_spread_bp", ">=", 3, "observations",
            spread_stats.get("positive_streak"),
        ),
        "reserve_below_yellow": (
            "reserve_balances", "<", 2900, "USD bn", reserve.get("value")
        ),
        "reserve_change_4w_negative": (
            "reserve_balances", "<", 0, "USD bn", reserve_stats.get("change_4w")
        ),
        "tga_near_1t": ("tga_daily", ">=", 950, "USD bn", tga.get("value")),
        "sofr_spread_above_red": (
            "sofr_iorb_spread_bp", ">", 3, "bp", spread.get("value")
        ),
        "reserve_below_red": (
            "reserve_balances", "<", 2800, "USD bn", reserve.get("value")
        ),
        "srf_positive_days": (
            "srf_accepted", ">=", 2, "days in latest 3 completed days",
            srf_stats.get("positive_nontechnical_latest_3"),
        ),
        "reserve_below_extreme": (
            "reserve_balances", "<", 2500, "USD bn", reserve.get("value")
        ),
        "reserve_rapid_decline": (
            "reserve_balances", "<=", reserve_stats.get("trailing_5y_p10"),
            "USD bn", reserve_stats.get("change_4w"),
        ),
    }


def _validate_formula_clause(
    clause: Any,
    *,
    expected_id: str,
    expected_order: int,
    metrics: Mapping[str, Any],
    context: Mapping[str, Any],
    disabled: bool,
) -> Mapping[str, Any]:
    path = f"decision model clause {expected_id}"
    clause = _require_mapping(clause, path)
    _require_exact_fields(
        clause,
        {
            "clause_id", "order", "label", "metric_id", "operator", "threshold",
            "threshold_unit", "current_value", "current_unit", "met",
            "observation_date", "released_at", "quality_status", "freshness",
            "evaluation_state", "basis", "note",
        },
        path,
    )
    if clause.get("clause_id") != expected_id or clause.get("order") != expected_order:
        raise ContractValidationError(f"{path} ID/order does not match the stable contract")
    if not isinstance(clause.get("label"), str) or not clause["label"].strip():
        raise ContractValidationError(f"{path}.label must be non-empty")
    if clause.get("operator") not in VIDEO_P0_OPERATORS:
        raise ContractValidationError(f"{path}.operator is invalid")
    _validate_formula_scalar(clause.get("threshold"), f"{path}.threshold")
    _validate_formula_scalar(clause.get("current_value"), f"{path}.current_value")
    _validate_optional_string(clause.get("threshold_unit"), f"{path}.threshold_unit")
    _validate_optional_string(clause.get("current_unit"), f"{path}.current_unit")
    if clause.get("met") is not None and not isinstance(clause.get("met"), bool):
        raise ContractValidationError(f"{path}.met must be boolean or null")
    _validate_optional_date(clause.get("observation_date"), f"{path}.observation_date")
    _validate_optional_utc_datetime(clause.get("released_at"), f"{path}.released_at")
    _require_enum(Health, clause.get("quality_status"), f"{path}.quality_status")
    _require_enum(Freshness, clause.get("freshness"), f"{path}.freshness")
    if clause.get("evaluation_state") not in VIDEO_P0_EVALUATION_STATES:
        raise ContractValidationError(f"{path}.evaluation_state is invalid")
    if not isinstance(clause.get("note"), str):
        raise ContractValidationError(f"{path}.note must be a string")
    basis = clause.get("basis")
    if not isinstance(basis, list) or len(basis) != 2:
        raise ContractValidationError(f"{path}.basis must contain two provenance records")
    kinds = []
    for index, item in enumerate(basis):
        item = _require_mapping(item, f"{path}.basis[{index}]")
        _require_exact_fields(
            item, {"kind", "label", "source_segment_id", "note"},
            f"{path}.basis[{index}]",
        )
        if item.get("kind") not in {
            "VIDEO_SOURCE_RULE", "DASHBOARD_OPERATIONALIZATION", "MANUAL_CONTEXT"
        } or item.get("kind") in kinds:
            raise ContractValidationError(f"{path}.basis kind is invalid or duplicated")
        kinds.append(item["kind"])
        _require_nonempty_string(item.get("label"), f"{path}.basis[{index}].label")
        _validate_optional_string(
            item.get("source_segment_id"), f"{path}.basis[{index}].source_segment_id"
        )
        if not isinstance(item.get("note"), str):
            raise ContractValidationError(f"{path}.basis[{index}].note must be a string")
    if "VIDEO_SOURCE_RULE" not in kinds or (
        expected_id == "no_major_crisis"
        and "MANUAL_CONTEXT" not in kinds
    ) or (
        expected_id != "no_major_crisis"
        and "DASHBOARD_OPERATIONALIZATION" not in kinds
    ):
        raise ContractValidationError(f"{path}.basis does not preserve both source layers")

    if disabled:
        if clause.get("met") is not None or clause.get("evaluation_state") != "DISABLED":
            raise ContractValidationError(f"{path} must be unknown/disabled")
        return clause

    if expected_id == "no_major_crisis":
        expected_current = context.get("status")
        expected_met = None if expected_current == "UNKNOWN" else expected_current == "NO_MAJOR_CRISIS"
        if (
            clause.get("metric_id") is not None
            or clause.get("operator") != "="
            or clause.get("threshold") != "NO_MAJOR_CRISIS"
            or clause.get("threshold_unit") is not None
            or clause.get("current_value") != expected_current
            or clause.get("current_unit") is not None
            or clause.get("met") is not expected_met
            or clause.get("observation_date") != context.get("as_of")
            or clause.get("released_at") != context.get("reviewed_at")
            or clause.get("evaluation_state")
            != ("REVIEW_REQUIRED" if expected_met is None else "CURRENT")
        ):
            raise ContractValidationError(f"{path} does not reconcile with crisis context")
        return clause

    expected = _formula_metric_expectations(metrics)[expected_id]
    metric_id, operator, threshold, threshold_unit, current = expected
    metric = _require_mapping(metrics.get(metric_id), f"metric {metric_id}")
    quality = _require_mapping(metric.get("quality"), f"metric {metric_id}.quality")
    if (
        clause.get("metric_id") != metric_id
        or clause.get("operator") != operator
        or not _same_scalar(clause.get("threshold"), threshold)
        or clause.get("threshold_unit") != threshold_unit
        or not _same_scalar(clause.get("current_value"), current)
        or clause.get("observation_date") != metric.get("observation_date")
        or clause.get("released_at") != metric.get("released_at")
        or clause.get("quality_status") != quality.get("status")
        or clause.get("freshness") != quality.get("freshness")
    ):
        raise ContractValidationError(f"{path} does not reconcile with its metric/threshold")
    status = quality.get("status")
    freshness = quality.get("freshness")
    usable = current is not None and (
        (status == "OK" and freshness in {"FRESH", "LATE"})
        or status == "NOT_RELEASED_YET"
    )
    expected_state = (
        "MISSING" if current is None
        else "CURRENT" if usable and status == "OK" and freshness == "FRESH"
        else "LAST_GOOD" if usable
        else "STALE" if status == "STALE" or freshness == "STALE"
        else "MISSING"
    )
    if expected_id == "srf_positive_days" and usable and (
        not isinstance(quality.get("sample_size"), int)
        or quality.get("sample_size") < 3
    ):
        expected_state = "MISSING"
        usable = False
    if clause.get("evaluation_state") != expected_state:
        raise ContractValidationError(f"{path}.evaluation_state does not match quality")
    expected_met = (
        _evaluate_operator(current, operator, threshold)
        if usable and threshold is not None
        else None
    )
    if clause.get("met") is not expected_met:
        raise ContractValidationError(f"{path}.met does not reconcile")
    return clause


def _validate_video_p0_notation(value: Any, path: str) -> None:
    if not isinstance(value, list) or len(value) != len(VIDEO_P0_NOTATION_KEYS):
        raise ContractValidationError(
            f"{path} must contain exactly {len(VIDEO_P0_NOTATION_KEYS)} entries"
        )
    keys: list[str] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _require_mapping(item, item_path)
        _require_exact_fields(
            item,
            {
                "key",
                "symbol_tex",
                "label",
                "definition",
                "unit",
                "source_kind",
                "note",
            },
            item_path,
        )
        key = item.get("key")
        _require_nonempty_string(key, f"{item_path}.key")
        assert isinstance(key, str)
        keys.append(key)
        for field in ("symbol_tex", "label", "definition", "note"):
            _require_nonempty_string(item.get(field), f"{item_path}.{field}")
        unit = item.get("unit")
        if unit is not None:
            _require_nonempty_string(unit, f"{item_path}.unit")
        if item.get("source_kind") != VIDEO_P0_NOTATION_KINDS.get(key):
            raise ContractValidationError(f"{item_path}.source_kind is invalid")
    if tuple(keys) != VIDEO_P0_NOTATION_KEYS:
        if len(keys) != len(set(keys)):
            raise ContractValidationError(f"{path} contains duplicate keys")
        raise ContractValidationError(f"{path} keys or order are invalid")


def _validate_video_p0_model(
    value: Any, *, metrics: Mapping[str, Any], generated_at: str
) -> None:
    path = "snapshot.decision_models.p0_video_liquidity"
    model = _require_mapping(value, path)
    _require_exact_fields(
        model,
        {
            "model_id", "label", "enabled", "status", "data_status", "confidence",
            "availability_reason", "evaluated_at", "source", "thresholds",
            "operationalizations", "crisis_context", "notation", "formulas",
            "technical_flags", "notes",
        },
        path,
    )
    if model.get("model_id") != "henren778_p0_liquidity":
        raise ContractValidationError(f"{path}.model_id is invalid")
    _require_nonempty_string(model.get("label"), f"{path}.label")
    if not isinstance(model.get("enabled"), bool):
        raise ContractValidationError(f"{path}.enabled must be boolean")
    if model.get("status") not in VIDEO_P0_STATUS:
        raise ContractValidationError(f"{path}.status is invalid")
    if model.get("data_status") not in VIDEO_P0_DATA_STATUS:
        raise ContractValidationError(f"{path}.data_status is invalid")
    if model.get("confidence") not in VIDEO_P0_CONFIDENCE:
        raise ContractValidationError(f"{path}.confidence is invalid")
    _validate_optional_string(model.get("availability_reason"), f"{path}.availability_reason")
    _validate_required_utc_datetime(model.get("evaluated_at"), f"{path}.evaluated_at")
    if model.get("evaluated_at") != generated_at:
        raise ContractValidationError(f"{path}.evaluated_at must equal snapshot.generated_at")
    _validate_video_source(model)

    thresholds = _require_mapping(model.get("thresholds"), f"{path}.thresholds")
    _require_exact_fields(
        thresholds, {"yellow", "red", "extreme", "tga_source_target_usd_bn"},
        f"{path}.thresholds",
    )
    yellow_thresholds = _require_mapping(thresholds.get("yellow"), f"{path}.thresholds.yellow")
    red_thresholds = _require_mapping(thresholds.get("red"), f"{path}.thresholds.red")
    extreme_thresholds = _require_mapping(thresholds.get("extreme"), f"{path}.thresholds.extreme")
    _require_exact_fields(
        yellow_thresholds,
        {"spread_positive_bp", "positive_streak_observations", "reserve_usd_bn", "reserve_change_4w_usd_bn", "tga_operational_floor_usd_bn"},
        f"{path}.thresholds.yellow",
    )
    _require_exact_fields(
        red_thresholds,
        {"spread_bp", "reserve_usd_bn", "srf_positive_days_required", "srf_window_completed_days"},
        f"{path}.thresholds.red",
    )
    _require_exact_fields(
        extreme_thresholds, {"reserve_usd_bn", "decline_percentile"},
        f"{path}.thresholds.extreme",
    )
    expected_thresholds = {
        "spread_positive_bp": (yellow_thresholds.get("spread_positive_bp"), 0),
        "positive_streak_observations": (yellow_thresholds.get("positive_streak_observations"), 3),
        "yellow_reserve": (yellow_thresholds.get("reserve_usd_bn"), 2900),
        "reserve_change": (yellow_thresholds.get("reserve_change_4w_usd_bn"), 0),
        "tga_floor": (yellow_thresholds.get("tga_operational_floor_usd_bn"), 950),
        "red_spread": (red_thresholds.get("spread_bp"), 3),
        "red_reserve": (red_thresholds.get("reserve_usd_bn"), 2800),
        "srf_required": (red_thresholds.get("srf_positive_days_required"), 2),
        "srf_window": (red_thresholds.get("srf_window_completed_days"), 3),
        "extreme_reserve": (extreme_thresholds.get("reserve_usd_bn"), 2500),
        "tga_target": (thresholds.get("tga_source_target_usd_bn"), 1000),
    }
    for field, (actual, expected) in expected_thresholds.items():
        if not _same_scalar(actual, expected):
            raise ContractValidationError(f"{path}.thresholds {field} is invalid")
    if extreme_thresholds.get("decline_percentile") != "TRAILING_5Y_P10":
        raise ContractValidationError(f"{path}.thresholds.extreme decline percentile is invalid")
    # Import lazily to keep this collector-independent contract module usable by
    # pipeline.config while making the published presentation auditable against
    # the same canonical builder used by the evaluator.
    from pipeline.rules.p0_video_model import build_video_p0_formula_presentation

    presentation = build_video_p0_formula_presentation(
        streak_required=int(yellow_thresholds["positive_streak_observations"]),
        yellow_reserve_tn=float(yellow_thresholds["reserve_usd_bn"]) / 1000,
        red_reserve_tn=float(red_thresholds["reserve_usd_bn"]) / 1000,
        extreme_reserve_tn=float(extreme_thresholds["reserve_usd_bn"]) / 1000,
        tga_floor_tn=float(yellow_thresholds["tga_operational_floor_usd_bn"]) / 1000,
        tga_target_tn=float(thresholds["tga_source_target_usd_bn"]) / 1000,
        spread_threshold=float(red_thresholds["spread_bp"]),
        srf_required=int(red_thresholds["srf_positive_days_required"]),
        srf_window=int(red_thresholds["srf_window_completed_days"]),
    )
    operationalizations = _require_mapping(
        model.get("operationalizations"), f"{path}.operationalizations"
    )
    for key, item in operationalizations.items():
        _require_nonempty_string(key, f"{path}.operationalizations key")
        if not isinstance(item, (str, bool, int, float)) or (
            isinstance(item, float) and not math.isfinite(item)
        ):
            raise ContractValidationError(f"{path}.operationalizations.{key} is invalid")

    context = _require_mapping(model.get("crisis_context"), f"{path}.crisis_context")
    _require_exact_fields(
        context, {"status", "as_of", "reviewed_at", "reviewer", "note"},
        f"{path}.crisis_context",
    )
    if context.get("status") not in {
        "UNKNOWN", "MAJOR_CRISIS_PRESENT", "NO_MAJOR_CRISIS"
    }:
        raise ContractValidationError(f"{path}.crisis_context.status is invalid")
    if context.get("status") == "UNKNOWN":
        if any(context.get(field) is not None for field in ("as_of", "reviewed_at", "reviewer", "note")):
            raise ContractValidationError(f"{path}.crisis_context UNKNOWN metadata must be null")
    else:
        _validate_optional_date(context.get("as_of"), f"{path}.crisis_context.as_of")
        _validate_required_utc_datetime(context.get("reviewed_at"), f"{path}.crisis_context.reviewed_at")
        _require_nonempty_string(context.get("reviewer"), f"{path}.crisis_context.reviewer")
        _require_nonempty_string(context.get("note"), f"{path}.crisis_context.note")

    _validate_video_p0_notation(model.get("notation"), f"{path}.notation")
    if model.get("notation") != presentation["notation"]:
        raise ContractValidationError(f"{path}.notation content does not reconcile")

    formulas = _require_mapping(model.get("formulas"), f"{path}.formulas")
    _require_exact_fields(formulas, {"yellow", "red", "extreme"}, f"{path}.formulas")
    disabled = model.get("enabled") is False
    validated: dict[str, list[Mapping[str, Any]]] = {}
    for formula_id, ids in VIDEO_P0_CLAUSE_IDS.items():
        formula = _require_mapping(formulas.get(formula_id), f"{path}.formulas.{formula_id}")
        expected_fields = {
            "expression", "display_tex", "plain_language", "triggered", "clauses"
        }
        if formula_id == "red":
            expected_fields.add("routes")
        if formula_id == "extreme":
            expected_fields |= {"candidate", "context_required"}
        _require_exact_fields(formula, expected_fields, f"{path}.formulas.{formula_id}")
        _require_nonempty_string(formula.get("expression"), f"{path}.formulas.{formula_id}.expression")
        _require_nonempty_string(formula.get("display_tex"), f"{path}.formulas.{formula_id}.display_tex")
        _require_nonempty_string(formula.get("plain_language"), f"{path}.formulas.{formula_id}.plain_language")
        expected_presentation = presentation[formula_id]
        if any(
            formula.get(field) != expected_presentation[field]
            for field in ("expression", "display_tex", "plain_language")
        ):
            raise ContractValidationError(
                f"{path}.formulas.{formula_id} presentation does not reconcile"
            )
        if formula.get("triggered") is not None and not isinstance(formula.get("triggered"), bool):
            raise ContractValidationError(f"{path}.formulas.{formula_id}.triggered is invalid")
        clauses = formula.get("clauses")
        if not isinstance(clauses, list) or len(clauses) != len(ids):
            raise ContractValidationError(f"{path}.formulas.{formula_id}.clauses length is invalid")
        validated[formula_id] = [
            _validate_formula_clause(
                clause,
                expected_id=clause_id,
                expected_order=index + 1,
                metrics=metrics,
                context=context,
                disabled=disabled,
            )
            for index, (clause, clause_id) in enumerate(zip(clauses, ids, strict=True))
        ]
    all_ids = [clause["clause_id"] for clauses in validated.values() for clause in clauses]
    if len(all_ids) != len(set(all_ids)):
        raise ContractValidationError(f"{path} contains duplicate clause IDs")

    yellow = formulas["yellow"]
    red = formulas["red"]
    extreme = formulas["extreme"]
    yellow_result = _tri_and([clause["met"] for clause in validated["yellow"]])
    route_a = _tri_and([clause["met"] for clause in validated["red"][:2]])
    route_b = validated["red"][2]["met"]
    red_result = _tri_or([route_a, route_b])
    candidate = _tri_and([clause["met"] for clause in validated["extreme"][:2]])
    extreme_result = _tri_and([candidate, validated["extreme"][2]["met"]])
    routes = red.get("routes")
    if not isinstance(routes, list) or len(routes) != 2:
        raise ContractValidationError(f"{path}.formulas.red.routes must contain two routes")
    expected_route_ids = ("spread_and_reserves", "srf_2_of_3")
    expected_route_clauses = (validated["red"][:2], validated["red"][2:])
    for index, route in enumerate(routes):
        route = _require_mapping(route, f"{path}.formulas.red.routes[{index}]")
        _require_exact_fields(
            route, {"route_id", "label", "expression", "triggered", "clauses"},
            f"{path}.formulas.red.routes[{index}]",
        )
        if (
            route.get("route_id") != expected_route_ids[index]
            or route.get("triggered") != (route_a if index == 0 else route_b)
            or route.get("clauses") != expected_route_clauses[index]
            or not isinstance(route.get("label"), str)
            or not route["label"].strip()
            or not isinstance(route.get("expression"), str)
            or not route["expression"].strip()
            or route.get("expression")
            != presentation["red"][
                "route_a_expression" if index == 0 else "route_b_expression"
            ]
        ):
            raise ContractValidationError(f"{path}.formulas.red route does not reconcile")
    if (
        yellow.get("triggered") != yellow_result
        or red.get("triggered") != red_result
        or extreme.get("candidate") != candidate
        or extreme.get("triggered") != extreme_result
        or extreme.get("context_required")
        is not (candidate is True and context.get("status") == "UNKNOWN")
    ):
        raise ContractValidationError(f"{path} formula truth values do not reconcile")

    if disabled:
        if (
            model.get("status") != "UNAVAILABLE"
            or model.get("data_status") != "UNAVAILABLE"
            or model.get("confidence") != "UNKNOWN"
            or model.get("availability_reason") != "DISABLED"
            or any(value is not None for value in (yellow_result, red_result, candidate))
        ):
            raise ContractValidationError(f"{path} disabled model must fail closed")
    else:
        if candidate is None and context.get("status") != "MAJOR_CRISIS_PRESENT":
            expected_status = "UNAVAILABLE"
        elif candidate is True and context.get("status") == "UNKNOWN":
            expected_status = "EXTREME_CONTEXT_REQUIRED"
        elif candidate is True and context.get("status") == "NO_MAJOR_CRISIS":
            expected_status = "EXTREME_CONFIRMED"
        elif red_result is None:
            expected_status = "UNAVAILABLE"
        elif red_result is True:
            expected_status = "RED"
        elif yellow_result is None:
            expected_status = "UNAVAILABLE"
        else:
            expected_status = "YELLOW" if yellow_result else "GREEN"
        if model.get("status") != expected_status:
            raise ContractValidationError(f"{path}.status does not reconcile with formula priority")
        if expected_status == "UNAVAILABLE":
            if model.get("data_status") != "UNAVAILABLE" or not model.get("availability_reason"):
                raise ContractValidationError(f"{path} unavailable model must include a reason")
        elif model.get("availability_reason") is not None:
            raise ContractValidationError(f"{path} available model cannot include an availability reason")
    if not isinstance(model.get("technical_flags"), list) or not all(
        isinstance(item, str) and item for item in model["technical_flags"]
    ):
        raise ContractValidationError(f"{path}.technical_flags must be a string list")
    if not isinstance(model.get("notes"), list) or not all(
        isinstance(item, str) and item for item in model["notes"]
    ):
        raise ContractValidationError(f"{path}.notes must be a non-empty string list")


def _require_exact_fields(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ContractValidationError(
            f"{path} must contain the exact field set"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; extra: {', '.join(extra)}" if extra else "")
        )


def _require_string_enum(value: Any, allowed: frozenset[str], path: str) -> str:
    if value not in allowed:
        raise ContractValidationError(
            f"{path} must be one of: {', '.join(sorted(allowed))}"
        )
    return str(value)


def _validate_nonnegative_integer(value: Any, path: str, *, positive: bool = False) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < (1 if positive else 0)
    ):
        qualifier = "positive" if positive else "non-negative"
        raise ContractValidationError(f"{path} must be a {qualifier} integer")
    return value


def _validate_rule_basis(value: Any, path: str) -> str:
    return _require_string_enum(value, INTERPRETATION_RULE_BASES, path)


def _validate_interpretation_view(value: Any, path: str, metric_ids: set[str] | None) -> None:
    view = _require_mapping(value, path)
    kind = view.get("kind")
    common_basis = lambda: _validate_rule_basis(view.get("basis"), f"{path}.basis")
    if kind == "REGIME_LADDER":
        _require_exact_fields(view, {"kind", "label", "rows", "note"}, path)
        _require_nonempty_string(view.get("label"), f"{path}.label")
        _require_nonempty_string(view.get("note"), f"{path}.note")
        rows = view.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ContractValidationError(f"{path}.rows must be a non-empty list")
        row_fields = {
            "label", "operator", "threshold", "upper_threshold", "unit",
            "rule", "basis", "active", "met",
        }
        for index, row_value in enumerate(rows):
            row_path = f"{path}.rows[{index}]"
            row = _require_mapping(row_value, row_path)
            _require_exact_fields(row, row_fields, row_path)
            for field in ("label", "operator", "unit", "rule"):
                _require_nonempty_string(row.get(field), f"{row_path}.{field}")
            _validate_nullable_number(row.get("threshold"), f"{row_path}.threshold")
            _validate_nullable_number(row.get("upper_threshold"), f"{row_path}.upper_threshold")
            _validate_rule_basis(row.get("basis"), f"{row_path}.basis")
            if not isinstance(row.get("active"), bool):
                raise ContractValidationError(f"{row_path}.active must be boolean")
            if row.get("met") is not None and not isinstance(row.get("met"), bool):
                raise ContractValidationError(f"{row_path}.met must be boolean or null")
        return
    if kind == "PERCENTILE_GAUGE":
        _require_exact_fields(
            view,
            {"kind", "label", "value", "unit", "percentile", "sample_size", "state", "slope", "slope_unit", "basis"},
            path,
        )
        for field in ("label", "unit", "state", "slope_unit"):
            _require_nonempty_string(view.get(field), f"{path}.{field}")
        for field in ("value", "percentile", "slope"):
            _validate_nullable_number(view.get(field), f"{path}.{field}")
        percentile = view.get("percentile")
        if percentile is not None and not 0 <= float(percentile) <= 1:
            raise ContractValidationError(f"{path}.percentile must be between zero and one")
        _validate_nonnegative_integer(view.get("sample_size"), f"{path}.sample_size")
        common_basis()
        return
    if kind == "EVENT_STEPPER":
        _require_exact_fields(
            view,
            {"kind", "label", "window_size", "positive_count", "required_count", "state", "technical_exercise", "basis"},
            path,
        )
        for field in ("label", "state"):
            _require_nonempty_string(view.get(field), f"{path}.{field}")
        window = _validate_nonnegative_integer(view.get("window_size"), f"{path}.window_size", positive=True)
        required = _validate_nonnegative_integer(view.get("required_count"), f"{path}.required_count", positive=True)
        if required > window:
            raise ContractValidationError(f"{path}.required_count cannot exceed window_size")
        count = view.get("positive_count")
        if count is not None:
            count = _validate_nonnegative_integer(count, f"{path}.positive_count")
            if count > window:
                raise ContractValidationError(f"{path}.positive_count cannot exceed window_size")
        if not isinstance(view.get("technical_exercise"), bool):
            raise ContractValidationError(f"{path}.technical_exercise must be boolean")
        common_basis()
        return
    if kind == "BREADTH_COUNTER":
        _require_exact_fields(
            view,
            {"kind", "label", "count", "total", "state", "members", "basis"},
            path,
        )
        for field in ("label", "state"):
            _require_nonempty_string(view.get(field), f"{path}.{field}")
        total = _validate_nonnegative_integer(view.get("total"), f"{path}.total", positive=True)
        count = view.get("count")
        if count is not None:
            count = _validate_nonnegative_integer(count, f"{path}.count")
            if count > total:
                raise ContractValidationError(f"{path}.count cannot exceed total")
        members = view.get("members")
        if not isinstance(members, list) or len(members) != total:
            raise ContractValidationError(f"{path}.members must match total")
        member_fields = {"metric_id", "state", "percentile", "slope", "confirming"}
        member_ids: list[str] = []
        for index, member_value in enumerate(members):
            member_path = f"{path}.members[{index}]"
            member = _require_mapping(member_value, member_path)
            _require_exact_fields(member, member_fields, member_path)
            member_id = _require_nonempty_string(member.get("metric_id"), f"{member_path}.metric_id")
            member_ids.append(member_id)
            if metric_ids is not None and member_id not in metric_ids:
                raise ContractValidationError(f"{member_path}.metric_id is unknown")
            _require_nonempty_string(member.get("state"), f"{member_path}.state")
            for field in ("percentile", "slope"):
                _validate_nullable_number(member.get(field), f"{member_path}.{field}")
            percentile = member.get("percentile")
            if percentile is not None and not 0 <= float(percentile) <= 1:
                raise ContractValidationError(f"{member_path}.percentile must be between zero and one")
            if member.get("confirming") is not None and not isinstance(member.get("confirming"), bool):
                raise ContractValidationError(f"{member_path}.confirming must be boolean or null")
        if len(member_ids) != len(set(member_ids)):
            raise ContractValidationError(f"{path}.members metric IDs must be unique")
        if total != 3 or tuple(member_ids) != INTERPRETATION_BREADTH_METRIC_IDS:
            raise ContractValidationError(
                f"{path}.members must be exactly EFFR, TGCR, BGCR in canonical order"
            )
        common_basis()
        return
    if kind == "DIRECTIONAL":
        _require_exact_fields(view, {"kind", "label", "value", "change", "unit", "state", "basis"}, path)
        for field in ("label", "unit", "state"):
            _require_nonempty_string(view.get(field), f"{path}.{field}")
        _validate_nullable_number(view.get("value"), f"{path}.value")
        _validate_nullable_number(view.get("change"), f"{path}.change")
        common_basis()
        return
    if kind == "CROSS_CHECK":
        _require_exact_fields(
            view,
            {"kind", "label", "primary_metric_id", "comparison_metric_id", "difference", "unit", "percentile", "sample_size", "state", "basis"},
            path,
        )
        for field in ("label", "primary_metric_id", "comparison_metric_id", "unit", "state"):
            _require_nonempty_string(view.get(field), f"{path}.{field}")
        if metric_ids is not None:
            for field in ("primary_metric_id", "comparison_metric_id"):
                if view[field] not in metric_ids:
                    raise ContractValidationError(f"{path}.{field} is unknown")
        _validate_nullable_number(view.get("difference"), f"{path}.difference")
        _validate_nullable_number(view.get("percentile"), f"{path}.percentile")
        percentile = view.get("percentile")
        if percentile is not None and not 0 <= float(percentile) <= 1:
            raise ContractValidationError(f"{path}.percentile must be between zero and one")
        _validate_nonnegative_integer(view.get("sample_size"), f"{path}.sample_size")
        common_basis()
        return
    raise ContractValidationError(f"{path}.kind is invalid")


def _validate_metric_interpretation(
    value: Any, path: str, *, metric_ids: set[str] | None = None
) -> None:
    interpretation = _require_mapping(value, path)
    expected_fields = {
        "role", "classification_type", "data_state", "numeric_direction",
        "impact", "state", "severity", "confidence", "headline",
        "what_it_measures", "current_reasons", "next_boundary", "views",
        "confirm_with", "cannot_infer", "rule_basis",
    }
    _require_exact_fields(interpretation, expected_fields, path)
    _require_string_enum(interpretation.get("role"), INTERPRETATION_ROLES, f"{path}.role")
    _require_string_enum(interpretation.get("classification_type"), INTERPRETATION_CLASSIFICATIONS, f"{path}.classification_type")
    _require_string_enum(interpretation.get("data_state"), INTERPRETATION_DATA_STATES, f"{path}.data_state")
    _require_string_enum(interpretation.get("numeric_direction"), INTERPRETATION_DIRECTIONS, f"{path}.numeric_direction")
    _require_string_enum(interpretation.get("impact"), INTERPRETATION_IMPACTS, f"{path}.impact")
    _require_string_enum(interpretation.get("severity"), INTERPRETATION_SEVERITIES, f"{path}.severity")
    _require_string_enum(interpretation.get("confidence"), INTERPRETATION_CONFIDENCES, f"{path}.confidence")
    for field in ("state", "headline", "what_it_measures", "cannot_infer"):
        _require_nonempty_string(interpretation.get(field), f"{path}.{field}")
    reasons = interpretation.get("current_reasons")
    if not isinstance(reasons, list) or not reasons:
        raise ContractValidationError(f"{path}.current_reasons must be a non-empty list")
    for index, reason in enumerate(reasons):
        _require_nonempty_string(reason, f"{path}.current_reasons[{index}]")
    confirmations = interpretation.get("confirm_with")
    if not isinstance(confirmations, list):
        raise ContractValidationError(f"{path}.confirm_with must be a list")
    for index, metric_id in enumerate(confirmations):
        metric_id = _require_nonempty_string(metric_id, f"{path}.confirm_with[{index}]")
        if metric_ids is not None and metric_id not in metric_ids:
            raise ContractValidationError(f"{path}.confirm_with[{index}] is unknown")
    if len(confirmations) != len(set(confirmations)):
        raise ContractValidationError(f"{path}.confirm_with must be unique")
    bases = interpretation.get("rule_basis")
    if not isinstance(bases, list) or not bases:
        raise ContractValidationError(f"{path}.rule_basis must be a non-empty list")
    for index, basis in enumerate(bases):
        _validate_rule_basis(basis, f"{path}.rule_basis[{index}]")
    if len(bases) != len(set(bases)):
        raise ContractValidationError(f"{path}.rule_basis must be unique")
    boundary = interpretation.get("next_boundary")
    if boundary is not None:
        boundary = _require_mapping(boundary, f"{path}.next_boundary")
        _require_exact_fields(boundary, {"label", "current", "threshold", "distance", "unit", "rule", "basis"}, f"{path}.next_boundary")
        for field in ("label", "unit", "rule"):
            _require_nonempty_string(boundary.get(field), f"{path}.next_boundary.{field}")
        for field in ("current", "threshold", "distance"):
            _validate_nullable_number(boundary.get(field), f"{path}.next_boundary.{field}")
        _validate_rule_basis(boundary.get("basis"), f"{path}.next_boundary.basis")
    views = interpretation.get("views")
    if not isinstance(views, list) or not views:
        raise ContractValidationError(f"{path}.views must be a non-empty list")
    for index, view in enumerate(views):
        _validate_interpretation_view(view, f"{path}.views[{index}]", metric_ids)
    context_roles = {
        "POLICY_RATE_ANCHOR", "POLICY_ANCHORED_MARKET_RATE",
        "TREASURY_CASH_FLOW", "LIQUIDITY_BUFFER", "BALANCE_SHEET_DRIVER",
        "CROSS_CHECK",
    }
    exposed_bases: list[str] = (
        ["CONTEXT_ONLY"] if interpretation["role"] in context_roles else []
    )

    def add_exposed_basis(basis: Any) -> None:
        if isinstance(basis, str) and basis not in exposed_bases:
            exposed_bases.append(basis)

    for view in views:
        if view.get("kind") == "REGIME_LADDER":
            for row in view["rows"]:
                add_exposed_basis(row.get("basis"))
        else:
            add_exposed_basis(view.get("basis"))
    if boundary is not None:
        add_exposed_basis(boundary.get("basis"))
    if bases != exposed_bases:
        raise ContractValidationError(
            f"{path}.rule_basis must equal the ordered union of view, row, and boundary bases"
        )


def validate_metric_record(
    metric: Mapping[str, Any], *, metric_ids: set[str] | None = None
) -> None:
    """Validate a normalized metric record without changing its values.

    Missing data must remain ``None``. The validator deliberately rejects bool,
    NaN, and infinity as numeric metric values and never coerces null to zero.
    """

    metric = _require_mapping(metric, "metric")
    metric_id = _require_nonempty_string(metric.get("metric_id"), "metric.metric_id")
    if "interpretation" not in metric:
        raise ContractValidationError("metric.interpretation is required")
    interpretation = metric.get("interpretation")
    if metric_id in INTERPRETED_P0_METRIC_IDS:
        if interpretation is None:
            raise ContractValidationError(
                f"metric.interpretation must be non-null for {metric_id}"
            )
        _validate_metric_interpretation(
            interpretation, "metric.interpretation", metric_ids=metric_ids
        )
    elif interpretation is not None:
        raise ContractValidationError(
            f"metric.interpretation must be null for non-P0 metric {metric_id}"
        )
    _require_nonempty_string(metric.get("label"), "metric.label")
    availability = _require_enum(
        Availability, metric.get("availability"), "metric.availability"
    )
    _require_nonempty_string(metric.get("unit"), "metric.unit")
    _require_nonempty_string(metric.get("frequency"), "metric.frequency")

    value = metric.get("value")
    _validate_nullable_number(value, "metric.value")

    _validate_optional_date(metric.get("observation_date"), "metric.observation_date")
    _validate_optional_utc_datetime(metric.get("released_at"), "metric.released_at")
    _validate_optional_utc_datetime(metric.get("updated_at"), "metric.updated_at")
    _validate_optional_date(
        metric.get("expected_next_update"), "metric.expected_next_update"
    )

    changes = _require_mapping(metric.get("changes"), "metric.changes")
    for field in (
        "one_observation",
        "five_observations",
        "eight_weeks",
        "twelve_weeks",
    ):
        if field not in changes:
            raise ContractValidationError(f"metric.changes.{field} is required")
        _validate_nullable_number(changes[field], f"metric.changes.{field}")
    for field in (
        "twenty_observations",
        "one_week",
        "four_weeks",
        "one_month",
        "one_quarter",
    ):
        if field in changes:
            _validate_nullable_number(changes[field], f"metric.changes.{field}")

    statistics = _require_mapping(metric.get("statistics"), "metric.statistics")
    for field, statistic in statistics.items():
        _require_nonempty_string(field, "metric.statistics key")
        _validate_nullable_number(statistic, f"metric.statistics.{field}")

    quality = _require_mapping(metric.get("quality"), "metric.quality")
    health = _require_enum(Health, quality.get("status"), "metric.quality.status")
    _require_enum(
        Freshness, quality.get("freshness"), "metric.quality.freshness"
    )
    _validate_optional_utc_datetime(
        quality.get("last_success_at"), "metric.quality.last_success_at"
    )
    if "last_attempt_at" not in quality:
        raise ContractValidationError("metric.quality.last_attempt_at is required")
    _validate_optional_utc_datetime(
        quality.get("last_attempt_at"), "metric.quality.last_attempt_at"
    )
    _validate_optional_string(
        quality.get("failure_reason"), "metric.quality.failure_reason"
    )
    _validate_nullable_number(quality.get("sample_size"), "metric.quality.sample_size")
    sample_size = quality.get("sample_size")
    if sample_size is not None and (
        not isinstance(sample_size, int) or sample_size < 0
    ):
        raise ContractValidationError(
            "metric.quality.sample_size must be a non-negative integer or null"
        )

    if availability in (Availability.MANUAL_READY, Availability.UNAVAILABLE_FREE):
        if value is not None:
            raise ContractValidationError(
                f"{availability.value} metric.value must be null"
            )
        if health is not Health.NOT_APPLICABLE:
            raise ContractValidationError(
                f"{availability.value} metric health must be NOT_APPLICABLE"
            )
    elif health is Health.NOT_APPLICABLE:
        raise ContractValidationError(
            f"{availability.value} metric health cannot be NOT_APPLICABLE"
        )

    context = _require_mapping(metric.get("context"), "metric.context")
    is_proxy = context.get("is_proxy")
    if not isinstance(is_proxy, bool):
        raise ContractValidationError("metric.context.is_proxy must be boolean")
    if availability is Availability.ACTIVE_PROXY and not is_proxy:
        raise ContractValidationError("ACTIVE_PROXY metric must set is_proxy=true")
    confidence = context.get("confidence")
    if confidence not in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}:
        raise ContractValidationError(
            "metric.context.confidence must be HIGH, MEDIUM, LOW, or UNKNOWN"
        )
    _validate_string_list(
        context.get("technical_flags"), "metric.context.technical_flags"
    )

    methodology = _require_mapping(metric.get("methodology"), "metric.methodology")
    missing_methodology = METHODOLOGY_FIELDS - methodology.keys()
    if missing_methodology:
        raise ContractValidationError(
            "metric.methodology missing fields: "
            + ", ".join(sorted(missing_methodology))
        )
    for field in METHODOLOGY_FIELDS - {"confirm_with"}:
        if not isinstance(methodology[field], str):
            raise ContractValidationError(f"metric.methodology.{field} must be a string")
    _validate_string_list(
        methodology["confirm_with"], "metric.methodology.confirm_with"
    )
    if is_proxy and not methodology["proxy_disclosure"]:
        raise ContractValidationError(
            "proxy metric must include methodology.proxy_disclosure"
        )

    source = _require_mapping(metric.get("source"), "metric.source")
    for field in ("name", "url", "tier"):
        _validate_optional_string(source.get(field), f"metric.source.{field}")
    _validate_optional_utc_datetime(
        source.get("retrieved_at"), "metric.source.retrieved_at"
    )
    if not isinstance(source.get("rights_note"), str):
        raise ContractValidationError("metric.source.rights_note must be a string")
    if availability in (Availability.ACTIVE_FREE, Availability.ACTIVE_PROXY):
        for field in ("source_id", "name", "url", "tier", "rights_note"):
            _require_nonempty_string(source.get(field), f"metric.source.{field}")
        if source.get("retrieved_at") is None:
            if value is not None or health is not Health.ERROR:
                raise ContractValidationError(
                    "active metric.source.retrieved_at may be null only before "
                    "the first failed/unattempted collection"
                )
        else:
            _validate_required_utc_datetime(
                source.get("retrieved_at"), "metric.source.retrieved_at"
            )

    short_series = metric.get("short_series")
    if not isinstance(short_series, list):
        raise ContractValidationError("metric.short_series must be a list")
    for index, point in enumerate(short_series):
        _validate_point(point, f"metric.short_series[{index}]")
        if metric.get("metric_id") == "srf_accepted":
            _validate_srf_point(point, f"metric.short_series[{index}]")


def _validate_evidence_block(value: Any, path: str) -> None:
    block = _require_mapping(value, path)
    for field in ("id", "label", "status", "summary", "direction", "confidence"):
        _require_nonempty_string(block.get(field), f"{path}.{field}")
    if not isinstance(block.get("available"), bool):
        raise ContractValidationError(f"{path}.available must be boolean")
    if block.get("triggered") is not None and not isinstance(
        block.get("triggered"), bool
    ):
        raise ContractValidationError(f"{path}.triggered must be boolean or null")


def _validate_switch(value: Any, path: str) -> None:
    switch = _require_mapping(value, path)
    _require_nonempty_string(switch.get("mode"), f"{path}.mode")
    _validate_optional_string(switch.get("assessment"), f"{path}.assessment")
    for field in ("available_blocks", "total_blocks"):
        count = switch.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ContractValidationError(f"{path}.{field} must be a non-negative integer")
    if switch["available_blocks"] > switch["total_blocks"]:
        raise ContractValidationError(
            f"{path}.available_blocks cannot exceed total_blocks"
        )
    _require_nonempty_string(switch.get("confidence"), f"{path}.confidence")
    if not isinstance(switch.get("summary"), str):
        raise ContractValidationError(f"{path}.summary must be a string")
    evidence = switch.get("evidence_blocks")
    if not isinstance(evidence, list):
        raise ContractValidationError(f"{path}.evidence_blocks must be a list")
    for index, block in enumerate(evidence):
        _validate_evidence_block(block, f"{path}.evidence_blocks[{index}]")
    if switch["total_blocks"] != len(evidence):
        raise ContractValidationError(
            f"{path}.total_blocks must equal the evidence block count"
        )
    available = sum(bool(block["available"]) for block in evidence)
    if switch["available_blocks"] != available:
        raise ContractValidationError(
            f"{path}.available_blocks must equal the available evidence block count"
        )


def _validate_collector_source(value: Any, path: str) -> None:
    source = _require_mapping(value, path)
    _require_nonempty_string(source.get("name"), f"{path}.name")
    _validate_optional_string(source.get("url"), f"{path}.url")
    _validate_optional_string(source.get("tier"), f"{path}.tier")
    if not isinstance(source.get("rights_note"), str):
        raise ContractValidationError(f"{path}.rights_note must be a string")
    _require_enum(Health, source.get("status"), f"{path}.status")
    _require_enum(Freshness, source.get("freshness"), f"{path}.freshness")
    _validate_optional_date(source.get("observation_date"), f"{path}.observation_date")
    _validate_optional_utc_datetime(source.get("released_at"), f"{path}.released_at")
    _validate_optional_utc_datetime(source.get("updated_at"), f"{path}.updated_at")
    _validate_optional_utc_datetime(
        source.get("last_success_at"), f"{path}.last_success_at"
    )
    if "last_attempt_at" not in source:
        raise ContractValidationError(f"{path}.last_attempt_at is required")
    _validate_optional_utc_datetime(
        source.get("last_attempt_at"), f"{path}.last_attempt_at"
    )
    _validate_optional_date(
        source.get("expected_next_update"), f"{path}.expected_next_update"
    )
    _validate_optional_string(source.get("failure_reason"), f"{path}.failure_reason")


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    """Validate the schema 2.3.0 snapshot envelope and all metric records."""

    snapshot = _require_mapping(snapshot, "snapshot")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ContractValidationError(
            f"snapshot.schema_version must be {SCHEMA_VERSION}"
        )
    _validate_required_utc_datetime(snapshot.get("generated_at"), "snapshot.generated_at")
    _validate_required_utc_datetime(
        snapshot.get("pipeline_updated_at"), "snapshot.pipeline_updated_at"
    )
    _validate_optional_date(snapshot.get("market_date"), "snapshot.market_date")
    _validate_optional_string(
        snapshot.get("overall_assessment"), "snapshot.overall_assessment"
    )

    switches = _require_mapping(snapshot.get("switches"), "snapshot.switches")
    for switch_id in (
        "liquidity_fuel",
        "market_ignition",
        "fundamental_exit",
    ):
        _validate_switch(switches.get(switch_id), f"snapshot.switches.{switch_id}")
    liquidity_assessment = switches["liquidity_fuel"]["assessment"]
    if snapshot.get("overall_assessment") != liquidity_assessment:
        raise ContractValidationError(
            "snapshot.overall_assessment must equal "
            "snapshot.switches.liquidity_fuel.assessment"
        )

    metrics = _require_mapping(snapshot.get("metrics"), "snapshot.metrics")
    metric_ids = set(metrics)
    missing_interpreted = INTERPRETED_P0_METRIC_IDS - metric_ids
    if missing_interpreted:
        raise ContractValidationError(
            "snapshot is missing interpreted P0 metrics: "
            + ", ".join(sorted(missing_interpreted))
        )
    for metric_id, metric in metrics.items():
        _require_nonempty_string(metric_id, "snapshot.metrics key")
        validate_metric_record(metric, metric_ids=metric_ids)
        if metric.get("metric_id") != metric_id:
            raise ContractValidationError(
                f"snapshot metric key {metric_id!r} does not match metric_id"
            )
    market_switch = switches["market_ignition"]
    if market_switch.get("mode") != "EVIDENCE_ONLY":
        raise ContractValidationError("market_ignition.mode must be EVIDENCE_ONLY")
    if market_switch.get("mode") == "EVIDENCE_ONLY":
        if market_switch.get("assessment") is not None:
            raise ContractValidationError("market_ignition.assessment must be null")
        blocks = market_switch["evidence_blocks"]
        if tuple(block["id"] for block in blocks) != P1_BLOCK_IDS:
            raise ContractValidationError(
                "market_ignition evidence block IDs/order do not match P1 contract"
            )
        for block in blocks:
            if block["triggered"] is not None:
                raise ContractValidationError(
                    "market_ignition evidence triggered must remain null"
                )
            if block["direction"] not in P1_DIRECTIONS:
                raise ContractValidationError(
                    "market_ignition evidence direction is invalid"
                )
            if block["confidence"] not in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}:
                raise ContractValidationError(
                    "market_ignition evidence confidence is invalid"
                )
        for block in (blocks[0], blocks[2], blocks[3]):
            if (
                block["available"]
                or block["status"] != "UNAVAILABLE_FREE"
                or block["direction"] != "UNKNOWN"
                or block["confidence"] != "UNKNOWN"
            ):
                raise ContractValidationError(
                    "rights-held P1 evidence blocks must remain unavailable/unknown"
                )
        missing_held = P1_HELD_METRICS - metrics.keys()
        if missing_held:
            raise ContractValidationError(
                "snapshot is missing rights-held P1 metrics: "
                + ", ".join(sorted(missing_held))
            )
        for metric_id in P1_HELD_METRICS:
            metric = metrics[metric_id]
            if (
                metric["availability"] != "UNAVAILABLE_FREE"
                or metric["value"] is not None
                or metric["quality"]["status"] != "NOT_APPLICABLE"
                or metric["short_series"]
            ):
                raise ContractValidationError(
                    f"rights-held P1 metric {metric_id} must fail closed"
                )
        missing_cftc = P1_CFTC_METRICS.keys() - metrics.keys()
        if missing_cftc:
            raise ContractValidationError(
                "snapshot is missing canonical CFTC metrics: "
                + ", ".join(sorted(missing_cftc))
            )
        retired_cftc = {
            "cftc_asset_manager_positioning",
            "cftc_leveraged_funds_positioning_proxy",
            "cta_proxy",
        } & metrics.keys()
        if retired_cftc:
            raise ContractValidationError(
                "snapshot contains retired CFTC metric IDs: "
                + ", ".join(sorted(retired_cftc))
            )
        cftc_metrics = {
            metric_id: metrics[metric_id] for metric_id in P1_CFTC_METRICS
        }
        dates = {metric["observation_date"] for metric in cftc_metrics.values()}
        for metric_id, expected_availability in P1_CFTC_METRICS.items():
            metric = cftc_metrics[metric_id]
            if metric["availability"] != expected_availability:
                raise ContractValidationError(
                    f"{metric_id}.availability does not match P1 contract"
                )
            if metric["unit"] != "percent_open_interest":
                raise ContractValidationError(
                    f"{metric_id}.unit must be percent_open_interest"
                )
            if metric["frequency"] != "weekly":
                raise ContractValidationError(f"{metric_id}.frequency must be weekly")
            stats = metric["statistics"]
            for field in (
                "sample_size",
                "net_position",
                "open_interest",
                "net_percent_open_interest",
                "change_8_weeks",
                "change_12_weeks",
                "z_score_3_year",
                "z_score_3_year_sample_size",
            ):
                if field not in stats:
                    raise ContractValidationError(
                        f"{metric_id}.statistics.{field} is required"
                    )
            if stats["sample_size"] != metric["quality"]["sample_size"]:
                raise ContractValidationError(
                    f"{metric_id}.statistics.sample_size must match quality"
                )
            if metric["changes"]["eight_weeks"] != stats["change_8_weeks"]:
                raise ContractValidationError(
                    f"{metric_id} 8W changes/statistics must match"
                )
            if metric["changes"]["twelve_weeks"] != stats["change_12_weeks"]:
                raise ContractValidationError(
                    f"{metric_id} 12W changes/statistics must match"
                )
            expected_direction = _p1_direction(stats["change_8_weeks"])
            if metric["context"].get("direction") != expected_direction:
                raise ContractValidationError(
                    f"{metric_id}.context.direction must match 8W change"
                )
        expected_positioning_available = (
            len(dates) == 1
            and None not in dates
            and all(
                metric["quality"]["status"] == "OK"
                and metric["quality"]["freshness"] == "FRESH"
                and metric["value"] is not None
                and metric["statistics"]["change_8_weeks"] is not None
                and metric["statistics"]["change_12_weeks"] is not None
                and metric["statistics"]["z_score_3_year"] is not None
                and metric["statistics"]["z_score_3_year_sample_size"] == 156
                for metric in cftc_metrics.values()
            )
        )
        if blocks[1]["available"] != expected_positioning_available:
            raise ContractValidationError(
                "trend_positioning availability does not match CFTC evidence coverage"
            )
        component_directions = [
            _p1_direction(metric["statistics"]["change_8_weeks"])
            for metric in cftc_metrics.values()
        ]
        expected_block_direction = (
            component_directions[0]
            if expected_positioning_available
            and len(set(component_directions)) == 1
            else "MIXED"
            if expected_positioning_available
            else "UNKNOWN"
        )
        expected_confidence = "LOW" if expected_positioning_available else "UNKNOWN"
        if (
            blocks[1]["direction"] != expected_block_direction
            or blocks[1]["status"]
            != (expected_block_direction if expected_positioning_available else "UNAVAILABLE_FREE")
            or blocks[1]["confidence"] != expected_confidence
            or market_switch["confidence"] != expected_confidence
        ):
            raise ContractValidationError(
                "trend_positioning direction/status/confidence does not match CFTC metrics"
            )

        source_map = _require_mapping(snapshot.get("sources"), "snapshot.sources")
        if "cftc_tff_futures_only" not in source_map:
            raise ContractValidationError(
                "snapshot.sources.cftc_tff_futures_only is required"
            )
        cftc_source = _require_mapping(
            source_map["cftc_tff_futures_only"],
            "snapshot.sources.cftc_tff_futures_only",
        )
        if cftc_source.get("collector_id") != "cftc_tff_futures_only":
            raise ContractValidationError(
                "cftc source collector_id must be cftc_tff_futures_only"
            )
        health_rank = {"NOT_APPLICABLE": -1, "OK": 0, "NOT_RELEASED_YET": 1, "STALE": 2, "ERROR": 3}
        freshness_rank = {"FRESH": 0, "LATE": 1, "STALE": 2, "UNKNOWN": 3}
        expected_health = max(
            (metric["quality"]["status"] for metric in cftc_metrics.values()),
            key=health_rank.__getitem__,
        )
        expected_freshness = max(
            (metric["quality"]["freshness"] for metric in cftc_metrics.values()),
            key=freshness_rank.__getitem__,
        )
        expected_date = max(
            (metric["observation_date"] for metric in cftc_metrics.values() if metric["observation_date"]),
            default=None,
        )
        expected_release = max(
            (metric["released_at"] for metric in cftc_metrics.values() if metric["released_at"]),
            default=None,
        )
        expected_next = max(
            (metric["expected_next_update"] for metric in cftc_metrics.values() if metric["expected_next_update"]),
            default=None,
        )
        successes = [
            metric["quality"]["last_success_at"]
            for metric in cftc_metrics.values()
            if metric["quality"]["last_success_at"]
        ]
        attempts = [
            metric["quality"]["last_attempt_at"]
            for metric in cftc_metrics.values()
            if metric["quality"]["last_attempt_at"]
        ]
        updates = [
            metric["updated_at"] for metric in cftc_metrics.values() if metric["updated_at"]
        ]
        failures = list(
            dict.fromkeys(
                metric["quality"]["failure_reason"]
                for metric in cftc_metrics.values()
                if metric["quality"]["failure_reason"]
            )
        )
        expected_attempt = max(attempts, default=None)
        expected_updated = (
            expected_attempt
            if expected_attempt == snapshot.get("generated_at")
            else max(updates, default=None)
        )
        expected_source_fields = {
            "status": expected_health,
            "freshness": expected_freshness,
            "observation_date": expected_date,
            "released_at": expected_release,
            "expected_next_update": expected_next,
            "last_success_at": (
                min(successes)
                if successes and all(
                    metric["quality"]["status"] == "OK"
                    for metric in cftc_metrics.values()
                )
                else max(successes, default=None)
            ),
            "last_attempt_at": expected_attempt,
            "failure_reason": "; ".join(failures) if failures else None,
        }
        if any(
            cftc_source.get(field) != value
            for field, value in expected_source_fields.items()
        ) or cftc_source.get("updated_at") != expected_updated:
            raise ContractValidationError(
                "cftc source state/provenance must match its four canonical metrics"
            )

    missing_p2 = (P2_ACTIVE_METRICS.keys() | P2_HELD_METRICS) - metrics.keys()
    if missing_p2:
        raise ContractValidationError(
            "snapshot is missing canonical P2 metrics: "
            + ", ".join(sorted(missing_p2))
        )
    retired_p2 = P2_RETIRED_METRICS & metrics.keys()
    if retired_p2:
        raise ContractValidationError(
            "snapshot contains retired P2 metric IDs: "
            + ", ".join(sorted(retired_p2))
        )
    for metric_id in P2_HELD_METRICS:
        metric = metrics[metric_id]
        if (
            metric["availability"] != "UNAVAILABLE_FREE"
            or metric["value"] is not None
            or metric["quality"]["status"] != "NOT_APPLICABLE"
            or metric["short_series"]
        ):
            raise ContractValidationError(
                f"rights-held P2 metric {metric_id} must fail closed"
            )
        for field in (
            "observation_date",
            "released_at",
            "updated_at",
            "expected_next_update",
        ):
            if field not in metric or metric[field] is not None:
                raise ContractValidationError(
                    f"rights-held P2 metric {metric_id}.{field} must be null"
                )
        for field in ("last_success_at", "last_attempt_at"):
            if field not in metric["quality"] or metric["quality"][field] is not None:
                raise ContractValidationError(
                    f"rights-held P2 metric {metric_id}.quality.{field} must be null"
                )
        for field in ("source_id", "retrieved_at"):
            if field not in metric["source"] or metric["source"][field] is not None:
                raise ContractValidationError(
                    f"rights-held P2 metric {metric_id}.source.{field} must be null"
                )
    for metric_id, (availability, unit, frequency) in P2_ACTIVE_METRICS.items():
        metric = metrics[metric_id]
        if (
            metric["availability"] != availability
            or metric["unit"] != unit
            or metric["frequency"] != frequency
        ):
            raise ContractValidationError(
                f"{metric_id} availability/unit/frequency does not match P2 contract"
            )

    macro = metrics["nonfinancial_equities_gdp_proxy"]
    missing_macro_stats = P2_MACRO_STATISTICS - macro["statistics"].keys()
    if missing_macro_stats:
        raise ContractValidationError(
            "nonfinancial equities/GDP statistics missing: "
            + ", ".join(sorted(missing_macro_stats))
        )
    macro_context = macro["context"]
    for field in (
        "equity_observation_date",
        "gdp_observation_date",
        "common_quarter",
    ):
        _validate_optional_string(
            macro_context.get(field),
            f"nonfinancial_equities_gdp_proxy.context.{field}",
        )
    percentile = macro["statistics"]["percentile_10y"]
    if percentile is not None and not 0 <= percentile <= 100:
        raise ContractValidationError("P2 macro percentile_10y must be between 0 and 100")
    percentile_sample = macro["statistics"]["percentile_10y_sample_size"]
    if (
        isinstance(percentile_sample, bool)
        or not isinstance(percentile_sample, int)
        or not 0 <= percentile_sample <= 40
    ):
        raise ContractValidationError(
            "P2 macro percentile_10y_sample_size must be an integer from 0 to 40"
        )
    if macro["changes"].get("one_quarter") != macro["statistics"].get(
        "change_1_quarter_pp"
    ) and "change_1_quarter_pp" in macro["statistics"]:
        raise ContractValidationError(
            "P2 macro one-quarter change must match ratio percentage-point statistics"
        )

    form4 = metrics["sec_form4_nonderivative_ps_count_ratio_20d"]
    missing_form4_stats = P2_FORM4_STATISTICS - form4["statistics"].keys()
    if missing_form4_stats:
        raise ContractValidationError(
            "SEC Form 4 statistics missing: "
            + ", ".join(sorted(missing_form4_stats))
        )
    if form4["value"] != form4["statistics"]["count_ratio_20d"]:
        raise ContractValidationError(
            "SEC Form 4 metric value must match count_ratio_20d"
        )
    form4_context = form4["context"]
    for field in (
        "window_start_5d",
        "window_end_5d",
        "window_start_20d",
        "window_end_20d",
        "dollar_status_5d",
        "dollar_status_20d",
        "ex_10b5_scope",
    ):
        _validate_optional_string(
            form4_context.get(field),
            f"sec_form4_nonderivative_ps_count_ratio_20d.context.{field}",
        )
    if form4_context.get("ex_10b5_scope") not in {
        None,
        "EXPLICIT_FALSE_ONLY",
    }:
        raise ContractValidationError(
            "SEC Form 4 ex_10b5_scope must be EXPLICIT_FALSE_ONLY"
        )
    for window in ("5d", "20d"):
        coverage = form4["statistics"][f"dollar_coverage_rate_{window}"]
        dollar_ratio = form4["statistics"][f"dollar_ratio_{window}"]
        if coverage is not None and not 0 <= coverage <= 1:
            raise ContractValidationError(
                f"SEC Form 4 dollar coverage {window} must be between 0 and 1"
            )
        if coverage is not None and coverage < 0.8 and dollar_ratio is not None:
            raise ContractValidationError(
                f"SEC Form 4 dollar ratio {window} requires at least 80% coverage"
            )

    technical_context = snapshot.get("technical_context")
    if not isinstance(technical_context, list):
        raise ContractValidationError("snapshot.technical_context must be a list")
    for index, item in enumerate(technical_context):
        context = _require_mapping(item, f"snapshot.technical_context[{index}]")
        _validate_optional_date(
            context.get("date"), f"snapshot.technical_context[{index}].date"
        )
        if context.get("date") is None:
            raise ContractValidationError(
                f"snapshot.technical_context[{index}].date is required"
            )
        _validate_string_list(
            context.get("flags"), f"snapshot.technical_context[{index}].flags"
        )
        if not isinstance(context.get("note"), str):
            raise ContractValidationError(
                f"snapshot.technical_context[{index}].note must be a string"
            )

    alerts = snapshot.get("alerts")
    if not isinstance(alerts, list):
        raise ContractValidationError("snapshot.alerts must be a list")
    for index, alert in enumerate(alerts):
        alert = _require_mapping(alert, f"snapshot.alerts[{index}]")
        for field in ("level", "title", "detail"):
            if not isinstance(alert.get(field), str):
                raise ContractValidationError(
                    f"snapshot.alerts[{index}].{field} must be a string"
                )
    if liquidity_assessment == "NEUTRAL":
        if alerts:
            raise ContractValidationError(
                "snapshot.alerts must be empty when Liquidity Fuel is NEUTRAL"
            )
    elif (
        len(alerts) != 1
        or alerts[0].get("level") != liquidity_assessment
        or alerts[0].get("title") != "Liquidity Fuel P0 assessment"
        or alerts[0].get("detail")
        != "技術事件只降低 confidence；severity 由獨立 evidence blocks 決定。"
    ):
        raise ContractValidationError(
            "snapshot.alerts must contain only the Liquidity Fuel P0 assessment"
        )

    explanations = _require_mapping(
        snapshot.get("explanations"), "snapshot.explanations"
    )
    if not isinstance(explanations.get("headline"), str):
        raise ContractValidationError("snapshot.explanations.headline must be a string")
    bullets = explanations.get("bullets")
    if not isinstance(bullets, list):
        raise ContractValidationError("snapshot.explanations.bullets must be a list")
    for index, bullet in enumerate(bullets):
        bullet = _require_mapping(bullet, f"snapshot.explanations.bullets[{index}]")
        for field in (
            "metric_id",
            "observation",
            "meaning",
            "alternative",
            "confirmation",
            "judgment",
            "confidence",
        ):
            if not isinstance(bullet.get(field), str):
                raise ContractValidationError(
                    f"snapshot.explanations.bullets[{index}].{field} must be a string"
                )

    sources = _require_mapping(snapshot.get("sources"), "snapshot.sources")
    for source_id, source in sources.items():
        _require_nonempty_string(source_id, "snapshot.sources key")
        _validate_collector_source(source, f"snapshot.sources.{source_id}")
    _validate_p2_collector_sources(snapshot, metrics, sources)
    _validate_p3_snapshot(snapshot, metrics, sources)
    decision_models = _require_mapping(
        snapshot.get("decision_models"), "snapshot.decision_models"
    )
    _require_exact_fields(
        decision_models, {"p0_video_liquidity"}, "snapshot.decision_models"
    )
    _validate_video_p0_model(
        decision_models.get("p0_video_liquidity"),
        metrics=metrics,
        generated_at=snapshot["generated_at"],
    )

    source_health = _require_mapping(
        snapshot.get("source_health"), "snapshot.source_health"
    )
    source_health_fields = {
        Health.OK: "ok",
        Health.STALE: "stale",
        Health.ERROR: "error",
        Health.NOT_RELEASED_YET: "not_released_yet",
        Health.NOT_APPLICABLE: "not_applicable",
    }
    for health, field in source_health_fields.items():
        count = source_health.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ContractValidationError(
                f"snapshot.source_health.{field} must be a non-negative integer"
            )
        expected = sum(source["status"] == health.value for source in sources.values())
        if count != expected:
            raise ContractValidationError(
                f"snapshot.source_health.{field} must equal {expected}, got {count!r}"
            )

    count_fields = {
        Availability.ACTIVE_FREE: "active_free_count",
        Availability.ACTIVE_PROXY: "active_proxy_count",
        Availability.MANUAL_READY: "manual_ready_count",
        Availability.UNAVAILABLE_FREE: "unavailable_free_count",
    }
    for availability, field in count_fields.items():
        expected = sum(
            metric["availability"] == availability.value for metric in metrics.values()
        )
        count = snapshot.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ContractValidationError(
                f"snapshot.{field} must be a non-negative integer"
            )
        if count != expected:
            raise ContractValidationError(
                f"snapshot.{field} must equal {expected}, got {count!r}"
            )

    expected_stale = sum(
        metric["quality"]["status"] == Health.STALE.value
        for metric in metrics.values()
    )
    stale_count = snapshot.get("stale_count")
    if not isinstance(stale_count, int) or isinstance(stale_count, bool) or stale_count < 0:
        raise ContractValidationError(
            "snapshot.stale_count must be a non-negative integer"
        )
    if stale_count != expected_stale:
        raise ContractValidationError(
            f"snapshot.stale_count must equal {expected_stale}"
        )


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the route/catalog manifest published beside a v2 snapshot."""

    manifest = _require_mapping(manifest, "manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ContractValidationError(
            f"manifest.schema_version must be {SCHEMA_VERSION}"
        )
    _validate_required_utc_datetime(manifest.get("generated_at"), "manifest.generated_at")
    metrics = manifest.get("metrics")
    if not isinstance(metrics, list):
        raise ContractValidationError("manifest.metrics must be a list")
    seen: set[str] = set()
    for index, raw_metric in enumerate(metrics):
        path = f"manifest.metrics[{index}]"
        metric = _require_mapping(raw_metric, path)
        metric_id = _require_nonempty_string(metric.get("metric_id"), f"{path}.metric_id")
        if metric_id in seen:
            raise ContractValidationError(f"duplicate manifest metric_id: {metric_id}")
        seen.add(metric_id)
        for field in ("label", "unit", "frequency", "role"):
            _require_nonempty_string(metric.get(field), f"{path}.{field}")
        if metric.get("layer") not in {
            "liquidity_fuel",
            "market_ignition",
            "fundamental_exit",
        }:
            raise ContractValidationError(f"{path}.layer is invalid")
        if metric.get("phase") not in {"P0", "P1", "P2", "P3"}:
            raise ContractValidationError(f"{path}.phase is invalid")
        _require_enum(Availability, metric.get("availability"), f"{path}.availability")
        expected_path = f"data/series/{metric_id}.json"
        if metric.get("series_path") != expected_path:
            raise ContractValidationError(
                f"{path}.series_path must be {expected_path}"
            )


def validate_series_file(series: Mapping[str, Any]) -> None:
    """Validate a full-series v2 payload without accepting a v1 alias shape."""

    series = _require_mapping(series, "series")
    if series.get("schema_version") != SCHEMA_VERSION:
        raise ContractValidationError(
            f"series.schema_version must be {SCHEMA_VERSION}"
        )
    _require_nonempty_string(series.get("metric_id"), "series.metric_id")
    for field in ("label", "unit", "frequency"):
        _require_nonempty_string(series.get(field), f"series.{field}")
    _require_enum(Availability, series.get("availability"), "series.availability")

    quality = _require_mapping(series.get("quality"), "series.quality")
    _require_enum(Health, quality.get("status"), "series.quality.status")
    _require_enum(Freshness, quality.get("freshness"), "series.quality.freshness")
    _validate_optional_utc_datetime(
        quality.get("last_success_at"), "series.quality.last_success_at"
    )
    if "last_attempt_at" not in quality:
        raise ContractValidationError("series.quality.last_attempt_at is required")
    _validate_optional_utc_datetime(
        quality.get("last_attempt_at"), "series.quality.last_attempt_at"
    )
    _validate_optional_string(
        quality.get("failure_reason"), "series.quality.failure_reason"
    )
    sample_size = quality.get("sample_size")
    if sample_size is not None and (
        isinstance(sample_size, bool)
        or not isinstance(sample_size, int)
        or sample_size < 0
    ):
        raise ContractValidationError(
            "series.quality.sample_size must be a non-negative integer or null"
        )

    _validate_optional_date(series.get("observation_date"), "series.observation_date")
    _validate_optional_utc_datetime(series.get("released_at"), "series.released_at")
    _validate_optional_utc_datetime(series.get("updated_at"), "series.updated_at")
    _validate_optional_date(
        series.get("expected_next_update"), "series.expected_next_update"
    )
    source = _require_mapping(series.get("source"), "series.source")
    for field in ("source_id", "name", "url", "tier"):
        _validate_optional_string(source.get(field), f"series.source.{field}")
    if not isinstance(source.get("rights_note"), str):
        raise ContractValidationError("series.source.rights_note must be a string")
    _validate_optional_utc_datetime(
        source.get("retrieved_at"), "series.source.retrieved_at"
    )

    observations = series.get("observations")
    if not isinstance(observations, list):
        raise ContractValidationError("series.observations must be a list")
    previous: str | None = None
    for index, point in enumerate(observations):
        _validate_point(point, f"series.observations[{index}]")
        if series.get("metric_id") == "srf_accepted":
            _validate_srf_point(point, f"series.observations[{index}]")
        day = point["date"]
        if previous is not None and day <= previous:
            raise ContractValidationError(
                "series.observations must be strictly increasing and deduplicated"
            )
        previous = day


def validate_alerts_file(alerts_file: Mapping[str, Any]) -> None:
    """Validate the standalone alerts artifact and its v2 envelope."""

    alerts_file = _require_mapping(alerts_file, "alerts_file")
    if alerts_file.get("schema_version") != SCHEMA_VERSION:
        raise ContractValidationError(
            f"alerts_file.schema_version must be {SCHEMA_VERSION}"
        )
    _validate_required_utc_datetime(
        alerts_file.get("generated_at"), "alerts_file.generated_at"
    )
    alerts = alerts_file.get("alerts")
    if not isinstance(alerts, list):
        raise ContractValidationError("alerts_file.alerts must be a list")
    for index, alert in enumerate(alerts):
        alert = _require_mapping(alert, f"alerts_file.alerts[{index}]")
        for field in ("level", "title", "detail"):
            if not isinstance(alert.get(field), str):
                raise ContractValidationError(
                    f"alerts_file.alerts[{index}].{field} must be a string"
                )


def validate_events_file(events_file: Mapping[str, Any]) -> None:
    """Validate the standalone technical-events artifact and envelope."""

    events_file = _require_mapping(events_file, "events_file")
    if events_file.get("schema_version") != SCHEMA_VERSION:
        raise ContractValidationError(
            f"events_file.schema_version must be {SCHEMA_VERSION}"
        )
    _validate_required_utc_datetime(
        events_file.get("generated_at"), "events_file.generated_at"
    )
    events = events_file.get("events")
    if not isinstance(events, list):
        raise ContractValidationError("events_file.events must be a list")
    previous: str | None = None
    for index, event in enumerate(events):
        path = f"events_file.events[{index}]"
        event = _require_mapping(event, path)
        _validate_optional_date(event.get("date"), f"{path}.date")
        if event.get("date") is None:
            raise ContractValidationError(f"{path}.date is required")
        if previous is not None and event["date"] <= previous:
            raise ContractValidationError(
                "events_file.events must be strictly increasing and deduplicated"
            )
        previous = event["date"]
        _validate_string_list(event.get("flags"), f"{path}.flags")
        if not isinstance(event.get("note"), str):
            raise ContractValidationError(f"{path}.note must be a string")


def validate_publication(
    snapshot: Mapping[str, Any],
    manifest: Mapping[str, Any],
    series_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    """Cross-check the complete staged v2 publication before promotion."""

    validate_snapshot(snapshot)
    validate_manifest(manifest)
    if manifest.get("generated_at") != snapshot.get("generated_at"):
        raise ContractValidationError(
            "manifest.generated_at must match snapshot.generated_at"
        )
    snapshot_ids = set(snapshot["metrics"])
    manifest_ids = {metric["metric_id"] for metric in manifest["metrics"]}
    series_ids = set(series_by_id)
    if snapshot_ids != manifest_ids or snapshot_ids != series_ids:
        raise ContractValidationError(
            "snapshot, manifest, and series metric IDs must match exactly"
        )
    manifest_by_id = {
        metric["metric_id"]: metric for metric in manifest["metrics"]
    }
    for metric_id, series in series_by_id.items():
        validate_series_file(series)
        if series.get("metric_id") != metric_id:
            raise ContractValidationError(
                f"series key {metric_id!r} does not match metric_id"
            )
        snapshot_metric = snapshot["metrics"][metric_id]
        manifest_metric = manifest_by_id[metric_id]
        for field in ("label", "unit", "frequency", "availability"):
            values = (
                snapshot_metric.get(field),
                manifest_metric.get(field),
                series.get(field),
            )
            if values[0] != values[1] or values[0] != values[2]:
                raise ContractValidationError(
                    f"{metric_id}.{field} must match across snapshot, manifest, and series"
                )
        for field in (
            "observation_date",
            "released_at",
            "updated_at",
            "expected_next_update",
        ):
            if snapshot_metric.get(field) != series.get(field):
                raise ContractValidationError(
                    f"{metric_id}.{field} must match across snapshot and series"
                )
        if snapshot_metric.get("quality") != series.get("quality"):
            raise ContractValidationError(
                f"{metric_id}.quality must match across snapshot and series"
            )
        if snapshot_metric.get("source") != series.get("source"):
            raise ContractValidationError(
                f"{metric_id}.source must match across snapshot and series"
            )
        if metric_id in P1_CFTC_IDENTITIES:
            contract_code, contract_name, category = P1_CFTC_IDENTITIES[metric_id]
            for index, point in enumerate(series["observations"]):
                path = f"{metric_id}.observations[{index}]"
                expected_identity = {
                    "contract_code": contract_code,
                    "contract_name": contract_name,
                    "trader_category": category,
                    "report_type": "TFF_FUTURES_ONLY",
                }
                if any(point.get(field) != expected for field, expected in expected_identity.items()):
                    raise ContractValidationError(
                        f"{path} CFTC identity metadata does not match metric"
                    )
                if point.get("market_and_exchange_name") != P1_CFTC_EXCHANGES[contract_code]:
                    raise ContractValidationError(
                        f"{path}.market_and_exchange_name does not match contract"
                    )
                for field in (
                    "cftc_market_code",
                    "cftc_commodity_code",
                    "commodity_name",
                    "contract_units",
                ):
                    _require_nonempty_string(point.get(field), f"{path}.{field}")
                for field in ("row_id", "source_report_id"):
                    _require_nonempty_string(point.get(field), f"{path}.{field}")
                _validate_optional_utc_datetime(
                    point.get("released_at"), f"{path}.released_at"
                )
                numeric_fields = (
                    "open_interest",
                    "long_position",
                    "short_position",
                    "net_position",
                    f"{category}_spread",
                )
                for field in numeric_fields:
                    value = point.get(field)
                    if isinstance(value, bool) or not isinstance(value, int):
                        raise ContractValidationError(f"{path}.{field} must be an integer")
                if (
                    point["open_interest"] <= 0
                    or min(
                        point["long_position"],
                        point["short_position"],
                        point[f"{category}_spread"],
                    ) < 0
                ):
                    raise ContractValidationError(f"{path} CFTC position domain is invalid")
                if point["net_position"] != point["long_position"] - point["short_position"]:
                    raise ContractValidationError(f"{path}.net_position does not reconcile")
                for position, field in (
                    (point["long_position"], f"{category}_pct_long"),
                    (point["short_position"], f"{category}_pct_short"),
                ):
                    percent = point.get(field)
                    if (
                        isinstance(percent, bool)
                        or not isinstance(percent, (int, float))
                        or not math.isfinite(float(percent))
                        or not 0 <= percent <= 100
                        or abs(percent - (100 * position / point["open_interest"])) > 0.11
                    ):
                        raise ContractValidationError(
                            f"{path}.{field} does not reconcile"
                        )
                expected_raw = 100 * point["net_position"] / point["open_interest"]
                raw = point.get("net_percent_open_interest_raw")
                if (
                    isinstance(raw, bool)
                    or not isinstance(raw, (int, float))
                    or not math.isfinite(raw)
                    or abs(raw - expected_raw) > 1e-12
                ):
                    raise ContractValidationError(f"{path} raw net percent does not reconcile")
                value = point.get("value")
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or abs(value - round(expected_raw, 6)) > 1e-12
                ):
                    raise ContractValidationError(f"{path}.value does not reconcile")
            latest_point_release = (
                series["observations"][-1].get("released_at")
                if series["observations"]
                else None
            )
            if series.get("released_at") != latest_point_release:
                raise ContractValidationError(
                    f"{metric_id}.released_at must match latest CFTC point"
                )
            expected_statistics = _cftc_statistics_from_points(
                list(series["observations"])
            )
            actual_statistics = snapshot_metric.get("statistics", {})
            for field, expected in expected_statistics.items():
                if not _same_nullable_number(actual_statistics.get(field), expected):
                    raise ContractValidationError(
                        f"{metric_id}.statistics.{field} must match full series"
                    )
            if snapshot_metric["quality"].get("sample_size") != len(
                series["observations"]
            ):
                raise ContractValidationError(
                    f"{metric_id}.quality.sample_size must match full series"
                )
        if metric_id == "nonfinancial_equities_gdp_proxy":
            _validate_p2_macro_artifacts(snapshot_metric, series)
        normalized_observations = []
        for point in series["observations"]:
            normalized = {"date": point["date"], "value": point["value"]}
            if metric_id == "srf_accepted":
                normalized.update(
                    {
                        field: point[field]
                        for field in (
                            "accepted_amount_usd_bn",
                            "alert_eligible_accepted_amount_usd_bn",
                            "exercise_accepted_amount_usd_bn",
                            "has_technical_exercise",
                            "technical_exercise",
                            "classification_complete",
                        )
                    }
                )
            normalized_observations.append(normalized)
        expected_short_series = normalized_observations[-22:]
        if snapshot_metric.get("short_series") != expected_short_series:
            raise ContractValidationError(
                f"{metric_id}.short_series must match the full-series suffix"
            )
        # The current observation can legitimately be null (for example when
        # one exact-quarter macro component is missing).  Never skip backwards
        # to a prior non-null value and present it as the current endpoint.
        expected_value = (
            normalized_observations[-1]["value"] if normalized_observations else None
        )
        expected_date = normalized_observations[-1]["date"] if normalized_observations else None
        if snapshot_metric.get("value") != expected_value:
            raise ContractValidationError(
                f"{metric_id}.value must match the full-series endpoint"
            )
        if snapshot_metric.get("observation_date") != expected_date:
            raise ContractValidationError(
                f"{metric_id}.observation_date must match the full-series endpoint"
            )
    # Interpretation is a deterministic derived view, not editable narrative.
    # Rebuild it from the canonical full series and audited config, then compare
    # exact JSON values so tampered state/headline/boundaries cannot pass.
    from pipeline.config import load_config_bundle
    from pipeline.interpretation import build_metric_interpretations

    bundle = load_config_bundle()
    expected_interpretations = build_metric_interpretations(
        metric_records=snapshot["metrics"],
        series_by_id={
            metric_id: series["observations"]
            for metric_id, series in series_by_id.items()
        },
        rules=bundle.interpretation_rules,
        alert_rules=bundle.alert_rules,
    )
    for metric_id, expected in expected_interpretations.items():
        if snapshot["metrics"][metric_id].get("interpretation") != expected:
            raise ContractValidationError(
                f"{metric_id}.interpretation does not reconcile with config and full series"
            )
    _validate_p3_publication(snapshot, manifest_by_id, series_by_id)
