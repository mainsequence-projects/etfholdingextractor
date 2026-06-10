from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_PROVIDERS = ("invesco", "ishares", "state_street", "vanguard")
ISHARES_PRODUCT_LISTING_URL = "https://www.ishares.com/us/products/etf-investments"
INVESCO_HOLDINGS_LANDING_URL_TEMPLATE = (
    "https://www.invesco.com/us/financial-products/etfs/holdings"
    "?audienceType=Investor&ticker={ticker}"
)
VANGUARD_PROFILE_URL_TEMPLATE = (
    "https://investor.vanguard.com/investment-products/etfs/profile/{ticker}#portfolio-composition"
)
STATE_STREET_QUICK_INFO_URL_TEMPLATE = (
    "https://www.ssga.com/bin/v1/ssmp/fund/productquickinfo"
    "?country=us&language=en&role=intermediary&ticker%5B%5D={ticker}"
)


@dataclass(frozen=True, slots=True)
class IsharesHoldingsSource:
    requested_ticker: str
    holdings_ticker: str
    product_listing_url: str


@dataclass(frozen=True, slots=True)
class InvescoHoldingsSource:
    requested_ticker: str
    holdings_ticker: str
    landing_url: str


@dataclass(frozen=True, slots=True)
class VanguardHoldingsSource:
    requested_ticker: str
    profile_url: str


@dataclass(frozen=True, slots=True)
class StateStreetHoldingsSource:
    requested_ticker: str
    holdings_ticker: str
    quick_info_url: str


def normalize_provider_name(provider: str) -> str:
    return provider.strip().lower()


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def get_ishares_holdings_source(ticker: str) -> IsharesHoldingsSource | None:
    normalized_ticker = normalize_ticker(ticker)
    if not normalized_ticker:
        return None
    return IsharesHoldingsSource(
        requested_ticker=normalized_ticker,
        holdings_ticker=normalized_ticker,
        product_listing_url=ISHARES_PRODUCT_LISTING_URL,
    )


def get_invesco_holdings_source(ticker: str) -> InvescoHoldingsSource | None:
    normalized_ticker = normalize_ticker(ticker)
    if not normalized_ticker:
        return None
    return InvescoHoldingsSource(
        requested_ticker=normalized_ticker,
        holdings_ticker=normalized_ticker,
        landing_url=INVESCO_HOLDINGS_LANDING_URL_TEMPLATE.format(ticker=normalized_ticker),
    )


def get_vanguard_holdings_source(ticker: str) -> VanguardHoldingsSource | None:
    normalized_ticker = normalize_ticker(ticker)
    if not normalized_ticker:
        return None
    return VanguardHoldingsSource(
        requested_ticker=normalized_ticker,
        profile_url=VANGUARD_PROFILE_URL_TEMPLATE.format(ticker=normalized_ticker.lower()),
    )


def get_state_street_holdings_source(ticker: str) -> StateStreetHoldingsSource | None:
    normalized_ticker = normalize_ticker(ticker)
    if not normalized_ticker:
        return None
    return StateStreetHoldingsSource(
        requested_ticker=normalized_ticker,
        holdings_ticker=normalized_ticker,
        quick_info_url=STATE_STREET_QUICK_INFO_URL_TEMPLATE.format(
            ticker=normalized_ticker.lower()
        ),
    )
