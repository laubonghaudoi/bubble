from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from email.message import Message
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any
import urllib.error

import pytest

from pipeline.collectors.common import CollectorError
from pipeline.collectors.sec_form4 import (
    FilingIndexEntry,
    PrivateResponseCache,
    SecHttpClient,
    SerializedTokenBucket,
    collect_form4_window,
    deduplicate_accessions,
    parse_complete_submission,
    parse_master_index,
    parse_quarter_index,
)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def index_entry(
    *,
    accession: str = "0000320193-26-000001",
    form_type: str = "4",
    filing_date: str = "2026-08-11",
    index_date: str = "2026-08-11",
    cik: str = "320193",
) -> FilingIndexEntry:
    return FilingIndexEntry(
        accession=accession,
        cik=cik,
        form_type=form_type,
        filing_date=filing_date,
        index_date=index_date,
        archive_path=f"edgar/data/{cik}/{accession}.txt",
    )


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        content_type: str,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def read(self, _size: int = -1) -> bytes:
        return self.body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class QueueOpener:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[Any] = []

    def __call__(self, request: Any, *, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def http_error(status: int, *, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://www.sec.gov/x", status, "error", headers, None)


def make_client(opener: QueueOpener, **kwargs: Any) -> SecHttpClient:
    return SecHttpClient(
        opener=opener,
        sleeper=kwargs.pop("sleeper", lambda _seconds: None),
        clock=kwargs.pop("clock", lambda: 1_000.0),
        now=kwargs.pop(
            "now", lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc)
        ),
        **kwargs,
    )


def test_quarter_index_discovers_only_exact_master_names_in_range():
    rows = parse_quarter_index(
        fixture_json("sec_quarter_index.json"),
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 12),
    )
    assert [day for day, _ in rows] == ["2026-08-11", "2026-08-12"]
    assert rows[0][1].endswith("/2026/QTR3/master.20260811.idx")


@pytest.mark.parametrize("payload", [{}, {"directory": {}}, {"directory": {"item": {}}}])
def test_quarter_index_schema_drift_fails_closed(payload):
    with pytest.raises(CollectorError, match="quarter index"):
        parse_quarter_index(
            payload,
            start_date=date(2026, 8, 11),
            end_date=date(2026, 8, 12),
        )


def test_master_index_keeps_exact_4_and_4a_and_deduplicates_accessions():
    rows = parse_master_index(
        fixture_bytes("sec_master_20260811.idx"), index_date="2026-08-11"
    )
    assert [(row.accession, row.form_type) for row in rows] == [
        ("0000320193-26-000001", "4"),
        ("0000789019-26-000002", "4/A"),
    ]
    assert rows[0].submission_url.endswith("/edgar/data/320193/0000320193-26-000001.txt")
    assert rows[0].filing_date == "2026-08-11"


def test_master_index_multi_entity_dedup_is_order_independent():
    issuer = index_entry()
    owner = FilingIndexEntry(
        accession=issuer.accession,
        cik="1000001",
        form_type=issuer.form_type,
        filing_date=issuer.filing_date,
        index_date=issuer.index_date,
        archive_path=f"edgar/data/1000001/{issuer.accession}.txt",
    )
    assert deduplicate_accessions([issuer, owner]) == [issuer]
    assert deduplicate_accessions([owner, issuer]) == [issuer]


def test_master_index_archive_directory_must_match_row_cik():
    body = fixture_bytes("sec_master_20260811.idx").replace(
        b"1000001|Example Reporting Owner|4|20260811|edgar/data/1000001/",
        b"1000001|Example Reporting Owner|4|20260811|edgar/data/320193/",
    )
    with pytest.raises(CollectorError, match="invalid archive path"):
        parse_master_index(body, index_date="2026-08-11")


@pytest.mark.parametrize(
    "header",
    [
        "CIK|Company Name|Form Type|Date Filed|Filename",
        "CIK|Company Name|Form Type|Date Filed|FileName",
        "CIK|Company Name|Date Filed|Form Type|File Name",
        "CIK|Company Name|Form Type|Date Filed|File Name|Extra",
    ],
)
def test_master_index_near_miss_header_schema_fails_closed(header):
    body = fixture_bytes("sec_master_20260811.idx").replace(
        b"CIK|Company Name|Form Type|Date Filed|File Name", header.encode()
    )
    with pytest.raises(CollectorError, match="header schema"):
        parse_master_index(body, index_date="2026-08-11")


@pytest.mark.parametrize("filing_date", ["2026-08-11", "2026081", "20261301"])
def test_master_index_nonofficial_or_invalid_filing_date_fails_closed(filing_date):
    body = fixture_bytes("sec_master_20260811.idx").replace(
        b"320193|Example Issuer One|4|20260811|",
        f"320193|Example Issuer One|4|{filing_date}|".encode(),
    )
    with pytest.raises(CollectorError, match="invalid filing date"):
        parse_master_index(body, index_date="2026-08-11")


def test_master_index_wrong_schema_html_and_conflicting_duplicate_fail_closed():
    with pytest.raises(CollectorError, match="header schema"):
        parse_master_index(b"not an index", index_date="2026-08-11")
    with pytest.raises(CollectorError, match="HTML"):
        parse_master_index(b"<html>blocked</html>", index_date="2026-08-11")
    first = index_entry()
    conflicting = FilingIndexEntry(
        **{**first.__dict__, "filing_date": "2026-08-10"}
    )
    with pytest.raises(CollectorError, match="conflicting duplicate"):
        deduplicate_accessions([first, conflicting])


def test_complete_submission_parses_only_table_i_p_and_s_with_required_mapping():
    filing = parse_complete_submission(
        fixture_bytes("sec_form4_complete.txt"), entry=index_entry()
    )
    assert filing.acceptance_at == "2026-08-12T01:55:01Z"
    assert filing.issuer_cik == "320193"
    assert [row.code for row in filing.transactions] == ["P", "S", "P"]
    assert [row.plan_10b5 for row in filing.transactions] == [
        "FALSE",
        "FALSE",
        "FALSE",
    ]
    assert filing.reporting_owner_ciks == ("1000001",)
    assert len(filing.eligible_transaction_fingerprints) == 3
    assert filing.transactions[0].dollar_value == 20
    assert filing.transactions[2].dollar_value is None
    assert filing.excluded_transaction_count == 1
    assert filing.missing_price_count == 1
    assert filing.parse_status == "PARSED"


def test_bad_p_s_mapping_is_quarantined_while_derivatives_and_other_codes_stay_excluded():
    body = fixture_bytes("sec_form4_complete.txt").replace(
        b"<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>",
        b"<transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>",
        1,
    )
    filing = parse_complete_submission(body, entry=index_entry())
    assert len(filing.transactions) == 2
    assert filing.parse_status == "PARSED_WITH_QUARANTINED_ROWS"
    assert filing.anomaly_codes == ("NONDERIVATIVE_ROW_1_QUARANTINED",)


def test_missing_or_duplicate_ownership_document_and_hash_change_fail_closed():
    body = fixture_bytes("sec_form4_complete.txt")
    without = body.replace(b"<ownershipDocument>", b"<otherDocument>").replace(
        b"</ownershipDocument>", b"</otherDocument>"
    )
    with pytest.raises(CollectorError, match="one ownershipDocument"):
        parse_complete_submission(without, entry=index_entry())
    document = body.split(b"<DOCUMENT>", 1)[1].split(b"</DOCUMENT>", 1)[0]
    duplicate = body.replace(b"</SEC-DOCUMENT>", b"<DOCUMENT>" + document + b"</DOCUMENT></SEC-DOCUMENT>")
    with pytest.raises(CollectorError, match="found 2"):
        parse_complete_submission(duplicate, entry=index_entry())
    with pytest.raises(CollectorError, match="hash changed"):
        parse_complete_submission(body, entry=index_entry(), expected_sha256="0" * 64)


def test_form4a_requires_exact_document_type_and_preserves_original_date():
    entry = index_entry(
        accession="0000789019-26-000002",
        form_type="4/A",
        cik="789019",
    )
    filing = parse_complete_submission(
        fixture_bytes("sec_form4a_complete.txt"), entry=entry
    )
    assert filing.form_type == "4/A"
    assert filing.original_submission_date == "2026-08-10"
    assert filing.transactions[0].plan_10b5 == "FALSE"
    with pytest.raises(CollectorError, match="does not match"):
        parse_complete_submission(
            fixture_bytes("sec_form4a_complete.txt"), entry=index_entry()
        )


def test_10b5_flag_is_filing_level_and_absence_is_unknown():
    body = fixture_bytes("sec_form4_complete.txt").replace(
        b"  <aff10b5One>0</aff10b5One>\n", b""
    ).replace(
        b"<transactionCoding><transactionCode>P</transactionCode></transactionCoding>",
        b"<transactionCoding><transactionCode>P</transactionCode><aff10b5One>true</aff10b5One></transactionCoding>",
        1,
    )
    filing = parse_complete_submission(body, entry=index_entry())
    assert {row.plan_10b5 for row in filing.transactions} == {"UNKNOWN"}


def test_serialized_token_bucket_enforces_four_requests_per_second_without_burst():
    now = [10.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = SerializedTokenBucket(4, clock=clock, sleeper=sleep)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    assert sleeps == pytest.approx([0.25, 0.25])


def test_http_retry_honors_retry_after_and_403_stops_immediately():
    delays: list[float] = []
    opener = QueueOpener(
        [
            http_error(429, retry_after="2"),
            FakeResponse(b"{}", content_type="application/json"),
        ]
    )
    client = make_client(opener, sleeper=delays.append)
    assert client.json_object("https://www.sec.gov/Archives/test/index.json") == {}
    assert 2.0 in delays
    forbidden = QueueOpener([http_error(403), FakeResponse(b"{}", content_type="application/json")])
    with pytest.raises(CollectorError, match="stop and review"):
        make_client(forbidden).json_object("https://www.sec.gov/Archives/test/index.json")
    assert len(forbidden.requests) == 1


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_each_locked_transient_http_status_is_retried(status):
    opener = QueueOpener(
        [
            http_error(status),
            FakeResponse(b"{}", content_type="application/json"),
        ]
    )
    assert make_client(opener).json_object(
        "https://www.sec.gov/Archives/test/index.json"
    ) == {}
    assert len(opener.requests) == 2


def test_conditional_cache_uses_etag_and_detects_tampering(tmp_path):
    url = "https://www.sec.gov/Archives/test/index.json"
    first = QueueOpener(
        [
            FakeResponse(
                b'{"directory":{"item":[]}}',
                content_type="application/json",
                headers={"ETag": '"abc"'},
            )
        ]
    )
    client = make_client(first, cache_dir=tmp_path)
    result = client.get(url, expected="json")
    assert result.from_cache is False
    second = QueueOpener([http_error(304)])
    cached = make_client(second, cache_dir=tmp_path).get(url, expected="json")
    assert cached.from_cache is True and cached.status == 304
    request = second.requests[0][0]
    assert request.get_header("If-none-match") == '"abc"'
    body_path, _metadata_path = PrivateResponseCache(tmp_path)._paths(url)
    body_path.write_bytes(b"tampered")
    with pytest.raises(CollectorError, match="hash mismatch"):
        make_client(QueueOpener([]), cache_dir=tmp_path).get(url, expected="json")


def test_immutable_complete_submission_cache_hit_requires_no_network(tmp_path):
    url = "https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001.txt"
    body = fixture_bytes("sec_form4_complete.txt")
    first = make_client(
        QueueOpener([FakeResponse(body, content_type="text/plain")]),
        cache_dir=tmp_path,
    )
    first.get(url, expected="submission", revalidate=False)
    cold_network = QueueOpener([])
    second = make_client(cold_network, cache_dir=tmp_path)
    result = second.get(url, expected="submission", revalidate=False)
    assert result.from_cache is True
    assert second.request_count == 0
    assert cold_network.requests == []


def test_declared_sec_gzip_response_is_decoded_before_schema_validation():
    response = FakeResponse(
        gzip.compress(b"{}"),
        content_type="application/json",
        headers={"Content-Encoding": "gzip"},
    )
    assert make_client(QueueOpener([response])).json_object(
        "https://www.sec.gov/Archives/test/index.json"
    ) == {}


@pytest.mark.parametrize(
    "body,content_type,message",
    [
        (b"", "application/json", "empty"),
        (b"<html>rate limited</html>", "application/json", "HTML"),
        (b"{}", "text/plain", "content type"),
    ],
)
def test_http_client_rejects_empty_html_and_wrong_content_type(body, content_type, message):
    client = make_client(QueueOpener([FakeResponse(body, content_type=content_type)]))
    with pytest.raises(CollectorError, match=message):
        client.get("https://www.sec.gov/Archives/test/index.json", expected="json")


def test_window_collection_fetches_duplicate_accession_once_and_marks_completed_day():
    quarter = json.dumps(
        {
            "directory": {
                "item": [{"name": "master.20260811.idx", "type": "file"}]
            }
        }
    ).encode()
    responses = QueueOpener(
        [
            FakeResponse(quarter, content_type="application/json"),
            FakeResponse(fixture_bytes("sec_master_20260811.idx"), content_type="text/plain"),
            FakeResponse(fixture_bytes("sec_form4_complete.txt"), content_type="text/plain"),
            FakeResponse(fixture_bytes("sec_form4a_complete.txt"), content_type="text/plain"),
        ]
    )
    collection = collect_form4_window(
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        client=make_client(responses),
    )
    assert len(collection.filings) == 2
    assert collection.completed_index_days == ("2026-08-11",)
    assert collection.source_requests == 4
    requested_urls = [request.full_url for request, _timeout in responses.requests]
    assert requested_urls.count(
        "https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001.txt"
    ) == 1


def test_window_collection_skips_known_accession_even_when_private_cache_is_cold():
    known = parse_complete_submission(
        fixture_bytes("sec_form4_complete.txt"), entry=index_entry()
    )
    quarter = b'{"directory":{"item":[{"name":"master.20260811.idx"}]}}'
    master = fixture_bytes("sec_master_20260811.idx").split(
        b"789019|Example", 1
    )[0]
    responses = QueueOpener(
        [
            FakeResponse(quarter, content_type="application/json"),
            FakeResponse(master, content_type="text/plain"),
        ]
    )
    collection = collect_form4_window(
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        client=make_client(responses),
        known_accessions={known.accession: known},
    )
    assert collection.filings == (known,)
    assert collection.completed_index_days == ("2026-08-11",)
    assert collection.source_requests == 2


def test_window_collection_skips_committed_privacy_ledger_accession_on_cold_cache():
    quarter = b'{"directory":{"item":[{"name":"master.20260811.idx"}]}}'
    master = fixture_bytes("sec_master_20260811.idx").split(
        b"789019|Example", 1
    )[0]
    accession = "0000320193-26-000001"
    ledger_entry = {
        "accession": accession,
        "form_type": "4",
        "filing_date": "2026-08-11",
        "index_date": "2026-08-11",
    }
    responses = QueueOpener(
        [
            FakeResponse(quarter, content_type="application/json"),
            FakeResponse(master, content_type="text/plain"),
        ]
    )
    collection = collect_form4_window(
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        client=make_client(responses),
        known_ledger_entries={accession: ledger_entry},
    )
    assert collection.filings == ()
    assert collection.reused_ledger_accessions == (accession,)
    assert collection.completed_index_days == ("2026-08-11",)
    assert collection.master_accessions_by_day == {"2026-08-11": (accession,)}
    assert collection.source_requests == 2


def test_committed_privacy_ledger_mismatch_leaves_day_incomplete():
    quarter = b'{"directory":{"item":[{"name":"master.20260811.idx"}]}}'
    master = fixture_bytes("sec_master_20260811.idx").split(
        b"789019|Example", 1
    )[0]
    accession = "0000320193-26-000001"
    collection = collect_form4_window(
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        client=make_client(
            QueueOpener(
                [
                    FakeResponse(quarter, content_type="application/json"),
                    FakeResponse(master, content_type="text/plain"),
                ]
            )
        ),
        known_ledger_entries={
            accession: {
                "accession": accession,
                "form_type": "4",
                "filing_date": "2026-08-10",
                "index_date": "2026-08-11",
            }
        },
    )
    assert collection.completed_index_days == ()
    assert collection.failures[0]["stage"] == "KNOWN_LEDGER_RECONCILIATION"


def test_completed_master_day_explicitly_reports_deletion_against_prior_ledger():
    quarter = b'{"directory":{"item":[{"name":"master.20260811.idx"}]}}'
    master = b"""Description: Daily Index\nCIK|Company Name|Form Type|Date Filed|File Name\n--------------------------------------------------------------------------------\n"""
    prior_accession = "0000320193-26-000001"
    collection = collect_form4_window(
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        client=make_client(
            QueueOpener(
                [
                    FakeResponse(quarter, content_type="application/json"),
                    FakeResponse(master, content_type="text/plain"),
                ]
            )
        ),
        known_ledger_entries={
            prior_accession: {
                "accession": prior_accession,
                "form_type": "4",
                "filing_date": "2026-08-11",
                "index_date": "2026-08-11",
            }
        },
    )
    assert collection.completed_index_days == ("2026-08-11",)
    assert collection.master_accessions_by_day == {"2026-08-11": ()}
    assert collection.reused_ledger_accessions == ()


def test_window_collection_fails_closed_when_known_accession_metadata_drifts():
    known = parse_complete_submission(
        fixture_bytes("sec_form4_complete.txt"), entry=index_entry()
    )
    quarter = b'{"directory":{"item":[{"name":"master.20260811.idx"}]}}'
    master = fixture_bytes("sec_master_20260811.idx").split(
        b"789019|Example", 1
    )[0]
    collection = collect_form4_window(
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        client=make_client(
            QueueOpener(
                [
                    FakeResponse(quarter, content_type="application/json"),
                    FakeResponse(master, content_type="text/plain"),
                ]
            )
        ),
        known_accessions={known.accession: replace(known, filing_date="2026-08-10")},
    )
    assert collection.completed_index_days == ()
    assert collection.failures[0]["stage"] == "KNOWN_ACCESSION_RECONCILIATION"


def test_transient_submission_failure_leaves_index_day_incomplete():
    quarter = b'{"directory":{"item":[{"name":"master.20260811.idx"}]}}'
    master = fixture_bytes("sec_master_20260811.idx").split(
        b"789019|Example", 1
    )[0]
    responses = QueueOpener(
        [
            FakeResponse(quarter, content_type="application/json"),
            FakeResponse(master, content_type="text/plain"),
            http_error(503),
        ]
    )
    collection = collect_form4_window(
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        client=make_client(responses, attempts=1),
    )
    assert collection.completed_index_days == ()
    assert collection.failures[0]["stage"] == "SUBMISSION"
