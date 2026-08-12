"""Schema 2.0.0 enums and validation helpers for the data-pipeline contract.

This module is intentionally independent of collectors and snapshot builders so
future releases can adopt the contract incrementally without mutating v1 data.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
import math
import re
from typing import Any, Mapping


SCHEMA_VERSION = "2.0.0"
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
    """Raised when a schema 2.0.0 record violates the canonical contract."""


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


def validate_metric_record(metric: Mapping[str, Any]) -> None:
    """Validate a normalized metric record without changing its values.

    Missing data must remain ``None``. The validator deliberately rejects bool,
    NaN, and infinity as numeric metric values and never coerces null to zero.
    """

    metric = _require_mapping(metric, "metric")
    _require_nonempty_string(metric.get("metric_id"), "metric.metric_id")
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
    """Validate the schema 2.0.0 snapshot envelope and all metric records."""

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
    for metric_id, metric in metrics.items():
        _require_nonempty_string(metric_id, "snapshot.metrics key")
        validate_metric_record(metric)
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
        normalized_observations = [
            {"date": point["date"], "value": point["value"]}
            for point in series["observations"]
        ]
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
