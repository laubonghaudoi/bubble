"""Release-one orchestration for the schema 2.0.0 static publication.

The module deliberately keeps collection, transformation, contract validation,
staging, and promotion as separate operations.  GitHub Actions can therefore
hold a complete candidate artifact outside ``public/data`` while the Python and
frontend gates run, then perform one whole-directory promotion.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
from typing import Any

from pipeline.build import (
    LEGACY_SERIES_IDS,
    NEW_YORK,
    FRESHNESS_ORDER,
    HEALTH_ORDER,
    SeriesState,
    availability_counts,
    collector_source_record,
    derived_state,
    freshness_for,
    generic_statistics,
    h41_freshness_for,
    load_last_good,
    manifest_record,
    metric_record,
    series_record,
    source_details,
    source_health_counts,
    successful_state,
    utc_now,
    utc_string,
)
from pipeline.collectors.fred import fetch_series as fetch_fred_series
from pipeline.collectors.nyfed import (
    fetch_on_rrp,
    fetch_reference_rate,
    fetch_srf_operations,
)
from pipeline.collectors.treasury import fetch_auctions, fetch_tga
from pipeline.config import (
    CANONICAL_P0_METRIC_IDS,
    ConfigBundle,
    assert_metric_network_eligible,
    assert_source_network_eligible,
    effective_metric_state,
    load_config_bundle,
)
from pipeline.contracts import (
    SCHEMA_VERSION,
    validate_alerts_file,
    validate_events_file,
    validate_publication,
)
from pipeline.io import (
    PublicationError,
    atomic_json,
    promote_data_directory,
    read_json,
    staged_data_directory,
)
from pipeline.rules.p0 import liquidity_alert_rule
from pipeline.transforms.p0 import (
    add_large_settlement_context,
    aggregate_srf_operations,
    aggregate_treasury_settlements,
    build_iorb_spreads,
    h41_change_4w_context,
    h41_weekly_stats,
    observation_period_end_flags,
    on_rrp_near_floor_context,
    reviewed_tax_window_events,
    srf_nontechnical_positive_use_streak,
    spread_observation_stats,
)


VALID_MODES = frozenset({"incremental", "backfill"})
VALID_GROUPS = frozenset(
    {"all", "daily", "h41", "weekly", "monthly", "quarterly", "manual"}
)
RATE_IDS = ("sofr", "effr", "obfr", "tgcr", "bgcr")
SPREAD_IDS = tuple(f"{metric_id}_iorb_spread_bp" for metric_id in RATE_IDS)
H41_SERIES = {
    "reserve_balances": ("WRESBAL", 1_000),
    "fed_total_assets": ("WALCL", 1_000),
    "tga_weekly_h41": ("WTREGEN", 1_000),
}


@dataclass(frozen=True)
class CollectorFunctions:
    """Injectable network boundary used by deterministic fixture tests."""

    rate: Callable[..., list[dict[str, Any]]] = fetch_reference_rate
    fred: Callable[..., list[dict[str, Any]]] = fetch_fred_series
    on_rrp: Callable[..., list[dict[str, Any]]] = fetch_on_rrp
    srf_operations: Callable[..., list[dict[str, Any]]] = fetch_srf_operations
    tga: Callable[..., list[dict[str, Any]]] = fetch_tga
    auctions: Callable[..., list[dict[str, Any]]] = fetch_auctions


@dataclass(frozen=True)
class Publication:
    snapshot: dict[str, Any]
    manifest: dict[str, Any]
    series_by_id: dict[str, dict[str, Any]]
    alerts: dict[str, Any]
    events: dict[str, Any]


def _failure_reason(error: BaseException) -> str:
    """Return a bounded failure reason without ever persisting a FRED key."""

    reason = str(error) or error.__class__.__name__
    key = os.environ.get("FRED_API_KEY")
    if key:
        reason = reason.replace(key, "<redacted>")
    reason = re.sub(r"(?i)(api_key=)[^&\s]+", r"\1<redacted>", reason)
    return reason[:1_000]


def _merge_observations(
    prior: Sequence[Mapping[str, Any]], current: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_date = {str(point["date"]): dict(point) for point in prior}
    by_date.update({str(point["date"]): dict(point) for point in current})
    return [by_date[day] for day in sorted(by_date)]


def _prior_series_payload(data_dir: Path, metric_id: str) -> Mapping[str, Any]:
    candidates = (metric_id, LEGACY_SERIES_IDS.get(metric_id))
    for candidate in candidates:
        if candidate:
            payload = read_json(data_dir / "series" / f"{candidate}.json", {}) or {}
            if isinstance(payload, Mapping) and payload.get("observations"):
                return payload
    return {}


def _preserved_state(
    metric_id: str,
    *,
    data_dir: Path,
    frequency: str,
    attempted_at: str,
    now_et: datetime,
) -> SeriesState:
    observations, inferred_success, inferred_release = load_last_good(data_dir, metric_id)
    prior = _prior_series_payload(data_dir, metric_id)
    quality = prior.get("quality") if isinstance(prior.get("quality"), Mapping) else {}
    observation_date = observations[-1]["date"] if observations else None
    freshness, health = (
        h41_freshness_for(observation_date, now_et=now_et)
        if metric_id in H41_SERIES
        else freshness_for(observation_date, frequency, now_et=now_et)
    )
    prior_health = quality.get("status")
    prior_freshness = quality.get("freshness")
    if prior_health in HEALTH_ORDER:
        health = max((health, str(prior_health)), key=HEALTH_ORDER.__getitem__)
    if prior_freshness in FRESHNESS_ORDER:
        freshness = max(
            (freshness, str(prior_freshness)), key=FRESHNESS_ORDER.__getitem__
        )
    previous_snapshot = read_json(data_dir / "snapshot.json", {}) or {}
    fallback_stamp = (
        previous_snapshot.get("pipeline_updated_at")
        or previous_snapshot.get("generated_at")
        or attempted_at
    )
    last_attempt = quality.get("last_attempt_at") or fallback_stamp
    last_success = quality.get("last_success_at") or inferred_success
    failure = quality.get("failure_reason")
    if not observations and not failure:
        failure = "No last-good observation is available for this enabled metric."
    return SeriesState(
        metric_id=metric_id,
        observations=observations,
        health=health,
        freshness=freshness,
        last_success_at=last_success if isinstance(last_success, str) else None,
        last_attempt_at=last_attempt if isinstance(last_attempt, str) else attempted_at,
        failure_reason=_failure_reason(RuntimeError(failure)) if failure else None,
        released_at=(
            prior.get("released_at")
            if isinstance(prior.get("released_at"), str)
            else inferred_release
        ),
        updated_at=(
            prior.get("updated_at")
            if isinstance(prior.get("updated_at"), str)
            else last_success if isinstance(last_success, str) else None
        ),
    )


def _failed_from_prior(
    metric_id: str,
    *,
    prior: SeriesState,
    attempted_at: str,
    error: BaseException,
) -> SeriesState:
    return SeriesState(
        metric_id=metric_id,
        observations=prior.observations,
        health="STALE" if prior.observations else "ERROR",
        freshness="STALE" if prior.observations else "UNKNOWN",
        last_success_at=prior.last_success_at,
        last_attempt_at=attempted_at,
        failure_reason=_failure_reason(error),
        released_at=prior.released_at,
        updated_at=prior.updated_at,
    )


def _success_with_history(
    metric_id: str,
    observations: Sequence[Mapping[str, Any]],
    *,
    prior: SeriesState,
    frequency: str,
    attempted_at: str,
    now_et: datetime,
    mode: str,
) -> SeriesState:
    merged = (
        _merge_observations(prior.observations, observations)
        if mode == "incremental"
        else list(observations)
    )
    return successful_state(
        metric_id,
        merged,
        frequency=frequency,
        attempted_at=attempted_at,
        now_et=now_et,
    )


def _prior_events(data_dir: Path) -> list[dict[str, Any]]:
    payload = read_json(data_dir / "events.json", []) or []
    if isinstance(payload, Mapping):
        payload = payload.get("events", [])
    return [dict(item) for item in payload if isinstance(item, Mapping)] if isinstance(payload, list) else []


def _settlement_state_from_prior(
    data_dir: Path, *, attempted_at: str
) -> tuple[list[dict[str, Any]], SeriesState]:
    rows = [
        event
        for event in _prior_events(data_dir)
        if isinstance(event.get("treasury_settlement_usd_bn"), (int, float))
    ]
    points = [
        {"date": row["date"], "value": row["treasury_settlement_usd_bn"]}
        for row in rows
        if isinstance(row.get("date"), str)
    ]
    snapshot = read_json(data_dir / "snapshot.json", {}) or {}
    source = snapshot.get("sources", {}).get("treasury_auctions", {}) if isinstance(snapshot.get("sources"), Mapping) else {}
    status = source.get("status") if source.get("status") in {"OK", "STALE", "ERROR", "NOT_RELEASED_YET"} else ("STALE" if points else "NOT_RELEASED_YET")
    freshness = source.get("freshness") if source.get("freshness") in {"FRESH", "LATE", "STALE", "UNKNOWN"} else ("STALE" if points else "UNKNOWN")
    stamp = source.get("last_attempt_at") or snapshot.get("pipeline_updated_at") or snapshot.get("generated_at") or attempted_at
    state = SeriesState(
        metric_id="treasury_settlement_calendar",
        observations=points,
        health=status,
        freshness=freshness,
        last_success_at=source.get("last_success_at"),
        last_attempt_at=stamp,
        failure_reason=source.get("failure_reason"),
        released_at=source.get("released_at"),
        updated_at=source.get("updated_at"),
    )
    return rows, state


def _merge_event_rows(*groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            day = raw.get("date")
            if not isinstance(day, str):
                continue
            event = merged.setdefault(day, {"date": day, "flags": []})
            event["flags"] = sorted(set(event["flags"]) | set(raw.get("flags", ())))
            for key, value in raw.items():
                if key not in {"date", "flags"}:
                    event[key] = value
    notes = {
        "MONTH_END": "月末資產負債表調整可能暫時影響隔夜利率。",
        "QUARTER_END": "季末資產負債表調整可能暫時影響隔夜利率。",
        "YEAR_END": "年末資產負債表調整可能暫時影響隔夜利率。",
        "TREASURY_SETTLEMENT": "Treasury 結算可能短暫抽走銀行體系現金。",
        "LARGE_TREASURY_SETTLEMENT": "Treasury 結算高於 trailing 3-year 非零日 p90。",
        "TAX_WINDOW": "已審核稅款限期前後一個 business day，現金流可能受技術因素影響。",
        "NYFED_OPERATIONAL_READINESS": "NY Fed 官方 operational-readiness allowlist 日期；不按金額推斷。",
    }
    for event in merged.values():
        event["note"] = " ".join(notes[flag] for flag in event["flags"] if flag in notes)
    return [merged[day] for day in sorted(merged)]


def _technical_events(
    bundle: ConfigBundle,
    *,
    observation_calendar: Sequence[str],
    settlements: Sequence[Mapping[str, Any]],
    current_new_york_date: date | None = None,
) -> list[dict[str, Any]]:
    calendar = sorted(set(observation_calendar))
    period_events = [
        {"date": day, "flags": flags}
        for day in calendar[:-1]
        if (flags := observation_period_end_flags(day, calendar))
    ]
    # The next official observation is not yet available when the dashboard is
    # most useful.  Once New York has crossed a month boundary, the latest
    # actual NY Fed observation is auditable as the preceding period's final
    # valid observation; classify it without fabricating a future data point.
    if calendar and current_new_york_date is not None:
        latest = date.fromisoformat(calendar[-1])
        # Only infer the just-crossed boundary while the latest observation is
        # still within the normal publication lag.  An old mid-period
        # last-good value must never be relabelled as a period-end observation.
        lag_days = (current_new_york_date - latest).days
        crossed_immediate_boundary = (
            current_new_york_date > latest
            and 0 < lag_days <= 4
            and (latest.year * 12 + latest.month + 1)
            == (current_new_york_date.year * 12 + current_new_york_date.month)
        )
        if crossed_immediate_boundary:
            flags: list[str] = []
            if (latest.year, latest.month) != (
                current_new_york_date.year,
                current_new_york_date.month,
            ):
                flags.append("MONTH_END")
            latest_quarter = (latest.month - 1) // 3
            current_quarter = (current_new_york_date.month - 1) // 3
            if (
                latest.year != current_new_york_date.year
                or latest_quarter != current_quarter
            ):
                flags.append("QUARTER_END")
            if latest.year != current_new_york_date.year:
                flags.append("YEAR_END")
            if flags:
                period_events.append({"date": latest.isoformat(), "flags": flags})
    tax_rows = []
    if calendar:
        lower, upper = calendar[0], calendar[-1]
        eligible_tax_dates = [
            item
            for item in bundle.us_tax_dates["tax_dates"]
            if date.fromisoformat(lower) - timedelta(days=7)
            <= date.fromisoformat(item["observed_deadline"])
            <= date.fromisoformat(upper) + timedelta(days=7)
        ]
        tax_calendar = set(calendar)
        for item in eligible_tax_dates:
            deadline = date.fromisoformat(item["observed_deadline"])
            tax_calendar.add(deadline.isoformat())
            for direction in (-1, 1):
                adjacent = deadline + timedelta(days=direction)
                while adjacent.weekday() >= 5:
                    adjacent += timedelta(days=direction)
                observed_candidates = [
                    date.fromisoformat(day)
                    for day in calendar
                    if (date.fromisoformat(day) - deadline).days * direction > 0
                    and abs((date.fromisoformat(day) - deadline).days) <= 7
                ]
                if observed_candidates:
                    adjacent = min(
                        observed_candidates,
                        key=lambda day: abs((day - deadline).days),
                    )
                tax_calendar.add(adjacent.isoformat())
        tax_rows = [
            row
            for row in reviewed_tax_window_events(
                eligible_tax_dates, sorted(tax_calendar)
            )
            if lower <= row["date"] <= upper
        ]
    readiness = [
        {
            "date": item["operation_date"],
            "flags": ["NYFED_OPERATIONAL_READINESS", f"{item['operation_type']}_EXERCISE"],
            "sources": [item["source_url"]],
            "exercise_id": item["exercise_id"],
        }
        for item in bundle.nyfed_operational_readiness["exercises"]
    ]
    return _merge_event_rows(period_events, list(settlements), tax_rows, readiness)


def _future_evidence_blocks(layer: str) -> list[dict[str, Any]]:
    labels = {
        "market_ignition": (
            ("volatility", "Volatility term structure"),
            ("positioning", "CFTC positioning"),
            ("crypto_funding", "Crypto funding"),
            ("trend_cross_asset", "Trend / cross-asset"),
        ),
        "fundamental_exit": (
            ("capex", "Hyperscaler CapEx"),
            ("orders_backlog", "Orders / backlog"),
            ("prepayments", "Prepayments"),
            ("take_or_pay", "Take-or-pay"),
        ),
    }[layer]
    return [
        {
            "id": block_id,
            "label": label,
            "available": False,
            "triggered": None,
            "status": "UNAVAILABLE_FREE",
            "summary": "本階段未啟用；權利未清楚嘅來源保持 null。",
        }
        for block_id, label in labels
    ]


def _explanation(
    assessment: str,
    confidence: str,
    sofr_stats: Mapping[str, Any],
    sofr_quality: Mapping[str, Any],
    rule: Mapping[str, Any],
    technical_flags: Sequence[str],
) -> dict[str, Any]:
    latest = sofr_stats.get("latest")
    quality_status = str(sofr_quality.get("status") or "UNKNOWN")
    has_last_good = isinstance(latest, (int, float)) and quality_status != "OK"
    quality_note = {
        "STALE": "資料已過期或今次抓取未成功",
        "NOT_RELEASED_YET": "今期尚未發布",
        "ERROR": "今次抓取失敗",
        "NOT_APPLICABLE": "今期不適用",
    }.get(quality_status, "資料健康狀態不正常")
    if has_last_good:
        observation = (
            f"SOFR−IORB 最後成功觀察值為 {latest:+.1f} bp"
            f"（{quality_note}；並非今日新值）。"
        )
    elif isinstance(latest, (int, float)):
        observation = f"SOFR−IORB 最新為 {latest:+.1f} bp。"
    else:
        observation = "SOFR−IORB 暫時缺失。"
    headline = {
        "NEUTRAL": "Liquidity Fuel 暫未觸發監察條件。",
        "WATCH": "SOFR−IORB 已觸發初步監察條件。",
        "ELEVATED": "初步訊號獲獨立融資利差確認。",
        "STRESS": "多個獨立 Liquidity Fuel evidence blocks 同時惡化。",
        "UNAVAILABLE": "P0 證據不足，今次不作中性推斷。",
    }.get(assessment, "P0 判讀已更新。")
    alternative = (
        "今日同時有技術事件，可能造成短暫扭曲；原始數據保留但信心下調。"
        if technical_flags
        else "單一日變化亦可能來自結算、稅款或市場微結構，唔等於準備金短缺。"
    )
    return {
        "headline": headline,
        "bullets": [
            {
                "metric_id": "sofr_iorb_spread_bp",
                "observation": observation,
                "meaning": (
                    "呢個 last-good 值只作歷史參考；正數代表 secured overnight funding 相對 IORB 變貴。"
                    if has_last_good
                    else "正數代表 secured overnight funding 相對 IORB 變貴。"
                ),
                "alternative": alternative,
                "confirmation": f"EFFR/TGCR/BGCR 當中 {rule['funding_confirmation_count']} 條同時向上確認。",
                "judgment": f"Deterministic P0 assessment：{assessment}；Overview overall 只代表 Liquidity Fuel。",
                "confidence": confidence,
            }
        ],
    }


def build_release(
    *,
    mode: str = "incremental",
    group: str = "all",
    data_dir: str | Path = Path("public/data"),
    now: datetime | None = None,
    bundle: ConfigBundle | None = None,
    collectors: CollectorFunctions | None = None,
) -> Publication:
    """Collect and assemble a complete in-memory Release 1 publication."""

    if mode not in VALID_MODES:
        raise ValueError(f"unsupported mode: {mode}")
    if group not in VALID_GROUPS:
        raise ValueError(f"unsupported group: {group}")
    root = Path(data_dir)
    bundle = bundle or load_config_bundle()
    collectors = collectors or CollectorFunctions()
    current = now or utc_now()
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    current = current.astimezone(timezone.utc)
    attempted_at = utc_string(current)
    now_et = current.astimezone(NEW_YORK)
    rate_years = 6 if mode == "backfill" else 2
    rate_start = now_et.date() - timedelta(days=366 * rate_years)
    fred_start = now_et.date() - timedelta(days=366 * 6)

    states = {
        metric_id: _preserved_state(
            metric_id,
            data_dir=root,
            frequency=bundle.metrics_by_id[metric_id]["frequency"],
            attempted_at=attempted_at,
            now_et=now_et,
        )
        for metric_id in CANONICAL_P0_METRIC_IDS
        if metric_id not in SPREAD_IDS
    }
    attempted_collectors: set[str] = set()
    daily = group in {"all", "daily"}
    h41 = group in {"all", "h41", "weekly"}

    if daily:
        attempted_collectors.add("nyfed_rates")
        for metric_id in RATE_IDS:
            prior = states[metric_id]
            try:
                assert_metric_network_eligible(bundle, metric_id)
                observations = collectors.rate(
                    metric_id, start=rate_start, end=now_et.date()
                )
                states[metric_id] = _success_with_history(
                    metric_id,
                    observations,
                    prior=prior,
                    frequency="business_daily",
                    attempted_at=attempted_at,
                    now_et=now_et,
                    mode=mode,
                )
            except Exception as error:
                states[metric_id] = _failed_from_prior(
                    metric_id, prior=prior, attempted_at=attempted_at, error=error
                )

        attempted_collectors.add("fred_iorb")
        prior = states["iorb"]
        try:
            assert_metric_network_eligible(bundle, "iorb")
            observations = collectors.fred(
                "IORB", observation_start=fred_start, scale=1
            )
            states["iorb"] = _success_with_history(
                "iorb",
                observations,
                prior=prior,
                frequency="policy_event",
                attempted_at=attempted_at,
                now_et=now_et,
                mode=mode,
            )
        except Exception as error:
            states["iorb"] = _failed_from_prior(
                "iorb", prior=prior, attempted_at=attempted_at, error=error
            )

        for collector_id, metric_id, fetch in (
            ("treasury_tga", "tga_daily", lambda: collectors.tga()),
            ("nyfed_on_rrp", "on_rrp_accepted", lambda: collectors.on_rrp()),
        ):
            attempted_collectors.add(collector_id)
            prior = states[metric_id]
            try:
                assert_metric_network_eligible(bundle, metric_id)
                observations = fetch()
                states[metric_id] = _success_with_history(
                    metric_id,
                    observations,
                    prior=prior,
                    frequency="business_daily",
                    attempted_at=attempted_at,
                    now_et=now_et,
                    mode=mode,
                )
            except Exception as error:
                states[metric_id] = _failed_from_prior(
                    metric_id, prior=prior, attempted_at=attempted_at, error=error
                )

        attempted_collectors.add("nyfed_srf")
        prior = states["srf_accepted"]
        try:
            assert_metric_network_eligible(bundle, "srf_accepted")
            raw_operations = collectors.srf_operations()
            exercise_operation_ids = {
                item["operation_id"]
                for item in bundle.nyfed_operational_readiness["exercises"]
                if item["operation_type"] == "SRF"
            }
            daily_srf = aggregate_srf_operations(
                raw_operations, exercise_operation_ids=exercise_operation_ids
            )
            releases: dict[str, list[str]] = {}
            for operation in raw_operations:
                released_at = operation.get("released_at")
                if isinstance(released_at, str):
                    releases.setdefault(operation["operation_date"], []).append(released_at)
            observations = [
                {
                    **row,
                    "value": row["accepted_amount_usd_bn"],
                    "released_at": max(releases.get(row["date"], []), default=None),
                }
                for row in daily_srf
            ]
            states["srf_accepted"] = _success_with_history(
                "srf_accepted",
                observations,
                prior=prior,
                frequency="business_daily",
                attempted_at=attempted_at,
                now_et=now_et,
                mode=mode,
            )
        except Exception as error:
            states["srf_accepted"] = _failed_from_prior(
                "srf_accepted", prior=prior, attempted_at=attempted_at, error=error
            )

    if h41:
        attempted_collectors.add("fred_h41")
        for metric_id, (series_id, scale) in H41_SERIES.items():
            prior = states[metric_id]
            try:
                assert_metric_network_eligible(bundle, metric_id)
                observations = collectors.fred(
                    series_id, observation_start=fred_start, scale=scale
                )
                state = _success_with_history(
                    metric_id,
                    observations,
                    prior=prior,
                    frequency="weekly",
                    attempted_at=attempted_at,
                    now_et=now_et,
                    mode=mode,
                )
                h41_freshness, h41_health = h41_freshness_for(
                    state.observation_date, now_et=now_et
                )
                states[metric_id] = replace(
                    state, freshness=h41_freshness, health=h41_health
                )
            except Exception as error:
                states[metric_id] = _failed_from_prior(
                    metric_id, prior=prior, attempted_at=attempted_at, error=error
                )

    spreads = build_iorb_spreads(
        {metric_id: states[metric_id].observations for metric_id in RATE_IDS},
        states["iorb"].observations,
    )
    for rate_id in RATE_IDS:
        metric_id = f"{rate_id}_iorb_spread_bp"
        states[metric_id] = derived_state(
            metric_id,
            spreads[metric_id],
            (states[rate_id], states["iorb"]),
            attempted_at=attempted_at,
        )

    prior_settlements, settlement_state = _settlement_state_from_prior(
        root, attempted_at=attempted_at
    )
    settlements = prior_settlements
    if daily:
        attempted_collectors.add("treasury_auctions")
        try:
            assert_source_network_eligible(bundle, "treasury_fiscaldata")
            auctions = collectors.auctions(
                start=now_et.date() - timedelta(days=366 * 3 + 14)
            )
            normalized_auctions = [
                {
                    **auction,
                    "offering_amount_usd_bn": auction["offering_usd_bn"],
                }
                for auction in auctions
            ]
            settlements = add_large_settlement_context(
                aggregate_treasury_settlements(normalized_auctions),
                trailing_years=3,
                percentile=bundle.alert_rules["alerts"]["technical_context"][
                    "large_treasury_settlement_percentile"
                ],
                minimum_nonzero_samples=bundle.alert_rules["alerts"]["technical_context"][
                    "large_treasury_settlement_min_nonzero_samples"
                ],
            )
            settlement_state = SeriesState(
                metric_id="treasury_settlement_calendar",
                observations=[
                    {
                        "date": row["date"],
                        "value": row["treasury_settlement_usd_bn"],
                    }
                    for row in settlements
                ],
                health="OK",
                freshness="FRESH",
                last_success_at=attempted_at,
                last_attempt_at=attempted_at,
                updated_at=attempted_at,
            )
        except Exception as error:
            settlement_state = SeriesState(
                **{
                    **settlement_state.__dict__,
                    "health": "STALE" if settlements else "ERROR",
                    "freshness": "STALE" if settlements else "UNKNOWN",
                    "last_attempt_at": attempted_at,
                    "failure_reason": _failure_reason(error),
                }
            )

    observation_calendar = [point["date"] for point in states["sofr"].observations]
    events = _technical_events(
        bundle,
        observation_calendar=observation_calendar,
        settlements=settlements,
        current_new_york_date=now_et.date(),
    )
    event_by_date = {event["date"]: event for event in events}
    market_date = states["sofr_iorb_spread_bp"].observation_date
    technical_flags = (
        list(event_by_date[market_date]["flags"])
        if market_date in event_by_date
        else []
    )

    statistics: dict[str, dict[str, int | float | None]] = {
        metric_id: spread_observation_stats(states[metric_id].observations)
        for metric_id in SPREAD_IDS
    }
    for metric_id in H41_SERIES:
        statistics[metric_id] = h41_weekly_stats(states[metric_id].observations)
    reserve_context = h41_change_4w_context(states["reserve_balances"].observations)
    statistics["reserve_balances"] = {
        **statistics["reserve_balances"],
        **reserve_context,
    }
    on_rrp_points = states["on_rrp_accepted"].observations
    on_rrp_floor = on_rrp_near_floor_context(on_rrp_points)
    statistics["on_rrp_accepted"] = {
        **generic_statistics(on_rrp_points),
        "near_floor_sample_size": on_rrp_floor["sample_size"],
        "near_floor_percentile_rank": on_rrp_floor["percentile_rank"],
        "near_floor_threshold_percentile": 0.10,
        "near_floor_minimum_samples": 20,
    }
    srf_points = states["srf_accepted"].observations
    statistics["srf_accepted"] = {
        "sample_size": len(srf_points),
        "nontechnical_positive_use_streak": (
            srf_nontechnical_positive_use_streak(srf_points)
        ),
        "positive_nontechnical_latest_3": sum(
            point.get(
                "alert_eligible_accepted_amount_usd_bn",
                point.get("accepted_amount_usd_bn", point.get("value", 0)),
            )
            > 0
            and not point.get("technical_exercise", False)
            for point in srf_points[-3:]
        ),
    }

    sofr_stats = statistics["sofr_iorb_spread_bp"]
    confirmations = {
        rate_id: statistics[f"{rate_id}_iorb_spread_bp"]
        for rate_id in ("effr", "tgcr", "bgcr")
    }
    input_statuses = [
        states[metric_id].health
        for metric_id in (
            "sofr_iorb_spread_bp",
            "effr_iorb_spread_bp",
            "tgcr_iorb_spread_bp",
            "bgcr_iorb_spread_bp",
            "srf_accepted",
            "reserve_balances",
        )
    ]
    rule = liquidity_alert_rule(
        latest_sofr_iorb_bp=sofr_stats["latest"],
        positive_streak=int(sofr_stats["positive_streak"] or 0),
        funding_confirmation_stats=confirmations,
        srf_recent_operation_days=[
            {
                "date": point["date"],
                "accepted_amount_usd_bn": point.get(
                    "alert_eligible_accepted_amount_usd_bn",
                    point.get("accepted_amount_usd_bn", point.get("value", 0)),
                ),
                "technical_exercise": bool(point.get("technical_exercise", False)),
            }
            for point in srf_points
        ],
        reserve_change_4w=reserve_context["change_4w"],
        reserve_trailing_5y_p10=reserve_context["trailing_5y_p10"],
        technical_flags=technical_flags,
        input_statuses=input_statuses,
        watch_threshold_bp=float(
            bundle.alert_rules["alerts"]["liquidity_fuel"]["sofr_iorb_watch_bp"]
        ),
        positive_streak_required=int(
            bundle.alert_rules["alerts"]["liquidity_fuel"][
                "positive_streak_observations"
            ]
        ),
    )
    assessment = {"NORMAL": "NEUTRAL"}.get(rule["level"], rule["level"])

    metric_records: dict[str, dict[str, Any]] = {}
    registry_for_manifest: list[dict[str, Any]] = []
    for registry_metric in bundle.metric_registry["metrics"]:
        metric_id = registry_metric["metric_id"]
        effective = effective_metric_state(registry_metric)
        availability = effective.availability.value
        state = states.get(metric_id)
        flags = []
        if state and state.observation_date in event_by_date:
            flags = event_by_date[state.observation_date]["flags"]
        provenance = []
        for source_id in registry_metric["source_ids"]:
            detail = source_details(bundle, source_id)
            if state and availability in {"ACTIVE_FREE", "ACTIVE_PROXY"}:
                detail["retrieved_at"] = state.last_attempt_at
            provenance.append(detail)
        extra: dict[str, Any] = {
            "provenance": provenance,
            "unavailability_reason": registry_metric.get("reason") or effective.reason,
        }
        if metric_id == "srf_accepted" and srf_points:
            extra["details"] = {
                key: value
                for key, value in srf_points[-1].items()
                if key not in {"date", "value"}
            }
        if metric_id == "on_rrp_accepted" and state and state.observations:
            extra["details"] = {
                key: value
                for key, value in state.observations[-1].items()
                if key not in {"date", "value"}
            }
        record = metric_record(
            bundle,
            registry_metric,
            state=state,
            attempted_at=attempted_at,
            statistics=statistics.get(metric_id),
            technical_flags=flags,
            effective_availability=availability,
            extra=extra,
        )
        if metric_id == "on_rrp_accepted":
            record["context"]["near_floor_context"] = on_rrp_floor
        metric_records[metric_id] = record
        registry_for_manifest.append(
            {**registry_metric, "effective_availability": availability}
        )

    price_available = states["sofr_iorb_spread_bp"].health == "OK"
    confirmation_available = all(
        states[f"{rate_id}_iorb_spread_bp"].health == "OK"
        for rate_id in ("effr", "tgcr", "bgcr")
    )
    srf_available = states["srf_accepted"].health == "OK"
    reserve_available = states["reserve_balances"].health == "OK"
    price_triggered = bool(
        sofr_stats["latest"] is not None
        and (
            sofr_stats["latest"]
            > float(
                bundle.alert_rules["alerts"]["liquidity_fuel"][
                    "sofr_iorb_watch_bp"
                ]
            )
            or int(sofr_stats["positive_streak"] or 0)
            >= int(
                bundle.alert_rules["alerts"]["liquidity_fuel"][
                    "positive_streak_observations"
                ]
            )
        )
    )
    p0_blocks = [
        {
            "id": "funding_price",
            "label": "SOFR−IORB",
            "available": price_available,
            "triggered": price_triggered if price_available else None,
            "status": ("WATCH" if price_triggered else "NORMAL") if price_available else "UNAVAILABLE",
            "summary": "+3bp 或連續三個正數 observations 觸發 WATCH。",
        },
        {
            "id": "funding_confirmations",
            "label": "EFFR / TGCR / BGCR confirmation",
            "available": confirmation_available,
            "triggered": rule["funding_confirmation_count"] > 0 if confirmation_available else None,
            "status": f"{rule['funding_confirmation_count']}/3 UP" if confirmation_available else "UNAVAILABLE",
            "summary": "change_5obs 與 5-observation slope 同時向上先計確認。",
        },
        {
            "id": "srf_backstop",
            "label": "SRF accepted",
            "available": srf_available,
            "triggered": rule["srf_positive_operation_days_latest_3"] >= 2 if srf_available else None,
            "status": f"{rule['srf_positive_operation_days_latest_3']}/3 POSITIVE" if srf_available else "UNAVAILABLE",
            "summary": "技術演習按官方 allowlist 標記，唔按金額猜測。",
        },
        {
            "id": "reserve_quantity",
            "label": "Reserve balances 4W",
            "available": reserve_available,
            "triggered": rule["reserve_4w_at_or_below_trailing_5y_p10"] if reserve_available else None,
            "status": (
                "P10 BREACH"
                if rule["reserve_4w_at_or_below_trailing_5y_p10"]
                else "NO P10 BREACH"
            ) if reserve_available else "UNAVAILABLE",
            "summary": "2.9T/2.8T/2.5T 只係參考線，並非固定壓力門檻。",
        },
    ]
    liquidity_switch = {
        "mode": "DETERMINISTIC",
        "assessment": assessment,
        "available_blocks": sum(block["available"] for block in p0_blocks),
        "total_blocks": len(p0_blocks),
        "confidence": rule["confidence"],
        "evidence_blocks": p0_blocks,
        "summary": "Overview overall assessment 只以 Liquidity Fuel P0 規則為基礎。",
    }

    sources = {
        "nyfed_rates": collector_source_record(
            bundle,
            "nyfed_rates",
            "nyfed_markets",
            [states[metric_id] for metric_id in RATE_IDS],
            attempted_at=attempted_at,
        ),
        "fred_iorb": collector_source_record(
            bundle, "fred_iorb", "fred_government", [states["iorb"]], attempted_at=attempted_at
        ),
        "fred_h41": collector_source_record(
            bundle,
            "fred_h41",
            "fred_government",
            [states[metric_id] for metric_id in H41_SERIES],
            attempted_at=attempted_at,
        ),
        "treasury_tga": collector_source_record(
            bundle, "treasury_tga", "treasury_fiscaldata", [states["tga_daily"]], attempted_at=attempted_at
        ),
        "nyfed_on_rrp": collector_source_record(
            bundle, "nyfed_on_rrp", "nyfed_markets", [states["on_rrp_accepted"]], attempted_at=attempted_at
        ),
        "nyfed_srf": collector_source_record(
            bundle, "nyfed_srf", "nyfed_markets", [states["srf_accepted"]], attempted_at=attempted_at
        ),
        "treasury_auctions": collector_source_record(
            bundle, "treasury_auctions", "treasury_fiscaldata", [settlement_state], attempted_at=attempted_at
        ),
    }
    for collector_id, source in sources.items():
        if collector_id not in attempted_collectors:
            relevant_states = {
                "nyfed_rates": [states[metric_id] for metric_id in RATE_IDS],
                "fred_iorb": [states["iorb"]],
                "fred_h41": [states[metric_id] for metric_id in H41_SERIES],
                "treasury_tga": [states["tga_daily"]],
                "nyfed_on_rrp": [states["on_rrp_accepted"]],
                "nyfed_srf": [states["srf_accepted"]],
                "treasury_auctions": [settlement_state],
            }[collector_id]
            source["last_attempt_at"] = max(
                (state.last_attempt_at for state in relevant_states if state.last_attempt_at),
                default=None,
            )
            source["updated_at"] = max(
                (state.updated_at for state in relevant_states if state.updated_at),
                default=None,
            )

    alerts = []
    if assessment not in {"NEUTRAL"}:
        alerts.append(
            {
                "level": assessment,
                "title": "Liquidity Fuel P0 assessment",
                "detail": "技術事件只降低 confidence；severity 由獨立 evidence blocks 決定。",
            }
        )
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": attempted_at,
        "pipeline_updated_at": attempted_at,
        "market_date": market_date,
        "overall_assessment": assessment,
        "switches": {
            "liquidity_fuel": liquidity_switch,
            "market_ignition": {
                "mode": "EVIDENCE_ONLY",
                "assessment": None,
                "available_blocks": 0,
                "total_blocks": 4,
                "confidence": "UNKNOWN",
                "evidence_blocks": _future_evidence_blocks("market_ignition"),
                "summary": "P1 production evidence 未上線；不產生 WATCH/STRESS。",
            },
            "fundamental_exit": {
                "mode": "EVIDENCE_ONLY",
                "assessment": None,
                "available_blocks": 0,
                "total_blocks": 4,
                "confidence": "UNKNOWN",
                "evidence_blocks": _future_evidence_blocks("fundamental_exit"),
                "summary": "P3 production evidence 未上線；不產生 WATCH/STRESS。",
            },
        },
        "metrics": metric_records,
        "technical_context": (
            [
                {
                    "date": market_date,
                    "flags": technical_flags,
                    "note": event_by_date[market_date]["note"],
                }
            ]
            if market_date in event_by_date and technical_flags
            else []
        ),
        "alerts": alerts,
        "explanations": _explanation(
            assessment,
            rule["confidence"],
            sofr_stats,
            metric_records["sofr_iorb_spread_bp"]["quality"],
            rule,
            technical_flags,
        ),
        "sources": sources,
        "source_health": source_health_counts(sources),
        "composite": rule,
        **availability_counts(metric_records),
    }
    manifest = manifest_record(registry_for_manifest, attempted_at)
    series_by_id = {
        metric_id: series_record(metric, states.get(metric_id))
        for metric_id, metric in metric_records.items()
    }
    validate_publication(snapshot, manifest, series_by_id)
    return Publication(
        snapshot=snapshot,
        manifest=manifest,
        series_by_id=series_by_id,
        alerts={
            "schema_version": SCHEMA_VERSION,
            "generated_at": attempted_at,
            "alerts": alerts,
        },
        events={
            "schema_version": SCHEMA_VERSION,
            "generated_at": attempted_at,
            "events": events,
        },
    )


def write_stage(publication: Publication, stage_dir: str | Path) -> Path:
    """Write a validated complete publication to an explicit staging directory."""

    validate_publication(
        publication.snapshot, publication.manifest, publication.series_by_id
    )
    validate_alerts_file(publication.alerts)
    validate_events_file(publication.events)
    stage = Path(stage_dir)
    if stage.exists() and any(stage.iterdir()):
        raise PublicationError(f"stage directory is not empty: {stage}")
    stage.mkdir(parents=True, exist_ok=True)
    atomic_json(stage / "snapshot.json", publication.snapshot)
    atomic_json(stage / "manifest.json", publication.manifest)
    atomic_json(stage / "alerts.json", publication.alerts)
    atomic_json(stage / "events.json", publication.events)
    for metric_id, series in publication.series_by_id.items():
        atomic_json(stage / "series" / f"{metric_id}.json", series)
    return stage


def load_stage(stage_dir: str | Path) -> Publication:
    """Read and validate an on-disk candidate before final promotion."""

    stage = Path(stage_dir)
    expected_entries = {"snapshot.json", "manifest.json", "alerts.json", "events.json", "series"}
    actual_entries = {path.name for path in stage.iterdir()} if stage.is_dir() else set()
    if actual_entries != expected_entries:
        raise PublicationError("stage contains missing or unexpected top-level artifacts")
    snapshot = read_json(stage / "snapshot.json")
    manifest = read_json(stage / "manifest.json")
    alerts = read_json(stage / "alerts.json")
    events = read_json(stage / "events.json")
    if not all(isinstance(value, Mapping) for value in (snapshot, manifest, alerts, events)):
        raise PublicationError("stage is missing a required v2 artifact")
    metric_ids = [item["metric_id"] for item in manifest.get("metrics", [])]
    series_by_id = {
        metric_id: read_json(stage / "series" / f"{metric_id}.json")
        for metric_id in metric_ids
    }
    if any(not isinstance(value, Mapping) for value in series_by_id.values()):
        raise PublicationError("stage is missing a required v2 series file")
    series_directory = stage / "series"
    actual_series_entries = {
        path.name for path in series_directory.iterdir()
    } if series_directory.is_dir() else set()
    expected_series_entries = {f"{metric_id}.json" for metric_id in metric_ids}
    if actual_series_entries != expected_series_entries:
        raise PublicationError("stage contains missing or unexpected series files")
    validate_publication(snapshot, manifest, series_by_id)
    validate_alerts_file(alerts)
    validate_events_file(events)
    if alerts["generated_at"] != snapshot["generated_at"] or alerts["alerts"] != snapshot["alerts"]:
        raise PublicationError("standalone alerts must match snapshot alerts")
    if events["generated_at"] != snapshot["generated_at"]:
        raise PublicationError("standalone events timestamp must match snapshot")
    return Publication(
        snapshot=dict(snapshot),
        manifest=dict(manifest),
        series_by_id={key: dict(value) for key, value in series_by_id.items()},
        alerts=dict(alerts),
        events=dict(events),
    )


def promote_stage(
    stage_dir: str | Path, *, data_dir: str | Path = Path("public/data")
) -> dict[str, Any]:
    """Revalidate and atomically promote a staged publication.

    A CI stage may live in ``RUNNER_TEMP`` on another filesystem.  In that case
    it is copied into a fresh directory adjacent to the target, revalidated,
    and only that adjacent directory participates in the atomic rename.
    """

    original = Path(stage_dir)
    publication = load_stage(original)
    target = Path(data_dir)
    if original.parent == target.parent:
        promote_data_directory(original, target)
    else:
        adjacent = staged_data_directory(target.parent)
        try:
            shutil.copytree(original, adjacent, dirs_exist_ok=True)
            load_stage(adjacent)
            promote_data_directory(adjacent, target)
        except Exception:
            if adjacent.exists():
                shutil.rmtree(adjacent)
            raise
        shutil.rmtree(original)
    return publication.snapshot


def run(
    mode: str = "incremental",
    *,
    group: str = "all",
    data_dir: str | Path = Path("public/data"),
    stage_only: bool = False,
    stage_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compatibility API for local builds and the workflow CLI."""

    publication = build_release(mode=mode, group=group, data_dir=data_dir)
    target = Path(data_dir)
    if stage_dir is None:
        if stage_only:
            raise ValueError("stage_dir is required when stage_only=True")
        stage = staged_data_directory(target.parent)
    else:
        stage = Path(stage_dir)
    write_stage(publication, stage)
    if not stage_only:
        promote_stage(stage, data_dir=target)
    return publication.snapshot
