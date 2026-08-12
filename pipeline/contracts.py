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
    for field in ("one_observation", "five_observations"):
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
    for field in ("id", "label", "status", "summary"):
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
        for field in ("observation_date", "released_at", "updated_at"):
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
