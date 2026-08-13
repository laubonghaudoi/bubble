"""Load and validate version-controlled Bubble pipeline configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

import yaml

from pipeline.contracts import (
    Availability,
    ContractValidationError,
    Freshness,
    Health,
    METHODOLOGY_FIELDS,
    SCHEMA_VERSION,
)


CONFIG_FILENAMES = (
    "metric_registry.yml",
    "source_registry.yml",
    "alert_rules.yml",
    "companies.yml",
    "us_tax_dates.yml",
    "nyfed_operational_readiness.yml",
    "cftc_release_schedule.yml",
)

CANONICAL_P0_METRIC_IDS = frozenset(
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

CANONICAL_P1_CFTC_METRIC_IDS = frozenset(
    {
        "cftc_e_mini_sp500_asset_manager_net_pct_oi",
        "cftc_e_mini_sp500_leveraged_funds_net_pct_oi",
        "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi",
        "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi",
    }
)

CANONICAL_P2_METRIC_IDS = frozenset(
    {
        "nonfinancial_equities_gdp_proxy",
        "sec_form4_nonderivative_ps_count_ratio_20d",
        "gamma_flip",
        "spx_0dte_share",
        "finra_margin_debt",
        "spy_holdings_top10_weight_proxy",
        "m2_nasdaq_divergence",
        "ndx_forward_pe",
    }
)

ACTIVE_P2_METRIC_IDS = frozenset(
    {
        "nonfinancial_equities_gdp_proxy",
        "sec_form4_nonderivative_ps_count_ratio_20d",
    }
)

CANONICAL_P3_METRIC_IDS = frozenset(
    {
        "hyperscaler_aggregate_cash_capex",
        "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
        "ai_upstream_orders_backlog",
        "customer_prepayments_contract_commitments",
        "take_or_pay_commitments",
    }
)

ACTIVE_P3_AUTOMATED_METRIC_IDS = frozenset(
    {
        "hyperscaler_aggregate_cash_capex",
        "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
    }
)

MANUAL_P3_METRIC_IDS = CANONICAL_P3_METRIC_IDS - ACTIVE_P3_AUTOMATED_METRIC_IDS

VIDEO_P0_CRISIS_CONTEXT_STATUSES = frozenset(
    {"UNKNOWN", "MAJOR_CRISIS_PRESENT", "NO_MAJOR_CRISIS"}
)
VIDEO_P0_SOURCE_SEGMENTS = (
    (
        "yellow_red",
        "Yellow / Red formula",
        1380,
        1440,
        "https://www.youtube.com/watch?v=MrnjBdgQPLU&t=1380s",
    ),
    (
        "reserve_exit_1",
        "Reserve exit context I",
        1140,
        1200,
        "https://www.youtube.com/watch?v=MrnjBdgQPLU&t=1140s",
    ),
    (
        "reserve_exit_2",
        "Reserve exit context II",
        1560,
        1620,
        "https://www.youtube.com/watch?v=MrnjBdgQPLU&t=1560s",
    ),
)


class ConfigValidationError(ContractValidationError):
    """Raised when a registry/config bundle is internally inconsistent."""


class SourceNotNetworkEligible(PermissionError):
    """Raised before a collector can access a disabled or rights-held source."""


@dataclass(frozen=True)
class EffectiveMetricState:
    """Publication state before any collector result is merged."""

    availability: Availability
    health: Health | None
    freshness: Freshness | None
    value: None
    reason: str | None


@dataclass(frozen=True)
class ConfigBundle:
    metric_registry: Mapping[str, Any]
    source_registry: Mapping[str, Any]
    alert_rules: Mapping[str, Any]
    companies: Mapping[str, Any]
    us_tax_dates: Mapping[str, Any]
    nyfed_operational_readiness: Mapping[str, Any]
    cftc_release_schedule: Mapping[str, Any]

    @property
    def metrics_by_id(self) -> dict[str, Mapping[str, Any]]:
        return {metric["metric_id"]: metric for metric in self.metric_registry["metrics"]}

    @property
    def sources_by_id(self) -> dict[str, Mapping[str, Any]]:
        return {source["source_id"]: source for source in self.source_registry["sources"]}


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigValidationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ConfigValidationError(f"{path} must contain a YAML object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ConfigValidationError(
            f"{path} schema_version must be {SCHEMA_VERSION}"
        )
    return value


def load_config_bundle(config_dir: str | Path | None = None) -> ConfigBundle:
    """Load the seven canonical YAML files and validate their cross-references."""

    root = (
        Path(config_dir)
        if config_dir is not None
        else Path(__file__).resolve().parents[1] / "config"
    )
    loaded = {filename: _load_yaml(root / filename) for filename in CONFIG_FILENAMES}
    bundle = ConfigBundle(
        metric_registry=loaded["metric_registry.yml"],
        source_registry=loaded["source_registry.yml"],
        alert_rules=loaded["alert_rules.yml"],
        companies=loaded["companies.yml"],
        us_tax_dates=loaded["us_tax_dates.yml"],
        nyfed_operational_readiness=loaded["nyfed_operational_readiness.yml"],
        cftc_release_schedule=loaded["cftc_release_schedule.yml"],
    )
    validate_config_bundle(bundle)
    return bundle


def _unique_records(records: Any, key: str, path: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(records, list):
        raise ConfigValidationError(f"{path} must be a list")
    index: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ConfigValidationError(f"{path} entries must be objects")
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise ConfigValidationError(f"{path}.{key} must be a non-empty string")
        if value in index:
            raise ConfigValidationError(f"duplicate {path}.{key}: {value}")
        index[value] = record
    return index


def _series_values(metric: Mapping[str, Any], source_id: str) -> list[str]:
    source_series = metric.get("source_series", {})
    if not isinstance(source_series, Mapping):
        raise ConfigValidationError(
            f"metric {metric['metric_id']} source_series must be an object"
        )
    value = source_series.get(source_id)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    raise ConfigValidationError(
        f"metric {metric['metric_id']} source_series.{source_id} must be a string or string list"
    )


def _assert_source_network_eligible(
    source: Mapping[str, Any], *, source_id: str, series_ids: list[str]
) -> None:
    rights = source.get("rights")
    if not isinstance(rights, Mapping):
        raise SourceNotNetworkEligible(f"source {source_id} has no rights record")
    blockers = []
    if source.get("enabled") is not True:
        blockers.append("disabled")
    if source.get("network_eligible") is not True:
        blockers.append("network_eligible=false")
    if rights.get("status") != "CLEARED":
        blockers.append(f"rights={rights.get('status')}")
    if rights.get("automated_fetch") is not True:
        blockers.append("automated_fetch=false")
    if rights.get("public_redistribution") is not True:
        blockers.append("public_redistribution=false")
    if blockers:
        raise SourceNotNetworkEligible(
            f"source {source_id} is not network eligible: {', '.join(blockers)}"
        )

    if "series_allowlist" in source:
        allowlist = source.get("series_allowlist")
        if not isinstance(allowlist, list) or not all(
            isinstance(item, str) and item for item in allowlist
        ):
            raise SourceNotNetworkEligible(
                f"source {source_id} has an invalid series_allowlist"
            )
        if not series_ids:
            raise SourceNotNetworkEligible(
                f"source {source_id} requires explicit source_series"
            )
        disallowed = sorted(set(series_ids) - set(allowlist))
        if disallowed:
            raise SourceNotNetworkEligible(
                f"source {source_id} series not allowlisted: {', '.join(disallowed)}"
            )


def assert_source_network_eligible(
    bundle: ConfigBundle, source_id: str, *, series_ids: list[str] | None = None
) -> Mapping[str, Any]:
    """Return a source only after its enablement and rights gates pass."""

    source = bundle.sources_by_id.get(source_id)
    if source is None:
        raise SourceNotNetworkEligible(f"unknown source: {source_id}")
    _assert_source_network_eligible(
        source, source_id=source_id, series_ids=list(series_ids or [])
    )
    return source


def assert_metric_network_eligible(
    bundle: ConfigBundle, metric_id: str
) -> tuple[Mapping[str, Any], ...]:
    """Fail closed unless a metric and every declared source pass rights gates."""

    metric = bundle.metrics_by_id.get(metric_id)
    if metric is None:
        raise SourceNotNetworkEligible(f"unknown metric: {metric_id}")
    if metric.get("implemented") is not True:
        raise SourceNotNetworkEligible(f"metric {metric_id} implemented=false")
    availability = Availability(metric["availability"])
    if metric.get("network_enabled") is not True:
        raise SourceNotNetworkEligible(f"metric {metric_id} has network_enabled=false")
    if availability not in (Availability.ACTIVE_FREE, Availability.ACTIVE_PROXY):
        raise SourceNotNetworkEligible(
            f"metric {metric_id} availability={availability.value} is not network eligible"
        )
    return tuple(
        assert_source_network_eligible(
            bundle,
            source_id,
            series_ids=_series_values(metric, source_id),
        )
        for source_id in metric["source_ids"]
    )


def effective_metric_state(metric: Mapping[str, Any]) -> EffectiveMetricState:
    """Map phase-pending and nonautomatic entries to safe publication defaults.

    Implemented active metrics leave health and freshness to their collector.
    Every other entry is a null, non-applicable value, so a future phase cannot
    be presented as active before its implementation ships.
    """

    try:
        configured = Availability(metric.get("availability"))
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError("metric has invalid availability") from exc
    if metric.get("implemented") is not True:
        phase = metric.get("phase", "future phase")
        return EffectiveMetricState(
            availability=Availability.UNAVAILABLE_FREE,
            health=Health.NOT_APPLICABLE,
            freshness=Freshness.UNKNOWN,
            value=None,
            reason=f"{phase} implementation is not released.",
        )
    if configured in (Availability.MANUAL_READY, Availability.UNAVAILABLE_FREE):
        return EffectiveMetricState(
            availability=configured,
            health=Health.NOT_APPLICABLE,
            freshness=Freshness.UNKNOWN,
            value=None,
            reason=metric.get("reason"),
        )
    return EffectiveMetricState(
        availability=configured,
        health=None,
        freshness=None,
        value=None,
        reason=None,
    )


def _finite_positive_config_number(value: Any, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise ConfigValidationError(f"{path} must be a finite positive number")
    return float(value)


def _finite_config_number(value: Any, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise ConfigValidationError(f"{path} must be a finite number")
    return float(value)


def validate_video_p0_crisis_context(
    context: Any,
    *,
    path: str = "alert_rules alerts.video_p0_model.crisis_context",
) -> None:
    """Validate the manually audited context gate without accepting stale metadata."""

    if not isinstance(context, Mapping):
        raise ConfigValidationError(f"{path} must be an object")
    expected_fields = {"status", "as_of", "reviewed_at", "reviewer", "note"}
    if set(context) != expected_fields:
        raise ConfigValidationError(
            f"{path} must contain exactly: " + ", ".join(sorted(expected_fields))
        )
    status = context.get("status")
    if status not in VIDEO_P0_CRISIS_CONTEXT_STATUSES:
        raise ConfigValidationError(
            f"{path}.status must be UNKNOWN, MAJOR_CRISIS_PRESENT, or NO_MAJOR_CRISIS"
        )
    audit_fields = ("as_of", "reviewed_at", "reviewer", "note")
    if status == "UNKNOWN":
        if any(context.get(field) is not None for field in audit_fields):
            raise ConfigValidationError(
                f"{path} UNKNOWN status requires null audit metadata"
            )
        return

    raw_as_of = context.get("as_of")
    if not isinstance(raw_as_of, str):
        raise ConfigValidationError(f"{path}.as_of must be an ISO date")
    try:
        as_of = date.fromisoformat(raw_as_of)
    except ValueError as exc:
        raise ConfigValidationError(f"{path}.as_of must be an ISO date") from exc
    if as_of.isoformat() != raw_as_of:
        raise ConfigValidationError(f"{path}.as_of must be an ISO date")

    raw_reviewed_at = context.get("reviewed_at")
    if not isinstance(raw_reviewed_at, str) or not raw_reviewed_at.endswith("Z"):
        raise ConfigValidationError(f"{path}.reviewed_at must be a UTC Z timestamp")
    try:
        reviewed_at = datetime.fromisoformat(raw_reviewed_at[:-1] + "+00:00")
    except ValueError as exc:
        raise ConfigValidationError(
            f"{path}.reviewed_at must be a UTC Z timestamp"
        ) from exc
    if reviewed_at.utcoffset() is None or reviewed_at.utcoffset().total_seconds() != 0:
        raise ConfigValidationError(f"{path}.reviewed_at must be a UTC Z timestamp")
    if reviewed_at.date() < as_of:
        raise ConfigValidationError(f"{path}.reviewed_at cannot precede as_of")
    for field in ("reviewer", "note"):
        value = context.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ConfigValidationError(f"{path}.{field} must be non-empty")


def _validate_video_p0_model_config(alerts: Mapping[str, Any]) -> None:
    path = "alert_rules alerts.video_p0_model"
    model = alerts.get("video_p0_model")
    if not isinstance(model, Mapping):
        raise ConfigValidationError(f"{path} must be an object")
    if not isinstance(model.get("enabled"), bool):
        raise ConfigValidationError(f"{path}.enabled must be boolean")
    if model.get("model_id") != "henren778_p0_liquidity":
        raise ConfigValidationError(
            f"{path}.model_id must be henren778_p0_liquidity"
        )
    if model.get("label") != "影片 P0 黃／紅警報":
        raise ConfigValidationError(f"{path}.label does not match the audited model")

    source = model.get("source")
    if not isinstance(source, Mapping):
        raise ConfigValidationError(f"{path}.source must be an object")
    expected_source = {
        "title": "一個月前全網喊AI泡沫要崩，我說鬼故事是洗盤不是葬禮，二波窗口鎖死7月底8月初！對賭：納指洗完近一成，道指標普齊創新高，美光單日暴拉18.4%！復盤釘死，二波打法五步三開關全套交付",
        "display_title": "一個月前全網喊 AI 泡沫要崩",
        "author": "一个狠人",
        "url": "https://www.youtube.com/watch?v=MrnjBdgQPLU",
    }
    for field, expected in expected_source.items():
        if source.get(field) != expected:
            raise ConfigValidationError(
                f"{path}.source.{field} does not match the audited source"
            )
    segments = source.get("segments")
    if not isinstance(segments, list) or len(segments) != len(VIDEO_P0_SOURCE_SEGMENTS):
        raise ConfigValidationError(f"{path}.source.segments must contain three entries")
    segment_fields = {
        "segment_id",
        "label",
        "start_seconds",
        "end_seconds",
        "timestamp_url",
    }
    for index, (segment, expected) in enumerate(
        zip(segments, VIDEO_P0_SOURCE_SEGMENTS, strict=True)
    ):
        segment_path = f"{path}.source.segments[{index}]"
        if not isinstance(segment, Mapping) or set(segment) != segment_fields:
            raise ConfigValidationError(
                f"{segment_path} must contain the exact audited segment fields"
            )
        actual = (
            segment.get("segment_id"),
            segment.get("label"),
            segment.get("start_seconds"),
            segment.get("end_seconds"),
            segment.get("timestamp_url"),
        )
        if actual != expected:
            raise ConfigValidationError(
                f"{segment_path} does not match the audited source segment"
            )

    yellow = model.get("yellow")
    red = model.get("red")
    extreme = model.get("extreme")
    if not all(isinstance(item, Mapping) for item in (yellow, red, extreme)):
        raise ConfigValidationError(f"{path} yellow/red/extreme rules must be objects")
    assert isinstance(yellow, Mapping)
    assert isinstance(red, Mapping)
    assert isinstance(extreme, Mapping)

    yellow_reserve = _finite_positive_config_number(
        yellow.get("reserve_below_usd_tn"), f"{path}.yellow.reserve_below_usd_tn"
    )
    red_reserve = _finite_positive_config_number(
        red.get("reserve_below_usd_tn"), f"{path}.red.reserve_below_usd_tn"
    )
    extreme_reserve = _finite_positive_config_number(
        extreme.get("reserve_below_usd_tn"),
        f"{path}.extreme.reserve_below_usd_tn",
    )
    if not extreme_reserve < red_reserve < yellow_reserve:
        raise ConfigValidationError(
            f"{path} reserve thresholds must satisfy extreme < red < yellow"
        )
    if (yellow_reserve, red_reserve, extreme_reserve) != (2.9, 2.8, 2.5):
        raise ConfigValidationError(
            f"{path} reserve thresholds must be the audited 2.9T/2.8T/2.5T values"
        )
    reserve_rules = alerts.get("reserve_balances")
    if not isinstance(reserve_rules, Mapping):
        raise ConfigValidationError("alert_rules alerts.reserve_balances must be an object")
    reserve_zones = reserve_rules.get("reference_zones_usd_tn")
    if reserve_zones != [yellow_reserve, red_reserve, extreme_reserve]:
        raise ConfigValidationError(
            f"{path} reserve thresholds must equal reserve_balances reference zones"
        )
    if reserve_rules.get("reference_only") is not True:
        raise ConfigValidationError(
            "alert_rules alerts.reserve_balances.reference_only must remain true"
        )

    streak = yellow.get("positive_streak_observations")
    if isinstance(streak, bool) or not isinstance(streak, int) or streak != 3:
        raise ConfigValidationError(
            f"{path}.yellow.positive_streak_observations must be exactly 3"
        )
    spread_positive = _finite_config_number(
        yellow.get("spread_positive_bp"), f"{path}.yellow.spread_positive_bp"
    )
    if spread_positive != 0:
        raise ConfigValidationError(
            f"{path}.yellow.spread_positive_bp must be exactly 0"
        )
    if yellow.get("require_negative_reserve_change_4w") is not True:
        raise ConfigValidationError(
            f"{path}.yellow.require_negative_reserve_change_4w must be true"
        )
    tga_floor = _finite_positive_config_number(
        yellow.get("tga_near_1t_floor_usd_tn"),
        f"{path}.yellow.tga_near_1t_floor_usd_tn",
    )
    tga_target = _finite_positive_config_number(
        yellow.get("tga_source_target_usd_tn"),
        f"{path}.yellow.tga_source_target_usd_tn",
    )
    if not tga_floor < tga_target:
        raise ConfigValidationError(f"{path} TGA floor must be below its source target")
    if (tga_floor, tga_target) != (0.95, 1.0):
        raise ConfigValidationError(
            f"{path} TGA floor/target must be the audited 0.95T/1.0T values"
        )

    spread = _finite_positive_config_number(
        red.get("sofr_iorb_bp"), f"{path}.red.sofr_iorb_bp"
    )
    if spread != 3.0:
        raise ConfigValidationError(f"{path}.red.sofr_iorb_bp must be exactly 3.0")
    if red.get("srf_window_completed_operation_days") != 3:
        raise ConfigValidationError(
            f"{path}.red.srf_window_completed_operation_days must be exactly 3"
        )
    if red.get("srf_positive_days_latest_3") != 2:
        raise ConfigValidationError(
            f"{path}.red.srf_positive_days_latest_3 must be exactly 2"
        )
    if red.get("exclude_technical_exercises") is not True:
        raise ConfigValidationError(
            f"{path}.red.exclude_technical_exercises must be true"
        )
    if extreme.get("rapid_decline_rule") != "trailing_5y_p10":
        raise ConfigValidationError(
            f"{path}.extreme.rapid_decline_rule must be trailing_5y_p10"
        )
    if extreme.get("crisis_context_required") is not True:
        raise ConfigValidationError(
            f"{path}.extreme.crisis_context_required must be true"
        )
    validate_video_p0_crisis_context(model.get("crisis_context"), path=f"{path}.crisis_context")


def validate_config_bundle(bundle: ConfigBundle) -> None:
    metrics = _unique_records(
        bundle.metric_registry.get("metrics"), "metric_id", "metrics"
    )
    sources = _unique_records(
        bundle.source_registry.get("sources"), "source_id", "sources"
    )
    alerts = bundle.alert_rules.get("alerts")
    if not isinstance(alerts, Mapping):
        raise ConfigValidationError("alert_rules alerts must be an object")
    _validate_video_p0_model_config(alerts)
    releases = bundle.cftc_release_schedule.get("releases")
    if not isinstance(releases, list) or not releases:
        raise ConfigValidationError("cftc release schedule must be non-empty")
    if bundle.cftc_release_schedule.get("source_url") != (
        "https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm"
    ):
        raise ConfigValidationError("cftc release schedule source_url must be official")
    if bundle.cftc_release_schedule.get("release_time_et") != "15:30":
        raise ConfigValidationError("cftc release_time_et must be 15:30")
    reviewed_at = bundle.cftc_release_schedule.get("reviewed_at")
    try:
        reviewed = datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigValidationError("cftc reviewed_at must be ISO-8601") from exc
    if reviewed.utcoffset() is None or reviewed.utcoffset().total_seconds() != 0:
        raise ConfigValidationError("cftc reviewed_at must use UTC")
    previous_release: str | None = None
    previous_observation: str | None = None
    for item in releases:
        if not isinstance(item, Mapping):
            raise ConfigValidationError("cftc release schedule entries must be objects")
        try:
            observation = date.fromisoformat(item["observation_date"])
            release = date.fromisoformat(item["release_date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigValidationError("cftc release schedule has invalid dates") from exc
        if release <= observation or (release - observation).days > 7:
            raise ConfigValidationError("cftc release schedule has an invalid lag")
        if previous_release is not None and item["release_date"] <= previous_release:
            raise ConfigValidationError("cftc release dates must be strictly increasing")
        previous_release = item["release_date"]
        if previous_observation is not None and item["observation_date"] <= previous_observation:
            raise ConfigValidationError("cftc observation dates must be strictly increasing")
        previous_observation = item["observation_date"]
        if not isinstance(item.get("delayed_for_holiday"), bool):
            raise ConfigValidationError("cftc delayed_for_holiday must be boolean")

    declared_p0 = bundle.metric_registry.get("canonical_p0_metric_ids")
    if not isinstance(declared_p0, list) or set(declared_p0) != CANONICAL_P0_METRIC_IDS:
        raise ConfigValidationError("canonical_p0_metric_ids does not match contract")
    missing_p0 = sorted(CANONICAL_P0_METRIC_IDS - set(metrics))
    if missing_p0:
        raise ConfigValidationError(
            f"metric registry is missing canonical P0 IDs: {', '.join(missing_p0)}"
        )
    declared_p1 = bundle.metric_registry.get("canonical_p1_metric_ids")
    if not isinstance(declared_p1, list) or set(declared_p1) != CANONICAL_P1_CFTC_METRIC_IDS:
        raise ConfigValidationError("canonical_p1_metric_ids does not match contract")
    retired_p1_ids = {
        "cftc_asset_manager_positioning",
        "cftc_leveraged_funds_positioning_proxy",
    }
    if retired_p1_ids & set(metrics):
        raise ConfigValidationError("retired generic CFTC metric IDs remain in registry")
    declared_p2 = bundle.metric_registry.get("canonical_p2_metric_ids")
    if not isinstance(declared_p2, list) or set(declared_p2) != CANONICAL_P2_METRIC_IDS:
        raise ConfigValidationError("canonical_p2_metric_ids does not match contract")
    missing_p2 = sorted(CANONICAL_P2_METRIC_IDS - set(metrics))
    if missing_p2:
        raise ConfigValidationError(
            "metric registry is missing canonical P2 IDs: " + ", ".join(missing_p2)
        )
    retired_p2_ids = {
        "buffett_indicator_proxy",
        "insider_buy_sell_proxy",
        "insider_ratio_proxy",
        "put_call_vol_skew",
        "sp500_top10_weight",
    }
    if retired_p2_ids & set(metrics):
        raise ConfigValidationError("retired P2 metric IDs remain in registry")
    expected_p2_availability = {
        "nonfinancial_equities_gdp_proxy": Availability.ACTIVE_PROXY,
        "sec_form4_nonderivative_ps_count_ratio_20d": Availability.ACTIVE_PROXY,
        **{
            metric_id: Availability.UNAVAILABLE_FREE
            for metric_id in CANONICAL_P2_METRIC_IDS - ACTIVE_P2_METRIC_IDS
        },
    }
    for metric_id, expected_availability in expected_p2_availability.items():
        metric = metrics[metric_id]
        if metric.get("implemented") is not True:
            raise ConfigValidationError(f"P2 metric {metric_id} must be implemented")
        if metric.get("availability") != expected_availability.value:
            raise ConfigValidationError(
                f"P2 metric {metric_id} availability must be {expected_availability.value}"
            )
    declared_p3 = bundle.metric_registry.get("canonical_p3_metric_ids")
    if not isinstance(declared_p3, list) or set(declared_p3) != CANONICAL_P3_METRIC_IDS:
        raise ConfigValidationError("canonical_p3_metric_ids does not match contract")
    missing_p3 = sorted(CANONICAL_P3_METRIC_IDS - set(metrics))
    if missing_p3:
        raise ConfigValidationError(
            "metric registry is missing canonical P3 IDs: " + ", ".join(missing_p3)
        )
    retired_p3_ids = {
        "hyperscaler_capex",
        "capex_acceleration",
        "upstream_backlog",
        "prepayments",
        "take_or_pay",
    }
    if retired_p3_ids & set(metrics):
        raise ConfigValidationError("retired P3 metric IDs remain in registry")
    for metric_id in ACTIVE_P3_AUTOMATED_METRIC_IDS:
        metric = metrics[metric_id]
        if (
            metric.get("implemented") is not True
            or metric.get("availability") != Availability.ACTIVE_FREE.value
            or metric.get("network_enabled") is not True
            or metric.get("source_ids") != ["sec_edgar"]
        ):
            raise ConfigValidationError(
                f"automated P3 metric {metric_id} must be implemented ACTIVE_FREE via SEC EDGAR"
            )
    for metric_id in MANUAL_P3_METRIC_IDS:
        metric = metrics[metric_id]
        if (
            metric.get("implemented") is not True
            or metric.get("availability") != Availability.MANUAL_READY.value
            or metric.get("network_enabled") is not False
            or metric.get("source_ids") != ["manual_public_filings"]
        ):
            raise ConfigValidationError(
                f"manual P3 metric {metric_id} must be implemented MANUAL_READY with network disabled"
            )
    expected_cftc_identity = {
        "cftc_e_mini_sp500_asset_manager_net_pct_oi": ("13874A", "E-MINI S&P 500", "asset_manager"),
        "cftc_e_mini_sp500_leveraged_funds_net_pct_oi": ("13874A", "E-MINI S&P 500", "leveraged_funds"),
        "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi": ("20974+", "NASDAQ-100 Consolidated", "asset_manager"),
        "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi": ("20974+", "NASDAQ-100 Consolidated", "leveraged_funds"),
    }
    for metric_id, identity in expected_cftc_identity.items():
        metric = metrics.get(metric_id)
        if metric is None:
            raise ConfigValidationError(f"metric registry is missing canonical P1 ID: {metric_id}")
        actual = (
            metric.get("contract_code"),
            metric.get("contract_name"),
            metric.get("trader_category"),
        )
        if actual != identity:
            raise ConfigValidationError(f"CFTC identity mismatch for {metric_id}")

    for metric_id, metric in metrics.items():
        try:
            availability = Availability(metric.get("availability"))
        except ValueError as exc:
            raise ConfigValidationError(
                f"metric {metric_id} has invalid availability"
            ) from exc
        source_ids = metric.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ConfigValidationError(f"metric {metric_id} requires source_ids")
        unknown_sources = sorted(set(source_ids) - set(sources))
        if unknown_sources:
            raise ConfigValidationError(
                f"metric {metric_id} has unknown sources: {', '.join(unknown_sources)}"
            )
        if not isinstance(metric.get("implemented"), bool):
            raise ConfigValidationError(f"metric {metric_id} implemented must be boolean")
        if availability is Availability.ACTIVE_PROXY:
            if metric.get("is_proxy") is not True or not metric.get("proxy_disclosure"):
                raise ConfigValidationError(
                    f"ACTIVE_PROXY metric {metric_id} requires an explicit proxy disclosure"
                )
        methodology = metric.get("methodology")
        if not isinstance(methodology, Mapping):
            raise ConfigValidationError(
                f"metric {metric_id} requires methodology metadata"
            )
        missing_methodology = METHODOLOGY_FIELDS - methodology.keys()
        if missing_methodology:
            raise ConfigValidationError(
                f"metric {metric_id} methodology missing: "
                + ", ".join(sorted(missing_methodology))
            )
        if not isinstance(methodology.get("confirm_with"), list) or not all(
            isinstance(item, str) and item
            for item in methodology.get("confirm_with", [])
        ):
            raise ConfigValidationError(
                f"metric {metric_id} methodology.confirm_with must be a string list"
            )
        for field in METHODOLOGY_FIELDS - {"confirm_with"}:
            if not isinstance(methodology.get(field), str):
                raise ConfigValidationError(
                    f"metric {metric_id} methodology.{field} must be a string"
                )
        if methodology["proxy_disclosure"] != (metric.get("proxy_disclosure") or ""):
            raise ConfigValidationError(
                f"metric {metric_id} proxy_disclosure must match methodology"
            )
        if availability in (Availability.MANUAL_READY, Availability.UNAVAILABLE_FREE):
            if metric.get("network_enabled") is not False:
                raise ConfigValidationError(
                    f"{availability.value} metric {metric_id} must disable network access"
                )
            if not metric.get("reason"):
                raise ConfigValidationError(
                    f"{availability.value} metric {metric_id} requires a reason"
                )
        if metric.get("network_enabled") is True and metric.get("implemented") is True:
            try:
                assert_metric_network_eligible(bundle, metric_id)
            except SourceNotNetworkEligible as exc:
                raise ConfigValidationError(
                    f"network-enabled metric {metric_id} fails rights gate: {exc}"
                ) from exc

    for source_id, source in sources.items():
        for field in ("name", "tier"):
            if not isinstance(source.get(field), str) or not source[field]:
                raise ConfigValidationError(
                    f"source {source_id} requires non-empty {field}"
                )
        if not isinstance(source.get("enabled"), bool) or not isinstance(
            source.get("network_eligible"), bool
        ):
            raise ConfigValidationError(
                f"source {source_id} enablement flags must be boolean"
            )
        auth = source.get("auth")
        if not isinstance(auth, Mapping) or auth.get("mode") not in {
            "NONE",
            "API_KEY",
            "IDENTIFYING_USER_AGENT",
            "MANUAL",
        }:
            raise ConfigValidationError(f"source {source_id} has invalid auth")
        required_env = auth.get("required_env")
        if required_env is not None and (
            not isinstance(required_env, str) or not required_env
        ):
            raise ConfigValidationError(
                f"source {source_id} auth.required_env must be a string or null"
            )
        if auth.get("mode") in {"API_KEY", "IDENTIFYING_USER_AGENT"} and not required_env:
            raise ConfigValidationError(
                f"source {source_id} auth mode requires required_env"
            )
        rights = source.get("rights")
        if not isinstance(rights, Mapping):
            raise ConfigValidationError(f"source {source_id} requires rights metadata")
        if rights.get("status") not in {"CLEARED", "HOLD"}:
            raise ConfigValidationError(
                f"source {source_id} rights.status must be CLEARED or HOLD"
            )
        if not isinstance(rights.get("automated_fetch"), bool) or not isinstance(
            rights.get("public_redistribution"), bool
        ):
            raise ConfigValidationError(
                f"source {source_id} rights flags must be boolean"
            )
        if not isinstance(rights.get("attribution_note"), str) or not rights.get(
            "attribution_note"
        ):
            raise ConfigValidationError(
                f"source {source_id} requires an attribution_note"
            )
        held = rights.get("status") != "CLEARED"
        if held and (
            source.get("enabled") is not False
            or source.get("network_eligible") is not False
            or rights.get("automated_fetch") is not False
            or rights.get("public_redistribution") is not False
        ):
            raise ConfigValidationError(
                f"rights-held source {source_id} must be fully disabled"
            )

    companies = _unique_records(
        bundle.companies.get("companies"), "company_id", "companies"
    )
    if set(companies) != {"microsoft", "alphabet", "amazon", "meta"}:
        raise ConfigValidationError("companies registry must contain the four fixed hyperscalers")
    expected_company_contract = {
        "microsoft": (
            "MSFT",
            "0000789019",
            "06-30",
            "PaymentsToAcquirePropertyPlantAndEquipment",
        ),
        "alphabet": (
            "GOOGL",
            "0001652044",
            "12-31",
            "PaymentsToAcquirePropertyPlantAndEquipment",
        ),
        "amazon": (
            "AMZN",
            "0001018724",
            "12-31",
            "PaymentsToAcquireProductiveAssets",
        ),
        "meta": (
            "META",
            "0001326801",
            "12-31",
            "PaymentsToAcquirePropertyPlantAndEquipment",
        ),
    }
    for company in companies.values():
        cik = company.get("cik")
        if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit():
            raise ConfigValidationError(f"company {company['company_id']} CIK must be 10 digits")
        for field in ("name", "ticker", "fiscal_year_end", "capex_definition"):
            if not isinstance(company.get(field), str) or not company[field]:
                raise ConfigValidationError(
                    f"company {company['company_id']} requires {field}"
                )
        for field in (
            "preferred_xbrl_tags",
            "fallback_xbrl_tags",
            "known_disclosure_differences",
        ):
            values = company.get(field)
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise ConfigValidationError(
                    f"company {company['company_id']} {field} must be a string list"
                )
        if not company["preferred_xbrl_tags"]:
            raise ConfigValidationError(
                f"company {company['company_id']} requires a preferred XBRL tag"
            )
        ticker, expected_cik, fiscal_year_end, cash_tag = expected_company_contract[
            company["company_id"]
        ]
        if (
            company.get("ticker") != ticker
            or company.get("cik") != expected_cik
            or company.get("fiscal_year_end") != fiscal_year_end
            or company.get("xbrl_namespace") != "us-gaap"
            or company.get("preferred_xbrl_tags") != [cash_tag]
            or company.get("fallback_xbrl_tags") != []
            or company.get("finance_lease_xbrl_tags")
            != ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"]
            or company.get("manual_override") is not None
        ):
            raise ConfigValidationError(
                f"company {company['company_id']} does not match the reviewed P3 SEC contract"
            )

    fundamental_rules = bundle.alert_rules.get("alerts", {}).get(
        "fundamental_exit"
    )
    if not isinstance(fundamental_rules, Mapping) or (
        fundamental_rules.get("mode") != "EVIDENCE_ONLY"
        or fundamental_rules.get("assessments_enabled") is not False
        or fundamental_rules.get("total_blocks") != 4
        or fundamental_rules.get("evidence_block_ids")
        != [
            "aggregate_capex_acceleration",
            "orders_backlog",
            "prepayments_commitments",
            "company_breadth",
        ]
    ):
        raise ConfigValidationError(
            "alert_rules fundamental_exit must use the exact evidence-only P3 blocks"
        )

    tax_dates = _unique_records(
        bundle.us_tax_dates.get("tax_dates"), "event_id", "tax_dates"
    )
    if not bundle.us_tax_dates.get("reviewed_at"):
        raise ConfigValidationError("us_tax_dates requires reviewed_at")
    try:
        date.fromisoformat(bundle.us_tax_dates["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError("us_tax_dates.reviewed_at must be an ISO date") from exc
    for event in tax_dates.values():
        for field in ("original_deadline", "observed_deadline"):
            try:
                date.fromisoformat(event[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ConfigValidationError(
                    f"tax event {event['event_id']} has invalid {field}"
                ) from exc
        if not event.get("source_url"):
            raise ConfigValidationError(
                f"tax event {event['event_id']} requires source_url"
            )
        if event.get("reviewed") is not True or not event.get("reviewer") or not event.get("reviewed_at"):
            raise ConfigValidationError(
                f"tax event {event['event_id']} must be explicitly reviewed"
            )
        try:
            date.fromisoformat(event["reviewed_at"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(
                f"tax event {event['event_id']} reviewed_at must be an ISO date"
            ) from exc

    exercises = _unique_records(
        bundle.nyfed_operational_readiness.get("exercises"),
        "exercise_id",
        "exercises",
    )
    try:
        date.fromisoformat(bundle.nyfed_operational_readiness["reviewed_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigValidationError(
            "nyfed_operational_readiness.reviewed_at must be an ISO date"
        ) from exc
    reviewed_operation_ids: set[tuple[str, str]] = set()
    for exercise in exercises.values():
        try:
            date.fromisoformat(exercise["operation_date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigValidationError(
                f"exercise {exercise['exercise_id']} has invalid operation_date"
            ) from exc
        if exercise.get("operation_type") not in {"ON_RRP", "SRF"}:
            raise ConfigValidationError(
                f"exercise {exercise['exercise_id']} has invalid operation_type"
            )
        operation_id = exercise.get("operation_id")
        if exercise.get("operation_type") == "SRF":
            if not isinstance(operation_id, str) or not operation_id.strip():
                raise ConfigValidationError(
                    f"exercise {exercise['exercise_id']} requires operation_id"
                )
            operation_key = ("SRF", operation_id.strip())
            if operation_key in reviewed_operation_ids:
                raise ConfigValidationError(
                    f"duplicate reviewed SRF operation_id: {operation_id.strip()}"
                )
            reviewed_operation_ids.add(operation_key)
        elif operation_id is not None and (
            not isinstance(operation_id, str) or not operation_id.strip()
        ):
            raise ConfigValidationError(
                f"exercise {exercise['exercise_id']} has invalid operation_id"
            )
        if exercise.get("technical_exercise") is not True:
            raise ConfigValidationError(
                f"exercise {exercise['exercise_id']} must set technical_exercise=true"
            )
        if not exercise.get("source_url"):
            raise ConfigValidationError(
                f"exercise {exercise['exercise_id']} requires source_url"
            )
        if (
            exercise.get("reviewed") is not True
            or not exercise.get("reviewer")
            or not exercise.get("reviewed_at")
        ):
            raise ConfigValidationError(
                f"exercise {exercise['exercise_id']} must be explicitly reviewed"
            )
        try:
            date.fromisoformat(exercise["reviewed_at"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(
                f"exercise {exercise['exercise_id']} reviewed_at must be an ISO date"
            ) from exc
