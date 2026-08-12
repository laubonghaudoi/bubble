from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from pipeline.collectors.sec_form4 import Form4Collection
from pipeline.contracts import (
    P2_COLLECTOR_SOURCES,
    P2_HELD_METRICS,
    ContractValidationError,
    validate_publication,
)
from pipeline.release import build_release
from pipeline.tests.test_p2_form4_ledger_transform import parsed_fixture
from pipeline.tests.test_release1 import NOW, fixture_collectors


MACRO_ID = "nonfinancial_equities_gdp_proxy"


@pytest.fixture
def publication(tmp_path):
    filing = parsed_fixture()

    def sec_form4(**_kwargs):
        return Form4Collection(
            filings=(filing,),
            reused_ledger_accessions=(),
            master_accessions_by_day={"2026-08-11": (filing.accession,)},
            completed_index_days=("2026-08-11",),
            discovered_index_days=("2026-08-11",),
            failures=(),
            reviews=(),
            source_requests=2,
        )

    result = build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=replace(fixture_collectors(), sec_form4=sec_form4),
    )
    validate_publication(result.snapshot, result.manifest, result.series_by_id)
    return result


def test_macro_full_series_recomputes_components_changes_and_rolling_statistics(
    publication,
):
    cases = (
        ("value", 999.0, "value does not reconcile to components"),
        ("equity_usd_bn", 1.0, "value does not reconcile to components"),
        ("change_1_quarter_pp", 999.0, "prior exact quarter"),
        ("qoq_percent_change", 999.0, "qoq_percent_change does not reconcile"),
        ("yoy_percent_change", 999.0, "yoy_percent_change does not reconcile"),
        ("percentile_10y", 1.0, "percentile_10y does not reconcile"),
        (
            "percentile_10y_sample_size",
            99,
            "percentile_10y_sample_size does not match",
        ),
    )
    for field, replacement, message in cases:
        series = copy.deepcopy(publication.series_by_id)
        series[MACRO_ID]["observations"][-1][field] = replacement
        with pytest.raises(ContractValidationError, match=message):
            validate_publication(publication.snapshot, publication.manifest, series)


def test_macro_full_series_requires_exact_quarter_and_realtime_provenance(publication):
    cases = (
        ("quarter", "2026-Q2", "calendar-quarter end"),
        (
            "equities_source_date",
            "2026-04-01",
            "exact common quarter",
        ),
        (
            "equities_realtime_start",
            "2026-07-01",
            "realtime interval is inverted",
        ),
    )
    for field, replacement, message in cases:
        series = copy.deepcopy(publication.series_by_id)
        series[MACRO_ID]["observations"][-1][field] = replacement
        with pytest.raises(ContractValidationError, match=message):
            validate_publication(publication.snapshot, publication.manifest, series)


@pytest.mark.parametrize(
    ("section", "field", "replacement", "message"),
    (
        ("statistics", "equity_usd_bn", 1.0, "statistics.equity_usd_bn"),
        ("statistics", "gdp_usd_bn", 1.0, "statistics.gdp_usd_bn"),
        ("statistics", "qoq_percent_change", 1.0, "statistics.qoq_percent_change"),
        ("statistics", "yoy_percent_change", 1.0, "statistics.yoy_percent_change"),
        ("statistics", "percentile_10y", 1.0, "statistics.percentile_10y"),
        (
            "statistics",
            "percentile_10y_sample_size",
            1,
            "statistics.percentile_10y_sample_size",
        ),
        ("changes", "one_quarter", 1.0, "changes.one_quarter"),
        ("context", "common_quarter", "2000-Q1", "context must match"),
        (
            "context",
            "equity_observation_date",
            "2000-01-01",
            "context must match",
        ),
        (
            "context",
            "gdp_observation_date",
            "2000-01-01",
            "context must match",
        ),
        ("quality", "sample_size", 1, "quality.sample_size"),
    ),
)
def test_macro_snapshot_endpoint_fields_must_match_full_series(
    publication, section, field, replacement, message
):
    snapshot = copy.deepcopy(publication.snapshot)
    snapshot["metrics"][MACRO_ID][section][field] = replacement
    series = publication.series_by_id
    if section == "quality":
        series = copy.deepcopy(publication.series_by_id)
        series[MACRO_ID]["quality"][field] = replacement
    with pytest.raises(ContractValidationError, match=message):
        validate_publication(snapshot, publication.manifest, series)


@pytest.mark.parametrize("collector_id", tuple(P2_COLLECTOR_SOURCES))
def test_p2_requires_both_exact_collector_source_records(publication, collector_id):
    snapshot = copy.deepcopy(publication.snapshot)
    del snapshot["sources"][collector_id]
    with pytest.raises(ContractValidationError, match=f"sources.{collector_id} is required"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("collector_id", "alias"),
        ("name", "Wrong source"),
        ("status", "STALE"),
        ("freshness", "STALE"),
        ("observation_date", "2000-01-01"),
        ("released_at", "2000-01-01T00:00:00Z"),
        ("updated_at", "2000-01-01T00:00:00Z"),
        ("last_success_at", "2000-01-01T00:00:00Z"),
        ("last_attempt_at", "2000-01-01T00:00:00Z"),
        ("expected_next_update", "2000-01-01"),
        ("failure_reason", "invented failure"),
    ),
)
@pytest.mark.parametrize("collector_id", tuple(P2_COLLECTOR_SOURCES))
def test_p2_collector_source_state_must_reconcile_to_its_metric(
    publication, collector_id, field, replacement
):
    snapshot = copy.deepcopy(publication.snapshot)
    snapshot["sources"][collector_id][field] = replacement
    with pytest.raises(ContractValidationError, match=collector_id):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


@pytest.mark.parametrize(
    ("collector_id", "expected_source_id"),
    tuple(
        (collector_id, source_id)
        for collector_id, (_metric_id, source_id) in P2_COLLECTOR_SOURCES.items()
    ),
)
def test_p2_metric_provenance_id_and_retrieval_must_match_attempt(
    publication, collector_id, expected_source_id
):
    metric_id = P2_COLLECTOR_SOURCES[collector_id][0]
    snapshot = copy.deepcopy(publication.snapshot)
    snapshot["metrics"][metric_id]["source"]["source_id"] = "alias"
    with pytest.raises(ContractValidationError, match=f"must be {expected_source_id}"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)

    snapshot = copy.deepcopy(publication.snapshot)
    snapshot["metrics"][metric_id]["source"]["retrieved_at"] = (
        "2000-01-01T00:00:00Z"
    )
    with pytest.raises(ContractValidationError, match="retrieved_at must match"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


@pytest.mark.parametrize("metric_id", tuple(sorted(P2_HELD_METRICS)))
def test_every_rights_held_p2_metric_has_no_attempt_timestamp(publication, metric_id):
    snapshot = copy.deepcopy(publication.snapshot)
    snapshot["metrics"][metric_id]["quality"]["last_attempt_at"] = (
        snapshot["generated_at"]
    )
    with pytest.raises(ContractValidationError, match="last_attempt_at must be null"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    (
        (("observation_date",), "2026-08-12", "observation_date must be null"),
        (("released_at",), "2026-08-12T20:00:00Z", "released_at must be null"),
        (("updated_at",), "2026-08-12T20:00:00Z", "updated_at must be null"),
        (("expected_next_update",), "2026-08-13", "expected_next_update must be null"),
        (
            ("quality", "last_success_at"),
            "2026-08-12T20:00:00Z",
            "last_success_at must be null",
        ),
        (
            ("quality", "last_attempt_at"),
            "2026-08-12T20:00:00Z",
            "last_attempt_at must be null",
        ),
        (("source", "source_id"), "forbidden", "source.source_id must be null"),
        (
            ("source", "retrieved_at"),
            "2026-08-12T20:00:00Z",
            "source.retrieved_at must be null",
        ),
    ),
)
def test_rights_held_p2_metrics_reject_all_collection_and_provenance_state(
    publication, path, replacement, message
):
    snapshot = copy.deepcopy(publication.snapshot)
    target = snapshot["metrics"]["gamma_flip"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(ContractValidationError, match=message):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


def test_p2_cannot_rewrite_the_liquidity_based_overall_assessment(publication):
    snapshot = copy.deepcopy(publication.snapshot)
    liquidity_assessment = snapshot["switches"]["liquidity_fuel"]["assessment"]
    snapshot["overall_assessment"] = (
        "NEUTRAL" if liquidity_assessment != "NEUTRAL" else "STRESS"
    )
    with pytest.raises(ContractValidationError, match="overall_assessment must equal"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)
