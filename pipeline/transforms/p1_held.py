"""Pure transforms for rights-held P1 provider interfaces.

These helpers deliberately contain no network or publication code.  They make
the future provider contracts testable while production rights gates remain
closed.  Missing inputs stay missing; no transform coerces ``None`` to zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from math import fsum, isfinite, log, sqrt
from statistics import median
from typing import Any


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _iso_date(value: Any, field: str = "date") -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error
    if result.isoformat() != value:
        raise ValueError(f"{field} must be an ISO date")
    return result


def _utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO timestamp") from error
    if result.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return result.astimezone(timezone.utc)


def _dated_values(
    observations: Sequence[Mapping[str, Any]],
    *,
    positive: bool = False,
) -> list[tuple[date, float]]:
    """Normalize observations, skipping nulls and rejecting conflicting dates."""

    by_date: dict[date, float] = {}
    for observation in observations:
        observation_date = _iso_date(observation.get("date"))
        value = observation.get("value")
        if value is None:
            continue
        numeric = _finite_number(value, "value")
        if positive and numeric <= 0:
            raise ValueError("value must be positive")
        previous = by_date.get(observation_date)
        if previous is not None and previous != numeric:
            raise ValueError(
                f"conflicting observations for {observation_date.isoformat()}"
            )
        by_date[observation_date] = numeric
    return sorted(by_date.items())


def _percentile_rank(values: Sequence[float], latest: float) -> float | None:
    if not values:
        return None
    below = sum(value < latest for value in values)
    equal = sum(value == latest for value in values)
    return (below + 0.5 * equal) / len(values)


def vix_vix3m_term_structure(
    vix: Sequence[Mapping[str, Any]],
    vix3m: Sequence[Mapping[str, Any]],
    *,
    percentile_window: int = 756,
    minimum_percentile_samples: int = 252,
) -> list[dict[str, Any]]:
    """Inner-join VIX/VIX3M and return ratio, spread and trailing percentile.

    ``ratio`` is VIX / VIX3M and ``term_spread`` is VIX3M - VIX.  The
    percentile is a mid-rank of the current ratio inside the inclusive
    trailing window.  It remains ``None`` until the declared sample floor is
    met, making partial history visible rather than silently overconfident.
    """

    if percentile_window <= 0 or minimum_percentile_samples <= 0:
        raise ValueError("percentile windows must be positive")
    if minimum_percentile_samples > percentile_window:
        raise ValueError("minimum percentile samples cannot exceed the window")
    vix_by_date = dict(_dated_values(vix, positive=True))
    vix3m_by_date = dict(_dated_values(vix3m, positive=True))
    ratios: list[float] = []
    output: list[dict[str, Any]] = []
    for observation_date in sorted(vix_by_date.keys() & vix3m_by_date.keys()):
        vix_value = vix_by_date[observation_date]
        vix3m_value = vix3m_by_date[observation_date]
        ratio = vix_value / vix3m_value
        ratios.append(ratio)
        window = ratios[-percentile_window:]
        percentile = (
            _percentile_rank(window, ratio)
            if len(window) >= minimum_percentile_samples
            else None
        )
        output.append(
            {
                "date": observation_date.isoformat(),
                "vix": vix_value,
                "vix3m": vix3m_value,
                "ratio": ratio,
                "term_spread": vix3m_value - vix_value,
                "ratio_percentile": percentile,
                "percentile_sample_size": len(window),
            }
        )
    return output


def skew_tail_risk_statistics(
    observations: Sequence[Mapping[str, Any]],
    *,
    change_short: int = 5,
    change_long: int = 20,
    percentile_window: int = 756,
    minimum_percentile_samples: int = 252,
) -> dict[str, Any]:
    """Return SKEW level, observation changes and trailing percentile."""

    if min(change_short, change_long, percentile_window, minimum_percentile_samples) <= 0:
        raise ValueError("SKEW windows must be positive")
    if minimum_percentile_samples > percentile_window:
        raise ValueError("minimum percentile samples cannot exceed the window")
    points = _dated_values(observations)
    values = [value for _, value in points]
    if not values:
        return {
            "observation_date": None,
            "level": None,
            "change_5_observations": None,
            "change_20_observations": None,
            "percentile_3_year": None,
            "percentile_sample_size": 0,
        }
    window = values[-percentile_window:]
    return {
        "observation_date": points[-1][0].isoformat(),
        "level": values[-1],
        "change_5_observations": (
            values[-1] - values[-change_short - 1]
            if len(values) > change_short
            else None
        ),
        "change_20_observations": (
            values[-1] - values[-change_long - 1]
            if len(values) > change_long
            else None
        ),
        "percentile_3_year": (
            _percentile_rank(window, values[-1])
            if len(window) >= minimum_percentile_samples
            else None
        ),
        "percentile_sample_size": len(window),
    }


def crypto_funding_summary(
    events: Sequence[Mapping[str, Any]],
    *,
    asset: str,
    as_of: str,
) -> dict[str, Any]:
    """Summarize variable-interval settled funding without assuming eight hours.

    Per-venue 24-hour values are sums of rates actually settled in the window.
    Seven-day comparisons use each event's explicit interval to normalize its
    rate to a daily equivalent.  Multi-venue output is the median of venue
    summaries; a single venue is always labelled low confidence.
    """

    canonical_asset = asset.strip().upper()
    if canonical_asset not in {"BTC", "ETH"}:
        raise ValueError("asset must be BTC or ETH")
    end = _utc_timestamp(as_of, "as_of")
    normalized: dict[tuple[str, str, datetime], dict[str, Any]] = {}
    for event in events:
        event_asset = event.get("asset")
        venue = event.get("venue")
        if not isinstance(event_asset, str) or not isinstance(venue, str) or not venue.strip():
            raise ValueError("funding event requires asset and venue")
        event_asset = event_asset.strip().upper()
        settled_at = _utc_timestamp(event.get("settled_at"), "settled_at")
        rate = _finite_number(event.get("funding_rate"), "funding_rate")
        interval = _finite_number(event.get("interval_hours"), "interval_hours")
        if interval <= 0:
            raise ValueError("interval_hours must be positive")
        row = {
            "asset": event_asset,
            "venue": venue.strip(),
            "settled_at": settled_at,
            "funding_rate": rate,
            "interval_hours": interval,
            "daily_normalized_rate": rate * 24 / interval,
        }
        key = (row["venue"], event_asset, settled_at)
        if key in normalized and normalized[key] != row:
            raise ValueError("conflicting duplicate funding settlement")
        normalized[key] = row

    selected = [
        row
        for row in normalized.values()
        if row["asset"] == canonical_asset and row["settled_at"] <= end
    ]
    by_venue: dict[str, list[dict[str, Any]]] = {}
    for row in selected:
        by_venue.setdefault(row["venue"], []).append(row)

    venue_output: dict[str, dict[str, Any]] = {}
    for venue, rows in sorted(by_venue.items()):
        rows.sort(key=lambda row: row["settled_at"])
        seven_day = [row for row in rows if row["settled_at"] >= end - timedelta(days=7)]
        if not seven_day:
            continue
        latest = seven_day[-1]
        last_24_hours = [
            row for row in seven_day if row["settled_at"] > end - timedelta(hours=24)
        ]
        normalized_values = [row["daily_normalized_rate"] for row in seven_day]
        venue_output[venue] = {
            "latest_settled_at": latest["settled_at"].isoformat().replace("+00:00", "Z"),
            "latest_funding_rate": latest["funding_rate"],
            "latest_interval_hours": latest["interval_hours"],
            "latest_daily_normalized_rate": latest["daily_normalized_rate"],
            "settled_sum_24h": fsum(row["funding_rate"] for row in last_24_hours),
            "mean_daily_normalized_7d": fsum(normalized_values) / len(normalized_values),
            "percentile_7d": _percentile_rank(
                normalized_values, latest["daily_normalized_rate"]
            ),
            "sample_size_7d": len(seven_day),
        }

    count = len(venue_output)
    if not count:
        return {
            "asset": canonical_asset,
            "as_of": end.isoformat().replace("+00:00", "Z"),
            "venue_count": 0,
            "venue": None,
            "confidence": "UNKNOWN",
            "latest_daily_normalized_rate": None,
            "settled_sum_24h": None,
            "mean_daily_normalized_7d": None,
            "percentile_7d": None,
            "venues": {},
        }

    def venue_median(field: str) -> float:
        return float(median(item[field] for item in venue_output.values()))

    return {
        "asset": canonical_asset,
        "as_of": end.isoformat().replace("+00:00", "Z"),
        "venue_count": count,
        "venue": next(iter(venue_output)) if count == 1 else "MULTI_VENUE_MEDIAN",
        "confidence": "LOW" if count == 1 else "MEDIUM" if count == 2 else "HIGH",
        "latest_daily_normalized_rate": venue_median("latest_daily_normalized_rate"),
        "settled_sum_24h": venue_median("settled_sum_24h"),
        "mean_daily_normalized_7d": venue_median("mean_daily_normalized_7d"),
        "percentile_7d": venue_median("percentile_7d"),
        "venues": venue_output,
    }


def trend_following_proxy(
    observations: Sequence[Mapping[str, Any]],
    *,
    short_window: int = 20,
    long_window: int = 60,
) -> dict[str, Any]:
    """Calculate disclosed price momentum and moving-average regime inputs."""

    if short_window <= 0 or long_window <= short_window:
        raise ValueError("trend windows must satisfy 0 < short < long")
    points = _dated_values(observations, positive=True)
    values = [value for _, value in points]
    if not values:
        return {
            "observation_date": None,
            "price": None,
            "return_20d_pct": None,
            "return_60d_pct": None,
            "moving_average_20d": None,
            "moving_average_60d": None,
            "regime": "UNKNOWN",
        }
    latest = values[-1]
    short_average = (
        fsum(values[-short_window:]) / short_window
        if len(values) >= short_window
        else None
    )
    long_average = (
        fsum(values[-long_window:]) / long_window
        if len(values) >= long_window
        else None
    )
    regime = "UNKNOWN"
    if short_average is not None and long_average is not None:
        if latest > short_average and latest > long_average:
            regime = "ABOVE_BOTH"
        elif latest < short_average and latest < long_average:
            regime = "BELOW_BOTH"
        elif latest == short_average and latest == long_average:
            regime = "FLAT"
        else:
            regime = "MIXED"
    return {
        "observation_date": points[-1][0].isoformat(),
        "price": latest,
        "return_20d_pct": (
            (latest / values[-short_window - 1] - 1) * 100
            if len(values) > short_window
            else None
        ),
        "return_60d_pct": (
            (latest / values[-long_window - 1] - 1) * 100
            if len(values) > long_window
            else None
        ),
        "moving_average_20d": short_average,
        "moving_average_60d": long_average,
        "regime": regime,
    }


def _daily_changes(
    observations: Sequence[Mapping[str, Any]], *, kind: str
) -> dict[date, float]:
    points = _dated_values(observations, positive=kind == "price")
    output: dict[date, float] = {}
    for index in range(1, len(points)):
        current_date, current = points[index]
        previous = points[index - 1][1]
        output[current_date] = (
            log(current / previous) if kind == "price" else (current - previous) * 100
        )
    return output


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = fsum(left) / len(left)
    right_mean = fsum(right) / len(right)
    left_var = fsum((value - left_mean) ** 2 for value in left)
    right_var = fsum((value - right_mean) ** 2 for value in right)
    if left_var <= 0 or right_var <= 0:
        return None
    covariance = fsum(
        (left[index] - left_mean) * (right[index] - right_mean)
        for index in range(len(left))
    )
    return covariance / sqrt(left_var * right_var)


def cross_asset_correlations(
    series: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    price_series_ids: Sequence[str],
    yield_series_ids: Sequence[str],
    pairs: Sequence[tuple[str, str, str]],
    short_window: int = 20,
    long_window: int = 60,
    minimum_short_samples: int = 15,
    minimum_long_samples: int = 40,
) -> dict[str, dict[str, Any]]:
    """Calculate inner-joined price-return/yield-change correlations.

    Price inputs become log returns; yield inputs become basis-point changes.
    The 20-day value is withheld below 15 common observations and the 60-day
    value below 40, exactly preserving insufficient coverage as ``None``.
    """

    if not (0 < minimum_short_samples <= short_window < long_window):
        raise ValueError("invalid short correlation window")
    if not (0 < minimum_long_samples <= long_window):
        raise ValueError("invalid long correlation window")
    price_ids = set(price_series_ids)
    yield_ids = set(yield_series_ids)
    if price_ids & yield_ids:
        raise ValueError("a series cannot be both price and yield")
    unknown = set(series) - price_ids - yield_ids
    if unknown:
        raise ValueError(f"series kind is not declared: {', '.join(sorted(unknown))}")
    changes = {
        metric_id: _daily_changes(
            observations, kind="price" if metric_id in price_ids else "yield"
        )
        for metric_id, observations in series.items()
    }
    output: dict[str, dict[str, Any]] = {}
    for label, left_id, right_id in pairs:
        if left_id not in changes or right_id not in changes:
            raise ValueError(f"pair {label} references an unknown series")
        dates = sorted(changes[left_id].keys() & changes[right_id].keys())
        left = [changes[left_id][day] for day in dates]
        right = [changes[right_id][day] for day in dates]
        short_count = min(len(dates), short_window)
        long_count = min(len(dates), long_window)
        output[label] = {
            "left": left_id,
            "right": right_id,
            "left_transform": "LOG_RETURN" if left_id in price_ids else "YIELD_BP_CHANGE",
            "right_transform": "LOG_RETURN" if right_id in price_ids else "YIELD_BP_CHANGE",
            "latest_common_date": dates[-1].isoformat() if dates else None,
            "common_sample_size": len(dates),
            "correlation_20d": (
                _correlation(left[-short_count:], right[-short_count:])
                if short_count >= minimum_short_samples
                else None
            ),
            "sample_size_20d": short_count,
            "correlation_60d": (
                _correlation(left[-long_count:], right[-long_count:])
                if long_count >= minimum_long_samples
                else None
            ),
            "sample_size_60d": long_count,
        }
    return output
