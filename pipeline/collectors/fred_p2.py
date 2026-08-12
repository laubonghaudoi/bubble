"""Strict FRED collector for the government-origin P2 macro proxy.

This module deliberately returns source observations and metadata without
scaling or combining them.  Unit conversion, quarter alignment and proxy math
belong to :mod:`pipeline.transforms.p2_macro`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlencode

from .common import DEFAULT_USER_AGENT, CollectorError, get_json, number

OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES_URL = "https://api.stlouisfed.org/fred/series"

SERIES_SPECS: dict[str, dict[str, str]] = {
    "NCBEILQ027S": {
        "frequency": "Quarterly",
        "frequency_short": "Q",
        "units": "Millions of U.S. Dollars",
        "units_short": "Mil. of U.S. $",
        "seasonal_adjustment": "Not Seasonally Adjusted",
        "seasonal_adjustment_short": "NSA",
    },
    "GDP": {
        "frequency": "Quarterly",
        "frequency_short": "Q",
        "units": "Billions of Dollars",
        "units_short": "Bil. of $",
        "seasonal_adjustment": "Seasonally Adjusted Annual Rate",
        "seasonal_adjustment_short": "SAAR",
    },
}


def _iso_date(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise CollectorError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CollectorError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise CollectorError(f"{field} must be an ISO date")
    return value


def _utc_timestamp(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise CollectorError(f"{field} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollectorError(f"{field} must be a timezone-aware timestamp") from exc
    if parsed.tzinfo is None:
        raise CollectorError(f"{field} must be a timezone-aware timestamp")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _nonempty_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectorError(f"{field} must be a non-empty string")
    return value


def _series_spec(series_id: str) -> dict[str, str]:
    try:
        return SERIES_SPECS[series_id]
    except KeyError as exc:
        raise CollectorError(
            f"FRED series {series_id!r} is not allowlisted for the P2 macro proxy"
        ) from exc


def parse_series_metadata(
    payload: Mapping[str, Any], *, series_id: str
) -> dict[str, Any]:
    """Validate the FRED series endpoint against the reviewed source contract."""

    if not isinstance(payload, Mapping):
        raise CollectorError("FRED series metadata response must be an object")
    rows = payload.get("seriess")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise CollectorError("FRED series metadata must contain exactly one series")
    source = rows[0]
    expected = _series_spec(series_id)
    if source.get("id") != series_id:
        raise CollectorError(f"FRED metadata series id mismatch for {series_id}")
    for field, expected_value in expected.items():
        if source.get(field) != expected_value:
            raise CollectorError(
                f"FRED metadata {field} mismatch for {series_id}: "
                f"expected {expected_value!r}"
            )

    observation_start = _iso_date(
        source.get("observation_start"), field="metadata.observation_start"
    )
    observation_end = _iso_date(
        source.get("observation_end"), field="metadata.observation_end"
    )
    if observation_end < observation_start:
        raise CollectorError("FRED metadata observation range is inverted")
    notes = source.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise CollectorError("FRED metadata notes must be text or null")

    return {
        "series_id": series_id,
        "title": _nonempty_text(source.get("title"), field="metadata.title"),
        **expected,
        "observation_start": observation_start,
        "observation_end": observation_end,
        "last_updated": _utc_timestamp(
            source.get("last_updated"), field="metadata.last_updated"
        ),
        "notes": notes,
        "period_position": (
            "END_OF_PERIOD" if series_id == "NCBEILQ027S" else "QUARTERLY_SAAR"
        ),
        "period_position_basis": "reviewed_official_series_definition",
    }


def parse_series_observations(
    payload: Mapping[str, Any],
    *,
    observation_end: date | None = None,
) -> list[dict[str, Any]]:
    """Validate current-vintage FRED observations without transforming units.

    FRED's ``.`` missing-value marker is preserved as ``None``.  Exact duplicate
    rows are idempotent; any disagreement for a source date fails closed.
    """

    if not isinstance(payload, Mapping):
        raise CollectorError("FRED observations response must be an object")
    rows = payload.get("observations")
    if not isinstance(rows, list) or not rows:
        raise CollectorError("FRED response missing non-empty observations")

    by_date: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise CollectorError("FRED observation must be an object")
        day = _iso_date(raw.get("date"), field="observation.date")
        if observation_end is not None and date.fromisoformat(day) > observation_end:
            continue
        realtime_start = _iso_date(
            raw.get("realtime_start"), field="observation.realtime_start"
        )
        realtime_end = _iso_date(
            raw.get("realtime_end"), field="observation.realtime_end"
        )
        if realtime_end < realtime_start:
            raise CollectorError("FRED observation realtime range is inverted")

        raw_value = raw.get("value")
        value = (
            None
            if raw_value in (None, "", ".")
            else number(raw_value, field="observation.value")
        )
        point = {
            "date": day,
            "value": value,
            "realtime_start": realtime_start,
            "realtime_end": realtime_end,
        }
        previous = by_date.get(day)
        if previous is not None and previous != point:
            raise CollectorError(f"conflicting duplicate FRED observation date: {day}")
        by_date[day] = point

    if not by_date:
        suffix = (
            f" on or before {observation_end.isoformat()}"
            if observation_end is not None
            else ""
        )
        raise CollectorError(f"FRED response contains no observations{suffix}")
    return [by_date[day] for day in sorted(by_date)]


def parse_series_bundle(
    metadata_payload: Mapping[str, Any],
    observations_payload: Mapping[str, Any],
    *,
    series_id: str,
    observation_end: date | None = None,
) -> dict[str, Any]:
    """Return one validated, untransformed FRED series bundle."""

    metadata = parse_series_metadata(metadata_payload, series_id=series_id)
    observations = parse_series_observations(
        observations_payload, observation_end=observation_end
    )
    metadata_start = date.fromisoformat(metadata["observation_start"])
    metadata_end = date.fromisoformat(metadata["observation_end"])
    for point in observations:
        point_date = date.fromisoformat(point["date"])
        if not metadata_start <= point_date <= metadata_end:
            raise CollectorError(
                f"FRED observation {point['date']} is outside metadata range"
            )
    return {**metadata, "observations": observations}


def _api_key(value: str | None) -> str:
    key = value or os.environ.get("FRED_API_KEY")
    if not key:
        raise CollectorError(
            "FRED_API_KEY is required; unsupported CSV workarounds are disabled"
        )
    if len(key) != 32 or not key.isalnum() or key.lower() != key:
        raise CollectorError(
            "FRED_API_KEY must be a 32-character lowercase alphanumeric key"
        )
    return key


def fetch_series_bundle(
    series_id: str,
    *,
    observation_start: date,
    observation_end: date | None = None,
    api_key: str | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, Any]:
    """Fetch metadata and observations from the official keyed FRED API."""

    _series_spec(series_id)
    if observation_end is not None and observation_end < observation_start:
        raise CollectorError("FRED observation_end must not precede observation_start")
    key = _api_key(api_key)
    common = {"series_id": series_id, "api_key": key, "file_type": "json"}
    observation_parameters = {
        **common,
        "observation_start": observation_start.isoformat(),
        "sort_order": "asc",
        "output_type": "1",
    }
    if observation_end is not None:
        observation_parameters["observation_end"] = observation_end.isoformat()

    metadata_payload = get_json(
        f"{SERIES_URL}?{urlencode(common)}", user_agent=user_agent
    )
    observations_payload = get_json(
        f"{OBSERVATIONS_URL}?{urlencode(observation_parameters)}",
        user_agent=user_agent,
    )
    return parse_series_bundle(
        metadata_payload,
        observations_payload,
        series_id=series_id,
        observation_end=observation_end,
    )
