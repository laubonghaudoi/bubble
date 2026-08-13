"""Deterministic schema-2.3 P0 metric interpretation.

This presentation layer is deliberately downstream of the audited alert and
video-formula engines.  It reads their thresholds and outputs descriptive
states, but cannot change an alert, switch, clause, or formula truth value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import ceil, fsum, isfinite
from typing import Any


INTERPRETED_P0_METRIC_IDS = frozenset(
    {
        "sofr",
        "iorb",
        "sofr_iorb_spread_bp",
        "effr",
        "effr_iorb_spread_bp",
        "obfr",
        "obfr_iorb_spread_bp",
        "tgcr",
        "tgcr_iorb_spread_bp",
        "bgcr",
        "bgcr_iorb_spread_bp",
        "tga_daily",
        "on_rrp_accepted",
        "srf_accepted",
        "reserve_balances",
        "fed_total_assets",
        "tga_weekly_h41",
    }
)
ABSOLUTE_RATE_IDS = frozenset({"sofr", "effr", "obfr", "tgcr", "bgcr"})
SPREAD_IDS = frozenset(
    {
        "sofr_iorb_spread_bp",
        "effr_iorb_spread_bp",
        "obfr_iorb_spread_bp",
        "tgcr_iorb_spread_bp",
        "bgcr_iorb_spread_bp",
    }
)
CONFIRMATION_IDS = (
    "effr_iorb_spread_bp",
    "tgcr_iorb_spread_bp",
    "bgcr_iorb_spread_bp",
)

VIDEO = "VIDEO_SOURCE_RULE"
OPERATIONAL = "DASHBOARD_OPERATIONALIZATION"
STATISTICAL = "STATISTICAL_BAND"
CONTEXT = "CONTEXT_ONLY"


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _values(points: Sequence[Mapping[str, Any]]) -> list[float]:
    return [
        number
        for point in points
        if (number := _finite(point.get("value"))) is not None
    ]


def _anchored_observations(
    metric: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """Return history ending at the metric's published endpoint.

    A null or mismatched endpoint must not silently fall back to an older finite
    observation.  LAST_GOOD records are intentionally anchored to their
    published ``observation_date``, so later null collection attempts cannot
    move the statistical endpoint.
    """

    current = _finite(metric.get("value"))
    observation_date = metric.get("observation_date")
    if current is None or not isinstance(observation_date, str):
        return []
    anchored = [
        point
        for point in observations
        if isinstance(point.get("date"), str)
        and str(point["date"]) <= observation_date
    ]
    if not anchored or anchored[-1].get("date") != observation_date:
        return []
    endpoint = _finite(anchored[-1].get("value"))
    if endpoint is None or endpoint != current:
        return []
    return anchored


def nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    """Return the deterministic nearest-rank quantile (ceil(q*n), 1-indexed)."""

    usable = sorted(float(value) for value in values if isfinite(float(value)))
    if not usable:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    rank = max(1, ceil(quantile * len(usable)))
    return usable[rank - 1]


def empirical_percentile(values: Sequence[float], current: float) -> float | None:
    usable = [float(value) for value in values if isfinite(float(value))]
    if not usable:
        return None
    return round(sum(value <= current for value in usable) / len(usable), 6)


def expanding_level_context(
    observations: Sequence[Mapping[str, Any]],
    *,
    minimum_samples: int,
    quantiles: Sequence[float],
) -> dict[str, Any]:
    """Rank the endpoint against prior levels only; the endpoint never self-ranks."""

    current = _finite(observations[-1].get("value")) if observations else None
    history = _values(observations[:-1])
    sufficient = current is not None and len(history) >= minimum_samples
    return {
        "value": current,
        "sample_size": len(history),
        "percentile": (
            empirical_percentile(history, current) if sufficient and current is not None else None
        ),
        "thresholds": {
            quantile: nearest_rank(history, quantile) if sufficient else None
            for quantile in quantiles
        },
    }


def expanding_change_context(
    observations: Sequence[Mapping[str, Any]],
    *,
    lag: int,
    minimum_samples: int,
    quantiles: Sequence[float],
) -> dict[str, Any]:
    """Rank the endpoint change against prior change endpoints without look-ahead."""

    if lag <= 0:
        raise ValueError("lag must be positive")
    values = _values(observations)
    changes = [
        values[index] - values[index - lag]
        for index in range(lag, len(values))
        if values[index] is not None and values[index - lag] is not None
    ]
    current = (
        values[-1] - values[-1 - lag]
        if len(values) > lag
        and values[-1] is not None
        and values[-1 - lag] is not None
        else None
    )
    history = changes[:-1]
    sufficient = current is not None and len(history) >= minimum_samples
    return {
        "value": round(current, 6) if current is not None else None,
        "sample_size": len(history),
        "percentile": (
            empirical_percentile(history, current) if sufficient and current is not None else None
        ),
        "thresholds": {
            quantile: (
                round(threshold, 6)
                if sufficient and (threshold := nearest_rank(history, quantile)) is not None
                else None
            )
            for quantile in quantiles
        },
    }


def _slope(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    x_mean = (len(values) - 1) / 2
    y_mean = fsum(values) / len(values)
    denominator = fsum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    return round(
        fsum(
            (index - x_mean) * (value - y_mean)
            for index, value in enumerate(values)
        )
        / denominator,
        6,
    )


def _numeric_direction(
    metric: Mapping[str, Any], direction_window: str
) -> tuple[str, float | None]:
    changes = metric.get("changes")
    if not isinstance(changes, Mapping):
        return "UNKNOWN", None
    change_field = {
        "ONE_OBSERVATION": "one_observation",
        "FIVE_OBSERVATIONS": "five_observations",
        "FOUR_WEEKS": "four_weeks",
    }.get(direction_window)
    if change_field is None:
        raise ValueError(f"unsupported direction window: {direction_window}")
    change = _finite(changes.get(change_field))
    if change is None:
        return "UNKNOWN", None
    if change > 0:
        return "RISING", change
    if change < 0:
        return "FALLING", change
    return "FLAT", change


def _data_state(metric: Mapping[str, Any]) -> str:
    if _finite(metric.get("value")) is None:
        return "UNKNOWN"
    quality = metric.get("quality")
    status = quality.get("status") if isinstance(quality, Mapping) else None
    freshness = quality.get("freshness") if isinstance(quality, Mapping) else None
    if freshness == "STALE" or status == "STALE":
        return "STALE"
    if status == "OK" and freshness == "FRESH":
        return "CURRENT"
    if status == "ERROR":
        return "UNKNOWN"
    if status == "NOT_RELEASED_YET" or (
        status == "OK" and freshness == "LATE"
    ):
        return "LAST_GOOD"
    return "UNKNOWN"


def _confidence(metric: Mapping[str, Any]) -> str:
    context = metric.get("context")
    value = context.get("confidence") if isinstance(context, Mapping) else None
    return value if value in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"} else "UNKNOWN"


def _impact(metric_id: str, direction: str, state: str) -> str:
    if metric_id == "iorb":
        return "POLICY_ANCHOR"
    if direction == "UNKNOWN":
        return "UNKNOWN"
    if metric_id in ABSOLUTE_RATE_IDS or metric_id in {"on_rrp_accepted", "tga_weekly_h41"}:
        return "AMBIGUOUS"
    if metric_id in SPREAD_IDS:
        return {"RISING": "TIGHTENING", "FALLING": "EASING", "FLAT": "NEUTRAL"}[direction]
    if metric_id == "reserve_balances":
        return {"RISING": "EASING", "FALLING": "TIGHTENING", "FLAT": "NEUTRAL"}[direction]
    if metric_id == "tga_daily":
        return {"RISING": "TIGHTENING", "FALLING": "EASING", "FLAT": "NEUTRAL"}[direction]
    if metric_id == "fed_total_assets":
        return {"RISING": "EASING", "FALLING": "TIGHTENING", "FLAT": "NEUTRAL"}[direction]
    if metric_id == "srf_accepted":
        if state == "OPERATIONAL_EXERCISE":
            return "AMBIGUOUS"
        return "TIGHTENING" if state in {"ISOLATED_USE", "PERSISTENT_USE"} else "NEUTRAL"
    return "UNKNOWN"


def _base(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    *,
    state: str,
    severity: str,
    headline: str,
    reasons: Sequence[str],
    views: Sequence[Mapping[str, Any]],
    context_only: bool = False,
    next_boundary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metric_id = str(metric["metric_id"])
    direction, _ = _numeric_direction(metric, str(rule["direction_window"]))
    rendered_views = [dict(view) for view in views]
    bases: list[str] = [CONTEXT] if context_only else []

    def add_basis(value: Any) -> None:
        if isinstance(value, str) and value not in bases:
            bases.append(value)

    for view in rendered_views:
        if view.get("kind") == "REGIME_LADDER":
            rows = view.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, Mapping):
                        add_basis(row.get("basis"))
        else:
            add_basis(view.get("basis"))
    if next_boundary is not None:
        add_basis(next_boundary.get("basis"))
    if not bases:
        raise ValueError(f"{metric_id} interpretation exposes no rule basis")
    return {
        "role": rule["role"],
        "classification_type": rule["classification_type"],
        "data_state": _data_state(metric),
        "numeric_direction": direction,
        "impact": _impact(metric_id, direction, state),
        "state": state,
        "severity": severity,
        "confidence": _confidence(metric),
        "headline": headline,
        "what_it_measures": rule["what_it_measures"],
        "current_reasons": list(reasons),
        "next_boundary": dict(next_boundary) if next_boundary is not None else None,
        "views": rendered_views,
        "confirm_with": list(rule["confirm_with"]),
        "cannot_infer": rule["cannot_infer"],
        "rule_basis": bases,
    }


def _directional_view(
    rule: Mapping[str, Any], metric: Mapping[str, Any], state: str
) -> dict[str, Any]:
    direction, change = _numeric_direction(metric, str(rule["direction_window"]))
    return {
        "kind": "DIRECTIONAL",
        "label": "DIRECTIONAL READ",
        "value": _finite(metric.get("value")),
        "change": change,
        "unit": str(metric["unit"]),
        "state": state if state else direction,
        "basis": CONTEXT,
    }


def _absolute_rate(rule: Mapping[str, Any], metric: Mapping[str, Any]) -> dict[str, Any]:
    metric_id = str(metric["metric_id"])
    value = _finite(metric.get("value"))
    state = "POLICY_ANCHOR" if metric_id == "iorb" else "NO_STANDALONE_RISK_BAND"
    reasons = [
        "最新數據暫時不可用。" if value is None else f"最新值為 {value:g} {metric['unit']}。",
        "絕對利率水平主要受政策錨影響；請配合相對 IORB 利差。",
    ]
    headline = (
        "最新數據不足，未能作方向判讀。"
        if value is None
        else "IORB 係政策錨，唔係獨立危險訊號。"
        if metric_id == "iorb"
        else "絕對利率冇獨立風險帶；資金壓力要睇相對 IORB 利差。"
    )
    return _base(
        rule,
        metric,
        state=state,
        severity="UNKNOWN" if value is None else "CONTEXT_ONLY",
        headline=headline,
        reasons=reasons,
        views=[_directional_view(rule, metric, state)],
        context_only=True,
    )


def _confirmation_context(
    metric: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    statistics: Mapping[str, Any],
) -> dict[str, Any]:
    minimum = int(statistics["daily_min_history_samples"])
    q80 = float(statistics["confirmation_elevated_quantile"])
    q95 = float(statistics["confirmation_extreme_quantile"])
    context = expanding_level_context(
        observations, minimum_samples=minimum, quantiles=(q80, q95)
    )
    window = int(statistics["confirmation_slope_observations"])
    recent = _values(observations)[-window:]
    slope = _slope(recent) if len(recent) == window else None
    percentile = context["percentile"]
    threshold80 = context["thresholds"].get(q80)
    threshold95 = context["thresholds"].get(q95)
    current = context["value"]
    if context["value"] is None:
        state = "UNKNOWN"
    elif threshold80 is None or threshold95 is None:
        state = "INSUFFICIENT_HISTORY"
    elif current >= threshold95:
        state = "EXTREME"
    elif current >= threshold80:
        state = "ELEVATED"
    else:
        state = "ORDINARY"
    confirming = (
        None
        if threshold80 is None or slope is None
        else current >= threshold80 and slope > 0
    )
    return {**context, "state": state, "slope": slope, "confirming": confirming}


def _percentile_view(
    *,
    label: str,
    context: Mapping[str, Any],
    unit: str,
    basis: str = STATISTICAL,
) -> dict[str, Any]:
    return {
        "kind": "PERCENTILE_GAUGE",
        "label": label,
        "value": context.get("value"),
        "unit": unit,
        "percentile": context.get("percentile"),
        "sample_size": int(context.get("sample_size", 0)),
        "state": str(context["state"]),
        "slope": context.get("slope"),
        "slope_unit": f"{unit}/observation",
        "basis": basis,
    }


def _confirmation(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    statistics: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    context = _confirmation_context(metric, observations, statistics)
    state = str(context["state"])
    confirming = context["confirming"]
    reasons = [
        f"歷史樣本 {context['sample_size']}；最低要求 {statistics['daily_min_history_samples']}。",
        "百分位同最近五期 slope 只作跨市場確認，唔會改變 alert。",
    ]
    headline = (
        "最新利差不可用。"
        if context["value"] is None
        else "歷史樣本不足，唔會補零或者外推百分位。"
        if context["percentile"] is None
        else "利差同近期 slope 同時提供確認。"
        if confirming
        else "未同時滿足 p80 同向上 slope 嘅確認條件。"
    )
    result = _base(
        rule,
        metric,
        state=state,
        severity="UNKNOWN" if context["value"] is None else "WATCH" if confirming else "NORMAL",
        headline=headline,
        reasons=reasons,
        views=[
            _percentile_view(
                label="EXPANDING PRIOR-HISTORY BAND",
                context=context,
                unit=str(metric["unit"]),
            )
        ],
    )
    return result, context


def _breadth_view(contexts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    members = []
    count = 0
    complete = True
    for metric_id in CONFIRMATION_IDS:
        context = contexts[metric_id]
        confirming = context["confirming"]
        complete = complete and confirming is not None
        count += int(confirming is True)
        members.append(
            {
                "metric_id": metric_id,
                "state": str(context["state"]),
                "percentile": context["percentile"],
                "slope": context["slope"],
                "confirming": confirming,
            }
        )
    state = (
        "INSUFFICIENT_HISTORY"
        if not complete
        else ("NO_CONFIRMATION", "ISOLATED", "BROADENING", "BROAD_FUNDING_PRESSURE")[count]
    )
    return {
        "kind": "BREADTH_COUNTER",
        "label": "EFFR / TGCR / BGCR CONFIRMATION",
        "count": count if complete else None,
        "total": 3,
        "state": state,
        "members": members,
        "basis": STATISTICAL,
    }


def _sofr_spread(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    *,
    video_config: Mapping[str, Any],
    reserve_value: float | None,
    breadth: Mapping[str, Any],
) -> dict[str, Any]:
    yellow = video_config["yellow"]
    red = video_config["red"]
    value = _finite(metric.get("value"))
    statistics = metric.get("statistics") if isinstance(metric.get("statistics"), Mapping) else {}
    streak = statistics.get("positive_streak")
    streak_value = streak if isinstance(streak, int) and not isinstance(streak, bool) else None
    positive_line = float(yellow["spread_positive_bp"])
    streak_required = int(yellow["positive_streak_observations"])
    red_line = float(red["sofr_iorb_bp"])
    reserve_red = float(red["reserve_below_usd_tn"]) * 1_000
    red_leg = value is not None and value > red_line
    full_red = red_leg and reserve_value is not None and reserve_value < reserve_red
    yellow_clause = (
        value is not None
        and streak_value is not None
        and streak_value >= streak_required
    )
    if value is None:
        state, severity = "UNKNOWN", "UNKNOWN"
    elif full_red:
        state, severity = "FULL_RED_ROUTE_A", "RED"
    elif red_leg:
        # The +3bp spread leg is only one input to Route A.  Never promote the
        # interpretation to RED unless the reserve confirmation is also met.
        state = "RED_SPREAD_LEG"
        severity = "YELLOW" if yellow_clause else "WATCH"
    elif yellow_clause:
        state, severity = "YELLOW_CLAUSE_MET", "YELLOW"
    elif value > positive_line:
        state, severity = "POSITIVE_PRINT", "NORMAL"
    else:
        state, severity = "NO_PRICE_PRESSURE", "NORMAL"
    rows = [
        {
            "label": "NO PRICE PRESSURE",
            "operator": "<=",
            "threshold": positive_line,
            "upper_threshold": None,
            "unit": "bp",
            "rule": "spread <= positive line",
            "basis": VIDEO,
            "active": state == "NO_PRICE_PRESSURE",
            "met": None if value is None else value <= positive_line,
        },
        {
            "label": "POSITIVE PRINT",
            "operator": ">",
            "threshold": positive_line,
            "upper_threshold": None,
            "unit": "bp",
            "rule": "spread > positive line",
            "basis": VIDEO,
            "active": state == "POSITIVE_PRINT",
            "met": None if value is None else value > positive_line,
        },
        {
            "label": "YELLOW CLAUSE",
            "operator": ">=",
            "threshold": float(streak_required),
            "upper_threshold": None,
            "unit": "observations",
            "rule": "positive_streak >= required observations",
            "basis": OPERATIONAL,
            "active": state == "YELLOW_CLAUSE_MET",
            "met": None if streak_value is None else streak_value >= streak_required,
        },
        {
            "label": "RED SPREAD LEG",
            "operator": ">",
            "threshold": red_line,
            "upper_threshold": None,
            "unit": "bp",
            "rule": "spread > red line",
            "basis": VIDEO,
            "active": state == "RED_SPREAD_LEG",
            "met": None if value is None else red_leg,
        },
        {
            "label": "FULL RED ROUTE A",
            "operator": (
                f"> {red_line:g} bp AND RESERVES < {reserve_red:,.0f} USD bn"
            ),
            "threshold": None,
            "upper_threshold": None,
            "unit": "route condition",
            "rule": "spread > red line AND reserves < red reserve line",
            "basis": VIDEO,
            "active": state == "FULL_RED_ROUTE_A",
            "met": None if value is None or reserve_value is None else full_red,
        },
    ]
    if value is None:
        boundary = None
    elif value <= positive_line:
        boundary = {
            "label": "POSITIVE PRINT",
            "current": value,
            "threshold": positive_line,
            "distance": round(positive_line - value, 6),
            "unit": "bp",
            "rule": "spread > positive line",
            "basis": VIDEO,
        }
    elif not red_leg:
        boundary = {
            "label": "RED SPREAD LEG",
            "current": value,
            "threshold": red_line,
            "distance": round(max(0.0, red_line - value), 6),
            "unit": "bp",
            "rule": "spread > red line",
            "basis": VIDEO,
        }
    elif not full_red:
        boundary = {
            "label": "FULL RED ROUTE A · RESERVE CONFIRMATION",
            "current": reserve_value,
            "threshold": reserve_red,
            "distance": (
                round(reserve_value - reserve_red, 6)
                if reserve_value is not None
                else None
            ),
            "unit": "USD bn",
            "rule": "reserves < red reserve line",
            "basis": VIDEO,
        }
    else:
        boundary = None
    reasons = [
        "最新利差暫時不可用。" if value is None else f"最新 SOFR−IORB 為 {value:g} bp。",
        f"連續正值期數：{streak_value if streak_value is not None else 'UNKNOWN'}。",
        f"Full Red Route A：{'MET' if full_red else 'NOT MET'}；Red spread leg 唔等於完整 Red route。",
    ]
    headline = {
        "UNKNOWN": "數據不足，唔會推斷為中性。",
        "NO_PRICE_PRESSURE": "Repo cash 暫未貴過 IORB。",
        "POSITIVE_PRINT": "利差已轉正，但未完成持續條件。",
        "YELLOW_CLAUSE_MET": "連續轉正嘅 Yellow clause 已滿足。",
        "RED_SPREAD_LEG": "Red spread leg 已滿足，但完整 Red Route A 未確認。",
        "FULL_RED_ROUTE_A": "價格同 reserve stock 已同時確認 Red Route A。",
    }[state]
    return _base(
        rule,
        metric,
        state=state,
        severity=severity,
        headline=headline,
        reasons=reasons,
        views=[
            {
                "kind": "REGIME_LADDER",
                "label": "SOFR−IORB REGIME LADDER",
                "rows": rows,
                "note": "Red spread leg 同完整 Red Route A 分開顯示。",
            },
            breadth,
        ],
        next_boundary=boundary,
    )


def _reserve(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    *,
    video_config: Mapping[str, Any],
) -> dict[str, Any]:
    value = _finite(metric.get("value"))
    statistics = metric.get("statistics") if isinstance(metric.get("statistics"), Mapping) else {}
    change = _finite(statistics.get("change_4w"))
    p10 = _finite(statistics.get("trailing_5y_p10"))
    sample_size = statistics.get("trailing_sample_size")
    sample_size = sample_size if isinstance(sample_size, int) and not isinstance(sample_size, bool) else 0
    yellow = float(video_config["yellow"]["reserve_below_usd_tn"]) * 1_000
    red = float(video_config["red"]["reserve_below_usd_tn"]) * 1_000
    extreme = float(video_config["extreme"]["reserve_below_usd_tn"]) * 1_000
    if value is None:
        level_state, severity = "UNKNOWN", "UNKNOWN"
    elif value < extreme:
        level_state, severity = "EXTREME_LEVEL_CANDIDATE", "EXTREME"
    elif value < red:
        level_state, severity = "RED_CONFIRMATION_ZONE", "RED"
    elif value < yellow:
        level_state, severity = "VIDEO_YELLOW_ZONE", "YELLOW"
    else:
        level_state, severity = "ABOVE_VIDEO_YELLOW_ZONE", "NORMAL"
    if change is None:
        speed_state = "INSUFFICIENT_HISTORY"
    elif change > 0:
        speed_state = "REPLENISHING"
    elif p10 is None:
        speed_state = "INSUFFICIENT_HISTORY"
    elif change <= p10:
        speed_state = "RAPID_DRAIN"
    else:
        speed_state = "ORDINARY_DRAIN"
    rows = []
    for label, operator, threshold, upper, active in (
        ("ABOVE VIDEO YELLOW ZONE", ">=", yellow, None, level_state == "ABOVE_VIDEO_YELLOW_ZONE"),
        ("VIDEO YELLOW ZONE", ">= AND <", red, yellow, level_state == "VIDEO_YELLOW_ZONE"),
        ("RED CONFIRMATION ZONE", ">= AND <", extreme, red, level_state == "RED_CONFIRMATION_ZONE"),
        ("EXTREME LEVEL CANDIDATE", "<", extreme, None, level_state == "EXTREME_LEVEL_CANDIDATE"),
    ):
        rows.append(
            {
                "label": label,
                "operator": operator,
                "threshold": threshold,
                "upper_threshold": upper,
                "unit": "USD bn",
                "rule": label.lower().replace(" ", "_"),
                "basis": VIDEO,
                "active": active,
                "met": None if value is None else active,
            }
        )
    if value is None or value < extreme:
        boundary = None
    else:
        target = yellow if value >= yellow else red if value >= red else extreme
        label = "VIDEO YELLOW ZONE" if target == yellow else "RED CONFIRMATION ZONE" if target == red else "EXTREME LEVEL CANDIDATE"
        boundary = {
            "label": label,
            "current": value,
            "threshold": target,
            "distance": round(value - target, 6),
            "unit": "USD bn",
            "rule": "reserve level falls below next source line",
            "basis": VIDEO,
        }
    speed_rows = [
        {
            "label": "REPLENISHING",
            "operator": ">",
            "threshold": 0.0,
            "upper_threshold": None,
            "unit": "USD bn",
            "rule": "4W reserve change > 0",
            "basis": OPERATIONAL,
            "active": speed_state == "REPLENISHING",
            "met": None if change is None else change > 0,
        },
        {
            "label": "ORDINARY DRAIN",
            "operator": "> p10 AND <=",
            "threshold": p10,
            "upper_threshold": 0.0,
            "unit": "USD bn",
            "rule": "trailing-5Y p10 < 4W reserve change <= 0",
            "basis": STATISTICAL,
            "active": speed_state == "ORDINARY_DRAIN",
            "met": (
                None
                if change is None or p10 is None
                else p10 < change <= 0
            ),
        },
        {
            "label": "RAPID DRAIN",
            "operator": "<=",
            "threshold": p10,
            "upper_threshold": None,
            "unit": "USD bn",
            "rule": "4W reserve change <= trailing-5Y p10",
            "basis": STATISTICAL,
            "active": speed_state == "RAPID_DRAIN",
            "met": (
                None
                if change is None or p10 is None
                else change <= p10
            ),
        },
    ]
    return _base(
        rule,
        metric,
        state=f"{level_state} · {speed_state}",
        severity=severity,
        headline=(
            "Reserve 數據不足。"
            if value is None
            else f"Reserve level 為 {level_state}；4W speed 為 {speed_state}。"
        ),
        reasons=[
            "最新 reserve level 暫時不可用。" if value is None else f"最新 level 為 {value:g} USD bn。",
            f"4W change：{change if change is not None else 'UNKNOWN'} USD bn；既有 trailing-5Y p10：{p10 if p10 is not None else 'UNKNOWN'}。",
        ],
        views=[
            {
                "kind": "REGIME_LADDER",
                "label": "VIDEO RESERVE LEVEL ZONES",
                "rows": rows,
                "note": "影片門檻唔係 Fed 官方跨時期危機線。",
            },
            {
                "kind": "REGIME_LADDER",
                "label": "4W RESERVE SPEED",
                "rows": speed_rows,
                "note": (
                    f"Trailing-5Y p10 uses {sample_size} change endpoints; "
                    "the source level zones remain separate."
                ),
            },
        ],
        next_boundary=boundary,
    )


def _tga_flow_state(context: Mapping[str, Any], q75: float, q90: float) -> str:
    value = context["value"]
    thresholds = context["thresholds"]
    threshold75 = thresholds.get(q75)
    threshold90 = thresholds.get(q90)
    if value is None:
        return "UNKNOWN"
    if value <= 0:
        return "LIQUIDITY_RELEASE"
    if threshold75 is None or threshold90 is None:
        return "INSUFFICIENT_HISTORY"
    if value >= threshold90:
        return "LARGE_DRAIN"
    if value >= threshold75:
        return "NOTABLE_DRAIN"
    return "MILD_DRAIN"


def _tga(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    video_config: Mapping[str, Any],
    statistics: Mapping[str, Any],
) -> dict[str, Any]:
    minimum = int(statistics["daily_min_history_samples"])
    q75 = float(statistics["tga_notable_quantile"])
    q90 = float(statistics["tga_large_quantile"])
    flow5 = expanding_change_context(
        observations,
        lag=int(statistics["tga_short_change_observations"]),
        minimum_samples=minimum,
        quantiles=(q75, q90),
    )
    flow20 = expanding_change_context(
        observations,
        lag=int(statistics["tga_long_change_observations"]),
        minimum_samples=minimum,
        quantiles=(q75, q90),
    )
    flow5["state"] = _tga_flow_state(flow5, q75, q90)
    flow20["state"] = _tga_flow_state(flow20, q75, q90)
    flow5["slope"] = None
    flow20["slope"] = None
    context = metric.get("context") if isinstance(metric.get("context"), Mapping) else {}
    flags = context.get("technical_flags") if isinstance(context.get("technical_flags"), list) else []
    technical = any(
        flag == "TAX_WINDOW" or "SETTLEMENT" in str(flag) for flag in flags
    )
    rank = {
        "UNKNOWN": -1,
        "LIQUIDITY_RELEASE": 0,
        "INSUFFICIENT_HISTORY": 1,
        "MILD_DRAIN": 2,
        "NOTABLE_DRAIN": 3,
        "LARGE_DRAIN": 4,
    }
    state = max((str(flow5["state"]), str(flow20["state"])), key=rank.__getitem__)
    if technical and state in {"MILD_DRAIN", "NOTABLE_DRAIN", "LARGE_DRAIN"}:
        state = f"{state}_TECHNICAL_DRAIN"
        flow5["state"] = f"{flow5['state']}_TECHNICAL_DRAIN" if flow5["state"] not in {"LIQUIDITY_RELEASE", "INSUFFICIENT_HISTORY", "UNKNOWN"} else flow5["state"]
        flow20["state"] = f"{flow20['state']}_TECHNICAL_DRAIN" if flow20["state"] not in {"LIQUIDITY_RELEASE", "INSUFFICIENT_HISTORY", "UNKNOWN"} else flow20["state"]
    value = _finite(metric.get("value"))
    floor = float(video_config["yellow"]["tga_near_1t_floor_usd_tn"]) * 1_000
    target = float(video_config["yellow"]["tga_source_target_usd_tn"]) * 1_000
    level_state = "UNKNOWN" if value is None else "BELOW_VIDEO_PROXIMITY_ZONE" if value < floor else "APPROACHING_1T" if value < target else "ABOVE_VIDEO_TARGET"
    level_rows = [
        {
            "label": "BELOW VIDEO PROXIMITY ZONE",
            "operator": "<",
            "threshold": floor,
            "upper_threshold": None,
            "unit": "USD bn",
            "rule": "TGA < source operational floor",
            "basis": OPERATIONAL,
            "active": level_state == "BELOW_VIDEO_PROXIMITY_ZONE",
            "met": None if value is None else value < floor,
        },
        {
            "label": "APPROACHING 1T",
            "operator": ">= AND <",
            "threshold": floor,
            "upper_threshold": target,
            "unit": "USD bn",
            "rule": "source proximity floor <= TGA < source target",
            "basis": OPERATIONAL,
            "active": level_state == "APPROACHING_1T",
            "met": None if value is None else floor <= value < target,
        },
        {
            "label": "ABOVE VIDEO TARGET",
            "operator": ">=",
            "threshold": target,
            "upper_threshold": None,
            "unit": "USD bn",
            "rule": "TGA >= source target",
            "basis": VIDEO,
            "active": level_state == "ABOVE_VIDEO_TARGET",
            "met": None if value is None else value >= target,
        },
    ]
    boundary = None if value is None or value >= target else {
        "label": "APPROACHING 1T" if value < floor else "ABOVE VIDEO TARGET",
        "current": value,
        "threshold": floor if value < floor else target,
        "distance": round((floor if value < floor else target) - value, 6),
        "unit": "USD bn",
        "rule": "TGA rises into next source context zone",
        "basis": OPERATIONAL if value < floor else VIDEO,
    }
    return _base(
        rule,
        metric,
        state=f"{level_state} · {state}",
        severity="UNKNOWN" if value is None else "CONTEXT_ONLY",
        headline=(
            "TGA 數據不足。"
            if value is None
            else f"TGA level 為 {level_state}；整體 flow 為 {state}。"
        ),
        reasons=[
            f"5-observation flow：{flow5['value'] if flow5['value'] is not None else 'UNKNOWN'} USD bn。",
            f"20-observation flow：{flow20['value'] if flow20['value'] is not None else 'UNKNOWN'} USD bn。",
            "稅期／settlement context 只改名為 TECHNICAL DRAIN，絕不叫 STRESS。" if technical else "今期無 tax／settlement technical suffix。",
        ],
        views=[
            _percentile_view(label="5-OBSERVATION FLOW", context=flow5, unit="USD bn"),
            _percentile_view(label="20-OBSERVATION FLOW", context=flow20, unit="USD bn"),
            {
                "kind": "REGIME_LADDER",
                "label": "VIDEO TGA LEVEL CONTEXT",
                "rows": level_rows,
                "note": "Level 只係影片 context；真正 liquidity impact 主要睇 flow。",
            },
        ],
        context_only=True,
        next_boundary=boundary,
    )


def _on_rrp(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    statistics: Mapping[str, Any],
) -> dict[str, Any]:
    window = int(statistics["on_rrp_history_observations"])
    minimum = int(statistics["on_rrp_min_history_samples"])
    q10 = float(statistics["on_rrp_near_floor_quantile"])
    value = _finite(observations[-1].get("value")) if observations else None
    prior = _values(observations[:-1])[-window:]
    sufficient = value is not None and len(prior) >= minimum
    percentile = empirical_percentile(prior, value) if sufficient else None
    threshold = nearest_rank(prior, q10) if sufficient else None
    recent = _values(observations)[-6:]
    slope = _slope(recent) if len(recent) >= 2 else None
    direction, _ = _numeric_direction(metric, str(rule["direction_window"]))
    if value is None:
        state = "UNKNOWN"
    elif value == 0:
        state = "AT_FLOOR"
    elif threshold is None:
        state = "INSUFFICIENT_HISTORY"
    elif value <= threshold:
        state = "NEAR_FLOOR"
    elif direction == "FALLING":
        state = "DEPLETING_BUFFER"
    else:
        state = "AVAILABLE_BUFFER"
    context = {
        "value": value,
        "percentile": percentile,
        "sample_size": len(prior),
        "state": state,
        "slope": slope,
    }
    return _base(
        rule,
        metric,
        state=state,
        severity="UNKNOWN" if value is None else "CONTEXT_ONLY",
        headline=(
            "ON RRP 數據不足。"
            if value is None
            else f"ON RRP buffer 狀態：{state}。"
        ),
        reasons=[
            f"只使用 endpoint 之前最多 {window} 個觀察；樣本為 {len(prior)}。",
            "ON RRP 只係緩衝 context，下降亦可能反映相對回報改變。",
        ],
        views=[
            _percentile_view(
                label="PRIOR-20 BUFFER POSITION",
                context=context,
                unit=str(metric["unit"]),
                basis=STATISTICAL,
            )
        ],
        context_only=True,
    )


def _srf(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    video_config: Mapping[str, Any],
) -> dict[str, Any]:
    window = int(video_config["red"]["srf_window_completed_operation_days"])
    required = int(video_config["red"]["srf_positive_days_latest_3"])
    latest = list(observations)[-window:]
    classified = len(latest) >= window and all(point.get("classification_complete") is True for point in latest)
    count = (
        sum((_finite(point.get("alert_eligible_accepted_amount_usd_bn")) or 0) > 0 for point in latest)
        if classified
        else None
    )
    current_technical = bool(latest and latest[-1].get("technical_exercise") is True)
    if _finite(metric.get("value")) is None or count is None:
        state, severity = "UNKNOWN", "UNKNOWN"
    elif count >= required:
        state, severity = "PERSISTENT_USE", "RED"
    elif current_technical and count == 0:
        state, severity = "OPERATIONAL_EXERCISE", "NORMAL"
    elif count == 1:
        state, severity = "ISOLATED_USE", "NORMAL"
    else:
        state, severity = "DORMANT", "NORMAL"
    return _base(
        rule,
        metric,
        state=state,
        severity=severity,
        headline=(
            "SRF operation-day evidence 未齊。"
            if count is None
            else "最新 completed day 只係 operational exercise，已排除警報。"
            if state == "OPERATIONAL_EXERCISE"
            else f"最近 {window} 個 completed days 有 {count} 日非技術性使用。"
        ),
        reasons=[
            f"非技術性 positive days：{count if count is not None else 'UNKNOWN'} / {window}。",
            "Technical exercise 保留數據但排除 Red Route B。",
        ],
        views=[
            {
                "kind": "EVENT_STEPPER",
                "label": "LATEST COMPLETED OPERATION DAYS",
                "window_size": window,
                "positive_count": count,
                "required_count": required,
                "state": state,
                "technical_exercise": current_technical,
                "basis": OPERATIONAL,
            }
        ],
    )


def _fed_assets(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    statistics: Mapping[str, Any],
) -> dict[str, Any]:
    q25 = float(statistics["fed_assets_lower_quantile"])
    q75 = float(statistics["fed_assets_upper_quantile"])
    context = expanding_change_context(
        observations,
        lag=int(statistics["fed_assets_change_observations"]),
        minimum_samples=int(statistics["weekly_min_history_samples"]),
        quantiles=(q25, q75),
    )
    value = context["value"]
    lower = context["thresholds"].get(q25)
    upper = context["thresholds"].get(q75)
    if value is None:
        state = "UNKNOWN"
    elif lower is None or upper is None:
        state = "INSUFFICIENT_HISTORY"
    elif value < lower:
        state = "CONTRACTING"
    elif value > upper:
        state = "EXPANDING"
    else:
        state = "BROADLY_FLAT"
    context["state"] = state
    context["slope"] = None
    return _base(
        rule,
        metric,
        state=state,
        severity="UNKNOWN" if value is None else "CONTEXT_ONLY",
        headline=(
            "Fed assets 4W impulse 暫不可用。"
            if value is None
            else f"Fed assets 4W impulse 狀態：{state}。"
        ),
        reasons=[
            f"4W impulse：{value if value is not None else 'UNKNOWN'} USD bn。",
            f"Expanding prior impulses：{context['sample_size']}；最低要求 {statistics['weekly_min_history_samples']}。",
        ],
        views=[_percentile_view(label="4W ASSET IMPULSE", context=context, unit="USD bn")],
        context_only=True,
    )


def _cross_check_context(
    weekly: Sequence[Mapping[str, Any]],
    daily: Sequence[Mapping[str, Any]],
    *,
    minimum_samples: int,
    q80: float,
    q95: float,
) -> dict[str, Any]:
    daily_by_date = {
        str(point.get("date")): number
        for point in daily
        if isinstance(point.get("date"), str)
        and (number := _finite(point.get("value"))) is not None
    }
    pairs = [
        (str(point["date"]), abs(float(point["value"]) - daily_by_date[str(point["date"])]))
        for point in weekly
        if isinstance(point.get("date"), str)
        and _finite(point.get("value")) is not None
        and str(point["date"]) in daily_by_date
    ]
    weekly_endpoint = (
        str(weekly[-1].get("date"))
        if weekly and isinstance(weekly[-1].get("date"), str)
        else None
    )
    current = pairs[-1] if pairs and pairs[-1][0] == weekly_endpoint else None
    history = [
        difference
        for paired_date, difference in pairs
        if weekly_endpoint is None or paired_date < weekly_endpoint
    ]
    sufficient = current is not None and len(history) >= minimum_samples
    percentile = empirical_percentile(history, current[1]) if sufficient and current else None
    threshold80 = nearest_rank(history, q80) if sufficient else None
    threshold95 = nearest_rank(history, q95) if sufficient else None
    if current is None:
        state = "NOT_RELEASED"
    elif threshold80 is None or threshold95 is None:
        state = "INSUFFICIENT_HISTORY"
    elif current[1] <= threshold80:
        state = "ALIGNED"
    elif current[1] <= threshold95:
        state = "TIMING_DIFFERENCE"
    else:
        state = "MATERIAL_DIVERGENCE"
    return {
        "paired_date": current[0] if current else None,
        "difference": round(current[1], 6) if current else None,
        "percentile": percentile,
        "sample_size": len(history),
        "state": state,
    }


def _cross_check(
    rule: Mapping[str, Any],
    metric: Mapping[str, Any],
    weekly: Sequence[Mapping[str, Any]],
    daily: Sequence[Mapping[str, Any]],
    statistics: Mapping[str, Any],
) -> dict[str, Any]:
    context = _cross_check_context(
        weekly,
        daily,
        minimum_samples=int(statistics["weekly_min_history_samples"]),
        q80=float(statistics["cross_check_aligned_quantile"]),
        q95=float(statistics["cross_check_material_quantile"]),
    )
    state = str(context["state"])
    return _base(
        rule,
        metric,
        state=state,
        severity="UNKNOWN" if state == "NOT_RELEASED" else "CONTEXT_ONLY",
        headline=(
            "Weekly H.4.1 同 daily TGA 暫無同日配對。"
            if state == "NOT_RELEASED"
            else f"Weekly/daily TGA cross-check：{state}。"
        ),
        reasons=[
            f"同日 absolute difference：{context['difference'] if context['difference'] is not None else 'UNKNOWN'} USD bn。",
            f"Prior common-date sample：{context['sample_size']}；只作 cross-check。",
        ],
        views=[
            {
                "kind": "CROSS_CHECK",
                "label": "H.4.1 / FISCALDATA COMMON-DATE CHECK",
                "primary_metric_id": "tga_weekly_h41",
                "comparison_metric_id": "tga_daily",
                "difference": context["difference"],
                "unit": "USD bn",
                "percentile": context["percentile"],
                "sample_size": context["sample_size"],
                "state": state,
                "basis": STATISTICAL,
            }
        ],
        context_only=True,
    )


def build_metric_interpretations(
    *,
    metric_records: Mapping[str, Mapping[str, Any]],
    series_by_id: Mapping[str, Sequence[Mapping[str, Any]]],
    rules: Mapping[str, Any],
    alert_rules: Mapping[str, Any],
) -> dict[str, dict[str, Any] | None]:
    """Return explicit interpretation values for every snapshot metric."""

    configured = {
        str(item["metric_id"]): item for item in rules["metrics"]
    }
    statistics = rules["statistics"]
    video_config = alert_rules["alerts"]["video_p0_model"]
    output: dict[str, dict[str, Any] | None] = {
        metric_id: None for metric_id in metric_records
    }

    confirmation_contexts: dict[str, dict[str, Any]] = {}
    for metric_id in ("effr_iorb_spread_bp", "obfr_iorb_spread_bp", "tgcr_iorb_spread_bp", "bgcr_iorb_spread_bp"):
        observations = _anchored_observations(
            metric_records[metric_id], series_by_id.get(metric_id, ())
        )
        result, context = _confirmation(
            configured[metric_id],
            metric_records[metric_id],
            observations,
            statistics,
        )
        output[metric_id] = result
        confirmation_contexts[metric_id] = context

    output["sofr_iorb_spread_bp"] = _sofr_spread(
        configured["sofr_iorb_spread_bp"],
        metric_records["sofr_iorb_spread_bp"],
        video_config=video_config,
        reserve_value=_finite(metric_records["reserve_balances"].get("value")),
        breadth=_breadth_view(confirmation_contexts),
    )
    for metric_id in (*ABSOLUTE_RATE_IDS, "iorb"):
        output[metric_id] = _absolute_rate(
            configured[metric_id], metric_records[metric_id]
        )
    output["reserve_balances"] = _reserve(
        configured["reserve_balances"],
        metric_records["reserve_balances"],
        video_config=video_config,
    )
    output["tga_daily"] = _tga(
        configured["tga_daily"],
        metric_records["tga_daily"],
        _anchored_observations(
            metric_records["tga_daily"], series_by_id.get("tga_daily", ())
        ),
        video_config=video_config,
        statistics=statistics,
    )
    output["on_rrp_accepted"] = _on_rrp(
        configured["on_rrp_accepted"],
        metric_records["on_rrp_accepted"],
        _anchored_observations(
            metric_records["on_rrp_accepted"],
            series_by_id.get("on_rrp_accepted", ()),
        ),
        statistics,
    )
    output["srf_accepted"] = _srf(
        configured["srf_accepted"],
        metric_records["srf_accepted"],
        _anchored_observations(
            metric_records["srf_accepted"], series_by_id.get("srf_accepted", ())
        ),
        video_config=video_config,
    )
    output["fed_total_assets"] = _fed_assets(
        configured["fed_total_assets"],
        metric_records["fed_total_assets"],
        _anchored_observations(
            metric_records["fed_total_assets"],
            series_by_id.get("fed_total_assets", ()),
        ),
        statistics,
    )
    output["tga_weekly_h41"] = _cross_check(
        configured["tga_weekly_h41"],
        metric_records["tga_weekly_h41"],
        _anchored_observations(
            metric_records["tga_weekly_h41"],
            series_by_id.get("tga_weekly_h41", ()),
        ),
        series_by_id.get("tga_daily", ()),
        statistics,
    )
    for metric_id in INTERPRETED_P0_METRIC_IDS:
        interpretation = output.get(metric_id)
        if interpretation is None:
            raise ValueError(f"missing interpretation for {metric_id}")
        actual_kind = interpretation["views"][0]["kind"]
        expected_kind = configured[metric_id]["primary_view"]
        if actual_kind != expected_kind:
            raise ValueError(
                f"{metric_id} primary view {actual_kind} does not match config {expected_kind}"
            )
    return output


__all__ = [
    "INTERPRETED_P0_METRIC_IDS",
    "build_metric_interpretations",
    "empirical_percentile",
    "expanding_change_context",
    "expanding_level_context",
    "nearest_rank",
]
