"""Dependency-injected, fail-closed interfaces for rights-held P1 sources."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


Fetcher = Callable[[str], Any]
Parser = Callable[[Any], Any]


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str
    availability: str
    value: Any | None
    observations: tuple[Any, ...]
    reason: str | None
    network_requested: bool


@dataclass(frozen=True)
class P1ProviderInterface:
    """A provider boundary that checks both gates before invoking a fetcher."""

    provider_id: str
    endpoint: str
    enabled: bool = False
    redistribution_cleared: bool = False
    hold_reason: str = "Public redistribution rights are not cleared."

    def collect(self, fetcher: Fetcher, parser: Parser) -> ProviderResult:
        if not self.enabled or not self.redistribution_cleared:
            return ProviderResult(
                provider_id=self.provider_id,
                availability="UNAVAILABLE_FREE",
                value=None,
                observations=(),
                reason=self.hold_reason,
                network_requested=False,
            )
        payload = fetcher(self.endpoint)
        parsed = parser(payload)
        observations = (
            tuple(parsed)
            if isinstance(parsed, (list, tuple))
            else ()
        )
        return ProviderResult(
            provider_id=self.provider_id,
            availability="ACTIVE_FREE",
            value=parsed,
            observations=observations,
            reason=None,
            network_requested=True,
        )


def held_p1_interfaces() -> Mapping[str, P1ProviderInterface]:
    """Return production-default P1 interfaces; every network gate is closed."""

    return {
        "vix_vix3m": P1ProviderInterface(
            provider_id="vix_vix3m",
            endpoint="provider://cboe/vix-vix3m",
            hold_reason="No redistribution-cleared Cboe feed is configured.",
        ),
        "cboe_skew": P1ProviderInterface(
            provider_id="cboe_skew",
            endpoint="provider://cboe/skew",
            hold_reason="No redistribution-cleared Cboe feed is configured.",
        ),
        "crypto_funding": P1ProviderInterface(
            provider_id="crypto_funding",
            endpoint="provider://crypto/funding",
            hold_reason=(
                "Public endpoints do not provide redistribution rights for "
                "this public dashboard."
            ),
        ),
        "trend_following": P1ProviderInterface(
            provider_id="trend_following",
            endpoint="provider://prices/trend",
            hold_reason=(
                "Redistribution-cleared equity and cross-asset price inputs "
                "are not configured."
            ),
        ),
        "cross_asset": P1ProviderInterface(
            provider_id="cross_asset",
            endpoint="provider://prices/cross-asset",
            hold_reason=(
                "Several planned price series carry third-party redistribution "
                "restrictions."
            ),
        ),
    }
