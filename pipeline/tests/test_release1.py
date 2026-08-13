from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from pipeline.config import CANONICAL_P0_METRIC_IDS, load_config_bundle
from pipeline.collectors.sec_form4 import Form4Collection
from pipeline.contracts import validate_publication
from pipeline.build import NEW_YORK, h41_freshness_for
from pipeline.release import (
    CollectorFunctions,
    build_release,
    load_stage,
    promote_stage,
    write_stage,
    _explanation,
    _preserved_state,
    _technical_events,
)


NOW = datetime(2026, 8, 12, 20, tzinfo=timezone.utc)


def business_points(start: datetime, days: int, base: float):
    return [
        {
            "date": (start + timedelta(days=index)).date().isoformat(),
            "value": round(base + index * 0.001, 6),
        }
        for index in range(days)
        if (start + timedelta(days=index)).weekday() < 5
    ]


def fixture_collectors(
    *,
    fred_error: Exception | None = None,
    fred_errors_by_series: dict[str, Exception] | None = None,
) -> CollectorFunctions:
    def rate(metric_id, **_kwargs):
        offsets = {"sofr": 0.01, "effr": 0.0, "obfr": -0.01, "tgcr": 0.0, "bgcr": 0.0}
        return business_points(datetime(2026, 5, 25, tzinfo=timezone.utc), 80, 3.5 + offsets[metric_id])

    def fred(series_id, **_kwargs):
        if fred_error is not None:
            raise fred_error
        if fred_errors_by_series and series_id in fred_errors_by_series:
            raise fred_errors_by_series[series_id]
        if series_id == "IORB":
            return [
                {"date": "2026-05-01", "value": 3.5},
                {"date": "2026-07-30", "value": 3.5},
            ]
        return [
            {
                "date": (datetime(2026, 6, 24, tzinfo=timezone.utc) + timedelta(days=7 * index)).date().isoformat(),
                "value": 3_100.0 - index * 5,
            }
            for index in range(7)
        ]

    def on_rrp(**_kwargs):
        days = [
            point["date"]
            for point in business_points(
                datetime(2026, 7, 16, tzinfo=timezone.utc), 28, 0
            )
        ]
        return [
            {
                "date": day,
                "value": float(len(days) - index - 1),
                "submitted_usd_bn": float(len(days) - index - 1),
            }
            for index, day in enumerate(days)
        ]

    def srf_operations(**_kwargs):
        return [
            {
                "operation_id": "SRF-2026-08-12",
                "operation_date": "2026-08-12",
                "collateral_type": "treasury",
                "submitted_amount_usd_bn": 0.0,
                "accepted_amount_usd_bn": 0.0,
                "rate_pct": 4.5,
                "released_at": "2026-08-12T18:00:00Z",
            }
        ]

    def tga(**_kwargs):
        return [{"date": "2026-08-12", "value": 900.0, "source_field": "open_today_bal"}]

    def auctions(**_kwargs):
        row = {
            "cusip": "912797ZZ1",
            "auction_date": "2026-08-10",
            "issue_date": "2026-08-12",
            "offering_usd_bn": 50.0,
        }
        return [row, dict(row)]

    def cftc(**_kwargs):
        output = {}
        for code, name in (("13874A", "E-MINI S&P 500"), ("20974+", "NASDAQ-100 Consolidated")):
            rows = []
            for index in range(14):
                day = (datetime(2026, 5, 5, tzinfo=timezone.utc) + timedelta(days=7 * index)).date().isoformat()
                rows.append(
                    {
                        "date": day,
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
                        "released_at": (datetime(2026, 5, 8, 19, 30, tzinfo=timezone.utc) + timedelta(days=7 * index)).isoformat().replace("+00:00", "Z"),
                        "open_interest": 1_000_000,
                        "asset_manager_long": 400_000 + index * 1_000,
                        "asset_manager_short": 200_000,
                        "asset_manager_spread": 10_000,
                        "asset_manager_pct_long": 40 + index * 0.1,
                        "asset_manager_pct_short": 20.0,
                        "leveraged_funds_long": 150_000 + index * 500,
                        "leveraged_funds_short": 250_000,
                        "leveraged_funds_spread": 8_000,
                        "leveraged_funds_pct_long": 15 + index * 0.05,
                        "leveraged_funds_pct_short": 25.0,
                    }
                )
            output[code] = rows
        return output

    def fred_p2(series_id, **_kwargs):
        if series_id == "NCBEILQ027S":
            values = [48_000_000.0, 49_500_000.0, 51_000_000.0, 52_500_000.0, 54_000_000.0]
        elif series_id == "GDP":
            values = [27_000.0, 27_500.0, 28_000.0, 28_500.0, 29_000.0]
        else:
            raise AssertionError(series_id)
        dates = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]
        return {
            "series_id": series_id,
            "title": series_id,
            "last_updated": "2026-06-26T12:00:00Z",
            "units": "Millions of U.S. Dollars" if series_id == "NCBEILQ027S" else "Billions of Dollars",
            "seasonal_adjustment": "Not Seasonally Adjusted" if series_id == "NCBEILQ027S" else "Seasonally Adjusted Annual Rate",
            "observations": [
                {
                    "date": day,
                    "value": value,
                    "realtime_start": "2026-06-26",
                    "realtime_end": "2026-06-26",
                }
                for day, value in zip(dates, values, strict=True)
            ],
        }

    def sec_form4(**_kwargs):
        days = tuple(
            point["date"]
            for point in business_points(
                datetime(2026, 7, 16, tzinfo=timezone.utc), 28, 0
            )
        )
        assert len(days) == 20
        return Form4Collection(
            filings=(),
            reused_ledger_accessions=(),
            master_accessions_by_day={day: () for day in days},
            completed_index_days=days,
            discovered_index_days=days,
            failures=(),
            reviews=(),
            source_requests=20,
        )

    def sec_companyfacts(_companies, **_kwargs):
        # Release-1/2/3 fixture scenarios predate P3 and must never cross the
        # network. Release-4 success coverage uses its own four-company bundle.
        raise RuntimeError("P3 Company Facts fixture is intentionally unavailable")

    return CollectorFunctions(
        rate=rate,
        fred=fred,
        on_rrp=on_rrp,
        srf_operations=srf_operations,
        tga=tga,
        auctions=auctions,
        cftc=cftc,
        fred_p2=fred_p2,
        sec_form4=sec_form4,
        sec_companyfacts=sec_companyfacts,
    )


def test_release_one_builds_complete_v2_contract_and_preserves_real_zero(tmp_path):
    publication = build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=fixture_collectors(),
    )

    validate_publication(
        publication.snapshot, publication.manifest, publication.series_by_id
    )
    assert publication.snapshot["schema_version"] == "2.3.0"
    assert CANONICAL_P0_METRIC_IDS <= publication.snapshot["metrics"].keys()
    assert len(publication.snapshot["sources"]) == 11
    assert sum(publication.snapshot["source_health"].values()) == 11
    assert publication.snapshot["metrics"]["srf_accepted"]["value"] == 0
    assert publication.snapshot["metrics"]["on_rrp_accepted"]["value"] == 0
    on_rrp = publication.snapshot["metrics"]["on_rrp_accepted"]
    assert on_rrp["context"]["near_floor_context"] == {
        "method": "TRAILING_20_OBSERVATION_PERCENTILE",
        "sample_size": 20,
        "percentile_rank": 0.025,
        "near_floor": True,
        "threshold_rule": "BOTTOM_DECILE_WHEN_SAMPLE_SUFFICIENT",
        "interpretation": (
            "History-relative context only, not a danger signal. Falling ON RRP "
            "may cushion QT or TGA growth, or simply reflect more attractive "
            "bill and repo returns."
        ),
    }
    assert on_rrp["statistics"]["near_floor_sample_size"] == 20
    assert on_rrp["statistics"]["near_floor_percentile_rank"] == 0.025
    assert not {
        "amount_threshold",
        "usd_threshold",
        "dollar_floor",
    } & on_rrp["context"]["near_floor_context"].keys()
    assert (
        publication.snapshot["metrics"]["srf_accepted"]["statistics"]
        ["nontechnical_positive_use_streak"]
        == 0
    )
    assert publication.snapshot["switches"]["market_ignition"]["assessment"] is None
    assert publication.snapshot["switches"]["fundamental_exit"]["assessment"] is None
    assert publication.snapshot["overall_assessment"] == publication.snapshot["switches"]["liquidity_fuel"]["assessment"]
    assert publication.snapshot["metrics"][
        "sec_form4_nonderivative_ps_count_ratio_20d"
    ]["value"] is None

    event_rows = publication.events["events"]
    settlement = next(row for row in event_rows if row["date"] == "2026-08-12")
    assert settlement["treasury_settlement_usd_bn"] == 50.0
    assert any("MONTH_END" in row["flags"] for row in event_rows)


def test_incomplete_sec_form4_attempt_preserves_last_good_metric_and_ledger(tmp_path):
    data_dir = tmp_path / "data"
    initial = build_release(
        data_dir=data_dir,
        now=NOW,
        collectors=fixture_collectors(),
    )
    stage = tmp_path / "initial-stage"
    write_stage(initial, stage)
    promote_stage(stage, data_dir=data_dir)

    base = fixture_collectors()

    def failed_sec_form4(**_kwargs):
        return Form4Collection(
            filings=(),
            reused_ledger_accessions=(),
            master_accessions_by_day={},
            completed_index_days=(),
            discovered_index_days=("2026-08-12",),
            failures=(
                {
                    "index_date": "2026-08-12",
                    "stage": "SUBMISSION",
                    "reason": "fixture transient failure",
                },
            ),
            reviews=(),
            source_requests=1,
        )

    failed = build_release(
        mode="incremental",
        group="daily",
        data_dir=data_dir,
        now=NOW + timedelta(days=1),
        collectors=replace(base, sec_form4=failed_sec_form4),
    )
    metric = failed.snapshot["metrics"][
        "sec_form4_nonderivative_ps_count_ratio_20d"
    ]
    assert metric["quality"]["status"] == "STALE"
    assert metric["quality"]["last_success_at"] == initial.snapshot["generated_at"]
    assert metric["quality"]["last_attempt_at"] == "2026-08-13T20:00:00Z"
    assert "fixture transient failure" in metric["quality"]["failure_reason"]
    assert failed.sec_form4_ledger == initial.sec_form4_ledger


def test_failed_fred_fetch_preserves_last_good_and_redacts_api_key(tmp_path, monkeypatch):
    old = tmp_path / "data"
    (old / "series").mkdir(parents=True)
    stamp = "2026-08-11T20:00:00Z"
    (old / "snapshot.json").write_text(
        json.dumps({"schema_version": "2.3.0", "generated_at": stamp, "pipeline_updated_at": stamp})
    )
    (old / "series" / "iorb.json").write_text(
        json.dumps(
            {
                "observations": [{"date": "2026-07-30", "value": 3.5}],
                "quality": {
                    "status": "OK",
                    "freshness": "FRESH",
                    "last_success_at": stamp,
                    "last_attempt_at": stamp,
                    "failure_reason": None,
                },
                "updated_at": stamp,
            }
        )
    )
    secret = "a" * 32
    monkeypatch.setenv("FRED_API_KEY", secret)
    publication = build_release(
        mode="incremental",
        group="daily",
        data_dir=old,
        now=NOW,
        collectors=fixture_collectors(
            fred_error=RuntimeError(f"HTTP 500 api_key={secret}&series_id=IORB")
        ),
    )

    quality = publication.snapshot["metrics"]["iorb"]["quality"]
    assert publication.snapshot["metrics"]["iorb"]["value"] == 3.5
    assert quality["status"] == "STALE"
    assert quality["last_success_at"] == stamp
    assert quality["last_attempt_at"] == "2026-08-12T20:00:00Z"
    assert secret not in quality["failure_reason"]
    assert "api_key=<redacted>" in quality["failure_reason"]
    liquidity_switch = publication.snapshot["switches"]["liquidity_fuel"]
    assert liquidity_switch["assessment"] == "UNAVAILABLE"
    assert liquidity_switch["confidence"] == "LOW"
    assert publication.snapshot["overall_assessment"] == "UNAVAILABLE"
    explanation = publication.snapshot["explanations"]["bullets"][0]
    assert "最後成功觀察值" in explanation["observation"]
    assert "並非今日新值" in explanation["observation"]
    assert "last-good" in explanation["meaning"]
    assert next(
        block
        for block in liquidity_switch["evidence_blocks"]
        if block["id"] == "funding_price"
    )["available"] is False
    for block in liquidity_switch["evidence_blocks"]:
        if block["available"] is False:
            assert block["status"] == "UNAVAILABLE"
    validate_publication(
        publication.snapshot, publication.manifest, publication.series_by_id
    )


def test_future_effective_iorb_is_hidden_until_new_york_observation_date(tmp_path):
    base = fixture_collectors()

    def fred(series_id, **kwargs):
        if series_id == "IORB":
            return [
                {"date": "2026-07-30", "value": 3.5},
                {"date": "2026-08-13", "value": 3.75},
            ]
        return base.fred(series_id, **kwargs)

    collectors = replace(base, fred=fred)
    before_effective = build_release(
        data_dir=tmp_path / "before",
        now=datetime(2026, 8, 12, 20, tzinfo=timezone.utc),
        collectors=collectors,
    )
    before_iorb = before_effective.snapshot["metrics"]["iorb"]
    assert before_iorb["observation_date"] == "2026-07-30"
    assert before_iorb["value"] == 3.5
    assert before_iorb["quality"]["status"] == "OK"
    assert before_effective.snapshot["metrics"]["sofr_iorb_spread_bp"][
        "quality"
    ]["status"] == "OK"
    assert before_effective.series_by_id["iorb"]["observations"][-1]["date"] == "2026-07-30"

    on_effective_date = build_release(
        data_dir=tmp_path / "after",
        now=datetime(2026, 8, 13, 14, tzinfo=timezone.utc),
        collectors=collectors,
    )
    assert on_effective_date.snapshot["metrics"]["iorb"]["observation_date"] == "2026-08-13"
    assert on_effective_date.snapshot["metrics"]["iorb"]["value"] == 3.75


def test_future_only_fred_response_and_polluted_last_good_fail_closed(tmp_path):
    base = fixture_collectors()

    def all_future_iorb(series_id, **kwargs):
        if series_id == "IORB":
            return [{"date": "2026-08-13", "value": 3.75}]
        return base.fred(series_id, **kwargs)

    no_prior = build_release(
        data_dir=tmp_path / "empty",
        now=NOW,
        collectors=replace(base, fred=all_future_iorb),
    )
    iorb = no_prior.snapshot["metrics"]["iorb"]
    assert iorb["value"] is None
    assert iorb["observation_date"] is None
    assert iorb["quality"]["status"] == "ERROR"
    assert "no observations effective on or before 2026-08-12" in iorb["quality"][
        "failure_reason"
    ]

    polluted = tmp_path / "polluted"
    (polluted / "series").mkdir(parents=True)
    (polluted / "series" / "iorb.json").write_text(
        json.dumps(
            {
                "observations": [
                    {"date": "2026-07-30", "value": 3.5},
                    {"date": "2026-08-13", "value": 3.75},
                ],
                "quality": {
                    "status": "ERROR",
                    "freshness": "UNKNOWN",
                    "last_success_at": "2026-08-12T20:00:00Z",
                    "last_attempt_at": "2026-08-12T20:00:00Z",
                    "failure_reason": None,
                },
            }
        )
    )
    recovered = build_release(
        data_dir=polluted,
        now=NOW,
        collectors=replace(base, fred=all_future_iorb),
    )
    recovered_series = recovered.series_by_id["iorb"]["observations"]
    assert recovered_series[-1] == {"date": "2026-07-30", "value": 3.5}
    assert recovered.snapshot["metrics"]["iorb"]["quality"]["status"] == "STALE"
    assert all(point["date"] <= "2026-08-12" for point in recovered_series)

    unattempted = build_release(
        group="monthly",
        data_dir=polluted,
        now=NOW,
        collectors=base,
    )
    assert unattempted.series_by_id["iorb"]["observations"][-1] == {
        "date": "2026-07-30",
        "value": 3.5,
    }
    assert unattempted.snapshot["metrics"]["iorb"]["quality"]["status"] == "OK"


@pytest.mark.parametrize(
    ("status", "quality_note"),
    (("STALE", "資料已過期"), ("NOT_RELEASED_YET", "今期尚未發布")),
)
def test_explanation_never_presents_non_ok_last_good_as_today(status, quality_note):
    explanation = _explanation(
        "UNAVAILABLE",
        "LOW",
        {"latest": 1.25},
        {"status": status},
        {"funding_confirmation_count": 0},
        [],
    )["bullets"][0]

    assert explanation["observation"].startswith(
        "SOFR−IORB 最後成功觀察值為 +1.2 bp"
    )
    assert quality_note in explanation["observation"]
    assert "並非今日新值" in explanation["observation"]
    assert "最新為" not in explanation["observation"]
    assert "last-good" in explanation["meaning"]


def test_stale_reserves_fail_closed_without_hiding_fresh_evidence_coverage(tmp_path):
    old = tmp_path / "data"
    (old / "series").mkdir(parents=True)
    stamp = "2026-08-11T20:00:00Z"
    (old / "snapshot.json").write_text(
        json.dumps(
            {
                "schema_version": "2.3.0",
                "generated_at": stamp,
                "pipeline_updated_at": stamp,
            }
        )
    )
    (old / "series" / "reserve_balances.json").write_text(
        json.dumps(
            {
                "observations": [
                    {"date": "2026-07-23", "value": 3_100.0},
                    {"date": "2026-07-30", "value": 3_090.0},
                ],
                "quality": {
                    "status": "OK",
                    "freshness": "FRESH",
                    "last_success_at": stamp,
                    "last_attempt_at": stamp,
                    "failure_reason": None,
                },
                "updated_at": stamp,
            }
        )
    )

    publication = build_release(
        data_dir=old,
        now=NOW,
        collectors=fixture_collectors(
            fred_errors_by_series={"WRESBAL": RuntimeError("H.4.1 unavailable")}
        ),
    )

    liquidity_switch = publication.snapshot["switches"]["liquidity_fuel"]
    blocks = {block["id"]: block for block in liquidity_switch["evidence_blocks"]}
    assert liquidity_switch["assessment"] == "UNAVAILABLE"
    assert liquidity_switch["confidence"] == "LOW"
    assert liquidity_switch["available_blocks"] == 3
    assert blocks["funding_price"]["available"] is True
    assert blocks["reserve_quantity"]["available"] is False
    assert blocks["reserve_quantity"]["triggered"] is None
    assert blocks["reserve_quantity"]["status"] == "UNAVAILABLE"


def test_stage_only_then_cross_parent_promotion_removes_v1_aliases(tmp_path):
    output = tmp_path / "workspace" / "public" / "data"
    output.mkdir(parents=True)
    (output / "old-v1-alias.json").write_text("legacy")
    (output / "series").mkdir()
    retired_cftc_files = (
        "cftc_asset_manager_positioning.json",
        "cftc_leveraged_funds_positioning_proxy.json",
    )
    for filename in retired_cftc_files:
        (output / "series" / filename).write_text("legacy")
    stage = tmp_path / "runner-temp" / "candidate"
    publication = build_release(
        data_dir=output,
        now=NOW,
        collectors=fixture_collectors(),
    )

    write_stage(publication, stage)
    loaded = load_stage(stage)
    assert set(loaded.series_by_id) == {
        metric["metric_id"] for metric in loaded.manifest["metrics"]
    }
    assert "sofr_iorb_spread" not in loaded.series_by_id
    promote_stage(stage, data_dir=output)

    assert not stage.exists()
    assert not (output / "old-v1-alias.json").exists()
    assert json.loads((output / "snapshot.json").read_text())["schema_version"] == "2.3.0"
    assert not (output / "series" / "sofr_iorb_spread.json").exists()
    assert all(not (output / "series" / filename).exists() for filename in retired_cftc_files)


def test_load_stage_rejects_tampered_alerts_and_events(tmp_path):
    publication = build_release(
        data_dir=tmp_path / "last-good",
        now=NOW,
        collectors=fixture_collectors(),
    )
    alerts_stage = write_stage(publication, tmp_path / "alerts-stage")
    (alerts_stage / "alerts.json").write_text(json.dumps({"garbage": True}))
    with pytest.raises(Exception, match="schema_version"):
        load_stage(alerts_stage)

    events_stage = write_stage(publication, tmp_path / "events-stage")
    (events_stage / "events.json").write_text(
        json.dumps(
            {
                    "schema_version": "2.3.0",
                "generated_at": publication.snapshot["generated_at"],
                "events": "not-a-list",
            }
        )
    )
    with pytest.raises(Exception, match="events must be a list"):
        load_stage(events_stage)

    extra_stage = write_stage(publication, tmp_path / "extra-series-stage")
    (extra_stage / "series" / "unexpected.bin").write_bytes(b"not part of v2")
    with pytest.raises(Exception, match="unexpected series files"):
        load_stage(extra_stage)


def test_unattempted_series_recomputes_freshness_instead_of_trusting_prior_flags(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "series").mkdir(parents=True)
    (data_dir / "series" / "reserve_balances.json").write_text(
        json.dumps(
            {
                "observations": [{"date": "2026-01-01", "value": 3_000.0}],
                "quality": {
                    "status": "OK",
                    "freshness": "FRESH",
                    "last_success_at": "2026-01-02T00:00:00Z",
                    "last_attempt_at": "2026-01-02T00:00:00Z",
                    "failure_reason": None,
                },
            }
        )
    )

    state = _preserved_state(
        "reserve_balances",
        data_dir=data_dir,
        frequency="weekly",
        attempted_at="2026-08-12T20:00:00Z",
        now_et=NOW.astimezone(NEW_YORK),
    )

    assert state.health == "STALE"
    assert state.freshness == "STALE"


def test_h41_missing_current_release_is_not_released_yet_then_becomes_stale():
    thursday = datetime(2026, 8, 13, 18, tzinfo=NEW_YORK)
    assert h41_freshness_for("2026-08-05", now_et=thursday) == (
        "LATE",
        "NOT_RELEASED_YET",
    )
    assert h41_freshness_for("2026-08-12", now_et=thursday) == ("FRESH", "OK")
    assert h41_freshness_for("2026-07-22", now_et=thursday) == (
        "STALE",
        "STALE",
    )


def test_h41_build_marks_unchanged_thursday_response_not_released(tmp_path):
    thursday = datetime(2026, 8, 13, 22, tzinfo=timezone.utc)
    publication = build_release(
        group="h41",
        data_dir=tmp_path / "last-good",
        now=thursday,
        collectors=fixture_collectors(),
    )

    for metric_id in ("reserve_balances", "fed_total_assets", "tga_weekly_h41"):
        metric = publication.snapshot["metrics"][metric_id]
        assert metric["quality"]["status"] == "NOT_RELEASED_YET"
        assert metric["quality"]["freshness"] == "LATE"
    cftc_source = publication.snapshot["sources"]["cftc_tff_futures_only"]
    assert cftc_source["last_attempt_at"] is None
    assert cftc_source["updated_at"] is None
    for metric_id in (
        "cftc_e_mini_sp500_asset_manager_net_pct_oi",
        "cftc_e_mini_sp500_leveraged_funds_net_pct_oi",
        "cftc_nasdaq100_consolidated_asset_manager_net_pct_oi",
        "cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi",
    ):
        assert publication.snapshot["metrics"][metric_id]["quality"]["last_attempt_at"] is None
        assert publication.snapshot["metrics"][metric_id]["updated_at"] is None


def test_tax_window_flags_business_day_before_reviewed_deadline():
    events = _technical_events(
        load_config_bundle(),
        observation_calendar=["2026-09-11", "2026-09-14"],
        settlements=[],
    )
    tax_event = next(event for event in events if event["date"] == "2026-09-14")
    assert tax_event["flags"] == ["TAX_WINDOW"]
    assert tax_event["deadlines"] == ["2026-09-15->2026-09-15"]


def test_latest_observation_is_period_end_after_new_york_crosses_boundary():
    events = _technical_events(
        load_config_bundle(),
        observation_calendar=["2026-08-28", "2026-08-31"],
        settlements=[],
        current_new_york_date=datetime(2026, 9, 1, tzinfo=NEW_YORK).date(),
    )
    event = next(row for row in events if row["date"] == "2026-08-31")
    assert event["flags"] == ["MONTH_END"]

    labor_day = _technical_events(
        load_config_bundle(),
        observation_calendar=["2025-08-28", "2025-08-29"],
        settlements=[],
        current_new_york_date=datetime(2025, 9, 2, tzinfo=NEW_YORK).date(),
    )
    labor_day_event = next(
        row for row in labor_day if row["date"] == "2025-08-29"
    )
    assert labor_day_event["flags"] == ["MONTH_END"]

    stale_midmonth = _technical_events(
        load_config_bundle(),
        observation_calendar=["2026-01-15"],
        settlements=[],
        current_new_york_date=datetime(2026, 8, 12, tzinfo=NEW_YORK).date(),
    )
    assert not any(
        flag in {"MONTH_END", "QUARTER_END", "YEAR_END"}
        for row in stale_midmonth
        for flag in row["flags"]
    )


def test_release_builder_downgrades_confidence_for_just_closed_period_end(tmp_path):
    base = fixture_collectors()

    def rate(metric_id, **_kwargs):
        offsets = {"sofr": 0.02, "effr": 0.01, "obfr": 0.0, "tgcr": 0.01, "bgcr": 0.01}
        return business_points(
            datetime(2026, 7, 1, tzinfo=timezone.utc),
            62,
            3.5 + offsets[metric_id],
        )

    def fred(series_id, **_kwargs):
        if series_id == "IORB":
            return [
                {"date": "2026-07-01", "value": 3.5},
                {"date": "2026-08-31", "value": 3.5},
            ]
        return [
            {
                "date": (
                    datetime(2026, 7, 15, tzinfo=timezone.utc)
                    + timedelta(days=7 * index)
                ).date().isoformat(),
                "value": 3_100.0 - index,
            }
            for index in range(7)
        ]

    collectors = replace(
        base,
        rate=rate,
        fred=fred,
        on_rrp=lambda **_kwargs: [
            {"date": "2026-08-31", "value": 0.7, "submitted_usd_bn": 0.7}
        ],
        srf_operations=lambda **_kwargs: [
            {
                "operation_id": "RP 083126 REGULAR",
                "operation_date": "2026-08-31",
                "collateral_type": "treasury",
                "submitted_amount_usd_bn": 0.0,
                "accepted_amount_usd_bn": 0.0,
                "rate_pct": 4.5,
                "released_at": "2026-08-31T18:00:00Z",
            }
        ],
        tga=lambda **_kwargs: [
            {"date": "2026-08-31", "value": 900.0, "source_field": "open_today_bal"}
        ],
        auctions=lambda **_kwargs: [
            {
                "cusip": "912797ZZ1",
                "auction_date": "2026-08-26",
                "issue_date": "2026-08-28",
                "offering_usd_bn": 50.0,
            }
        ],
    )

    before_boundary = build_release(
        data_dir=tmp_path / "before",
        now=datetime(2026, 8, 31, 20, tzinfo=timezone.utc),
        collectors=collectors,
    )
    after_boundary = build_release(
        data_dir=tmp_path / "after",
        now=datetime(2026, 9, 1, 14, tzinfo=timezone.utc),
        collectors=collectors,
    )

    assert before_boundary.snapshot["switches"]["liquidity_fuel"]["confidence"] == "HIGH"
    assert after_boundary.snapshot["switches"]["liquidity_fuel"]["confidence"] == "MEDIUM"
    event = next(
        item
        for item in after_boundary.snapshot["technical_context"]
        if item["date"] == "2026-08-31"
    )
    assert "MONTH_END" in event["flags"]
