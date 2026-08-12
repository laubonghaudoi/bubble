"""CFTC Traders in Financial Futures, futures-only collector.

The public PRE filtered view is used instead of the mixed ``TFF_All`` dataset,
and contract identity is enforced by code.  One request returns both contracts
so Release 2 can publish the four market/category series atomically.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import json
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from .common import CollectorError, DEFAULT_USER_AGENT, as_iso_utc, number


DATASET_ID = "gpe5-46if"
API_URL = f"https://publicreporting.cftc.gov/resource/{DATASET_ID}.json"
PAGE_LIMIT = 1_000
MAX_PAGES = 100
CONTRACTS = {
    "13874A": "E-MINI S&P 500",
    "20974+": "NASDAQ-100 Consolidated",
}
MARKET_NAMES = {
    "13874A": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
    "20974+": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
}
SELECT_FIELDS = (
    "id",
    ":id",
    ":updated_at",
    "market_and_exchange_names",
    "contract_market_name",
    "cftc_contract_market_code",
    "cftc_market_code",
    "cftc_commodity_code",
    "commodity_name",
    "report_date_as_yyyy_mm_dd",
    "open_interest_all",
    "asset_mgr_positions_long",
    "asset_mgr_positions_short",
    "asset_mgr_positions_spread",
    "pct_of_oi_asset_mgr_long",
    "pct_of_oi_asset_mgr_short",
    "lev_money_positions_long",
    "lev_money_positions_short",
    "lev_money_positions_spread",
    "pct_of_oi_lev_money_long",
    "pct_of_oi_lev_money_short",
    "contract_units",
    "futonly_or_combined",
)


def _nonnegative_integer(value: Any, *, field: str) -> int:
    parsed = number(value, field=field)
    if parsed < 0 or not parsed.is_integer():
        raise CollectorError(f"{field} must be a non-negative integer")
    return int(parsed)


def _report_date(value: Any) -> str:
    if not isinstance(value, str):
        raise CollectorError("report_date_as_yyyy_mm_dd is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollectorError("report_date_as_yyyy_mm_dd is invalid") from exc
    if parsed.time() != datetime.min.time():
        raise CollectorError("CFTC report date must be a midnight calendar date")
    return parsed.date().isoformat()


def _nonempty_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectorError(f"{field} must be a non-empty string")
    return value


def _official_percent(value: Any, *, field: str) -> float:
    parsed = number(value, field=field)
    if parsed < 0 or parsed > 100:
        raise CollectorError(f"{field} must be between 0 and 100")
    return parsed


def _plausible_release(value: Any, *, observation_date: str) -> str | None:
    """Keep PRE system update time only when it resembles that report's release.

    Historic PRE rows can be bulk-migrated.  A system update far from the
    Tuesday observation is not represented as an economic release timestamp.
    """

    if not isinstance(value, str):
        raise CollectorError(":updated_at is missing")
    released = as_iso_utc(value)
    released_day = datetime.fromisoformat(released.replace("Z", "+00:00")).date()
    lag = (released_day - date.fromisoformat(observation_date)).days
    return released if 2 <= lag <= 7 else None


def parse_tff_futures_only(
    payload: Sequence[Mapping[str, Any]],
    *,
    contracts: Mapping[str, str] = CONTRACTS,
) -> dict[str, list[dict[str, Any]]]:
    """Validate and normalize raw PRE rows grouped by exact contract code."""

    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence) or not payload:
        raise CollectorError("CFTC response must be a non-empty JSON array")
    expected_codes = set(contracts)
    grouped: dict[str, dict[str, dict[str, Any]]] = {
        code: {} for code in expected_codes
    }
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise CollectorError("CFTC row must be an object")
        code = raw.get("cftc_contract_market_code")
        if code not in expected_codes:
            raise CollectorError(f"unexpected CFTC contract code: {code!r}")
        if raw.get("contract_market_name") != contracts[code]:
            raise CollectorError(f"CFTC contract name mismatch for {code}")
        if raw.get("market_and_exchange_names") != MARKET_NAMES[code]:
            raise CollectorError(f"CFTC market/exchange name mismatch for {code}")
        if raw.get("futonly_or_combined") != "FutOnly":
            raise CollectorError(f"CFTC row {code} is not futures-only")
        row_id = raw.get(":id")
        if not isinstance(row_id, str) or not row_id:
            raise CollectorError("CFTC row is missing :id")
        source_report_id = _nonempty_text(raw.get("id"), field="id")
        day = _report_date(raw.get("report_date_as_yyyy_mm_dd"))
        open_interest = _nonnegative_integer(
            raw.get("open_interest_all"), field="open_interest_all"
        )
        if open_interest == 0:
            raise CollectorError("open_interest_all must be positive")
        asset_manager_long = _nonnegative_integer(
            raw.get("asset_mgr_positions_long"), field="asset_mgr_positions_long"
        )
        asset_manager_short = _nonnegative_integer(
            raw.get("asset_mgr_positions_short"), field="asset_mgr_positions_short"
        )
        leveraged_funds_long = _nonnegative_integer(
            raw.get("lev_money_positions_long"), field="lev_money_positions_long"
        )
        leveraged_funds_short = _nonnegative_integer(
            raw.get("lev_money_positions_short"), field="lev_money_positions_short"
        )
        official_percentages = {
            "asset_manager_pct_long": _official_percent(
                raw.get("pct_of_oi_asset_mgr_long"), field="pct_of_oi_asset_mgr_long"
            ),
            "asset_manager_pct_short": _official_percent(
                raw.get("pct_of_oi_asset_mgr_short"), field="pct_of_oi_asset_mgr_short"
            ),
            "leveraged_funds_pct_long": _official_percent(
                raw.get("pct_of_oi_lev_money_long"), field="pct_of_oi_lev_money_long"
            ),
            "leveraged_funds_pct_short": _official_percent(
                raw.get("pct_of_oi_lev_money_short"), field="pct_of_oi_lev_money_short"
            ),
        }
        reconciliations = {
            "asset_manager_pct_long": 100 * asset_manager_long / open_interest,
            "asset_manager_pct_short": 100 * asset_manager_short / open_interest,
            "leveraged_funds_pct_long": 100 * leveraged_funds_long / open_interest,
            "leveraged_funds_pct_short": 100 * leveraged_funds_short / open_interest,
        }
        for field, calculated in reconciliations.items():
            if abs(official_percentages[field] - calculated) > 0.11:
                raise CollectorError(f"official CFTC percentage does not reconcile: {field}")
        observation = {
            "date": day,
            "contract_code": code,
            "contract_name": contracts[code],
            "market_and_exchange_name": MARKET_NAMES[code],
            "cftc_market_code": _nonempty_text(
                raw.get("cftc_market_code"), field="cftc_market_code"
            ),
            "cftc_commodity_code": _nonempty_text(
                raw.get("cftc_commodity_code"), field="cftc_commodity_code"
            ),
            "commodity_name": _nonempty_text(
                raw.get("commodity_name"), field="commodity_name"
            ),
            "contract_units": _nonempty_text(
                raw.get("contract_units"), field="contract_units"
            ),
            "report_type": "TFF_FUTURES_ONLY",
            "row_id": row_id,
            "source_report_id": source_report_id,
            "released_at": _plausible_release(
                raw.get(":updated_at"), observation_date=day
            ),
            "open_interest": open_interest,
            "asset_manager_long": asset_manager_long,
            "asset_manager_short": asset_manager_short,
            "asset_manager_spread": _nonnegative_integer(
                raw.get("asset_mgr_positions_spread"), field="asset_mgr_positions_spread"
            ),
            "leveraged_funds_long": leveraged_funds_long,
            "leveraged_funds_short": leveraged_funds_short,
            "leveraged_funds_spread": _nonnegative_integer(
                raw.get("lev_money_positions_spread"), field="lev_money_positions_spread"
            ),
            **official_percentages,
        }
        previous = grouped[code].get(day)
        if previous is not None:
            comparable_previous = {k: v for k, v in previous.items() if k != "row_id"}
            comparable_current = {k: v for k, v in observation.items() if k != "row_id"}
            if comparable_previous != comparable_current:
                raise CollectorError(
                    f"conflicting duplicate CFTC observation: {code} {day}"
                )
            continue
        grouped[code][day] = observation
    missing = sorted(code for code, rows in grouped.items() if not rows)
    if missing:
        raise CollectorError(f"CFTC response is missing contracts: {', '.join(missing)}")
    normalized = {
        code: [rows[day] for day in sorted(rows)] for code, rows in grouped.items()
    }
    latest_dates = {rows[-1]["date"] for rows in normalized.values()}
    if len(latest_dates) != 1:
        raise CollectorError("CFTC contracts do not share the same latest report date")
    return normalized


def _get_json_array(
    url: str,
    *,
    user_agent: str,
    timeout: float = 30,
    attempts: int = 3,
) -> list[Mapping[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": user_agent},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get_content_type().lower()
                if content_type not in {"application/json", "application/problem+json"}:
                    raise CollectorError(f"unexpected content type {content_type!r}")
                raw = response.read()
            if not raw.strip():
                raise CollectorError("empty JSON response")
            value = json.loads(raw)
            if not isinstance(value, list):
                raise CollectorError("CFTC JSON root must be an array")
            return value
        except (
            CollectorError,
            json.JSONDecodeError,
            urllib.error.URLError,
            TimeoutError,
        ) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    raise CollectorError(f"request failed after {attempts} attempts: {last_error}")


def fetch_tff_futures_only(
    *,
    start: date,
    end: date,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, list[dict[str, Any]]]:
    if start > end:
        raise CollectorError("CFTC start date must not be after end date")
    codes = " or ".join(
        f'cftc_contract_market_code="{code}"' for code in CONTRACTS
    )
    base_query = {
        "$select": ",".join(SELECT_FIELDS),
        "$where": (
            f"({codes}) and "
            f'report_date_as_yyyy_mm_dd between "{start.isoformat()}T00:00:00.000" '
            f'and "{end.isoformat()}T00:00:00.000"'
        ),
        "$order": "report_date_as_yyyy_mm_dd asc,cftc_contract_market_code asc,id asc,:id asc",
        "$limit": str(PAGE_LIMIT),
    }
    payload: list[Mapping[str, Any]] = []
    for page in range(MAX_PAGES):
        query = urllib.parse.urlencode(
            {**base_query, "$offset": str(page * PAGE_LIMIT)}
        )
        rows = _get_json_array(f"{API_URL}?{query}", user_agent=user_agent)
        payload.extend(rows)
        if len(rows) < PAGE_LIMIT:
            break
    else:
        raise CollectorError(
            f"CFTC pagination exceeded {MAX_PAGES} pages; refusing a partial bundle"
        )
    return parse_tff_futures_only(payload)
