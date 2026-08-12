"""Privacy-minimized, deterministic SEC Form 4 accession ledger.

Only accession-level transaction aggregates required by the P2 proxy are
serialised.  Reporting-owner names, addresses, signatures, security titles,
and complete submission text are intentionally absent.  Callers may write the
ledger under a staged data directory and promote it with the existing snapshot
publication after every contract gate passes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
import uuid

from pipeline.collectors.common import CollectorError
from pipeline.collectors.sec_form4 import ParsedForm4, ParsedTransaction


LEDGER_SCHEMA_VERSION = "1.0.0"
RETENTION_CALENDAR_DAYS = 45
EFFECTIVE_STATUSES = frozenset({"ORIGINAL_EFFECTIVE", "AMENDMENT_EFFECTIVE"})
PUBLIC_ENTRY_KEYS = frozenset(
    {
        "accession",
        "acceptance_at",
        "amendment_status",
        "anomaly_codes",
        "excluded_transaction_count",
        "filing_date",
        "filing_10b5_status",
        "form_type",
        "index_date",
        "issuer_cik",
        "linked_original_accession",
        "missing_price_count",
        "original_submission_date",
        "ownership_document_sha256",
        "parse_status",
        "period_of_report",
        "owner_cik_set_hash",
        "eligible_transaction_fingerprints",
        "eligible_transactions_hash",
        "submission_sha256",
        "tenb5_flags_present",
        "totals",
    }
)
TOTAL_KEYS = frozenset(
    {
        "eligible_transaction_count",
        "priced_transaction_count",
        "purchase_count",
        "purchase_dollars",
        "purchase_priced_count",
        "purchase_shares",
        "sale_count",
        "sale_dollars",
        "sale_priced_count",
        "sale_shares",
    }
)
PLAN_BUCKETS = ("ALL", "FALSE", "TRUE", "UNKNOWN")
PRIVATE_KEY_MARKERS = (
    "address",
    "company_name",
    "owner_name",
    "reporting_owner",
    "security_title",
    "signature",
    "raw",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise CollectorError("ledger decimal must be finite")
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CollectorError(f"{field} is not a decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise CollectorError(f"{field} is outside its valid domain")
    return parsed


def _empty_totals() -> dict[str, int | Decimal]:
    return {
        "eligible_transaction_count": 0,
        "priced_transaction_count": 0,
        "purchase_count": 0,
        "purchase_dollars": Decimal("0"),
        "purchase_priced_count": 0,
        "purchase_shares": Decimal("0"),
        "sale_count": 0,
        "sale_dollars": Decimal("0"),
        "sale_priced_count": 0,
        "sale_shares": Decimal("0"),
    }


def _add_transaction(bucket: dict[str, int | Decimal], row: ParsedTransaction) -> None:
    side = "purchase" if row.code == "P" else "sale"
    bucket["eligible_transaction_count"] = int(bucket["eligible_transaction_count"]) + 1
    bucket[f"{side}_count"] = int(bucket[f"{side}_count"]) + 1
    bucket[f"{side}_shares"] = Decimal(bucket[f"{side}_shares"]) + row.shares
    if row.dollar_value is not None:
        bucket["priced_transaction_count"] = int(bucket["priced_transaction_count"]) + 1
        bucket[f"{side}_priced_count"] = int(bucket[f"{side}_priced_count"]) + 1
        bucket[f"{side}_dollars"] = Decimal(bucket[f"{side}_dollars"]) + row.dollar_value


def _serialize_totals(bucket: Mapping[str, int | Decimal]) -> dict[str, int | str]:
    return {
        key: _decimal_text(value) if isinstance(value, Decimal) else int(value)
        for key, value in sorted(bucket.items())
    }


def public_ledger_entry(filing: ParsedForm4) -> dict[str, Any]:
    """Reduce a parsed filing to an explicitly allowlisted public record."""

    buckets = {name: _empty_totals() for name in PLAN_BUCKETS}
    flags: set[str] = set()
    for transaction in filing.transactions:
        if transaction.code not in {"P", "S"}:
            raise CollectorError("ledger received a non-P/S eligible transaction")
        if transaction.plan_10b5 not in {"FALSE", "TRUE", "UNKNOWN"}:
            raise CollectorError("ledger received an invalid 10b5 flag")
        _add_transaction(buckets["ALL"], transaction)
        _add_transaction(buckets[transaction.plan_10b5], transaction)
        flags.add(transaction.plan_10b5)
    record = {
        "accession": filing.accession,
        "acceptance_at": filing.acceptance_at,
        "amendment_status": "PENDING_RESOLUTION",
        "anomaly_codes": list(filing.anomaly_codes),
        "excluded_transaction_count": filing.excluded_transaction_count,
        "filing_date": filing.filing_date,
        "filing_10b5_status": filing.filing_plan_10b5,
        "form_type": filing.form_type,
        "index_date": filing.index_date,
        "issuer_cik": filing.issuer_cik,
        "linked_original_accession": None,
        "missing_price_count": filing.missing_price_count,
        "original_submission_date": filing.original_submission_date,
        "ownership_document_sha256": filing.ownership_document_sha256,
        "parse_status": filing.parse_status,
        "period_of_report": filing.period_of_report,
        "owner_cik_set_hash": filing.reporting_owner_ciks_hash,
        "eligible_transaction_fingerprints": list(
            filing.eligible_transaction_fingerprints
        ),
        "eligible_transactions_hash": filing.eligible_transactions_hash,
        "submission_sha256": filing.submission_sha256,
        "tenb5_flags_present": sorted(flags),
        "totals": {name: _serialize_totals(buckets[name]) for name in PLAN_BUCKETS},
    }
    validate_public_entry(record, allow_pending=True)
    return record


def resolve_amendments(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply the conservative unique-link rule for Form 4/A.

    An amendment links only when its structured ``dateOfOriginalSubmission``,
    issuer CIK, reporting-owner CIK-set hash, period of report, and normalized
    eligible-transaction tuple identify exactly one original Form 4. No name,
    amount, or nearest-date inference is permitted. If multiple amendments
    uniquely link to one original, only the latest accepted amendment remains
    effective.
    """

    records = [dict(entry) for entry in entries]
    for record in records:
        validate_public_entry(record, allow_pending=True)
    originals = [record for record in records if record["form_type"] == "4"]
    amendments = [record for record in records if record["form_type"] == "4/A"]
    for original in originals:
        original["amendment_status"] = "ORIGINAL_EFFECTIVE"
        original["linked_original_accession"] = None
    linked: dict[str, list[dict[str, Any]]] = {}
    for amendment in amendments:
        amendment["linked_original_accession"] = None
        original_date = amendment.get("original_submission_date")
        candidates = [
            original
            for original in originals
            if original_date is not None
            and original["issuer_cik"] == amendment["issuer_cik"]
            and original["filing_date"] == original_date
            and original.get("period_of_report") is not None
            and original.get("period_of_report") == amendment.get("period_of_report")
            and original.get("owner_cik_set_hash")
            == amendment.get("owner_cik_set_hash")
            and original.get("eligible_transactions_hash")
            == amendment.get("eligible_transactions_hash")
            and original.get("eligible_transaction_fingerprints")
            == amendment.get("eligible_transaction_fingerprints")
        ]
        if len(candidates) != 1:
            amendment["amendment_status"] = "UNLINKED_REVIEW"
            continue
        original = candidates[0]
        amendment["linked_original_accession"] = original["accession"]
        linked.setdefault(original["accession"], []).append(amendment)
    by_accession = {record["accession"]: record for record in originals}
    for original_accession, group in linked.items():
        original = by_accession[original_accession]
        original["amendment_status"] = "ORIGINAL_SUPERSEDED"
        ordered = sorted(group, key=lambda row: (row["acceptance_at"], row["accession"]))
        for amendment in ordered[:-1]:
            amendment["amendment_status"] = "AMENDMENT_SUPERSEDED"
        ordered[-1]["amendment_status"] = "AMENDMENT_EFFECTIVE"
    resolved = sorted(records, key=lambda row: (row["index_date"], row["accession"]))
    for record in resolved:
        validate_public_entry(record)
    return resolved


def prune_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
    retention_days: int = RETENTION_CALENDAR_DAYS,
) -> list[dict[str, Any]]:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    cutoff = as_of - timedelta(days=retention_days - 1)
    kept: list[dict[str, Any]] = []
    for entry in entries:
        try:
            index_day = date.fromisoformat(str(entry["index_date"]))
        except (KeyError, ValueError) as exc:
            raise CollectorError("ledger entry has invalid index_date") from exc
        if cutoff <= index_day <= as_of:
            kept.append(dict(entry))
    return sorted(kept, key=lambda row: (row["index_date"], row["accession"]))


def merge_last_good_entries(
    prior: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
    *,
    completed_index_days: Iterable[str],
    as_of: date,
    master_accessions_by_day: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    """Merge successful index days while preserving incomplete last-good days."""

    completed = set(completed_index_days)
    for value in completed:
        date.fromisoformat(value)
    master_membership = (
        {day: set(accessions) for day, accessions in master_accessions_by_day.items()}
        if master_accessions_by_day is not None
        else None
    )
    if master_membership is not None and set(master_membership) != completed:
        raise CollectorError(
            "master_accessions_by_day must exactly cover completed index days"
        )
    retained_completed: dict[str, dict[str, Any]] = {}
    if master_membership is not None:
        for entry in prior:
            day = str(entry.get("index_date"))
            accession = str(entry.get("accession"))
            if day in completed and accession in master_membership[day]:
                retained_completed[accession] = dict(entry)
    merged = {
        str(entry["accession"]): dict(entry)
        for entry in prior
        if str(entry.get("index_date")) not in completed
    }
    merged.update(retained_completed)
    for entry in current:
        if str(entry.get("index_date")) not in completed:
            continue
        accession = str(entry["accession"])
        if accession in merged and merged[accession] != entry:
            raise CollectorError(f"conflicting ledger accession {accession}")
        merged[accession] = dict(entry)
    return prune_entries(resolve_amendments(list(merged.values())), as_of=as_of)


def _privacy_walk(value: Any, path: str = "ledger") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in PRIVATE_KEY_MARKERS):
                raise CollectorError(f"privacy-prohibited ledger key at {path}.{key}")
            _privacy_walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _privacy_walk(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if "<sec-document" in lowered or "<ownershipdocument" in lowered:
            raise CollectorError(f"raw filing text is prohibited at {path}")


def validate_public_entry(
    entry: Mapping[str, Any], *, allow_pending: bool = False
) -> None:
    if set(entry) != PUBLIC_ENTRY_KEYS:
        missing = sorted(PUBLIC_ENTRY_KEYS - set(entry))
        extra = sorted(set(entry) - PUBLIC_ENTRY_KEYS)
        raise CollectorError(f"ledger entry key mismatch; missing={missing}, extra={extra}")
    if entry["form_type"] not in {"4", "4/A"}:
        raise CollectorError("ledger form_type must be exact 4 or 4/A")
    if not isinstance(entry["accession"], str) or not re.fullmatch(
        r"\d{10}-\d{2}-\d{6}", entry["accession"]
    ):
        raise CollectorError("ledger accession is invalid")
    if not isinstance(entry["issuer_cik"], str) or not entry["issuer_cik"].isdigit():
        raise CollectorError("ledger issuer_cik is invalid")
    for field in ("filing_date", "index_date"):
        try:
            date.fromisoformat(str(entry[field]))
        except ValueError as exc:
            raise CollectorError(f"ledger {field} is invalid") from exc
    for field in ("period_of_report", "original_submission_date"):
        if entry[field] is not None:
            try:
                date.fromisoformat(str(entry[field]))
            except ValueError as exc:
                raise CollectorError(f"ledger {field} is invalid") from exc
    if entry["parse_status"] not in {"PARSED", "PARSED_WITH_QUARANTINED_ROWS"}:
        raise CollectorError("ledger parse_status is invalid")
    if entry["filing_10b5_status"] not in {"FALSE", "TRUE", "UNKNOWN"}:
        raise CollectorError("ledger filing_10b5_status is invalid")
    allowed_statuses = {
        "ORIGINAL_EFFECTIVE",
        "ORIGINAL_SUPERSEDED",
        "AMENDMENT_EFFECTIVE",
        "AMENDMENT_SUPERSEDED",
        "UNLINKED_REVIEW",
    }
    if allow_pending:
        allowed_statuses.add("PENDING_RESOLUTION")
    if entry["amendment_status"] not in allowed_statuses:
        raise CollectorError("ledger amendment_status is invalid")
    for key in (
        "submission_sha256",
        "ownership_document_sha256",
        "owner_cik_set_hash",
        "eligible_transactions_hash",
    ):
        if not isinstance(entry[key], str) or not re_full_sha256(entry[key]):
            raise CollectorError(f"ledger {key} must be SHA-256")
    fingerprints = entry["eligible_transaction_fingerprints"]
    if (
        not isinstance(fingerprints, list)
        or fingerprints != sorted(fingerprints)
        or any(not isinstance(value, str) or not re_full_sha256(value) for value in fingerprints)
    ):
        raise CollectorError("ledger eligible_transaction_fingerprints are invalid")
    expected_transaction_hash = hashlib.sha256(
        "\n".join(fingerprints).encode("ascii")
    ).hexdigest()
    if entry["eligible_transactions_hash"] != expected_transaction_hash:
        raise CollectorError("ledger eligible transaction hash does not reconcile")
    totals = entry["totals"]
    if not isinstance(totals, Mapping) or set(totals) != set(PLAN_BUCKETS):
        raise CollectorError("ledger totals must contain all 10b5 buckets")
    for bucket_name, bucket in totals.items():
        if not isinstance(bucket, Mapping) or set(bucket) != TOTAL_KEYS:
            raise CollectorError(f"ledger totals.{bucket_name} key mismatch")
        for key, raw in bucket.items():
            if key.endswith("count"):
                if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                    raise CollectorError(f"ledger totals.{bucket_name}.{key} must be integer")
            else:
                _decimal(raw, field=f"totals.{bucket_name}.{key}")
        if bucket["eligible_transaction_count"] != (
            bucket["purchase_count"] + bucket["sale_count"]
        ):
            raise CollectorError(f"ledger totals.{bucket_name} eligible count mismatch")
        if bucket["priced_transaction_count"] != (
            bucket["purchase_priced_count"] + bucket["sale_priced_count"]
        ):
            raise CollectorError(f"ledger totals.{bucket_name} priced count mismatch")
        if bucket["purchase_priced_count"] > bucket["purchase_count"] or bucket[
            "sale_priced_count"
        ] > bucket["sale_count"]:
            raise CollectorError(f"ledger totals.{bucket_name} priced count exceeds count")
    all_bucket = totals["ALL"]
    for field in TOTAL_KEYS:
        components = [totals[name][field] for name in ("FALSE", "TRUE", "UNKNOWN")]
        if field.endswith("count"):
            if all_bucket[field] != sum(components):
                raise CollectorError(f"ledger ALL.{field} does not match 10b5 buckets")
        elif _decimal(all_bucket[field], field=f"ALL.{field}") != sum(
            (_decimal(value, field=f"component.{field}") for value in components),
            Decimal("0"),
        ):
            raise CollectorError(f"ledger ALL.{field} does not match 10b5 buckets")
    if entry["missing_price_count"] != (
        all_bucket["eligible_transaction_count"]
        - all_bucket["priced_transaction_count"]
    ):
        raise CollectorError("ledger missing_price_count does not reconcile")
    expected_flags = sorted(
        name
        for name in ("FALSE", "TRUE", "UNKNOWN")
        if totals[name]["eligible_transaction_count"] > 0
    )
    if entry["tenb5_flags_present"] != expected_flags:
        raise CollectorError("ledger tenb5_flags_present does not match buckets")
    nonempty_plan_buckets = [
        name
        for name in ("FALSE", "TRUE", "UNKNOWN")
        if totals[name]["eligible_transaction_count"] > 0
    ]
    if nonempty_plan_buckets and nonempty_plan_buckets != [entry["filing_10b5_status"]]:
        raise CollectorError("ledger 10b5 buckets must match the filing-level flag")
    _privacy_walk(entry)


def re_full_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def build_ledger_package(
    entries: Sequence[Mapping[str, Any]],
    *,
    completed_index_days: Iterable[str],
    as_of: date,
    failures: Sequence[Mapping[str, Any]] = (),
    reviews: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    pruned = prune_entries(entries, as_of=as_of)
    for entry in pruned:
        validate_public_entry(entry)
    completed = sorted(
        day
        for day in set(completed_index_days)
        if as_of - timedelta(days=RETENTION_CALENDAR_DAYS - 1)
        <= date.fromisoformat(day)
        <= as_of
    )
    audit_cutoff = as_of - timedelta(days=RETENTION_CALENDAR_DAYS - 1)

    def validated_audit_rows(
        values: Sequence[Mapping[str, Any]], *, field: str
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in values:
            if not isinstance(raw, Mapping):
                raise CollectorError(f"ledger {field} entry must be an object")
            row = dict(raw)
            raw_day = row.get("index_date")
            if not isinstance(raw_day, str):
                raise CollectorError(f"ledger {field} entry requires index_date")
            try:
                day = date.fromisoformat(raw_day)
            except ValueError as exc:
                raise CollectorError(
                    f"ledger {field} entry has invalid index_date"
                ) from exc
            if not audit_cutoff <= day <= as_of:
                continue
            if not isinstance(row.get("stage"), str) or not row["stage"]:
                raise CollectorError(f"ledger {field} entry requires stage")
            if not isinstance(row.get("reason"), str) or not row["reason"]:
                raise CollectorError(f"ledger {field} entry requires reason")
            rows.append(row)
        return sorted(rows, key=canonical_json_bytes)

    package = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "as_of": as_of.isoformat(),
        "retention_calendar_days": RETENTION_CALENDAR_DAYS,
        "completed_index_days": completed,
        "entries": pruned,
        "failures": validated_audit_rows(failures, field="failures"),
        "reviews": validated_audit_rows(reviews, field="reviews"),
    }
    _privacy_walk(package)
    return package


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_ledger_atomic(
    target: Path | str,
    package: Mapping[str, Any],
    *,
    replace: Any = os.replace,
) -> dict[str, Any]:
    """Write deterministic daily shards and promote the directory atomically."""

    target_path = Path(target)
    parent = target_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = parent / f".{target_path.name}-stage-{uuid.uuid4().hex}"
    backup = parent / f".{target_path.name}-backup-{uuid.uuid4().hex}"
    required_package_keys = {
        "schema_version",
        "as_of",
        "retention_calendar_days",
        "completed_index_days",
        "entries",
        "failures",
        "reviews",
    }
    if set(package) != required_package_keys:
        raise CollectorError("ledger package key mismatch")
    try:
        package_as_of = date.fromisoformat(str(package.get("as_of")))
    except ValueError as exc:
        raise CollectorError("ledger package as_of is invalid") from exc
    entries = package.get("entries")
    if not isinstance(entries, list):
        raise CollectorError("ledger package entries must be a list")
    canonical_package = build_ledger_package(
        entries,
        completed_index_days=package.get("completed_index_days", ()),
        as_of=package_as_of,
        failures=package.get("failures", ()),
        reviews=package.get("reviews", ()),
    )
    if dict(package) != canonical_package:
        raise CollectorError("ledger package is not canonical")
    package = canonical_package
    _privacy_walk(package)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise CollectorError("ledger entry must be an object")
        validate_public_entry(raw)
        grouped.setdefault(str(raw["index_date"]), []).append(dict(raw))
    moved_old = False
    manifest: dict[str, Any] = {}
    try:
        stage.mkdir()
        shard_hashes: dict[str, str] = {}
        for day in sorted(grouped):
            records = sorted(grouped[day], key=lambda row: row["accession"])
            shard = {"index_date": day, "entries": records}
            relative = f"shards/{day}.json"
            data = canonical_json_bytes(shard)
            _atomic_write(stage / relative, data)
            shard_hashes[relative] = hashlib.sha256(data).hexdigest()
        manifest = {
            "schema_version": package.get("schema_version"),
            "as_of": package.get("as_of"),
            "retention_calendar_days": package.get("retention_calendar_days"),
            "completed_index_days": package.get("completed_index_days", []),
            "entry_count": len(entries),
            "failures": package.get("failures", []),
            "reviews": package.get("reviews", []),
            "shards": shard_hashes,
        }
        manifest["ledger_sha256"] = canonical_sha256(manifest)
        _atomic_write(stage / "manifest.json", canonical_json_bytes(manifest))
        if target_path.exists():
            replace(target_path, backup)
            moved_old = True
        replace(stage, target_path)
    except BaseException:
        if moved_old and backup.exists() and not target_path.exists():
            replace(backup, target_path)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    if backup.exists():
        shutil.rmtree(backup)
    return manifest


def load_ledger(target: Path | str) -> dict[str, Any]:
    target_path = Path(target)
    try:
        manifest = json.loads((target_path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectorError("Form 4 ledger manifest is unreadable") from exc
    if not isinstance(manifest, Mapping):
        raise CollectorError("Form 4 ledger manifest must be an object")
    required_manifest_keys = {
        "schema_version",
        "as_of",
        "retention_calendar_days",
        "completed_index_days",
        "entry_count",
        "failures",
        "reviews",
        "shards",
        "ledger_sha256",
    }
    if set(manifest) != required_manifest_keys:
        raise CollectorError("Form 4 ledger manifest key mismatch")
    if manifest.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise CollectorError("Form 4 ledger schema_version is invalid")
    if manifest.get("retention_calendar_days") != RETENTION_CALENDAR_DAYS:
        raise CollectorError("Form 4 ledger retention policy is invalid")
    try:
        as_of = date.fromisoformat(str(manifest.get("as_of")))
    except ValueError as exc:
        raise CollectorError("Form 4 ledger as_of is invalid") from exc
    completed = manifest.get("completed_index_days")
    if not isinstance(completed, list) or completed != sorted(set(completed)):
        raise CollectorError("Form 4 ledger completed_index_days are invalid")
    cutoff = as_of - timedelta(days=RETENTION_CALENDAR_DAYS - 1)
    for raw_day in completed:
        try:
            day = date.fromisoformat(str(raw_day))
        except ValueError as exc:
            raise CollectorError(
                "Form 4 ledger completed index day is invalid"
            ) from exc
        if not cutoff <= day <= as_of:
            raise CollectorError("Form 4 ledger completed index day is out of range")
    expected_ledger_hash = manifest.get("ledger_sha256")
    unsigned = dict(manifest)
    unsigned.pop("ledger_sha256", None)
    if expected_ledger_hash != canonical_sha256(unsigned):
        raise CollectorError("Form 4 ledger manifest hash mismatch")
    entries: list[dict[str, Any]] = []
    shards = manifest.get("shards")
    if not isinstance(shards, Mapping):
        raise CollectorError("Form 4 ledger manifest shards must be an object")
    expected_files = {"manifest.json", *(str(relative) for relative in shards)}
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for path in target_path.rglob("*"):
        if path.is_symlink():
            raise CollectorError("Form 4 ledger must not contain symlinks")
        if path.is_file():
            actual_files.add(path.relative_to(target_path).as_posix())
        elif path.is_dir():
            actual_directories.add(path.relative_to(target_path).as_posix())
    if actual_files != expected_files:
        raise CollectorError("Form 4 ledger contains undeclared or missing files")
    expected_directories = {"shards"} if shards else set()
    if actual_directories != expected_directories:
        raise CollectorError("Form 4 ledger contains unexpected directories")
    seen_accessions: set[str] = set()
    for relative, expected_hash in sorted(shards.items()):
        relative_text = str(relative)
        match = re.fullmatch(r"shards/(\d{4}-\d{2}-\d{2})\.json", relative_text)
        if match is None or match.group(1) not in completed:
            raise CollectorError("Form 4 ledger shard path is invalid")
        path = target_path / relative_text
        try:
            data = path.read_bytes()
            shard = json.loads(data)
        except (OSError, json.JSONDecodeError) as exc:
            raise CollectorError(f"Form 4 ledger shard {relative} is unreadable") from exc
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise CollectorError(f"Form 4 ledger shard {relative} hash mismatch")
        if (
            not isinstance(shard, Mapping)
            or set(shard) != {"index_date", "entries"}
            or shard.get("index_date") != match.group(1)
            or not isinstance(shard.get("entries"), list)
        ):
            raise CollectorError(f"Form 4 ledger shard {relative} has wrong schema")
        for raw in shard["entries"]:
            if not isinstance(raw, Mapping):
                raise CollectorError("Form 4 ledger shard entry must be an object")
            validate_public_entry(raw)
            if raw.get("index_date") != shard["index_date"]:
                raise CollectorError("Form 4 ledger entry is in the wrong shard")
            accession = str(raw["accession"])
            if accession in seen_accessions:
                raise CollectorError("Form 4 ledger contains duplicate accession")
            seen_accessions.add(accession)
            entries.append(dict(raw))
    if len(entries) != manifest.get("entry_count"):
        raise CollectorError("Form 4 ledger entry count mismatch")
    package = dict(unsigned)
    package.pop("entry_count", None)
    package.pop("shards", None)
    package["entries"] = sorted(entries, key=lambda row: (row["index_date"], row["accession"]))
    # Rebuild through the same contract gate to validate audit rows and dates.
    package = build_ledger_package(
        package["entries"],
        completed_index_days=package["completed_index_days"],
        as_of=as_of,
        failures=package["failures"],
        reviews=package["reviews"],
    )
    _privacy_walk(package)
    return package


__all__ = [
    "EFFECTIVE_STATUSES",
    "LEDGER_SCHEMA_VERSION",
    "RETENTION_CALENDAR_DAYS",
    "build_ledger_package",
    "canonical_sha256",
    "load_ledger",
    "merge_last_good_entries",
    "prune_entries",
    "public_ledger_entry",
    "resolve_amendments",
    "validate_public_entry",
    "write_ledger_atomic",
]
