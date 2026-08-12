from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlencode

from .common import CollectorError, get_json, number

API_ROOT = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1"
DEFAULT_USER_AGENT = "Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com"


def parse_tga(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise CollectorError("FiscalData TGA response missing non-empty data")
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise CollectorError("FiscalData TGA row must be an object")
        day = row.get("record_date")
        if not isinstance(day, str):
            raise CollectorError("FiscalData TGA row missing record_date")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise CollectorError("FiscalData TGA row has invalid record_date") from exc
        if row.get("account_type") != "Treasury General Account (TGA) Closing Balance":
            raise CollectorError("FiscalData TGA response contains the wrong account_type")
        # FiscalData's current DTS row-oriented payload puts the row's `Today`
        # amount in open_today_bal even for the explicit Closing Balance row.
        # This is an audited source-field mapping, never a same-row opening-balance
        # fallback: the account_type must identify the closing-balance line.
        source_field = "close_today_bal"
        raw = row.get(source_field)
        if raw in (None, "", "null"):
            source_field = "open_today_bal"
            raw = row.get(source_field)
        value = number(raw, field=source_field)
        observation = {
            "date": day,
            "value": round(value / 1_000, 6),
            "source_field": source_field,
        }
        previous = by_date.get(day)
        if previous is not None and previous != observation:
            raise CollectorError(
                f"conflicting duplicate FiscalData TGA observation date: {day}"
            )
        by_date[day] = observation
    if not by_date:
        raise CollectorError("FiscalData TGA response contains no published closing balances")
    return [by_date[day] for day in sorted(by_date)]


def fetch_tga(*, page_size: int = 400, user_agent: str = DEFAULT_USER_AGENT) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "filter": "account_type:eq:Treasury General Account (TGA) Closing Balance",
            "sort": "-record_date",
            "page[size]": page_size,
        }
    )
    payload = get_json(
        f"{API_ROOT}/accounting/dts/operating_cash_balance?{query}",
        user_agent=user_agent,
    )
    return parse_tga(payload)


def parse_auctions(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise CollectorError("FiscalData auction response missing non-empty data")
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise CollectorError("FiscalData auction row must be an object")
        cusip, auction_day, issue_day = row.get("cusip"), row.get("auction_date"), row.get("issue_date")
        if not all(isinstance(value, str) and value not in {"", "null"} for value in (cusip, auction_day, issue_day)):
            raise CollectorError("auction row missing CUSIP, auction_date, or issue_date")
        try:
            date.fromisoformat(str(auction_day))
            date.fromisoformat(str(issue_day))
        except ValueError as exc:
            raise CollectorError("auction row has invalid auction_date or issue_date") from exc
        amount = number(row.get("offering_amt"), field="offering_amt")
        key = (str(cusip), str(auction_day), str(issue_day))
        auction = {
            "cusip": str(cusip),
            "auction_date": str(auction_day),
            "issue_date": str(issue_day),
            "offering_usd_bn": round(amount / 1_000_000_000, 6),
            "security_type": row.get("security_type"),
            "security_term": row.get("security_term"),
        }
        previous = by_key.get(key)
        if previous is not None and previous != auction:
            raise CollectorError(
                "conflicting duplicate FiscalData auction key: "
                f"{key[0]}/{key[1]}/{key[2]}"
            )
        by_key[key] = auction
    return sorted(by_key.values(), key=lambda row: (row["issue_date"], row["cusip"], row["auction_date"]))


def fetch_auctions(
    *,
    start: date,
    page_size: int = 10_000,
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "filter": f"issue_date:gte:{start.isoformat()}",
            "sort": "issue_date,cusip,auction_date",
            "page[size]": page_size,
        }
    )
    payload = get_json(f"{API_ROOT}/accounting/od/auctions_query?{query}", user_agent=user_agent)
    rows = payload.get("data")
    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        total = meta.get("total-count") or meta.get("total_count")
        if total not in (None, "null") and int(total) > page_size:
            raise CollectorError("auction response is paginated beyond configured page size")
    return parse_auctions(payload)
