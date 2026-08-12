"""Deterministic P0 liquidity alert and quality rules."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from math import isfinite
from typing import Any


CONFIRMATION_SPREAD_IDS = frozenset({"effr", "tgcr", "bgcr"})

_STATUS_SEVERITY = {
    "OK": 0,
    "NOT_RELEASED_YET": 1,
    "STALE": 2,
    "UNAVAILABLE": 3,
    "MISSING": 4,
    "ERROR": 5,
}
_STATUS_ALIASES = {
    "NOT_RELEASED": "NOT_RELEASED_YET",
    "NOT_RELEASED_YET": "NOT_RELEASED_YET",
}
_CONFIDENCE_LEVELS = ("LOW", "MEDIUM", "HIGH")


def _canonical_status(status: str) -> str:
    if not isinstance(status, str):
        raise ValueError("input status must be a string")
    canonical = status.strip().upper()
    canonical = _STATUS_ALIASES.get(canonical, canonical)
    if canonical not in _STATUS_SEVERITY:
        raise ValueError(f"unsupported input status: {status}")
    return canonical


def weakest_input_status(statuses: Iterable[str]) -> str:
    """Propagate the weakest runtime status, failing on an empty input list."""

    canonical = [_canonical_status(status) for status in statuses]
    if not canonical:
        raise ValueError("at least one input status is required")
    return max(canonical, key=_STATUS_SEVERITY.__getitem__)


def downgrade_confidence(confidence: str, *, steps: int = 1) -> str:
    """Downgrade an ordered HIGH/MEDIUM/LOW confidence without underflow."""

    canonical = confidence.strip().upper() if isinstance(confidence, str) else ""
    if canonical not in _CONFIDENCE_LEVELS:
        raise ValueError(f"unsupported confidence: {confidence}")
    if steps < 0:
        raise ValueError("steps cannot be negative")
    index = _CONFIDENCE_LEVELS.index(canonical)
    return _CONFIDENCE_LEVELS[max(0, index - steps)]


def liquidity_alert_rule(
    *,
    latest_sofr_iorb_bp: float | None,
    positive_streak: int,
    funding_confirmation_stats: Mapping[str, Mapping[str, float | int | None]],
    srf_recent_operation_days: Sequence[Mapping[str, Any]],
    reserve_change_4w: float | None,
    reserve_trailing_5y_p10: float | None,
    technical_flags: Sequence[str] = (),
    input_statuses: Sequence[str] = ("OK",),
    base_confidence: str = "HIGH",
    watch_threshold_bp: float = 3.0,
    positive_streak_required: int = 3,
) -> dict[str, Any]:
    """Evaluate exact WATCH/ELEVATED/STRESS rules.

    Rules are deliberately evidence-block based:

    * WATCH: latest SOFR-IORB is above the configured threshold, or the
      positive streak reaches the configured observation count.
    * ELEVATED: WATCH plus at least one independent EFFR/TGCR/BGCR spread
      whose five-observation change and slope are both positive.
    * STRESS: ELEVATED plus non-technical positive SRF use on at least two of
      the latest three operation days, reserve four-week change at or below
      its trailing-five-year p10, or all three confirmation spreads worsening.

    Technical flags downgrade confidence exactly one step and never alter the
    alert level or trigger evidence.
    """

    if positive_streak < 0 or positive_streak_required <= 0:
        raise ValueError("streak inputs must be non-negative and the requirement positive")
    if isinstance(watch_threshold_bp, bool) or not isinstance(watch_threshold_bp, (int, float)) or not isfinite(watch_threshold_bp):
        raise ValueError("watch_threshold_bp must be finite")
    if latest_sofr_iorb_bp is not None and (
        isinstance(latest_sofr_iorb_bp, bool)
        or not isinstance(latest_sofr_iorb_bp, (int, float))
        or not isfinite(latest_sofr_iorb_bp)
    ):
        raise ValueError("latest_sofr_iorb_bp must be finite or null")
    unknown = set(funding_confirmation_stats) - CONFIRMATION_SPREAD_IDS
    if unknown:
        raise ValueError(f"unsupported funding confirmations: {sorted(unknown)}")

    confirmation_ids: list[str] = []
    for metric_id, stats in funding_confirmation_stats.items():
        if not isinstance(stats, Mapping):
            raise ValueError("funding confirmation stats must be mappings")
        change = stats.get("change_5obs")
        slope = stats.get("slope_5obs_bp_per_obs")
        for field, value in (("change_5obs", change), ("slope_5obs_bp_per_obs", slope)):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{field} must be finite or null")
        if change is not None and slope is not None and change > 0 and slope > 0:
            confirmation_ids.append(metric_id)

    quality_status = weakest_input_status(input_statuses)
    confirmation_ids.sort()
    confirmation_count = len(confirmation_ids)
    evaluated = latest_sofr_iorb_bp is not None and quality_status == "OK"
    above_threshold = evaluated and latest_sofr_iorb_bp > watch_threshold_bp
    streak_met = positive_streak >= positive_streak_required
    watch = bool(evaluated and (above_threshold or streak_met))
    elevated = bool(watch and confirmation_count >= 1)

    srf_positive_days = 0
    seen_srf_dates: set[str] = set()
    normalized_srf_days: list[tuple[str, bool]] = []
    for day in srf_recent_operation_days:
        operation_date = day.get("date")
        if not isinstance(operation_date, str):
            raise ValueError("SRF operation day requires an ISO date")
        try:
            canonical_date = date.fromisoformat(operation_date).isoformat()
        except ValueError as error:
            raise ValueError("SRF operation day requires an ISO date") from error
        if canonical_date in seen_srf_dates:
            raise ValueError(f"duplicate SRF operation day: {canonical_date}")
        seen_srf_dates.add(canonical_date)
        amount = day.get("accepted_amount_usd_bn")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not isfinite(amount)
            or amount < 0
        ):
            raise ValueError("SRF accepted amount must be finite and non-negative")
        technical_exercise = day.get("technical_exercise")
        if not isinstance(technical_exercise, bool):
            raise ValueError("SRF operation day requires technical_exercise boolean")
        normalized_srf_days.append((canonical_date, amount > 0 and not technical_exercise))
    for _, positive in sorted(normalized_srf_days)[-3:]:
        srf_positive_days += int(positive)
    srf_persistent = srf_positive_days >= 2

    for name, value in (
        ("reserve_change_4w", reserve_change_4w),
        ("reserve_trailing_5y_p10", reserve_trailing_5y_p10),
    ):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
        ):
            raise ValueError(f"{name} must be finite or null")
    reserve_stress = (
        reserve_change_4w is not None
        and reserve_trailing_5y_p10 is not None
        and reserve_change_4w < 0
        and reserve_change_4w <= reserve_trailing_5y_p10
    )

    stress_reasons: list[str] = []
    if srf_persistent:
        stress_reasons.append("SRF_NONTECHNICAL_USE_2_OF_3")
    if reserve_stress:
        stress_reasons.append("RESERVE_4W_AT_OR_BELOW_TRAILING_5Y_P10")
    if confirmation_count >= 3:
        stress_reasons.append("MULTIPLE_FUNDING_SPREADS_UP")
    stress = bool(elevated and stress_reasons)

    if not evaluated:
        level = "UNAVAILABLE"
    elif stress:
        level = "STRESS"
    elif elevated:
        level = "ELEVATED"
    elif watch:
        level = "WATCH"
    else:
        level = "NORMAL"

    flags = sorted(set(technical_flags))
    normalized_base_confidence = base_confidence.strip().upper()
    if normalized_base_confidence not in _CONFIDENCE_LEVELS:
        raise ValueError(f"unsupported confidence: {base_confidence}")
    if not evaluated:
        confidence = "LOW"
    else:
        confidence = (
            downgrade_confidence(normalized_base_confidence)
            if flags
            else normalized_base_confidence
        )

    return {
        "level": level,
        "quality_status": quality_status,
        "confidence": confidence,
        "technical_flags": flags,
        "watch_triggered": watch,
        "elevated_triggered": elevated,
        "stress_triggered": stress,
        "latest_above_watch_threshold": bool(above_threshold),
        "positive_streak_met": streak_met,
        "funding_confirmation_count": confirmation_count,
        "funding_confirmation_ids": confirmation_ids,
        "srf_positive_operation_days_latest_3": srf_positive_days,
        "reserve_4w_at_or_below_trailing_5y_p10": reserve_stress,
        "stress_reasons": stress_reasons if stress else [],
        "thresholds": {
            "sofr_iorb_watch_bp": float(watch_threshold_bp),
            "positive_streak_observations": positive_streak_required,
            "multiple_funding_confirmations": 3,
        },
    }
