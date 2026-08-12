"""P2 SEC Form 4 open-market purchase/sale proxy transforms.

``P/S`` means the ratio of non-derivative, open-market purchase-code ``P``
transactions to sale-code ``S`` transactions.  It never means
"open-market-only".  Count ratios use the locked add-one smoothing convention;
dollar ratios are unsmoothed, require at least 80% priced-row coverage, and are
null when priced sales are zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from pipeline.collectors.common import CollectorError
from pipeline.form4_ledger import EFFECTIVE_STATUSES, resolve_amendments


METRIC_ID = "sec_form4_nonderivative_ps_count_ratio_20d"
DOLLAR_COVERAGE_THRESHOLD = Decimal("0.80")
EX_10B5_SCOPE = "EXPLICIT_FALSE_ONLY"


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CollectorError(f"{field} is not decimal") from exc
    if not result.is_finite() or result < 0:
        raise CollectorError(f"{field} is outside its valid domain")
    return result


def _rounded(value: Decimal | None, places: str = "0.000001") -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _completed_days(values: Sequence[Any], *, as_of: date | None) -> list[str]:
    days: set[str] = set()
    for raw in values:
        if isinstance(raw, str):
            day_text, status = raw, "COMPLETE"
        elif isinstance(raw, Mapping):
            day_text, status = raw.get("date"), raw.get("status")
        else:
            raise CollectorError("completed index day must be a string or object")
        if status != "COMPLETE" or not isinstance(day_text, str):
            continue
        try:
            parsed = date.fromisoformat(day_text)
        except ValueError as exc:
            raise CollectorError("completed index day is invalid") from exc
        if as_of is None or parsed <= as_of:
            days.add(parsed.isoformat())
    return sorted(days)


def _bucket(entry: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    totals = entry.get("totals")
    if not isinstance(totals, Mapping) or not isinstance(totals.get(name), Mapping):
        raise CollectorError(f"Form 4 ledger entry is missing {name} totals")
    return totals[name]


def _window_entries(
    entries: Sequence[Mapping[str, Any]], days: Sequence[str]
) -> list[Mapping[str, Any]]:
    selected = set(days)
    return [entry for entry in entries if entry.get("index_date") in selected]


def _failure_count(
    failures: Sequence[Mapping[str, Any]], days: Sequence[str]
) -> int:
    selected = set(days)
    return sum(
        1
        for failure in failures
        if failure.get("index_date") in selected
        and failure.get("stage")
        in {"SUBMISSION", "TRANSACTION_PARSE", "TRANSACTION_QUARANTINE"}
    )


def _window_summary(
    entries: Sequence[Mapping[str, Any]],
    *,
    days: Sequence[str],
    required_days: int,
    failures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    processed = _window_entries(entries, days)
    effective = [
        entry
        for entry in processed
        if entry.get("amendment_status") in EFFECTIVE_STATUSES
        and entry.get("parse_status")
        in {"PARSED", "PARSED_WITH_QUARANTINED_ROWS"}
    ]
    complete_window = len(days) == required_days
    all_purchase = all_sale = all_priced = all_eligible = 0
    purchase_dollars = Decimal("0")
    sale_dollars = Decimal("0")
    false_purchase = false_sale = false_eligible = 0
    issuers: set[str] = set()
    tenb5_true = tenb5_false = tenb5_unknown = 0
    for entry in effective:
        issuers.add(str(entry.get("issuer_cik")))
        filing_flag = entry.get("filing_10b5_status")
        if filing_flag not in {"TRUE", "FALSE", "UNKNOWN"}:
            raise CollectorError("Form 4 ledger filing 10b5 status is invalid")
        tenb5_true += int(filing_flag == "TRUE")
        tenb5_false += int(filing_flag == "FALSE")
        tenb5_unknown += int(filing_flag == "UNKNOWN")
        all_bucket = _bucket(entry, "ALL")
        false_bucket = _bucket(entry, "FALSE")
        all_purchase += int(all_bucket["purchase_count"])
        all_sale += int(all_bucket["sale_count"])
        all_priced += int(all_bucket["priced_transaction_count"])
        all_eligible += int(all_bucket["eligible_transaction_count"])
        purchase_dollars += _decimal(
            all_bucket["purchase_dollars"], field="purchase_dollars"
        )
        sale_dollars += _decimal(all_bucket["sale_dollars"], field="sale_dollars")
        false_purchase += int(false_bucket["purchase_count"])
        false_sale += int(false_bucket["sale_count"])
        false_eligible += int(false_bucket["eligible_transaction_count"])

    count_ratio = (
        Decimal(all_purchase + 1) / Decimal(all_sale + 1)
        if complete_window and all_eligible > 0
        else None
    )
    dollar_coverage = (
        Decimal(all_priced) / Decimal(all_eligible)
        if complete_window and all_eligible > 0
        else None
    )
    if not complete_window:
        dollar_ratio = None
        dollar_status = "INSUFFICIENT_COMPLETED_DAYS"
    elif all_eligible == 0:
        dollar_ratio = None
        dollar_status = "NO_ELIGIBLE_ROWS"
    elif dollar_coverage is None or dollar_coverage < DOLLAR_COVERAGE_THRESHOLD:
        dollar_ratio = None
        dollar_status = "INSUFFICIENT_PRICE_COVERAGE"
    elif sale_dollars == 0:
        dollar_ratio = None
        dollar_status = "NO_SALES_DOLLAR_DENOMINATOR"
    else:
        dollar_ratio = purchase_dollars / sale_dollars
        dollar_status = "PUBLISHED"

    false_ratio = (
        Decimal(false_purchase + 1) / Decimal(false_sale + 1)
        if complete_window and false_eligible > 0
        else None
    )
    false_coverage = (
        Decimal(false_eligible) / Decimal(all_eligible)
        if complete_window and all_eligible > 0
        else None
    )
    return {
        "completed_day_count": len(days),
        "window_start": days[0] if days else None,
        "window_end": days[-1] if days else None,
        "count_ratio": _rounded(count_ratio),
        "purchase_count": all_purchase,
        "sale_count": all_sale,
        "dollar_ratio": _rounded(dollar_ratio),
        "dollar_coverage_rate": _rounded(dollar_coverage),
        "dollar_status": dollar_status,
        "ex_explicit_false_count_ratio": _rounded(false_ratio),
        "ex_explicit_false_coverage": _rounded(false_coverage),
        "eligible_transaction_count": all_eligible,
        "priced_transaction_count": all_priced,
        "unique_accessions": len({str(entry["accession"]) for entry in processed}),
        "unique_issuers": len(issuers),
        "filings_processed": len(processed),
        "form4_count": sum(entry.get("form_type") == "4" for entry in processed),
        "form4a_count": sum(entry.get("form_type") == "4/A" for entry in processed),
        "amendments_linked": sum(
            entry.get("form_type") == "4/A"
            and entry.get("linked_original_accession") is not None
            for entry in processed
        ),
        "amendments_review_count": sum(
            entry.get("amendment_status") == "UNLINKED_REVIEW" for entry in processed
        ),
        "parse_failures": _failure_count(failures, days),
        "tenb5_true_filings": tenb5_true,
        "tenb5_false_filings": tenb5_false,
        "tenb5_unknown_filings": tenb5_unknown,
    }


def form4_statistics(
    package: Mapping[str, Any], *, as_of: date | None = None
) -> tuple[dict[str, int | float | None], dict[str, str | None]]:
    """Build the locked numeric stats and context keys for frontend integration."""

    raw_entries = package.get("entries")
    raw_days = package.get("completed_index_days")
    raw_failures = package.get("failures", [])
    raw_reviews = package.get("reviews", [])
    if not isinstance(raw_entries, list) or not isinstance(raw_days, list):
        raise CollectorError("Form 4 ledger package has the wrong schema")
    if not isinstance(raw_failures, list) or not isinstance(raw_reviews, list):
        raise CollectorError("Form 4 ledger package failures/reviews must be lists")
    parse_events = [*raw_failures, *raw_reviews]
    entries = resolve_amendments(raw_entries)
    completed = _completed_days(raw_days, as_of=as_of)
    days_5 = completed[-5:]
    days_20 = completed[-20:]
    summary_5 = _window_summary(
        entries, days=days_5, required_days=5, failures=parse_events
    )
    summary_20 = _window_summary(
        entries, days=days_20, required_days=20, failures=parse_events
    )
    stats: dict[str, int | float | None] = {
        "ratio_5d": summary_5["count_ratio"],
        "count_ratio_20d": summary_20["count_ratio"],
        "purchase_count_5d": summary_5["purchase_count"],
        "sale_count_5d": summary_5["sale_count"],
        "purchase_count_20d": summary_20["purchase_count"],
        "sale_count_20d": summary_20["sale_count"],
        "dollar_ratio_5d": summary_5["dollar_ratio"],
        "dollar_ratio_20d": summary_20["dollar_ratio"],
        "dollar_coverage_rate_5d": summary_5["dollar_coverage_rate"],
        "dollar_coverage_rate_20d": summary_20["dollar_coverage_rate"],
        "ex_explicit_false_count_ratio_5d": summary_5[
            "ex_explicit_false_count_ratio"
        ],
        "ex_explicit_false_count_ratio_20d": summary_20[
            "ex_explicit_false_count_ratio"
        ],
        "ex_explicit_false_coverage_5d": summary_5[
            "ex_explicit_false_coverage"
        ],
        "ex_explicit_false_coverage_20d": summary_20[
            "ex_explicit_false_coverage"
        ],
        "eligible_transaction_count_20d": summary_20[
            "eligible_transaction_count"
        ],
        "priced_transaction_count_20d": summary_20["priced_transaction_count"],
        "unique_accessions_20d": summary_20["unique_accessions"],
        "unique_issuers_20d": summary_20["unique_issuers"],
        "filings_processed_20d": summary_20["filings_processed"],
        "form4_count_20d": summary_20["form4_count"],
        "form4a_count_20d": summary_20["form4a_count"],
        "amendments_linked_20d": summary_20["amendments_linked"],
        "amendments_review_count_20d": summary_20["amendments_review_count"],
        "parse_failures_20d": summary_20["parse_failures"],
        "tenb5_true_filings_20d": summary_20["tenb5_true_filings"],
        "tenb5_false_filings_20d": summary_20["tenb5_false_filings"],
        "tenb5_unknown_filings_20d": summary_20["tenb5_unknown_filings"],
    }
    context: dict[str, str | None] = {
        "window_start_5d": summary_5["window_start"],
        "window_end_5d": summary_5["window_end"],
        "window_start_20d": summary_20["window_start"],
        "window_end_20d": summary_20["window_end"],
        "dollar_status_5d": summary_5["dollar_status"],
        "dollar_status_20d": summary_20["dollar_status"],
        "ex_10b5_scope": EX_10B5_SCOPE,
    }
    return stats, context


def form4_metric_observation(
    package: Mapping[str, Any], *, as_of: date | None = None
) -> dict[str, Any]:
    """Return a release-layer-friendly observation/statistics payload."""

    stats, context = form4_statistics(package, as_of=as_of)
    completed = _completed_days(package.get("completed_index_days", []), as_of=as_of)
    return {
        "metric_id": METRIC_ID,
        "date": completed[-1] if completed else None,
        "value": stats["count_ratio_20d"],
        "statistics": stats,
        "technical_context": context,
    }


__all__ = [
    "DOLLAR_COVERAGE_THRESHOLD",
    "EX_10B5_SCOPE",
    "METRIC_ID",
    "form4_metric_observation",
    "form4_statistics",
]
