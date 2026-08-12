import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from pipeline.collectors.common import CollectorError
from pipeline.collectors.fred import fetch_series, parse_observations
from pipeline.collectors.nyfed import normalized_srf_operations, parse_on_rrp, parse_reference_rates, parse_srf
from pipeline.collectors.treasury import parse_auctions, parse_tga


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_nyfed_rate_parser_deduplicates_dates():
    assert parse_reference_rates(fixture("nyfed_rates.json"), expected_type="sofr") == [
        {"date": "2026-08-10", "value": 3.63},
        {"date": "2026-08-11", "value": 3.64},
    ]


def test_on_rrp_aggregates_accepted_amount():
    row = parse_on_rrp(fixture("nyfed_on_rrp.json"))[0]
    assert row["value"] == 0.75
    assert row["submitted_usd_bn"] == 0.75
    assert row["source_total_amt_accepted"] == 750_000_000
    assert row["source_total_amt_submitted"] == 750_000_000
    assert row["source_amount_unit"] == "USD"
    assert row["operation_count"] == 2


def test_srf_preserves_zero_and_marks_only_allowlisted_exercises():
    row = parse_srf(
        fixture("nyfed_srf.json"),
        operational_readiness_operation_ids={"SRF AM"},
    )[0]
    assert row["value"] == 2.5
    assert row["has_technical_exercise"] is True
    assert row["technical_exercise"] is False
    assert row["breakdown"]["Treasury"]["accepted_usd_bn"] == 2.0

    zero = fixture("nyfed_srf.json")
    for operation in zero["repo"]["operations"]:
        operation["totalAmtAccepted"] = 0
        for detail in operation["details"]:
            detail["amtAccepted"] = 0
    assert parse_srf(zero)[0]["value"] == 0


def test_srf_collector_flattens_collateral_rows_for_transform_layer():
    rows = normalized_srf_operations(fixture("nyfed_srf.json"))
    assert len(rows) == 4
    assert {row["collateral_type"] for row in rows} == {
        "treasury", "agency_debt", "agency_mbs",
    }
    assert sum(row["accepted_amount_usd_bn"] for row in rows) == 2.5


def test_fred_parser_scales_and_deduplicates_and_requires_api_key(monkeypatch):
    assert parse_observations(fixture("fred_observations.json"), scale=1000)[-1] == {
        "date": "2026-08-12",
        "value": 3000.0,
    }
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(CollectorError, match="FRED_API_KEY is required"):
        fetch_series("WRESBAL", observation_start=__import__("datetime").date(2020, 1, 1))


def test_fred_observation_end_excludes_future_effective_values(monkeypatch):
    payload = fixture("fred_observations.json")
    payload["observations"].append({"date": "2026-08-13", "value": "3100000"})

    assert parse_observations(
        payload,
        scale=1000,
        observation_end=date(2026, 8, 12),
    )[-1] == {"date": "2026-08-12", "value": 3000.0}

    captured: dict[str, str] = {}

    def get_json(url, *, user_agent):
        captured["url"] = url
        captured["user_agent"] = user_agent
        return payload

    monkeypatch.setattr("pipeline.collectors.fred.get_json", get_json)
    observations = fetch_series(
        "IORB",
        observation_start=date(2026, 8, 1),
        observation_end=date(2026, 8, 12),
        scale=1000,
        api_key="a" * 32,
    )
    query = parse_qs(urlparse(captured["url"]).query)
    assert query["observation_end"] == ["2026-08-12"]
    assert observations[-1]["date"] == "2026-08-12"


def test_fred_all_future_or_empty_through_cutoff_fails_closed():
    with pytest.raises(
        CollectorError,
        match="no usable observations on or before 2026-08-12",
    ):
        parse_observations(
            {"observations": [{"date": "2026-08-13", "value": "3.5"}]},
            observation_end=date(2026, 8, 12),
        )

    with pytest.raises(CollectorError, match="missing non-empty observations"):
        parse_observations(
            {"observations": []},
            observation_end=date(2026, 8, 12),
        )


def test_tga_uses_audited_closing_balance_row_mapping():
    assert parse_tga(fixture("treasury_tga.json")) == [
        {
            "date": "2026-08-10",
            "value": 966.851,
            "source_field": "open_today_bal",
        }
    ]


def test_auction_parser_deduplicates_composite_key():
    rows = parse_auctions(fixture("treasury_auctions.json"))
    assert len(rows) == 1
    assert rows[0]["offering_usd_bn"] == 72


def test_date_and_composite_key_duplicates_fail_closed_on_conflicts():
    fred = fixture("fred_observations.json")
    fred["observations"].append({"date": "2026-08-12", "value": "3000001"})
    with pytest.raises(CollectorError, match="conflicting duplicate FRED"):
        parse_observations(fred, scale=1000)

    rates = fixture("nyfed_rates.json")
    rates["refRates"].append(
        {"effectiveDate": "2026-08-11", "type": "SOFR", "percentRate": 3.65}
    )
    with pytest.raises(CollectorError, match="conflicting duplicate NY Fed"):
        parse_reference_rates(rates, expected_type="SOFR")

    wrong_rate = fixture("nyfed_rates.json")
    wrong_rate["refRates"][0]["type"] = "EFFR"
    with pytest.raises(CollectorError, match="row type must be SOFR"):
        parse_reference_rates(wrong_rate, expected_type="SOFR")

    tga = fixture("treasury_tga.json")
    conflicting_tga = deepcopy(tga["data"][0])
    conflicting_tga["open_today_bal"] = "966852"
    tga["data"].append(conflicting_tga)
    with pytest.raises(CollectorError, match="conflicting duplicate FiscalData TGA"):
        parse_tga(tga)

    auctions = fixture("treasury_auctions.json")
    auctions["data"][-1]["offering_amt"] = "71000000000"
    with pytest.raises(CollectorError, match="conflicting duplicate FiscalData auction"):
        parse_auctions(auctions)


def test_exact_duplicate_observations_and_operations_are_counted_once():
    fred = fixture("fred_observations.json")
    fred["observations"].append(
        {"date": "2026-08-12", "value": "3000000"}
    )
    assert len(parse_observations(fred, scale=1000)) == 2

    on_rrp = fixture("nyfed_on_rrp.json")
    on_rrp["repo"]["operations"].append(
        deepcopy(on_rrp["repo"]["operations"][0])
    )
    assert parse_on_rrp(on_rrp)[0]["operation_count"] == 2

    srf = fixture("nyfed_srf.json")
    srf["repo"]["operations"].append(
        deepcopy(srf["repo"]["operations"][0])
    )
    assert parse_srf(srf)[0]["operation_count"] == 2
    assert len(normalized_srf_operations(srf)) == 4


def test_on_rrp_operation_identity_fallback_dedupes_but_ambiguous_rows_fail():
    payload = fixture("nyfed_on_rrp.json")
    operation = payload["repo"]["operations"][0]
    operation.pop("operationId")
    payload["repo"]["operations"].append(deepcopy(operation))
    assert parse_on_rrp(payload)[0]["operation_count"] == 2

    operation.pop("lastUpdated")
    with pytest.raises(CollectorError, match="defensible lastUpdated fallback"):
        parse_on_rrp(payload)


def test_nyfed_conflicting_operations_and_invalid_amount_domains_fail_closed():
    on_rrp = fixture("nyfed_on_rrp.json")
    conflicting = deepcopy(on_rrp["repo"]["operations"][0])
    conflicting["totalAmtAccepted"] = 400_000_000
    on_rrp["repo"]["operations"].append(conflicting)
    with pytest.raises(CollectorError, match="conflicting duplicate ON RRP"):
        parse_on_rrp(on_rrp)

    invalid_on_rrp = fixture("nyfed_on_rrp.json")
    invalid_on_rrp["repo"]["operations"][0]["totalAmtAccepted"] = 500_000_001
    with pytest.raises(CollectorError, match="0 <= accepted <= submitted"):
        parse_on_rrp(invalid_on_rrp)

    invalid_srf = fixture("nyfed_srf.json")
    invalid_srf["repo"]["operations"][0]["details"][0]["amtAccepted"] = -1
    with pytest.raises(CollectorError, match="0 <= accepted <= submitted"):
        normalized_srf_operations(invalid_srf)

    mismatched_srf = fixture("nyfed_srf.json")
    mismatched_srf["repo"]["operations"][0]["totalAmtAccepted"] = 1_900_000_000
    with pytest.raises(CollectorError, match="must equal top-level totals"):
        normalized_srf_operations(mismatched_srf)

    conflicting_detail = fixture("nyfed_srf.json")
    detail = deepcopy(conflicting_detail["repo"]["operations"][0]["details"][0])
    detail["amtAccepted"] = 1_000_000_000
    conflicting_detail["repo"]["operations"][0]["details"].append(detail)
    with pytest.raises(CollectorError, match="conflicting duplicate SRF detail"):
        normalized_srf_operations(conflicting_detail)


@pytest.mark.parametrize(
    "parser,payload",
    [
        (lambda payload: parse_reference_rates(payload, expected_type="SOFR"), {"refRates": []}),
        (parse_on_rrp, {"repo": {"operations": []}}),
        (parse_tga, {"data": []}),
        (parse_auctions, {"data": []}),
    ],
)
def test_empty_success_responses_fail_closed(parser, payload):
    with pytest.raises(CollectorError):
        parser(payload)
