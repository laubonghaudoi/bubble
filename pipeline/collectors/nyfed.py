from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta, timezone
from math import isclose
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .common import CollectorError, get_json, number, optional_number

API_ROOT = "https://markets.newyorkfed.org/api"
DEFAULT_USER_AGENT = "Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com"
NEW_YORK = ZoneInfo("America/New_York")


def _iso_release(operation: Mapping[str, Any]) -> str | None:
    value = operation.get("lastUpdated")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=NEW_YORK)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_reference_rates(
    payload: Mapping[str, Any], *, expected_type: str
) -> list[dict[str, Any]]:
    expected = expected_type.strip().upper() if isinstance(expected_type, str) else ""
    if expected not in {"SOFR", "EFFR", "OBFR", "TGCR", "BGCR"}:
        raise CollectorError(f"unsupported NY Fed reference-rate type: {expected_type!r}")
    rows = payload.get("refRates")
    if not isinstance(rows, list) or not rows:
        raise CollectorError("NY Fed response missing non-empty refRates")
    by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise CollectorError("NY Fed refRates row must be an object")
        if row.get("type") != expected:
            raise CollectorError(
                f"NY Fed reference-rate row type must be {expected}"
            )
        day = row.get("effectiveDate")
        if not isinstance(day, str):
            raise CollectorError("NY Fed rate missing effectiveDate")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise CollectorError("NY Fed rate has invalid effectiveDate") from exc
        value = number(row.get("percentRate"), field="percentRate")
        observation = {"date": day, "value": value}
        previous = by_date.get(day)
        if previous is not None and previous != observation:
            raise CollectorError(
                f"conflicting duplicate NY Fed reference-rate date: {day}"
            )
        by_date[day] = observation
    return [by_date[day] for day in sorted(by_date)]


def fetch_reference_rate(
    metric_id: str,
    *,
    start: date,
    end: date,
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[dict[str, Any]]:
    segment = "secured" if metric_id in {"sofr", "tgcr", "bgcr"} else "unsecured"
    query = urlencode(
        {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "type": "rate",
        }
    )
    payload = get_json(
        f"{API_ROOT}/rates/{segment}/{metric_id}/search.json?{query}",
        user_agent=user_agent,
    )
    return parse_reference_rates(payload, expected_type=metric_id)


def _operation_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    repo = payload.get("repo")
    rows = repo.get("operations") if isinstance(repo, Mapping) else None
    if not isinstance(rows, list) or not rows:
        raise CollectorError("NY Fed operation response missing non-empty repo.operations")
    if not all(isinstance(row, Mapping) for row in rows):
        raise CollectorError("NY Fed operation row must be an object")
    return rows


def _operation_day(row: Mapping[str, Any], *, label: str) -> str:
    day = row.get("operationDate")
    if not isinstance(day, str):
        raise CollectorError(f"{label} operation missing operationDate")
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise CollectorError(f"{label} operation has invalid operationDate") from exc
    return day


def _operation_identity(
    row: Mapping[str, Any],
    *,
    label: str,
    allow_fallback: bool,
) -> tuple[str, ...]:
    operation_id = row.get("operationId")
    if operation_id is not None:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise CollectorError(f"{label} operation has invalid operationId")
        return ("operationId", operation_id.strip())
    if not allow_fallback:
        raise CollectorError(f"{label} operation missing operationId")

    # ON RRP operationId is the primary identity.  Older payloads can omit it,
    # so operation date/type plus the source's release timestamp is the only
    # fallback accepted.  Amounts are deliberately excluded: otherwise a
    # corrected duplicate could masquerade as a second operation and be summed.
    last_updated = row.get("lastUpdated")
    if (
        not isinstance(last_updated, str)
        or not last_updated.strip()
        or _iso_release(row) is None
    ):
        raise CollectorError(
            f"{label} operation missing operationId and a defensible lastUpdated fallback"
        )
    return (
        "fallback",
        _operation_day(row, label=label),
        str(row.get("operationType")),
        last_updated.strip(),
    )


def _dedupe_operation_rows(
    payload: Mapping[str, Any],
    *,
    operation_type: str,
    label: str,
    allow_fallback: bool,
) -> list[Mapping[str, Any]]:
    by_identity: dict[tuple[str, ...], Mapping[str, Any]] = {}
    for row in _operation_rows(payload):
        if row.get("operationType") != operation_type:
            raise CollectorError(
                f"{label} response contains an unexpected operation type"
            )
        _operation_day(row, label=label)
        identity = _operation_identity(
            row, label=label, allow_fallback=allow_fallback
        )
        previous = by_identity.get(identity)
        if previous is not None and dict(previous) != dict(row):
            raise CollectorError(
                f"conflicting duplicate {label} operation: {'/'.join(identity)}"
            )
        by_identity[identity] = row
    return list(by_identity.values())


def _accepted_submitted(
    row: Mapping[str, Any],
    *,
    submitted_field: str,
    accepted_field: str,
    label: str,
) -> tuple[float, float]:
    submitted = number(row.get(submitted_field), field=submitted_field)
    accepted = number(row.get(accepted_field), field=accepted_field)
    if submitted < 0 or accepted < 0 or accepted > submitted:
        raise CollectorError(
            f"{label} amounts must satisfy 0 <= accepted <= submitted"
        )
    return accepted, submitted


def _dedupe_details(
    row: Mapping[str, Any], *, label: str
) -> list[Mapping[str, Any]]:
    details = row.get("details")
    if not isinstance(details, list) or not details:
        raise CollectorError(f"{label} operation missing non-empty details")
    by_security: dict[str, Mapping[str, Any]] = {}
    for detail in details:
        if not isinstance(detail, Mapping):
            raise CollectorError(f"{label} detail must be an object")
        security = detail.get("securityType")
        if not isinstance(security, str) or not security:
            raise CollectorError(f"{label} detail missing securityType")
        previous = by_security.get(security)
        if previous is not None and dict(previous) != dict(detail):
            raise CollectorError(
                f"conflicting duplicate {label} detail: {security}"
            )
        by_security[security] = detail
    return list(by_security.values())


def parse_on_rrp(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in _dedupe_operation_rows(
        payload,
        operation_type="Reverse Repo",
        label="ON RRP",
        allow_fallback=True,
    ):
        day = _operation_day(row, label="ON RRP")
        _accepted_submitted(
            row,
            submitted_field="totalAmtSubmitted",
            accepted_field="totalAmtAccepted",
            label="ON RRP",
        )
        grouped[day].append(row)

    observations: list[dict[str, Any]] = []
    for day in sorted(grouped):
        operations = grouped[day]
        amounts = [
            _accepted_submitted(
                row,
                submitted_field="totalAmtSubmitted",
                accepted_field="totalAmtAccepted",
                label="ON RRP",
            )
            for row in operations
        ]
        accepted = sum(item[0] for item in amounts)
        submitted = sum(item[1] for item in amounts)
        releases = [value for value in (_iso_release(row) for row in operations) if value]
        observations.append(
            {
                "date": day,
                "value": round(accepted / 1_000_000_000, 6),
                "submitted_usd_bn": round(submitted / 1_000_000_000, 6),
                "source_total_amt_accepted": accepted,
                "source_total_amt_submitted": submitted,
                "source_amount_unit": "USD",
                "operation_count": len(operations),
                "released_at": max(releases, default=None),
            }
        )
    return observations


def parse_srf(
    payload: Mapping[str, Any],
    *,
    operational_readiness_operation_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    if isinstance(operational_readiness_operation_ids, str):
        raise CollectorError(
            "operational_readiness_operation_ids must be a collection of strings"
        )
    readiness: set[str] = set()
    for value in operational_readiness_operation_ids:
        if not isinstance(value, str) or not value.strip():
            raise CollectorError(
                "operational readiness operation ID must be a non-empty string"
            )
        readiness.add(value.strip())
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in _dedupe_operation_rows(
        payload,
        operation_type="Repo",
        label="SRF",
        allow_fallback=True,
    ):
        day = _operation_day(row, label="SRF")
        grouped[day].append(row)

    observations: list[dict[str, Any]] = []
    for day in sorted(grouped):
        operations = grouped[day]
        accepted = 0.0
        submitted = 0.0
        breakdown: dict[str, dict[str, float | None]] = {}
        rates: list[float] = []
        releases: list[str] = []
        exercise_operation_ids: set[str] = set()
        regular_operation_ids: set[str] = set()
        for row in operations:
            identity = _operation_identity(
                row, label="SRF", allow_fallback=True
            )
            operation_id = identity[1] if identity[0] == "operationId" else None
            if operation_id in readiness:
                exercise_operation_ids.add(operation_id)
            else:
                regular_operation_ids.add("/".join(identity))
            row_accepted, row_submitted = _accepted_submitted(
                row,
                submitted_field="totalAmtSubmitted",
                accepted_field="totalAmtAccepted",
                label="SRF",
            )
            accepted += row_accepted
            submitted += row_submitted
            release = _iso_release(row)
            if release:
                releases.append(release)
            detail_accepted_total = 0.0
            detail_submitted_total = 0.0
            for detail in _dedupe_details(row, label="SRF"):
                security = str(detail["securityType"])
                detail_accepted, detail_submitted = _accepted_submitted(
                    detail,
                    submitted_field="amtSubmitted",
                    accepted_field="amtAccepted",
                    label=f"SRF {security} detail",
                )
                detail_accepted_total += detail_accepted
                detail_submitted_total += detail_submitted
                bucket = breakdown.setdefault(
                    security,
                    {"submitted_usd_bn": 0.0, "accepted_usd_bn": 0.0, "rate_pct": None},
                )
                bucket["submitted_usd_bn"] = round(
                    float(bucket["submitted_usd_bn"] or 0)
                    + detail_submitted / 1_000_000_000,
                    6,
                )
                bucket["accepted_usd_bn"] = round(
                    float(bucket["accepted_usd_bn"] or 0)
                    + detail_accepted / 1_000_000_000,
                    6,
                )
                rate = optional_number(detail.get("percentOfferingRate"), field="percentOfferingRate")
                if rate is not None:
                    rates.append(rate)
                    bucket["rate_pct"] = rate
            if not (
                isclose(
                    detail_accepted_total, row_accepted, rel_tol=0, abs_tol=1e-6
                )
                and isclose(
                    detail_submitted_total,
                    row_submitted,
                    rel_tol=0,
                    abs_tol=1e-6,
                )
            ):
                raise CollectorError(
                    "SRF detail submitted/accepted sums must equal top-level totals"
                )
        observations.append(
            {
                "date": day,
                "value": round(accepted / 1_000_000_000, 6),
                "submitted_usd_bn": round(submitted / 1_000_000_000, 6),
                "accepted_usd_bn": round(accepted / 1_000_000_000, 6),
                "rate_pct": max(rates, default=None),
                "breakdown": breakdown,
                "operation_count": len(operations),
                "has_technical_exercise": bool(exercise_operation_ids),
                "technical_exercise": (
                    bool(exercise_operation_ids) and not regular_operation_ids
                ),
                "released_at": max(releases, default=None),
            }
        )
    return observations


def normalized_srf_operations(
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Flatten operation/security rows for the canonical P0 transform layer."""

    output: list[dict[str, Any]] = []
    for row in _dedupe_operation_rows(
        payload,
        operation_type="Repo",
        label="SRF",
        allow_fallback=False,
    ):
        operation_id = str(row["operationId"]).strip()
        operation_day = _operation_day(row, label="SRF")
        top_accepted, top_submitted = _accepted_submitted(
            row,
            submitted_field="totalAmtSubmitted",
            accepted_field="totalAmtAccepted",
            label="SRF",
        )
        operation_output: list[dict[str, Any]] = []
        detail_accepted_total = 0.0
        detail_submitted_total = 0.0
        for detail in _dedupe_details(row, label="SRF"):
            security = str(detail["securityType"])
            aliases = {
                "Treasury": "treasury",
                "Agency": "agency_debt",
                "Mortgage-Backed": "agency_mbs",
            }
            if security not in aliases:
                raise CollectorError(f"unsupported SRF securityType {security!r}")
            accepted, submitted = _accepted_submitted(
                detail,
                submitted_field="amtSubmitted",
                accepted_field="amtAccepted",
                label=f"SRF {security} detail",
            )
            detail_accepted_total += accepted
            detail_submitted_total += submitted
            operation_output.append(
                {
                    "operation_id": operation_id,
                    "operation_date": operation_day,
                    "collateral_type": aliases[security],
                    "submitted_amount_usd_bn": round(
                        submitted / 1_000_000_000,
                        6,
                    ),
                    "accepted_amount_usd_bn": round(
                        accepted / 1_000_000_000,
                        6,
                    ),
                    "rate_pct": optional_number(
                        detail.get("percentOfferingRate"), field="percentOfferingRate"
                    ),
                    "released_at": _iso_release(row),
                }
            )
        if not (
            isclose(detail_accepted_total, top_accepted, rel_tol=0, abs_tol=1e-6)
            and isclose(
                detail_submitted_total, top_submitted, rel_tol=0, abs_tol=1e-6
            )
        ):
            raise CollectorError(
                "SRF detail submitted/accepted sums must equal top-level totals "
                f"for operation {operation_id}"
            )
        output.extend(operation_output)
    return output


def fetch_on_rrp(*, count: int = 400, user_agent: str = DEFAULT_USER_AGENT) -> list[dict[str, Any]]:
    payload = get_json(
        f"{API_ROOT}/rp/reverserepo/fixed/results/last/{count}.json",
        user_agent=user_agent,
    )
    return parse_on_rrp(payload)


def fetch_srf(
    *,
    count: int = 400,
    operational_readiness_operation_ids: Iterable[str] = (),
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[dict[str, Any]]:
    payload = get_json(
        f"{API_ROOT}/rp/repo/allotment/results/last/{count}.json",
        user_agent=user_agent,
    )
    return parse_srf(
        payload,
        operational_readiness_operation_ids=operational_readiness_operation_ids,
    )


def fetch_srf_operations(
    *, count: int = 400, user_agent: str = DEFAULT_USER_AGENT
) -> list[dict[str, Any]]:
    payload = get_json(
        f"{API_ROOT}/rp/repo/allotment/results/last/{count}.json",
        user_agent=user_agent,
    )
    return normalized_srf_operations(payload)


def default_rate_window(*, years: int = 2) -> tuple[date, date]:
    end = datetime.now(timezone.utc).astimezone(NEW_YORK).date()
    return end - timedelta(days=366 * years), end
