"""Schema 2.0.0 enums and validation helpers for the data-pipeline contract.

This module is intentionally independent of collectors and snapshot builders so
future releases can adopt the contract incrementally without mutating v1 data.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
import math
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
        normalized_observations = [
            {"date": point["date"], "value": point["value"]}
            for point in series["observations"]
        ]
        expected_short_series = normalized_observations[-22:]
        if snapshot_metric.get("short_series") != expected_short_series:
            raise ContractValidationError(
                f"{metric_id}.short_series must match the full-series suffix"
            )
        latest_non_null = next(
            (
                point
                for point in reversed(normalized_observations)
                if point["value"] is not None
            ),
            None,
        )
        expected_value = latest_non_null["value"] if latest_non_null else None
        expected_date = normalized_observations[-1]["date"] if normalized_observations else None
        if snapshot_metric.get("value") != expected_value:
            raise ContractValidationError(
                f"{metric_id}.value must match the latest non-null full-series value"
            )
        if snapshot_metric.get("observation_date") != expected_date:
            raise ContractValidationError(
                f"{metric_id}.observation_date must match the full-series endpoint"
            )
