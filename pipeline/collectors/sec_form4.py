"""Fail-closed SEC EDGAR Form 4 collector and ownership-XML parser.

The collector deliberately starts from the official daily ``master`` indexes,
then downloads the complete submission text exactly once per deduplicated
accession.  It does not use issuer feeds (which can silently omit filings from
other issuers) and it never infers a Form 4 amendment relationship from names
or transaction amounts.

Network access is injectable so fixture tests can exercise retries, caching and
rate limiting without contacting SEC systems.  Raw submissions may be kept in
the caller-selected *private* cache; public ledger serialization lives in
``pipeline.form4_ledger`` and contains no raw filing text or reporting-owner
identity fields.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
import zlib

from .common import CollectorError, DEFAULT_USER_AGENT


SEC_ARCHIVES = "https://www.sec.gov/Archives"
DAILY_INDEX_ROOT = f"{SEC_ARCHIVES}/edgar/daily-index"
FORM_TYPES = frozenset({"4", "4/A"})
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
ACCESSION_RE = re.compile(r"(?P<accession>\d{10}-\d{2}-\d{6})\.txt$")
MASTER_NAME_RE = re.compile(r"^master\.(?P<day>\d{8})\.idx$")
MAX_BODY_BYTES = 40 * 1024 * 1024
DEFAULT_TIMEOUT = 30.0
DEFAULT_ATTEMPTS = 4
DEFAULT_RATE_PER_SECOND = 4.0


def _utc_string(value: datetime) -> str:
    if value.tzinfo is None:
        raise CollectorError("timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _quarter(day: date) -> int:
    return (day.month - 1) // 3 + 1


def _quarter_starts(start: date, end: date) -> Iterable[tuple[int, int]]:
    if end < start:
        raise CollectorError("end date must not precede start date")
    year, quarter = start.year, _quarter(start)
    last = (end.year, _quarter(end))
    while (year, quarter) <= last:
        yield year, quarter
        if quarter == 4:
            year, quarter = year + 1, 1
        else:
            quarter += 1


@dataclass(frozen=True)
class FetchResult:
    url: str
    body: bytes
    sha256: str
    content_type: str
    fetched_at: str
    from_cache: bool
    status: int


@dataclass(frozen=True)
class FilingIndexEntry:
    accession: str
    cik: str
    form_type: str
    filing_date: str
    index_date: str
    archive_path: str

    @property
    def submission_url(self) -> str:
        return f"{SEC_ARCHIVES}/{self.archive_path.lstrip('/')}"


@dataclass(frozen=True)
class ParsedTransaction:
    transaction_date: str
    code: str
    acquired_disposed: str
    shares: Decimal
    price_per_share: Decimal | None
    dollar_value: Decimal | None
    plan_10b5: str
    fingerprint: str


@dataclass(frozen=True)
class ParsedForm4:
    accession: str
    form_type: str
    filing_date: str
    index_date: str
    acceptance_at: str
    issuer_cik: str
    reporting_owner_ciks: tuple[str, ...]
    reporting_owner_ciks_hash: str
    period_of_report: str | None
    original_submission_date: str | None
    filing_plan_10b5: str
    submission_sha256: str
    ownership_document_sha256: str
    transactions: tuple[ParsedTransaction, ...]
    eligible_transaction_fingerprints: tuple[str, ...]
    eligible_transactions_hash: str
    excluded_transaction_count: int
    missing_price_count: int
    anomaly_codes: tuple[str, ...] = ()
    parse_status: str = "PARSED"


@dataclass(frozen=True)
class Form4Collection:
    filings: tuple[ParsedForm4, ...]
    reused_ledger_accessions: tuple[str, ...]
    master_accessions_by_day: dict[str, tuple[str, ...]]
    completed_index_days: tuple[str, ...]
    discovered_index_days: tuple[str, ...]
    failures: tuple[dict[str, str], ...]
    reviews: tuple[dict[str, str], ...]
    source_requests: int


class SerializedTokenBucket:
    """A capacity-one token bucket safe across collector threads.

    Capacity one intentionally prevents an initial burst.  SEC asks automated
    clients to stay below its ceiling; this dashboard uses four serialized
    requests per second, leaving ample headroom.
    """

    def __init__(
        self,
        rate_per_second: float = DEFAULT_RATE_PER_SECOND,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0 or rate_per_second > 5:
            raise ValueError("SEC request rate must be in (0, 5]")
        self._interval = 1.0 / rate_per_second
        self._clock = clock
        self._sleep = sleeper
        self._next_at: float | None = None
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            if self._next_at is not None and now < self._next_at:
                self._sleep(self._next_at - now)
                now = self._clock()
            self._next_at = max(now, self._next_at or now) + self._interval


class PrivateResponseCache:
    """Content-addressed private response cache with tamper detection."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.root / f"{key}.body", self.root / f"{key}.json"

    def load(self, url: str) -> tuple[bytes, dict[str, Any]] | None:
        body_path, metadata_path = self._paths(url)
        if not body_path.exists() or not metadata_path.exists():
            return None
        try:
            body = body_path.read_bytes()
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CollectorError("SEC private cache is unreadable") from exc
        if not isinstance(metadata, Mapping) or metadata.get("url") != url:
            raise CollectorError("SEC private cache metadata does not match URL")
        if metadata.get("sha256") != _sha256(body):
            raise CollectorError("SEC private cache content hash mismatch")
        return body, dict(metadata)

    def store(
        self,
        url: str,
        body: bytes,
        *,
        content_type: str,
        fetched_at: str,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        body_path, metadata_path = self._paths(url)
        digest = _sha256(body)
        metadata = {
            "content_type": content_type,
            "etag": etag,
            "fetched_at": fetched_at,
            "last_modified": last_modified,
            "sha256": digest,
            "url": url,
        }
        self._atomic_bytes(body_path, body)
        self._atomic_bytes(
            metadata_path,
            (json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            ),
        )

    @staticmethod
    def _atomic_bytes(path: Path, data: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


class SecHttpClient:
    """Small SEC-only HTTP client with rate, retry and conditional-cache policy."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        cache_dir: Path | str | None = None,
        rate_per_second: float = DEFAULT_RATE_PER_SECOND,
        timeout: float = DEFAULT_TIMEOUT,
        attempts: int = DEFAULT_ATTEMPTS,
        opener: Callable[..., Any] = urllib.request.urlopen,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        resolved_user_agent = user_agent or os.environ.get(
            "SEC_USER_AGENT", DEFAULT_USER_AGENT
        )
        if (
            not isinstance(resolved_user_agent, str)
            or "@" not in resolved_user_agent
            or len(resolved_user_agent) < 12
        ):
            raise ValueError("SEC User-Agent must identify the application and contact")
        if attempts < 1:
            raise ValueError("attempts must be positive")
        self.user_agent = resolved_user_agent
        self.timeout = timeout
        self.attempts = attempts
        self.opener = opener
        self.sleeper = sleeper
        self.now = now
        self.limiter = SerializedTokenBucket(
            rate_per_second, clock=clock, sleeper=sleeper
        )
        self.cache = PrivateResponseCache(cache_dir) if cache_dir is not None else None
        self.request_count = 0

    def get(
        self,
        url: str,
        *,
        expected: str,
        revalidate: bool = True,
    ) -> FetchResult:
        if not url.startswith(f"{SEC_ARCHIVES}/"):
            raise CollectorError("SEC collector refused a non-Archives URL")
        if expected not in {"json", "text", "submission"}:
            raise ValueError("unknown SEC response type")
        cached = self.cache.load(url) if self.cache is not None else None
        if cached is not None and not revalidate:
            body, metadata = cached
            self._validate_body(body, str(metadata["content_type"]), expected)
            return FetchResult(
                url=url,
                body=body,
                sha256=str(metadata["sha256"]),
                content_type=str(metadata["content_type"]),
                fetched_at=str(metadata["fetched_at"]),
                from_cache=True,
                status=200,
            )

        headers = {
            "Accept": "application/json" if expected == "json" else "text/plain, */*;q=0.1",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": self.user_agent,
        }
        if cached is not None:
            _, metadata = cached
            if metadata.get("etag"):
                headers["If-None-Match"] = str(metadata["etag"])
            if metadata.get("last_modified"):
                headers["If-Modified-Since"] = str(metadata["last_modified"])

        last_error: BaseException | None = None
        for attempt in range(self.attempts):
            self.limiter.acquire()
            self.request_count += 1
            request = urllib.request.Request(url, headers=headers)
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    status = int(getattr(response, "status", response.getcode()))
                    raw = response.read(MAX_BODY_BYTES + 1)
                    if len(raw) > MAX_BODY_BYTES:
                        raise CollectorError("SEC response exceeds maximum body size")
                    raw = self._decode_content(
                        raw, response.headers.get("Content-Encoding")
                    )
                    content_type = self._content_type(response.headers)
                    self._validate_body(raw, content_type, expected)
                    fetched_at = _utc_string(self.now())
                    if self.cache is not None:
                        self.cache.store(
                            url,
                            raw,
                            content_type=content_type,
                            fetched_at=fetched_at,
                            etag=response.headers.get("ETag"),
                            last_modified=response.headers.get("Last-Modified"),
                        )
                    return FetchResult(
                        url=url,
                        body=raw,
                        sha256=_sha256(raw),
                        content_type=content_type,
                        fetched_at=fetched_at,
                        from_cache=False,
                        status=status,
                    )
            except urllib.error.HTTPError as exc:
                if exc.code == 304 and cached is not None:
                    body, metadata = cached
                    content_type = str(metadata["content_type"])
                    self._validate_body(body, content_type, expected)
                    return FetchResult(
                        url=url,
                        body=body,
                        sha256=str(metadata["sha256"]),
                        content_type=content_type,
                        fetched_at=str(metadata["fetched_at"]),
                        from_cache=True,
                        status=304,
                    )
                if exc.code == 403:
                    raise CollectorError("SEC returned 403; stop and review access policy") from exc
                last_error = exc
                if exc.code not in RETRYABLE_STATUS or attempt + 1 >= self.attempts:
                    break
                self.sleeper(self._retry_delay(exc.headers.get("Retry-After"), attempt))
            except (CollectorError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if isinstance(exc, CollectorError) or attempt + 1 >= self.attempts:
                    break
                self.sleeper(0.5 * (2**attempt))
        raise CollectorError(
            f"SEC request failed after {min(self.attempts, attempt + 1)} attempts: {last_error}"
        )

    def json_object(self, url: str, *, revalidate: bool = True) -> Mapping[str, Any]:
        result = self.get(url, expected="json", revalidate=revalidate)
        try:
            value = json.loads(result.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectorError("SEC JSON response is invalid") from exc
        if not isinstance(value, Mapping):
            raise CollectorError("SEC JSON root must be an object")
        return value

    @staticmethod
    def _content_type(headers: Any) -> str:
        value = headers.get("Content-Type", "") if headers is not None else ""
        return str(value).split(";", 1)[0].strip().lower()

    @staticmethod
    def _validate_body(body: bytes, content_type: str, expected: str) -> None:
        if not body.strip():
            raise CollectorError("SEC returned an empty response")
        prefix = body.lstrip()[:256].lower()
        if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
            raise CollectorError("SEC returned an HTML error page")
        if expected == "json" and content_type not in {
            "application/json",
            "application/problem+json",
        }:
            raise CollectorError(f"SEC JSON response has content type {content_type!r}")
        if expected in {"text", "submission"} and content_type not in {
            "text/plain",
            "text/html",  # SEC occasionally labels complete SGML text this way.
            "application/octet-stream",
        }:
            raise CollectorError(f"SEC text response has content type {content_type!r}")
        if expected == "submission" and b"<SEC-DOCUMENT" not in body[:4096].upper():
            raise CollectorError("SEC complete submission has the wrong schema")

    @staticmethod
    def _decode_content(body: bytes, encoding: str | None) -> bytes:
        normalized = (encoding or "").strip().lower()
        try:
            if normalized == "gzip":
                decoded = zlib.decompress(body, zlib.MAX_WBITS | 16)
            elif normalized == "deflate":
                try:
                    decoded = zlib.decompress(body)
                except zlib.error:
                    decoded = zlib.decompress(body, -zlib.MAX_WBITS)
            elif normalized in {"", "identity"}:
                decoded = body
            else:
                raise CollectorError(
                    f"SEC response has unsupported content encoding {normalized!r}"
                )
        except zlib.error as exc:
            raise CollectorError("SEC compressed response is invalid") from exc
        if len(decoded) > MAX_BODY_BYTES:
            raise CollectorError("SEC decoded response exceeds maximum body size")
        return decoded

    def _retry_delay(self, value: str | None, attempt: int) -> float:
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(value)
                    now = self.now()
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return max(0.0, (parsed - now).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        return 0.5 * (2**attempt)


def parse_quarter_index(
    payload: Mapping[str, Any], *, start_date: date, end_date: date
) -> list[tuple[str, str]]:
    """Return ``(index_date, URL)`` pairs from an official quarter index JSON."""

    directory = payload.get("directory")
    if not isinstance(directory, Mapping):
        raise CollectorError("SEC quarter index is missing directory")
    items = directory.get("item")
    if not isinstance(items, list):
        raise CollectorError("SEC quarter index is missing directory.item")
    selected: dict[str, str] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise CollectorError("SEC quarter index item must be an object")
        name = item.get("name")
        if not isinstance(name, str):
            raise CollectorError("SEC quarter index item is missing name")
        match = MASTER_NAME_RE.fullmatch(name)
        if match is None:
            continue
        try:
            day = datetime.strptime(match.group("day"), "%Y%m%d").date()
        except ValueError as exc:
            raise CollectorError("SEC master index filename has an invalid date") from exc
        if start_date <= day <= end_date:
            day_text = day.isoformat()
            if day_text in selected:
                raise CollectorError(f"duplicate SEC master index listing for {day_text}")
            selected[day_text] = name
    return [
        (
            day,
            f"{DAILY_INDEX_ROOT}/{date.fromisoformat(day).year}/QTR{_quarter(date.fromisoformat(day))}/{selected[day]}",
        )
        for day in sorted(selected)
    ]


def discover_daily_master_indexes(
    client: SecHttpClient, *, start_date: date, end_date: date
) -> list[tuple[str, str]]:
    discovered: dict[str, str] = {}
    for year, quarter in _quarter_starts(start_date, end_date):
        url = f"{DAILY_INDEX_ROOT}/{year}/QTR{quarter}/index.json"
        payload = client.json_object(url)
        for day, index_url in parse_quarter_index(
            payload, start_date=start_date, end_date=end_date
        ):
            if day in discovered and discovered[day] != index_url:
                raise CollectorError(f"conflicting master index URLs for {day}")
            discovered[day] = index_url
    return sorted(discovered.items())


def parse_master_index(body: bytes | str, *, index_date: str) -> list[FilingIndexEntry]:
    """Parse exact Form 4 and 4/A rows from a daily EDGAR master index."""

    if isinstance(body, bytes):
        try:
            text = body.decode("latin-1")
        except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 is total
            raise CollectorError("SEC master index is not decodable") from exc
    else:
        text = body
    if not text.strip():
        raise CollectorError("SEC master index is empty")
    if text.lstrip().lower().startswith(("<html", "<!doctype html")):
        raise CollectorError("SEC master index is an HTML error page")
    lines = text.splitlines()
    header_index = next(
        (
            offset
            for offset, line in enumerate(lines)
            if line.strip() == "CIK|Company Name|Form Type|Date Filed|Filename"
        ),
        None,
    )
    if header_index is None:
        raise CollectorError("SEC master index header schema is missing")
    try:
        expected_index_date = date.fromisoformat(index_date)
    except ValueError as exc:
        raise CollectorError("index_date is invalid") from exc
    entries: list[FilingIndexEntry] = []
    for line in lines[header_index + 1 :]:
        if not line.strip() or set(line.strip()) <= {"-"}:
            continue
        parts = line.split("|")
        if len(parts) != 5:
            raise CollectorError("SEC master index row has the wrong field count")
        cik, _company_name, form_type, filing_date, archive_path = (
            part.strip() for part in parts
        )
        if form_type not in FORM_TYPES:
            continue
        if not cik.isdigit() or int(cik) <= 0:
            raise CollectorError("SEC Form 4 master row has invalid CIK")
        try:
            filed = date.fromisoformat(filing_date)
        except ValueError as exc:
            raise CollectorError("SEC Form 4 master row has invalid filing date") from exc
        if filed > expected_index_date:
            raise CollectorError("SEC filing date is later than its master index date")
        match = ACCESSION_RE.search(archive_path)
        if match is None or not archive_path.startswith("edgar/data/"):
            raise CollectorError("SEC Form 4 master row has invalid archive path")
        entries.append(
            FilingIndexEntry(
                accession=match.group("accession"),
                cik=str(int(cik)),
                form_type=form_type,
                filing_date=filed.isoformat(),
                index_date=expected_index_date.isoformat(),
                archive_path=archive_path,
            )
        )
    return deduplicate_accessions(entries)


def deduplicate_accessions(
    entries: Sequence[FilingIndexEntry],
) -> list[FilingIndexEntry]:
    by_accession: dict[str, FilingIndexEntry] = {}
    for entry in entries:
        prior = by_accession.get(entry.accession)
        if prior is not None and prior != entry:
            raise CollectorError(f"conflicting duplicate SEC accession {entry.accession}")
        by_accession[entry.accession] = entry
    return [by_accession[key] for key in sorted(by_accession)]


def _sgml_value(text: str, name: str) -> str | None:
    tag_match = re.search(rf"<{re.escape(name)}>\s*([^\r\n<]+)", text, re.I)
    if tag_match:
        return tag_match.group(1).strip()
    header_match = re.search(
        rf"^\s*{re.escape(name).replace(r'\_', r'[\s_-]')}\s*:\s*(.+?)\s*$",
        text,
        re.I | re.M,
    )
    return header_match.group(1).strip() if header_match else None


def _parse_acceptance(text: str) -> str:
    value = _sgml_value(text, "ACCEPTANCE-DATETIME")
    if value is None or not re.fullmatch(r"\d{14}", value):
        raise CollectorError("SEC submission is missing a valid acceptance datetime")
    # EDGAR acceptance timestamps in the dissemination header are US Eastern
    # local time.  Convert with the IANA zone so daylight-saving offsets are
    # handled by the filing date rather than assumed to be UTC.
    parsed = datetime.strptime(value, "%Y%m%d%H%M%S").replace(
        tzinfo=ZoneInfo("America/New_York")
    )
    return _utc_string(parsed)


def _ownership_xml(text: str) -> tuple[str, str]:
    documents = re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", text, re.I | re.S)
    candidates: list[str] = []
    for document in documents:
        xml_match = re.search(r"<XML>(.*?)</XML>", document, re.I | re.S)
        if xml_match is None:
            continue
        xml = xml_match.group(1).strip()
        if re.search(r"<\s*(?:\w+:)?ownershipDocument(?:\s|>)", xml, re.I):
            candidates.append(xml)
    if len(candidates) != 1:
        raise CollectorError(
            f"SEC submission must contain one ownershipDocument, found {len(candidates)}"
        )
    xml = candidates[0]
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise CollectorError("SEC ownership XML contains a forbidden declaration")
    return xml, _sha256(xml.encode("utf-8"))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _children(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(node) if _local_name(child.tag) == name]


def _child(node: ET.Element, name: str) -> ET.Element | None:
    values = _children(node, name)
    if len(values) > 1:
        raise CollectorError(f"ownership XML contains duplicate {name}")
    return values[0] if values else None


def _path(node: ET.Element, *names: str) -> ET.Element | None:
    current = node
    for name in names:
        current = _child(current, name)  # type: ignore[assignment]
        if current is None:
            return None
    return current


def _value(node: ET.Element, *names: str, required: bool = False) -> str | None:
    found = _path(node, *names)
    if found is None:
        if required:
            raise CollectorError(f"ownership XML missing {'/'.join(names)}")
        return None
    value_node = _child(found, "value")
    target = value_node if value_node is not None else found
    text = (target.text or "").strip()
    if required and not text:
        raise CollectorError(f"ownership XML has empty {'/'.join(names)}")
    return text or None


def _decimal(value: str | None, *, field_name: str, allow_zero: bool = True) -> Decimal:
    if value is None:
        raise CollectorError(f"{field_name} is missing")
    try:
        parsed = Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise CollectorError(f"{field_name} is not decimal") from exc
    if not parsed.is_finite() or parsed < 0 or (not allow_zero and parsed == 0):
        raise CollectorError(f"{field_name} is outside its valid domain")
    return parsed


def _date_value(value: str | None, *, field_name: str) -> str:
    if value is None:
        raise CollectorError(f"{field_name} is missing")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise CollectorError(f"{field_name} is invalid") from exc


def _plan_flag(value: str | None) -> str:
    if value is None or value.strip() == "":
        return "UNKNOWN"
    normalized = value.strip().lower()
    if normalized in {"0", "false"}:
        return "FALSE"
    if normalized in {"1", "true"}:
        return "TRUE"
    raise CollectorError("aff10b5One must be explicit true, false, or absent")


def _fingerprint(
    *,
    transaction_date: str,
    code: str,
    acquired_disposed: str,
    shares: Decimal,
    price: Decimal | None,
) -> str:
    canonical = "|".join(
        (
            transaction_date,
            code,
            acquired_disposed,
            format(shares.normalize(), "f"),
            format(price.normalize(), "f") if price is not None else "MISSING",
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_transactions(
    root: ET.Element, *, filing_plan_10b5: str
) -> tuple[tuple[ParsedTransaction, ...], int, int, tuple[str, ...]]:
    table = _child(root, "nonDerivativeTable")
    if table is None:
        return (), 0, 0, ()
    transactions: list[ParsedTransaction] = []
    excluded = 0
    missing_price = 0
    anomalies: list[str] = []
    for ordinal, transaction in enumerate(_children(table, "nonDerivativeTransaction"), 1):
        code = _value(transaction, "transactionCoding", "transactionCode")
        if code not in {"P", "S"}:
            excluded += 1
            continue
        try:
            acquired_disposed = _value(
                transaction,
                "transactionAmounts",
                "transactionAcquiredDisposedCode",
                required=True,
            )
            expected = "A" if code == "P" else "D"
            if acquired_disposed != expected:
                raise CollectorError(f"{code} transaction must use {expected}")
            shares = _decimal(
                _value(
                    transaction,
                    "transactionAmounts",
                    "transactionShares",
                    required=True,
                ),
                field_name="transactionShares",
                allow_zero=False,
            )
            raw_price = _value(
                transaction,
                "transactionAmounts",
                "transactionPricePerShare",
            )
            price = (
                _decimal(raw_price, field_name="transactionPricePerShare")
                if raw_price is not None
                else None
            )
            transaction_day = _date_value(
                _value(transaction, "transactionDate", required=True),
                field_name="transactionDate",
            )
            # Since Ownership XML 5.3 the optional aff10b5One indicator is a
            # filing-level ownershipDocument field, not a Table-I row field.
            # Apply that tri-state to every eligible P/S row and publish its
            # filing-level coverage; no per-transaction plan status is inferred.
            flag = filing_plan_10b5
            fingerprint = _fingerprint(
                transaction_date=transaction_day,
                code=code,
                acquired_disposed=acquired_disposed,
                shares=shares,
                price=price,
            )
            transactions.append(
                ParsedTransaction(
                    transaction_date=transaction_day,
                    code=code,
                    acquired_disposed=acquired_disposed,
                    shares=shares,
                    price_per_share=price,
                    dollar_value=shares * price if price is not None else None,
                    plan_10b5=flag,
                    fingerprint=fingerprint,
                )
            )
            if price is None:
                missing_price += 1
        except CollectorError:
            anomalies.append(f"NONDERIVATIVE_ROW_{ordinal}_QUARANTINED")
    return tuple(transactions), excluded, missing_price, tuple(anomalies)


def parse_complete_submission(
    body: bytes,
    *,
    entry: FilingIndexEntry,
    expected_sha256: str | None = None,
) -> ParsedForm4:
    """Parse one complete submission and quarantine malformed P/S rows."""

    digest = _sha256(body)
    if expected_sha256 is not None and digest != expected_sha256:
        raise CollectorError("SEC submission hash changed before parsing")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("latin-1")
    if not text.strip() or text.lstrip().lower().startswith(("<html", "<!doctype html")):
        raise CollectorError("SEC complete submission is empty or HTML")
    if b"<SEC-DOCUMENT" not in body[:4096].upper():
        raise CollectorError("SEC complete submission has the wrong schema")
    header_accession = _sgml_value(text, "ACCESSION NUMBER")
    if header_accession is not None and header_accession != entry.accession:
        raise CollectorError("SEC accession does not match daily master index")
    acceptance_at = _parse_acceptance(text)
    xml, xml_digest = _ownership_xml(text)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise CollectorError("SEC ownershipDocument XML is invalid") from exc
    if _local_name(root.tag) != "ownershipDocument":
        raise CollectorError("SEC XML root is not ownershipDocument")
    document_type = _value(root, "documentType", required=True)
    if document_type != entry.form_type or document_type not in FORM_TYPES:
        raise CollectorError("ownership document type does not match master index")
    issuer_cik = _value(root, "issuer", "issuerCik", required=True)
    if issuer_cik is None or not issuer_cik.isdigit():
        raise CollectorError("ownership XML issuer CIK is invalid")
    period = _value(root, "periodOfReport")
    period_of_report = (
        _date_value(period, field_name="periodOfReport") if period is not None else None
    )
    original = _value(root, "dateOfOriginalSubmission")
    original_submission_date = (
        _date_value(original, field_name="dateOfOriginalSubmission")
        if original is not None
        else None
    )
    reporting_owner_ciks: set[str] = set()
    for owner in _children(root, "reportingOwner"):
        owner_cik = _value(owner, "reportingOwnerId", "rptOwnerCik", required=True)
        if owner_cik is None or not owner_cik.isdigit():
            raise CollectorError("ownership XML reporting-owner CIK is invalid")
        reporting_owner_ciks.add(str(int(owner_cik)))
    if not reporting_owner_ciks:
        raise CollectorError("ownership XML has no reporting-owner CIK")
    normalized_owner_ciks = tuple(sorted(reporting_owner_ciks))
    owner_hash = hashlib.sha256(
        "\n".join(normalized_owner_ciks).encode("utf-8")
    ).hexdigest()
    filing_plan_10b5 = _plan_flag(_value(root, "aff10b5One"))
    transactions, excluded, missing_price, anomalies = _parse_transactions(
        root, filing_plan_10b5=filing_plan_10b5
    )
    fingerprints = tuple(sorted(transaction.fingerprint for transaction in transactions))
    transactions_hash = hashlib.sha256("\n".join(fingerprints).encode("ascii")).hexdigest()
    return ParsedForm4(
        accession=entry.accession,
        form_type=entry.form_type,
        filing_date=entry.filing_date,
        index_date=entry.index_date,
        acceptance_at=acceptance_at,
        issuer_cik=str(int(issuer_cik)),
        reporting_owner_ciks=normalized_owner_ciks,
        reporting_owner_ciks_hash=owner_hash,
        period_of_report=period_of_report,
        original_submission_date=original_submission_date,
        filing_plan_10b5=filing_plan_10b5,
        submission_sha256=digest,
        ownership_document_sha256=xml_digest,
        transactions=transactions,
        eligible_transaction_fingerprints=fingerprints,
        eligible_transactions_hash=transactions_hash,
        excluded_transaction_count=excluded,
        missing_price_count=missing_price,
        anomaly_codes=anomalies,
        parse_status="PARSED_WITH_QUARANTINED_ROWS" if anomalies else "PARSED",
    )


def collect_form4_window(
    *,
    start_date: date,
    end_date: date,
    client: SecHttpClient,
    known_accessions: Mapping[str, ParsedForm4] | None = None,
    known_ledger_entries: Mapping[str, Mapping[str, Any]] | None = None,
) -> Form4Collection:
    """Collect a bounded daily-index window without publishing or backfilling.

    A master index day is considered completed when its index was fetched and
    every deduplicated Form 4 accession either parsed or reached a deterministic
    quarantine.  Transient/HTTP failures leave the day incomplete, preventing
    downstream windows from silently treating a partial day as complete.
    """

    known = dict(known_accessions or {})
    if any(key != value.accession for key, value in known.items()):
        raise CollectorError("known_accessions key does not match parsed filing")
    known_ledger = {key: dict(value) for key, value in (known_ledger_entries or {}).items()}
    for accession, entry in known_ledger.items():
        if entry.get("accession") != accession:
            raise CollectorError("known_ledger_entries key does not match ledger accession")
        if entry.get("form_type") not in FORM_TYPES:
            raise CollectorError("known ledger entry has invalid form_type")
        for key in ("filing_date", "index_date"):
            try:
                date.fromisoformat(str(entry.get(key)))
            except ValueError as exc:
                raise CollectorError(f"known ledger entry has invalid {key}") from exc
    discovered = discover_daily_master_indexes(
        client, start_date=start_date, end_date=end_date
    )
    all_entries: dict[str, FilingIndexEntry] = {}
    by_day: dict[str, list[FilingIndexEntry]] = {}
    failures: list[dict[str, str]] = []
    reviews: list[dict[str, str]] = []
    day_complete: dict[str, bool] = {}
    for index_day, index_url in discovered:
        day_complete[index_day] = True
        try:
            result = client.get(index_url, expected="text")
            entries = parse_master_index(result.body, index_date=index_day)
        except CollectorError as exc:
            failures.append(
                {"index_date": index_day, "stage": "MASTER_INDEX", "reason": str(exc)}
            )
            day_complete[index_day] = False
            continue
        by_day[index_day] = entries
        for entry in entries:
            prior = all_entries.get(entry.accession)
            if prior is not None and prior != entry:
                failures.append(
                    {
                        "accession": entry.accession,
                        "index_date": index_day,
                        "stage": "ACCESSION_DEDUPLICATION",
                        "reason": "conflicting duplicate accession metadata",
                    }
                )
                day_complete[index_day] = False
                continue
            all_entries[entry.accession] = entry

    filings: list[ParsedForm4] = []
    reused_ledger: list[str] = []
    failed_accessions: set[str] = set()
    for accession in sorted(all_entries):
        entry = all_entries[accession]
        prior = known.get(accession)
        if prior is not None:
            if (
                prior.form_type != entry.form_type
                or prior.filing_date != entry.filing_date
                or prior.index_date != entry.index_date
            ):
                failed_accessions.add(accession)
                failures.append(
                    {
                        "accession": accession,
                        "index_date": entry.index_date,
                        "stage": "KNOWN_ACCESSION_RECONCILIATION",
                        "reason": "known accession does not match current master index",
                    }
                )
            else:
                filings.append(prior)
            continue
        prior_ledger = known_ledger.get(accession)
        if prior_ledger is not None:
            if (
                prior_ledger.get("form_type") != entry.form_type
                or prior_ledger.get("filing_date") != entry.filing_date
                or prior_ledger.get("index_date") != entry.index_date
            ):
                failed_accessions.add(accession)
                failures.append(
                    {
                        "accession": accession,
                        "index_date": entry.index_date,
                        "stage": "KNOWN_LEDGER_RECONCILIATION",
                        "reason": "known ledger accession does not match current master index",
                    }
                )
            else:
                reused_ledger.append(accession)
            continue
        try:
            # Complete accepted submissions are immutable.  When a verified
            # private cache entry exists, reuse it without a conditional GET;
            # the content-addressed hash check still detects local corruption.
            response = client.get(
                entry.submission_url, expected="submission", revalidate=False
            )
            filing = parse_complete_submission(
                response.body, entry=entry, expected_sha256=response.sha256
            )
            filings.append(filing)
            if filing.anomaly_codes:
                reviews.append(
                    {
                        "accession": accession,
                        "index_date": entry.index_date,
                        "stage": "TRANSACTION_QUARANTINE",
                        "reason": ",".join(filing.anomaly_codes),
                    }
                )
        except CollectorError as exc:
            failed_accessions.add(accession)
            failures.append(
                {
                    "accession": accession,
                    "index_date": entry.index_date,
                    "stage": "SUBMISSION",
                    "reason": str(exc),
                }
            )
    for day, entries in by_day.items():
        if any(entry.accession in failed_accessions for entry in entries):
            day_complete[day] = False
    completed = tuple(day for day in sorted(day_complete) if day_complete[day])
    master_accessions = {
        day: tuple(sorted(entry.accession for entry in by_day.get(day, ())))
        for day in completed
    }
    return Form4Collection(
        filings=tuple(filings),
        reused_ledger_accessions=tuple(sorted(reused_ledger)),
        master_accessions_by_day=master_accessions,
        completed_index_days=completed,
        discovered_index_days=tuple(day for day, _ in discovered),
        failures=tuple(failures),
        reviews=tuple(reviews),
        source_requests=client.request_count,
    )


__all__ = [
    "CollectorError",
    "FetchResult",
    "FilingIndexEntry",
    "Form4Collection",
    "ParsedForm4",
    "ParsedTransaction",
    "PrivateResponseCache",
    "SecHttpClient",
    "SerializedTokenBucket",
    "collect_form4_window",
    "deduplicate_accessions",
    "discover_daily_master_indexes",
    "parse_complete_submission",
    "parse_master_index",
    "parse_quarter_index",
]
