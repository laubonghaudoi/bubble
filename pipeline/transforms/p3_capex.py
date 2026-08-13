"""Pure P3 transforms for hyperscaler cash CapEx and acceleration evidence."""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from math import isfinite
from typing import Any

from pipeline.collectors.common import CollectorError
from pipeline.collectors.sec_companyfacts import EXPECTED_CASH_CAPEX_TAGS


CAPEX_METRIC_ID = "hyperscaler_aggregate_cash_capex"
ACCELERATION_METRIC_ID = "hyperscaler_aggregate_cash_capex_yoy_acceleration_pp"
COMPANY_TOTAL = 4
MIN_QUARTERS = 12


def _fye(value: Any) -> tuple[int, int]:
    if not isinstance(value, str) or len(value) != 5 or value[2] != "-":
        raise CollectorError("fiscal_year_end must use MM-DD")
    try:
        month, day = (int(part) for part in value.split("-"))
        date(2000, month, day)
    except (TypeError, ValueError) as exc:
        raise CollectorError("fiscal_year_end must use MM-DD") from exc
    if day != calendar.monthrange(2000, month)[1]:
        raise CollectorError("P3 fiscal year end must be a calendar month end")
    return month, day


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _shift_month_end(value: date, months: int) -> date:
    ordinal = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(ordinal, 12)
    return _month_end(year, zero_month + 1)


def _fiscal_year_for_end(value: date, fiscal_year_end: tuple[int, int]) -> int:
    return value.year + (1 if (value.month, value.day) > fiscal_year_end else 0)


def _fiscal_context(
    fiscal_year: int, fiscal_year_end: tuple[int, int], quarter: int
) -> tuple[date, date]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1..4")
    month, _day = fiscal_year_end
    fiscal_end = _month_end(fiscal_year, month)
    quarter_end = _shift_month_end(fiscal_end, (quarter - 4) * 3)
    previous_fiscal_end = _month_end(fiscal_year - 1, month)
    return previous_fiscal_end + timedelta(days=1), quarter_end


def _choose_restatement(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    usable = [
        candidate
        for candidate in candidates
        if candidate.get("accepted_at") is not None
        and candidate.get("filing_url") is not None
        and candidate.get("filing_metadata_missing") is False
    ]
    if not usable:
        raise CollectorError("required Company Fact has no matching filing provenance")
    ordered = sorted(
        usable,
        key=lambda fact: (
            fact["accepted_at"],
            fact["filed_at"],
            fact["form"].endswith("/A"),
            fact["accession"],
        ),
    )
    latest = ordered[-1]
    latest_key = (latest["accepted_at"], latest["filed_at"])
    tied = [
        fact
        for fact in ordered
        if (fact["accepted_at"], fact["filed_at"]) == latest_key
    ]
    if any(float(fact["value"]) != float(latest["value"]) for fact in tied):
        raise CollectorError("ambiguous latest Company Fact restatement")
    return dict(latest)


def _cumulative_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    fiscal_year_end: tuple[int, int],
    expected_tag: str,
) -> dict[tuple[int, int], dict[str, Any]]:
    candidates: dict[tuple[int, int], list[Mapping[str, Any]]] = {}
    for fact in facts:
        if (
            fact.get("namespace") != "us-gaap"
            or fact.get("tag") != expected_tag
            or fact.get("unit") != "USD"
        ):
            raise CollectorError("normalized Company Fact identity or unit mismatch")
        # The SEC recent-submissions table is intentionally bounded.  Old
        # Company Facts without matching filing provenance cannot be
        # published, but they also must not prevent a newer fully-provenanced
        # 12-quarter suffix from being used.
        if (
            fact.get("accepted_at") is None
            or fact.get("filing_url") is None
            or fact.get("filing_metadata_missing") is not False
        ):
            continue
        try:
            start = date.fromisoformat(str(fact["start"]))
            end = date.fromisoformat(str(fact["end"]))
            value = float(fact["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CollectorError("normalized Company Fact is malformed") from exc
        if not isfinite(value) or value < 0:
            raise CollectorError("normalized Company Fact value must be non-negative")
        fiscal_year = _fiscal_year_for_end(end, fiscal_year_end)
        for quarter in (1, 2, 3, 4):
            expected_start, expected_end = _fiscal_context(
                fiscal_year, fiscal_year_end, quarter
            )
            if start == expected_start and end == expected_end:
                candidates.setdefault((fiscal_year, quarter), []).append(fact)
                break
    return {
        key: _choose_restatement(rows) for key, rows in sorted(candidates.items())
    }


def _quarterized_values(
    cumulative: Mapping[tuple[int, int], Mapping[str, Any]],
    *,
    optional: bool,
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    methods = {
        1: "Q1_YTD",
        2: "H1_MINUS_Q1",
        3: "9M_MINUS_H1",
        4: "FY_MINUS_9M",
    }
    for (fiscal_year, quarter), current in sorted(cumulative.items()):
        previous = cumulative.get((fiscal_year, quarter - 1)) if quarter > 1 else None
        if quarter > 1 and previous is None:
            # Concept adoption and taxonomy migrations can leave older fiscal
            # years incomplete.  Skip that non-derivable quarter; the strict
            # consecutive-suffix gate below still fails closed if the latest
            # publication window has any hole.
            continue
        value = float(current["value"])
        if previous is not None:
            value -= float(previous["value"])
        if value < 0:
            if optional:
                continue
            raise CollectorError(
                f"negative quarterized cash CapEx for FY{fiscal_year} Q{quarter}"
            )
        output[current["end"]] = {
            "value_usd": value,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": f"FY{fiscal_year}Q{quarter}",
            "quarterization_method": methods[quarter],
            "source": dict(current),
        }
    return output


def _percent_change(current: float, previous: float | None) -> float | None:
    if previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _direction(acceleration: float | None) -> str:
    if acceleration is None:
        return "UNKNOWN"
    if acceleration > 0:
        return "ACCELERATING"
    if acceleration < 0:
        return "DECELERATING"
    return "FLAT"


def _require_consecutive_suffix(
    points: Sequence[dict[str, Any]], *, minimum: int
) -> list[dict[str, Any]]:
    if not points:
        raise CollectorError("quarterized CapEx series is empty")
    suffix = [points[-1]]
    for point in reversed(points[:-1]):
        expected = _shift_month_end(date.fromisoformat(suffix[0]["date"]), -3)
        if date.fromisoformat(point["date"]) != expected:
            break
        suffix.insert(0, point)
    if len(suffix) < minimum:
        raise CollectorError(
            f"cash CapEx requires at least {minimum} consecutive fiscal quarters"
        )
    return suffix


def quarterize_company_cash_capex(
    bundle: Mapping[str, Any], *, minimum_quarters: int = MIN_QUARTERS
) -> list[dict[str, Any]]:
    """Quarterize one company's fiscal/YTD cash CapEx without finance leases."""

    company_id = bundle.get("company_id")
    if company_id not in EXPECTED_CASH_CAPEX_TAGS:
        raise CollectorError(f"unsupported P3 company bundle: {company_id}")
    if bundle.get("cash_capex_tag") != EXPECTED_CASH_CAPEX_TAGS[company_id]:
        raise CollectorError(f"cash CapEx tag mismatch for {company_id}")
    fiscal_year_end = _fye(bundle.get("fiscal_year_end"))
    cash_facts = bundle.get("cash_capex_facts")
    finance_facts = bundle.get("finance_lease_facts")
    if not isinstance(cash_facts, Sequence) or isinstance(cash_facts, (str, bytes)):
        raise CollectorError("cash_capex_facts must be a list")
    if not isinstance(finance_facts, Sequence) or isinstance(
        finance_facts, (str, bytes)
    ):
        raise CollectorError("finance_lease_facts must be a list")
    cash = _quarterized_values(
        _cumulative_facts(
            cash_facts,
            fiscal_year_end=fiscal_year_end,
            expected_tag=bundle["cash_capex_tag"],
        ),
        optional=False,
    )
    finance = _quarterized_values(
        _cumulative_facts(
            finance_facts,
            fiscal_year_end=fiscal_year_end,
            expected_tag="RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability",
        ),
        optional=True,
    )

    points: list[dict[str, Any]] = []
    for day, quarter in sorted(cash.items()):
        source = quarter["source"]
        finance_quarter = finance.get(day)
        # The public company record only carries the cash filing's URL/form/
        # acceptance provenance.  Publish finance-lease evidence only when it
        # comes from that same filing; otherwise fail closed until the schema
        # grows an independent finance-lease provenance object.
        if (
            finance_quarter is not None
            and finance_quarter["source"].get("accession")
            != source.get("accession")
        ):
            finance_quarter = None
        finance_source = finance_quarter["source"] if finance_quarter else None
        cash_usd_bn = quarter["value_usd"] / 1_000_000_000
        previous = points[-1] if points else None
        year_ago = points[-4] if len(points) >= 4 else None
        qoq = _percent_change(
            cash_usd_bn,
            float(previous["cash_capex_usd_bn"]) if previous else None,
        )
        yoy = _percent_change(
            cash_usd_bn,
            float(year_ago["cash_capex_usd_bn"]) if year_ago else None,
        )
        previous_qoq = previous["qoq_percent_change"] if previous else None
        previous_yoy = previous["yoy_percent_change"] if previous else None
        qoq_acceleration = (
            qoq - float(previous_qoq)
            if qoq is not None and previous_qoq is not None
            else None
        )
        yoy_acceleration = (
            yoy - float(previous_yoy)
            if yoy is not None and previous_yoy is not None
            else None
        )
        points.append(
            {
                "date": day,
                "company_id": company_id,
                "ticker": bundle["ticker"],
                "cik": bundle["cik"],
                "fiscal_quarter": quarter["fiscal_quarter"],
                "calendar_period_end": day,
                "cash_capex_usd_bn": _rounded(cash_usd_bn),
                "qoq_percent_change": _rounded(qoq),
                "yoy_percent_change": _rounded(yoy),
                "qoq_acceleration_pp": _rounded(qoq_acceleration),
                "yoy_acceleration_pp": _rounded(yoy_acceleration),
                "direction": _direction(yoy_acceleration),
                "tag": source["tag"],
                "namespace": source["namespace"],
                "unit": source["unit"],
                "accession": source["accession"],
                "form": source["form"],
                "filed_at": source["filed_at"],
                "accepted_at": source["accepted_at"],
                "filing_url": source["filing_url"],
                "frame": source["frame"],
                "context_start": source["start"],
                "context_end": source["end"],
                "quarterization_method": quarter["quarterization_method"],
                "manual_review_required": False,
                "finance_lease_additions_usd_bn": (
                    _rounded(finance_quarter["value_usd"] / 1_000_000_000)
                    if finance_quarter
                    else None
                ),
                "finance_lease_tag": (
                    finance_source["tag"] if finance_source else None
                ),
                "finance_lease_accession": (
                    finance_source["accession"] if finance_source else None
                ),
                "finance_lease_quarterization_method": (
                    finance_quarter["quarterization_method"]
                    if finance_quarter
                    else None
                ),
            }
        )
    return _require_consecutive_suffix(points, minimum=minimum_quarters)


def aggregate_hyperscaler_cash_capex(
    company_series: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    minimum_quarters: int = MIN_QUARTERS,
) -> list[dict[str, Any]]:
    """Align exact quarter ends, aggregate dollars, then calculate growth."""

    if set(company_series) != set(EXPECTED_CASH_CAPEX_TAGS):
        raise CollectorError("P3 aggregation requires the four fixed hyperscalers")
    indexed: dict[str, dict[str, Mapping[str, Any]]] = {}
    for company_id, points in company_series.items():
        rows: dict[str, Mapping[str, Any]] = {}
        for point in points:
            if point.get("company_id") != company_id:
                raise CollectorError(f"{company_id} CapEx series identity mismatch")
            day = point.get("date")
            if not isinstance(day, str):
                raise CollectorError(f"{company_id} CapEx point is missing date")
            try:
                if date.fromisoformat(day).isoformat() != day:
                    raise ValueError
            except ValueError as exc:
                raise CollectorError(
                    f"{company_id} CapEx point has an invalid date"
                ) from exc
            value = point.get("cash_capex_usd_bn")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(float(value))
                or value < 0
            ):
                raise CollectorError(
                    f"{company_id} CapEx point has an invalid cash value"
                )
            if day in rows:
                raise CollectorError(f"duplicate {company_id} CapEx quarter: {day}")
            rows[day] = point
        indexed[company_id] = rows
    common_dates = set.intersection(*(set(rows) for rows in indexed.values()))
    if not common_dates:
        raise CollectorError("hyperscaler CapEx series have no common quarters")

    points: list[dict[str, Any]] = []
    aligned_company_history: dict[str, list[dict[str, Any]]] = {
        company_id: [] for company_id in indexed
    }
    for day in sorted(common_dates):
        companies: list[dict[str, Any]] = []
        for company_id in sorted(indexed):
            company = dict(indexed[company_id][day])
            history = aligned_company_history[company_id]
            previous_company = history[-1] if history else None
            year_ago_company = history[-4] if len(history) >= 4 else None
            company_qoq = _percent_change(
                float(company["cash_capex_usd_bn"]),
                float(previous_company["cash_capex_usd_bn"])
                if previous_company
                else None,
            )
            company_yoy = _percent_change(
                float(company["cash_capex_usd_bn"]),
                float(year_ago_company["cash_capex_usd_bn"])
                if year_ago_company
                else None,
            )
            company_qoq_acceleration = (
                company_qoq - float(previous_company["qoq_percent_change"])
                if company_qoq is not None
                and previous_company is not None
                and previous_company["qoq_percent_change"] is not None
                else None
            )
            company_yoy_acceleration = (
                company_yoy - float(previous_company["yoy_percent_change"])
                if company_yoy is not None
                and previous_company is not None
                and previous_company["yoy_percent_change"] is not None
                else None
            )
            company.update(
                {
                    "qoq_percent_change": _rounded(company_qoq),
                    "yoy_percent_change": _rounded(company_yoy),
                    "qoq_acceleration_pp": _rounded(company_qoq_acceleration),
                    "yoy_acceleration_pp": _rounded(company_yoy_acceleration),
                    "direction": _direction(company_yoy_acceleration),
                }
            )
            history.append(company)
            companies.append(company)
        aggregate = sum(float(company["cash_capex_usd_bn"]) for company in companies)
        previous = points[-1] if points else None
        year_ago = points[-4] if len(points) >= 4 else None
        qoq = _percent_change(
            aggregate,
            float(previous["aggregate_cash_capex_usd_bn"]) if previous else None,
        )
        yoy = _percent_change(
            aggregate,
            float(year_ago["aggregate_cash_capex_usd_bn"]) if year_ago else None,
        )
        previous_qoq = previous["qoq_percent_change"] if previous else None
        previous_yoy = previous["yoy_percent_change"] if previous else None
        qoq_acceleration = (
            qoq - float(previous_qoq)
            if qoq is not None and previous_qoq is not None
            else None
        )
        yoy_acceleration = (
            yoy - float(previous_yoy)
            if yoy is not None and previous_yoy is not None
            else None
        )
        direction = _direction(yoy_acceleration)
        known_company_directions = [
            company["direction"]
            for company in companies
            if company["direction"] != "UNKNOWN"
        ]
        breadth = (
            sum(company_direction == direction for company_direction in known_company_directions)
            if direction != "UNKNOWN"
            else 0
        )
        breadth_ratio = (
            breadth / len(known_company_directions)
            if direction != "UNKNOWN" and known_company_directions
            else None
        )
        points.append(
            {
                "date": day,
                "value": _rounded(aggregate),
                "aggregate_cash_capex_usd_bn": _rounded(aggregate),
                "qoq_percent_change": _rounded(qoq),
                "yoy_percent_change": _rounded(yoy),
                "qoq_acceleration_pp": _rounded(qoq_acceleration),
                "yoy_acceleration_pp": _rounded(yoy_acceleration),
                "aggregate_direction": direction,
                "company_breadth": breadth,
                "company_total": COMPANY_TOTAL,
                "company_breadth_ratio": _rounded(breadth_ratio),
                "finance_lease_disclosure_breadth": sum(
                    company["finance_lease_additions_usd_bn"] is not None
                    for company in companies
                ),
                "manual_review_count": sum(
                    company["manual_review_required"] is True
                    for company in companies
                ),
                "companies": [dict(company) for company in companies],
            }
        )
    return _require_consecutive_suffix(points, minimum=minimum_quarters)


def build_hyperscaler_capex(
    bundles: Mapping[str, Mapping[str, Any]],
    *,
    minimum_quarters: int = MIN_QUARTERS,
) -> dict[str, Any]:
    """Build both P3 automated metric payloads from four normalized bundles."""

    company_series = {
        company_id: quarterize_company_cash_capex(
            bundle, minimum_quarters=minimum_quarters
        )
        for company_id, bundle in bundles.items()
    }
    base_series = aggregate_hyperscaler_cash_capex(
        company_series, minimum_quarters=minimum_quarters
    )
    acceleration_series = [
        {**point, "value": point["yoy_acceleration_pp"]} for point in base_series
    ]
    latest = base_series[-1]
    previous = base_series[-2] if len(base_series) > 1 else None
    statistics = {
        "aggregate_cash_capex_usd_bn": latest["aggregate_cash_capex_usd_bn"],
        "qoq_percent_change": latest["qoq_percent_change"],
        "yoy_percent_change": latest["yoy_percent_change"],
        "qoq_acceleration_pp": latest["qoq_acceleration_pp"],
        "yoy_acceleration_pp": latest["yoy_acceleration_pp"],
        "company_breadth": latest["company_breadth"],
        "company_total": latest["company_total"],
        "company_breadth_ratio": latest["company_breadth_ratio"],
        "finance_lease_disclosure_breadth": latest[
            "finance_lease_disclosure_breadth"
        ],
        "manual_review_count": latest["manual_review_count"],
        "quarter_count": len(base_series),
    }
    details = {
        "fundamental": {
            "aggregate_direction": latest["aggregate_direction"],
            "company_breadth": latest["company_breadth"],
            "company_total": COMPANY_TOTAL,
            "companies": latest["companies"],
            "caveats": [
                "Cash CapEx is quarterized from fiscal YTD cash-flow facts; "
                "Q4 is fiscal-year cash CapEx less nine-month cash CapEx.",
                "Finance-lease right-of-use asset additions are shown separately "
                "and are never added to cash CapEx.",
                "SEC facts may be amended or restated; the latest accepted filing "
                "for each exact context is used.",
                "This is evidence coverage and direction, not an automatic "
                "WATCH or STRESS assessment.",
            ],
        }
    }
    change_one_quarter = (
        _rounded(
            float(latest["aggregate_cash_capex_usd_bn"])
            - float(previous["aggregate_cash_capex_usd_bn"])
        )
        if previous
        else None
    )
    acceleration_change = (
        _rounded(
            float(latest["yoy_acceleration_pp"])
            - float(previous["yoy_acceleration_pp"])
        )
        if previous
        and latest["yoy_acceleration_pp"] is not None
        and previous["yoy_acceleration_pp"] is not None
        else None
    )
    return {
        "metric_id": CAPEX_METRIC_ID,
        "acceleration_metric_id": ACCELERATION_METRIC_ID,
        "unit": "USD bn",
        "acceleration_unit": "percentage_points",
        "frequency": "quarterly",
        "series": base_series,
        "acceleration_series": acceleration_series,
        "statistics": statistics,
        "changes": {"one_quarter": change_one_quarter},
        "acceleration_changes": {"one_quarter": acceleration_change},
        "details": details,
        "company_series": company_series,
    }
