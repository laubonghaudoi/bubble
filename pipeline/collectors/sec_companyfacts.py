"""Strict SEC Company Facts collector for P3 hyperscaler cash CapEx.

Company Facts is the numeric source.  The corresponding submissions feed is
joined by accession so every retained fact has an accepted timestamp and an
official filing URL.  This module deliberately does not quarterize cumulative
cash-flow facts; that pure transformation lives in
``pipeline.transforms.p3_capex``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from math import isfinite
import os
import re
from typing import Any

from .common import CollectorError, DEFAULT_USER_AGENT, as_iso_utc, get_json
from .sec_form4 import SerializedTokenBucket


SEC_DATA_ROOT = "https://data.sec.gov"
COMPANY_FACTS_URL = f"{SEC_DATA_ROOT}/api/xbrl/companyfacts/CIK{{cik}}.json"
SUBMISSIONS_URL = f"{SEC_DATA_ROOT}/submissions/CIK{{cik}}.json"
SUPPORTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
PRIMARY_DOCUMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EXPECTED_CASH_CAPEX_TAGS = {
    "microsoft": "PaymentsToAcquirePropertyPlantAndEquipment",
    "alphabet": "PaymentsToAcquirePropertyPlantAndEquipment",
    "amazon": "PaymentsToAcquireProductiveAssets",
    "meta": "PaymentsToAcquirePropertyPlantAndEquipment",
}
EXPECTED_COMPANY_IDENTITIES = {
    "microsoft": ("0000789019", "MSFT", "06-30"),
    "alphabet": ("0001652044", "GOOGL", "12-31"),
    "amazon": ("0001018724", "AMZN", "12-31"),
    "meta": ("0001326801", "META", "12-31"),
}
FINANCE_LEASE_ADDITIONS_TAG = (
    "RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"
)


def _iso_date(value: Any, *, field: str, allow_empty: bool = False) -> str | None:
    if allow_empty and value in (None, ""):
        return None
    if not isinstance(value, str):
        raise CollectorError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CollectorError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise CollectorError(f"{field} must be an ISO date")
    return value


def _nonempty(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectorError(f"{field} must be a non-empty string")
    return value


def _company_identity(company: Mapping[str, Any]) -> dict[str, str]:
    company_id = _nonempty(company.get("company_id"), field="company.company_id")
    cik = company.get("cik")
    if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit():
        raise CollectorError("company.cik must be a 10-digit string")
    expected_tag = EXPECTED_CASH_CAPEX_TAGS.get(company_id)
    if expected_tag is None:
        raise CollectorError(f"unsupported P3 company: {company_id}")
    expected_cik, expected_ticker, expected_fye = EXPECTED_COMPANY_IDENTITIES[
        company_id
    ]
    if cik != expected_cik:
        raise CollectorError(f"{company_id} CIK must be exactly {expected_cik}")
    if company.get("ticker") != expected_ticker:
        raise CollectorError(f"{company_id} ticker must be exactly {expected_ticker}")
    if company.get("fiscal_year_end") != expected_fye:
        raise CollectorError(
            f"{company_id} fiscal year end must be exactly {expected_fye}"
        )
    preferred = company.get("preferred_xbrl_tags")
    if preferred != [expected_tag]:
        raise CollectorError(
            f"{company_id} cash CapEx tag must be exactly {expected_tag}"
        )
    if company.get("fallback_xbrl_tags") != []:
        raise CollectorError(f"{company_id} fallback cash CapEx tags are not reviewed")
    if company.get("xbrl_namespace") != "us-gaap":
        raise CollectorError(f"{company_id} XBRL namespace must be us-gaap")
    if company.get("finance_lease_xbrl_tags") != [FINANCE_LEASE_ADDITIONS_TAG]:
        raise CollectorError(
            f"{company_id} finance-lease additions tag is not reviewed"
        )
    return {
        "company_id": company_id,
        "name": _nonempty(company.get("name"), field="company.name"),
        "ticker": _nonempty(company.get("ticker"), field="company.ticker"),
        "cik": cik,
        "fiscal_year_end": _nonempty(
            company.get("fiscal_year_end"), field="company.fiscal_year_end"
        ),
        "namespace": "us-gaap",
        "cash_capex_tag": expected_tag,
        "finance_lease_tag": FINANCE_LEASE_ADDITIONS_TAG,
    }


def _payload_cik(value: Any, *, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise CollectorError(f"{field} must be a CIK")
    digits = str(value)
    if not digits.isdigit() or len(digits) > 10:
        raise CollectorError(f"{field} must be a CIK")
    return digits.zfill(10)


def _parse_fact_rows(
    concept: Mapping[str, Any],
    *,
    namespace: str,
    tag: str,
) -> list[dict[str, Any]]:
    _nonempty(concept.get("label"), field=f"facts.{namespace}.{tag}.label")
    _nonempty(
        concept.get("description"), field=f"facts.{namespace}.{tag}.description"
    )
    units = concept.get("units")
    if not isinstance(units, Mapping) or set(units) != {"USD"}:
        raise CollectorError(f"facts.{namespace}.{tag}.units must be exactly USD")
    raw_rows = units.get("USD")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        raise CollectorError(f"facts.{namespace}.{tag}.units.USD must be a list")

    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, raw in enumerate(raw_rows):
        path = f"facts.{namespace}.{tag}.units.USD[{index}]"
        if not isinstance(raw, Mapping):
            raise CollectorError(f"{path} must be an object")
        form = raw.get("form")
        # Company Facts can carry 8-K comparisons for the same concept.  They
        # are not fiscal-quarter inputs and are intentionally ignored.
        if form not in SUPPORTED_FORMS:
            continue
        start = _iso_date(raw.get("start"), field=f"{path}.start")
        end = _iso_date(raw.get("end"), field=f"{path}.end")
        filed = _iso_date(raw.get("filed"), field=f"{path}.filed")
        assert start is not None and end is not None and filed is not None
        if end < start:
            raise CollectorError(f"{path} has an inverted context")
        if filed < end:
            raise CollectorError(f"{path}.filed precedes the context end")
        accession = raw.get("accn")
        if not isinstance(accession, str) or not ACCESSION_RE.fullmatch(accession):
            raise CollectorError(f"{path}.accn is invalid")
        value = raw.get("val")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CollectorError(f"{path}.val must be numeric")
        parsed_value = float(value)
        if not isfinite(parsed_value) or parsed_value < 0:
            raise CollectorError(f"{path}.val must be finite and non-negative")
        fiscal_year = raw.get("fy")
        if isinstance(fiscal_year, bool) or not isinstance(fiscal_year, int):
            raise CollectorError(f"{path}.fy must be an integer")
        fiscal_period = raw.get("fp")
        if fiscal_period not in {"Q1", "Q2", "Q3", "FY"}:
            raise CollectorError(f"{path}.fp is invalid")
        frame = raw.get("frame")
        if frame is not None and (not isinstance(frame, str) or not frame):
            raise CollectorError(f"{path}.frame must be text or null")
        point = {
            "namespace": namespace,
            "tag": tag,
            "unit": "USD",
            "start": start,
            "end": end,
            "value": parsed_value,
            "accession": accession,
            "fiscal_year_filed": fiscal_year,
            "fiscal_period_filed": fiscal_period,
            "form": form,
            "filed_at": filed,
            "frame": frame,
        }
        identity = (start, end, accession)
        previous = by_identity.get(identity)
        if previous is not None and previous != point:
            raise CollectorError(
                f"conflicting duplicate SEC Company Fact: {tag} {start} {end} {accession}"
            )
        by_identity[identity] = point
    return sorted(
        by_identity.values(),
        key=lambda point: (
            point["end"],
            point["start"],
            point["filed_at"],
            point["accession"],
        ),
    )


def parse_company_facts(
    payload: Mapping[str, Any], *, company: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one official Company Facts response without quarterizing it."""

    identity = _company_identity(company)
    if not isinstance(payload, Mapping):
        raise CollectorError("SEC Company Facts response must be an object")
    if _payload_cik(payload.get("cik"), field="companyfacts.cik") != identity["cik"]:
        raise CollectorError(f"SEC Company Facts CIK mismatch for {identity['company_id']}")
    entity_name = _nonempty(payload.get("entityName"), field="companyfacts.entityName")
    facts = payload.get("facts")
    if not isinstance(facts, Mapping):
        raise CollectorError("companyfacts.facts must be an object")
    namespace = facts.get(identity["namespace"])
    if not isinstance(namespace, Mapping):
        raise CollectorError("companyfacts.facts.us-gaap must be an object")
    cash_concept = namespace.get(identity["cash_capex_tag"])
    if not isinstance(cash_concept, Mapping):
        raise CollectorError(
            f"Company Facts is missing {identity['cash_capex_tag']} for {identity['company_id']}"
        )
    cash_facts = _parse_fact_rows(
        cash_concept,
        namespace=identity["namespace"],
        tag=identity["cash_capex_tag"],
    )
    if not cash_facts:
        raise CollectorError(
            "Company Facts has no supported cash CapEx facts for "
            f"{identity['company_id']}"
        )

    finance_concept = namespace.get(identity["finance_lease_tag"])
    finance_facts = (
        _parse_fact_rows(
            finance_concept,
            namespace=identity["namespace"],
            tag=identity["finance_lease_tag"],
        )
        if isinstance(finance_concept, Mapping)
        else []
    )
    return {
        **identity,
        "entity_name": entity_name,
        "cash_capex_facts": cash_facts,
        "finance_lease_facts": finance_facts,
    }


def parse_submissions(
    payload: Mapping[str, Any], *, company: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Validate the recent filings table and index supported XBRL filings."""

    identity = _company_identity(company)
    if not isinstance(payload, Mapping):
        raise CollectorError("SEC submissions response must be an object")
    if _payload_cik(payload.get("cik"), field="submissions.cik") != identity["cik"]:
        raise CollectorError(f"SEC submissions CIK mismatch for {identity['company_id']}")
    _nonempty(payload.get("name"), field="submissions.name")
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, Mapping) else None
    if not isinstance(recent, Mapping):
        raise CollectorError("submissions.filings.recent must be an object")
    required = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
        "isXBRL",
    )
    arrays = {}
    for field in required:
        value = recent.get(field)
        if not isinstance(value, list):
            raise CollectorError(f"submissions.filings.recent.{field} must be a list")
        arrays[field] = value
    lengths = {len(values) for values in arrays.values()}
    if len(lengths) != 1:
        raise CollectorError("submissions recent filing arrays have different lengths")

    indexed: dict[str, dict[str, Any]] = {}
    cik_path = str(int(identity["cik"]))
    for index in range(next(iter(lengths), 0)):
        form = arrays["form"][index]
        if form not in SUPPORTED_FORMS:
            continue
        accession = arrays["accessionNumber"][index]
        if not isinstance(accession, str) or not ACCESSION_RE.fullmatch(accession):
            raise CollectorError(f"submissions accession {index} is invalid")
        filing_date = _iso_date(
            arrays["filingDate"][index], field=f"submissions.filingDate[{index}]"
        )
        report_date = _iso_date(
            arrays["reportDate"][index],
            field=f"submissions.reportDate[{index}]",
            allow_empty=True,
        )
        accepted_at = as_iso_utc(arrays["acceptanceDateTime"][index])
        is_xbrl = arrays["isXBRL"][index]
        if isinstance(is_xbrl, bool) or is_xbrl not in (0, 1):
            raise CollectorError(f"submissions.isXBRL[{index}] must be 0 or 1")
        if is_xbrl != 1:
            continue
        primary_document = arrays["primaryDocument"][index]
        if not isinstance(primary_document, str) or not PRIMARY_DOCUMENT_RE.fullmatch(
            primary_document
        ):
            raise CollectorError(
                f"submissions.primaryDocument[{index}] is not a safe filename"
            )
        assert filing_date is not None
        point = {
            "accession": accession,
            "form": form,
            "filing_date": filing_date,
            "report_date": report_date,
            "accepted_at": accepted_at,
            "primary_document": primary_document,
            "filing_url": (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{cik_path}/{accession.replace('-', '')}/{primary_document}"
            ),
        }
        previous = indexed.get(accession)
        if previous is not None and previous != point:
            raise CollectorError(f"conflicting duplicate SEC submission: {accession}")
        indexed[accession] = point
    if not indexed:
        raise CollectorError("SEC submissions has no supported XBRL filings")
    return dict(sorted(indexed.items()))


def parse_company_bundle(
    company_facts_payload: Mapping[str, Any],
    submissions_payload: Mapping[str, Any],
    *,
    company: Mapping[str, Any],
) -> dict[str, Any]:
    """Join numeric facts to filing provenance by exact accession."""

    bundle = parse_company_facts(company_facts_payload, company=company)
    submissions = parse_submissions(submissions_payload, company=company)
    joined: dict[str, list[dict[str, Any]]] = {}
    for fact_kind in ("cash_capex_facts", "finance_lease_facts"):
        output = []
        for fact in bundle[fact_kind]:
            filing = submissions.get(fact["accession"])
            if filing is None:
                # Older Company Facts may predate the recent submissions table.
                # Retain the fact as explicitly unusable; the transform fails if
                # such a row is needed for the latest 12-quarter window.
                output.append(
                    {
                        **fact,
                        "accepted_at": None,
                        "report_date": None,
                        "primary_document": None,
                        "filing_url": None,
                        "filing_metadata_missing": True,
                    }
                )
                continue
            if filing["form"] != fact["form"] or filing["filing_date"] != fact["filed_at"]:
                raise CollectorError(
                    f"Company Fact/submission mismatch for {fact['accession']}"
                )
            output.append(
                {
                    **fact,
                    "accepted_at": filing["accepted_at"],
                    "report_date": filing["report_date"],
                    "primary_document": filing["primary_document"],
                    "filing_url": filing["filing_url"],
                    "filing_metadata_missing": False,
                }
            )
        joined[fact_kind] = output
    return {**bundle, **joined, "submission_count": len(submissions)}


def _resolved_user_agent(value: str | None) -> str:
    user_agent = value or os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    if not isinstance(user_agent, str) or "@" not in user_agent or len(user_agent) < 12:
        raise CollectorError("SEC User-Agent must identify the application and contact")
    return user_agent


def fetch_company_bundle(
    company: Mapping[str, Any],
    *,
    user_agent: str | None = None,
    limiter: SerializedTokenBucket | None = None,
    json_fetcher: Callable[..., Mapping[str, Any]] = get_json,
) -> dict[str, Any]:
    """Fetch the two official SEC JSON endpoints for one reviewed company."""

    identity = _company_identity(company)
    agent = _resolved_user_agent(user_agent)
    rate_limiter = limiter or SerializedTokenBucket(4.0)
    rate_limiter.acquire()
    company_facts = json_fetcher(
        COMPANY_FACTS_URL.format(cik=identity["cik"]), user_agent=agent
    )
    rate_limiter.acquire()
    submissions = json_fetcher(
        SUBMISSIONS_URL.format(cik=identity["cik"]), user_agent=agent
    )
    return parse_company_bundle(company_facts, submissions, company=company)


def fetch_company_bundles(
    companies: Sequence[Mapping[str, Any]],
    *,
    user_agent: str | None = None,
    rate_per_second: float = 4.0,
    json_fetcher: Callable[..., Mapping[str, Any]] = get_json,
) -> dict[str, dict[str, Any]]:
    """Fetch all four bundles under one serialized 2--5 requests/sec limiter."""

    if rate_per_second < 2 or rate_per_second > 5:
        raise CollectorError("SEC Company Facts rate must be between 2 and 5 requests/sec")
    identities = [_company_identity(company) for company in companies]
    company_ids = [identity["company_id"] for identity in identities]
    if len(company_ids) != len(set(company_ids)):
        raise CollectorError("duplicate P3 company")
    if set(company_ids) != set(EXPECTED_CASH_CAPEX_TAGS):
        raise CollectorError("P3 Company Facts collection requires all four hyperscalers")
    limiter = SerializedTokenBucket(rate_per_second)
    output: dict[str, dict[str, Any]] = {}
    for company, identity in zip(companies, identities, strict=True):
        output[identity["company_id"]] = fetch_company_bundle(
            company,
            user_agent=user_agent,
            limiter=limiter,
            json_fetcher=json_fetcher,
        )
    return output
