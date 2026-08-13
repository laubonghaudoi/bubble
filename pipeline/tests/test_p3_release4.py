from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from pipeline.contracts import ContractValidationError, validate_publication, validate_snapshot
from pipeline.manual_signals import MANUAL_SIGNAL_COLUMNS
from pipeline.release import build_release
from pipeline.tests.test_p3_capex import _synthetic_bundle, companies
from pipeline.tests.test_p3_manual_signals import valid_row
from pipeline.tests.test_release1 import fixture_collectors


NOW = datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)
AUTOMATED_IDS = (
    "hyperscaler_aggregate_cash_capex",
    "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp",
)


def p3_bundles():
    output = {}
    for index, company in enumerate(companies(), start=1):
        bundle = _synthetic_bundle(company, index)
        for group in ("cash_capex_facts", "finance_lease_facts"):
            for fact in bundle[group]:
                accession = fact["accession"].replace("-", "")
                fact["filing_url"] = (
                    "https://www.sec.gov/Archives/edgar/data/"
                    f"{int(company['cik'])}/{accession}/filing.htm"
                )
        output[company["company_id"]] = bundle
    return output


def p3_collectors(*, error: Exception | None = None):
    def collect(_companies):
        if error is not None:
            raise error
        return deepcopy(p3_bundles())

    return replace(fixture_collectors(), sec_companyfacts=collect)


def write_manual_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANUAL_SIGNAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_valid_publication(tmp_path, *, rows=()):
    manual = tmp_path / "industry_signals.csv"
    write_manual_csv(manual, rows)
    return build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=p3_collectors(),
        manual_signals_path=manual,
    )


def test_release_four_builds_two_automated_blocks_and_three_manual_ready_metrics(
    tmp_path,
):
    manual = tmp_path / "industry_signals.csv"
    write_manual_csv(manual, [])
    publication = build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=p3_collectors(),
        manual_signals_path=manual,
    )
    validate_publication(
        publication.snapshot, publication.manifest, publication.series_by_id
    )
    snapshot = publication.snapshot
    switch = snapshot["switches"]["fundamental_exit"]
    assert switch["mode"] == "EVIDENCE_ONLY"
    assert switch["assessment"] is None
    assert switch["available_blocks"] == 2
    assert switch["confidence"] == "LOW"
    assert [block["id"] for block in switch["evidence_blocks"]] == [
        "aggregate_capex_acceleration",
        "orders_backlog",
        "prepayments_commitments",
        "company_breadth",
    ]
    assert all(snapshot["metrics"][metric_id]["quality"]["status"] == "OK" for metric_id in AUTOMATED_IDS)
    assert all(len(publication.series_by_id[metric_id]["observations"]) == 12 for metric_id in AUTOMATED_IDS)
    assert snapshot["metrics"][AUTOMATED_IDS[0]]["value"] == 259
    assert snapshot["metrics"][AUTOMATED_IDS[1]]["value"] == -4.378019
    assert snapshot["metrics"][AUTOMATED_IDS[0]]["context"]["technical_flags"] == []
    assert snapshot["sources"]["sec_companyfacts_capex"]["status"] == "OK"
    assert len(snapshot["sources"]) == 11
    assert "manual_public_filings" not in snapshot["sources"]
    for metric_id in (
        "ai_upstream_orders_backlog",
        "customer_prepayments_contract_commitments",
        "take_or_pay_commitments",
    ):
        metric = snapshot["metrics"][metric_id]
        assert metric["availability"] == "MANUAL_READY"
        assert metric["value"] is None
        assert metric["source"]["source_id"] == "manual_public_filings"
        assert metric.get("details") is None
        assert publication.series_by_id[metric_id]["observations"] == []


def test_release_four_manual_true_zero_activates_evidence_without_network_collector(
    tmp_path,
):
    manual = tmp_path / "industry_signals.csv"
    write_manual_csv(
        manual,
        [valid_row(value="0", unit="count", yoy_pct="0")],
    )
    publication = build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=p3_collectors(),
        manual_signals_path=manual,
    )
    metric = publication.snapshot["metrics"]["ai_upstream_orders_backlog"]
    assert metric["availability"] == "ACTIVE_FREE"
    assert metric["value"] is None
    assert metric["details"]["manual_evidence"]["records"][0]["value"] == 0
    assert publication.snapshot["switches"]["fundamental_exit"]["available_blocks"] == 3
    assert "manual_public_filings" not in publication.snapshot["sources"]
    validate_publication(
        publication.snapshot, publication.manifest, publication.series_by_id
    )


def test_release_four_stale_reviewed_manual_evidence_is_not_described_as_missing(
    tmp_path,
):
    manual = tmp_path / "industry_signals.csv"
    write_manual_csv(manual, [valid_row()])
    publication = build_release(
        data_dir=tmp_path / "last-good",
        now=datetime(2026, 12, 15, 12, 0, tzinfo=timezone.utc),
        collectors=p3_collectors(),
        manual_signals_path=manual,
    )
    block = publication.snapshot["switches"]["fundamental_exit"][
        "evidence_blocks"
    ][1]
    assert block["available"] is False
    assert block["status"] == "STALE"
    assert "已有經 PR 覆核" in block["summary"]
    assert "超過 120 日" in block["summary"]
    assert "尚未有" not in block["summary"]


def test_release_four_collector_failure_keeps_last_good_stale_and_removes_coverage(
    tmp_path,
):
    manual = tmp_path / "industry_signals.csv"
    write_manual_csv(manual, [])
    first = build_release(
        data_dir=tmp_path / "empty",
        now=NOW,
        collectors=p3_collectors(),
        manual_signals_path=manual,
    )
    from pipeline.release import write_stage, promote_stage

    stage = tmp_path / "stage"
    target = tmp_path / "published"
    write_stage(first, stage)
    promote_stage(stage, data_dir=target)
    failed = build_release(
        data_dir=target,
        group="quarterly",
        now=datetime(2026, 8, 13, 2, 0, tzinfo=timezone.utc),
        collectors=p3_collectors(error=RuntimeError("SEC unavailable")),
        manual_signals_path=manual,
    )
    for metric_id in AUTOMATED_IDS:
        metric = failed.snapshot["metrics"][metric_id]
        assert metric["quality"]["status"] == "STALE"
        assert metric["value"] == first.snapshot["metrics"][metric_id]["value"]
        assert "SEC unavailable" in metric["quality"]["failure_reason"]
    assert failed.snapshot["switches"]["fundamental_exit"]["available_blocks"] == 0
    assert failed.snapshot["switches"]["fundamental_exit"]["confidence"] == "UNKNOWN"
    validate_publication(failed.snapshot, failed.manifest, failed.series_by_id)


def test_release_four_contract_rejects_extra_automated_collector(tmp_path):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    snapshot["sources"]["fake_collector"] = {
        **deepcopy(snapshot["sources"]["nyfed_rates"]),
        "collector_id": "fake_collector",
    }
    snapshot["source_health"]["ok"] += 1
    with pytest.raises(ContractValidationError, match="exact automated collector set"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


def test_release_four_contract_rejects_collector_source_severity_injection(tmp_path):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    snapshot["sources"]["sec_companyfacts_capex"]["severity"] = "STRESS"
    with pytest.raises(ContractValidationError, match="exact collector source fields"):
        validate_snapshot(snapshot)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("form", "8-K", "form is not an allowed"),
        ("form", "10-K", "form does not match fiscal_quarter"),
        ("quarterization_method", "MADE_UP", "does not match fiscal_quarter"),
        ("fiscal_quarter", "FY9999Q3", "does not match issuer fiscal calendar"),
        ("context_start", "1900-01-01", "does not match the fiscal YTD context"),
        ("filed_at", "1900-01-01", "must follow context end"),
        ("accepted_at", "2030-01-01T00:00:00Z", "must not be future-dated"),
    ],
)
def test_release_four_contract_rejects_unreviewed_company_fact_domains(
    tmp_path, field, value, message
):
    publication = build_valid_publication(tmp_path)
    series = deepcopy(publication.series_by_id)
    for metric_id in AUTOMATED_IDS:
        company = series[metric_id]["observations"][0]["companies"][0]
        company[field] = value
        if field == "accepted_at":
            company["filed_at"] = value[:10]
    with pytest.raises(ContractValidationError, match=message):
        validate_publication(publication.snapshot, publication.manifest, series)


def test_release_four_contract_recomputes_company_growth_from_full_series(tmp_path):
    publication = build_valid_publication(tmp_path)
    series = deepcopy(publication.series_by_id)
    for metric_id in AUTOMATED_IDS:
        series[metric_id]["observations"][5]["companies"][0][
            "yoy_percent_change"
        ] += 10
    with pytest.raises(ContractValidationError, match="yoy_percent_change does not reconcile"):
        validate_publication(publication.snapshot, publication.manifest, series)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("date", "1900-01-01", "identity, tag, unit, or period"),
        ("injected", "STRESS", "exact P3 company fields"),
        (
            "filing_url",
            "https://www.sec.gov/Archives/edgar/data/1652044/"
            "000165204423000003/bogus.txt?x=1",
            "direct SEC filing document",
        ),
        (
            "finance_lease_accession",
            "0001652044-23-999999",
            "must match the cash filing accession",
        ),
    ],
)
def test_release_four_contract_locks_nested_company_schema_and_filing_provenance(
    tmp_path, field, value, message
):
    publication = build_valid_publication(tmp_path)
    series = deepcopy(publication.series_by_id)
    for metric_id in AUTOMATED_IDS:
        series[metric_id]["observations"][0]["companies"][0][field] = value
    with pytest.raises(ContractValidationError, match=message):
        validate_publication(publication.snapshot, publication.manifest, series)


def test_release_four_contract_requires_atomic_automated_quality(tmp_path):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    acceleration = snapshot["metrics"][AUTOMATED_IDS[1]]
    acceleration["quality"]["status"] = "STALE"
    acceleration["quality"]["failure_reason"] = "Synthetic stale attempt."
    acceleration["context"]["confidence"] = "MEDIUM"
    with pytest.raises(ContractValidationError, match=r"share quality\.status"):
        validate_snapshot(snapshot)


def test_release_four_contract_locks_source_registry_metadata(tmp_path):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    snapshot["metrics"][AUTOMATED_IDS[0]]["source"]["url"] = (
        "https://evil.example/fake-feed"
    )
    snapshot["metrics"][AUTOMATED_IDS[0]]["provenance"][0]["url"] = (
        "https://evil.example/fake-feed"
    )
    with pytest.raises(ContractValidationError, match="source metadata does not match"):
        validate_snapshot(snapshot)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"source_url": "https://evil.example/forged"}, "allowlisted official source"),
        ({"source_type": "BLOG"}, "source_type is not allowlisted"),
        ({"unit": "bananas"}, "unit is not allowlisted"),
        ({"value": -4}, "value must be non-negative"),
    ],
)
def test_release_four_contract_revalidates_manual_public_records(
    tmp_path, updates, message
):
    publication = build_valid_publication(tmp_path, rows=[valid_row()])
    snapshot = deepcopy(publication.snapshot)
    record = snapshot["metrics"]["ai_upstream_orders_backlog"]["details"][
        "manual_evidence"
    ]["records"][0]
    record.update(updates)
    with pytest.raises(ContractValidationError, match=message):
        validate_snapshot(snapshot)


def test_release_four_contract_derives_manual_staleness_from_generated_date(tmp_path):
    publication = build_valid_publication(tmp_path, rows=[valid_row()])
    snapshot = deepcopy(publication.snapshot)
    snapshot["generated_at"] = "2027-01-01T12:00:00Z"
    with pytest.raises(ContractValidationError, match="120-day evidence age"):
        validate_snapshot(snapshot)


def test_release_four_contract_forbids_p3_severity_alert_injection(tmp_path):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    snapshot["alerts"].append(
        {"level": "STRESS", "title": "Fundamental Exit P3", "detail": "P3 severity"}
    )
    with pytest.raises(ContractValidationError, match="alerts must contain only"):
        validate_snapshot(snapshot)


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("switch", "exact evidence-only switch fields"),
        ("block", "exact evidence-only fields"),
        ("metric", "exact P3 metric fields"),
    ],
)
def test_release_four_contract_rejects_p3_severity_shape_injection(
    tmp_path, target, message
):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    if target == "switch":
        snapshot["switches"]["fundamental_exit"]["severity"] = "STRESS"
    elif target == "block":
        snapshot["switches"]["fundamental_exit"]["evidence_blocks"][0][
            "severity"
        ] = "STRESS"
    else:
        snapshot["metrics"][AUTOMATED_IDS[0]]["assessment"] = "STRESS"
    with pytest.raises(ContractValidationError, match=message):
        validate_snapshot(snapshot)


def test_release_four_contract_locks_metric_provenance_to_reviewed_source(tmp_path):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    snapshot["metrics"][AUTOMATED_IDS[0]]["provenance"] = [
        {"source_id": "evil"}
    ]
    with pytest.raises(ContractValidationError, match="provenance must contain"):
        validate_snapshot(snapshot)


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("quality", "quality must use the exact P3 fields"),
        ("source", "source must use the exact P3 fields"),
        ("context", "context must use the exact P3 fields"),
        ("methodology", "methodology must use the exact P3 fields"),
        ("fundamental", "fundamental must use the exact P3 fields"),
        ("series", "series must use the exact P3 envelope"),
        ("manifest", "manifest must use the exact P3 fields"),
    ],
)
def test_release_four_contract_rejects_nested_or_artifact_severity_injection(
    tmp_path, target, message
):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    manifest = deepcopy(publication.manifest)
    series = deepcopy(publication.series_by_id)
    metric_id = AUTOMATED_IDS[0]
    if target == "quality":
        snapshot["metrics"][metric_id]["quality"]["severity"] = "STRESS"
        series[metric_id]["quality"]["severity"] = "STRESS"
    elif target == "source":
        snapshot["metrics"][metric_id]["source"]["severity"] = "STRESS"
        snapshot["metrics"][metric_id]["provenance"][0]["severity"] = "STRESS"
        series[metric_id]["source"]["severity"] = "STRESS"
    elif target == "context":
        snapshot["metrics"][metric_id]["context"]["severity"] = "STRESS"
    elif target == "methodology":
        snapshot["metrics"][metric_id]["methodology"]["assessment"] = "STRESS"
    elif target == "fundamental":
        snapshot["metrics"][metric_id]["details"]["fundamental"][
            "assessment"
        ] = "STRESS"
    elif target == "series":
        series[metric_id]["severity"] = "STRESS"
    else:
        next(
            item for item in manifest["metrics"] if item["metric_id"] == metric_id
        )["severity"] = "STRESS"
    with pytest.raises(ContractValidationError, match=message):
        validate_publication(snapshot, manifest, series)


@pytest.mark.parametrize("availability", ["MANUAL_READY", "ACTIVE_FREE"])
def test_release_four_manual_changes_and_confidence_are_evidence_only(
    tmp_path, availability
):
    rows = [valid_row()] if availability == "ACTIVE_FREE" else []
    publication = build_valid_publication(tmp_path, rows=rows)
    snapshot = deepcopy(publication.snapshot)
    metric = snapshot["metrics"]["ai_upstream_orders_backlog"]
    metric["changes"]["one_observation"] = 99
    with pytest.raises(ContractValidationError, match="changes must remain null"):
        validate_snapshot(snapshot)

    snapshot = deepcopy(publication.snapshot)
    snapshot["metrics"]["ai_upstream_orders_backlog"]["context"][
        "confidence"
    ] = "HIGH"
    with pytest.raises(ContractValidationError, match="MANUAL_READY state|timestamps/state"):
        validate_snapshot(snapshot)


def test_release_four_publication_declares_exactly_five_p3_metrics(tmp_path):
    publication = build_valid_publication(tmp_path)
    snapshot = deepcopy(publication.snapshot)
    manifest = deepcopy(publication.manifest)
    series = deepcopy(publication.series_by_id)
    source_id = "take_or_pay_commitments"
    invented_id = "invented_p3_metric"
    invented_metric = deepcopy(snapshot["metrics"][source_id])
    invented_metric.update({"metric_id": invented_id, "label": invented_id})
    snapshot["metrics"][invented_id] = invented_metric
    snapshot["manual_ready_count"] += 1
    invented_manifest = next(
        deepcopy(metric)
        for metric in manifest["metrics"]
        if metric["metric_id"] == source_id
    )
    invented_manifest.update(
        {
            "metric_id": invented_id,
            "label": invented_id,
            "series_path": f"data/series/{invented_id}.json",
        }
    )
    manifest["metrics"].append(invented_manifest)
    invented_series = deepcopy(series[source_id])
    invented_series.update({"metric_id": invented_id, "label": invented_id})
    series[invented_id] = invented_series
    with pytest.raises(ContractValidationError, match="exactly the five canonical P3"):
        validate_publication(snapshot, manifest, series)


def test_release_four_contract_locks_cumulative_manual_company_evidence(tmp_path):
    alphabet = valid_row(
        company_id="alphabet",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/1652044/"
            "000165204426000321/goog-20260630.htm"
        ),
        filing_accession="0001652044-26-000321",
        filing_accepted_at="2026-08-11T20:00:00Z",
        as_of="2026-08-12",
        reviewed_at="2026-08-12T22:00:00Z",
    )
    publication = build_valid_publication(
        tmp_path,
        rows=[valid_row(), alphabet],
    )
    snapshot = deepcopy(publication.snapshot)
    series = deepcopy(publication.series_by_id)
    metric_id = "ai_upstream_orders_backlog"
    latest = series[metric_id]["observations"][-1]
    latest["records"] = [
        record for record in latest["records"] if record["company_id"] == "alphabet"
    ]
    latest.update(
        {
            "record_count": 1,
            "company_count": 1,
            "comparable_count": 1,
            "direction": "UP",
        }
    )
    detail = snapshot["metrics"][metric_id]["details"]["manual_evidence"]
    detail.update(
        {
            "records": deepcopy(latest["records"]),
            "record_count": 1,
            "company_count": 1,
            "comparable_count": 1,
            "direction": "UP",
        }
    )
    snapshot["metrics"][metric_id]["statistics"] = {
        "record_count": 1,
        "company_count": 1,
        "comparable_count": 1,
    }
    snapshot["metrics"][metric_id]["quality"]["sample_size"] = 1
    series[metric_id]["quality"] = deepcopy(snapshot["metrics"][metric_id]["quality"])
    with pytest.raises(ContractValidationError, match="cumulative latest evidence"):
        validate_publication(snapshot, publication.manifest, series)
