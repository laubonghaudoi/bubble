from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json
import hashlib
import os
from pathlib import Path

import pytest

from pipeline.collectors.common import CollectorError
from pipeline.collectors.sec_form4 import FilingIndexEntry, ParsedTransaction, parse_complete_submission
from pipeline.form4_ledger import (
    build_ledger_package,
    canonical_sha256,
    load_ledger,
    merge_last_good_entries,
    prune_entries,
    public_ledger_entry,
    resolve_amendments,
    validate_public_entry,
    write_ledger_atomic,
)
from pipeline.transforms.p2_form4 import form4_metric_observation, form4_statistics


FIXTURES = Path(__file__).parent / "fixtures"
HASH_A = "a" * 64
HASH_B = "b" * 64


def parsed_fixture():
    return parse_complete_submission(
        (FIXTURES / "sec_form4_complete.txt").read_bytes(),
        entry=FilingIndexEntry(
            accession="0000320193-26-000001",
            cik="320193",
            form_type="4",
            filing_date="2026-08-11",
            index_date="2026-08-11",
            archive_path="edgar/data/320193/0000320193-26-000001.txt",
        ),
    )


def public_entry(
    day: str,
    *,
    accession_suffix: int = 1,
    issuer: str = "320193",
    form_type: str = "4",
    original_submission_date: str | None = None,
    purchases: int = 1,
    sales: int = 1,
    priced: int | None = None,
    purchase_dollars: str = "10",
    sale_dollars: str = "10",
    filing_flag: str = "FALSE",
) -> dict:
    eligible = purchases + sales
    priced_value = eligible if priced is None else priced

    def bucket(p: int, s: int, priced_count: int, pd: str, sd: str) -> dict:
        return {
            "eligible_transaction_count": p + s,
            "priced_transaction_count": priced_count,
            "purchase_count": p,
            "purchase_dollars": pd,
            "purchase_priced_count": min(p, priced_count),
            "purchase_shares": str(p),
            "sale_count": s,
            "sale_dollars": sd,
            "sale_priced_count": max(0, priced_count - min(p, priced_count)),
            "sale_shares": str(s),
        }

    accession = f"0000320193-26-{accession_suffix:06d}"
    fingerprint_count = purchases + sales
    fingerprints = [
        hashlib.sha256(
            f"{issuer}|{day}|{index}|{purchases}|{sales}".encode()
        ).hexdigest()
        for index in range(fingerprint_count)
    ]
    fingerprints.sort()
    transactions_hash = hashlib.sha256(
        "\n".join(fingerprints).encode("ascii")
    ).hexdigest()
    owner_hash = hashlib.sha256(b"1000001").hexdigest()
    all_bucket = bucket(
        purchases,
        sales,
        priced_value,
        purchase_dollars,
        sale_dollars,
    )
    empty = bucket(0, 0, 0, "0", "0")
    buckets = {
        "ALL": all_bucket,
        "FALSE": all_bucket if filing_flag == "FALSE" else empty,
        "TRUE": all_bucket if filing_flag == "TRUE" else empty,
        "UNKNOWN": all_bucket if filing_flag == "UNKNOWN" else empty,
    }
    actual_flags = [
        name for name in ("FALSE", "TRUE", "UNKNOWN") if buckets[name]["eligible_transaction_count"]
    ]
    return {
        "accession": accession,
        "acceptance_at": f"{day}T22:00:00Z",
        "amendment_status": "PENDING_RESOLUTION",
        "anomaly_codes": [],
        "excluded_transaction_count": 0,
        "filing_date": day,
        "filing_10b5_status": filing_flag,
        "form_type": form_type,
        "index_date": day,
        "issuer_cik": issuer,
        "linked_original_accession": None,
        "missing_price_count": eligible - priced_value,
        "original_submission_date": original_submission_date,
        "ownership_document_sha256": HASH_B,
        "parse_status": "PARSED",
        "period_of_report": day,
        "owner_cik_set_hash": owner_hash,
        "eligible_transaction_fingerprints": fingerprints,
        "eligible_transactions_hash": transactions_hash,
        "submission_sha256": HASH_A,
        "tenb5_flags_present": actual_flags,
        "totals": buckets,
    }


def completed_days(count: int = 20) -> list[str]:
    start = date(2026, 7, 20)
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def package_for(entries: list[dict], days: list[str] | None = None, **extra):
    resolved = resolve_amendments(entries)
    return {
        "entries": resolved,
        "completed_index_days": days if days is not None else completed_days(),
        "failures": extra.get("failures", []),
        "reviews": extra.get("reviews", []),
    }


def test_public_entry_is_accession_aggregate_without_owner_identity_or_raw_text():
    record = public_ledger_entry(parsed_fixture())
    serialized = json.dumps(record).lower()
    assert "fixture person" not in serialized
    assert "signature" not in serialized
    assert "reportingowner" not in serialized
    assert "<ownershipdocument" not in serialized
    assert record["totals"]["ALL"]["purchase_count"] == 2
    assert record["totals"]["ALL"]["sale_count"] == 1
    assert record["totals"]["ALL"]["priced_transaction_count"] == 2
    assert record["totals"]["FALSE"]["purchase_dollars"] == "20"
    assert "owner_cik_set_hash" in record
    assert "1000001" not in serialized


def test_privacy_allowlist_rejects_identity_and_raw_fields():
    record = public_entry("2026-08-01")
    record["owner_name"] = "not allowed"
    with pytest.raises(CollectorError, match="key mismatch"):
        validate_public_entry(record, allow_pending=True)
    record = public_entry("2026-08-01")
    record["anomaly_codes"] = ["<ownershipDocument>raw"]
    with pytest.raises(CollectorError, match="raw filing text"):
        validate_public_entry(record, allow_pending=True)


def test_unique_amendment_link_supersedes_original_but_unlinked_goes_to_review():
    original = public_entry("2026-08-01", accession_suffix=1)
    amendment = public_entry(
        "2026-08-02",
        accession_suffix=2,
        form_type="4/A",
        original_submission_date="2026-08-01",
    )
    amendment["period_of_report"] = original["period_of_report"]
    amendment["owner_cik_set_hash"] = original["owner_cik_set_hash"]
    amendment["eligible_transaction_fingerprints"] = original[
        "eligible_transaction_fingerprints"
    ]
    amendment["eligible_transactions_hash"] = original["eligible_transactions_hash"]
    resolved = resolve_amendments([original, amendment])
    statuses = {row["accession"]: row["amendment_status"] for row in resolved}
    assert statuses[original["accession"]] == "ORIGINAL_SUPERSEDED"
    assert statuses[amendment["accession"]] == "AMENDMENT_EFFECTIVE"
    assert resolved[-1]["linked_original_accession"] == original["accession"]

    ambiguous = public_entry("2026-08-01", accession_suffix=3)
    unresolved = resolve_amendments([original, ambiguous, amendment])
    amendment_result = next(row for row in unresolved if row["form_type"] == "4/A")
    assert amendment_result["amendment_status"] == "UNLINKED_REVIEW"
    assert amendment_result["linked_original_accession"] is None


def test_latest_of_multiple_uniquely_linked_amendments_is_effective():
    original = public_entry("2026-08-01", accession_suffix=1)
    amendments = []
    for suffix, index_day, accepted in [
        (2, "2026-08-02", "2026-08-02T20:00:00Z"),
        (3, "2026-08-03", "2026-08-03T20:00:00Z"),
    ]:
        row = public_entry(
            index_day,
            accession_suffix=suffix,
            form_type="4/A",
            original_submission_date="2026-08-01",
        )
        row["period_of_report"] = original["period_of_report"]
        row["owner_cik_set_hash"] = original["owner_cik_set_hash"]
        row["eligible_transaction_fingerprints"] = original[
            "eligible_transaction_fingerprints"
        ]
        row["eligible_transactions_hash"] = original["eligible_transactions_hash"]
        row["acceptance_at"] = accepted
        amendments.append(row)
    resolved = resolve_amendments([original, *amendments])
    assert [row["amendment_status"] for row in resolved if row["form_type"] == "4/A"] == [
        "AMENDMENT_SUPERSEDED",
        "AMENDMENT_EFFECTIVE",
    ]


def test_prune_is_exactly_45_calendar_days_inclusive():
    as_of = date(2026, 8, 12)
    cutoff = as_of - timedelta(days=44)
    too_old = cutoff - timedelta(days=1)
    rows = resolve_amendments(
        [
            public_entry(too_old.isoformat(), accession_suffix=1),
            public_entry(cutoff.isoformat(), accession_suffix=2),
            public_entry(as_of.isoformat(), accession_suffix=3),
        ]
    )
    assert [row["index_date"] for row in prune_entries(rows, as_of=as_of)] == [
        cutoff.isoformat(),
        as_of.isoformat(),
    ]


def test_last_good_merge_replaces_complete_day_and_preserves_incomplete_day():
    prior_a = public_entry("2026-08-01", accession_suffix=1)
    prior_b = public_entry("2026-08-02", accession_suffix=2)
    current = public_entry("2026-08-02", accession_suffix=3)
    merged = merge_last_good_entries(
        resolve_amendments([prior_a, prior_b]),
        resolve_amendments([current]),
        completed_index_days=["2026-08-02"],
        as_of=date(2026, 8, 12),
    )
    assert {row["accession"] for row in merged} == {
        prior_a["accession"],
        current["accession"],
    }


def test_last_good_merge_uses_completed_master_membership_for_unchanged_and_deleted():
    keep = public_entry("2026-08-02", accession_suffix=1)
    deleted = public_entry("2026-08-02", accession_suffix=2)
    merged = merge_last_good_entries(
        resolve_amendments([keep, deleted]),
        [],
        completed_index_days=["2026-08-02"],
        master_accessions_by_day={"2026-08-02": [keep["accession"]]},
        as_of=date(2026, 8, 12),
    )
    assert [row["accession"] for row in merged] == [keep["accession"]]


def test_atomic_ledger_roundtrip_is_deterministic_and_hash_verified(tmp_path):
    rows = resolve_amendments(
        [
            public_entry("2026-08-01", accession_suffix=1),
            public_entry("2026-08-02", accession_suffix=2),
        ]
    )
    package = build_ledger_package(
        rows,
        completed_index_days=["2026-08-01", "2026-08-02"],
        as_of=date(2026, 8, 12),
    )
    manifest_a = write_ledger_atomic(tmp_path / "ledger-a", package)
    manifest_b = write_ledger_atomic(tmp_path / "ledger-b", package)
    assert manifest_a["ledger_sha256"] == manifest_b["ledger_sha256"]
    assert manifest_a["shards"] == manifest_b["shards"]
    loaded = load_ledger(tmp_path / "ledger-a")
    assert loaded["entries"] == package["entries"]

    shard = next((tmp_path / "ledger-a" / "shards").iterdir())
    shard.write_text("{}")
    with pytest.raises(CollectorError, match="hash mismatch"):
        load_ledger(tmp_path / "ledger-a")


def test_ledger_loader_rejects_undeclared_files_directories_and_symlinks(tmp_path):
    package = build_ledger_package(
        resolve_amendments([public_entry("2026-08-01")]),
        completed_index_days=["2026-08-01"],
        as_of=date(2026, 8, 12),
    )
    for name, make_extra in (
        ("file", lambda root: (root / "raw-submission.txt").write_text("raw")),
        ("directory", lambda root: (root / "private-cache").mkdir()),
        (
            "symlink",
            lambda root: (root / "raw-link").symlink_to(root / "manifest.json"),
        ),
    ):
        root = tmp_path / name
        write_ledger_atomic(root, package)
        make_extra(root)
        with pytest.raises(CollectorError, match="undeclared|unexpected|symlink"):
            load_ledger(root)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "999", "schema_version"),
        ("retention_calendar_days", 999, "retention"),
        ("as_of", "not-a-date", "as_of"),
        ("completed_index_days", ["garbage"], "completed index"),
        ("completed_index_days", ["1900-01-01"], "out of range"),
    ],
)
def test_ledger_loader_validates_manifest_contract_even_with_valid_self_hash(
    tmp_path, field, value, message
):
    root = tmp_path / field
    package = build_ledger_package(
        resolve_amendments([public_entry("2026-08-01")]),
        completed_index_days=["2026-08-01"],
        as_of=date(2026, 8, 12),
    )
    write_ledger_atomic(root, package)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    unsigned = dict(manifest)
    unsigned.pop("ledger_sha256")
    manifest["ledger_sha256"] = canonical_sha256(unsigned)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    with pytest.raises(CollectorError, match=message):
        load_ledger(root)


def test_ledger_audit_rows_require_schema_and_share_45_day_retention():
    as_of = date(2026, 8, 12)
    cutoff = as_of - timedelta(days=44)
    package = build_ledger_package(
        [],
        completed_index_days=[],
        as_of=as_of,
        failures=[
            {
                "index_date": (cutoff - timedelta(days=1)).isoformat(),
                "stage": "SUBMISSION",
                "reason": "expired",
            },
            {
                "index_date": cutoff.isoformat(),
                "stage": "SUBMISSION",
                "reason": "retained",
            },
        ],
    )
    assert [row["reason"] for row in package["failures"]] == ["retained"]
    with pytest.raises(CollectorError, match="requires index_date"):
        build_ledger_package(
            [],
            completed_index_days=[],
            as_of=as_of,
            reviews=[{"stage": "TRANSACTION_QUARANTINE", "reason": "missing day"}],
        )


def test_atomic_ledger_promotion_rolls_back_existing_target_on_failure(tmp_path):
    target = tmp_path / "ledger"
    target.mkdir()
    (target / "sentinel.txt").write_text("last-good")
    package = build_ledger_package(
        resolve_amendments([public_entry("2026-08-01")]),
        completed_index_days=["2026-08-01"],
        as_of=date(2026, 8, 12),
    )

    def failing_replace(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path == target and "stage" in source_path.name:
            raise OSError("simulated promotion failure")
        os.replace(source, destination)

    with pytest.raises(OSError, match="simulated"):
        write_ledger_atomic(target, package, replace=failing_replace)
    assert (target / "sentinel.txt").read_text() == "last-good"


def test_count_ratio_and_locked_stats_use_last_5_and_20_completed_index_days():
    days = completed_days()
    rows = [
        public_entry(day, accession_suffix=index + 1, purchases=2, sales=1)
        for index, day in enumerate(days)
    ]
    observation = form4_metric_observation(package_for(rows, days))
    assert observation["metric_id"] == "sec_form4_nonderivative_ps_count_ratio_20d"
    assert observation["date"] == days[-1]
    # Count ratio is (P + 1) / (S + 1), not raw P/S and not "open market only".
    assert observation["value"] == pytest.approx(41 / 21)
    stats = observation["statistics"]
    assert stats["ratio_5d"] == pytest.approx(11 / 6)
    assert stats["purchase_count_20d"] == 40
    assert stats["sale_count_20d"] == 20
    assert stats["unique_accessions_20d"] == 20
    assert observation["technical_context"]["window_start_20d"] == days[0]
    assert observation["technical_context"]["ex_10b5_scope"] == "EXPLICIT_FALSE_ONLY"


def test_no_eligible_rows_or_incomplete_window_is_null_not_zero():
    days = completed_days()
    empty = public_entry(days[-1], purchases=0, sales=0, priced=0)
    stats, context = form4_statistics(package_for([empty], days))
    assert stats["count_ratio_20d"] is None
    assert stats["dollar_ratio_20d"] is None
    assert context["dollar_status_20d"] == "NO_ELIGIBLE_ROWS"
    stats, context = form4_statistics(package_for([empty], days[:19]))
    assert stats["count_ratio_20d"] is None
    assert context["dollar_status_20d"] == "INSUFFICIENT_COMPLETED_DAYS"


@pytest.mark.parametrize(
    "eligible,priced,expected_status,published",
    [
        (100, 80, "PUBLISHED", True),
        (1000, 799, "INSUFFICIENT_PRICE_COVERAGE", False),
    ],
)
def test_dollar_coverage_threshold_is_exactly_point_80(
    eligible, priced, expected_status, published
):
    days = completed_days()
    row = public_entry(
        days[-1],
        purchases=eligible // 2,
        sales=eligible - eligible // 2,
        priced=priced,
        purchase_dollars="200",
        sale_dollars="100",
    )
    stats, context = form4_statistics(package_for([row], days))
    assert stats["dollar_coverage_rate_20d"] == pytest.approx(priced / eligible)
    assert context["dollar_status_20d"] == expected_status
    assert (stats["dollar_ratio_20d"] is not None) is published


def test_zero_priced_sales_denominator_keeps_dollar_ratio_null():
    days = completed_days()
    row = public_entry(
        days[-1],
        purchases=2,
        sales=1,
        priced=3,
        purchase_dollars="100",
        sale_dollars="0",
    )
    stats, context = form4_statistics(package_for([row], days))
    assert stats["dollar_coverage_rate_20d"] == 1
    assert stats["dollar_ratio_20d"] is None
    assert context["dollar_status_20d"] == "NO_SALES_DOLLAR_DENOMINATOR"


def test_ex_10b5_sensitivity_includes_explicit_false_only_and_discloses_coverage():
    days = completed_days()
    false_row = public_entry(
        days[-1],
        accession_suffix=1,
        purchases=2,
        sales=1,
        filing_flag="FALSE",
    )
    true_row = public_entry(
        days[-1],
        accession_suffix=2,
        purchases=2,
        sales=2,
        filing_flag="TRUE",
    )
    unknown_row = public_entry(
        days[-1],
        accession_suffix=3,
        purchases=1,
        sales=2,
        filing_flag="UNKNOWN",
    )
    # Explicit-false rows are 3/10; true/unknown rows stay in the main ratio but
    # are excluded from the named sensitivity.
    stats, _context = form4_statistics(
        package_for([false_row, true_row, unknown_row], days)
    )
    assert stats["count_ratio_20d"] == 1
    assert stats["ex_explicit_false_count_ratio_20d"] == 1.5
    assert stats["ex_explicit_false_coverage_20d"] == 0.3
    assert stats["tenb5_true_filings_20d"] == 1
    assert stats["tenb5_false_filings_20d"] == 1
    assert stats["tenb5_unknown_filings_20d"] == 1


def test_amendment_reviews_and_parse_failures_are_explicit_counts():
    days = completed_days()
    amendment = public_entry(
        days[-1],
        form_type="4/A",
        original_submission_date="2026-01-01",
    )
    failures = [
        {
            "index_date": days[-1],
            "stage": "SUBMISSION",
            "accession": "0000000000-26-000999",
            "reason": "fixture failure",
        }
    ]
    stats, _context = form4_statistics(package_for([amendment], days, failures=failures))
    assert stats["form4a_count_20d"] == 1
    assert stats["amendments_review_count_20d"] == 1
    assert stats["parse_failures_20d"] == 1
    assert stats["eligible_transaction_count_20d"] == 0
