import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.parse

import pytest

from pipeline.collectors.common import CollectorError
from pipeline.collectors.cftc import (
    _get_json_array,
    fetch_tff_futures_only,
    parse_tff_futures_only,
)
from pipeline.config import (
    CANONICAL_P1_CFTC_METRIC_IDS,
    ConfigValidationError,
    load_config_bundle,
    validate_config_bundle,
)
from pipeline.contracts import ContractValidationError, validate_publication, validate_snapshot
from pipeline.release import (
    CollectorFunctions,
    _cftc_expected_next_update,
    _cftc_freshness_for,
    build_release,
    promote_stage,
    write_stage,
)
from pipeline.tests.test_release1 import NOW, fixture_collectors
from pipeline.transforms.p1 import (
    cftc_position_series,
    cftc_position_statistics,
    common_direction,
    positioning_direction,
)


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "cftc_tff_futures_only.json").read_text()
)


def test_cftc_parser_enforces_futures_only_identity_and_raw_reconciliation():
    parsed = parse_tff_futures_only(FIXTURE)
    assert set(parsed) == {"13874A", "20974+"}
    assert parsed["13874A"][-1] == {
        "date": "2026-08-04",
        "contract_code": "13874A",
        "contract_name": "E-MINI S&P 500",
        "market_and_exchange_name": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        "cftc_market_code": "CME",
        "cftc_commodity_code": "138",
        "commodity_name": "S&P BROAD BASED STOCK INDICES",
        "contract_units": "($50 X S&P 500 INDEX)",
        "report_type": "TFF_FUTURES_ONLY",
        "row_id": "row-es-2",
        "source_report_id": "26080413874AF",
        "released_at": "2026-08-07T19:30:05Z",
        "open_interest": 1000,
        "asset_manager_long": 510,
        "asset_manager_short": 100,
        "asset_manager_spread": 50,
        "leveraged_funds_long": 90,
        "leveraged_funds_short": 300,
        "leveraged_funds_spread": 25,
        "asset_manager_pct_long": 51.0,
        "asset_manager_pct_short": 10.0,
        "leveraged_funds_pct_long": 9.0,
        "leveraged_funds_pct_short": 30.0,
    }
    assert parsed["20974+"][-1]["contract_name"] == "NASDAQ-100 Consolidated"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda row: row.pop("id"), "id must be"),
        (lambda row: row.__setitem__("futonly_or_combined", "Combined"), "not futures-only"),
        (lambda row: row.__setitem__("contract_market_name", "NASDAQ MINI"), "name mismatch"),
        (lambda row: row.__setitem__("open_interest_all", "0"), "must be positive"),
        (lambda row: row.__setitem__("pct_of_oi_asset_mgr_long", "1.0"), "does not reconcile"),
        (lambda row: row.__setitem__("report_date_as_yyyy_mm_dd", "bad"), "invalid"),
    ],
)
def test_cftc_parser_fails_closed_on_schema_date_unit_and_identity_drift(mutator, message):
    payload = copy.deepcopy(FIXTURE)
    mutator(payload[0])
    with pytest.raises(CollectorError, match=message):
        parse_tff_futures_only(payload)


def test_cftc_parser_deduplicates_exact_rows_but_rejects_conflicts_and_empty():
    assert len(parse_tff_futures_only([*FIXTURE, copy.deepcopy(FIXTURE[0])])["13874A"]) == 2
    conflicting = copy.deepcopy(FIXTURE[0])
    conflicting[":id"] = "different-row"
    conflicting["asset_mgr_positions_long"] = "501"
    conflicting["pct_of_oi_asset_mgr_long"] = "50.1"
    with pytest.raises(CollectorError, match="conflicting duplicate"):
        parse_tff_futures_only([*FIXTURE, conflicting])
    for payload in ([], {}, "<html>error</html>"):
        with pytest.raises(CollectorError):
            parse_tff_futures_only(payload)


def test_cftc_fetch_query_encodes_plus_and_uses_stable_order(monkeypatch):
    captured = {}

    def fake_get(url, **_kwargs):
        captured["url"] = url
        return FIXTURE

    monkeypatch.setattr("pipeline.collectors.cftc._get_json_array", fake_get)
    result = fetch_tff_futures_only(
        start=datetime(2026, 7, 1).date(), end=datetime(2026, 8, 12).date()
    )
    assert result["20974+"][-1]["date"] == "2026-08-04"
    assert "20974%2B" in captured["url"]
    assert "%3Aid+asc" in captured["url"]
    assert "id+asc" in captured["url"]
    assert "%24offset=0" in captured["url"]


def test_cftc_fetch_paginates_stably_and_rejects_unbounded_full_pages(monkeypatch):
    urls = []

    def paged_get(url, **_kwargs):
        urls.append(url)
        offset = int(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["$offset"][0])
        return FIXTURE[offset : offset + 2]

    monkeypatch.setattr("pipeline.collectors.cftc.PAGE_LIMIT", 2)
    monkeypatch.setattr("pipeline.collectors.cftc._get_json_array", paged_get)
    result = fetch_tff_futures_only(
        start=datetime(2026, 7, 1).date(), end=datetime(2026, 8, 12).date()
    )
    assert [len(result[code]) for code in ("13874A", "20974+")] == [2, 2]
    assert [urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["$offset"][0] for url in urls] == ["0", "2", "4"]

    monkeypatch.setattr("pipeline.collectors.cftc.MAX_PAGES", 2)
    monkeypatch.setattr(
        "pipeline.collectors.cftc._get_json_array",
        lambda *_args, **_kwargs: FIXTURE[:2],
    )
    with pytest.raises(CollectorError, match="pagination exceeded"):
        fetch_tff_futures_only(
            start=datetime(2026, 7, 1).date(), end=datetime(2026, 8, 12).date()
        )


class _Headers:
    def __init__(self, content_type):
        self.content_type = content_type

    def get_content_type(self):
        return self.content_type


class _Response:
    def __init__(self, body, content_type="application/json"):
        self.body = body
        self.headers = _Headers(content_type)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


@pytest.mark.parametrize(
    ("body", "content_type", "message"),
    [
        (b"<html>oops</html>", "text/html", "content type"),
        (b"", "application/json", "empty"),
        (b"{}", "application/json", "root must be an array"),
    ],
)
def test_cftc_http_boundary_rejects_html_empty_and_wrong_json_root(
    monkeypatch, body, content_type, message
):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_args, **_kwargs: _Response(body, content_type)
    )
    monkeypatch.setattr("pipeline.collectors.cftc.time.sleep", lambda *_args: None)
    with pytest.raises(CollectorError, match=message):
        _get_json_array("https://example.test", user_agent="test", attempts=1)


def _normalized_rows(count=160, *, latest="2026-08-04"):
    latest_date = datetime.fromisoformat(latest).date()
    output = {}
    for code, name in (("13874A", "E-MINI S&P 500"), ("20974+", "NASDAQ-100 Consolidated")):
        rows = []
        for reverse_index in reversed(range(count)):
            day = latest_date - timedelta(days=7 * reverse_index)
            index = count - reverse_index
            oi = 1_000_000 + index * 100
            rows.append(
                {
                    "date": day.isoformat(),
                    "contract_code": code,
                    "contract_name": name,
                    "market_and_exchange_name": f"{name} - CHICAGO MERCANTILE EXCHANGE",
                    "cftc_market_code": "CME",
                    "cftc_commodity_code": "138" if code == "13874A" else "209",
                    "commodity_name": "STOCK INDICES",
                    "contract_units": "INDEX",
                    "report_type": "TFF_FUTURES_ONLY",
                    "row_id": f"row-{code}-{index}",
                    "source_report_id": f"report-{code}-{index}",
                    "released_at": (datetime.combine(day + timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc).replace(hour=19, minute=30)).isoformat().replace("+00:00", "Z"),
                    "open_interest": oi,
                    "asset_manager_long": 400_000 + index * index,
                    "asset_manager_short": 200_000 + index,
                    "asset_manager_spread": 10_000,
                    "asset_manager_pct_long": 100 * (400_000 + index * index) / oi,
                    "asset_manager_pct_short": 100 * (200_000 + index) / oi,
                    "leveraged_funds_long": 150_000 + index * index // 2,
                    "leveraged_funds_short": 250_000 + index,
                    "leveraged_funds_spread": 8_000,
                    "leveraged_funds_pct_long": 100 * (150_000 + index * index // 2) / oi,
                    "leveraged_funds_pct_short": 100 * (250_000 + index) / oi,
                }
            )
        output[code] = rows
    return output


def test_cftc_transform_uses_raw_percent_changes_and_population_zscore():
    points = cftc_position_series(_normalized_rows()["13874A"], category="asset_manager")
    stats = cftc_position_statistics(points)
    assert stats["sample_size"] == 160
    assert stats["z_score_3_year_sample_size"] == 156
    assert stats["change_8_weeks"] == pytest.approx(
        points[-1]["net_percent_open_interest_raw"]
        - points[-9]["net_percent_open_interest_raw"],
        abs=1e-6,
    )
    assert stats["change_12_weeks"] == pytest.approx(
        points[-1]["net_percent_open_interest_raw"]
        - points[-13]["net_percent_open_interest_raw"]
    )
    assert stats["z_score_3_year"] is not None
    flat = copy.deepcopy(points[-156:])
    for point in flat:
        point["net_percent_open_interest_raw"] = 1.0
    assert cftc_position_statistics(flat)["z_score_3_year"] is None
    assert positioning_direction(1) == "MORE_NET_LONG"
    assert positioning_direction(-1) == "MORE_NET_SHORT"
    assert common_direction(["MORE_NET_LONG", "MORE_NET_SHORT"]) == "MIXED"


def test_live_reference_fixture_math_matches_audited_cftc_values():
    latest = {
        "13874A": {
            "date": "2026-08-04", "contract_code": "13874A", "contract_name": "E-MINI S&P 500",
            "market_and_exchange_name": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE", "cftc_market_code": "CME",
            "cftc_commodity_code": "138", "commodity_name": "STOCK INDICES", "contract_units": "INDEX",
            "report_type": "TFF_FUTURES_ONLY", "row_id": "row-es", "source_report_id": "26080413874AF",
            "open_interest": 2116079, "asset_manager_long": 1162320, "asset_manager_short": 225287,
            "asset_manager_spread": 0, "asset_manager_pct_long": 54.9, "asset_manager_pct_short": 10.6,
            "leveraged_funds_long": 206039, "leveraged_funds_short": 536038, "leveraged_funds_spread": 0,
            "leveraged_funds_pct_long": 9.7, "leveraged_funds_pct_short": 25.3,
        },
        "20974+": {
            "date": "2026-08-04", "contract_code": "20974+", "contract_name": "NASDAQ-100 Consolidated",
            "market_and_exchange_name": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE", "cftc_market_code": "CME",
            "cftc_commodity_code": "209", "commodity_name": "STOCK INDICES", "contract_units": "INDEX",
            "report_type": "TFF_FUTURES_ONLY", "row_id": "row-nq", "source_report_id": "26080420974+F",
            "open_interest": 334748, "asset_manager_long": 100767, "asset_manager_short": 35515,
            "asset_manager_spread": 0, "asset_manager_pct_long": 30.1, "asset_manager_pct_short": 10.6,
            "leveraged_funds_long": 40114, "leveraged_funds_short": 140754, "leveraged_funds_spread": 0,
            "leveraged_funds_pct_long": 12.0, "leveraged_funds_pct_short": 42.0,
        },
    }
    expected = {
        ("13874A", "asset_manager"): (937033, 44.281570),
        ("13874A", "leveraged_funds"): (-329999, -15.594834),
        ("20974+", "asset_manager"): (65252, 19.492872),
        ("20974+", "leveraged_funds"): (-100640, -30.064407),
    }
    for identity, (net, pct) in expected.items():
        point = cftc_position_series([latest[identity[0]]], category=identity[1])[0]
        assert point["net_position"] == net
        assert point["value"] == pytest.approx(pct)


def test_cftc_transform_rejects_duplicate_dates_and_mixed_contracts():
    rows = _normalized_rows(2)["13874A"]
    with pytest.raises(CollectorError, match="strictly increasing"):
        cftc_position_series([rows[0], copy.deepcopy(rows[0])], category="asset_manager")
    mixed = copy.deepcopy(rows)
    mixed[-1]["contract_code"] = "20974+"
    with pytest.raises(CollectorError, match="mixes contract"):
        cftc_position_series(mixed, category="asset_manager")


def test_cftc_schedule_uses_reviewed_holidays_and_release_grace():
    schedule = load_config_bundle().cftc_release_schedule["releases"]
    assert _cftc_expected_next_update("2026-06-09", "2026-06-12T19:30:00Z", schedule) == "2026-06-22"
    assert _cftc_expected_next_update("2026-08-04", "2026-08-07T19:30:05Z", schedule) == "2026-08-14"
    assert _cftc_freshness_for(
        "2026-08-04",
        "2026-08-07T19:30:05Z",
        now_et=datetime(2026, 8, 14, 17, 29, tzinfo=timezone(timedelta(hours=-4))),
        release_schedule=schedule,
    ) == ("FRESH", "OK")
    assert _cftc_freshness_for(
        "2026-08-04",
        "2026-08-07T19:30:05Z",
        now_et=datetime(2026, 8, 14, 17, 31, tzinfo=timezone(timedelta(hours=-4))),
        release_schedule=schedule,
    ) == ("LATE", "NOT_RELEASED_YET")
    assert _cftc_expected_next_update("2026-08-04", None, []) is None
    assert _cftc_freshness_for(
        "2026-08-04",
        None,
        now_et=datetime(2026, 8, 14, 17, 31, tzinfo=timezone(timedelta(hours=-4))),
        release_schedule=[],
    ) == ("UNKNOWN", "ERROR")


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda schedule: schedule.__setitem__(
                "source_url", "https://example.test/schedule"
            ),
            "source_url must be official",
        ),
        (
            lambda schedule: schedule.__setitem__("release_time_et", "16:00"),
            "release_time_et must be 15:30",
        ),
        (
            lambda schedule: schedule.__setitem__(
                "reviewed_at", "2026-08-12T16:00:00-04:00"
            ),
            "reviewed_at must use UTC",
        ),
        (
            lambda schedule: schedule["releases"][2].update(
                {
                    "observation_date": schedule["releases"][1]["observation_date"],
                    "release_date": "2026-01-10",
                }
            ),
            "observation dates must be strictly increasing",
        ),
        (
            lambda schedule: schedule["releases"][2].update(
                {
                    "observation_date": "2026-01-07",
                    "release_date": schedule["releases"][1]["release_date"],
                }
            ),
            "release dates must be strictly increasing",
        ),
    ],
)
def test_cftc_schedule_config_fails_closed_on_unreviewed_or_ambiguous_data(
    mutator, message
):
    bundle = load_config_bundle()
    schedule = copy.deepcopy(bundle.cftc_release_schedule)
    mutator(schedule)
    with pytest.raises(ConfigValidationError, match=message):
        validate_config_bundle(replace(bundle, cftc_release_schedule=schedule))


def _release_collectors(cftc_rows):
    return replace(fixture_collectors(), cftc=lambda **_kwargs: cftc_rows)


def test_release_two_publishes_one_cftc_source_and_evidence_only_switch(tmp_path):
    publication = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    )
    snapshot = publication.snapshot
    assert set(CANONICAL_P1_CFTC_METRIC_IDS) <= snapshot["metrics"].keys()
    assert not {
        "cftc_asset_manager_positioning",
        "cftc_leveraged_funds_positioning_proxy",
        "cta_proxy",
    } & snapshot["metrics"].keys()
    assert len(snapshot["sources"]) == 11
    assert "cftc_tff_futures_only" in snapshot["sources"]
    switch = snapshot["switches"]["market_ignition"]
    assert switch["mode"] == "EVIDENCE_ONLY"
    assert switch["assessment"] is None
    assert switch["available_blocks"] == 1
    assert switch["confidence"] == "LOW"
    assert all(block["triggered"] is None for block in switch["evidence_blocks"])
    positioning = switch["evidence_blocks"][1]
    assert positioning["direction"] in {"MORE_NET_LONG", "MORE_NET_SHORT", "MIXED", "FLAT"}
    for metric_id in CANONICAL_P1_CFTC_METRIC_IDS:
        metric = snapshot["metrics"][metric_id]
        series = publication.series_by_id[metric_id]
        assert metric["changes"]["eight_weeks"] == metric["statistics"]["change_8_weeks"]
        assert metric["changes"]["twelve_weeks"] == metric["statistics"]["change_12_weeks"]
        assert metric["expected_next_update"] == "2026-08-14"
        assert series["expected_next_update"] == "2026-08-14"
        assert series["observations"][-1]["source_report_id"].startswith("report-")
    assert snapshot["sources"]["cftc_tff_futures_only"]["expected_next_update"] == "2026-08-14"


def test_truncated_or_stale_cftc_never_publishes_neutral_coverage(tmp_path):
    truncated = build_release(
        data_dir=tmp_path / "truncated",
        now=NOW,
        collectors=_release_collectors(_normalized_rows(13)),
    )
    switch = truncated.snapshot["switches"]["market_ignition"]
    assert switch["available_blocks"] == 0
    assert switch["confidence"] == "UNKNOWN"
    assert switch["evidence_blocks"][1]["direction"] == "UNKNOWN"

    stale = build_release(
        data_dir=tmp_path / "stale",
        now=NOW,
        collectors=_release_collectors(_normalized_rows(latest="2026-07-14")),
    )
    assert stale.snapshot["switches"]["market_ignition"]["available_blocks"] == 0


def test_cftc_bundle_failure_preserves_all_four_last_good_atomically(tmp_path):
    data_dir = tmp_path / "data"
    stage = tmp_path / "stage"
    first = build_release(
        data_dir=data_dir,
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    )
    write_stage(first, stage)
    promote_stage(stage, data_dir=data_dir)

    def fail(**_kwargs):
        raise CollectorError("schema drift")

    second = build_release(
        data_dir=data_dir,
        now=NOW + timedelta(days=1),
        collectors=replace(fixture_collectors(), cftc=fail),
    )
    for metric_id in CANONICAL_P1_CFTC_METRIC_IDS:
        assert second.snapshot["metrics"][metric_id]["value"] == first.snapshot["metrics"][metric_id]["value"]
        assert second.snapshot["metrics"][metric_id]["quality"]["status"] == "STALE"
    assert second.snapshot["switches"]["market_ignition"]["available_blocks"] == 0

    failed_stage = tmp_path / "failed-stage"
    write_stage(second, failed_stage)
    promote_stage(failed_stage, data_dir=data_dir)
    unattempted = build_release(
        group="monthly",
        data_dir=data_dir,
        now=NOW + timedelta(days=1, hours=1),
        collectors=fixture_collectors(),
    )
    for metric_id in CANONICAL_P1_CFTC_METRIC_IDS:
        assert unattempted.snapshot["metrics"][metric_id]["quality"]["status"] == "STALE"
    assert unattempted.snapshot["switches"]["market_ignition"]["available_blocks"] == 0


def test_latest_implausible_pre_update_does_not_reuse_prior_release(tmp_path):
    rows = _normalized_rows()
    for contract_rows in rows.values():
        contract_rows[-1].pop("released_at")
    publication = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(rows),
    )
    for metric_id in CANONICAL_P1_CFTC_METRIC_IDS:
        assert publication.snapshot["metrics"][metric_id]["released_at"] is None


def test_p1_contract_rejects_severity_and_held_source_leaks(tmp_path):
    snapshot = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    ).snapshot
    bad = copy.deepcopy(snapshot)
    bad["switches"]["market_ignition"]["assessment"] = "WATCH"
    with pytest.raises(ContractValidationError, match="assessment must be null"):
        validate_snapshot(bad)
    wrong_mode = copy.deepcopy(snapshot)
    wrong_mode["switches"]["market_ignition"]["mode"] = "WATCH"
    with pytest.raises(ContractValidationError, match="mode must be EVIDENCE_ONLY"):
        validate_snapshot(wrong_mode)
    leaked = copy.deepcopy(snapshot)
    leaked["metrics"]["crypto_funding_btc"]["value"] = 0
    with pytest.raises(ContractValidationError):
        validate_snapshot(leaked)
    wrong_order = copy.deepcopy(snapshot)
    wrong_order["switches"]["market_ignition"]["evidence_blocks"].reverse()
    with pytest.raises(ContractValidationError, match="IDs/order"):
        validate_snapshot(wrong_order)

    wrong_direction = copy.deepcopy(snapshot)
    metric_id = "cftc_e_mini_sp500_asset_manager_net_pct_oi"
    actual_direction = wrong_direction["metrics"][metric_id]["context"]["direction"]
    wrong_direction["metrics"][metric_id]["context"]["direction"] = (
        "MORE_NET_SHORT"
        if actual_direction != "MORE_NET_SHORT"
        else "MORE_NET_LONG"
    )
    with pytest.raises(ContractValidationError, match="context.direction"):
        validate_snapshot(wrong_direction)
    wrong_block = copy.deepcopy(snapshot)
    wrong_block["switches"]["market_ignition"]["evidence_blocks"][1]["confidence"] = "HIGH"
    with pytest.raises(ContractValidationError, match="direction/status/confidence"):
        validate_snapshot(wrong_block)

    for field, value in (
        ("direction", "MORE_NET_LONG"),
        ("status", "MORE_NET_LONG"),
    ):
        wrong_block = copy.deepcopy(snapshot)
        block = wrong_block["switches"]["market_ignition"]["evidence_blocks"][1]
        block[field] = value if block[field] != value else "MORE_NET_SHORT"
        with pytest.raises(ContractValidationError, match="direction/status/confidence"):
            validate_snapshot(wrong_block)
    wrong_switch_confidence = copy.deepcopy(snapshot)
    wrong_switch_confidence["switches"]["market_ignition"]["confidence"] = "HIGH"
    with pytest.raises(ContractValidationError, match="direction/status/confidence"):
        validate_snapshot(wrong_switch_confidence)


def test_p1_contract_requires_all_cftc_artifacts_and_atomic_source(tmp_path):
    publication = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    )
    missing_source = copy.deepcopy(publication.snapshot)
    source = missing_source["sources"].pop("cftc_tff_futures_only")
    missing_source["source_health"][source["status"].lower()] -= 1
    with pytest.raises(ContractValidationError, match="cftc_tff_futures_only is required"):
        validate_snapshot(missing_source)

    snapshot = copy.deepcopy(publication.snapshot)
    manifest = copy.deepcopy(publication.manifest)
    series = copy.deepcopy(publication.series_by_id)
    for metric_id in CANONICAL_P1_CFTC_METRIC_IDS:
        availability = snapshot["metrics"].pop(metric_id)["availability"]
        snapshot[
            "active_free_count" if availability == "ACTIVE_FREE" else "active_proxy_count"
        ] -= 1
        series.pop(metric_id)
    snapshot["switches"]["market_ignition"]["available_blocks"] = 0
    positioning = snapshot["switches"]["market_ignition"]["evidence_blocks"][1]
    positioning.update(
        {
            "available": False,
            "status": "UNAVAILABLE_FREE",
            "direction": "UNKNOWN",
            "confidence": "UNKNOWN",
        }
    )
    snapshot["switches"]["market_ignition"]["confidence"] = "UNKNOWN"
    source = snapshot["sources"].pop("cftc_tff_futures_only")
    snapshot["source_health"][source["status"].lower()] -= 1
    manifest["metrics"] = [
        row
        for row in manifest["metrics"]
        if row["metric_id"] not in CANONICAL_P1_CFTC_METRIC_IDS
    ]
    with pytest.raises(ContractValidationError, match="missing canonical CFTC metrics"):
        validate_publication(snapshot, manifest, series)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "STALE"),
        ("last_success_at", "2000-01-01T00:00:00Z"),
        ("last_attempt_at", "2000-01-01T00:00:00Z"),
        ("updated_at", "2000-01-01T00:00:00Z"),
        ("failure_reason", "invented failure"),
    ],
)
def test_p1_contract_rejects_cftc_source_state_or_provenance_lies(
    tmp_path, field, value
):
    snapshot = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    ).snapshot
    source = snapshot["sources"]["cftc_tff_futures_only"]
    if field == "status":
        snapshot["source_health"][source["status"].lower()] -= 1
        snapshot["source_health"][value.lower()] += 1
    source[field] = value
    with pytest.raises(ContractValidationError, match="source state/provenance"):
        validate_snapshot(snapshot)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("contract_code", "20974+", "identity metadata"),
        ("contract_name", "wrong", "identity metadata"),
        ("trader_category", "leveraged_funds", "identity metadata"),
        ("report_type", "Combined", "identity metadata"),
        ("market_and_exchange_name", "wrong", "market_and_exchange_name"),
        ("cftc_market_code", "", "cftc_market_code"),
        ("cftc_commodity_code", "", "cftc_commodity_code"),
        ("commodity_name", "", "commodity_name"),
        ("contract_units", "", "contract_units"),
        ("row_id", "", "row_id"),
        ("source_report_id", "", "source_report_id"),
        ("released_at", "not-a-timestamp", "released_at"),
        ("open_interest", 0, "domain"),
        ("asset_manager_spread", -1, "domain"),
        ("asset_manager_pct_long", 0.0, "does not reconcile"),
        ("net_position", 0, "net_position"),
        ("net_percent_open_interest_raw", 0.0, "raw net percent"),
        ("value", 0.0, "value does not reconcile"),
    ],
)
def test_publication_rejects_tampered_cftc_full_series_points(tmp_path, field, value, message):
    publication = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    )
    series = copy.deepcopy(publication.series_by_id)
    metric_id = "cftc_e_mini_sp500_asset_manager_net_pct_oi"
    series[metric_id]["observations"][-1][field] = value
    with pytest.raises(ContractValidationError, match=message):
        validate_publication(publication.snapshot, publication.manifest, series)


@pytest.mark.parametrize(
    "field",
    (
        "net_position",
        "open_interest",
        "net_percent_open_interest",
        "change_8_weeks",
        "change_12_weeks",
        "z_score_3_year",
        "z_score_3_year_sample_size",
    ),
)
def test_publication_recomputes_cftc_statistics_from_full_series(tmp_path, field):
    publication = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    )
    snapshot = copy.deepcopy(publication.snapshot)
    metric_id = "cftc_e_mini_sp500_asset_manager_net_pct_oi"
    actual = snapshot["metrics"][metric_id]["statistics"][field]
    snapshot["metrics"][metric_id]["statistics"][field] = actual + 1
    if field == "change_8_weeks":
        snapshot["metrics"][metric_id]["changes"]["eight_weeks"] = actual + 1
        snapshot["metrics"][metric_id]["context"]["direction"] = positioning_direction(actual + 1)
    elif field == "change_12_weeks":
        snapshot["metrics"][metric_id]["changes"]["twelve_weeks"] = actual + 1
    elif field == "z_score_3_year_sample_size":
        positioning = snapshot["switches"]["market_ignition"]["evidence_blocks"][1]
        positioning.update(
            {
                "available": False,
                "status": "UNAVAILABLE_FREE",
                "direction": "UNKNOWN",
                "confidence": "UNKNOWN",
            }
        )
        snapshot["switches"]["market_ignition"]["available_blocks"] = 0
        snapshot["switches"]["market_ignition"]["confidence"] = "UNKNOWN"
    with pytest.raises(ContractValidationError, match="must match full series"):
        validate_publication(snapshot, publication.manifest, publication.series_by_id)


def test_publication_cross_checks_cftc_series_schedule_and_latest_release(tmp_path):
    publication = build_release(
        data_dir=tmp_path / "data",
        now=NOW,
        collectors=_release_collectors(_normalized_rows()),
    )
    metric_id = "cftc_e_mini_sp500_asset_manager_net_pct_oi"
    wrong_schedule = copy.deepcopy(publication.series_by_id)
    wrong_schedule[metric_id]["expected_next_update"] = "2026-08-15"
    with pytest.raises(ContractValidationError, match="expected_next_update must match"):
        validate_publication(publication.snapshot, publication.manifest, wrong_schedule)

    wrong_release = copy.deepcopy(publication.series_by_id)
    wrong_release[metric_id]["observations"][-1]["released_at"] = (
        "2026-08-08T19:30:00Z"
    )
    with pytest.raises(ContractValidationError, match="latest CFTC point"):
        validate_publication(publication.snapshot, publication.manifest, wrong_release)
