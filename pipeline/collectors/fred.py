from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlencode

from .common import CollectorError, get_json, number

API_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_USER_AGENT = "Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com"


def parse_observations(payload: Mapping[str, Any], *, scale: float = 1) -> list[dict[str, Any]]:
    rows = payload.get("observations")
    if not isinstance(rows, list) or not rows:
        raise CollectorError("FRED response missing non-empty observations")
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise CollectorError("FRED observation must be an object")
        day = row.get("date")
        if not isinstance(day, str):
            raise CollectorError("FRED observation missing date")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise CollectorError("FRED observation has invalid date") from exc
        if row.get("value") in (None, ".", ""):
            continue
        observation = {
            "date": day,
            "value": round(number(row.get("value"), field="value") / scale, 6),
        }
        previous = by_date.get(day)
        if previous is not None and previous != observation:
            raise CollectorError(
                f"conflicting duplicate FRED observation date: {day}"
            )
        by_date[day] = observation
    if not by_date:
        raise CollectorError("FRED response contains no usable observations")
    return [by_date[day] for day in sorted(by_date)]


def fetch_series(
    series_id: str,
    *,
    observation_start: date,
    scale: float = 1,
    api_key: str | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[dict[str, Any]]:
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        raise CollectorError("FRED_API_KEY is required; unsupported CSV workarounds are disabled")
    if len(key) != 32 or not key.isalnum() or key.lower() != key:
        raise CollectorError("FRED_API_KEY must be a 32-character lowercase alphanumeric key")
    query = urlencode(
        {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "observation_start": observation_start.isoformat(),
            "sort_order": "asc",
        }
    )
    return parse_observations(get_json(f"{API_URL}?{query}", user_agent=user_agent), scale=scale)
