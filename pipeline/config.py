"""Load and validate version-controlled Bubble pipeline configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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


def validate_config_bundle(bundle: ConfigBundle) -> None:
    metrics = _unique_records(
        bundle.metric_registry.get("metrics"), "metric_id", "metrics"
    )
    sources = _unique_records(
        bundle.source_registry.get("sources"), "source_id", "sources"
    )
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
