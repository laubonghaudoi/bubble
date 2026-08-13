"""Maintain one review-only GitHub issue for P3 manual disclosures.

This checker reads filing metadata and the reviewed CSV.  It never downloads
filing prose, extracts values, or writes dashboard data.  Its only mutation is
creating/updating a single deduplicated GitHub issue that asks a human to
review newer periodic filings or stale manual evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

from pipeline.manual_signals import (
    DEFAULT_MANUAL_SIGNALS_PATH,
    MANUAL_EVIDENCE_MAX_AGE_DAYS,
    MANUAL_SOURCE_TYPES,
    P3_COMPANY_CIKS,
    P3_COMPANY_IDS,
    P3_MANUAL_METRIC_IDS,
    ManualSignal,
    load_manual_signals,
)

ISSUE_TITLE = "[P3 manual review] Industry disclosure queue"
ISSUE_MARKER = "<!-- bubble:p3-manual-disclosure-review:v1 -->"
ISSUE_AUTHOR = "github-actions[bot]"
SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
GITHUB_API_BASE = "https://api.github.com"
REQUIRED_SEC_USER_AGENT = "Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com"
ELIGIBLE_FORMS = MANUAL_SOURCE_TYPES
DEFAULT_OVERDUE_DAYS = MANUAL_EVIDENCE_MAX_AGE_DAYS
DEFAULT_FILING_LOOKBACK_DAYS = 180


class DisclosureCheckError(RuntimeError):
    """The review check could not complete without guessing or partial data."""


@dataclass(frozen=True)
class Company:
    company_id: str
    name: str
    cik: str


@dataclass(frozen=True)
class Filing:
    company_id: str
    form: str
    accession: str
    filed_on: str
    report_date: str
    accepted_at: str
    source_url: str


@dataclass(frozen=True)
class ReviewTask:
    company_id: str
    metric_id: str
    reasons: tuple[str, ...]
    latest_reviewed_at: str | None
    latest_reviewed_accession: str | None
    candidate_accessions: tuple[str, ...]


JsonFetcher = Callable[[str, Mapping[str, str]], Any]
GitHubRequester = Callable[[str, str, Mapping[str, Any] | None], Any]
Sleeper = Callable[[float], None]


def load_p3_companies(path: str | Path) -> tuple[Company, ...]:
    """Load and cross-check the four locked hyperscaler identities."""

    source = Path(path)
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DisclosureCheckError(f"cannot load {source}: {exc}") from exc
    if not isinstance(document, Mapping) or not isinstance(
        document.get("companies"), list
    ):
        raise DisclosureCheckError(f"{source} must contain a companies list")
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in document["companies"]:
        if not isinstance(row, Mapping) or not isinstance(row.get("company_id"), str):
            raise DisclosureCheckError(f"{source} contains an invalid company record")
        company_id = row["company_id"]
        if company_id in indexed:
            raise DisclosureCheckError(f"{source} duplicates company_id {company_id}")
        indexed[company_id] = row

    companies: list[Company] = []
    for company_id in P3_COMPANY_IDS:
        row = indexed.get(company_id)
        if row is None:
            raise DisclosureCheckError(f"{source} is missing company_id {company_id}")
        name, cik = row.get("name"), row.get("cik")
        if not isinstance(name, str) or not name:
            raise DisclosureCheckError(f"{company_id} must have a non-empty name")
        if cik != P3_COMPANY_CIKS[company_id]:
            raise DisclosureCheckError(
                f"{company_id} CIK does not match the locked identity"
            )
        companies.append(Company(company_id=company_id, name=name, cik=cik))
    return tuple(companies)


def _strict_utc_timestamp(value: Any, *, path: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value)
        is None
    ):
        raise DisclosureCheckError(f"{path} must be an ISO UTC timestamp")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DisclosureCheckError(f"{path} must be a valid ISO UTC timestamp") from exc
    return value


def _strict_date(value: Any, *, path: str, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str):
        raise DisclosureCheckError(f"{path} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DisclosureCheckError(f"{path} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise DisclosureCheckError(f"{path} must be an ISO date")
    return value


def parse_sec_submissions(company: Company, payload: Any) -> tuple[Filing, ...]:
    """Parse only SEC filing metadata needed to identify human-review work."""

    if not isinstance(payload, Mapping):
        raise DisclosureCheckError(
            f"SEC submissions for {company.company_id} must be an object"
        )
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, Mapping) else None
    if not isinstance(recent, Mapping):
        raise DisclosureCheckError(
            f"SEC submissions for {company.company_id} lack filings.recent"
        )
    fields = (
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
    )
    arrays: dict[str, list[Any]] = {}
    for field in fields:
        values = recent.get(field)
        if not isinstance(values, list):
            raise DisclosureCheckError(
                f"SEC submissions for {company.company_id} lack filings.recent.{field}"
            )
        arrays[field] = values
    lengths = {len(values) for values in arrays.values()}
    if len(lengths) != 1:
        raise DisclosureCheckError(
            f"SEC submissions for {company.company_id} have misaligned recent arrays"
        )

    output: list[Filing] = []
    for index in range(next(iter(lengths), 0)):
        form = arrays["form"][index]
        if form not in ELIGIBLE_FORMS:
            continue
        accession = arrays["accessionNumber"][index]
        if (
            not isinstance(accession, str)
            or re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) is None
        ):
            raise DisclosureCheckError(
                f"SEC submissions {company.company_id} row {index} has an invalid accession"
            )
        primary_document = arrays["primaryDocument"][index]
        if (
            not isinstance(primary_document, str)
            or not primary_document
            or "/" in primary_document
            or "\\" in primary_document
        ):
            raise DisclosureCheckError(
                f"SEC submissions {company.company_id} row {index} primaryDocument is invalid"
            )
        accepted_at = _strict_utc_timestamp(
            arrays["acceptanceDateTime"][index],
            path=f"SEC submissions {company.company_id} row {index} acceptanceDateTime",
        )
        filed_on = _strict_date(
            arrays["filingDate"][index],
            path=f"SEC submissions {company.company_id} row {index} filingDate",
        )
        report_date = _strict_date(
            arrays["reportDate"][index],
            path=f"SEC submissions {company.company_id} row {index} reportDate",
            allow_empty=True,
        )
        accession_digits = accession.replace("-", "")
        source_url = (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{int(company.cik)}/{accession_digits}/{quote(primary_document)}"
        )
        output.append(
            Filing(
                company_id=company.company_id,
                form=form,
                accession=accession,
                filed_on=filed_on,
                report_date=report_date,
                accepted_at=accepted_at,
                source_url=source_url,
            )
        )
    if not output:
        raise DisclosureCheckError(
            f"SEC submissions for {company.company_id} contain no eligible filing metadata"
        )
    return tuple(
        sorted(output, key=lambda filing: (filing.accepted_at, filing.accession))
    )


def collect_recent_filings(
    companies: Sequence[Company],
    *,
    fetch_json: JsonFetcher,
    sec_user_agent: str,
    sleep: Sleeper = time.sleep,
    request_interval_seconds: float = 0.25,
) -> dict[str, tuple[Filing, ...]]:
    """Read four SEC submission indexes at no more than four requests/second."""

    if sec_user_agent != REQUIRED_SEC_USER_AGENT:
        raise DisclosureCheckError(
            "SEC_USER_AGENT must equal the reviewed dashboard contact string"
        )
    if not 0.2 <= request_interval_seconds <= 0.5:
        raise DisclosureCheckError(
            "SEC request interval must remain within the reviewed 2-5 requests/second range"
        )
    headers = {
        "Accept": "application/json",
        "User-Agent": sec_user_agent,
    }
    output: dict[str, tuple[Filing, ...]] = {}
    for index, company in enumerate(companies):
        if index:
            sleep(request_interval_seconds)
        url = f"{SEC_SUBMISSIONS_BASE}/CIK{company.cik}.json"
        output[company.company_id] = parse_sec_submissions(
            company, fetch_json(url, headers)
        )
    return output


def validate_manual_timestamps_not_future(
    records: Sequence[ManualSignal], *, now: datetime
) -> None:
    """Reject future reviewed evidence before any discovery network request."""

    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise DisclosureCheckError("now must be timezone-aware UTC")
    for record in records:
        accepted_at = datetime.fromisoformat(record.filing_accepted_at[:-1] + "+00:00")
        reviewed_at = datetime.fromisoformat(record.reviewed_at[:-1] + "+00:00")
        if (
            accepted_at > now
            or reviewed_at > now
            or date.fromisoformat(record.as_of) > now.date()
        ):
            raise DisclosureCheckError(
                f"manual signal {record.identity} must not be future-dated"
            )


def reconcile_manual_signals_with_sec_metadata(
    records: Sequence[ManualSignal],
    filings_by_company: Mapping[str, Sequence[Filing]],
    *,
    now: datetime,
    filing_lookback_days: int = DEFAULT_FILING_LOOKBACK_DAYS,
) -> None:
    """Cross-check recent reviewed rows against official SEC filing metadata."""

    cutoff = now.date() - timedelta(days=filing_lookback_days)
    for record in records:
        filings = filings_by_company.get(record.company_id)
        if filings is None:
            raise DisclosureCheckError(
                f"filing metadata is missing for {record.company_id}"
            )
        matches = [
            filing for filing in filings if filing.accession == record.filing_accession
        ]
        if not matches:
            if date.fromisoformat(record.as_of) >= cutoff:
                raise DisclosureCheckError(
                    f"recent manual signal accession is absent from SEC metadata: {record.filing_accession}"
                )
            continue
        if len(matches) != 1:
            raise DisclosureCheckError(
                f"SEC metadata duplicates accession {record.filing_accession}"
            )
        filing = matches[0]
        if filing.form != record.source_type:
            raise DisclosureCheckError(
                f"manual signal {record.filing_accession} source_type does not match SEC metadata"
            )
        accepted_at = datetime.fromisoformat(record.filing_accepted_at[:-1] + "+00:00")
        sec_accepted_at = datetime.fromisoformat(filing.accepted_at[:-1] + "+00:00")
        if accepted_at != sec_accepted_at:
            raise DisclosureCheckError(
                f"manual signal {record.filing_accession} accepted timestamp does not match SEC metadata"
            )
        if record.source_url != filing.source_url:
            raise DisclosureCheckError(
                f"manual signal {record.filing_accession} source_url does not match SEC primary document"
            )


def build_review_queue(
    records: Sequence[ManualSignal],
    companies: Sequence[Company],
    filings_by_company: Mapping[str, Sequence[Filing]],
    *,
    now: datetime,
    overdue_days: int = DEFAULT_OVERDUE_DAYS,
    filing_lookback_days: int = DEFAULT_FILING_LOOKBACK_DAYS,
) -> tuple[ReviewTask, ...]:
    """Identify missing, stale, or superseded human reviews without inferring values."""

    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise DisclosureCheckError("now must be timezone-aware UTC")
    if overdue_days < 1 or filing_lookback_days < 1:
        raise DisclosureCheckError("review windows must be positive days")
    lookback = (
        (now - timedelta(days=filing_lookback_days)).isoformat().replace("+00:00", "Z")
    )
    tasks: list[ReviewTask] = []
    for company in companies:
        if company.company_id not in filings_by_company:
            raise DisclosureCheckError(
                f"filing metadata is missing for {company.company_id}"
            )
        filings = sorted(
            filings_by_company[company.company_id],
            key=lambda filing: (filing.accepted_at, filing.accession),
        )
        for metric_id in P3_MANUAL_METRIC_IDS:
            candidates = [
                record
                for record in records
                if record.company_id == company.company_id
                and record.metric_id == metric_id
            ]
            latest = max(
                candidates,
                key=lambda record: (
                    record.as_of,
                    record.period_end,
                    record.filing_accepted_at,
                    record.reviewed_at,
                    record.filing_accession,
                ),
                default=None,
            )
            reviewed_accessions = {record.filing_accession for record in candidates}
            newer = tuple(
                filing
                for filing in filings
                if filing.accepted_at > lookback
                and filing.accession not in reviewed_accessions
            )
            reasons: list[str] = []
            if latest is None:
                reasons.append("NO_REVIEWED_ROW")
            else:
                evidence_age = now.date() - date.fromisoformat(latest.as_of)
                if evidence_age > timedelta(days=overdue_days):
                    reasons.append("REVIEW_OVERDUE")
            if newer:
                reasons.append("NEW_FILING")
            if reasons:
                tasks.append(
                    ReviewTask(
                        company_id=company.company_id,
                        metric_id=metric_id,
                        reasons=tuple(reasons),
                        latest_reviewed_at=(latest.reviewed_at if latest else None),
                        latest_reviewed_accession=(
                            latest.filing_accession if latest else None
                        ),
                        candidate_accessions=tuple(
                            filing.accession for filing in newer
                        ),
                    )
                )
    return tuple(sorted(tasks, key=lambda task: (task.company_id, task.metric_id)))


def render_issue_body(
    tasks: Sequence[ReviewTask],
    filings_by_company: Mapping[str, Sequence[Filing]],
) -> str:
    """Render a stable review queue containing metadata and no extracted numbers."""

    filing_index = {
        filing.accession: filing
        for filings in filings_by_company.values()
        for filing in filings
    }
    lines = [
        ISSUE_MARKER,
        "## P3 reviewed-public-filing queue",
        "",
        "This issue is a discovery queue only. The automation does **not** extract or guess disclosure values.",
        "Review the official filing, update `data/manual/industry_signals.csv` in a pull request, and let the normal validation/deploy workflow publish it after review.",
        "",
    ]
    if not tasks:
        lines.extend(["No manual disclosure review is currently due.", ""])
        return "\n".join(lines)

    lines.extend(
        [
            "### Review tasks",
            "",
            "| Company | Metric | Reason | Last reviewed | Candidate filings |",
            "|---|---|---|---|---|",
        ]
    )
    referenced: set[str] = set()
    for task in tasks:
        accessions = (
            ", ".join(f"`{value}`" for value in task.candidate_accessions) or "—"
        )
        referenced.update(task.candidate_accessions)
        lines.append(
            "| "
            f"{task.company_id} | `{task.metric_id}` | "
            f"{', '.join(task.reasons)} | {task.latest_reviewed_at or '—'} | {accessions} |"
        )

    if referenced:
        lines.extend(
            [
                "",
                "### Official filing candidates",
                "",
                "| Company | Form | Report period | Accepted (UTC) | Accession |",
                "|---|---|---|---|---|",
            ]
        )
        for accession in sorted(
            referenced,
            key=lambda value: (filing_index[value].accepted_at, value),
        ):
            filing = filing_index[accession]
            lines.append(
                "| "
                f"{filing.company_id} | {filing.form} | {filing.report_date or '—'} | "
                f"{filing.accepted_at} | [{filing.accession}]({filing.source_url}) |"
            )
    lines.extend(
        [
            "",
            "### Review guardrails",
            "",
            "- Preserve `null`; a missing disclosure is never zero.",
            "- Use a short factual paraphrase, not copied filing prose.",
            "- Set `comparable=false` when the definition or scope changed.",
            "- Do not edit generated `public/data/**` files by hand.",
            "",
        ]
    )
    return "\n".join(lines)


def upsert_review_issue(
    *,
    repository: str,
    body: str,
    has_tasks: bool,
    request: GitHubRequester,
) -> str:
    """Create, reopen, update, close, or no-op exactly one marker-owned issue."""

    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise DisclosureCheckError("GITHUB_REPOSITORY must be owner/name")
    issues: list[Any] = []
    for page in range(1, 101):
        result = request(
            "GET",
            (
                f"/repos/{repository}/issues?state=all&per_page=100"
                f"&sort=updated&direction=desc&page={page}"
            ),
            None,
        )
        if not isinstance(result, list):
            raise DisclosureCheckError("GitHub issues response must be a list")
        issues.extend(result)
        if len(result) < 100:
            break
    else:
        raise DisclosureCheckError(
            "GitHub issue scan exceeded 10,000 records; refusing a partial dedupe"
        )
    matches = [
        issue
        for issue in issues
        if isinstance(issue, Mapping)
        and ISSUE_MARKER in str(issue.get("body") or "")
        and isinstance(issue.get("user"), Mapping)
        and issue["user"].get("login") == ISSUE_AUTHOR
        and "pull_request" not in issue
    ]
    if len(matches) > 1:
        raise DisclosureCheckError(
            "multiple marker-owned P3 review issues exist; resolve duplicates manually"
        )
    existing = matches[0] if matches else None
    desired_state = "open" if has_tasks else "closed"
    if existing is None:
        if not has_tasks:
            return "noop"
        request(
            "POST",
            f"/repos/{repository}/issues",
            {"title": ISSUE_TITLE, "body": body},
        )
        return "created"

    number = existing.get("number")
    if not isinstance(number, int) or isinstance(number, bool):
        raise DisclosureCheckError(
            "marker-owned GitHub issue has no numeric issue number"
        )
    current_state = existing.get("state")
    if current_state not in {"open", "closed"}:
        raise DisclosureCheckError("marker-owned GitHub issue has an invalid state")
    payload: dict[str, Any] = {}
    if existing.get("title") != ISSUE_TITLE:
        payload["title"] = ISSUE_TITLE
    if existing.get("body") != body:
        payload["body"] = body
    if current_state != desired_state:
        payload["state"] = desired_state
    if not payload:
        return "noop"
    request("PATCH", f"/repos/{repository}/issues/{number}", payload)
    return (
        "reopened"
        if desired_state == "open" and current_state == "closed"
        else ("closed" if desired_state == "closed" else "updated")
    )


def _http_json(url: str, headers: Mapping[str, str]) -> Any:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "text/json"}:
                raise DisclosureCheckError(
                    f"unexpected content type from {url}: {content_type}"
                )
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DisclosureCheckError(f"request failed for {url}: {exc}") from exc


def github_requester(token: str) -> GitHubRequester:
    if not token:
        raise DisclosureCheckError("GITHUB_TOKEN is required")

    def request(method: str, path: str, payload: Mapping[str, Any] | None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "bubble-p3-disclosure-check",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        http_request = Request(
            f"{GITHUB_API_BASE}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(http_request, timeout=30) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise DisclosureCheckError(
                f"GitHub API {method} {path} failed: {exc}"
            ) from exc

    return request


def run_check(
    *,
    csv_path: str | Path,
    companies_path: str | Path,
    now: datetime,
    sec_user_agent: str,
    fetch_json: JsonFetcher = _http_json,
    sleep: Sleeper = time.sleep,
    overdue_days: int = DEFAULT_OVERDUE_DAYS,
    filing_lookback_days: int = DEFAULT_FILING_LOOKBACK_DAYS,
) -> tuple[tuple[ReviewTask, ...], dict[str, tuple[Filing, ...]], str]:
    """Validate local input before any request, then build the review issue."""

    records = load_manual_signals(csv_path)
    validate_manual_timestamps_not_future(records, now=now)
    companies = load_p3_companies(companies_path)
    filings = collect_recent_filings(
        companies,
        fetch_json=fetch_json,
        sec_user_agent=sec_user_agent,
        sleep=sleep,
    )
    reconcile_manual_signals_with_sec_metadata(
        records,
        filings,
        now=now,
        filing_lookback_days=filing_lookback_days,
    )
    tasks = build_review_queue(
        records,
        companies,
        filings,
        now=now,
        overdue_days=overdue_days,
        filing_lookback_days=filing_lookback_days,
    )
    return tasks, filings, render_issue_body(tasks, filings)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(DEFAULT_MANUAL_SIGNALS_PATH))
    parser.add_argument(
        "--companies",
        default=str(Path(__file__).resolve().parents[1] / "config" / "companies.yml"),
    )
    parser.add_argument("--overdue-days", type=int, default=DEFAULT_OVERDUE_DAYS)
    parser.add_argument(
        "--filing-lookback-days", type=int, default=DEFAULT_FILING_LOOKBACK_DAYS
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    tasks, _, body = run_check(
        csv_path=args.csv,
        companies_path=args.companies,
        now=now,
        sec_user_agent=os.environ.get("SEC_USER_AGENT", ""),
        overdue_days=args.overdue_days,
        filing_lookback_days=args.filing_lookback_days,
    )
    if args.dry_run:
        print(body)
        return 0
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    action = upsert_review_issue(
        repository=repository,
        body=body,
        has_tasks=bool(tasks),
        request=github_requester(os.environ.get("GITHUB_TOKEN", "")),
    )
    print(f"P3 manual disclosure issue action: {action}; tasks: {len(tasks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
