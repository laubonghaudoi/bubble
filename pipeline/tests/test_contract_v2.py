import copy
import json
from pathlib import Path

import pytest

from pipeline.config import (
    CANONICAL_P0_METRIC_IDS,
    ConfigValidationError,
    SourceNotNetworkEligible,
    assert_metric_network_eligible,
    assert_source_network_eligible,
    effective_metric_state,
    load_config_bundle,
    validate_config_bundle,
)
from pipeline.contracts import (
    METHODOLOGY_FIELDS,
    ContractValidationError,
    validate_manifest,
    validate_alerts_file,
    validate_events_file,
    validate_publication,
    validate_series_file,
    validate_snapshot,
)


FIXTURE = Path(__file__).parent / "fixtures" / "snapshot_v2_minimal.json"


def fixture_snapshot():
    """Expand the compact JSON seed into the complete locked P1 metric roster."""

    snapshot = json.loads(FIXTURE.read_text())
    template = snapshot["metrics"]["spx_0dte_share"]
    held_ids = {
        "vix_vix3m_term_structure_proxy",
        "cboe_skew_tail_risk_proxy",
        "crypto_funding_btc",
        "crypto_funding_eth",
        "trend_following_positioning_proxy",
        "cross_asset_correlation",
    }
    for metric_id in held_ids:
        metric = copy.deepcopy(template)
        metric["metric_id"] = metric_id
        metric["label"] = metric_id
        metric["availability"] = "UNAVAILABLE_FREE"
        snapshot["metrics"][metric_id] = metric

    cftc_ids = {
        "cftc_e_mini_sp500_asset_manager_net_pct_oi": "ACTIVE_FREE",
        "cftc_e_mini_sp500_leveraged_funds_net_pct_oi": "ACTIVE_PROXY",
        "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi": "ACTIVE_FREE",
        "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi": "ACTIVE_PROXY",
    }
    for metric_id, availability in cftc_ids.items():
        metric = copy.deepcopy(template)
        metric.update(
            {
                "metric_id": metric_id,
                "label": metric_id,
                "availability": availability,
                "unit": "percent_open_interest",
                "frequency": "weekly",
                "updated_at": snapshot["generated_at"],
            }
        )
        metric["quality"].update(
            {
                "status": "ERROR",
                "freshness": "UNKNOWN",
                "last_attempt_at": snapshot["generated_at"],
                "failure_reason": "Fixture has no CFTC observations.",
                "sample_size": 0,
            }
        )
        metric["statistics"] = {
            "sample_size": 0,
            "net_position": None,
            "open_interest": None,
            "net_percent_open_interest": None,
            "change_8_weeks": None,
            "change_12_weeks": None,
            "z_score_3_year": None,
            "z_score_3_year_sample_size": 0,
        }
        metric["source"] = {
            "source_id": "cftc_pre",
            "name": "CFTC PRE",
            "url": "https://publicreporting.cftc.gov/",
            "tier": "OFFICIAL",
            "retrieved_at": snapshot["generated_at"],
            "rights_note": "Official CFTC data.",
        }
        is_proxy = availability == "ACTIVE_PROXY"
        metric["context"]["is_proxy"] = is_proxy
        metric["context"]["direction"] = "UNKNOWN"
        metric["methodology"]["proxy_disclosure"] = (
            "CFTC category is a proxy, not every CTA." if is_proxy else ""
        )
        snapshot["metrics"][metric_id] = metric
    snapshot["sources"]["cftc_tff_futures_only"] = {
        "collector_id": "cftc_tff_futures_only",
        "name": "CFTC PRE",
        "url": "https://publicreporting.cftc.gov/",
        "tier": "OFFICIAL",
        "rights_note": "Official CFTC data.",
        "status": "ERROR",
        "freshness": "UNKNOWN",
        "observation_date": None,
        "released_at": None,
        "updated_at": snapshot["generated_at"],
        "last_success_at": None,
        "last_attempt_at": snapshot["generated_at"],
        "expected_next_update": None,
        "failure_reason": "Fixture has no CFTC observations.",
    }
    snapshot["source_health"]["error"] += 1
    snapshot.update(
        {
            "active_free_count": 3,
            "active_proxy_count": 2,
            "manual_ready_count": 1,
            "unavailable_free_count": 6,
        }
    )
    return snapshot


def test_loads_schema_2_registry_bundle_and_canonical_p0_ids():
    bundle = load_config_bundle()
    assert bundle.metric_registry["schema_version"] == "2.0.0"
    assert bundle.source_registry["schema_version"] == "2.0.0"
    assert CANONICAL_P0_METRIC_IDS <= bundle.metrics_by_id.keys()


def test_every_registry_metric_has_locked_methodology_contract():
    bundle = load_config_bundle()
    for metric in bundle.metrics_by_id.values():
        methodology = metric["methodology"]
        assert METHODOLOGY_FIELDS <= methodology.keys()
        assert isinstance(methodology["confirm_with"], list)
        assert methodology["proxy_disclosure"] == metric["proxy_disclosure"]


def test_release_two_marks_p0_and_p1_interfaces_implemented():
    bundle = load_config_bundle()
    assert all(metric["implemented"] for metric in bundle.metrics_by_id.values() if metric["phase"] in {"P0", "P1"})
    assert all(not metric["implemented"] for metric in bundle.metrics_by_id.values() if metric["phase"] in {"P2", "P3"})


def test_snapshot_v2_contract_preserves_null_and_zero_distinction():
    snapshot = fixture_snapshot()
    validate_snapshot(snapshot)
    assert snapshot["metrics"]["spx_0dte_share"]["value"] is None

    zero_snapshot = copy.deepcopy(snapshot)
    zero_snapshot["metrics"]["on_rrp_accepted"]["value"] = 0
    validate_snapshot(zero_snapshot)
    assert zero_snapshot["metrics"]["on_rrp_accepted"]["value"] == 0

    invalid = copy.deepcopy(snapshot)
    invalid["metrics"]["spx_0dte_share"]["value"] = 0
    with pytest.raises(ContractValidationError, match="must be null"):
        validate_snapshot(invalid)


def test_contract_axes_reject_legacy_or_conflated_states():
    snapshot = fixture_snapshot()
    snapshot["metrics"]["on_rrp_accepted"]["quality"]["status"] = "missing"
    with pytest.raises(ContractValidationError, match="quality.status"):
        validate_snapshot(snapshot)


def test_statistics_are_numeric_or_null_and_attempt_time_is_utc():
    snapshot = fixture_snapshot()
    snapshot["metrics"]["on_rrp_accepted"]["statistics"]["optional"] = None
    validate_snapshot(snapshot)

    invalid_statistic = copy.deepcopy(snapshot)
    invalid_statistic["metrics"]["on_rrp_accepted"]["statistics"]["trend"] = "down"
    with pytest.raises(ContractValidationError, match="statistics.trend"):
        validate_snapshot(invalid_statistic)

    invalid_attempt = copy.deepcopy(snapshot)
    invalid_attempt["metrics"]["on_rrp_accepted"]["quality"]["last_attempt_at"] = (
        "2026-08-11T14:15:00-04:00"
    )
    with pytest.raises(ContractValidationError, match="must use UTC"):
        validate_snapshot(invalid_attempt)


def test_publication_contract_hard_cuts_v1_and_cross_checks_all_metric_ids():
    snapshot = fixture_snapshot()
    manifest = {
        "schema_version": "2.0.0",
        "generated_at": snapshot["generated_at"],
        "metrics": [
            {
                "metric_id": metric_id,
                "label": metric["label"],
                "unit": metric["unit"],
                "frequency": metric["frequency"],
                "layer": "liquidity_fuel" if metric_id == "on_rrp_accepted" else "market_ignition",
                "phase": "P0" if metric_id == "on_rrp_accepted" else "P2",
                "role": "evidence",
                "availability": metric["availability"],
                "series_path": f"data/series/{metric_id}.json",
            }
            for metric_id, metric in snapshot["metrics"].items()
        ],
    }
    series = {
        metric_id: {
            "schema_version": "2.0.0",
            "metric_id": metric_id,
            "label": metric["label"],
            "unit": metric["unit"],
            "frequency": metric["frequency"],
            "availability": metric["availability"],
            "quality": metric["quality"],
            "observation_date": metric["observation_date"],
            "released_at": metric["released_at"],
                "updated_at": metric["updated_at"],
                "expected_next_update": metric["expected_next_update"],
                "source": metric["source"],
            "observations": metric["short_series"],
        }
        for metric_id, metric in snapshot["metrics"].items()
    }

    validate_manifest(manifest)
    for value in series.values():
        validate_series_file(value)
    validate_publication(snapshot, manifest, series)

    legacy = copy.deepcopy(manifest)
    legacy["schema_version"] = "1.0.0"
    with pytest.raises(ContractValidationError, match="schema_version"):
        validate_manifest(legacy)

    incomplete = dict(series)
    incomplete.pop("spx_0dte_share")
    with pytest.raises(ContractValidationError, match="must match exactly"):
        validate_publication(snapshot, manifest, incomplete)


def test_series_contract_requires_sorted_unique_real_dates():
    snapshot = fixture_snapshot()
    metric = snapshot["metrics"]["on_rrp_accepted"]
    series = {
        "schema_version": "2.0.0",
        "metric_id": metric["metric_id"],
        "label": metric["label"],
        "unit": metric["unit"],
        "frequency": metric["frequency"],
        "availability": metric["availability"],
        "quality": metric["quality"],
        "observation_date": metric["observation_date"],
        "released_at": metric["released_at"],
                "updated_at": metric["updated_at"],
                "expected_next_update": metric["expected_next_update"],
                "source": metric["source"],
        "observations": list(reversed(metric["short_series"])),
    }
    with pytest.raises(ContractValidationError, match="strictly increasing"):
        validate_series_file(series)


def test_publication_cross_checks_contract_critical_metric_fields():
    snapshot = fixture_snapshot()
    manifest = {
        "schema_version": "2.0.0",
        "generated_at": snapshot["generated_at"],
        "metrics": [],
    }
    series = {}
    for metric_id, metric in snapshot["metrics"].items():
        manifest["metrics"].append(
            {
                "metric_id": metric_id,
                "label": metric["label"],
                "unit": metric["unit"],
                "frequency": metric["frequency"],
                "layer": "liquidity_fuel" if metric_id == "on_rrp_accepted" else "market_ignition",
                "phase": "P0" if metric_id == "on_rrp_accepted" else "P2",
                "role": "evidence",
                "availability": metric["availability"],
                "series_path": f"data/series/{metric_id}.json",
            }
        )
        series[metric_id] = {
            "schema_version": "2.0.0",
            "metric_id": metric_id,
            "label": metric["label"],
            "unit": metric["unit"],
            "frequency": metric["frequency"],
            "availability": metric["availability"],
            "quality": metric["quality"],
            "observation_date": metric["observation_date"],
            "released_at": metric["released_at"],
                "updated_at": metric["updated_at"],
                "expected_next_update": metric["expected_next_update"],
                "source": metric["source"],
            "observations": metric["short_series"],
        }
    series["on_rrp_accepted"] = {
        **series["on_rrp_accepted"],
        "unit": "percent",
    }
    with pytest.raises(ContractValidationError, match="unit must match"):
        validate_publication(snapshot, manifest, series)

    series["on_rrp_accepted"] = {
        **series["on_rrp_accepted"],
        "unit": snapshot["metrics"]["on_rrp_accepted"]["unit"],
        "observations": [
            *series["on_rrp_accepted"]["observations"][:-1],
            {
                **series["on_rrp_accepted"]["observations"][-1],
                "value": 999_999,
            },
        ],
    }
    with pytest.raises(ContractValidationError, match="short_series must match"):
        validate_publication(snapshot, manifest, series)


def test_publication_rejects_internally_mixed_switches_and_timestamps():
    snapshot = fixture_snapshot()
    manifest = {
        "schema_version": "2.0.0",
        "generated_at": snapshot["generated_at"],
        "metrics": [],
    }
    series = {}
    for metric_id, metric in snapshot["metrics"].items():
        manifest["metrics"].append(
            {
                "metric_id": metric_id,
                "label": metric["label"],
                "unit": metric["unit"],
                "frequency": metric["frequency"],
                "layer": "liquidity_fuel" if metric_id == "on_rrp_accepted" else "market_ignition",
                "phase": "P0" if metric_id == "on_rrp_accepted" else "P2",
                "role": "evidence",
                "availability": metric["availability"],
                "series_path": f"data/series/{metric_id}.json",
            }
        )
        series[metric_id] = {
            "schema_version": "2.0.0",
            "metric_id": metric_id,
            "label": metric["label"],
            "unit": metric["unit"],
            "frequency": metric["frequency"],
            "availability": metric["availability"],
            "quality": metric["quality"],
            "observation_date": metric["observation_date"],
            "released_at": metric["released_at"],
            "updated_at": metric["updated_at"],
            "source": metric["source"],
            "observations": metric["short_series"],
        }

    bad_count = copy.deepcopy(snapshot)
    bad_count["switches"]["liquidity_fuel"]["available_blocks"] = 0
    with pytest.raises(ContractValidationError, match="available_blocks must equal"):
        validate_publication(bad_count, manifest, series)

    bad_overall = copy.deepcopy(snapshot)
    bad_overall["overall_assessment"] = "STRESS"
    with pytest.raises(ContractValidationError, match="overall_assessment must equal"):
        validate_publication(bad_overall, manifest, series)

    bad_timestamp = copy.deepcopy(manifest)
    bad_timestamp["generated_at"] = "2000-01-01T00:00:00Z"
    with pytest.raises(ContractValidationError, match="generated_at must match"):
        validate_publication(snapshot, bad_timestamp, series)


def test_standalone_alerts_and_events_require_v2_shapes():
    with pytest.raises(ContractValidationError, match="schema_version"):
        validate_alerts_file({"garbage": True})
    with pytest.raises(ContractValidationError, match="events must be a list"):
        validate_events_file(
            {
                "schema_version": "2.0.0",
                "generated_at": "2026-08-12T20:00:00Z",
                "events": "not-a-list",
            }
        )


def test_rights_held_sources_are_not_network_eligible():
    bundle = load_config_bundle()
    for source_id in (
        "fred_third_party",
        "finra_margin",
        "cboe",
        "ssga_spy",
        "coinbase_market_data",
        "bybit_market_data",
        "licensed_provider",
    ):
        source = bundle.sources_by_id[source_id]
        assert source["enabled"] is False
        assert source["network_eligible"] is False
        assert source["rights"]["status"] == "HOLD"
        with pytest.raises(SourceNotNetworkEligible):
            assert_source_network_eligible(bundle, source_id)


def test_metric_rights_gate_prevents_held_source_network_access():
    bundle = load_config_bundle()
    with pytest.raises(SourceNotNetworkEligible):
        assert_metric_network_eligible(bundle, "finra_margin_debt")
    with pytest.raises(SourceNotNetworkEligible):
        assert_metric_network_eligible(bundle, "vix_vix3m_term_structure_proxy")


def test_metric_rights_gate_allows_nyfed_p0_metrics():
    bundle = load_config_bundle()
    sources = assert_metric_network_eligible(bundle, "on_rrp_accepted")
    assert [source["source_id"] for source in sources] == ["nyfed_markets"]


def test_every_canonical_p0_metric_passes_static_rights_gate():
    bundle = load_config_bundle()
    for metric_id in CANONICAL_P0_METRIC_IDS:
        assert assert_metric_network_eligible(bundle, metric_id)


def test_rights_held_p1_interface_stays_null_after_implementation():
    bundle = load_config_bundle()
    metric = bundle.metrics_by_id["vix_vix3m_term_structure_proxy"]
    assert metric["availability"] == "UNAVAILABLE_FREE"
    assert metric["implemented"] is True
    with pytest.raises(SourceNotNetworkEligible):
        assert_metric_network_eligible(bundle, metric["metric_id"])
    state = effective_metric_state(metric)
    assert state.availability.value == "UNAVAILABLE_FREE"
    assert state.health.value == "NOT_APPLICABLE"
    assert state.freshness.value == "UNKNOWN"
    assert state.value is None


def test_implemented_active_metric_defers_quality_to_collector():
    bundle = load_config_bundle()
    state = effective_metric_state(bundle.metrics_by_id["on_rrp_accepted"])
    assert state.availability.value == "ACTIVE_FREE"
    assert state.health is None
    assert state.freshness is None


def test_fred_government_series_are_allowlisted_and_third_party_is_rejected():
    bundle = load_config_bundle()
    assert_metric_network_eligible(bundle, "iorb")
    assert_metric_network_eligible(bundle, "reserve_balances")
    source = bundle.sources_by_id["fred_government"]
    assert source["auth"]["required_env"] == "FRED_API_KEY"
    with pytest.raises(SourceNotNetworkEligible, match="not allowlisted"):
        assert_source_network_eligible(
            bundle, "fred_government", series_ids=["SP500"]
        )


def test_rights_hold_cannot_be_enabled_by_configuration_drift():
    bundle = load_config_bundle()
    source = bundle.sources_by_id["cboe"]
    source["enabled"] = True
    source["network_eligible"] = True
    with pytest.raises(ConfigValidationError, match="rights-held source cboe"):
        validate_config_bundle(bundle)


def test_operational_readiness_calendar_uses_explicit_official_entries():
    bundle = load_config_bundle()
    entries = bundle.nyfed_operational_readiness["exercises"]
    assert {(entry["operation_date"], entry["operation_type"]) for entry in entries} == {
        ("2026-05-13", "ON_RRP"),
        ("2026-05-27", "SRF"),
    }
    assert all(entry["technical_exercise"] is True for entry in entries)
    srf = next(entry for entry in entries if entry["operation_type"] == "SRF")
    assert srf["operation_id"] == "RP 052726 99"

    invalid = copy.deepcopy(bundle)
    invalid_srf = next(
        entry
        for entry in invalid.nyfed_operational_readiness["exercises"]
        if entry["operation_type"] == "SRF"
    )
    invalid_srf.pop("operation_id")
    with pytest.raises(ConfigValidationError, match="requires operation_id"):
        validate_config_bundle(invalid)


def test_alert_and_tax_config_use_locked_sample_and_window_rules():
    bundle = load_config_bundle()
    rules = bundle.alert_rules["alerts"]["technical_context"]
    assert rules["large_treasury_settlement_min_nonzero_samples"] == 60
    assert rules["tax_window_business_days_before"] == 1
    assert rules["tax_window_business_days_after"] == 1
    assert all(
        event["reviewed"] is True
        for event in bundle.us_tax_dates["tax_dates"]
    )
