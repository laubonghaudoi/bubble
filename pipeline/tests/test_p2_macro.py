from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from pipeline.collectors.common import CollectorError
from pipeline.collectors.fred_p2 import (
    fetch_series_bundle,
    parse_series_bundle,
    parse_series_metadata,
    parse_series_observations,
)
from pipeline.transforms.p2_macro import (
    build_nonfinancial_equities_gdp_proxy,
    nonfinancial_equities_gdp_series,
    nonfinancial_equities_gdp_statistics,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def bundles():
    equities = fixture("fred_p2_nonfinancial_equities.json")
    gdp = fixture("fred_p2_gdp.json")
    return (
        parse_series_bundle(
            equities["metadata"],
            equities["observations"],
            series_id="NCBEILQ027S",
        ),
        parse_series_bundle(gdp["metadata"], gdp["observations"], series_id="GDP"),
    )


def test_collector_preserves_unscaled_values_metadata_and_revision_dates():
    equities, gdp = bundles()

    assert equities["series_id"] == "NCBEILQ027S"
    assert equities["units"] == "Millions of U.S. Dollars"
    assert equities["seasonal_adjustment_short"] == "NSA"
    assert equities["period_position"] == "END_OF_PERIOD"
    assert equities["last_updated"] == "2026-06-11T12:46:00Z"
    assert equities["observations"][0] == {
        "date": "2024-01-01",
        "value": 28_000_000.0,
        "realtime_start": "2026-08-12",
        "realtime_end": "2026-08-12",
    }
    assert gdp["units"] == "Billions of Dollars"
    assert gdp["seasonal_adjustment_short"] == "SAAR"


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("id", "SP500", "series id mismatch"),
        ("frequency", "Monthly", "frequency mismatch"),
        ("frequency_short", "M", "frequency_short mismatch"),
        ("units", "Index 2015=100", "units mismatch"),
        ("units_short", "Index", "units_short mismatch"),
        (
            "seasonal_adjustment",
            "Seasonally Adjusted",
            "seasonal_adjustment mismatch",
        ),
        ("seasonal_adjustment_short", "SA", "seasonal_adjustment_short mismatch"),
    ],
)
def test_metadata_contract_fails_closed_on_identity_or_semantic_drift(
    field, bad_value, message
):
    payload = fixture("fred_p2_nonfinancial_equities.json")["metadata"]
    payload["seriess"][0][field] = bad_value
    with pytest.raises(CollectorError, match=message):
        parse_series_metadata(payload, series_id="NCBEILQ027S")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"seriess": []},
        {"seriess": [{}, {}]},
        "<html>error</html>",
    ],
)
def test_metadata_empty_html_and_schema_drift_fail_closed(payload):
    with pytest.raises(CollectorError):
        parse_series_metadata(payload, series_id="GDP")


def test_observations_preserve_null_and_deduplicate_exact_rows():
    payload = fixture("fred_p2_gdp.json")["observations"]
    payload["observations"][1]["value"] = "."
    payload["observations"].append(deepcopy(payload["observations"][0]))
    parsed = parse_series_observations(payload)

    assert len(parsed) == 8
    assert parsed[1]["value"] is None


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload["observations"][0].__setitem__(
                "date", "2025-02-30"
            ),
            "ISO date",
        ),
        (
            lambda payload: payload["observations"][0].__setitem__("value", "NaN"),
            "not finite",
        ),
        (
            lambda payload: payload["observations"][0].__setitem__(
                "realtime_start", "not-a-date"
            ),
            "ISO date",
        ),
        (
            lambda payload: payload["observations"][0].__setitem__(
                "realtime_end", "2020-01-01"
            ),
            "realtime range is inverted",
        ),
    ],
)
def test_observation_domains_fail_closed(mutator, message):
    payload = fixture("fred_p2_gdp.json")["observations"]
    mutator(payload)
    with pytest.raises(CollectorError, match=message):
        parse_series_observations(payload)


def test_conflicting_duplicate_or_empty_observations_fail_closed():
    payload = fixture("fred_p2_gdp.json")["observations"]
    conflict = deepcopy(payload["observations"][0])
    conflict["value"] = "99999"
    payload["observations"].append(conflict)
    with pytest.raises(CollectorError, match="conflicting duplicate"):
        parse_series_observations(payload)

    for invalid in ({}, {"observations": []}, "<html>error</html>"):
        with pytest.raises(CollectorError):
            parse_series_observations(invalid)


def test_observation_cutoff_and_metadata_range_are_enforced():
    payload = fixture("fred_p2_gdp.json")["observations"]
    parsed = parse_series_observations(payload, observation_end=date(2025, 6, 30))
    assert parsed[-1]["date"] == "2025-04-01"

    metadata = fixture("fred_p2_gdp.json")["metadata"]
    metadata["seriess"][0]["observation_start"] = "2024-04-01"
    with pytest.raises(CollectorError, match="outside metadata range"):
        parse_series_bundle(
            metadata, payload, series_id="GDP", observation_end=date(2025, 12, 31)
        )

    with pytest.raises(CollectorError, match="no observations on or before"):
        parse_series_observations(payload, observation_end=date(2023, 12, 31))


def test_fetch_requires_key_and_calls_only_official_metadata_and_observation_apis(
    monkeypatch,
):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(CollectorError, match="FRED_API_KEY is required"):
        fetch_series_bundle("GDP", observation_start=date(2024, 1, 1))
    with pytest.raises(CollectorError, match="32-character"):
        fetch_series_bundle("GDP", observation_start=date(2024, 1, 1), api_key="BAD")
    with pytest.raises(CollectorError, match="not allowlisted"):
        fetch_series_bundle(
            "SP500", observation_start=date(2024, 1, 1), api_key="a" * 32
        )

    source = fixture("fred_p2_gdp.json")
    calls = []

    def fake_get_json(url, *, user_agent):
        calls.append((url, user_agent))
        return source["metadata"] if "/series?" in url else source["observations"]

    monkeypatch.setattr("pipeline.collectors.fred_p2.get_json", fake_get_json)
    result = fetch_series_bundle(
        "GDP",
        observation_start=date(2024, 1, 1),
        observation_end=date(2025, 12, 31),
        api_key="a" * 32,
        user_agent="Bubble tests test@example.com",
    )
    assert result["observations"][-1]["date"] == "2025-10-01"
    assert len(calls) == 2
    assert calls[0][0].startswith("https://api.stlouisfed.org/fred/series?")
    assert calls[1][0].startswith(
        "https://api.stlouisfed.org/fred/series/observations?"
    )
    metadata_query = parse_qs(urlparse(calls[0][0]).query)
    observation_query = parse_qs(urlparse(calls[1][0]).query)
    assert metadata_query["series_id"] == ["GDP"]
    assert observation_query["observation_start"] == ["2024-01-01"]
    assert observation_query["observation_end"] == ["2025-12-31"]
    assert observation_query["output_type"] == ["1"]
    assert {user_agent for _, user_agent in calls} == {"Bubble tests test@example.com"}


def test_fetch_rejects_inverted_dates_and_bad_success_bodies(monkeypatch):
    with pytest.raises(CollectorError, match="must not precede"):
        fetch_series_bundle(
            "GDP",
            observation_start=date(2025, 1, 1),
            observation_end=date(2024, 1, 1),
            api_key="a" * 32,
        )

    monkeypatch.setattr(
        "pipeline.collectors.fred_p2.get_json",
        lambda *_args, **_kwargs: "<html>blocked</html>",
    )
    with pytest.raises(CollectorError, match="metadata response must be an object"):
        fetch_series_bundle("GDP", observation_start=date(2024, 1, 1), api_key="a" * 32)


def test_transform_scales_joins_and_exposes_locked_integration_shape():
    equities, gdp = bundles()
    result = build_nonfinancial_equities_gdp_proxy(equities, gdp)
    latest = result["series"][-1]
    previous = result["series"][-2]
    prior_year = result["series"][-5]

    assert result["metric_id"] == "nonfinancial_equities_gdp_proxy"
    assert latest["date"] == "2025-12-31"
    assert latest["quarter"] == "2025-Q4"
    assert latest["equity_usd_bn"] == 37_800
    assert latest["gdp_usd_bn"] == 31_500
    assert latest["value"] == 120
    assert latest["change_1_quarter_pp"] == pytest.approx(
        latest["value"] - previous["value"]
    )
    assert latest["qoq_percent_change"] == pytest.approx(
        (latest["value"] / previous["value"] - 1) * 100, abs=1e-5
    )
    assert latest["yoy_percent_change"] == pytest.approx(
        (latest["value"] / prior_year["value"] - 1) * 100, abs=1e-5
    )
    assert latest["percentile_10y"] == 93.75
    assert latest["percentile_10y_sample_size"] == 8
    assert result["statistics"]["equity_usd_bn"] == 37_800
    assert result["statistics"]["percentile_10y_sample_size"] == 8
    assert set(result["statistics"]) == {
        "equity_usd_bn",
        "gdp_usd_bn",
        "qoq_percent_change",
        "yoy_percent_change",
        "percentile_10y",
        "percentile_10y_sample_size",
    }
    assert result["changes"] == {"one_quarter": latest["change_1_quarter_pp"]}
    assert result["context"] == {
        "equity_observation_date": "2025-10-01",
        "gdp_observation_date": "2025-10-01",
        "common_quarter": "2025-Q4",
    }
    assert "quarter-end" in result["caveats"][1]


def test_transform_normalizes_source_dates_but_preserves_each_date():
    equities, gdp = bundles()
    gdp["observations"][-1]["date"] = "2025-12-15"
    latest = nonfinancial_equities_gdp_series(equities, gdp)[-1]

    assert latest["date"] == "2025-12-31"
    assert latest["equities_source_date"] == "2025-10-01"
    assert latest["gdp_source_date"] == "2025-12-15"


def test_transform_is_exact_quarter_only_and_does_not_bridge_gaps_for_qoq():
    equities, gdp = bundles()
    gdp["observations"] = [
        point for point in gdp["observations"] if point["date"] != "2024-04-01"
    ]
    points = nonfinancial_equities_gdp_series(equities, gdp)
    q3 = next(point for point in points if point["quarter"] == "2024-Q3")

    assert "2024-Q2" not in {point["quarter"] for point in points}
    assert q3["change_1_quarter_pp"] is None
    assert q3["qoq_percent_change"] is None


def test_null_and_zero_denominator_remain_null_without_last_good_substitution():
    equities, gdp = bundles()
    equities["observations"][-1]["value"] = None
    latest = nonfinancial_equities_gdp_series(equities, gdp)[-1]
    assert latest["value"] is None
    assert latest["qoq_percent_change"] is None
    assert latest["percentile_10y"] is None
    assert latest["percentile_10y_sample_size"] == 7

    equities, gdp = bundles()
    gdp["observations"][-1]["value"] = 0
    latest = nonfinancial_equities_gdp_series(equities, gdp)[-1]
    assert latest["gdp_usd_bn"] == 0
    assert latest["value"] is None
    stats = nonfinancial_equities_gdp_statistics(
        nonfinancial_equities_gdp_series(equities, gdp)
    )
    assert stats["ratio_percent"] is None


def test_zero_prior_ratio_allows_pp_change_but_not_percent_change():
    equities, gdp = bundles()
    equities["observations"][-2]["value"] = 0
    latest = nonfinancial_equities_gdp_series(equities, gdp)[-1]

    assert latest["change_1_quarter_pp"] == 120
    assert latest["qoq_percent_change"] is None


@pytest.mark.parametrize(("series", "value"), [("equities", -1), ("gdp", -1)])
def test_negative_component_values_fail_closed(series, value):
    equities, gdp = bundles()
    target = equities if series == "equities" else gdp
    target["observations"][-1]["value"] = value
    with pytest.raises(CollectorError, match="cannot be negative"):
        nonfinancial_equities_gdp_series(equities, gdp)


def test_transform_rejects_conflicting_same_quarter_and_nonfinite_values():
    equities, gdp = bundles()
    conflict = deepcopy(equities["observations"][-1])
    conflict["date"] = "2025-12-01"
    conflict["value"] += 1
    equities["observations"].append(conflict)
    with pytest.raises(CollectorError, match="conflicting observations"):
        nonfinancial_equities_gdp_series(equities, gdp)

    equities, gdp = bundles()
    gdp["observations"][-1]["value"] = float("inf")
    with pytest.raises(CollectorError, match="must be finite"):
        nonfinancial_equities_gdp_series(equities, gdp)


def test_percentile_is_midrank_over_at_most_40_calendar_quarters():
    def source_bundle(series_id, values):
        observations = []
        for index, value in enumerate(values):
            year = 2015 + index // 4
            month = (index % 4) * 3 + 1
            observations.append(
                {
                    "date": date(year, month, 1).isoformat(),
                    "value": value,
                    "realtime_start": "2026-08-12",
                    "realtime_end": "2026-08-12",
                }
            )
        return {"series_id": series_id, "observations": observations}

    # Constant GDP and linearly increasing numerator make the latest point the
    # top of the inclusive 40-quarter window: (39 below + 0.5 equal) / 40 * 100.
    equities = source_bundle(
        "NCBEILQ027S", [(index + 1) * 1_000_000 for index in range(45)]
    )
    gdp = source_bundle("GDP", [1_000 for _ in range(45)])
    latest = nonfinancial_equities_gdp_series(equities, gdp)[-1]
    assert latest["percentile_10y_sample_size"] == 40
    assert latest["percentile_10y"] == 98.75

    tied = source_bundle("NCBEILQ027S", [1_000_000 for _ in range(45)])
    latest_tied = nonfinancial_equities_gdp_series(tied, gdp)[-1]
    assert latest_tied["percentile_10y"] == 50

    falling = source_bundle(
        "NCBEILQ027S", [(45 - index) * 1_000_000 for index in range(45)]
    )
    latest_low = nonfinancial_equities_gdp_series(falling, gdp)[-1]
    assert latest_low["percentile_10y"] == 1.25
    assert 0 <= latest_low["percentile_10y"] <= 100


def test_no_common_quarters_returns_explicit_empty_statistics():
    equities, gdp = bundles()
    for point in gdp["observations"]:
        year = int(point["date"][:4]) + 10
        point["date"] = f"{year}{point['date'][4:]}"
    points = nonfinancial_equities_gdp_series(equities, gdp)
    assert points == []
    assert nonfinancial_equities_gdp_statistics(points) == {
        "observation_date": None,
        "quarter": None,
        "ratio_percent": None,
        "equity_usd_bn": None,
        "gdp_usd_bn": None,
        "change_1_quarter_pp": None,
        "qoq_percent_change": None,
        "yoy_percent_change": None,
        "percentile_10y": None,
        "percentile_10y_sample_size": 0,
        "exact_common_quarter_count": 0,
    }
