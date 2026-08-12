import json
from datetime import date, timedelta
from math import exp
from pathlib import Path

import pytest

from pipeline.providers.p1_interfaces import P1ProviderInterface, held_p1_interfaces
from pipeline.transforms.p1_held import (
    cross_asset_correlations,
    crypto_funding_summary,
    skew_tail_risk_statistics,
    trend_following_proxy,
    vix_vix3m_term_structure,
)


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "p1_held_synthetic.json").read_text()
)


def test_vix_vix3m_inner_join_ratio_spread_and_percentile():
    vix = [*FIXTURE["vix"], {"date": "2026-08-07", "value": 99.0}]
    output = vix_vix3m_term_structure(
        vix,
        FIXTURE["vix3m"],
        percentile_window=4,
        minimum_percentile_samples=3,
    )

    assert [item["date"] for item in output] == [
        "2026-08-03",
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
    ]
    assert output[0]["ratio_percentile"] is None
    assert output[-1]["date"] == "2026-08-06"
    assert {key: value for key, value in output[-1].items() if key != "date"} == pytest.approx(
        {
            "vix": 24.0,
            "vix3m": 20.0,
            "ratio": 1.2,
            "term_spread": -4.0,
            "ratio_percentile": 0.875,
            "percentile_sample_size": 4,
        }
    )


def test_skew_changes_and_three_year_percentile_keep_insufficient_null():
    stats = skew_tail_risk_statistics(
        FIXTURE["skew"],
        percentile_window=21,
        minimum_percentile_samples=21,
    )
    assert stats == {
        "observation_date": "2026-07-21",
        "level": 120.0,
        "change_5_observations": 5.0,
        "change_20_observations": 20.0,
        "percentile_3_year": pytest.approx(20.5 / 21),
        "percentile_sample_size": 21,
    }
    insufficient = skew_tail_risk_statistics(
        FIXTURE["skew"][:20],
        percentile_window=21,
        minimum_percentile_samples=21,
    )
    assert insufficient["change_20_observations"] is None
    assert insufficient["percentile_3_year"] is None


def test_crypto_funding_respects_intervals_and_uses_multi_venue_medians():
    btc = crypto_funding_summary(
        FIXTURE["funding"], asset="BTC", as_of="2026-08-12T00:00:00Z"
    )
    assert btc["venue"] == "MULTI_VENUE_MEDIAN"
    assert btc["venue_count"] == 2
    assert btc["confidence"] == "MEDIUM"
    alpha = btc["venues"]["ALPHA"]
    assert alpha["latest_settled_at"] == "2026-08-12T00:00:00Z"
    assert {key: value for key, value in alpha.items() if key != "latest_settled_at"} == pytest.approx(
        {
            "latest_funding_rate": 0.003,
            "latest_interval_hours": 8.0,
            "latest_daily_normalized_rate": 0.009,
            "settled_sum_24h": 0.004,
            "mean_daily_normalized_7d": 0.00375,
            "percentile_7d": 0.875,
            "sample_size_7d": 4,
        }
    )
    assert btc["venues"]["BETA"]["latest_interval_hours"] == 12
    assert btc["latest_daily_normalized_rate"] == pytest.approx(0.0065)
    assert btc["settled_sum_24h"] == pytest.approx(0.005)

    eth = crypto_funding_summary(
        FIXTURE["funding"], asset="ETH", as_of="2026-08-12T00:00:00Z"
    )
    assert eth["venue"] == "ALPHA"
    assert eth["venue_count"] == 1
    assert eth["confidence"] == "LOW"


def test_crypto_funding_empty_and_invalid_intervals_fail_closed():
    empty = crypto_funding_summary(
        [], asset="BTC", as_of="2026-08-12T00:00:00Z"
    )
    assert empty["venue_count"] == 0
    assert empty["latest_daily_normalized_rate"] is None
    assert empty["settled_sum_24h"] is None
    invalid = [
        {
            "asset": "BTC",
            "venue": "ALPHA",
            "settled_at": "2026-08-12T00:00:00Z",
            "funding_rate": 0.001,
            "interval_hours": 0,
        }
    ]
    with pytest.raises(ValueError, match="interval_hours must be positive"):
        crypto_funding_summary(
            invalid, asset="BTC", as_of="2026-08-12T00:00:00Z"
        )


def _dated_prices(count, *, falling=False):
    start = date(2026, 1, 1)
    values = range(count, 0, -1) if falling else range(1, count + 1)
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "value": float(value)}
        for index, value in enumerate(values)
    ]


def test_trend_proxy_discloses_20_60_momentum_and_ma_regime():
    rising = trend_following_proxy(_dated_prices(61))
    assert rising["observation_date"] == "2026-03-02"
    assert rising["return_20d_pct"] == pytest.approx((61 / 41 - 1) * 100)
    assert rising["return_60d_pct"] == pytest.approx(6000)
    assert rising["moving_average_20d"] == pytest.approx(51.5)
    assert rising["moving_average_60d"] == pytest.approx(31.5)
    assert rising["regime"] == "ABOVE_BOTH"

    partial = trend_following_proxy(_dated_prices(20))
    assert partial["return_20d_pct"] is None
    assert partial["return_60d_pct"] is None
    assert partial["regime"] == "UNKNOWN"


def _cross_asset_fixture(common_changes):
    start = date(2026, 1, 1)
    equity = 100.0
    usd = 90.0
    btc = 1000.0
    oil = 70.0
    yield_level = 4.0
    output = {key: [] for key in ("equity", "usd", "btc", "oil", "yield10y")}
    for index in range(common_changes + 1):
        day = (start + timedelta(days=index)).isoformat()
        output["equity"].append({"date": day, "value": equity})
        output["usd"].append({"date": day, "value": usd})
        output["btc"].append({"date": day, "value": btc})
        output["oil"].append({"date": day, "value": oil})
        output["yield10y"].append({"date": day, "value": yield_level})
        change = 0.001 + (index % 7) * 0.0002
        equity *= exp(change)
        usd *= exp(change)
        btc *= exp(-change)
        oil *= exp(change * 0.5)
        yield_level += change / 100
    return output


def test_cross_asset_inner_join_transforms_and_sample_guards():
    pairs = [
        ("equity_usd", "equity", "usd"),
        ("equity_yield", "equity", "yield10y"),
        ("equity_btc", "equity", "btc"),
        ("equity_oil", "equity", "oil"),
    ]
    result = cross_asset_correlations(
        _cross_asset_fixture(40),
        price_series_ids=("equity", "usd", "btc", "oil"),
        yield_series_ids=("yield10y",),
        pairs=pairs,
    )
    assert result["equity_usd"]["correlation_20d"] == pytest.approx(1)
    assert result["equity_yield"]["right_transform"] == "YIELD_BP_CHANGE"
    assert result["equity_yield"]["correlation_60d"] == pytest.approx(1)
    assert result["equity_btc"]["correlation_20d"] == pytest.approx(-1)
    assert result["equity_oil"]["sample_size_60d"] == 40

    fourteen = cross_asset_correlations(
        _cross_asset_fixture(14),
        price_series_ids=("equity", "usd", "btc", "oil"),
        yield_series_ids=("yield10y",),
        pairs=pairs,
    )
    assert fourteen["equity_usd"]["correlation_20d"] is None
    assert fourteen["equity_usd"]["correlation_60d"] is None

    thirty_nine = cross_asset_correlations(
        _cross_asset_fixture(39),
        price_series_ids=("equity", "usd", "btc", "oil"),
        yield_series_ids=("yield10y",),
        pairs=pairs,
    )
    assert thirty_nine["equity_usd"]["correlation_20d"] == pytest.approx(1)
    assert thirty_nine["equity_usd"]["correlation_60d"] is None


def test_rights_held_interfaces_make_zero_requests_and_publish_no_value():
    calls = []

    def forbidden_fetch(endpoint):
        calls.append(endpoint)
        raise AssertionError("rights-held provider attempted network access")

    def forbidden_parser(payload):
        raise AssertionError(f"rights-held provider parsed payload: {payload}")

    results = {
        provider_id: interface.collect(forbidden_fetch, forbidden_parser)
        for provider_id, interface in held_p1_interfaces().items()
    }
    assert calls == []
    assert set(results) == {
        "vix_vix3m",
        "cboe_skew",
        "crypto_funding",
        "trend_following",
        "cross_asset",
    }
    assert all(result.availability == "UNAVAILABLE_FREE" for result in results.values())
    assert all(result.value is None for result in results.values())
    assert all(result.observations == () for result in results.values())
    assert all(result.network_requested is False for result in results.values())

    enabled_without_rights = P1ProviderInterface(
        provider_id="still-held",
        endpoint="fixture://must-not-run",
        enabled=True,
        redistribution_cleared=False,
    )
    held = enabled_without_rights.collect(forbidden_fetch, forbidden_parser)
    assert calls == []
    assert held.value is None
    assert held.network_requested is False


def test_provider_interface_dependencies_are_injected_when_both_gates_pass():
    calls = []
    interface = P1ProviderInterface(
        provider_id="synthetic",
        endpoint="fixture://synthetic",
        enabled=True,
        redistribution_cleared=True,
    )
    result = interface.collect(
        lambda endpoint: calls.append(endpoint) or {"values": [1, 2]},
        lambda payload: payload["values"],
    )
    assert calls == ["fixture://synthetic"]
    assert result.value == [1, 2]
    assert result.observations == (1, 2)
    assert result.network_requested is True
