"""Source-specific, tri-state evaluation for the audited video P0 model.

This module deliberately does not change the core P0 liquidity engine.  It
reproduces one cited video's thresholds, preserves the evidence state of every
clause, and never turns missing/stale input into a negative observation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isclose, isfinite
from typing import Any, Callable

from pipeline.config import validate_video_p0_crisis_context


_HEALTH_STATUSES = {
    "OK",
    "STALE",
    "ERROR",
    "NOT_RELEASED_YET",
    "NOT_APPLICABLE",
}
_FRESHNESS = {"FRESH", "LATE", "STALE", "UNKNOWN"}
_METRIC_IDS = {
    "spread": "sofr_iorb_spread_bp",
    "reserves": "reserve_balances",
    "tga": "tga_daily",
    "srf": "srf_accepted",
}
_CONFIDENCE = ("LOW", "MEDIUM", "HIGH")


@dataclass(frozen=True)
class _Evidence:
    quality_status: str
    freshness: str
    observation_date: str | None
    released_at: str | None
    evaluation_state: str
    usable: bool


def _finite_number(value: Any, field: str, *, nonnegative: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field} must be a finite number or null")
    numeric = float(value)
    if nonnegative and numeric < 0:
        raise ValueError(f"{field} must be non-negative")
    return numeric


def _iso_date_or_none(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date or null")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date or null") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be an ISO date or null")
    return value


def _iso_timestamp_or_none(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp or null") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def _utc_timestamp(value: str | None) -> str:
    if value is None:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("evaluated_at must be a UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("evaluated_at must be a UTC Z timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("evaluated_at must be a UTC Z timestamp")
    return value


def _tri_and(values: Sequence[bool | None]) -> bool | None:
    if any(value is False for value in values):
        return False
    if any(value is None for value in values):
        return None
    return True


def _tri_or(values: Sequence[bool | None]) -> bool | None:
    if any(value is True for value in values):
        return True
    if any(value is None for value in values):
        return None
    return False


def _quality_record(
    metric_quality: Mapping[str, Mapping[str, Any]],
    metric_id: str,
    *,
    value_present: bool,
) -> _Evidence:
    raw_record = metric_quality.get(metric_id)
    if not isinstance(raw_record, Mapping):
        return _Evidence("ERROR", "UNKNOWN", None, None, "MISSING", False)

    nested_quality = raw_record.get("quality")
    quality = nested_quality if isinstance(nested_quality, Mapping) else raw_record
    raw_status = quality.get("status")
    if raw_status is None:
        return _Evidence(
            "ERROR",
            "UNKNOWN",
            _iso_date_or_none(
                raw_record.get("observation_date"), f"{metric_id}.observation_date"
            ),
            _iso_timestamp_or_none(
                raw_record.get("released_at"), f"{metric_id}.released_at"
            ),
            "MISSING",
            False,
        )
    if not isinstance(raw_status, str) or raw_status not in _HEALTH_STATUSES:
        raise ValueError(f"{metric_id}.quality.status is unsupported")
    raw_freshness = quality.get("freshness", "UNKNOWN")
    if not isinstance(raw_freshness, str) or raw_freshness not in _FRESHNESS:
        raise ValueError(f"{metric_id}.quality.freshness is unsupported")
    observation_date = _iso_date_or_none(
        raw_record.get("observation_date", quality.get("observation_date")),
        f"{metric_id}.observation_date",
    )
    released_at = _iso_timestamp_or_none(
        raw_record.get("released_at", quality.get("released_at")),
        f"{metric_id}.released_at",
    )

    if not value_present:
        state, usable = "MISSING", False
    elif raw_status == "OK" and raw_freshness == "FRESH":
        state, usable = "CURRENT", True
    elif raw_status == "NOT_RELEASED_YET" or (
        raw_status == "OK" and raw_freshness == "LATE"
    ):
        state, usable = "LAST_GOOD", True
    elif raw_status == "STALE" or raw_freshness == "STALE":
        state, usable = "STALE", False
    elif raw_status == "ERROR":
        state, usable = "MISSING", False
    else:
        state, usable = "MISSING", False
    return _Evidence(
        raw_status,
        raw_freshness,
        observation_date,
        released_at,
        state,
        usable,
    )


def _basis(
    kind: str,
    label: str,
    source_segment_id: str | None,
    note: str,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "source_segment_id": source_segment_id,
        "note": note,
    }


def _clause(
    *,
    clause_id: str,
    order: int,
    label: str,
    metric_id: str | None,
    operator: str,
    threshold: int | float | str | bool | None,
    threshold_unit: str | None,
    current_value: int | float | str | bool | None,
    current_unit: str | None,
    met: bool | None,
    evidence: _Evidence,
    basis: Sequence[Mapping[str, Any]],
    note: str,
) -> dict[str, Any]:
    return {
        "clause_id": clause_id,
        "order": order,
        "label": label,
        "metric_id": metric_id,
        "operator": operator,
        "threshold": threshold,
        "threshold_unit": threshold_unit,
        "current_value": current_value,
        "current_unit": current_unit,
        "met": met,
        "observation_date": evidence.observation_date,
        "released_at": evidence.released_at,
        "quality_status": evidence.quality_status,
        "freshness": evidence.freshness,
        "evaluation_state": evidence.evaluation_state,
        "basis": [dict(item) for item in basis],
        "note": note,
    }


def _numeric_clause(
    *,
    clause_id: str,
    order: int,
    label: str,
    metric_id: str,
    operator: str,
    threshold: int | float,
    threshold_unit: str,
    current_value: int | float | None,
    current_unit: str,
    evidence: _Evidence,
    predicate: Callable[[float], bool],
    basis: Sequence[Mapping[str, Any]],
    note: str,
) -> dict[str, Any]:
    met = predicate(float(current_value)) if current_value is not None and evidence.usable else None
    return _clause(
        clause_id=clause_id,
        order=order,
        label=label,
        metric_id=metric_id,
        operator=operator,
        threshold=threshold,
        threshold_unit=threshold_unit,
        current_value=current_value,
        current_unit=current_unit,
        met=met,
        evidence=evidence,
        basis=basis,
        note=note,
    )


def _model_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate: Any = config
    alerts = candidate.get("alerts") if isinstance(candidate, Mapping) else None
    if isinstance(alerts, Mapping):
        candidate = alerts
    nested = candidate.get("video_p0_model") if isinstance(candidate, Mapping) else None
    if isinstance(nested, Mapping):
        candidate = nested
    if not isinstance(candidate, Mapping) or candidate.get("model_id") != "henren778_p0_liquidity":
        raise ValueError("config must contain the audited video_p0_model")
    for key in ("source", "yellow", "red", "extreme", "crisis_context"):
        if not isinstance(candidate.get(key), Mapping):
            raise ValueError(f"video_p0_model.{key} must be an object")
    return candidate


def _srf_clause(
    rows: Sequence[Mapping[str, Any]],
    *,
    evidence: _Evidence,
    window_days: int,
    required_positive_days: int,
) -> tuple[dict[str, Any], int | None]:
    normalized: list[tuple[str, bool]] = []
    seen_dates: set[str] = set()
    classification_complete = True
    latest_date: str | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError("SRF operation-day rows must be objects")
        operation_date = _iso_date_or_none(row.get("date"), f"SRF row {index}.date")
        assert operation_date is not None
        if operation_date in seen_dates:
            raise ValueError(f"duplicate SRF operation day: {operation_date}")
        seen_dates.add(operation_date)
        latest_date = max(latest_date, operation_date) if latest_date else operation_date

        required_classification = {
            "accepted_amount_usd_bn",
            "alert_eligible_accepted_amount_usd_bn",
            "exercise_accepted_amount_usd_bn",
            "has_technical_exercise",
            "technical_exercise",
            "classification_complete",
        }
        if not required_classification.issubset(row) or row.get("classification_complete") is not True:
            classification_complete = False
            continue
        accepted = _finite_number(
            row.get("accepted_amount_usd_bn"),
            f"SRF row {operation_date}.accepted_amount_usd_bn",
            nonnegative=True,
        )
        eligible = _finite_number(
            row.get("alert_eligible_accepted_amount_usd_bn"),
            f"SRF row {operation_date}.alert_eligible_accepted_amount_usd_bn",
            nonnegative=True,
        )
        exercise = _finite_number(
            row.get("exercise_accepted_amount_usd_bn"),
            f"SRF row {operation_date}.exercise_accepted_amount_usd_bn",
            nonnegative=True,
        )
        has_exercise = row.get("has_technical_exercise")
        technical_only = row.get("technical_exercise")
        if not isinstance(has_exercise, bool) or not isinstance(technical_only, bool):
            raise ValueError("SRF technical classification fields must be boolean")
        assert accepted is not None and eligible is not None and exercise is not None
        if not isclose(accepted, eligible + exercise, abs_tol=1e-6):
            raise ValueError("SRF daily accepted amount must equal eligible plus exercise use")
        if technical_only and (not has_exercise or eligible != 0):
            raise ValueError("SRF technical-only classification is inconsistent")
        normalized.append((operation_date, eligible > 0))

    positive_count: int | None = None
    if classification_complete:
        latest = sorted(normalized)[-window_days:]
        positive_count = sum(int(positive) for _, positive in latest)
    complete_window = classification_complete and len(normalized) >= window_days
    if not evidence.usable or not complete_window:
        met = None
    else:
        assert positive_count is not None
        met = positive_count >= required_positive_days

    clause_evidence = evidence
    if latest_date is not None and evidence.observation_date is None:
        clause_evidence = _Evidence(
            evidence.quality_status,
            evidence.freshness,
            latest_date,
            evidence.released_at,
            evidence.evaluation_state,
            evidence.usable,
        )
    if not classification_complete:
        clause_evidence = _Evidence(
            "ERROR",
            clause_evidence.freshness,
            clause_evidence.observation_date,
            clause_evidence.released_at,
            "MISSING",
            False,
        )
    elif len(normalized) < window_days and evidence.usable:
        clause_evidence = _Evidence(
            clause_evidence.quality_status,
            clause_evidence.freshness,
            clause_evidence.observation_date,
            clause_evidence.released_at,
            "MISSING",
            False,
        )

    note = (
        "Latest three completed operation days; technical-only exercises are excluded, "
        "while mixed days use only alert-eligible nontechnical accepted amount."
    )
    if not classification_complete:
        note += " One or more daily rows lack complete technical classification."
    elif len(normalized) < window_days:
        note += f" Only {len(normalized)} of {window_days} required daily rows are available."
    clause = _clause(
        clause_id="srf_positive_days",
        order=3,
        label="Nontechnical SRF positive on at least 2 of latest 3 operation days",
        metric_id=_METRIC_IDS["srf"],
        operator=">=",
        threshold=required_positive_days,
        threshold_unit=f"days in latest {window_days} completed days",
        current_value=positive_count,
        current_unit="days",
        met=met,
        evidence=clause_evidence,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "yellow_red",
                "The source says SRF use suddenly rises.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "yellow_red",
                "The dashboard requires nontechnical positive use on 2 of 3 completed days.",
            ),
        ),
        note=note,
    )
    return clause, positive_count


def _downgrade(confidence: str) -> str:
    if confidence not in _CONFIDENCE:
        return confidence
    return _CONFIDENCE[max(0, _CONFIDENCE.index(confidence) - 1)]


def evaluate_video_p0_model(
    *,
    latest_sofr_iorb_bp: float | None,
    positive_streak: int | None,
    reserve_balance_usd_bn: float | None,
    reserve_change_4w_usd_bn: float | None,
    reserve_trailing_5y_p10_usd_bn: float | None,
    tga_daily_usd_bn: float | None,
    srf_recent_operation_days: Sequence[Mapping[str, Any]],
    metric_quality: Mapping[str, Mapping[str, Any]],
    technical_flags: Sequence[str] = (),
    crisis_context: Mapping[str, Any] | None = None,
    config: Mapping[str, Any],
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate the video model with SQL-style three-valued clause logic.

    A false term resolves an AND even when another term is unknown, and a true
    term resolves an OR.  Unknown higher-priority conditions prevent a lower
    status only when the unknown could still change that status.
    """

    model_config = _model_config(config)
    source = model_config["source"]
    yellow_config = model_config["yellow"]
    red_config = model_config["red"]
    extreme_config = model_config["extreme"]
    assert isinstance(source, Mapping)
    assert isinstance(yellow_config, Mapping)
    assert isinstance(red_config, Mapping)
    assert isinstance(extreme_config, Mapping)

    spread = _finite_number(latest_sofr_iorb_bp, "latest_sofr_iorb_bp")
    if positive_streak is not None and (
        isinstance(positive_streak, bool)
        or not isinstance(positive_streak, int)
        or positive_streak < 0
    ):
        raise ValueError("positive_streak must be a non-negative integer or null")
    reserves = _finite_number(
        reserve_balance_usd_bn, "reserve_balance_usd_bn", nonnegative=True
    )
    reserve_change = _finite_number(
        reserve_change_4w_usd_bn, "reserve_change_4w_usd_bn"
    )
    reserve_p10 = _finite_number(
        reserve_trailing_5y_p10_usd_bn, "reserve_trailing_5y_p10_usd_bn"
    )
    tga = _finite_number(tga_daily_usd_bn, "tga_daily_usd_bn", nonnegative=True)
    if not isinstance(metric_quality, Mapping):
        raise ValueError("metric_quality must be an object")
    if not isinstance(srf_recent_operation_days, Sequence) or isinstance(
        srf_recent_operation_days, (str, bytes)
    ):
        raise ValueError("srf_recent_operation_days must be a sequence")

    flags: list[str] = []
    for flag in technical_flags:
        if not isinstance(flag, str) or not flag.strip():
            raise ValueError("technical_flags must contain non-empty strings")
        flags.append(flag.strip().upper())
    flags = sorted(set(flags))

    context_value = model_config["crisis_context"] if crisis_context is None else crisis_context
    validate_video_p0_crisis_context(context_value, path="crisis_context")
    assert isinstance(context_value, Mapping)
    context = dict(context_value)

    yellow_reserve_bn = round(float(yellow_config["reserve_below_usd_tn"]) * 1000, 6)
    red_reserve_bn = round(float(red_config["reserve_below_usd_tn"]) * 1000, 6)
    extreme_reserve_bn = round(float(extreme_config["reserve_below_usd_tn"]) * 1000, 6)
    tga_floor_bn = round(float(yellow_config["tga_near_1t_floor_usd_tn"]) * 1000, 6)
    tga_target_bn = round(float(yellow_config["tga_source_target_usd_tn"]) * 1000, 6)
    streak_required = int(yellow_config["positive_streak_observations"])
    positive_spread_line = float(yellow_config["spread_positive_bp"])
    spread_threshold = float(red_config["sofr_iorb_bp"])
    srf_window = int(red_config["srf_window_completed_operation_days"])
    srf_required = int(red_config["srf_positive_days_latest_3"])

    spread_evidence = _quality_record(
        metric_quality, _METRIC_IDS["spread"], value_present=spread is not None
    )
    streak_evidence = _quality_record(
        metric_quality,
        _METRIC_IDS["spread"],
        value_present=positive_streak is not None,
    )
    reserve_evidence = _quality_record(
        metric_quality, _METRIC_IDS["reserves"], value_present=reserves is not None
    )
    change_evidence = _quality_record(
        metric_quality,
        _METRIC_IDS["reserves"],
        value_present=reserve_change is not None,
    )
    p10_evidence = _quality_record(
        metric_quality,
        _METRIC_IDS["reserves"],
        value_present=reserve_change is not None and reserve_p10 is not None,
    )
    tga_evidence = _quality_record(
        metric_quality, _METRIC_IDS["tga"], value_present=tga is not None
    )
    srf_evidence = _quality_record(
        metric_quality,
        _METRIC_IDS["srf"],
        value_present=bool(srf_recent_operation_days),
    )

    yellow_streak = _numeric_clause(
        clause_id="sofr_positive_streak",
        order=1,
        label="SOFR−IORB positive streak",
        metric_id=_METRIC_IDS["spread"],
        operator=">=",
        threshold=streak_required,
        threshold_unit="observations",
        current_value=positive_streak,
        current_unit="observations",
        evidence=streak_evidence,
        predicate=lambda value: value >= streak_required,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "yellow_red",
                "The source says the spread turns persistently positive.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "yellow_red",
                "Persistence is operationalized as three valid observations.",
            ),
        ),
        note="Three observations are a dashboard operationalization, not a quoted duration.",
    )
    yellow_reserve = _numeric_clause(
        clause_id="reserve_below_yellow",
        order=2,
        label="Reserve Balances < 2.9T",
        metric_id=_METRIC_IDS["reserves"],
        operator="<",
        threshold=yellow_reserve_bn,
        threshold_unit="USD bn",
        current_value=reserves,
        current_unit="USD bn",
        evidence=reserve_evidence,
        predicate=lambda value: value < yellow_reserve_bn,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "yellow_red",
                "2.9T is the source model's yellow reserve threshold.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "yellow_red",
                "The dashboard evaluates the cited reserve level in USD bn.",
            ),
        ),
        note="This source-model threshold is not a universal reserve-scarcity boundary.",
    )
    yellow_change = _numeric_clause(
        clause_id="reserve_change_4w_negative",
        order=3,
        label="Four-week Reserve Balances change < 0",
        metric_id=_METRIC_IDS["reserves"],
        operator="<",
        threshold=0,
        threshold_unit="USD bn",
        current_value=reserve_change,
        current_unit="USD bn",
        evidence=change_evidence,
        predicate=lambda value: value < 0,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "reserve_exit_1",
                "The source describes reserves falling through 2.9T toward 2.8T.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "reserve_exit_1",
                "The direction toward 2.8T is operationalized as a negative four-week change.",
            ),
        ),
        note="A negative change establishes direction only; it does not by itself mean stress.",
    )
    yellow_tga = _numeric_clause(
        clause_id="tga_near_1t",
        order=4,
        label="TGA near 1T operational floor",
        metric_id=_METRIC_IDS["tga"],
        operator=">=",
        threshold=tga_floor_bn,
        threshold_unit="USD bn",
        current_value=tga,
        current_unit="USD bn",
        evidence=tga_evidence,
        predicate=lambda value: value >= tga_floor_bn,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "yellow_red",
                "The source says TGA approaches 1T.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "yellow_red",
                "The dashboard uses 0.95T as the one-sided operational floor.",
            ),
        ),
        note="Values above 1T still satisfy this one-sided proximity rule.",
    )
    yellow_clauses = [yellow_streak, yellow_reserve, yellow_change, yellow_tga]
    yellow_triggered = _tri_and([clause["met"] for clause in yellow_clauses])

    red_spread = _numeric_clause(
        clause_id="sofr_spread_above_red",
        order=1,
        label="SOFR−IORB > +3 bp",
        metric_id=_METRIC_IDS["spread"],
        operator=">",
        threshold=spread_threshold,
        threshold_unit="bp",
        current_value=spread,
        current_unit="bp",
        evidence=spread_evidence,
        predicate=lambda value: value > spread_threshold,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "yellow_red",
                "+3 bp is the source model's strict spread line.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "yellow_red",
                "The dashboard evaluates the cited line as a strict greater-than comparison in bp.",
            ),
        ),
        note="Equality at +3 bp does not meet this strict greater-than clause.",
    )
    red_reserve = _numeric_clause(
        clause_id="reserve_below_red",
        order=2,
        label="Reserve Balances < 2.8T",
        metric_id=_METRIC_IDS["reserves"],
        operator="<",
        threshold=red_reserve_bn,
        threshold_unit="USD bn",
        current_value=reserves,
        current_unit="USD bn",
        evidence=reserve_evidence,
        predicate=lambda value: value < red_reserve_bn,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "yellow_red",
                "2.8T is the source model's red reserve confirmation line.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "yellow_red",
                "The dashboard evaluates the cited reserve level in USD bn.",
            ),
        ),
        note="This source-model threshold is not a Federal Reserve official crisis line.",
    )
    srf_clause, _ = _srf_clause(
        srf_recent_operation_days,
        evidence=srf_evidence,
        window_days=srf_window,
        required_positive_days=srf_required,
    )
    route_a_triggered = _tri_and([red_spread["met"], red_reserve["met"]])
    route_b_triggered = srf_clause["met"]
    red_triggered = _tri_or([route_a_triggered, route_b_triggered])
    red_clauses = [red_spread, red_reserve, srf_clause]

    extreme_reserve = _numeric_clause(
        clause_id="reserve_below_extreme",
        order=1,
        label="Reserve Balances < 2.5T",
        metric_id=_METRIC_IDS["reserves"],
        operator="<",
        threshold=extreme_reserve_bn,
        threshold_unit="USD bn",
        current_value=reserves,
        current_unit="USD bn",
        evidence=reserve_evidence,
        predicate=lambda value: value < extreme_reserve_bn,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "reserve_exit_2",
                "2.5T is the source model's extreme reserve line.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "reserve_exit_2",
                "The dashboard evaluates the cited reserve level in USD bn.",
            ),
        ),
        note="This threshold belongs to the cited source model, not all reserve regimes.",
    )
    rapid_met = (
        reserve_change <= reserve_p10
        if reserve_change is not None and reserve_p10 is not None and p10_evidence.usable
        else None
    )
    rapid_current: float | None = reserve_change
    rapid_clause = _clause(
        clause_id="reserve_rapid_decline",
        order=2,
        label="Four-week decline ≤ trailing five-year p10",
        metric_id=_METRIC_IDS["reserves"],
        operator="<=",
        threshold=reserve_p10,
        threshold_unit="USD bn",
        current_value=rapid_current,
        current_unit="USD bn",
        met=rapid_met,
        evidence=p10_evidence,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "reserve_exit_2",
                "The source requires a rapid fall below 2.5T.",
            ),
            _basis(
                "DASHBOARD_OPERATIONALIZATION",
                "OPERATIONALIZED",
                "reserve_exit_2",
                "Rapid decline is operationalized as four-week change at or below trailing 5Y p10.",
            ),
        ),
        note="The current four-week change is compared with the precomputed trailing p10.",
    )

    context_status = context["status"]
    no_major_crisis = {
        "UNKNOWN": None,
        "MAJOR_CRISIS_PRESENT": False,
        "NO_MAJOR_CRISIS": True,
    }[context_status]
    if context_status == "UNKNOWN":
        context_evidence = _Evidence(
            "NOT_APPLICABLE", "UNKNOWN", None, None, "REVIEW_REQUIRED", False
        )
    else:
        context_evidence = _Evidence(
            "OK",
            "FRESH",
            context["as_of"],
            context["reviewed_at"],
            "CURRENT",
            True,
        )
    context_clause = _clause(
        clause_id="no_major_crisis",
        order=3,
        label="No major crisis or special-policy context",
        metric_id=None,
        operator="=",
        threshold="NO_MAJOR_CRISIS",
        threshold_unit=None,
        current_value=context_status,
        current_unit=None,
        met=no_major_crisis,
        evidence=context_evidence,
        basis=(
            _basis(
                "VIDEO_SOURCE_RULE",
                "SOURCE RULE",
                "reserve_exit_2",
                "The source limits the extreme condition to an absence of major-crisis context.",
            ),
            _basis(
                "MANUAL_CONTEXT",
                "MANUAL REVIEW",
                None,
                "Crisis context must be supported by dated reviewer metadata.",
            ),
        ),
        note="UNKNOWN never confirms or denies the manual context gate.",
    )
    extreme_candidate = _tri_and([extreme_reserve["met"], rapid_clause["met"]])
    extreme_triggered = _tri_and([extreme_candidate, no_major_crisis])
    context_required = extreme_candidate is True and no_major_crisis is None
    extreme_clauses = [extreme_reserve, rapid_clause, context_clause]

    extreme_unknown_can_outrank = extreme_candidate is None and no_major_crisis is not False
    if extreme_triggered is True:
        status = "EXTREME_CONFIRMED"
    elif context_required:
        status = "EXTREME_CONTEXT_REQUIRED"
    elif extreme_unknown_can_outrank:
        status = "UNAVAILABLE"
    elif red_triggered is True:
        status = "RED"
    elif red_triggered is None:
        status = "UNAVAILABLE"
    elif yellow_triggered is True:
        status = "YELLOW"
    elif yellow_triggered is None:
        status = "UNAVAILABLE"
    else:
        status = "GREEN"

    evidence_clauses = [
        yellow_streak,
        yellow_reserve,
        yellow_change,
        yellow_tga,
        red_spread,
        srf_clause,
        rapid_clause,
    ]
    evidence_states = {clause["evaluation_state"] for clause in evidence_clauses}
    if status == "UNAVAILABLE":
        data_status = "UNAVAILABLE"
    elif evidence_states & {"STALE", "MISSING"}:
        data_status = "PARTIAL"
    elif "LAST_GOOD" in evidence_states:
        data_status = "LAST_GOOD"
    else:
        data_status = "CURRENT"

    if status == "UNAVAILABLE":
        confidence = "UNKNOWN"
    elif data_status == "CURRENT":
        confidence = "HIGH"
    else:
        confidence = "MEDIUM"
    if status == "EXTREME_CONTEXT_REQUIRED" and confidence == "HIGH":
        confidence = "MEDIUM"
    if flags:
        confidence = _downgrade(confidence)

    unknown_ids = sorted(
        {
            clause["clause_id"]
            for clause in evidence_clauses
            if clause["met"] is None
        }
    )
    availability_reason = (
        "Evidence required to resolve model priority is unavailable: "
        + ", ".join(unknown_ids)
        if status == "UNAVAILABLE"
        else None
    )
    notes = [
        "Video-model thresholds are source-specific reference rules, not universal reserve-scarcity laws.",
        "This decision model does not replace the audited NORMAL/WATCH/ELEVATED/STRESS P0 engine.",
    ]
    if data_status == "LAST_GOOD":
        notes.append("At least one clause uses a last-good value because a new release is not yet available.")
    elif data_status == "PARTIAL":
        notes.append("Some clause evidence is stale, missing, or incompletely classified.")
    if flags:
        notes.append("Technical-date flags lower confidence but do not suppress formula results.")

    segments = source.get("segments")
    if not isinstance(segments, list) or not all(isinstance(item, Mapping) for item in segments):
        raise ValueError("video_p0_model.source.segments must be an object list")
    result = {
        "model_id": "henren778_p0_liquidity",
        "label": str(model_config["label"]),
        "enabled": bool(model_config["enabled"]),
        "status": status,
        "data_status": data_status,
        "confidence": confidence,
        "availability_reason": availability_reason,
        "evaluated_at": _utc_timestamp(evaluated_at),
        "source": {
            "title": str(source["title"]),
            "display_title": str(source["display_title"]),
            "author": str(source["author"]),
            "url": str(source["url"]),
            "segments": [dict(item) for item in segments],
        },
        "thresholds": {
            "yellow": {
                "spread_positive_bp": positive_spread_line,
                "positive_streak_observations": streak_required,
                "reserve_usd_bn": yellow_reserve_bn,
                "reserve_change_4w_usd_bn": 0,
                "tga_operational_floor_usd_bn": tga_floor_bn,
            },
            "red": {
                "spread_bp": spread_threshold,
                "reserve_usd_bn": red_reserve_bn,
                "srf_positive_days_required": srf_required,
                "srf_window_completed_days": srf_window,
            },
            "extreme": {
                "reserve_usd_bn": extreme_reserve_bn,
                "decline_percentile": "TRAILING_5Y_P10",
            },
            "tga_source_target_usd_bn": tga_target_bn,
        },
        "operationalizations": {
            "positive_streak_observations": streak_required,
            "tga_near_1t_floor_usd_bn": tga_floor_bn,
            "rapid_reserve_decline_rule": "TRAILING_5Y_P10",
            "srf_positive_days_latest_3": srf_required,
            "srf_window_completed_operation_days": srf_window,
            "exclude_technical_exercises": True,
        },
        "crisis_context": context,
        "formulas": {
            "yellow": {
                "expression": (
                    "PERSIST(SOFR−IORB > 0) ∧ RESERVES < 2.9T ∧ "
                    "Δ4W RESERVES < 0 ∧ TGA ≥ 0.95T"
                ),
                "triggered": yellow_triggered,
                "clauses": yellow_clauses,
            },
            "red": {
                "expression": (
                    "[(SOFR−IORB > +3 bp) ∧ (RESERVES < 2.8T)] "
                    "∨ NONTECHNICAL SRF ↑"
                ),
                "triggered": red_triggered,
                "clauses": red_clauses,
                "routes": [
                    {
                        "route_id": "spread_and_reserves",
                        "label": "ROUTE A · SPREAD + RESERVES",
                        "expression": "SOFR−IORB > +3 bp ∧ RESERVES < 2.8T",
                        "triggered": route_a_triggered,
                        "clauses": [red_spread, red_reserve],
                    },
                    {
                        "route_id": "srf_2_of_3",
                        "label": "ROUTE B · NONTECHNICAL SRF",
                        "expression": "NONTECHNICAL SRF POSITIVE ON ≥2 OF LATEST 3 DAYS",
                        "triggered": route_b_triggered,
                        "clauses": [srf_clause],
                    },
                ],
            },
            "extreme": {
                "expression": (
                    "RESERVES < 2.5T ∧ 4W DECLINE ≤ TRAILING 5Y P10 "
                    "∧ NO MAJOR CRISIS"
                ),
                "triggered": extreme_triggered,
                "clauses": extreme_clauses,
                "candidate": extreme_candidate,
                "context_required": context_required,
            },
        },
        "technical_flags": flags,
        "notes": notes,
    }
    if not model_config["enabled"]:
        unique_clauses = [
            *result["formulas"]["yellow"]["clauses"],
            *result["formulas"]["red"]["clauses"],
            *result["formulas"]["extreme"]["clauses"],
        ]
        for item in unique_clauses:
            item["met"] = None
            item["evaluation_state"] = "DISABLED"
        result["status"] = "UNAVAILABLE"
        result["data_status"] = "UNAVAILABLE"
        result["confidence"] = "UNKNOWN"
        result["availability_reason"] = "DISABLED"
        result["formulas"]["yellow"]["triggered"] = None
        result["formulas"]["red"]["triggered"] = None
        for route in result["formulas"]["red"]["routes"]:
            route["triggered"] = None
        result["formulas"]["extreme"]["candidate"] = None
        result["formulas"]["extreme"]["triggered"] = None
        result["formulas"]["extreme"]["context_required"] = False
        result["technical_flags"] = []
        result["notes"] = []
    return result
