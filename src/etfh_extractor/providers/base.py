from __future__ import annotations

import ssl
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from ..artifacts import ArtifactPayload, persist_extraction_artifacts
from ..exceptions import FetchError, UnsupportedProviderError
from ..models import FundHoldings


class HoldingsProvider(ABC):
    provider_name: str

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
        self.fetcher = fetcher or self._fetch_text
        self.binary_fetcher = binary_fetcher or self._fetch_bytes
        self.artifact_root = artifact_root

    @classmethod
    @abstractmethod
    def supports_url(cls, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_url(self, url: str) -> FundHoldings:
        raise NotImplementedError

    def read_ticker(self, ticker: str) -> FundHoldings:
        raise UnsupportedProviderError(
            f"Provider {self.provider_name!r} does not support ticker-based extraction."
        )

    def persist_artifacts(
        self,
        *,
        fund_holdings: FundHoldings,
        source_artifacts: list[ArtifactPayload],
        requested_ticker: str | None = None,
        metadata_extra: dict[str, object] | None = None,
    ) -> FundHoldings:
        return persist_extraction_artifacts(
            provider_name=self.provider_name,
            fund_holdings=fund_holdings,
            source_artifacts=source_artifacts,
            requested_ticker=requested_ticker,
            artifact_root=self.artifact_root,
            metadata_extra=metadata_extra,
        )

    def _fetch_text(self, url: str) -> str:
        payload, charset = self._fetch_raw(url)
        return payload.decode(charset, errors="replace").lstrip("\ufeff")

    def _fetch_bytes(self, url: str) -> bytes:
        payload, _ = self._fetch_raw(url)
        return payload

    def _fetch_raw(self, url: str) -> tuple[bytes, str]:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xml,text/xml,*/*",
            },
        )

        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(request, timeout=self.timeout, context=ssl_context) as response:
                payload = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
        except (HTTPError, URLError) as exc:
            raise FetchError(f"Failed to fetch {url}: {exc}") from exc

        return payload, charset
