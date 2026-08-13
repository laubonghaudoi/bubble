"""Validate reviewed P3 industry-disclosure records.

The CSV is deliberately a human-review interface, not a collector.  A valid
row may promote one manual evidence metric from ``MANUAL_READY`` to
``ACTIVE_FREE``, but it never makes the source network-enabled and never
extracts or infers a value from filing prose.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

DEFAULT_MANUAL_SIGNALS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "manual" / "industry_signals.csv"
)

MANUAL_SIGNAL_COLUMNS = (
    "company_id",
    "period_end",
    "metric_id",
    "direction",
    "value",
    "unit",
    "yoy_pct",
    "comparable",
    "source_type",
    "source_url",
    "filing_accession",
    "filing_accepted_at",
    "as_of",
    "reviewer",
    "reviewed_at",
    "paraphrase",
    "review_note",
)

P3_MANUAL_METRIC_IDS = (
    "ai_upstream_orders_backlog",
    "customer_prepayments_contract_commitments",
    "take_or_pay_commitments",
)
P3_COMPANY_IDS = ("microsoft", "alphabet", "amazon", "meta")
MANUAL_EVIDENCE_MAX_AGE_DAYS = 120
P3_COMPANY_CIKS = {
    "microsoft": "0000789019",
    "alphabet": "0001652044",
    "amazon": "0001018724",
    "meta": "0001326801",
}
MANUAL_DIRECTIONS = frozenset({"UP", "FLAT", "DOWN", "UNKNOWN"})
MANUAL_SOURCE_TYPES = frozenset(
    {
        "10-Q",
        "10-Q/A",
        "10-K",
        "10-K/A",
        "8-K",
        "8-K/A",
        "DEF 14A",
    }
)
MANUAL_VALUE_UNITS = frozenset(
    {
        "USD",
        "USD mn",
        "USD bn",
        "count",
        "units",
        "percent",
        "percentage_points",
        "ratio",
        "MW",
        "GW",
    }
)

_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_NUMBER_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
_UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


class ManualSignalValidationError(ValueError):
    """The reviewed manual input is not safe to publish."""


@dataclass(frozen=True)
class ManualSignal:
    company_id: str
    period_end: str
    metric_id: str
    direction: str
    value: float | int | None
    unit: str | None
    yoy_pct: float | int | None
    comparable: bool
    source_type: str
    source_url: str
    filing_accession: str
    filing_accepted_at: str
    as_of: str
    reviewer: str
    reviewed_at: str
    paraphrase: str
    review_note: str

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.company_id,
            self.period_end,
            self.metric_id,
            self.filing_accession,
        )

    def as_public_record(self) -> dict[str, Any]:
        """Return a JSON-safe copy without changing null or zero semantics."""

        return asdict(self)


def _error(row_number: int, field: str, detail: str) -> ManualSignalValidationError:
    return ManualSignalValidationError(f"row {row_number} {field}: {detail}")


def _plain_cell(value: str, *, row_number: int, field: str) -> str:
    if value != value.strip():
        raise _error(row_number, field, "leading or trailing whitespace is not allowed")
    if "\n" in value or "\r" in value:
        raise _error(row_number, field, "line breaks are not allowed")
    return value


def _iso_date(value: str, *, row_number: int, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _error(row_number, field, "must be an ISO YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise _error(row_number, field, "must be an ISO YYYY-MM-DD date")
    return parsed


def _utc_timestamp(value: str, *, row_number: int, field: str) -> datetime:
    if _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise _error(row_number, field, "must be an ISO UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(row_number, field, "must be a valid ISO UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise _error(row_number, field, "must be UTC")
    return parsed


def _canonical_utc_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _number(
    value: str,
    *,
    row_number: int,
    field: str,
    nonnegative: bool = False,
) -> float | int | None:
    if value == "":
        return None
    if _NUMBER_RE.fullmatch(value) is None:
        raise _error(
            row_number,
            field,
            "must be a plain finite decimal without commas, percent signs, or exponents",
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise _error(row_number, field, "must be a finite decimal") from exc
    if not parsed.is_finite() or (nonnegative and parsed < 0):
        qualifier = "non-negative " if nonnegative else ""
        raise _error(row_number, field, f"must be a finite {qualifier}decimal")
    if parsed == parsed.to_integral_value():
        return int(parsed)
    return float(parsed)


def _official_source_url(
    value: str,
    *,
    company_id: str,
    accession: str,
    row_number: int,
) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise _error(
            row_number, "source_url", "must be a valid public HTTPS URL"
        ) from exc
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
        or parsed.path in {"", "/"}
    ):
        raise _error(
            row_number,
            "source_url",
            "must be a document-level public HTTPS URL without credentials or a fragment",
        )
    if hostname != "www.sec.gov":
        raise _error(
            row_number,
            "source_url",
            f"host is not an allowlisted official source for {company_id}",
        )
    accession_digits = accession.replace("-", "")
    decoded_path = unquote(parsed.path)
    archive_prefix = (
        f"/Archives/edgar/data/{int(P3_COMPANY_CIKS[company_id])}/"
        f"{accession_digits}/"
    )
    if (
        parsed.query
        or decoded_path != parsed.path
        or any(segment in {".", ".."} for segment in decoded_path.split("/"))
        or re.fullmatch(
            re.escape(archive_prefix) + r"[^/]+\.html?",
            decoded_path,
            flags=re.IGNORECASE,
        )
        is None
    ):
        raise _error(
            row_number,
            "source_url",
            "must be a direct SEC filing document matching accession and issuer CIK",
        )


def _short_text(
    value: str,
    *,
    row_number: int,
    field: str,
    maximum: int,
) -> str:
    if not value:
        raise _error(row_number, field, "is required")
    if len(value) > maximum:
        raise _error(row_number, field, f"must be at most {maximum} characters")
    return value


def validate_manual_signal_row(
    row: Mapping[str, str], *, row_number: int
) -> ManualSignal:
    """Validate one exact CSV row and return its typed representation."""

    if set(row) != set(MANUAL_SIGNAL_COLUMNS):
        raise _error(row_number, "columns", "do not match the 17-column contract")
    cells = {
        field: _plain_cell(row[field], row_number=row_number, field=field)
        for field in MANUAL_SIGNAL_COLUMNS
    }

    company_id = cells["company_id"]
    if company_id not in P3_COMPANY_IDS:
        raise _error(row_number, "company_id", "is not a canonical P3 company ID")
    metric_id = cells["metric_id"]
    if metric_id not in P3_MANUAL_METRIC_IDS:
        raise _error(row_number, "metric_id", "is not a canonical P3 manual metric ID")
    direction = cells["direction"]
    if direction not in MANUAL_DIRECTIONS:
        raise _error(row_number, "direction", "must be UP, FLAT, DOWN, or UNKNOWN")

    period_end = _iso_date(
        cells["period_end"], row_number=row_number, field="period_end"
    )
    as_of = _iso_date(cells["as_of"], row_number=row_number, field="as_of")
    accepted_at = _utc_timestamp(
        cells["filing_accepted_at"],
        row_number=row_number,
        field="filing_accepted_at",
    )
    reviewed_at = _utc_timestamp(
        cells["reviewed_at"], row_number=row_number, field="reviewed_at"
    )
    if not (period_end <= accepted_at.date() <= as_of <= reviewed_at.date()):
        raise _error(
            row_number,
            "chronology",
            "must satisfy period_end <= filing accepted date <= as_of <= reviewed date",
        )
    if accepted_at > reviewed_at:
        raise _error(
            row_number, "chronology", "review cannot predate filing acceptance"
        )

    accession = cells["filing_accession"]
    if _ACCESSION_RE.fullmatch(accession) is None:
        raise _error(
            row_number,
            "filing_accession",
            "must use the canonical 10-2-6 dashed SEC accession form",
        )
    source_type = cells["source_type"]
    if source_type not in MANUAL_SOURCE_TYPES:
        raise _error(row_number, "source_type", "is not an allowed SEC filing type")
    _official_source_url(
        cells["source_url"],
        company_id=company_id,
        accession=accession,
        row_number=row_number,
    )

    value = _number(
        cells["value"], row_number=row_number, field="value", nonnegative=True
    )
    unit = cells["unit"] or None
    if value is None and unit is not None:
        raise _error(row_number, "unit", "must be empty when value is null")
    if value is not None and unit not in MANUAL_VALUE_UNITS:
        raise _error(
            row_number,
            "unit",
            "must use an exact allowlisted unit when value is present",
        )
    yoy_pct = _number(cells["yoy_pct"], row_number=row_number, field="yoy_pct")
    comparable_cell = cells["comparable"]
    if comparable_cell not in {"true", "false"}:
        raise _error(row_number, "comparable", "must be exactly true or false")
    comparable = comparable_cell == "true"
    if yoy_pct is not None and not comparable:
        raise _error(
            row_number,
            "yoy_pct",
            "must be null when comparable is false",
        )

    reviewer = _short_text(
        cells["reviewer"], row_number=row_number, field="reviewer", maximum=80
    )
    paraphrase = _short_text(
        cells["paraphrase"], row_number=row_number, field="paraphrase", maximum=280
    )
    review_note = _short_text(
        cells["review_note"], row_number=row_number, field="review_note", maximum=500
    )

    return ManualSignal(
        company_id=company_id,
        period_end=period_end.isoformat(),
        metric_id=metric_id,
        direction=direction,
        value=value,
        unit=unit,
        yoy_pct=yoy_pct,
        comparable=comparable,
        source_type=source_type,
        source_url=cells["source_url"],
        filing_accession=accession,
        filing_accepted_at=_canonical_utc_timestamp(accepted_at),
        as_of=as_of.isoformat(),
        reviewer=reviewer,
        reviewed_at=_canonical_utc_timestamp(reviewed_at),
        paraphrase=paraphrase,
        review_note=review_note,
    )


def validate_manual_signals(
    rows: Iterable[Mapping[str, str]],
    *,
    first_row_number: int = 2,
) -> tuple[ManualSignal, ...]:
    """Validate records, reject duplicate identities, and sort deterministically."""

    records: list[ManualSignal] = []
    seen: dict[tuple[str, str, str, str], int] = {}
    for offset, row in enumerate(rows):
        row_number = first_row_number + offset
        record = validate_manual_signal_row(row, row_number=row_number)
        if record.identity in seen:
            raise _error(
                row_number,
                "identity",
                f"duplicates row {seen[record.identity]}",
            )
        seen[record.identity] = row_number
        records.append(record)
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.metric_id,
                record.company_id,
                record.period_end,
                record.filing_accepted_at,
                record.filing_accession,
            ),
        )
    )


def load_manual_signals(
    path: str | Path = DEFAULT_MANUAL_SIGNALS_PATH,
) -> tuple[ManualSignal, ...]:
    """Load the exact 17-column CSV; a header-only template is valid."""

    source = Path(path)
    try:
        handle = source.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        raise ManualSignalValidationError(f"cannot read {source}: {exc}") from exc
    with handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ManualSignalValidationError(
                f"{source} must contain the exact 17-column header"
            ) from exc
        if tuple(header) != MANUAL_SIGNAL_COLUMNS:
            raise ManualSignalValidationError(
                f"{source} header must exactly equal {','.join(MANUAL_SIGNAL_COLUMNS)}"
            )
        rows: list[dict[str, str]] = []
        for row_number, values in enumerate(reader, start=2):
            if not values or all(value == "" for value in values):
                raise ManualSignalValidationError(
                    f"row {row_number}: blank rows are not allowed"
                )
            if len(values) != len(MANUAL_SIGNAL_COLUMNS):
                raise ManualSignalValidationError(
                    f"row {row_number}: expected 17 columns, found {len(values)}"
                )
            rows.append(dict(zip(MANUAL_SIGNAL_COLUMNS, values, strict=True)))
    return validate_manual_signals(rows)


def _latest_records_as_of(
    records: Sequence[ManualSignal], *, as_of: str
) -> tuple[ManualSignal, ...]:
    latest_by_company: dict[str, ManualSignal] = {}
    aggregate_date = date.fromisoformat(as_of)
    for record in records:
        if record.as_of > as_of:
            continue
        if (
            aggregate_date - date.fromisoformat(record.as_of)
        ).days > MANUAL_EVIDENCE_MAX_AGE_DAYS:
            continue
        current = latest_by_company.get(record.company_id)
        if current is None or (
            record.as_of,
            record.period_end,
            record.filing_accepted_at,
            record.reviewed_at,
            record.filing_accession,
        ) > (
            current.as_of,
            current.period_end,
            current.filing_accepted_at,
            current.reviewed_at,
            current.filing_accession,
        ):
            latest_by_company[record.company_id] = record
    return tuple(
        latest_by_company[company_id] for company_id in sorted(latest_by_company)
    )


def _manual_direction(records: Sequence[ManualSignal]) -> str:
    comparable = [record.direction for record in records if record.comparable]
    if not comparable or "UNKNOWN" in comparable:
        return "UNKNOWN"
    directions = set(comparable)
    return next(iter(directions)) if len(directions) == 1 else "MIXED"


def build_manual_metric_observations(
    records: Sequence[ManualSignal], metric_id: str
) -> tuple[dict[str, Any], ...]:
    """Build one lossless aggregate point per as-of date.

    The aggregate has no numeric value because manual disclosures can use
    mixed units.  Exact reviewed values, including true zeroes, remain nested
    in the latest-per-company 17-field records.
    """

    if metric_id not in P3_MANUAL_METRIC_IDS:
        raise ManualSignalValidationError(
            f"{metric_id} is not a canonical P3 manual metric ID"
        )
    selected = tuple(record for record in records if record.metric_id == metric_id)
    observations: list[dict[str, Any]] = []
    for as_of in sorted({record.as_of for record in selected}):
        latest = _latest_records_as_of(selected, as_of=as_of)
        observations.append(
            {
                "date": as_of,
                "value": None,
                "direction": _manual_direction(latest),
                "record_count": len(latest),
                "company_count": len({record.company_id for record in latest}),
                "comparable_count": sum(record.comparable for record in latest),
                "records": [record.as_public_record() for record in latest],
            }
        )
    return tuple(observations)


def build_manual_metric_states(
    records: Sequence[ManualSignal],
) -> dict[str, dict[str, Any]]:
    """Build deterministic, integration-ready state for all three manual metrics."""

    output: dict[str, dict[str, Any]] = {}
    for metric_id in P3_MANUAL_METRIC_IDS:
        observations = build_manual_metric_observations(records, metric_id)
        latest = observations[-1] if observations else None
        latest_records = latest["records"] if latest is not None else []
        latest_filing_accepted_at = max(
            (record["filing_accepted_at"] for record in latest_records), default=None
        )
        latest_reviewed_at = max(
            (record["reviewed_at"] for record in latest_records), default=None
        )
        manual_evidence = {
            "source_id": "manual_public_filings",
            "network_enabled": False,
            "observation_date": latest["date"] if latest is not None else None,
            "direction": latest["direction"] if latest is not None else "UNKNOWN",
            "record_count": latest["record_count"] if latest is not None else 0,
            "company_count": latest["company_count"] if latest is not None else 0,
            "comparable_count": (
                latest["comparable_count"] if latest is not None else 0
            ),
            "latest_filing_accepted_at": latest_filing_accepted_at,
            "latest_reviewed_at": latest_reviewed_at,
            "records": latest_records,
        }
        output[metric_id] = {
            "metric_id": metric_id,
            "availability": "ACTIVE_FREE" if observations else "MANUAL_READY",
            "network_enabled": False,
            "source_id": "manual_public_filings",
            "observation_date": latest["date"] if latest is not None else None,
            "latest_as_of": latest["date"] if latest is not None else None,
            "latest_filing_accepted_at": latest_filing_accepted_at,
            "latest_reviewed_at": latest_reviewed_at,
            "released_at": latest_filing_accepted_at,
            "updated_at": latest_reviewed_at,
            "last_success_at": latest_reviewed_at,
            "record_count": manual_evidence["record_count"],
            "company_count": manual_evidence["company_count"],
            "comparable_count": manual_evidence["comparable_count"],
            "direction": manual_evidence["direction"],
            "observations": list(observations),
            "details": {"manual_evidence": manual_evidence},
        }
    return output
