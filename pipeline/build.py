"""Schema 2.3.0 assembly helpers for the static dashboard publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import floor, isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pipeline.config import ConfigBundle
from pipeline.contracts import SCHEMA_VERSION
from pipeline.io import read_json


NEW_YORK = ZoneInfo("America/New_York")
LEGACY_SERIES_IDS: dict[str, str] = {
    "sofr_iorb_spread_bp": "sofr_iorb_spread",
    "on_rrp_accepted": "on_rrp",
    "srf_accepted": "srf_usage",
    "vix_vix3m_term_structure_proxy": "vix_curve",
    "cross_asset_correlation": "cross_asset_corr",
}

FRESHNESS_ORDER = {"FRESH": 0, "LATE": 1, "STALE": 2, "UNKNOWN": 3}
HEALTH_ORDER = {
    "OK": 0,
    "NOT_RELEASED_YET": 1,
    "STALE": 2,
    "ERROR": 3,
    "NOT_APPLICABLE": -1,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def valid_points(value: Any) -> list[dict[str, Any]]:
    """Keep date/value observations, preserving validated source metadata."""

    if not isinstance(value, list):
        return []
    by_date: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            continue
        day, raw = item.get("date"), item.get("value")
        if not isinstance(day, str):
            continue
        try:
            if date.fromisoformat(day).isoformat() != day:
                continue
        except ValueError:
            continue
        if raw is None:
            point: dict[str, Any] = {"date": day, "value": None}
        elif isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(raw):
            continue
        else:
            point = {"date": day, "value": float(raw)}
        for key, extra in item.items():
            if key not in {"date", "value"}:
                point[key] = extra
        by_date[day] = point
    return [by_date[day] for day in sorted(by_date)]


def load_last_good(
    data_dir: str | Path,
    metric_id: str,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Read a canonical or one-time legacy series without changing its observations."""

    root = Path(data_dir)
    candidates = [metric_id]
    legacy = LEGACY_SERIES_IDS.get(metric_id)
    if legacy:
        candidates.append(legacy)
    snapshot = read_json(root / "snapshot.json", {}) or {}
    snapshot_stamp = snapshot.get("pipeline_updated_at") or snapshot.get("generated_at")
    for candidate in candidates:
        payload = read_json(root / "series" / f"{candidate}.json", {}) or {}
        observations = valid_points(payload.get("observations"))
        if observations:
            quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
            stamp = (
                quality.get("last_success_at")
                or payload.get("updated_at")
                or payload.get("retrieved_at")
                or snapshot_stamp
            )
            released_at = payload.get("released_at")
            return observations, stamp if isinstance(stamp, str) else None, released_at if isinstance(released_at, str) else None
    return [], None, None


@dataclass
class SeriesState:
    metric_id: str
    observations: list[dict[str, Any]]
    health: str
    freshness: str
    last_success_at: str | None
    last_attempt_at: str | None
    failure_reason: str | None = None
    released_at: str | None = None
    updated_at: str | None = None

    @property
    def observation_date(self) -> str | None:
        return self.observations[-1]["date"] if self.observations else None


def freshness_for(
    observation_date: str | None,
    frequency: str,
    *,
    now_et: datetime,
) -> tuple[str, str]:
    if observation_date is None:
        return "UNKNOWN", "ERROR"
    lag = (now_et.date() - date.fromisoformat(observation_date)).days
    if lag < 0:
        return "UNKNOWN", "ERROR"
    if frequency == "weekly":
        if lag <= 10:
            return "FRESH", "OK"
        if lag <= 17:
            return "LATE", "OK"
        return "STALE", "STALE"
    if frequency == "policy_event":
        return ("FRESH", "OK") if lag <= 45 else ("LATE", "OK")
    if frequency in {"business_daily", "daily"}:
        if lag <= 3:
            return "FRESH", "OK"
        if lag <= 7:
            return "LATE", "OK"
        return "STALE", "STALE"
    return "UNKNOWN", "OK"


def h41_freshness_for(
    observation_date: str | None,
    *,
    now_et: datetime,
) -> tuple[str, str]:
    """Return H.4.1 freshness using its Wednesday-level/Thursday-release cycle.

    Before the current expected Wednesday level appears, retain the last value
    as ``NOT_RELEASED_YET`` rather than treating an unchanged FRED response as
    a fresh success. Data older than the normal weekly tolerance remains
    ``STALE`` so a missed release cannot stay in the softer state forever.
    """

    freshness, health = freshness_for(
        observation_date, "weekly", now_et=now_et
    )
    if observation_date is None or health == "STALE":
        return freshness, health

    today = now_et.date()
    days_since_wednesday = (today.weekday() - 2) % 7
    expected_observation = today - timedelta(days=days_since_wednesday)
    if today.weekday() == 2:
        # Wednesday levels are not normally published until Thursday.
        expected_observation -= timedelta(days=7)

    if date.fromisoformat(observation_date) < expected_observation:
        return "LATE", "NOT_RELEASED_YET"
    return freshness, health


def successful_state(
    metric_id: str,
    observations: Sequence[Mapping[str, Any]],
    *,
    frequency: str,
    attempted_at: str,
    now_et: datetime,
) -> SeriesState:
    points = valid_points(list(observations))
    if not points:
        raise ValueError(f"{metric_id} collector returned no usable observations")
    freshness, health = freshness_for(points[-1]["date"], frequency, now_et=now_et)
    released_values = [point.get("released_at") for point in points if isinstance(point.get("released_at"), str)]
    return SeriesState(
        metric_id=metric_id,
        observations=points,
        health=health,
        freshness=freshness,
        last_success_at=attempted_at,
        last_attempt_at=attempted_at,
        released_at=max(released_values, default=None),
        updated_at=attempted_at,
    )


def failed_state(
    metric_id: str,
    *,
    data_dir: str | Path,
    attempted_at: str,
    reason: str,
) -> SeriesState:
    observations, last_success, released_at = load_last_good(data_dir, metric_id)
    return SeriesState(
        metric_id=metric_id,
        observations=observations,
        health="STALE" if observations else "ERROR",
        freshness="STALE" if observations else "UNKNOWN",
        last_success_at=last_success,
        last_attempt_at=attempted_at,
        failure_reason=reason,
        released_at=released_at,
        updated_at=last_success,
    )


def weakest_health(states: Sequence[SeriesState]) -> str:
    applicable = [state.health for state in states if state.health != "NOT_APPLICABLE"]
    return max(applicable, key=HEALTH_ORDER.__getitem__) if applicable else "NOT_APPLICABLE"


def weakest_freshness(states: Sequence[SeriesState]) -> str:
    return max((state.freshness for state in states), key=FRESHNESS_ORDER.__getitem__)


def derived_state(
    metric_id: str,
    observations: Sequence[Mapping[str, Any]],
    inputs: Sequence[SeriesState],
    *,
    attempted_at: str,
) -> SeriesState:
    points = valid_points(list(observations))
    health = weakest_health(inputs)
    if not points and health not in {"ERROR", "STALE"}:
        health = "ERROR"
    successes = [state.last_success_at for state in inputs if state.last_success_at]
    releases = [state.released_at for state in inputs if state.released_at]
    failures = [state.failure_reason for state in inputs if state.failure_reason]
    return SeriesState(
        metric_id=metric_id,
        observations=points,
        health=health,
        freshness=weakest_freshness(inputs),
        last_success_at=min(successes) if successes and health == "OK" else max(successes, default=None),
        last_attempt_at=attempted_at,
        failure_reason="; ".join(failures) if failures else None,
        released_at=max(releases, default=None),
        updated_at=attempted_at if health == "OK" else max(successes, default=None),
    )


def changes_for(points: Sequence[Mapping[str, Any]], frequency: str) -> dict[str, float | None]:
    values = [point["value"] for point in valid_points(list(points)) if point["value"] is not None]
    one = round(values[-1] - values[-2], 6) if len(values) >= 2 else None
    five = round(values[-1] - values[-6], 6) if len(values) >= 6 else None
    twenty = round(values[-1] - values[-21], 6) if len(values) >= 21 else None
    output: dict[str, float | None] = {
        "one_observation": one,
        "five_observations": five,
        "twenty_observations": twenty,
        "eight_weeks": None,
        "twelve_weeks": None,
    }
    if frequency == "weekly":
        output["one_week"] = one
        output["four_weeks"] = round(values[-1] - values[-5], 6) if len(values) >= 5 else None
        output["eight_weeks"] = round(values[-1] - values[-9], 6) if len(values) >= 9 else None
        output["twelve_weeks"] = round(values[-1] - values[-13], 6) if len(values) >= 13 else None
    if frequency == "monthly":
        output["one_month"] = one
    if frequency == "quarterly":
        output["one_quarter"] = one
    return output


def percentile_rank(values: Sequence[float], value: float) -> float | None:
    usable = sorted(number for number in values if isfinite(number))
    if not usable:
        return None
    below = sum(number < value for number in usable)
    equal = sum(number == value for number in usable)
    return round((below + 0.5 * equal) / len(usable), 6)


def linear_slope(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    return round(
        sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator,
        6,
    )


def generic_statistics(points: Sequence[Mapping[str, Any]]) -> dict[str, float | int | None]:
    values = [point["value"] for point in valid_points(list(points)) if point["value"] is not None]
    return {
        "sample_size": len(values),
        "twenty_observation_percentile": percentile_rank(values[-20:], values[-1]) if values else None,
        "twenty_observation_slope": linear_slope(values[-20:]),
    }


def next_business_day(day: str | None) -> str | None:
    if day is None:
        return None
    candidate = date.fromisoformat(day) + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def expected_next_update(day: str | None, frequency: str) -> str | None:
    if day is None:
        return None
    parsed = date.fromisoformat(day)
    if frequency == "weekly":
        # H.4.1 observations are normally Wednesday levels released Thursday.
        return (parsed + timedelta(days=(3 - parsed.weekday()) % 7 or 7)).isoformat()
    if frequency in {"business_daily", "daily"}:
        return next_business_day(day)
    return None


def source_details(bundle: ConfigBundle, source_id: str | None) -> dict[str, Any]:
    if source_id is None:
        return {
            "source_id": None,
            "name": None,
            "url": None,
            "tier": None,
            "retrieved_at": None,
            "rights_note": "No production source is active for this metric.",
        }
    source = bundle.sources_by_id[source_id]
    rights = source["rights"]
    return {
        "source_id": source_id,
        "name": source["name"],
        "url": source.get("homepage"),
        "tier": source.get("tier"),
        "retrieved_at": None,
        "rights_note": rights.get("attribution_note") or rights.get("hold_reason") or "",
    }


def metric_record(
    bundle: ConfigBundle,
    registry_metric: Mapping[str, Any],
    *,
    state: SeriesState | None,
    attempted_at: str,
    statistics: Mapping[str, int | float | None] | None = None,
    technical_flags: Sequence[str] = (),
    effective_availability: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    implemented = registry_metric.get("implemented") is True
    availability = effective_availability or (
        registry_metric["availability"] if implemented else "UNAVAILABLE_FREE"
    )
    active = availability in {"ACTIVE_FREE", "ACTIVE_PROXY"}
    points = state.observations if state and active else []
    value = points[-1]["value"] if points else None
    source_id = registry_metric["source_ids"][0] if active else None
    source = source_details(bundle, source_id)
    if state and state.last_attempt_at:
        source["retrieved_at"] = state.last_attempt_at
    if state and active:
        health = state.health
        freshness = state.freshness
        failure_reason = state.failure_reason
        last_success = state.last_success_at
        last_attempt = state.last_attempt_at
        released_at = state.released_at
        updated_at = state.updated_at or attempted_at
    else:
        health, freshness = "NOT_APPLICABLE", "UNKNOWN"
        failure_reason = (
            registry_metric.get("reason")
            or (f"{registry_metric['phase']} production implementation is not released yet." if not implemented else None)
        )
        last_success = last_attempt = released_at = updated_at = None
    methodology = dict(registry_metric["methodology"])
    short_series = []
    for point in points[-22:]:
        short_point = {"date": point["date"], "value": point["value"]}
        if registry_metric["metric_id"] == "srf_accepted":
            for field in (
                "accepted_amount_usd_bn",
                "alert_eligible_accepted_amount_usd_bn",
                "exercise_accepted_amount_usd_bn",
                "has_technical_exercise",
                "technical_exercise",
                "classification_complete",
            ):
                if field in point:
                    short_point[field] = point[field]
        short_series.append(short_point)

    record: dict[str, Any] = {
        "metric_id": registry_metric["metric_id"],
        "label": registry_metric["label"],
        "availability": availability,
        "value": value,
        "unit": registry_metric["unit"],
        "frequency": registry_metric["frequency"],
        "observation_date": state.observation_date if state and active else None,
        "released_at": released_at,
        "updated_at": updated_at,
        "expected_next_update": expected_next_update(
            state.observation_date if state and active else None,
            registry_metric["frequency"],
        ),
        "changes": changes_for(points, registry_metric["frequency"]),
        "statistics": dict(statistics or (generic_statistics(points) if points else {})),
        "quality": {
            "status": health,
            "freshness": freshness,
            "last_success_at": last_success,
            "last_attempt_at": last_attempt,
            "failure_reason": failure_reason,
            "sample_size": len([point for point in points if point.get("value") is not None]) if active else None,
        },
        "context": {
            "technical_flags": sorted(set(technical_flags)),
            "is_proxy": bool(registry_metric.get("is_proxy")),
            "confidence": "HIGH" if active and health == "OK" else "MEDIUM" if active and value is not None else "UNKNOWN",
        },
        "source": source,
        "methodology": methodology,
        "short_series": short_series,
    }
    if extra:
        record.update(extra)
    return record


def series_record(metric: Mapping[str, Any], state: SeriesState | None) -> dict[str, Any]:
    observations = state.observations if state and metric["availability"] in {"ACTIVE_FREE", "ACTIVE_PROXY"} else []
    return {
        "schema_version": SCHEMA_VERSION,
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
        "observations": observations,
    }


def manifest_record(metrics: Sequence[Mapping[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "metrics": [
            {
                "metric_id": metric["metric_id"],
                "label": metric["label"],
                "unit": metric["unit"],
                "frequency": metric["frequency"],
                "layer": str(metric["layer"]).lower(),
                "phase": metric["phase"],
                "role": metric.get("role", "evidence"),
                "availability": metric["effective_availability"],
                "series_path": f"data/series/{metric['metric_id']}.json",
            }
            for metric in metrics
        ],
    }


def collector_source_record(
    bundle: ConfigBundle,
    collector_id: str,
    source_id: str,
    states: Sequence[SeriesState],
    *,
    attempted_at: str,
) -> dict[str, Any]:
    source = source_details(bundle, source_id)
    observation_dates = [state.observation_date for state in states if state.observation_date]
    releases = [state.released_at for state in states if state.released_at]
    successes = [state.last_success_at for state in states if state.last_success_at]
    failures = [state.failure_reason for state in states if state.failure_reason]
    return {
        "collector_id": collector_id,
        "name": source["name"],
        "url": source["url"],
        "tier": source["tier"],
        "rights_note": source["rights_note"],
        "status": weakest_health(states),
        "freshness": weakest_freshness(states),
        "observation_date": max(observation_dates, default=None),
        "released_at": max(releases, default=None),
        "updated_at": attempted_at,
        "last_success_at": min(successes) if successes and all(state.health == "OK" for state in states) else max(successes, default=None),
        "last_attempt_at": attempted_at,
        "expected_next_update": max(
            (
                expected
                for state in states
                if state.metric_id in bundle.metrics_by_id
                if (
                    expected := expected_next_update(
                        state.observation_date,
                        bundle.metrics_by_id[state.metric_id]["frequency"],
                    )
                )
                is not None
            ),
            default=None,
        ),
        "failure_reason": "; ".join(dict.fromkeys(failures)) if failures else None,
    }


def availability_counts(metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return {
        "active_free_count": sum(metric["availability"] == "ACTIVE_FREE" for metric in metrics.values()),
        "active_proxy_count": sum(metric["availability"] == "ACTIVE_PROXY" for metric in metrics.values()),
        "manual_ready_count": sum(metric["availability"] == "MANUAL_READY" for metric in metrics.values()),
        "unavailable_free_count": sum(metric["availability"] == "UNAVAILABLE_FREE" for metric in metrics.values()),
        "stale_count": sum(metric["quality"]["status"] == "STALE" for metric in metrics.values()),
    }


def source_health_counts(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return {
        "ok": sum(source["status"] == "OK" for source in sources.values()),
        "stale": sum(source["status"] == "STALE" for source in sources.values()),
        "error": sum(source["status"] == "ERROR" for source in sources.values()),
        "not_released_yet": sum(source["status"] == "NOT_RELEASED_YET" for source in sources.values()),
        "not_applicable": sum(source["status"] == "NOT_APPLICABLE" for source in sources.values()),
    }
