import csv
import json
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from pipeline.check_p3_disclosures import (
    ISSUE_MARKER,
    ISSUE_TITLE,
    REQUIRED_SEC_USER_AGENT,
    Company,
    DisclosureCheckError,
    Filing,
    build_review_queue,
    collect_recent_filings,
    parse_sec_submissions,
    reconcile_manual_signals_with_sec_metadata,
    render_issue_body,
    run_check,
    upsert_review_issue,
    validate_manual_timestamps_not_future,
)
from pipeline.manual_signals import (
    MANUAL_SIGNAL_COLUMNS,
    ManualSignalValidationError,
    build_manual_metric_observations,
    build_manual_metric_states,
    load_manual_signals,
)
from pipeline.release import VALID_GROUPS, CollectorFunctions, build_release

FIXTURE_DIR = Path(__file__).parent / "fixtures"
WORKFLOW_PATH = Path(".github/workflows/check-p3-disclosures.yml")


def valid_row(**changes):
    row = {
        "company_id": "microsoft",
        "period_end": "2026-06-30",
        "metric_id": "ai_upstream_orders_backlog",
        "direction": "UP",
        "value": "12.5",
        "unit": "USD bn",
        "yoy_pct": "25",
        "comparable": "true",
        "source_type": "10-Q",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312526000123/msft-20260630.htm"
        ),
        "filing_accession": "0001193125-26-000123",
        "filing_accepted_at": "2026-07-30T20:01:02Z",
        "as_of": "2026-07-30",
        "reviewer": "reviewer@example.com",
        "reviewed_at": "2026-07-30T22:00:00Z",
        "paraphrase": "Reviewed demand disclosure increased from the comparable prior period.",
        "review_note": "Period, scope, unit, and source were checked against the filing.",
    }
    row.update(changes)
    return row


def write_csv(path, rows, header=MANUAL_SIGNAL_COLUMNS):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def test_header_only_template_is_valid_and_all_metrics_remain_manual_ready(tmp_path):
    path = tmp_path / "industry_signals.csv"
    write_csv(path, [])
    records = load_manual_signals(path)
    assert records == ()
    states = build_manual_metric_states(records)
    assert list(states) == [
        "ai_upstream_orders_backlog",
        "customer_prepayments_contract_commitments",
        "take_or_pay_commitments",
    ]
    assert all(state["availability"] == "MANUAL_READY" for state in states.values())
    assert all(state["network_enabled"] is False for state in states.values())
    assert all(state["observations"] == [] for state in states.values())
    assert all(
        state["details"]["manual_evidence"]["records"] == []
        for state in states.values()
    )


def test_version_controlled_manual_file_obeys_contract_without_requiring_it_empty():
    records = load_manual_signals("data/manual/industry_signals.csv")
    states = build_manual_metric_states(records)
    assert all(state["network_enabled"] is False for state in states.values())
    assert all(
        state["availability"] in {"MANUAL_READY", "ACTIVE_FREE"}
        for state in states.values()
    )


def test_reviewed_rows_preserve_null_and_true_zero_and_activate_only_their_metrics(
    tmp_path,
):
    path = tmp_path / "industry_signals.csv"
    write_csv(
        path,
        [
            valid_row(value="0", unit="count", yoy_pct="0"),
            valid_row(
                metric_id="customer_prepayments_contract_commitments",
                direction="UNKNOWN",
                value="",
                unit="",
                yoy_pct="",
                comparable="false",
            ),
        ],
    )
    records = load_manual_signals(path)
    assert len(records) == 2
    assert records[0].value == 0
    assert records[0].yoy_pct == 0
    assert records[0].filing_accepted_at == "2026-07-30T20:01:02.000000Z"
    assert records[0].reviewed_at == "2026-07-30T22:00:00.000000Z"
    assert records[1].value is None
    assert records[1].unit is None

    states = build_manual_metric_states(records)
    assert states["ai_upstream_orders_backlog"]["availability"] == "ACTIVE_FREE"
    assert states["customer_prepayments_contract_commitments"]["availability"] == (
        "ACTIVE_FREE"
    )
    assert states["take_or_pay_commitments"]["availability"] == "MANUAL_READY"
    assert states["ai_upstream_orders_backlog"]["network_enabled"] is False


def test_publication_observation_keeps_same_date_company_evidence_without_overwrite(
    tmp_path,
):
    path = tmp_path / "industry_signals.csv"
    old_microsoft = valid_row(
        value="7",
        filing_accession="0001193125-26-000122",
        filing_accepted_at="2026-07-29T20:01:02Z",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312526000122/msft-20260630.htm"
        ),
        reviewed_at="2026-07-30T21:00:00Z",
    )
    latest_microsoft = valid_row(value="0", unit="count", yoy_pct="0")
    alphabet = valid_row(
        company_id="alphabet",
        direction="DOWN",
        value="",
        unit="",
        yoy_pct="",
        filing_accession="0001652044-26-000321",
        filing_accepted_at="2026-07-30T21:01:02Z",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/1652044/"
            "000165204426000321/goog-20260630.htm"
        ),
        reviewed_at="2026-07-30T23:00:00Z",
    )
    write_csv(path, [old_microsoft, latest_microsoft, alphabet])
    records = load_manual_signals(path)

    observations = build_manual_metric_observations(
        records, "ai_upstream_orders_backlog"
    )
    assert len(observations) == 1
    point = observations[0]
    assert point["date"] == "2026-07-30"
    assert point["value"] is None
    assert point["direction"] == "MIXED"
    assert point["record_count"] == 2
    assert point["company_count"] == 2
    assert point["comparable_count"] == 2
    assert [record["company_id"] for record in point["records"]] == [
        "alphabet",
        "microsoft",
    ]
    microsoft = next(
        record for record in point["records"] if record["company_id"] == "microsoft"
    )
    assert microsoft["filing_accession"] == "0001193125-26-000123"
    assert microsoft["value"] == 0
    assert tuple(microsoft) == MANUAL_SIGNAL_COLUMNS

    state = build_manual_metric_states(records)["ai_upstream_orders_backlog"]
    assert state["availability"] == "ACTIVE_FREE"
    assert state["direction"] == "MIXED"
    assert state["observation_date"] == "2026-07-30"
    assert state["latest_filing_accepted_at"] == "2026-07-30T21:01:02.000000Z"
    assert state["latest_reviewed_at"] == "2026-07-30T23:00:00.000000Z"
    assert state["released_at"] == state["latest_filing_accepted_at"]
    assert state["updated_at"] == state["latest_reviewed_at"]
    evidence = state["details"]["manual_evidence"]
    assert evidence["direction"] == "MIXED"
    assert evidence["records"] == point["records"]
    assert all(tuple(record) == MANUAL_SIGNAL_COLUMNS for record in evidence["records"])


def test_publication_direction_is_unknown_if_comparable_evidence_is_unknown(tmp_path):
    path = tmp_path / "industry_signals.csv"
    write_csv(path, [valid_row(direction="UNKNOWN", value="", unit="", yoy_pct="")])
    point = build_manual_metric_observations(
        load_manual_signals(path), "ai_upstream_orders_backlog"
    )[0]
    assert point["direction"] == "UNKNOWN"
    with pytest.raises(ManualSignalValidationError, match="canonical P3 manual metric"):
        build_manual_metric_observations((), "old_manual_id")


def test_each_publication_point_carries_latest_company_records_through_staggered_dates(
    tmp_path,
):
    path = tmp_path / "industry_signals.csv"
    meta = valid_row(
        company_id="meta",
        as_of="2026-08-01",
        filing_accession="0001628280-26-000777",
        filing_accepted_at="2026-08-01T12:00:00Z",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/1326801/"
            "000162828026000777/meta-20260630.htm"
        ),
        reviewed_at="2026-08-01T14:00:00Z",
    )
    write_csv(path, [valid_row(), meta])
    observations = build_manual_metric_observations(
        load_manual_signals(path), "ai_upstream_orders_backlog"
    )
    assert [point["date"] for point in observations] == ["2026-07-30", "2026-08-01"]
    assert [point["company_count"] for point in observations] == [1, 2]
    assert all(
        record["as_of"] <= point["date"]
        for point in observations
        for record in point["records"]
    )
    assert [record["company_id"] for record in observations[-1]["records"]] == [
        "meta",
        "microsoft",
    ]


def test_staggered_publication_drops_carried_company_evidence_older_than_120_days(
    tmp_path,
):
    path = tmp_path / "industry_signals.csv"
    old_microsoft = valid_row(
        period_end="2024-12-31",
        as_of="2025-01-30",
        filing_accession="0001193125-25-000122",
        filing_accepted_at="2025-01-30T20:01:02Z",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312525000122/msft-20241231.htm"
        ),
        reviewed_at="2025-01-30T22:00:00Z",
    )
    fresh_meta = valid_row(
        company_id="meta",
        as_of="2026-08-01",
        filing_accession="0001628280-26-000777",
        filing_accepted_at="2026-08-01T12:00:00Z",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/1326801/"
            "000162828026000777/meta-20260630.htm"
        ),
        reviewed_at="2026-08-01T14:00:00Z",
    )
    write_csv(path, [old_microsoft, fresh_meta])
    latest = build_manual_metric_observations(
        load_manual_signals(path), "ai_upstream_orders_backlog"
    )[-1]
    assert latest["company_count"] == 1
    assert latest["record_count"] == 1
    assert latest["records"][0]["company_id"] == "meta"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"company_id": "MSFT"}, "canonical P3 company"),
        ({"metric_id": "upstream_backlog"}, "canonical P3 manual metric"),
        ({"direction": "RISING"}, "UP, FLAT, DOWN, or UNKNOWN"),
        ({"value": "1e6"}, "plain finite decimal"),
        ({"value": "-1"}, "non-negative"),
        ({"value": "", "unit": "USD bn"}, "empty when value is null"),
        ({"unit": "usd billions"}, "exact allowlisted unit"),
        ({"comparable": "TRUE"}, "exactly true or false"),
        ({"comparable": "false", "yoy_pct": "1"}, "null when comparable is false"),
        ({"source_type": "NEWS"}, "allowed SEC filing type"),
        ({"source_url": "http://www.sec.gov/file"}, "public HTTPS URL"),
        ({"source_url": "https://example.com/file"}, "allowlisted official source"),
        (
            {"source_url": "https://www.sec.gov/Archives/edgar/data/789019/other.htm"},
            "direct SEC filing document matching accession and issuer CIK",
        ),
        (
            {
                "source_url": (
                    "https://www.sec.gov/Archives/edgar/data/789019/"
                    "000119312526000123/../evil.htm"
                )
            },
            "direct SEC filing document matching accession and issuer CIK",
        ),
        (
            {
                "source_url": (
                    "https://www.sec.gov/Archives/edgar/data/789019/"
                    "000119312526000123/%2e%2e/evil.htm"
                )
            },
            "direct SEC filing document matching accession and issuer CIK",
        ),
        ({"filing_accession": "789019-26-1"}, "10-2-6 dashed"),
        (
            {
                "company_id": "alphabet",
                "filing_accession": "0001193125-26-000123",
                "source_url": (
                    "https://www.sec.gov/Archives/edgar/data/789019/"
                    "000119312526000123/goog-20260630.htm"
                ),
            },
            "direct SEC filing document matching accession and issuer CIK",
        ),
        ({"filing_accepted_at": "2026-07-30T20:01:02-04:00"}, "ending in Z"),
        ({"reviewed_at": "2026-07-29T22:00:00Z"}, "chronology"),
        ({"reviewer": ""}, "reviewer: is required"),
        ({"paraphrase": "x" * 281}, "at most 280"),
        ({"review_note": "x" * 501}, "at most 500"),
        ({"review_note": " leading"}, "whitespace"),
    ],
)
def test_manual_contract_fails_closed_on_unsafe_or_ambiguous_rows(
    tmp_path, changes, message
):
    path = tmp_path / "industry_signals.csv"
    write_csv(path, [valid_row(**changes)])
    with pytest.raises(ManualSignalValidationError, match=message):
        load_manual_signals(path)


def test_header_shape_blank_rows_and_duplicate_identity_are_rejected(tmp_path):
    wrong_header = tmp_path / "wrong.csv"
    write_csv(wrong_header, [], header=MANUAL_SIGNAL_COLUMNS[:-1])
    with pytest.raises(ManualSignalValidationError, match="header must exactly equal"):
        load_manual_signals(wrong_header)

    blank = tmp_path / "blank.csv"
    blank.write_text(",".join(MANUAL_SIGNAL_COLUMNS) + "\n\n", encoding="utf-8")
    with pytest.raises(ManualSignalValidationError, match="blank rows"):
        load_manual_signals(blank)

    duplicate = tmp_path / "duplicate.csv"
    write_csv(duplicate, [valid_row(), valid_row(direction="DOWN")])
    with pytest.raises(ManualSignalValidationError, match="duplicates row 2"):
        load_manual_signals(duplicate)


def microsoft_company():
    return Company(
        company_id="microsoft",
        name="Microsoft Corporation",
        cik="0000789019",
    )


def microsoft_filing():
    return Filing(
        company_id="microsoft",
        form="10-Q",
        accession="0001193125-26-000123",
        filed_on="2026-07-30",
        report_date="2026-06-30",
        accepted_at="2026-07-30T20:01:02.000Z",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312526000123/msft-20260630.htm"
        ),
    )


def sec_payload(company):
    accession = f"{company.cik}-26-000123"
    return {
        "filings": {
            "recent": {
                "accessionNumber": [accession],
                "filingDate": ["2026-07-30"],
                "reportDate": ["2026-06-30"],
                "acceptanceDateTime": ["2026-07-30T20:01:02.000Z"],
                "form": ["10-Q"],
                "primaryDocument": ["filing.htm"],
            }
        }
    }


def test_sec_metadata_parser_filters_forms_and_never_downloads_filing_prose():
    fixture = json.loads((FIXTURE_DIR / "p3_sec_submissions.json").read_text())
    filings = parse_sec_submissions(microsoft_company(), fixture)
    assert len(filings) == 1
    assert filings[0].accession == "0001193125-26-000123"
    assert filings[0].accepted_at == "2026-07-30T20:01:02.000Z"
    assert filings[0].source_url.endswith("/000119312526000123/msft-20260630.htm")

    fixture["filings"]["recent"]["form"] = ["4", "4"]
    with pytest.raises(DisclosureCheckError, match="no eligible filing metadata"):
        parse_sec_submissions(microsoft_company(), fixture)

    proxy = sec_payload(microsoft_company())
    proxy["filings"]["recent"]["form"] = ["DEF 14A"]
    assert parse_sec_submissions(microsoft_company(), proxy)[0].form == "DEF 14A"


def test_collector_uses_identified_agent_and_four_requests_per_second_maximum():
    companies = (
        microsoft_company(),
        Company("alphabet", "Alphabet Inc.", "0001652044"),
        Company("amazon", "Amazon.com, Inc.", "0001018724"),
        Company("meta", "Meta Platforms, Inc.", "0001326801"),
    )
    calls, sleeps = [], []

    def fetch(url, headers):
        company = companies[len(calls)]
        calls.append((url, headers))
        return sec_payload(company)

    filings = collect_recent_filings(
        companies,
        fetch_json=fetch,
        sec_user_agent=REQUIRED_SEC_USER_AGENT,
        sleep=sleeps.append,
    )
    assert set(filings) == {company.company_id for company in companies}
    assert len(calls) == 4
    assert sleeps == [0.25, 0.25, 0.25]
    assert all(call[1]["User-Agent"] == REQUIRED_SEC_USER_AGENT for call in calls)
    with pytest.raises(DisclosureCheckError, match="2-5 requests/second"):
        collect_recent_filings(
            companies,
            fetch_json=fetch,
            sec_user_agent=REQUIRED_SEC_USER_AGENT,
            sleep=sleeps.append,
            request_interval_seconds=0.1,
        )
    with pytest.raises(DisclosureCheckError, match="reviewed dashboard contact"):
        collect_recent_filings(
            companies,
            fetch_json=fetch,
            sec_user_agent="Bubble Dashboard reviewer@example.com",
            sleep=sleeps.append,
        )


def test_empty_manual_file_creates_review_tasks_but_no_guessed_values():
    filing = microsoft_filing()
    tasks = build_review_queue(
        (),
        (microsoft_company(),),
        {"microsoft": (filing,)},
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert len(tasks) == 3
    assert all(task.reasons == ("NO_REVIEWED_ROW", "NEW_FILING") for task in tasks)
    body = render_issue_body(tasks, {"microsoft": (filing,)})
    assert ISSUE_MARKER in body
    assert "does **not** extract or guess disclosure values" in body
    assert "0001193125-26-000123" in body
    assert "12.5" not in body
    assert "update `data/manual/industry_signals.csv` in a pull request" in body


def test_review_queue_detects_new_filings_and_overdue_review(tmp_path):
    path = tmp_path / "industry_signals.csv"
    write_csv(
        path,
        [
            valid_row(
                filing_accepted_at="2026-07-01T20:01:02Z",
                reviewed_at="2027-01-01T00:00:00Z",
            )
        ],
    )
    records = load_manual_signals(path)
    newer_filing = replace(
        microsoft_filing(),
        accession="0001193125-26-000124",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312526000124/msft-20260630.htm"
        ),
    )
    tasks = build_review_queue(
        records,
        (microsoft_company(),),
        {"microsoft": (newer_filing,)},
        now=datetime(2027, 1, 1, tzinfo=timezone.utc),
        overdue_days=120,
        filing_lookback_days=365,
    )
    selected = next(
        task for task in tasks if task.metric_id == "ai_upstream_orders_backlog"
    )
    assert selected.reasons == ("REVIEW_OVERDUE", "NEW_FILING")

    with pytest.raises(DisclosureCheckError, match="metadata is missing"):
        build_review_queue(
            records,
            (microsoft_company(),),
            {},
            now=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )


def test_review_queue_never_hides_unreviewed_filing_overflow(tmp_path):
    filings = tuple(
        replace(
            microsoft_filing(),
            accession=f"0001193125-26-{index:06d}",
            filed_on=f"2026-07-{index:02d}",
            accepted_at=f"2026-07-{index:02d}T20:01:02.000Z",
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/789019/"
                f"000119312526{index:06d}/filing.htm"
            ),
        )
        for index in range(1, 11)
    )
    empty_tasks = build_review_queue(
        (),
        (microsoft_company(),),
        {"microsoft": filings},
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    first = next(
        task for task in empty_tasks if task.metric_id == "ai_upstream_orders_backlog"
    )
    assert first.candidate_accessions == tuple(
        f"0001193125-26-{index:06d}" for index in range(1, 11)
    )

    path = tmp_path / "industry_signals.csv"
    write_csv(
        path,
        [
            valid_row(
                filing_accession="0001193125-26-000010",
                filing_accepted_at="2026-07-10T20:01:02Z",
                as_of="2026-07-10",
                source_url=(
                    "https://www.sec.gov/Archives/edgar/data/789019/"
                    "000119312526000010/filing.htm"
                ),
                reviewed_at="2026-07-10T22:00:00Z",
            )
        ],
    )
    tasks = build_review_queue(
        load_manual_signals(path),
        (microsoft_company(),),
        {"microsoft": filings},
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    reviewed_latest = next(
        task for task in tasks if task.metric_id == "ai_upstream_orders_backlog"
    )
    assert reviewed_latest.candidate_accessions == tuple(
        f"0001193125-26-{index:06d}" for index in range(1, 10)
    )


def test_review_queue_latest_evidence_orders_by_as_of_not_late_review_time(tmp_path):
    path = tmp_path / "industry_signals.csv"
    older = valid_row(
        period_end="2024-12-31",
        filing_accession="0001193125-25-000111",
        filing_accepted_at="2025-01-30T20:01:02Z",
        as_of="2025-01-30",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312525000111/filing.htm"
        ),
        reviewed_at="2026-08-01T22:00:00Z",
    )
    write_csv(path, [valid_row(), older])
    records = load_manual_signals(path)
    reviewed_filings = (
        microsoft_filing(),
        replace(
            microsoft_filing(),
            accession="0001193125-25-000111",
            filed_on="2025-01-30",
            report_date="2024-12-31",
            accepted_at="2025-01-30T20:01:02.000Z",
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/789019/"
                "000119312525000111/filing.htm"
            ),
        ),
    )
    tasks = build_review_queue(
        records,
        (microsoft_company(),),
        {"microsoft": reviewed_filings},
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert not any(task.metric_id == "ai_upstream_orders_backlog" for task in tasks)


def test_run_check_validates_csv_before_any_network_request(tmp_path):
    invalid = tmp_path / "invalid.csv"
    invalid.write_text("wrong,header\n", encoding="utf-8")
    calls = []
    with pytest.raises(ManualSignalValidationError):
        run_check(
            csv_path=invalid,
            companies_path="config/companies.yml",
            now=datetime(2026, 8, 12, tzinfo=timezone.utc),
            sec_user_agent=REQUIRED_SEC_USER_AGENT,
            fetch_json=lambda *args: calls.append(args),
        )
    assert calls == []

    future = tmp_path / "future.csv"
    write_csv(
        future,
        [
            valid_row(
                period_end="2027-06-30",
                filing_accepted_at="2027-07-30T20:01:02Z",
                as_of="2027-07-30",
                reviewed_at="2027-07-30T22:00:00Z",
            )
        ],
    )
    with pytest.raises(DisclosureCheckError, match="must not be future-dated"):
        run_check(
            csv_path=future,
            companies_path="config/companies.yml",
            now=datetime(2026, 8, 12, tzinfo=timezone.utc),
            sec_user_agent=REQUIRED_SEC_USER_AGENT,
            fetch_json=lambda *args: calls.append(args),
        )
    assert calls == []


def test_every_release_group_rejects_invalid_manual_contract_before_collectors(
    tmp_path,
):
    invalid = tmp_path / "invalid-release.csv"
    invalid.write_text("wrong,header\n", encoding="utf-8")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("collector ran before manual validation")

    collectors = CollectorFunctions(
        **{field.name: forbidden for field in fields(CollectorFunctions)}
    )
    for group in sorted(VALID_GROUPS):
        with pytest.raises(ManualSignalValidationError):
            build_release(
                group=group,
                data_dir=tmp_path / group,
                now=datetime(2026, 8, 12, tzinfo=timezone.utc),
                collectors=collectors,
                manual_signals_path=invalid,
            )
    assert calls == []


def test_reviewed_rows_reconcile_form_and_acceptance_against_sec_metadata(tmp_path):
    path = tmp_path / "industry_signals.csv"
    write_csv(path, [valid_row()])
    records = load_manual_signals(path)
    filing = microsoft_filing()
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    validate_manual_timestamps_not_future(records, now=now)
    reconcile_manual_signals_with_sec_metadata(
        records, {"microsoft": (filing,)}, now=now
    )

    with pytest.raises(DisclosureCheckError, match="source_type does not match"):
        reconcile_manual_signals_with_sec_metadata(
            records,
            {"microsoft": (replace(filing, form="8-K"),)},
            now=now,
        )
    with pytest.raises(DisclosureCheckError, match="accepted timestamp does not match"):
        reconcile_manual_signals_with_sec_metadata(
            records,
            {"microsoft": (replace(filing, accepted_at="2026-07-30T20:01:03.000Z"),)},
            now=now,
        )
    with pytest.raises(DisclosureCheckError, match="source_url does not match"):
        reconcile_manual_signals_with_sec_metadata(
            records,
            {
                "microsoft": (
                    replace(
                        filing,
                        source_url=(
                            "https://www.sec.gov/Archives/edgar/data/789019/"
                            "000119312526000123/bogus.htm"
                        ),
                    ),
                )
            },
            now=now,
        )
    with pytest.raises(DisclosureCheckError, match="absent from SEC metadata"):
        reconcile_manual_signals_with_sec_metadata(
            records,
            {"microsoft": (replace(filing, accession="0001193125-26-999999"),)},
            now=now,
        )


def test_issue_upsert_creates_updates_noops_and_refuses_duplicates():
    body = f"{ISSUE_MARKER}\nqueue"
    calls = []

    def create_request(method, path, payload):
        calls.append((method, path, payload))
        return [] if method == "GET" else {"number": 7}

    assert (
        upsert_review_issue(
            repository="owner/repo", body=body, has_tasks=True, request=create_request
        )
        == "created"
    )
    assert calls[-1] == (
        "POST",
        "/repos/owner/repo/issues",
        {"title": ISSUE_TITLE, "body": body},
    )

    existing = {
        "number": 7,
        "state": "open",
        "title": ISSUE_TITLE,
        "body": body,
        "user": {"login": "github-actions[bot]"},
    }

    def noop_request(method, path, payload):
        calls.append((method, path, payload))
        return [existing]

    before = len(calls)
    assert (
        upsert_review_issue(
            repository="owner/repo", body=body, has_tasks=True, request=noop_request
        )
        == "noop"
    )
    assert len(calls) == before + 1

    closed = {**existing, "state": "closed", "body": f"{ISSUE_MARKER}\nold body"}

    def reopen_request(method, path, payload):
        calls.append((method, path, payload))
        return [closed] if method == "GET" else {"number": 7}

    assert (
        upsert_review_issue(
            repository="owner/repo", body=body, has_tasks=True, request=reopen_request
        )
        == "reopened"
    )
    assert calls[-1] == (
        "PATCH",
        "/repos/owner/repo/issues/7",
        {"body": body, "state": "open"},
    )

    def duplicate_request(method, path, payload):
        return [existing, {**existing, "number": 8}]

    with pytest.raises(DisclosureCheckError, match="multiple marker-owned"):
        upsert_review_issue(
            repository="owner/repo",
            body=body,
            has_tasks=True,
            request=duplicate_request,
        )


def test_clean_queue_closes_existing_issue_and_does_not_create_an_empty_one():
    body = render_issue_body((), {})
    calls = []

    def no_existing(method, path, payload):
        calls.append((method, path, payload))
        return []

    assert (
        upsert_review_issue(
            repository="owner/repo", body=body, has_tasks=False, request=no_existing
        )
        == "noop"
    )
    assert len(calls) == 1

    existing = {
        "number": 9,
        "state": "open",
        "title": ISSUE_TITLE,
        "body": f"{ISSUE_MARKER}\nold",
        "user": {"login": "github-actions[bot]"},
    }

    def close_request(method, path, payload):
        calls.append((method, path, payload))
        return [existing] if method == "GET" else {"number": 9}

    assert (
        upsert_review_issue(
            repository="owner/repo", body=body, has_tasks=False, request=close_request
        )
        == "closed"
    )
    assert calls[-1] == (
        "PATCH",
        "/repos/owner/repo/issues/9",
        {"body": body, "state": "closed"},
    )


def test_issue_dedupe_paginates_and_ignores_spoofed_external_markers():
    body = f"{ISSUE_MARKER}\nqueue"
    bot_issue = {
        "number": 10,
        "state": "open",
        "title": ISSUE_TITLE,
        "body": body,
        "user": {"login": "github-actions[bot]"},
    }
    calls = []

    def paginated_request(method, path, payload):
        calls.append((method, path, payload))
        if path.endswith("&page=1"):
            return [
                {
                    "number": index,
                    "state": "open",
                    "title": "unrelated",
                    "body": "",
                    "user": {"login": "someone"},
                }
                for index in range(100)
            ]
        return [bot_issue]

    assert (
        upsert_review_issue(
            repository="owner/repo",
            body=body,
            has_tasks=True,
            request=paginated_request,
        )
        == "noop"
    )
    assert len(calls) == 2
    assert "page=2" in calls[-1][1]

    spoof = {**bot_issue, "number": 11, "user": {"login": "external-user"}}

    def spoof_request(method, path, payload):
        calls.append((method, path, payload))
        return [spoof] if method == "GET" else {"number": 12}

    assert (
        upsert_review_issue(
            repository="owner/repo",
            body=body,
            has_tasks=True,
            request=spoof_request,
        )
        == "created"
    )
    assert calls[-1][0] == "POST"


def test_dedicated_workflow_has_narrow_permissions_and_no_publish_path():
    workflow = yaml.load(WORKFLOW_PATH.read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    assert workflow["on"]["schedule"] == [{"cron": "30 14 * * 1-5"}]
    assert workflow["permissions"] == {"contents": "read", "issues": "write"}
    assert workflow["concurrency"] == {
        "group": "bubble-p3-manual-disclosure-review",
        "cancel-in-progress": "false",
    }
    assert list(workflow["jobs"]) == ["update-review-issue"]
    job = workflow["jobs"]["update-review-issue"]
    assert "env" not in job
    checker = next(
        step
        for step in job["steps"]
        if step.get("name") == "Validate reviewed CSV and update the deduplicated issue"
    )
    assert checker["env"] == {
        "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}",
        "SEC_USER_AGENT": "${{ vars.SEC_USER_AGENT }}",
    }
    assert all(
        "GITHUB_TOKEN" not in step.get("env", {})
        and "SEC_USER_AGENT" not in step.get("env", {})
        for step in job["steps"]
        if step is not checker
    )
    serialized = WORKFLOW_PATH.read_text()
    assert "python -m pipeline.check_p3_disclosures" in serialized
    assert "SEC_USER_AGENT: ${{ vars.SEC_USER_AGENT }}" in serialized
    assert "git push" not in serialized
    assert "public/data" not in serialized
    assert "deploy-pages" not in serialized
    assert "contents: write" not in serialized
