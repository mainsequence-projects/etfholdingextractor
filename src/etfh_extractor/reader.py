from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .exceptions import UnsupportedProviderError
from .models import FundHoldings
from .providers.registry import build_provider, build_provider_from_url


class ETFHoldingsReader:
    """Extract holdings from supported ETF providers."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        fetcher: Callable[[str], str] | None = None,
        binary_fetcher: Callable[[str], bytes] | None = None,
        artifact_root: Path | None = None,
        user_agent: str = "etfh-extractor/0.1.0",
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.fetcher = fetcher
        self.binary_fetcher = binary_fetcher
        self.artifact_root = artifact_root

    def read(self, url: str) -> FundHoldings:
        provider = build_provider_from_url(
            url,
            timeout=self.timeout,
            fetcher=self.fetcher,
            binary_fetcher=self.binary_fetcher,
            artifact_root=self.artifact_root,
            user_agent=self.user_agent,
        )
        return provider.read_url(url)

    def read_many(self, urls: Iterable[str]) -> list[FundHoldings]:
        return [self.read(url) for url in urls]

    def read_ticker(self, ticker: str, *, provider: str | None = None) -> FundHoldings:
        if provider is None:
            raise UnsupportedProviderError(
                "Ticker-only extraction requires an explicit provider. "
                "Provider inference is supported from fund URLs, not from ETF tickers."
            )

        active_provider = build_provider(
            provider,
            timeout=self.timeout,
            fetcher=self.fetcher,
            binary_fetcher=self.binary_fetcher,
            artifact_root=self.artifact_root,
            user_agent=self.user_agent,
        )
        return active_provider.read_ticker(ticker)

    def extract_ticker_weights(self, url: str) -> dict[str, float]:
        return self.read(url).ticker_weights()

    def extract_many_ticker_weights(self, urls: Iterable[str]) -> dict[str, dict[str, float]]:
        return {result.url: result.ticker_weights() for result in self.read_many(urls)}

    def extract_ticker_weights_for_ticker(
        self,
        ticker: str,
        *,
        provider: str | None = None,
    ) -> dict[str, float]:
        return self.read_ticker(ticker, provider=provider).ticker_weights()


def extract_ticker_weights(url: str, **kwargs: Any) -> dict[str, float]:
    return ETFHoldingsReader(**kwargs).extract_ticker_weights(url)


def extract_many_ticker_weights(
    urls: Iterable[str],
    **kwargs: Any,
) -> dict[str, dict[str, float]]:
    return ETFHoldingsReader(**kwargs).extract_many_ticker_weights(urls)


def extract_ticker_weights_for_ticker(
    ticker: str,
    *,
    provider: str | None = None,
    **kwargs: Any,
) -> dict[str, float]:
    return ETFHoldingsReader(**kwargs).extract_ticker_weights_for_ticker(
        ticker,
        provider=provider,
    )
