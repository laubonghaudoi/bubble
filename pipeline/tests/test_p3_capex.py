from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from pipeline.collectors.common import CollectorError
from pipeline.collectors.sec_companyfacts import (
    COMPANY_FACTS_URL,
    SUBMISSIONS_URL,
    fetch_company_bundle,
    fetch_company_bundles,
    parse_company_bundle,
    parse_company_facts,
    parse_submissions,
)
from pipeline.config import load_config_bundle
from pipeline.transforms.p3_capex import (
    ACCELERATION_METRIC_ID,
    CAPEX_METRIC_ID,
    aggregate_hyperscaler_cash_capex,
    build_hyperscaler_capex,
    quarterize_company_cash_capex,
)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def companies():
    return load_config_bundle().companies["companies"]


def company(company_id: str):
    return next(item for item in companies() if item["company_id"] == company_id)


def microsoft_bundle():
    return parse_company_bundle(
        fixture("sec_companyfacts_capex.json"),
        fixture("sec_submissions_capex.json"),
        company=company("microsoft"),
    )


def test_company_registry_locks_current_amazon_tag_and_separate_finance_lease_tag():
    registry = {item["company_id"]: item for item in companies()}
    assert registry["amazon"]["preferred_xbrl_tags"] == [
        "PaymentsToAcquireProductiveAssets"
    ]
    assert all(item["xbrl_namespace"] == "us-gaap" for item in registry.values())
    assert all(
        item["finance_lease_xbrl_tags"]
        == ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"]
        for item in registry.values()
    )


def test_companyfacts_parser_uses_reviewed_identity_units_and_supported_forms_only():
    parsed = parse_company_facts(
        fixture("sec_companyfacts_capex.json"), company=company("microsoft")
    )
    assert parsed["company_id"] == "microsoft"
    assert parsed["cash_capex_tag"] == "PaymentsToAcquirePropertyPlantAndEquipment"
    assert len(parsed["cash_capex_facts"]) == 13
    assert {point["form"] for point in parsed["cash_capex_facts"]} == {
        "10-K",
        "10-Q",
        "10-Q/A",
    }
    assert parsed["cash_capex_facts"][-1]["unit"] == "USD"
    assert len(parsed["finance_lease_facts"]) == 4


def test_submissions_join_preserves_acceptance_and_official_filing_url():
    bundle = microsoft_bundle()
    amended = next(
        point
        for point in bundle["cash_capex_facts"]
        if point["accession"] == "0000789019-25-000106"
    )
    assert amended["accepted_at"] == "2025-02-03T20:06:07Z"
    assert amended["filing_url"] == (
        "https://www.sec.gov/Archives/edgar/data/789019/"
        "000078901925000106/msft-20241231a.htm"
    )
    assert bundle["submission_count"] == 13


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.__setitem__("cik", 1), "CIK mismatch"),
        (
            lambda payload: payload["facts"]["us-gaap"]
            ["PaymentsToAcquirePropertyPlantAndEquipment"]["units"].__setitem__(
                "shares", []
            ),
            "units must be exactly USD",
        ),
        (
            lambda payload: payload["facts"]["us-gaap"]
            ["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"][0].__setitem__(
                "val", -1
            ),
            "non-negative",
        ),
        (
            lambda payload: payload["facts"]["us-gaap"]
            ["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"][0].__setitem__(
                "end", "2023-02-30"
            ),
            "ISO date",
        ),
    ],
)
def test_companyfacts_identity_unit_value_and_date_drift_fail_closed(mutation, message):
    payload = fixture("sec_companyfacts_capex.json")
    mutation(payload)
    with pytest.raises(CollectorError, match=message):
        parse_company_facts(payload, company=company("microsoft"))


def test_companyfacts_conflicting_duplicate_fails_closed_but_exact_duplicate_is_idempotent():
    payload = fixture("sec_companyfacts_capex.json")
    rows = payload["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"][
        "units"
    ]["USD"]
    rows.append(deepcopy(rows[0]))
    assert (
        len(
            parse_company_facts(payload, company=company("microsoft"))[
                "cash_capex_facts"
            ]
        )
        == 13
    )
    rows[-1]["val"] += 1
    with pytest.raises(CollectorError, match="conflicting duplicate"):
        parse_company_facts(payload, company=company("microsoft"))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload["filings"]["recent"]["form"].pop(),
            "different lengths",
        ),
        (
            lambda payload: payload["filings"]["recent"]["primaryDocument"].__setitem__(
                0, "../unsafe.htm"
            ),
            "safe filename",
        ),
        (
            lambda payload: payload["filings"]["recent"]["acceptanceDateTime"].__setitem__(
                0, "2023-10-24"
            ),
            "offset",
        ),
    ],
)
def test_submissions_schema_path_and_timestamp_drift_fail_closed(mutation, message):
    payload = fixture("sec_submissions_capex.json")
    mutation(payload)
    with pytest.raises(CollectorError, match=message):
        parse_submissions(payload, company=company("microsoft"))


@pytest.mark.parametrize(
    "payload",
    [{}, "<html>blocked</html>", {"cik": 789019, "entityName": "MSFT"}],
)
def test_companyfacts_empty_html_and_schema_drift_fail_closed(payload):
    with pytest.raises(CollectorError):
        parse_company_facts(payload, company=company("microsoft"))


class _Limiter:
    def __init__(self):
        self.calls = 0

    def acquire(self):
        self.calls += 1


def test_fetch_uses_only_official_sec_data_endpoints_identifying_ua_and_no_key():
    facts = fixture("sec_companyfacts_capex.json")
    submissions = fixture("sec_submissions_capex.json")
    calls = []

    def fake_get(url, *, user_agent):
        calls.append((url, user_agent))
        return facts if "/companyfacts/" in url else submissions

    limiter = _Limiter()
    bundle = fetch_company_bundle(
        company("microsoft"),
        user_agent="Bubble tests tests@example.com",
        limiter=limiter,
        json_fetcher=fake_get,
    )
    assert bundle["company_id"] == "microsoft"
    assert limiter.calls == 2
    assert calls == [
        (COMPANY_FACTS_URL.format(cik="0000789019"), "Bubble tests tests@example.com"),
        (SUBMISSIONS_URL.format(cik="0000789019"), "Bubble tests tests@example.com"),
    ]
    assert all("key=" not in url.lower() for url, _ in calls)


def test_fetch_all_requires_four_unique_companies_and_rate_between_two_and_five():
    with pytest.raises(CollectorError, match="between 2 and 5"):
        fetch_company_bundles(companies(), rate_per_second=1.99)
    with pytest.raises(CollectorError, match="between 2 and 5"):
        fetch_company_bundles(companies(), rate_per_second=5.01)
    with pytest.raises(CollectorError, match="duplicate"):
        fetch_company_bundles(
            [company("microsoft")] * 4,
            json_fetcher=lambda *_args, **_kwargs: {},
        )


def test_quarterization_prefers_latest_amendment_and_deducts_h1_9m_and_q4():
    points = quarterize_company_cash_capex(microsoft_bundle())
    assert len(points) == 12
    fy2025 = {
        point["fiscal_quarter"]: point
        for point in points
        if "FY2025" in point["fiscal_quarter"]
    }
    assert fy2025["FY2025Q1"]["cash_capex_usd_bn"] == 14
    assert fy2025["FY2025Q2"]["cash_capex_usd_bn"] == 18
    assert fy2025["FY2025Q2"]["accession"] == "0000789019-25-000106"
    assert fy2025["FY2025Q2"]["quarterization_method"] == "H1_MINUS_Q1"
    assert fy2025["FY2025Q3"]["cash_capex_usd_bn"] == 18
    assert fy2025["FY2025Q3"]["quarterization_method"] == "9M_MINUS_H1"
    assert fy2025["FY2025Q4"]["cash_capex_usd_bn"] == 22
    assert fy2025["FY2025Q4"]["quarterization_method"] == "FY_MINUS_9M"
    latest = points[-1]
    assert latest["cash_capex_usd_bn"] == 34
    assert latest["finance_lease_additions_usd_bn"] == 4
    assert latest["finance_lease_quarterization_method"] == "FY_MINUS_9M"
    assert latest["cash_capex_usd_bn"] != latest["finance_lease_additions_usd_bn"]


def test_quarterization_requires_twelve_consecutive_quarters_and_complete_ytd_inputs():
    bundle = microsoft_bundle()
    bundle["cash_capex_facts"] = bundle["cash_capex_facts"][4:]
    with pytest.raises(CollectorError, match="at least 12 consecutive"):
        quarterize_company_cash_capex(bundle)

    bundle = microsoft_bundle()
    bundle["cash_capex_facts"] = [
        fact
        for fact in bundle["cash_capex_facts"]
        if not (fact["start"] == "2025-07-01" and fact["end"] == "2025-12-31")
    ]
    with pytest.raises(CollectorError, match="at least 12 consecutive"):
        quarterize_company_cash_capex(bundle)


def test_quarterization_keeps_missing_finance_lease_as_null_and_rejects_tag_drift():
    bundle = microsoft_bundle()
    bundle["finance_lease_facts"] = []
    points = quarterize_company_cash_capex(bundle)
    assert points[-1]["finance_lease_additions_usd_bn"] is None

    bundle = microsoft_bundle()
    bundle["cash_capex_facts"][-1]["tag"] = "WrongTag"
    with pytest.raises(CollectorError, match="identity or unit mismatch"):
        quarterize_company_cash_capex(bundle)


def test_quarterization_fails_closed_when_finance_lease_uses_another_filing():
    bundle = microsoft_bundle()
    bundle["finance_lease_facts"][-1]["accession"] = "0000789019-26-999999"
    points = quarterize_company_cash_capex(bundle)
    latest = points[-1]
    assert latest["finance_lease_additions_usd_bn"] is None
    assert latest["finance_lease_tag"] is None
    assert latest["finance_lease_accession"] is None
    assert latest["finance_lease_quarterization_method"] is None

def _aggregate_company_series():
    microsoft = quarterize_company_cash_capex(microsoft_bundle())
    output = {}
    for index, company_id in enumerate(("microsoft", "alphabet", "amazon", "meta"), start=1):
        output[company_id] = [
            {
                **point,
                "company_id": company_id,
                "ticker": company_id[:4].upper(),
                "cik": str(index).zfill(10),
                "cash_capex_usd_bn": point["cash_capex_usd_bn"] * index,
                "finance_lease_additions_usd_bn": (
                    point["finance_lease_additions_usd_bn"] * index
                    if point["finance_lease_additions_usd_bn"] is not None
                    else None
                ),
            }
            for point in microsoft
        ]
    return output


def test_aggregate_sums_dollars_before_growth_and_exposes_flat_numeric_statistics_shape():
    company_series = _aggregate_company_series()
    points = aggregate_hyperscaler_cash_capex(company_series)
    latest = points[-1]
    assert latest["aggregate_cash_capex_usd_bn"] == 340
    assert latest["value"] == 340
    expected_yoy = (340 / 220 - 1) * 100
    assert latest["yoy_percent_change"] == pytest.approx(expected_yoy, abs=1e-6)
    assert latest["company_total"] == 4
    assert latest["finance_lease_disclosure_breadth"] == 4
    assert [company["company_id"] for company in latest["companies"]] == [
        "alphabet",
        "amazon",
        "meta",
        "microsoft",
    ]


def _synthetic_bundle(company_config, multiplier):
    """Convert the compact Microsoft fixture into each fixed fiscal calendar."""

    fiscal_month = int(company_config["fiscal_year_end"][:2])
    facts = []
    finance = []
    years = (2024, 2025, 2026) if fiscal_month == 6 else (2023, 2024, 2025, 2026)
    for year in years:
        fiscal_end = date(year, fiscal_month, 1)
        fiscal_end = date(
            fiscal_end.year,
            fiscal_end.month,
            30 if fiscal_month in {4, 6, 9, 11} else 31,
        )
        fiscal_start = date(year - 1, fiscal_month, fiscal_end.day) + timedelta(days=1)
        cumulative = (
            [8, 18, 29, 42]
            if year == 2023
            else (
                [10, 22, 35, 50]
                if year == 2024
                else ([14, 32, 50, 72] if year == 2025 else [20, 45, 74, 108])
            )
        )
        finance_cumulative = [1, 3, 6, 10]
        for quarter in range(1, 5):
            months_back = (4 - quarter) * 3
            ordinal = fiscal_end.year * 12 + fiscal_end.month - 1 - months_back
            end_year, end_zero_month = divmod(ordinal, 12)
            end_month = end_zero_month + 1
            end_day = (
                30
                if end_month in {4, 6, 9, 11}
                else (
                    29
                    if end_month == 2 and end_year % 4 == 0
                    else (28 if end_month == 2 else 31)
                )
            )
            end = date(end_year, end_month, end_day)
            accession = f"{company_config['cik']}-{str(year)[-2:]}-{quarter:06d}"
            common = {
                "namespace": "us-gaap",
                "unit": "USD",
                "start": fiscal_start.isoformat(),
                "end": end.isoformat(),
                "accession": accession,
                "fiscal_year_filed": year,
                "fiscal_period_filed": "FY" if quarter == 4 else f"Q{quarter}",
                "form": "10-K" if quarter == 4 else "10-Q",
                "filed_at": (end + timedelta(days=30)).isoformat(),
                "frame": None,
                "accepted_at": f"{(end + timedelta(days=30)).isoformat()}T20:00:00Z",
                "report_date": end.isoformat(),
                "primary_document": "filing.htm",
                "filing_url": f"https://www.sec.gov/Archives/{accession}",
                "filing_metadata_missing": False,
            }
            facts.append(
                {
                    **common,
                    "tag": company_config["preferred_xbrl_tags"][0],
                    "value": cumulative[quarter - 1] * multiplier * 1_000_000_000,
                }
            )
            finance.append(
                {
                    **common,
                    "tag": company_config["finance_lease_xbrl_tags"][0],
                    "value": finance_cumulative[quarter - 1] * multiplier * 1_000_000_000,
                }
            )
    return {
        "company_id": company_config["company_id"],
        "ticker": company_config["ticker"],
        "cik": company_config["cik"],
        "fiscal_year_end": company_config["fiscal_year_end"],
        "cash_capex_tag": company_config["preferred_xbrl_tags"][0],
        "cash_capex_facts": facts,
        "finance_lease_facts": finance,
    }


def test_build_exposes_two_locked_metrics_series_point_provenance_and_details():
    bundles = {
        item["company_id"]: _synthetic_bundle(item, index)
        for index, item in enumerate(companies(), start=1)
    }
    result = build_hyperscaler_capex(bundles)
    assert result["metric_id"] == CAPEX_METRIC_ID
    assert result["acceleration_metric_id"] == ACCELERATION_METRIC_ID
    assert result["unit"] == "USD bn"
    assert result["acceleration_unit"] == "percentage_points"
    assert len(result["series"]) == 12
    assert result["acceleration_series"][-1]["value"] == result["series"][-1][
        "yoy_acceleration_pp"
    ]
    assert all(
        value is None or isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in result["statistics"].values()
    )
    assert set(result["statistics"]) == {
        "aggregate_cash_capex_usd_bn",
        "qoq_percent_change",
        "yoy_percent_change",
        "qoq_acceleration_pp",
        "yoy_acceleration_pp",
        "company_breadth",
        "company_total",
        "company_breadth_ratio",
        "finance_lease_disclosure_breadth",
        "manual_review_count",
        "quarter_count",
    }
    details = result["details"]["fundamental"]
    assert details["company_total"] == 4
    assert len(details["companies"]) == 4
    assert all(
        company["filing_url"].startswith("https://www.sec.gov/")
        for company in details["companies"]
    )
    methods = {
        item["company_id"]: item["quarterization_method"]
        for item in details["companies"]
    }
    assert methods == {
        "alphabet": "H1_MINUS_Q1",
        "amazon": "H1_MINUS_Q1",
        "meta": "H1_MINUS_Q1",
        "microsoft": "FY_MINUS_9M",
    }
    assert all(
        company["finance_lease_additions_usd_bn"] is not None
        for company in details["companies"]
    )
