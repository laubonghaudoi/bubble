"""Pure P2 macro transform for the nonfinancial-equities/GDP proxy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from math import isfinite
from typing import Any

from pipeline.collectors.common import CollectorError

METRIC_ID = "nonfinancial_equities_gdp_proxy"
EQUITIES_SERIES_ID = "NCBEILQ027S"
GDP_SERIES_ID = "GDP"
PERCENTILE_WINDOW_QUARTERS = 40


def _finite_or_none(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CollectorError(f"{field} must be numeric or null")
    result = float(value)
    if not isfinite(result):
        raise CollectorError(f"{field} must be finite")
    return result


def _iso_date(value: Any, *, field: str) -> date:
    if not isinstance(value, str):
        raise CollectorError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CollectorError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise CollectorError(f"{field} must be an ISO date")
    return parsed


def _quarter_key(value: date) -> tuple[int, int]:
    return value.year, (value.month - 1) // 3 + 1


def _quarter_ordinal(key: tuple[int, int]) -> int:
    year, quarter = key
    return year * 4 + quarter - 1


def _quarter_end(key: tuple[int, int]) -> str:
    year, quarter = key
    return date(year, quarter * 3, (31, 30, 30, 31)[quarter - 1]).isoformat()


def _validated_quarters(
    bundle: Mapping[str, Any], *, expected_series_id: str
) -> dict[tuple[int, int], dict[str, Any]]:
    if not isinstance(bundle, Mapping) or bundle.get("series_id") != expected_series_id:
        raise CollectorError(f"expected FRED series {expected_series_id}")
    observations = bundle.get("observations")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise CollectorError(f"{expected_series_id} observations must be a list")

    by_quarter: dict[tuple[int, int], dict[str, Any]] = {}
    for raw in observations:
        if not isinstance(raw, Mapping):
            raise CollectorError(f"{expected_series_id} observation must be an object")
        source_date = _iso_date(
            raw.get("date"), field=f"{expected_series_id}.observation.date"
        )
        value = _finite_or_none(
            raw.get("value"), field=f"{expected_series_id}.observation.value"
        )
        realtime_start = _iso_date(
            raw.get("realtime_start"),
            field=f"{expected_series_id}.observation.realtime_start",
        )
        realtime_end = _iso_date(
            raw.get("realtime_end"),
            field=f"{expected_series_id}.observation.realtime_end",
        )
        if realtime_end < realtime_start:
            raise CollectorError(f"{expected_series_id} realtime range is inverted")
        quarter = _quarter_key(source_date)
        point = {
            "source_date": source_date.isoformat(),
            "value": value,
            "realtime_start": realtime_start.isoformat(),
            "realtime_end": realtime_end.isoformat(),
        }
        previous = by_quarter.get(quarter)
        if previous is not None and previous != point:
            raise CollectorError(
                f"{expected_series_id} has conflicting observations in "
                f"{quarter[0]}-Q{quarter[1]}"
            )
        by_quarter[quarter] = point
    return by_quarter


def _percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def _midrank(values: Sequence[float], current: float) -> float:
    below = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return (below + 0.5 * equal) / len(values) * 100


def nonfinancial_equities_gdp_series(
    equities_bundle: Mapping[str, Any],
    gdp_bundle: Mapping[str, Any],
    *,
    percentile_window_quarters: int = PERCENTILE_WINDOW_QUARTERS,
) -> list[dict[str, Any]]:
    """Inner-join exact calendar quarters and calculate the market-value proxy.

    ``NCBEILQ027S`` is converted from millions to billions of dollars before
    division by nominal GDP.  Output dates are calendar quarter ends, while
    each source's original observation date and realtime interval are retained.
    A missing component or zero GDP denominator yields a null proxy; neither is
    coerced to zero or forward-filled.
    """

    if percentile_window_quarters <= 0:
        raise ValueError("percentile_window_quarters must be positive")
    equities = _validated_quarters(
        equities_bundle, expected_series_id=EQUITIES_SERIES_ID
    )
    gdp = _validated_quarters(gdp_bundle, expected_series_id=GDP_SERIES_ID)
    common_quarters = sorted(equities.keys() & gdp.keys())

    output: list[dict[str, Any]] = []
    ratios_by_ordinal: dict[int, float | None] = {}
    for quarter in common_quarters:
        ordinal = _quarter_ordinal(quarter)
        equity_millions = equities[quarter]["value"]
        gdp_billions = gdp[quarter]["value"]
        equity_billions = (
            equity_millions / 1_000 if equity_millions is not None else None
        )
        if equity_billions is not None and equity_billions < 0:
            raise CollectorError("nonfinancial corporate equities cannot be negative")
        if gdp_billions is not None and gdp_billions < 0:
            raise CollectorError("nominal GDP cannot be negative")
        ratio = (
            equity_billions / gdp_billions * 100
            if equity_billions is not None
            and gdp_billions is not None
            and gdp_billions != 0
            else None
        )
        ratios_by_ordinal[ordinal] = ratio
        previous_quarter = ratios_by_ordinal.get(ordinal - 1)
        previous_year = ratios_by_ordinal.get(ordinal - 4)
        trailing = [
            value
            for candidate_ordinal, value in ratios_by_ordinal.items()
            if ordinal - percentile_window_quarters + 1 <= candidate_ordinal <= ordinal
            and value is not None
        ]
        output.append(
            {
                "date": _quarter_end(quarter),
                "quarter": f"{quarter[0]}-Q{quarter[1]}",
                "value": round(ratio, 6) if ratio is not None else None,
                "equity_usd_bn": (
                    round(equity_billions, 6) if equity_billions is not None else None
                ),
                "gdp_usd_bn": (
                    round(gdp_billions, 6) if gdp_billions is not None else None
                ),
                "change_1_quarter_pp": (
                    round(ratio - previous_quarter, 6)
                    if ratio is not None and previous_quarter is not None
                    else None
                ),
                "qoq_percent_change": (
                    round(change, 6)
                    if (change := _percent_change(ratio, previous_quarter)) is not None
                    else None
                ),
                "yoy_percent_change": (
                    round(change, 6)
                    if (change := _percent_change(ratio, previous_year)) is not None
                    else None
                ),
                "percentile_10y": (
                    round(_midrank(trailing, ratio), 6)
                    if ratio is not None and trailing
                    else None
                ),
                "percentile_10y_sample_size": len(trailing),
                "equities_source_date": equities[quarter]["source_date"],
                "gdp_source_date": gdp[quarter]["source_date"],
                "equities_realtime_start": equities[quarter]["realtime_start"],
                "equities_realtime_end": equities[quarter]["realtime_end"],
                "gdp_realtime_start": gdp[quarter]["realtime_start"],
                "gdp_realtime_end": gdp[quarter]["realtime_end"],
            }
        )
    return output


def nonfinancial_equities_gdp_statistics(
    points: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return latest-quarter statistics without substituting a last-good value."""

    empty = {
        "observation_date": None,
        "quarter": None,
        "ratio_percent": None,
        "equity_usd_bn": None,
        "gdp_usd_bn": None,
        "change_1_quarter_pp": None,
        "qoq_percent_change": None,
        "yoy_percent_change": None,
        "percentile_10y": None,
        "percentile_10y_sample_size": 0,
        "exact_common_quarter_count": 0,
    }
    if not points:
        return empty
    latest = points[-1]
    fields = (
        "date",
        "quarter",
        "value",
        "equity_usd_bn",
        "gdp_usd_bn",
        "change_1_quarter_pp",
        "qoq_percent_change",
        "yoy_percent_change",
        "percentile_10y",
        "percentile_10y_sample_size",
    )
    if any(field not in latest for field in fields):
        raise CollectorError("P2 macro point is missing required statistics")
    return {
        "observation_date": latest["date"],
        "quarter": latest["quarter"],
        "ratio_percent": latest["value"],
        "equity_usd_bn": latest["equity_usd_bn"],
        "gdp_usd_bn": latest["gdp_usd_bn"],
        "change_1_quarter_pp": latest["change_1_quarter_pp"],
        "qoq_percent_change": latest["qoq_percent_change"],
        "yoy_percent_change": latest["yoy_percent_change"],
        "percentile_10y": latest["percentile_10y"],
        "percentile_10y_sample_size": latest["percentile_10y_sample_size"],
        "exact_common_quarter_count": len(points),
    }


def build_nonfinancial_equities_gdp_proxy(
    equities_bundle: Mapping[str, Any],
    gdp_bundle: Mapping[str, Any],
    *,
    percentile_window_quarters: int = PERCENTILE_WINDOW_QUARTERS,
) -> dict[str, Any]:
    """Build the integration bundle consumed by the Release 3 publisher."""

    points = nonfinancial_equities_gdp_series(
        equities_bundle,
        gdp_bundle,
        percentile_window_quarters=percentile_window_quarters,
    )
    latest_statistics = nonfinancial_equities_gdp_statistics(points)
    latest = points[-1] if points else None
    statistics = {
        key: latest_statistics[key]
        for key in (
            "equity_usd_bn",
            "gdp_usd_bn",
            "qoq_percent_change",
            "yoy_percent_change",
            "percentile_10y",
            "percentile_10y_sample_size",
        )
    }
    return {
        "metric_id": METRIC_ID,
        "unit": "percent",
        "frequency": "quarterly",
        "series": points,
        "statistics": statistics,
        "changes": {"one_quarter": latest_statistics["change_1_quarter_pp"]},
        "context": {
            "equity_observation_date": (
                latest["equities_source_date"] if latest is not None else None
            ),
            "gdp_observation_date": (
                latest["gdp_source_date"] if latest is not None else None
            ),
            "common_quarter": latest["quarter"] if latest is not None else None,
        },
        "source_metadata": {
            "equities": {
                "series_id": EQUITIES_SERIES_ID,
                "title": equities_bundle.get("title"),
                "last_updated": equities_bundle.get("last_updated"),
                "units": equities_bundle.get("units"),
                "seasonal_adjustment": equities_bundle.get("seasonal_adjustment"),
            },
            "gdp": {
                "series_id": GDP_SERIES_ID,
                "title": gdp_bundle.get("title"),
                "last_updated": gdp_bundle.get("last_updated"),
                "units": gdp_bundle.get("units"),
                "seasonal_adjustment": gdp_bundle.get("seasonal_adjustment"),
            },
        },
        "caveats": [
            "Proxy context only; it is not a standalone bubble or timing signal.",
            "The numerator is a quarter-end nonfinancial corporate equity stock, while GDP is a seasonally adjusted annual-rate flow.",
            "FRED distributes the series; the underlying government sources are Federal Reserve Z.1 and U.S. BEA.",
            "Recent quarters can be revised; realtime ranges and source observation dates are preserved.",
        ],
    }
