"""Pure Release 2 Market Ignition transforms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from math import isfinite, sqrt
from typing import Any

from pipeline.collectors.common import CollectorError


CATEGORIES = {
    "asset_manager": ("asset_manager_long", "asset_manager_short"),
    "leveraged_funds": ("leveraged_funds_long", "leveraged_funds_short"),
}


def cftc_position_series(
    rows: Sequence[Mapping[str, Any]], *, category: str
) -> list[dict[str, Any]]:
    """Calculate raw net position and net percent OI without rounded source pct."""

    if category not in CATEGORIES:
        raise ValueError(f"unsupported CFTC category: {category}")
    long_field, short_field = CATEGORIES[category]
    output = []
    previous_date: str | None = None
    identity: tuple[str, str] | None = None
    for row in rows:
        try:
            long_value = int(row[long_field])
            short_value = int(row[short_field])
            open_interest = int(row["open_interest"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CollectorError("normalized CFTC row is missing position fields") from exc
        if open_interest <= 0 or min(long_value, short_value) < 0:
            raise CollectorError("normalized CFTC positions have an invalid domain")
        day = row.get("date")
        try:
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                raise ValueError
        except ValueError as exc:
            raise CollectorError("normalized CFTC row has an invalid date") from exc
        if previous_date is not None and day <= previous_date:
            raise CollectorError("normalized CFTC dates must be strictly increasing")
        previous_date = day
        current_identity = (str(row.get("contract_code")), str(row.get("contract_name")))
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise CollectorError("normalized CFTC series mixes contract identities")
        net_position = long_value - short_value
        raw_net_percent = 100 * net_position / open_interest
        if not isfinite(raw_net_percent):
            raise CollectorError("normalized CFTC net percent is not finite")
        point = {
            "date": day,
            "value": round(raw_net_percent, 6),
            "net_percent_open_interest_raw": raw_net_percent,
            "net_position": net_position,
            "open_interest": open_interest,
            "long_position": long_value,
            "short_position": short_value,
            "contract_code": row["contract_code"],
            "contract_name": row["contract_name"],
            "trader_category": category,
            "report_type": row["report_type"],
            "row_id": row["row_id"],
            "source_report_id": row["source_report_id"],
        }
        for field in (
            "market_and_exchange_name",
            "cftc_market_code",
            "cftc_commodity_code",
            "commodity_name",
            "contract_units",
            f"{category}_spread",
            f"{category}_pct_long",
            f"{category}_pct_short",
        ):
            if field not in row:
                raise CollectorError(f"normalized CFTC row is missing {field}")
            point[field] = row[field]
        if row.get("released_at") is not None:
            point["released_at"] = row["released_at"]
        output.append(point)
    return output


def _change(values: Sequence[float], weeks: int) -> float | None:
    return round(values[-1] - values[-(weeks + 1)], 6) if len(values) > weeks else None


def _population_z_score(values: Sequence[float]) -> float | None:
    if len(values) < 156:
        return None
    window = list(values[-156:])
    mean = sum(window) / len(window)
    variance = sum((value - mean) ** 2 for value in window) / len(window)
    if variance == 0:
        return None
    return round((window[-1] - mean) / sqrt(variance), 6)


def cftc_position_statistics(
    points: Sequence[Mapping[str, Any]],
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
    latest = points[-1]
    return {
        "sample_size": len(points),
        "net_position": int(latest["net_position"]),
        "open_interest": int(latest["open_interest"]),
        "net_percent_open_interest": values[-1],
        "change_8_weeks": _change(values, 8),
        "change_12_weeks": _change(values, 12),
        # Population standard deviation (ddof=0) over the latest 156 reports.
        "z_score_3_year": _population_z_score(values),
        "z_score_3_year_sample_size": min(len(values), 156),
    }


def positioning_direction(change_8_weeks: float | int | None) -> str:
    if change_8_weeks is None:
        return "UNKNOWN"
    if change_8_weeks > 0:
        return "MORE_NET_LONG"
    if change_8_weeks < 0:
        return "MORE_NET_SHORT"
    return "FLAT"


def common_direction(directions: Sequence[str]) -> str:
    known = [direction for direction in directions if direction != "UNKNOWN"]
    if len(known) != len(directions) or not known:
        return "UNKNOWN"
    return known[0] if len(set(known)) == 1 else "MIXED"
