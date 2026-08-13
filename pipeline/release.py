"""Phased orchestration for the schema 2.2.0 static publication.

The module deliberately keeps collection, transformation, contract validation,
staging, and promotion as separate operations.  GitHub Actions can therefore
hold a complete candidate artifact outside ``public/data`` while the Python and
frontend gates run, then perform one whole-directory promotion.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import math
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
from pipeline.collectors.fred_p2 import fetch_series_bundle as fetch_fred_p2_series
from pipeline.collectors.cftc import fetch_tff_futures_only
from pipeline.collectors.nyfed import (
    fetch_on_rrp,
    fetch_reference_rate,
    fetch_srf_operations,
)
from pipeline.collectors.sec_form4 import (
    Form4Collection,
    SecHttpClient,
    collect_form4_window,
)
from pipeline.collectors.sec_companyfacts import fetch_company_bundles
from pipeline.collectors.treasury import fetch_auctions, fetch_tga
from pipeline.config import (
    ACTIVE_P3_AUTOMATED_METRIC_IDS,
    ACTIVE_P2_METRIC_IDS,
    CANONICAL_P0_METRIC_IDS,
    CANONICAL_P1_CFTC_METRIC_IDS,
    MANUAL_P3_METRIC_IDS,
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
from pipeline.form4_ledger import (
    build_ledger_package,
    load_ledger,
    merge_last_good_entries,
    public_ledger_entry,
    write_ledger_atomic,
)
from pipeline.manual_signals import (
    DEFAULT_MANUAL_SIGNALS_PATH,
    build_manual_metric_states,
    load_manual_signals,
)
from pipeline.rules.p0 import liquidity_alert_rule
from pipeline.rules.p0_video_model import evaluate_video_p0_model
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
from pipeline.transforms.p1 import (
    cftc_position_series,
    cftc_position_statistics,
    common_direction,
    positioning_direction,
)
from pipeline.transforms.p2_macro import (
    build_nonfinancial_equities_gdp_proxy,
    nonfinancial_equities_gdp_statistics,
)
from pipeline.transforms.p2_form4 import form4_metric_observation
from pipeline.transforms.p3_capex import (
    ACCELERATION_METRIC_ID,
    CAPEX_METRIC_ID,
    build_hyperscaler_capex,
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
CFTC_METRICS = {
    "cftc_e_mini_sp500_asset_manager_net_pct_oi": ("13874A", "asset_manager"),
    "cftc_e_mini_sp500_leveraged_funds_net_pct_oi": ("13874A", "leveraged_funds"),
    "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi": ("20974+", "asset_manager"),
    "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi": ("20974+", "leveraged_funds"),
}
P2_MACRO_ID = "nonfinancial_equities_gdp_proxy"
P2_FORM4_ID = "sec_form4_nonderivative_ps_count_ratio_20d"
P3_CAPEX_ID = CAPEX_METRIC_ID
P3_ACCELERATION_ID = ACCELERATION_METRIC_ID
P3_AUTOMATED_IDS = (P3_CAPEX_ID, P3_ACCELERATION_ID)
P3_MANUAL_IDS = tuple(sorted(MANUAL_P3_METRIC_IDS))
P3_STATISTIC_KEYS = (
    "aggregate_cash_capex_usd_bn",
    "qoq_percent_change",
    "yoy_percent_change",
    "qoq_acceleration_pp",
    "yoy_acceleration_pp",
    "company_breadth",
    "company_total",
    "company_breadth_ratio",
    "finance_lease_disclosure_breadth",
    "manual_review_count",
)
P3_CAVEATS = (
    "Cash CapEx is quarterized from fiscal YTD cash-flow facts; Q4 is fiscal-year cash CapEx less nine-month cash CapEx.",
    "Finance-lease right-of-use asset additions are shown separately and are never added to cash CapEx.",
    "SEC facts may be amended or restated; the latest accepted filing for each exact context is used.",
    "This is evidence coverage and direction, not an automatic WATCH or STRESS assessment.",
)


def _collect_sec_form4_window(**kwargs: Any) -> Form4Collection:
    cache_dir = os.environ.get("SEC_FORM4_CACHE_DIR")
    client = SecHttpClient(cache_dir=cache_dir if cache_dir else None)
    return collect_form4_window(client=client, **kwargs)


@dataclass(frozen=True)
class CollectorFunctions:
    """Injectable network boundary used by deterministic fixture tests."""

    rate: Callable[..., list[dict[str, Any]]] = fetch_reference_rate
    fred: Callable[..., list[dict[str, Any]]] = fetch_fred_series
    on_rrp: Callable[..., list[dict[str, Any]]] = fetch_on_rrp
    srf_operations: Callable[..., list[dict[str, Any]]] = fetch_srf_operations
    tga: Callable[..., list[dict[str, Any]]] = fetch_tga
    auctions: Callable[..., list[dict[str, Any]]] = fetch_auctions
    cftc: Callable[..., dict[str, list[dict[str, Any]]]] = fetch_tff_futures_only
    fred_p2: Callable[..., dict[str, Any]] = fetch_fred_p2_series
    sec_form4: Callable[..., Form4Collection] = _collect_sec_form4_window
    sec_companyfacts: Callable[..., dict[str, Any]] = fetch_company_bundles


@dataclass(frozen=True)
class Publication:
    snapshot: dict[str, Any]
    manifest: dict[str, Any]
    series_by_id: dict[str, dict[str, Any]]
    alerts: dict[str, Any]
    events: dict[str, Any]
    sec_form4_ledger: dict[str, Any]


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


def _fred_observations_as_of(
    observations: Sequence[Mapping[str, Any]],
    *,
    observation_end: date,
    require_nonempty: bool,
) -> list[dict[str, Any]]:
    """Keep only FRED observations effective by the New York market date.

    ``observation_end`` is also sent to FRED, but this publication-boundary
    check protects injected collectors, schema drift, and a last-good series
    that was written before the API bound existed.
    """

    eligible: list[dict[str, Any]] = []
    for point in observations:
        raw_date = point.get("date")
        if not isinstance(raw_date, str):
            raise ValueError("FRED observation missing date")
        try:
            effective_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError("FRED observation has invalid date") from exc
        if effective_date <= observation_end:
            eligible.append(dict(point))
    if require_nonempty and not eligible:
        raise ValueError(
            "FRED collector returned no observations effective on or before "
            f"{observation_end.isoformat()}"
        )
    return eligible


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


def _cftc_expected_next_update(
    observation_date: str | None,
    released_at: str | None,
    release_schedule: Sequence[Mapping[str, Any]],
) -> str | None:
    """Return the next expected TFF publication date, never H.4.1 Thursday."""

    if observation_date is None:
        return None
    if released_at:
        anchor = datetime.fromisoformat(released_at.replace("Z", "+00:00")).date()
    else:
        anchor = date.fromisoformat(observation_date)
    future = [
        item["release_date"]
        for item in release_schedule
        if date.fromisoformat(item["release_date"]) > anchor
        and date.fromisoformat(item["observation_date"])
        > date.fromisoformat(observation_date)
    ]
    return min(future, default=None)


def _cftc_freshness_for(
    observation_date: str | None,
    released_at: str | None,
    *,
    now_et: datetime,
    release_schedule: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    if not release_schedule:
        # A reviewed schedule is part of the source contract.  Never invent a
        # Friday cadence when the schedule is missing or failed validation.
        return "UNKNOWN", "ERROR"
    freshness, health = freshness_for(observation_date, "weekly", now_et=now_et)
    if observation_date is None or health == "STALE":
        return freshness, health
    next_release = _cftc_expected_next_update(
        observation_date, released_at, release_schedule
    )
    if next_release is None:
        return freshness, health
    # CFTC's normal TFF release is Friday 15:30 ET.  Allow two hours for PRE
    # propagation; actual :updated_at remains authoritative when a row arrives.
    release_deadline = datetime.combine(
        date.fromisoformat(next_release),
        datetime.min.time(),
        tzinfo=NEW_YORK,
    ).replace(hour=17, minute=30)
    expected_report_date = next(
        date.fromisoformat(item["observation_date"])
        for item in release_schedule
        if item["release_date"] == next_release
    )
    if now_et > release_deadline and date.fromisoformat(observation_date) < expected_report_date:
        return "LATE", "NOT_RELEASED_YET"
    return freshness, health


def _quarterly_proxy_freshness_for(
    observation_date: str | None, *, now_et: datetime
) -> tuple[str, str]:
    """Evaluate the lagged exact-common-quarter proxy on its own cadence."""

    if observation_date is None:
        return "UNKNOWN", "ERROR"
    observed = date.fromisoformat(observation_date)
    today = now_et.date()
    if observed > today:
        return "UNKNOWN", "ERROR"
    observed_ordinal = observed.year * 4 + (observed.month - 1) // 3
    current_ordinal = today.year * 4 + (today.month - 1) // 3
    quarter_lag = current_ordinal - observed_ordinal
    # Z.1 normally arrives after GDP.  Two calendar quarters of apparent lag
    # can therefore still be the newest exact common quarter.
    if quarter_lag <= 2:
        return "FRESH", "OK"
    if quarter_lag == 3:
        return "LATE", "OK"
    return "STALE", "STALE"


def _p2_macro_statistics(
    observations: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[str, int | float | None],
    dict[str, str | None],
    float | None,
]:
    latest = nonfinancial_equities_gdp_statistics(observations)
    statistics: dict[str, int | float | None] = {
        key: latest[key]
        for key in (
            "equity_usd_bn",
            "gdp_usd_bn",
            "qoq_percent_change",
            "yoy_percent_change",
            "percentile_10y",
            "percentile_10y_sample_size",
        )
    }
    context = {
        "equity_observation_date": (
            observations[-1].get("equities_source_date") if observations else None
        ),
        "gdp_observation_date": (
            observations[-1].get("gdp_source_date") if observations else None
        ),
        "common_quarter": observations[-1].get("quarter") if observations else None,
    }
    return statistics, context, latest.get("change_1_quarter_pp")


def _p3_capex_payload(
    observations: Sequence[Mapping[str, Any]],
    *,
    acceleration_metric: bool,
) -> tuple[
    dict[str, int | float | None],
    dict[str, Any],
    float | None,
    str | None,
]:
    """Rebuild the public P3 endpoint from the persisted full series.

    The same helper is used after a fresh SEC collection and on a non-due
    republish, so the snapshot never depends on transient in-memory collector
    output that is absent from the canonical series file.
    """

    if not observations:
        empty_statistics = {key: None for key in P3_STATISTIC_KEYS}
        empty_statistics.update(
            {
                "company_breadth": 0,
                "company_total": 4,
                "finance_lease_disclosure_breadth": 0,
                "manual_review_count": 0,
            }
        )
        return (
            {**empty_statistics, "quarter_count": 0},
            {
                "fundamental": {
                    "aggregate_direction": "UNKNOWN",
                    "company_breadth": 0,
                    "company_total": 4,
                    "companies": [],
                    "caveats": list(P3_CAVEATS),
                }
            },
            None,
            None,
        )
    latest = observations[-1]
    previous = observations[-2] if len(observations) > 1 else None
    statistics = {
        key: latest.get(key)
        for key in P3_STATISTIC_KEYS
    }
    statistics["quarter_count"] = len(observations)
    companies = latest.get("companies")
    details = {
        "fundamental": {
            "aggregate_direction": latest.get("aggregate_direction", "UNKNOWN"),
            "company_breadth": latest.get("company_breadth", 0),
            "company_total": latest.get("company_total", 4),
            "companies": (
                [dict(company) for company in companies]
                if isinstance(companies, list)
                else []
            ),
            "caveats": list(P3_CAVEATS),
        }
    }
    value_key = (
        "yoy_acceleration_pp"
        if acceleration_metric
        else "aggregate_cash_capex_usd_bn"
    )
    change = None
    if previous is not None:
        current_value = latest.get(value_key)
        previous_value = previous.get(value_key)
        if isinstance(current_value, (int, float)) and not isinstance(
            current_value, bool
        ) and isinstance(previous_value, (int, float)) and not isinstance(
            previous_value, bool
        ):
            change = round(float(current_value) - float(previous_value), 6)
    release_candidates = [
        company.get("accepted_at")
        for company in details["fundamental"]["companies"]
        if isinstance(company.get("accepted_at"), str)
    ]
    return statistics, details, change, max(release_candidates, default=None)


def _manual_series_state(
    payload: Mapping[str, Any], *, now_et: datetime
) -> SeriesState | None:
    """Convert reviewed local CSV evidence into a non-network SeriesState."""

    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        return None
    observation_date = payload.get("observation_date")
    if not isinstance(observation_date, str):
        raise ValueError("active P3 manual evidence requires observation_date")
    lag = (now_et.date() - date.fromisoformat(observation_date)).days
    if lag < 0:
        raise ValueError("P3 manual evidence must not be future-dated")
    reviewed_at = payload.get("latest_reviewed_at")
    released_at = payload.get("latest_filing_accepted_at")
    for label, value in (("reviewed_at", reviewed_at), ("released_at", released_at)):
        if not isinstance(value, str):
            raise ValueError(f"active P3 manual evidence requires {label}")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed > now_et.astimezone(timezone.utc):
            raise ValueError(f"P3 manual evidence {label} must not be future-dated")
    stale = lag > 120
    return SeriesState(
        metric_id=str(payload["metric_id"]),
        observations=[dict(point) for point in observations],
        health="STALE" if stale else "OK",
        freshness="STALE" if stale else "FRESH",
        last_success_at=reviewed_at,
        last_attempt_at=reviewed_at,
        failure_reason=None,
        released_at=released_at,
        updated_at=reviewed_at,
    )


def _common_p3_direction(directions: Sequence[str]) -> str:
    if not directions or "UNKNOWN" in directions:
        return "UNKNOWN"
    return directions[0] if len(set(directions)) == 1 else "MIXED"


def _preserve_source_timestamps_when_not_due(
    state: SeriesState, *, data_dir: Path, metric_id: str
) -> SeriesState:
    """Republish an unattempted collector without inventing a new attempt."""

    prior_payload = _prior_series_payload(data_dir, metric_id)
    prior_quality = (
        prior_payload.get("quality")
        if isinstance(prior_payload.get("quality"), Mapping)
        else {}
    )
    return replace(
        state,
        last_attempt_at=(
            prior_quality.get("last_attempt_at")
            if isinstance(prior_quality.get("last_attempt_at"), str)
            else None
        ),
        updated_at=(
            prior_payload.get("updated_at")
            if isinstance(prior_payload.get("updated_at"), str)
            else None
        ),
    )


def _empty_form4_ledger(*, as_of: date) -> dict[str, Any]:
    return build_ledger_package([], completed_index_days=(), as_of=as_of)


def _prior_form4_ledger(data_dir: Path, *, as_of: date) -> dict[str, Any]:
    path = data_dir / "ledgers" / "sec_form4"
    if not path.exists():
        return _empty_form4_ledger(as_of=as_of)
    return load_ledger(path)


def _merge_audit_rows(
    prior: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
) -> list[dict[str, Any]]:
    cutoff = as_of - timedelta(days=44)
    output: dict[str, dict[str, Any]] = {}
    for raw in (*prior, *current):
        if not isinstance(raw, Mapping):
            raise ValueError("SEC Form 4 audit row must be an object")
        row = dict(raw)
        raw_day = row.get("index_date")
        if not isinstance(raw_day, str):
            raise ValueError("SEC Form 4 audit row requires index_date")
        try:
            parsed_day = date.fromisoformat(raw_day)
        except ValueError as exc:
            raise ValueError("SEC Form 4 audit row has invalid index_date") from exc
        if parsed_day < cutoff:
            continue
        if parsed_day > as_of:
            raise ValueError("SEC Form 4 audit row is future-dated")
        if not isinstance(row.get("stage"), str) or not row["stage"]:
            raise ValueError("SEC Form 4 audit row requires stage")
        if not isinstance(row.get("reason"), str) or not row["reason"]:
            raise ValueError("SEC Form 4 audit row requires reason")
        key = repr(sorted(row.items()))
        output[key] = row
    return [output[key] for key in sorted(output)]


def _validate_form4_metric_against_ledger(
    snapshot: Mapping[str, Any],
    ledger: Mapping[str, Any],
    series_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    metric = snapshot["metrics"][P2_FORM4_ID]
    observation = form4_metric_observation(
        ledger,
        as_of=(
            date.fromisoformat(ledger["as_of"])
            if isinstance(ledger.get("as_of"), str)
            else None
        ),
    )
    if metric.get("value") != observation["value"]:
        raise PublicationError("SEC Form 4 snapshot value does not match ledger")
    if metric.get("statistics") != observation["statistics"]:
        raise PublicationError("SEC Form 4 snapshot statistics do not match ledger")
    for key, value in observation["technical_context"].items():
        if metric.get("context", {}).get(key) != value:
            raise PublicationError(
                f"SEC Form 4 snapshot context.{key} does not match ledger"
            )
    if metric.get("observation_date") != observation["date"]:
        raise PublicationError(
            "SEC Form 4 snapshot observation_date does not match ledger"
        )
    generated_at = snapshot.get("generated_at")
    try:
        generated_new_york_day = datetime.fromisoformat(
            str(generated_at).replace("Z", "+00:00")
        ).astimezone(NEW_YORK).date().isoformat()
    except (ValueError, TypeError) as exc:
        raise PublicationError("snapshot generated_at is invalid") from exc
    try:
        ledger_as_of = date.fromisoformat(str(ledger.get("as_of")))
    except ValueError as exc:
        raise PublicationError("SEC Form 4 ledger as_of is invalid") from exc
    if ledger_as_of > date.fromisoformat(generated_new_york_day):
        raise PublicationError("SEC Form 4 ledger must not be future-dated")
    if series_by_id is not None:
        series = series_by_id.get(P2_FORM4_ID)
        if not isinstance(series, Mapping):
            raise PublicationError("SEC Form 4 series is missing")
        observations = series.get("observations")
        if not isinstance(observations, list):
            raise PublicationError("SEC Form 4 series observations are invalid")
        endpoint = observations[-1] if observations else None
        if endpoint is None:
            if observation["date"] is not None:
                raise PublicationError("SEC Form 4 series endpoint is missing")
        elif (
            endpoint.get("date") != observation["date"]
            or endpoint.get("value") != observation["value"]
        ):
            raise PublicationError("SEC Form 4 series endpoint does not match ledger")


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
            ("volatility_term_structure", "Volatility term structure"),
            ("trend_positioning", "Trend / positioning"),
            ("options_tail_risk", "Options / tail risk"),
            ("crypto_cross_asset", "Crypto funding / cross-asset"),
        ),
        "fundamental_exit": (
            ("aggregate_capex_acceleration", "Aggregate CapEx acceleration"),
            ("orders_backlog", "Orders / backlog"),
            ("prepayments_commitments", "Prepayments / commitments"),
            ("company_breadth", "Company breadth"),
        ),
    }[layer]
    return [
        {
            "id": block_id,
            "label": label,
            "available": False,
            "triggered": None,
            "status": "UNAVAILABLE_FREE",
            "direction": "UNKNOWN",
            "confidence": "UNKNOWN",
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
    manual_signals_path: str | Path = DEFAULT_MANUAL_SIGNALS_PATH,
) -> Publication:
    """Collect and assemble a complete in-memory schema-v2 publication."""

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
    p2_macro_start = now_et.date() - timedelta(days=366 * 12)
    cftc_due = group in {"all", "daily", "weekly"}
    p2_macro_due = group in {"all", "monthly", "quarterly"}
    p2_form4_due = group in {"all", "daily", "weekly"}
    p3_capex_due = group in {"all", "quarterly"}
    manual_payloads = build_manual_metric_states(
        load_manual_signals(manual_signals_path)
    )

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
    # A non-daily schedule group can republish last-good data without calling
    # FRED.  Apply the same market-date boundary up front so an artifact
    # written by an older pipeline cannot keep leaking a future-effective
    # observation on monthly, quarterly, or manual runs.
    for metric_id in ("iorb", *H41_SERIES):
        state = states[metric_id]
        observations = _fred_observations_as_of(
            state.observations,
            observation_end=now_et.date(),
            require_nonempty=False,
        )
        if len(observations) == len(state.observations):
            continue
        if observations:
            freshness, health = (
                h41_freshness_for(observations[-1]["date"], now_et=now_et)
                if metric_id in H41_SERIES
                else freshness_for(
                    observations[-1]["date"],
                    bundle.metrics_by_id[metric_id]["frequency"],
                    now_et=now_et,
                )
            )
        else:
            freshness, health = "UNKNOWN", "ERROR"
        states[metric_id] = replace(
            state,
            observations=observations,
            # Filtering a future point can repair the earlier pipeline's
            # date-derived ERROR, but never clears a real collector failure.
            freshness=state.freshness if state.failure_reason else freshness,
            health=state.health if state.failure_reason else health,
        )
    for metric_id in CANONICAL_P1_CFTC_METRIC_IDS:
        state = _preserved_state(
            metric_id,
            data_dir=root,
            frequency="weekly",
            attempted_at=attempted_at,
            now_et=now_et,
        )
        if not cftc_due:
            prior_payload = _prior_series_payload(root, metric_id)
            prior_quality = (
                prior_payload.get("quality")
                if isinstance(prior_payload.get("quality"), Mapping)
                else {}
            )
            state = replace(
                state,
                last_attempt_at=(
                    prior_quality.get("last_attempt_at")
                    if isinstance(prior_quality.get("last_attempt_at"), str)
                    else None
                ),
                updated_at=(
                    prior_payload.get("updated_at")
                    if isinstance(prior_payload.get("updated_at"), str)
                    else None
                ),
            )
        cftc_freshness, cftc_health = _cftc_freshness_for(
            state.observation_date,
            state.released_at,
            now_et=now_et,
            release_schedule=bundle.cftc_release_schedule["releases"],
        )
        states[metric_id] = replace(
            state,
            freshness=max(
                (state.freshness, cftc_freshness),
                key=FRESHNESS_ORDER.__getitem__,
            ),
            health=max(
                (state.health, cftc_health),
                key=HEALTH_ORDER.__getitem__,
            ),
        )
    macro_state = _preserved_state(
        P2_MACRO_ID,
        data_dir=root,
        frequency="quarterly",
        attempted_at=attempted_at,
        now_et=now_et,
    )
    if not p2_macro_due:
        macro_state = _preserve_source_timestamps_when_not_due(
            macro_state, data_dir=root, metric_id=P2_MACRO_ID
        )
    macro_freshness, macro_health = _quarterly_proxy_freshness_for(
        macro_state.observation_date, now_et=now_et
    )
    states[P2_MACRO_ID] = replace(
        macro_state,
        freshness=max(
            (macro_state.freshness, macro_freshness),
            key=FRESHNESS_ORDER.__getitem__,
        ) if macro_state.failure_reason else macro_freshness,
        health=max(
            (macro_state.health, macro_health),
            key=HEALTH_ORDER.__getitem__,
        ) if macro_state.failure_reason else macro_health,
    )
    form4_state = _preserved_state(
        P2_FORM4_ID,
        data_dir=root,
        frequency="business_daily",
        attempted_at=attempted_at,
        now_et=now_et,
    )
    if not p2_form4_due:
        form4_state = _preserve_source_timestamps_when_not_due(
            form4_state, data_dir=root, metric_id=P2_FORM4_ID
        )
    states[P2_FORM4_ID] = form4_state
    for metric_id in P3_AUTOMATED_IDS:
        state = _preserved_state(
            metric_id,
            data_dir=root,
            frequency="quarterly",
            attempted_at=attempted_at,
            now_et=now_et,
        )
        if not p3_capex_due:
            state = _preserve_source_timestamps_when_not_due(
                state, data_dir=root, metric_id=metric_id
            )
        capex_freshness, capex_health = _quarterly_proxy_freshness_for(
            state.observation_date, now_et=now_et
        )
        states[metric_id] = replace(
            state,
            freshness=(
                max(
                    (state.freshness, capex_freshness),
                    key=FRESHNESS_ORDER.__getitem__,
                )
                if state.failure_reason
                else capex_freshness
            ),
            health=(
                max((state.health, capex_health), key=HEALTH_ORDER.__getitem__)
                if state.failure_reason
                else capex_health
            ),
        )
    for metric_id in P3_MANUAL_IDS:
        manual_state = _manual_series_state(manual_payloads[metric_id], now_et=now_et)
        if manual_state is not None:
            states[metric_id] = manual_state
    prior_form4_ledger = _prior_form4_ledger(root, as_of=now_et.date())
    form4_ledger = prior_form4_ledger
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
                "IORB",
                observation_start=fred_start,
                observation_end=now_et.date(),
                scale=1,
            )
            observations = _fred_observations_as_of(
                observations,
                observation_end=now_et.date(),
                require_nonempty=True,
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
                    series_id,
                    observation_start=fred_start,
                    observation_end=now_et.date(),
                    scale=scale,
                )
                observations = _fred_observations_as_of(
                    observations,
                    observation_end=now_et.date(),
                    require_nonempty=True,
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

    if cftc_due:
        attempted_collectors.add("cftc_tff_futures_only")
        priors = {metric_id: states[metric_id] for metric_id in CFTC_METRICS}
        try:
            for metric_id in CFTC_METRICS:
                assert_metric_network_eligible(bundle, metric_id)
            raw_by_contract = collectors.cftc(
                start=now_et.date() - timedelta(days=366 * 3 + 35),
                end=now_et.date(),
            )
            if set(raw_by_contract) != {"13874A", "20974+"}:
                raise ValueError("CFTC collector returned an incomplete contract bundle")
            latest_dates = {
                rows[-1]["date"]
                for rows in raw_by_contract.values()
                if rows
            }
            if len(latest_dates) != 1 or any(not rows for rows in raw_by_contract.values()):
                raise ValueError("CFTC contract bundle has mismatched latest dates")
            candidate_states: dict[str, SeriesState] = {}
            for metric_id, (contract_code, category) in CFTC_METRICS.items():
                points = cftc_position_series(
                    raw_by_contract[contract_code], category=category
                )
                state = _success_with_history(
                    metric_id,
                    points,
                    prior=priors[metric_id],
                    frequency="weekly",
                    attempted_at=attempted_at,
                    now_et=now_et,
                    mode=mode,
                )
                freshness, health = _cftc_freshness_for(
                    state.observation_date,
                    state.released_at,
                    now_et=now_et,
                    release_schedule=bundle.cftc_release_schedule["releases"],
                )
                candidate_states[metric_id] = replace(
                    state,
                    freshness=freshness,
                    health=health,
                    released_at=(
                        state.observations[-1].get("released_at")
                        if state.observations
                        else None
                    ),
                )
            states.update(candidate_states)
        except Exception as error:
            for metric_id, prior in priors.items():
                states[metric_id] = _failed_from_prior(
                    metric_id,
                    prior=prior,
                    attempted_at=attempted_at,
                    error=error,
                )

    if p2_macro_due:
        attempted_collectors.add("fred_nonfinancial_equities_gdp")
        prior = states[P2_MACRO_ID]
        try:
            assert_metric_network_eligible(bundle, P2_MACRO_ID)
            equities_bundle = collectors.fred_p2(
                "NCBEILQ027S",
                observation_start=p2_macro_start,
                observation_end=now_et.date(),
            )
            gdp_bundle = collectors.fred_p2(
                "GDP",
                observation_start=p2_macro_start,
                observation_end=now_et.date(),
            )
            transformed = build_nonfinancial_equities_gdp_proxy(
                equities_bundle, gdp_bundle
            )
            # Preserve a newly published exact common quarter even when one
            # component is null.  Dropping it would falsely present the prior
            # ratio as the current endpoint rather than disclosing missing.
            observations = list(transformed["series"])
            state = _success_with_history(
                P2_MACRO_ID,
                observations,
                prior=prior,
                frequency="quarterly",
                attempted_at=attempted_at,
                now_et=now_et,
                mode=mode,
            )
            freshness, health = _quarterly_proxy_freshness_for(
                state.observation_date, now_et=now_et
            )
            release_candidates = [
                value
                for value in (
                    equities_bundle.get("last_updated"),
                    gdp_bundle.get("last_updated"),
                )
                if isinstance(value, str)
            ]
            states[P2_MACRO_ID] = replace(
                state,
                freshness=freshness,
                health=health,
                released_at=max(release_candidates, default=None),
            )
        except Exception as error:
            states[P2_MACRO_ID] = _failed_from_prior(
                P2_MACRO_ID,
                prior=prior,
                attempted_at=attempted_at,
                error=error,
            )

    if p2_form4_due:
        attempted_collectors.add("sec_form4_daily_index")
        prior = states[P2_FORM4_ID]
        try:
            assert_metric_network_eligible(bundle, P2_FORM4_ID)
            prior_entries = [
                dict(entry) for entry in prior_form4_ledger.get("entries", [])
            ]
            known_entries = {
                str(entry["accession"]): entry for entry in prior_entries
            }
            # Daily runs revalidate the newest five calendar days. Weekly/all
            # runs reconcile the complete retained 45-day master-index window.
            collection_start = now_et.date() - timedelta(
                days=44 if group in {"all", "weekly"} or not prior_entries else 4
            )
            collection = collectors.sec_form4(
                start_date=collection_start,
                end_date=now_et.date(),
                known_ledger_entries=known_entries,
            )
            incomplete_days = sorted(
                set(collection.discovered_index_days)
                - set(collection.completed_index_days)
            )
            if collection.failures or incomplete_days:
                failure_details = "; ".join(
                    str(item.get("reason", "unknown SEC collection failure"))
                    for item in collection.failures[:3]
                )
                suffix = (
                    f"; incomplete index days: {', '.join(incomplete_days)}"
                    if incomplete_days
                    else ""
                )
                raise ValueError(
                    f"SEC Form 4 collection incomplete: {failure_details or 'required day failed'}{suffix}"
                )
            current_entries = [
                public_ledger_entry(filing) for filing in collection.filings
            ]
            merged_entries = merge_last_good_entries(
                prior_entries,
                current_entries,
                completed_index_days=collection.completed_index_days,
                master_accessions_by_day=collection.master_accessions_by_day,
                as_of=now_et.date(),
            )
            completed_days = sorted(
                set(prior_form4_ledger.get("completed_index_days", []))
                | set(collection.completed_index_days)
            )
            form4_ledger = build_ledger_package(
                merged_entries,
                completed_index_days=completed_days,
                as_of=now_et.date(),
                failures=_merge_audit_rows(
                    prior_form4_ledger.get("failures", []),
                    collection.failures,
                    as_of=now_et.date(),
                ),
                reviews=_merge_audit_rows(
                    prior_form4_ledger.get("reviews", []),
                    collection.reviews,
                    as_of=now_et.date(),
                ),
            )
            observation = form4_metric_observation(
                form4_ledger, as_of=now_et.date()
            )
            point = {
                "date": observation["date"],
                "value": observation["value"],
            }
            if point["date"] is None:
                raise ValueError("SEC Form 4 has no completed index day")
            state = _success_with_history(
                P2_FORM4_ID,
                [point],
                prior=prior,
                frequency="business_daily",
                attempted_at=attempted_at,
                now_et=now_et,
                mode=mode,
            )
            releases = [
                entry.get("acceptance_at")
                for entry in merged_entries
                if entry.get("index_date") in set(completed_days[-20:])
                and isinstance(entry.get("acceptance_at"), str)
            ]
            states[P2_FORM4_ID] = replace(
                state,
                released_at=max(releases, default=None),
            )
        except Exception as error:
            states[P2_FORM4_ID] = _failed_from_prior(
                P2_FORM4_ID,
                prior=prior,
                attempted_at=attempted_at,
                error=error,
            )
            form4_ledger = prior_form4_ledger

    if p3_capex_due:
        attempted_collectors.add("sec_companyfacts_capex")
        priors = {metric_id: states[metric_id] for metric_id in P3_AUTOMATED_IDS}
        try:
            if set(P3_AUTOMATED_IDS) != set(ACTIVE_P3_AUTOMATED_METRIC_IDS):
                raise ValueError("P3 automated metric constants are inconsistent")
            for metric_id in P3_AUTOMATED_IDS:
                assert_metric_network_eligible(bundle, metric_id)
            bundles = collectors.sec_companyfacts(bundle.companies["companies"])
            transformed = build_hyperscaler_capex(bundles)
            if (
                transformed.get("metric_id") != P3_CAPEX_ID
                or transformed.get("acceleration_metric_id") != P3_ACCELERATION_ID
            ):
                raise ValueError("P3 transform returned the wrong metric identity")
            candidate_states: dict[str, SeriesState] = {}
            for metric_id, key in (
                (P3_CAPEX_ID, "series"),
                (P3_ACCELERATION_ID, "acceleration_series"),
            ):
                observations = transformed.get(key)
                if not isinstance(observations, list) or len(observations) < 12:
                    raise ValueError(
                        f"{metric_id} requires at least 12 transformed quarters"
                    )
                state = _success_with_history(
                    metric_id,
                    observations,
                    prior=priors[metric_id],
                    frequency="quarterly",
                    attempted_at=attempted_at,
                    now_et=now_et,
                    mode=mode,
                )
                freshness, health = _quarterly_proxy_freshness_for(
                    state.observation_date, now_et=now_et
                )
                _stats, _details, _change, released_at = _p3_capex_payload(
                    state.observations,
                    acceleration_metric=metric_id == P3_ACCELERATION_ID,
                )
                candidate_states[metric_id] = replace(
                    state,
                    freshness=freshness,
                    health=health,
                    released_at=released_at,
                )
            if (
                candidate_states[P3_CAPEX_ID].observation_date
                != candidate_states[P3_ACCELERATION_ID].observation_date
            ):
                raise ValueError("P3 automated series endpoints do not align")
            states.update(candidate_states)
        except Exception as error:
            for metric_id, prior in priors.items():
                states[metric_id] = _failed_from_prior(
                    metric_id,
                    prior=prior,
                    attempted_at=attempted_at,
                    error=error,
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
    srf_points = []
    for point in states["srf_accepted"].observations:
        numeric_fields = (
            "accepted_amount_usd_bn",
            "alert_eligible_accepted_amount_usd_bn",
            "exercise_accepted_amount_usd_bn",
        )
        classification_complete = (
            all(
                isinstance(point.get(field), (int, float))
                and not isinstance(point.get(field), bool)
                and math.isfinite(float(point[field]))
                for field in numeric_fields
            )
            and isinstance(point.get("has_technical_exercise"), bool)
            and isinstance(point.get("technical_exercise"), bool)
        )
        srf_points.append(
            {**point, "classification_complete": classification_complete}
        )
    states["srf_accepted"] = replace(
        states["srf_accepted"], observations=srf_points
    )
    classified_srf = all(
        point.get("classification_complete") is True for point in srf_points
    )
    statistics["srf_accepted"] = {
        "sample_size": len(srf_points),
        "nontechnical_positive_use_streak": (
            srf_nontechnical_positive_use_streak(srf_points)
        ),
        "positive_nontechnical_latest_3": (
            sum(
                point["alert_eligible_accepted_amount_usd_bn"] > 0
                for point in srf_points[-3:]
            )
            if classified_srf
            else None
        ),
    }
    for metric_id in CFTC_METRICS:
        statistics[metric_id] = cftc_position_statistics(
            states[metric_id].observations
        )
    macro_statistics, macro_context, macro_change_one_quarter = (
        _p2_macro_statistics(states[P2_MACRO_ID].observations)
    )
    statistics[P2_MACRO_ID] = macro_statistics
    form4_observation = form4_metric_observation(
        form4_ledger, as_of=now_et.date()
    )
    statistics[P2_FORM4_ID] = dict(form4_observation["statistics"])
    p3_details: dict[str, dict[str, Any]] = {}
    p3_change_one_quarter: dict[str, float | None] = {}
    for metric_id in P3_AUTOMATED_IDS:
        p3_statistics, details, change, _released_at = _p3_capex_payload(
            states[metric_id].observations,
            acceleration_metric=metric_id == P3_ACCELERATION_ID,
        )
        statistics[metric_id] = p3_statistics
        p3_details[metric_id] = details
        p3_change_one_quarter[metric_id] = change
    for metric_id in P3_MANUAL_IDS:
        payload = manual_payloads[metric_id]
        statistics[metric_id] = {
            "record_count": int(payload["record_count"]),
            "company_count": int(payload["company_count"]),
            "comparable_count": int(payload["comparable_count"]),
        }
        p3_details[metric_id] = dict(payload["details"])

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
        if metric_id in P3_MANUAL_IDS:
            availability = str(manual_payloads[metric_id]["availability"])
        state = states.get(metric_id)
        flags = []
        # Treasury/tax/period-end flags are P0 liquidity interpretation
        # context.  A quarterly fundamentals point or filing-window end that
        # happens to share the same calendar date must not inherit them.
        if (
            registry_metric["phase"] == "P0"
            and state
            and state.observation_date in event_by_date
        ):
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
        if metric_id in CFTC_METRICS and state and state.observations:
            extra["details"] = {
                key: value
                for key, value in state.observations[-1].items()
                if key not in {"date", "value", "net_percent_open_interest_raw"}
            }
        if metric_id in P3_AUTOMATED_IDS or (
            metric_id in P3_MANUAL_IDS and availability == "ACTIVE_FREE"
        ):
            extra["details"] = p3_details[metric_id]
        metric_statistics = statistics.get(metric_id)
        if metric_id in P3_MANUAL_IDS and availability == "MANUAL_READY":
            metric_statistics = {}
        record = metric_record(
            bundle,
            registry_metric,
            state=state,
            attempted_at=attempted_at,
            statistics=metric_statistics,
            technical_flags=flags,
            effective_availability=availability,
            extra=extra,
        )
        if metric_id == "on_rrp_accepted":
            record["context"]["near_floor_context"] = on_rrp_floor
        if metric_id in CFTC_METRICS:
            if not cftc_due:
                record["updated_at"] = state.updated_at if state else None
            record["expected_next_update"] = _cftc_expected_next_update(
                state.observation_date if state else None,
                state.released_at if state else None,
                bundle.cftc_release_schedule["releases"],
            )
            change_8w = record["statistics"].get("change_8_weeks")
            record["changes"]["eight_weeks"] = change_8w
            record["changes"]["twelve_weeks"] = record["statistics"].get(
                "change_12_weeks"
            )
            record["context"]["direction"] = positioning_direction(change_8w)
        if metric_id == P2_MACRO_ID:
            if not p2_macro_due:
                record["updated_at"] = state.updated_at if state else None
            record["changes"]["one_quarter"] = macro_change_one_quarter
            record["context"].update(macro_context)
            # There is no reviewed exact next-release calendar spanning both
            # Z.1 and GDP.  Null is more accurate than fabricating a date.
            record["expected_next_update"] = None
        if metric_id == P2_FORM4_ID:
            if not p2_form4_due:
                record["updated_at"] = state.updated_at if state else None
            record["context"].update(form4_observation["technical_context"])
        if metric_id in P3_AUTOMATED_IDS:
            if not p3_capex_due:
                record["updated_at"] = state.updated_at if state else None
            record["changes"]["one_quarter"] = p3_change_one_quarter[metric_id]
            record["expected_next_update"] = None
            record["context"]["direction"] = p3_details[metric_id][
                "fundamental"
            ]["aggregate_direction"]
        if metric_id in P3_MANUAL_IDS:
            if availability == "MANUAL_READY":
                record["source"] = source_details(bundle, "manual_public_filings")
            record["expected_next_update"] = None
            record["context"]["direction"] = str(
                manual_payloads[metric_id]["direction"]
            )
            record["context"]["confidence"] = (
                "MEDIUM" if state is not None and state.health == "OK" else "UNKNOWN"
            )
            record["quality"]["sample_size"] = (
                int(manual_payloads[metric_id]["record_count"])
                if availability == "ACTIVE_FREE"
                else None
            )
        metric_records[metric_id] = record
        registry_for_manifest.append(
            {**registry_metric, "effective_availability": availability}
        )

    video_p0_model = evaluate_video_p0_model(
        latest_sofr_iorb_bp=sofr_stats["latest"],
        positive_streak=(
            int(sofr_stats["positive_streak"])
            if sofr_stats.get("positive_streak") is not None
            else None
        ),
        reserve_balance_usd_bn=metric_records["reserve_balances"]["value"],
        reserve_change_4w_usd_bn=reserve_context["change_4w"],
        reserve_trailing_5y_p10_usd_bn=reserve_context["trailing_5y_p10"],
        tga_daily_usd_bn=metric_records["tga_daily"]["value"],
        srf_recent_operation_days=srf_points,
        metric_quality={
            metric_id: metric_records[metric_id]
            for metric_id in (
                "sofr_iorb_spread_bp",
                "reserve_balances",
                "tga_daily",
                "srf_accepted",
            )
        },
        technical_flags=technical_flags,
        crisis_context=bundle.alert_rules["alerts"]["video_p0_model"][
            "crisis_context"
        ],
        config=bundle.alert_rules,
        evaluated_at=attempted_at,
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
            "direction": ("TIGHTER" if price_triggered else "STABLE") if price_available else "UNKNOWN",
            "confidence": rule["confidence"] if price_available else "UNKNOWN",
            "summary": "+3bp 或連續三個正數 observations 觸發 WATCH。",
        },
        {
            "id": "funding_confirmations",
            "label": "EFFR / TGCR / BGCR confirmation",
            "available": confirmation_available,
            "triggered": rule["funding_confirmation_count"] > 0 if confirmation_available else None,
            "status": f"{rule['funding_confirmation_count']}/3 UP" if confirmation_available else "UNAVAILABLE",
            "direction": "TIGHTER" if rule["funding_confirmation_count"] > 0 and confirmation_available else "STABLE" if confirmation_available else "UNKNOWN",
            "confidence": rule["confidence"] if confirmation_available else "UNKNOWN",
            "summary": "change_5obs 與 5-observation slope 同時向上先計確認。",
        },
        {
            "id": "srf_backstop",
            "label": "SRF accepted",
            "available": srf_available,
            "triggered": rule["srf_positive_operation_days_latest_3"] >= 2 if srf_available else None,
            "status": f"{rule['srf_positive_operation_days_latest_3']}/3 POSITIVE" if srf_available else "UNAVAILABLE",
            "direction": "MORE_USE" if rule["srf_positive_operation_days_latest_3"] > 0 and srf_available else "FLAT" if srf_available else "UNKNOWN",
            "confidence": rule["confidence"] if srf_available else "UNKNOWN",
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
            "direction": "LOWER" if rule["reserve_4w_at_or_below_trailing_5y_p10"] and reserve_available else "STABLE" if reserve_available else "UNKNOWN",
            "confidence": rule["confidence"] if reserve_available else "UNKNOWN",
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

    cftc_latest_dates = {
        states[metric_id].observation_date for metric_id in CFTC_METRICS
    }
    cftc_available = (
        len(cftc_latest_dates) == 1
        and None not in cftc_latest_dates
        and all(
            states[metric_id].health == "OK"
            and states[metric_id].freshness == "FRESH"
            and states[metric_id].observations
            and states[metric_id].observations[-1].get("value") is not None
            and statistics[metric_id].get("change_8_weeks") is not None
            and statistics[metric_id].get("change_12_weeks") is not None
            and statistics[metric_id].get("z_score_3_year") is not None
            and statistics[metric_id].get("z_score_3_year_sample_size") == 156
            for metric_id in CFTC_METRICS
        )
    )
    cftc_directions = {
        metric_id: positioning_direction(
            statistics[metric_id].get("change_8_weeks")
        )
        for metric_id in CFTC_METRICS
    }
    cftc_block_direction = (
        common_direction(list(cftc_directions.values()))
        if cftc_available
        else "UNKNOWN"
    )
    direction_labels = {
        "cftc_e_mini_sp500_asset_manager_net_pct_oi": "ES Asset Manager",
        "cftc_e_mini_sp500_leveraged_funds_net_pct_oi": "ES Leveraged Funds",
        "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi": "NQ consolidated Asset Manager",
        "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi": "NQ consolidated Leveraged Funds",
    }
    cftc_direction_summary = "; ".join(
        f"{direction_labels[metric_id]}: {cftc_directions[metric_id]}"
        for metric_id in CFTC_METRICS
    )
    p1_blocks = [
        {
            "id": "volatility_term_structure",
            "label": "Volatility term structure",
            "available": False,
            "triggered": None,
            "status": "UNAVAILABLE_FREE",
            "direction": "UNKNOWN",
            "confidence": "UNKNOWN",
            "summary": bundle.metrics_by_id["vix_vix3m_term_structure_proxy"]["reason"],
        },
        {
            "id": "trend_positioning",
            "label": "Trend / positioning",
            "available": cftc_available,
            "triggered": None,
            "status": cftc_block_direction if cftc_available else "UNAVAILABLE_FREE",
            "direction": cftc_block_direction,
            "confidence": "LOW" if cftc_available else "UNKNOWN",
            "summary": (
                cftc_direction_summary
                if cftc_available
                else "四條 CFTC contract/category series 未全部健康；不當作 neutral。"
            ),
        },
        {
            "id": "options_tail_risk",
            "label": "Options / tail risk",
            "available": False,
            "triggered": None,
            "status": "UNAVAILABLE_FREE",
            "direction": "UNKNOWN",
            "confidence": "UNKNOWN",
            "summary": bundle.metrics_by_id["cboe_skew_tail_risk_proxy"]["reason"],
        },
        {
            "id": "crypto_cross_asset",
            "label": "Crypto funding / cross-asset",
            "available": False,
            "triggered": None,
            "status": "UNAVAILABLE_FREE",
            "direction": "UNKNOWN",
            "confidence": "UNKNOWN",
            "summary": bundle.metrics_by_id["crypto_funding_btc"]["reason"],
        },
    ]
    market_ignition_switch = {
        "mode": "EVIDENCE_ONLY",
        "assessment": None,
        "available_blocks": sum(block["available"] for block in p1_blocks),
        "total_blocks": len(p1_blocks),
        "confidence": "LOW" if cftc_available else "UNKNOWN",
        "evidence_blocks": p1_blocks,
        "summary": "只展示 evidence coverage、方向與信心；Market Ignition 不產生 WATCH/STRESS。",
    }

    p3_fundamental = p3_details[P3_CAPEX_ID]["fundamental"]
    p3_automated_available = (
        states[P3_CAPEX_ID].health == "OK"
        and states[P3_CAPEX_ID].freshness == "FRESH"
        and states[P3_ACCELERATION_ID].health == "OK"
        and states[P3_ACCELERATION_ID].freshness == "FRESH"
        and len(states[P3_CAPEX_ID].observations) >= 12
        and len(states[P3_ACCELERATION_ID].observations) >= 12
        and metric_records[P3_CAPEX_ID]["value"] is not None
        and metric_records[P3_ACCELERATION_ID]["value"] is not None
        and statistics[P3_CAPEX_ID].get("quarter_count", 0) >= 12
        and statistics[P3_ACCELERATION_ID].get("quarter_count", 0) >= 12
    )
    p3_aggregate_direction = (
        str(p3_fundamental["aggregate_direction"])
        if p3_automated_available
        else "UNKNOWN"
    )
    p3_company_direction = (
        _common_p3_direction(
            [str(company["direction"]) for company in p3_fundamental["companies"]]
        )
        if p3_automated_available
        else "UNKNOWN"
    )

    def manual_block_state(metric_ids: Sequence[str]) -> tuple[bool, str, str]:
        active_ids = [
            metric_id
            for metric_id in metric_ids
            if manual_payloads[metric_id]["availability"] == "ACTIVE_FREE"
        ]
        if not active_ids:
            return False, "UNKNOWN", "MANUAL_READY"
        healthy = all(
            states[metric_id].health == "OK"
            and states[metric_id].freshness == "FRESH"
            for metric_id in active_ids
        )
        if not healthy:
            return False, "UNKNOWN", "STALE"
        direction = _common_p3_direction(
            [str(manual_payloads[metric_id]["direction"]) for metric_id in active_ids]
        )
        return True, direction, direction

    orders_available, orders_direction, orders_status = manual_block_state(
        ("ai_upstream_orders_backlog",)
    )
    commitments_available, commitments_direction, commitments_status = (
        manual_block_state(
            (
                "customer_prepayments_contract_commitments",
                "take_or_pay_commitments",
            )
        )
    )
    p3_blocks = [
        {
            "id": "aggregate_capex_acceleration",
            "label": "Aggregate CapEx acceleration",
            "available": p3_automated_available,
            "triggered": None,
            "status": (
                p3_aggregate_direction if p3_automated_available else "UNAVAILABLE"
            ),
            "direction": p3_aggregate_direction,
            "confidence": "MEDIUM" if p3_automated_available else "UNKNOWN",
            "summary": (
                "四家公司現金 CapEx 先加總，再計 QoQ、YoY 同 acceleration；finance leases 分開披露。"
                if p3_automated_available
                else "四家公司至少 12 個共同季度嘅健康 SEC facts 尚未齊備。"
            ),
        },
        {
            "id": "orders_backlog",
            "label": "Orders / backlog",
            "available": orders_available,
            "triggered": None,
            "status": orders_status,
            "direction": orders_direction,
            "confidence": "MEDIUM" if orders_available else "UNKNOWN",
            "summary": (
                "顯示已人工覆核、保留 filing provenance 嘅 orders/backlog disclosures。"
                if orders_available
                else (
                    "已有經 PR 覆核嘅 orders/backlog 記錄，但證據已超過 120 日或狀態過期，需重新覆核。"
                    if orders_status == "STALE"
                    else "尚未有經 PR 覆核嘅 orders/backlog CSV 記錄。"
                )
            ),
        },
        {
            "id": "prepayments_commitments",
            "label": "Prepayments / commitments",
            "available": commitments_available,
            "triggered": None,
            "status": commitments_status,
            "direction": commitments_direction,
            "confidence": "MEDIUM" if commitments_available else "UNKNOWN",
            "summary": (
                "顯示已人工覆核嘅 customer prepayments、contract commitments 或 take-or-pay 證據。"
                if commitments_available
                else (
                    "已有經 PR 覆核嘅 prepayments／commitments 記錄，但證據已超過 120 日或狀態過期，需重新覆核。"
                    if commitments_status == "STALE"
                    else "尚未有經 PR 覆核嘅 prepayments／commitments CSV 記錄。"
                )
            ),
        },
        {
            "id": "company_breadth",
            "label": "Company breadth",
            "available": p3_automated_available,
            "triggered": None,
            "status": p3_company_direction if p3_automated_available else "UNAVAILABLE",
            "direction": p3_company_direction,
            "confidence": "MEDIUM" if p3_automated_available else "UNKNOWN",
            "summary": (
                f"{int(statistics[P3_CAPEX_ID]['company_breadth'] or 0)}/4 家公司方向同 aggregate acceleration 一致。"
                if p3_automated_available
                else "公司層面 acceleration breadth 尚未有完整健康證據。"
            ),
        },
    ]
    p3_available_blocks = sum(block["available"] for block in p3_blocks)
    fundamental_exit_switch = {
        "mode": "EVIDENCE_ONLY",
        "assessment": None,
        "available_blocks": p3_available_blocks,
        "total_blocks": len(p3_blocks),
        "confidence": (
            "UNKNOWN"
            if p3_available_blocks == 0
            else "LOW"
            if p3_available_blocks <= 2
            else "MEDIUM"
        ),
        "evidence_blocks": p3_blocks,
        "summary": "只展示 evidence coverage、方向與公司 breadth；Fundamental Exit 不產生 WATCH/STRESS。",
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
        "cftc_tff_futures_only": collector_source_record(
            bundle,
            "cftc_tff_futures_only",
            "cftc_pre",
            [states[metric_id] for metric_id in CFTC_METRICS],
            attempted_at=attempted_at,
        ),
        "fred_nonfinancial_equities_gdp": collector_source_record(
            bundle,
            "fred_nonfinancial_equities_gdp",
            "fred_government",
            [states[P2_MACRO_ID]],
            attempted_at=attempted_at,
        ),
        "sec_form4_daily_index": collector_source_record(
            bundle,
            "sec_form4_daily_index",
            "sec_edgar",
            [states[P2_FORM4_ID]],
            attempted_at=attempted_at,
        ),
        "sec_companyfacts_capex": collector_source_record(
            bundle,
            "sec_companyfacts_capex",
            "sec_edgar",
            [states[metric_id] for metric_id in P3_AUTOMATED_IDS],
            attempted_at=attempted_at,
        ),
    }
    cftc_latest_state = states[
        "cftc_e_mini_sp500_asset_manager_net_pct_oi"
    ]
    sources["cftc_tff_futures_only"]["expected_next_update"] = (
        _cftc_expected_next_update(
            cftc_latest_state.observation_date,
            cftc_latest_state.released_at,
            bundle.cftc_release_schedule["releases"],
        )
    )
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
                "cftc_tff_futures_only": [
                    states[metric_id] for metric_id in CFTC_METRICS
                ],
                "fred_nonfinancial_equities_gdp": [states[P2_MACRO_ID]],
                "sec_form4_daily_index": [states[P2_FORM4_ID]],
                "sec_companyfacts_capex": [
                    states[metric_id] for metric_id in P3_AUTOMATED_IDS
                ],
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
                **market_ignition_switch,
            },
            "fundamental_exit": fundamental_exit_switch,
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
        "decision_models": {"p0_video_liquidity": video_p0_model},
        "composite": rule,
        **availability_counts(metric_records),
    }
    manifest = manifest_record(registry_for_manifest, attempted_at)
    series_by_id = {
        metric_id: series_record(metric, states.get(metric_id))
        for metric_id, metric in metric_records.items()
    }
    validate_publication(snapshot, manifest, series_by_id)
    _validate_form4_metric_against_ledger(snapshot, form4_ledger, series_by_id)
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
        sec_form4_ledger=form4_ledger,
    )


def write_stage(publication: Publication, stage_dir: str | Path) -> Path:
    """Write a validated complete publication to an explicit staging directory."""

    validate_publication(
        publication.snapshot, publication.manifest, publication.series_by_id
    )
    _validate_form4_metric_against_ledger(
        publication.snapshot,
        publication.sec_form4_ledger,
        publication.series_by_id,
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
    write_ledger_atomic(stage / "ledgers" / "sec_form4", publication.sec_form4_ledger)
    return stage


def load_stage(stage_dir: str | Path) -> Publication:
    """Read and validate an on-disk candidate before final promotion."""

    stage = Path(stage_dir)
    expected_entries = {
        "snapshot.json",
        "manifest.json",
        "alerts.json",
        "events.json",
        "series",
        "ledgers",
    }
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
    ledgers_directory = stage / "ledgers"
    if (
        not ledgers_directory.is_dir()
        or {path.name for path in ledgers_directory.iterdir()} != {"sec_form4"}
    ):
        raise PublicationError("stage contains missing or unexpected ledger directories")
    try:
        sec_form4_ledger = load_ledger(ledgers_directory / "sec_form4")
    except Exception as error:
        raise PublicationError("SEC Form 4 ledger failed validation") from error
    validate_publication(snapshot, manifest, series_by_id)
    _validate_form4_metric_against_ledger(snapshot, sec_form4_ledger, series_by_id)
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
        sec_form4_ledger=sec_form4_ledger,
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
