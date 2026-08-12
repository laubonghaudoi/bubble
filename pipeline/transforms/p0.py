"""Pure P0 liquidity transforms.

Collectors are expected to normalize source-specific payloads before calling
these helpers.  The functions in this module never fetch data and fail closed
on conflicting duplicate observations.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Collection, Mapping, Sequence
from datetime import date
from math import floor, fsum, isfinite
from typing import Any


IORB_SPREAD_RATE_IDS = ("sofr", "effr", "obfr", "tgcr", "bgcr")
SRF_COLLATERAL_TYPES = ("treasury", "agency_debt", "agency_mbs")


def _as_date(value: Any, field: str = "date") -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be an ISO date")
    return parsed


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return float(value)


def _valid_observations(observations: Sequence[Mapping[str, Any]]) -> list[tuple[date, float]]:
    """Return sorted, non-null observations and reject conflicting duplicates."""

    by_date: dict[date, float] = {}
    for observation in observations:
        observation_date = _as_date(observation.get("date"))
        value = observation.get("value")
        if value is None:
            continue
        numeric = _number(value, "value")
        previous = by_date.get(observation_date)
        if previous is not None and previous != numeric:
            raise ValueError(f"conflicting observations for {observation_date.isoformat()}")
        by_date[observation_date] = numeric
    return sorted(by_date.items())


def backward_asof_join(
    primary: Sequence[Mapping[str, Any]],
    regime: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join each valid primary observation to the latest regime value on or before it.

    This is an observation-date backward as-of join.  It never interpolates,
    and primary dates before the first regime observation are omitted.
    """

    primary_points = _valid_observations(primary)
    regime_points = _valid_observations(regime)
    regime_dates = [item[0] for item in regime_points]
    joined: list[dict[str, Any]] = []
    for primary_date, primary_value in primary_points:
        regime_index = bisect_right(regime_dates, primary_date) - 1
        if regime_index < 0:
            continue
        regime_date, regime_value = regime_points[regime_index]
        joined.append(
            {
                "date": primary_date.isoformat(),
                "left": primary_value,
                "right": regime_value,
                "right_observation_date": regime_date.isoformat(),
            }
        )
    return joined


def build_iorb_spreads(
    rate_series: Mapping[str, Sequence[Mapping[str, Any]]],
    iorb_series: Sequence[Mapping[str, Any]],
    *,
    rate_ids: Sequence[str] = IORB_SPREAD_RATE_IDS,
) -> dict[str, list[dict[str, Any]]]:
    """Build the five canonical market-rate minus IORB spread series in bp."""

    output: dict[str, list[dict[str, Any]]] = {}
    for rate_id in rate_ids:
        observations = []
        for joined in backward_asof_join(rate_series.get(rate_id, ()), iorb_series):
            observations.append(
                {
                    "date": joined["date"],
                    "value": round((joined["left"] - joined["right"]) * 100, 4),
                    "market_rate_pct": joined["left"],
                    "iorb_pct": joined["right"],
                    "iorb_observation_date": joined["right_observation_date"],
                }
            )
        output[f"{rate_id}_iorb_spread_bp"] = observations
    return output


def _contiguous_streak(values: Sequence[float], predicate: Any) -> int:
    count = 0
    for value in reversed(values):
        if not predicate(value):
            break
        count += 1
    return count


def _linear_slope(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    x_mean = (len(values) - 1) / 2
    y_mean = fsum(values) / len(values)
    denominator = fsum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    numerator = fsum((index - x_mean) * (value - y_mean) for index, value in enumerate(values))
    return round(numerator / denominator, 4)


def spread_observation_stats(
    observations: Sequence[Mapping[str, Any]],
    *,
    alert_threshold_bp: float = 3.0,
) -> dict[str, int | float | None]:
    """Calculate effective-observation changes, five-observation trend and streaks."""

    values = [value for _, value in _valid_observations(observations)]
    window = values[-5:]
    return {
        "latest": values[-1] if values else None,
        "change_1obs": round(values[-1] - values[-2], 4) if len(values) >= 2 else None,
        "change_5obs": round(values[-1] - values[-6], 4) if len(values) >= 6 else None,
        "mean_5obs": round(fsum(window) / len(window), 4) if window else None,
        "slope_5obs_bp_per_obs": _linear_slope(window),
        "positive_streak": _contiguous_streak(values, lambda value: value > 0),
        "above_3bp_streak": _contiguous_streak(values, lambda value: value > alert_threshold_bp),
        "observations_used": len(window),
    }


def h41_weekly_stats(observations: Sequence[Mapping[str, Any]]) -> dict[str, int | float | None]:
    """Return level plus one- and four-observation changes for weekly H.4.1 data."""

    values = [value for _, value in _valid_observations(observations)]
    return {
        "level": values[-1] if values else None,
        "change_1w": round(values[-1] - values[-2], 3) if len(values) >= 2 else None,
        "change_4w": round(values[-1] - values[-5], 3) if len(values) >= 5 else None,
        "observations_used": len(values),
    }


def on_rrp_near_floor_context(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Describe ON RRP's history-relative position without a dollar threshold.

    The latest accepted amount is ranked inside the last 20 valid published
    observations.  ``near_floor`` is only available for a complete 20-point
    window and is descriptive context, never a danger or severity signal.
    """

    values = [value for _, value in _valid_observations(observations)][-20:]
    percentile_rank: float | None = None
    if values:
        latest = values[-1]
        below = sum(value < latest for value in values)
        equal = sum(value == latest for value in values)
        percentile_rank = round((below + 0.5 * equal) / len(values), 6)
    sufficient = len(values) >= 20
    return {
        "method": "TRAILING_20_OBSERVATION_PERCENTILE",
        "sample_size": len(values),
        "percentile_rank": percentile_rank,
        "near_floor": (
            percentile_rank <= 0.10
            if sufficient and percentile_rank is not None
            else None
        ),
        "threshold_rule": "BOTTOM_DECILE_WHEN_SAMPLE_SUFFICIENT",
        "interpretation": (
            "History-relative context only, not a danger signal. Falling ON RRP "
            "may cushion QT or TGA growth, or simply reflect more attractive "
            "bill and repo returns."
        ),
    }


def h41_change_4w_context(
    observations: Sequence[Mapping[str, Any]],
    *,
    trailing_years: int = 5,
) -> dict[str, int | float | None]:
    """Compare the latest four-observation H.4.1 change with trailing-history p10.

    The percentile uses completed four-observation changes strictly before the
    latest observation and only those whose ending dates fall inside the
    trailing calendar-year window.  The current change is never in its own
    reference distribution.
    """

    if trailing_years <= 0:
        raise ValueError("trailing_years must be positive")
    points = _valid_observations(observations)
    if len(points) < 5:
        return {
            "change_4w": None,
            "trailing_5y_p10": None,
            "trailing_sample_size": 0,
        }
    current_date = points[-1][0]
    current_change = round(points[-1][1] - points[-5][1], 3)
    start = _years_before(current_date, trailing_years)
    historical_changes = [
        points[index][1] - points[index - 4][1]
        for index in range(4, len(points) - 1)
        if start <= points[index][0] < current_date
    ]
    p10 = _percentile(historical_changes, 0.10) if historical_changes else None
    return {
        "change_4w": current_change,
        "trailing_5y_p10": round(p10, 3) if p10 is not None else None,
        "trailing_sample_size": len(historical_changes),
    }


def _collateral_type(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("collateral_type must be a string")
    canonical = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"agency": "agency_debt", "mbs": "agency_mbs"}
    canonical = aliases.get(canonical, canonical)
    if canonical not in SRF_COLLATERAL_TYPES:
        raise ValueError(f"unsupported SRF collateral_type: {value}")
    return canonical


def aggregate_srf_operations(
    operations: Sequence[Mapping[str, Any]],
    *,
    exercise_operation_ids: Collection[str],
) -> list[dict[str, Any]]:
    """Aggregate normalized SRF operations by date without amount-based heuristics.

    ``exercise_operation_ids`` is a reviewed operational-readiness operation
    allowlist.  A technical operation never suppresses a regular operation on
    the same date.
    Exact duplicate rows are ignored; conflicting rows for an
    operation/collateral key fail closed.  Every operation on an allowlisted
    ID is marked technical and excluded from alert-eligible accepted use.
    """

    if isinstance(exercise_operation_ids, str):
        raise ValueError("exercise_operation_ids must be a collection of strings")
    reviewed_exercise_ids: set[str] = set()
    for value in exercise_operation_ids:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("exercise operation ID must be a non-empty string")
        reviewed_exercise_ids.add(value.strip())
    normalized: dict[tuple[str, str, str], dict[str, Any]] = {}
    for operation in operations:
        operation_id = operation.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id is required")
        operation_id = operation_id.strip()
        operation_date = _as_date(operation.get("operation_date"), "operation_date").isoformat()
        collateral = _collateral_type(operation.get("collateral_type"))
        submitted = _number(operation.get("submitted_amount_usd_bn"), "submitted_amount_usd_bn")
        accepted = _number(operation.get("accepted_amount_usd_bn"), "accepted_amount_usd_bn")
        if submitted < 0 or accepted < 0 or accepted > submitted:
            raise ValueError("SRF amounts must satisfy 0 <= accepted <= submitted")
        rate = operation.get("rate_pct")
        rate_pct = None if rate is None else _number(rate, "rate_pct")
        row = {
            "operation_id": operation_id,
            "operation_date": operation_date,
            "collateral_type": collateral,
            "submitted_amount_usd_bn": submitted,
            "accepted_amount_usd_bn": accepted,
            "rate_pct": rate_pct,
            "technical_exercise": operation_id in reviewed_exercise_ids,
        }
        key = (operation_date, operation_id, collateral)
        if key in normalized and normalized[key] != row:
            raise ValueError(f"conflicting duplicate SRF operation: {operation_id}/{collateral}")
        normalized[key] = row

    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in normalized.values():
        by_date.setdefault(row["operation_date"], []).append(row)

    daily: list[dict[str, Any]] = []
    for operation_date, rows in sorted(by_date.items()):
        operation_ids = {row["operation_id"] for row in rows}
        exercise_ids_on_date = {row["operation_id"] for row in rows if row["technical_exercise"]}
        nonexercise_ids = operation_ids - exercise_ids_on_date
        breakdown: dict[str, dict[str, float]] = {}
        for collateral in SRF_COLLATERAL_TYPES:
            collateral_rows = [row for row in rows if row["collateral_type"] == collateral]
            breakdown[collateral] = {
                "submitted_amount_usd_bn": round(
                    fsum(row["submitted_amount_usd_bn"] for row in collateral_rows), 6
                ),
                "accepted_amount_usd_bn": round(
                    fsum(row["accepted_amount_usd_bn"] for row in collateral_rows), 6
                ),
                "alert_eligible_accepted_amount_usd_bn": round(
                    fsum(
                        row["accepted_amount_usd_bn"]
                        for row in collateral_rows
                        if not row["technical_exercise"]
                    ),
                    6,
                ),
            }
        rates = sorted({row["rate_pct"] for row in rows if row["rate_pct"] is not None})
        accepted = round(fsum(row["accepted_amount_usd_bn"] for row in rows), 6)
        alert_eligible = round(
            fsum(row["accepted_amount_usd_bn"] for row in rows if not row["technical_exercise"]), 6
        )
        daily.append(
            {
                "date": operation_date,
                "submitted_amount_usd_bn": round(
                    fsum(row["submitted_amount_usd_bn"] for row in rows), 6
                ),
                "accepted_amount_usd_bn": accepted,
                "alert_eligible_accepted_amount_usd_bn": alert_eligible,
                "exercise_accepted_amount_usd_bn": round(accepted - alert_eligible, 6),
                "operation_count": len(operation_ids),
                "exercise_operation_count": len(exercise_ids_on_date),
                "has_technical_exercise": bool(exercise_ids_on_date),
                "technical_exercise": bool(exercise_ids_on_date) and not nonexercise_ids,
                "rate_pct": rates[0] if len(rates) == 1 else None,
                "rates_pct": rates,
                "breakdown": breakdown,
            }
        )
    return daily


def srf_nontechnical_positive_use_streak(
    observations: Sequence[Mapping[str, Any]],
) -> int:
    """Count contiguous positive nontechnical SRF observations.

    Technical-only exercises are removed from the eligible observation
    sequence.  A genuine zero-use observation resets the streak.  Mixed days
    use only ``alert_eligible_accepted_amount_usd_bn`` from regular operations.
    """

    by_date: dict[str, tuple[float, bool]] = {}
    for observation in observations:
        observation_date = _as_date(observation.get("date")).isoformat()
        technical = observation.get("technical_exercise", False)
        if not isinstance(technical, bool):
            raise ValueError("technical_exercise must be boolean")
        raw_amount = observation.get(
            "alert_eligible_accepted_amount_usd_bn",
            observation.get("accepted_amount_usd_bn", observation.get("value")),
        )
        amount = _number(raw_amount, "alert_eligible_accepted_amount_usd_bn")
        if amount < 0:
            raise ValueError("SRF accepted amount cannot be negative")
        canonical = (amount, technical)
        previous = by_date.get(observation_date)
        if previous is not None and previous != canonical:
            raise ValueError(
                f"conflicting duplicate SRF daily observation: {observation_date}"
            )
        by_date[observation_date] = canonical

    streak = 0
    for observation_date in sorted(by_date):
        amount, technical = by_date[observation_date]
        if technical:
            continue
        streak = streak + 1 if amount > 0 else 0
    return streak


def observation_period_end_flags(
    observation_date: str,
    observation_calendar: Sequence[str],
) -> list[str]:
    """Classify period ends using the next actual valid observation date."""

    target = _as_date(observation_date, "observation_date")
    calendar = sorted({_as_date(item, "observation_calendar date") for item in observation_calendar})
    if target not in calendar:
        raise ValueError("observation_date is absent from observation_calendar")
    next_dates = [item for item in calendar if item > target]
    if not next_dates:
        return []
    next_date = next_dates[0]
    flags: list[str] = []
    if (target.year, target.month) != (next_date.year, next_date.month):
        flags.append("MONTH_END")
    target_quarter = (target.month - 1) // 3
    next_quarter = (next_date.month - 1) // 3
    if target.year != next_date.year or target_quarter != next_quarter:
        flags.append("QUARTER_END")
    if target.year != next_date.year:
        flags.append("YEAR_END")
    return flags


def aggregate_treasury_settlements(
    auctions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Dedupe auctions by (CUSIP, auction date, issue date) and sum settlements."""

    normalized: dict[tuple[str, str, str], dict[str, Any]] = {}
    for auction in auctions:
        cusip = auction.get("cusip")
        if not isinstance(cusip, str) or not cusip:
            raise ValueError("cusip is required")
        auction_date = _as_date(auction.get("auction_date"), "auction_date").isoformat()
        issue_date = _as_date(auction.get("issue_date"), "issue_date").isoformat()
        amount = _number(auction.get("offering_amount_usd_bn"), "offering_amount_usd_bn")
        if amount < 0:
            raise ValueError("offering_amount_usd_bn cannot be negative")
        row = {
            "cusip": cusip,
            "auction_date": auction_date,
            "issue_date": issue_date,
            "date": issue_date,
            "offering_amount_usd_bn": amount,
        }
        key = (cusip, auction_date, issue_date)
        if key in normalized and normalized[key] != row:
            raise ValueError(f"conflicting duplicate Treasury auction: {key}")
        normalized[key] = row

    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in normalized.values():
        by_date.setdefault(row["date"], []).append(row)
    return [
        {
            "date": settlement_date,
            "treasury_settlement_usd_bn": round(
                fsum(row["offering_amount_usd_bn"] for row in rows), 6
            ),
            "security_count": len(rows),
            "auction_keys": sorted(
                [row["cusip"], row["auction_date"], row["issue_date"]] for row in rows
            ),
        }
        for settlement_date, rows in sorted(by_date.items())
    ]


def _years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def add_large_settlement_context(
    daily_settlements: Sequence[Mapping[str, Any]],
    *,
    trailing_years: int = 3,
    percentile: float = 0.90,
    minimum_nonzero_samples: int = 60,
) -> list[dict[str, Any]]:
    """Add trailing, no-lookahead settlement p90 context to daily totals."""

    if trailing_years <= 0 or not 0 < percentile < 1 or minimum_nonzero_samples <= 0:
        raise ValueError("invalid large-settlement context parameters")
    normalized: list[tuple[date, float, Mapping[str, Any]]] = []
    seen_dates: set[date] = set()
    for item in daily_settlements:
        item_date = _as_date(item.get("date"))
        if item_date in seen_dates:
            raise ValueError(f"duplicate daily settlement date: {item_date.isoformat()}")
        seen_dates.add(item_date)
        amount = _number(item.get("treasury_settlement_usd_bn"), "treasury_settlement_usd_bn")
        if amount < 0:
            raise ValueError("treasury_settlement_usd_bn cannot be negative")
        normalized.append((item_date, amount, item))
    normalized.sort(key=lambda item: item[0])

    output: list[dict[str, Any]] = []
    for item_date, amount, item in normalized:
        start = _years_before(item_date, trailing_years)
        history = [
            prior_amount
            for prior_date, prior_amount, _ in normalized
            if start <= prior_date < item_date and prior_amount > 0
        ]
        threshold = _percentile(history, percentile) if len(history) >= minimum_nonzero_samples else None
        flags = list(item.get("flags", ()))
        if amount > 0 and "TREASURY_SETTLEMENT" not in flags:
            flags.append("TREASURY_SETTLEMENT")
        is_large = None if threshold is None else amount >= threshold and amount > 0
        if is_large and "LARGE_TREASURY_SETTLEMENT" not in flags:
            flags.append("LARGE_TREASURY_SETTLEMENT")
        output.append(
            {
                **item,
                "date": item_date.isoformat(),
                "treasury_settlement_usd_bn": amount,
                "trailing_nonzero_sample_size": len(history),
                "trailing_p90_usd_bn": round(threshold, 6) if threshold is not None else None,
                "large_treasury_settlement": is_large,
                "flags": flags,
            }
        )
    return output


def reviewed_tax_window_events(
    tax_dates: Sequence[Mapping[str, Any]],
    business_calendar: Sequence[str],
    *,
    adjacent_business_days: int = 1,
) -> list[dict[str, Any]]:
    """Expand reviewed tax deadlines to adjacent dates in a supplied business calendar."""

    if adjacent_business_days < 0:
        raise ValueError("adjacent_business_days cannot be negative")
    calendar = sorted({_as_date(item, "business_calendar date") for item in business_calendar})
    index_by_date = {item: index for index, item in enumerate(calendar)}
    events: dict[date, dict[str, set[str]]] = {}
    for item in tax_dates:
        if item.get("reviewed") is not True:
            raise ValueError("tax deadline must be explicitly reviewed")
        tax_type = item.get("tax_type")
        source_url = item.get("source_url")
        if not isinstance(tax_type, str) or not tax_type:
            raise ValueError("tax_type is required")
        if not isinstance(source_url, str) or not source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        original = _as_date(item.get("original_deadline"), "original_deadline")
        observed = _as_date(item.get("observed_deadline"), "observed_deadline")
        if observed not in index_by_date:
            raise ValueError("observed_deadline is absent from business_calendar")
        observed_index = index_by_date[observed]
        lower = max(0, observed_index - adjacent_business_days)
        upper = min(len(calendar), observed_index + adjacent_business_days + 1)
        for window_date in calendar[lower:upper]:
            event = events.setdefault(
                window_date,
                {"tax_types": set(), "sources": set(), "deadlines": set()},
            )
            event["tax_types"].add(tax_type)
            event["sources"].add(source_url)
            event["deadlines"].add(
                f"{original.isoformat()}->{observed.isoformat()}"
            )
    return [
        {
            "date": event_date.isoformat(),
            "flags": ["TAX_WINDOW"],
            "tax_types": sorted(event["tax_types"]),
            "sources": sorted(event["sources"]),
            "deadlines": sorted(event["deadlines"]),
        }
        for event_date, event in sorted(events.items())
    ]
