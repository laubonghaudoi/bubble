from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

DEFAULT_USER_AGENT = "Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com"


class CollectorError(RuntimeError):
    """A source response could not be safely used."""


def number(value: Any, *, field: str) -> float:
    if value in (None, "", "null", ".") or isinstance(value, bool):
        raise CollectorError(f"{field} is missing")
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise CollectorError(f"{field} is not numeric") from exc
    if result != result or result in (float("inf"), float("-inf")):
        raise CollectorError(f"{field} is not finite")
    return result


def optional_number(value: Any, *, field: str) -> float | None:
    if value in (None, "", "null", "."):
        return None
    return number(value, field=field)


def get_json(
    url: str,
    *,
    user_agent: str,
    timeout: float = 30,
    attempts: int = 3,
) -> Mapping[str, Any]:
    """Fetch a JSON object and reject HTML, empty, array, and invalid success bodies."""

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": user_agent,
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get_content_type().lower()
                if content_type not in {"application/json", "application/problem+json"}:
                    raise CollectorError(f"unexpected content type {content_type!r}")
                raw = response.read()
            if not raw.strip():
                raise CollectorError("empty JSON response")
            value = json.loads(raw)
            if not isinstance(value, Mapping):
                raise CollectorError("JSON root must be an object")
            return value
        except (CollectorError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    raise CollectorError(f"request failed after {attempts} attempts: {last_error}")


def as_iso_utc(value: str) -> str:
    """Normalize an ISO timestamp to a canonical UTC Z timestamp."""

    from datetime import datetime, timezone

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise CollectorError("timestamp is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise CollectorError("timestamp must include an offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
