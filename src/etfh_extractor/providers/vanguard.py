from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlparse

from ..artifacts import ArtifactPayload
from ..exceptions import UnsupportedProviderError, WorkbookParseError
from ..models import FundHoldings, Holding
from ..settings import VanguardHoldingsSource, get_vanguard_holdings_source
from .base import HoldingsProvider
from .common import find_first_string_value, is_probable_security_ticker, load_json_payload, normalize_ticker, parse_float


class VanguardHoldingsProvider(HoldingsProvider):
    provider_name = "vanguard"
    profile_path_pattern = re.compile(r"/profile/(?P<ticker>[^/?#]+)", re.IGNORECASE)
    weight_key_candidates = (
        "weight",
        "weighting",
        "weightPercentage",
        "percentWeight",
        "portfolioWeight",
        "percentOfAssets",
    )
    name_key_candidates = ("name", "holdingName", "securityName", "issuerName", "description")
    ticker_key_candidates = ("ticker", "symbol")
    asset_class_key_candidates = ("assetClass", "securityType", "assetType")

    @classmethod
    def supports_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and "vanguard.com" in parsed.netloc.lower()

    @staticmethod
    def build_payload_url(source: VanguardHoldingsSource) -> str:
        return (
            f"https://investor.vanguard.com/vmf/api/{source.requested_ticker}"
            "/portfolio-holding/stock.json?asOfType=daily"
        )

    @classmethod
    def extract_ticker_from_profile_url(cls, url: str) -> str:
        match = cls.profile_path_pattern.search(urlparse(url).path)
        if match is None:
            raise UnsupportedProviderError(
                "Could not resolve a Vanguard ETF ticker from the provided profile URL."
            )
        return normalize_ticker(match.group("ticker"))

    @classmethod
    def _mapping_value(
        cls,
        mapping: Mapping[str, object],
        candidates: tuple[str, ...],
    ) -> object | None:
        normalized = {key.strip().lower(): value for key, value in mapping.items()}
        for candidate in candidates:
            if candidate.strip().lower() in normalized:
                return normalized[candidate.strip().lower()]
        return None

    @classmethod
    def parse_holdings_payload(
        cls,
        *,
        source_url: str,
        download_url: str,
        payload_text: str,
        fund_name_fallback: str,
    ) -> FundHoldings:
        payload = load_json_payload(payload_text)
        fund_payload = payload.get("fund")
        if isinstance(fund_payload, Mapping):
            raw_holdings = fund_payload.get("entity")
        else:
            raw_holdings = payload.get("entity")
        if not isinstance(raw_holdings, list):
            raise WorkbookParseError("The Vanguard holdings payload did not contain a holdings list.")

        holdings: list[Holding] = []
        for entry in raw_holdings:
            if not isinstance(entry, Mapping):
                continue
            ticker_value = cls._mapping_value(entry, cls.ticker_key_candidates)
            ticker = normalize_ticker(str(ticker_value or ""))
            if not is_probable_security_ticker(ticker):
                continue
            weight = parse_float(cls._mapping_value(entry, cls.weight_key_candidates))
            if weight is None:
                continue
            name_value = cls._mapping_value(entry, cls.name_key_candidates)
            asset_class_value = cls._mapping_value(entry, cls.asset_class_key_candidates)
            holdings.append(
                Holding(
                    ticker=ticker,
                    name=str(name_value or ticker).strip(),
                    weight=weight,
                    asset_class=str(asset_class_value).strip() if asset_class_value else None,
                )
            )

        if not holdings:
            raise WorkbookParseError("No weighted holdings were parsed from the Vanguard payload.")

        fund_name = (
            find_first_string_value(payload, ("fundName", "name", "longName", "productName"))
            or fund_name_fallback
        )
        as_of_date = find_first_string_value(
            payload,
            ("asOfDate", "effectiveDate", "date", "holdingsDate"),
        ) or ""
        return FundHoldings(
            url=source_url,
            download_url=download_url,
            fund_name=fund_name,
            as_of_date=as_of_date,
            holdings=tuple(holdings),
        )

    def read_ticker(self, ticker: str) -> FundHoldings:
        source = get_vanguard_holdings_source(ticker)
        if source is None:
            raise UnsupportedProviderError("ETF ticker must not be empty.")
        return self.read_url(source.profile_url, requested_ticker=source.requested_ticker)

    def read_url(self, url: str, requested_ticker: str | None = None) -> FundHoldings:
        if not self.supports_url(url):
            raise UnsupportedProviderError(
                "Only supported Vanguard fund URLs are supported by the Vanguard provider."
            )

        resolved_ticker = requested_ticker or self.extract_ticker_from_profile_url(url)
        source = get_vanguard_holdings_source(resolved_ticker)
        if source is None:
            raise UnsupportedProviderError("Could not build a Vanguard holdings source.")

        page_html = self.fetcher(source.profile_url)
        payload_url = self.build_payload_url(source)
        payload_text = self.fetcher(payload_url)
        fund_holdings = self.parse_holdings_payload(
            source_url=source.profile_url,
            download_url=payload_url,
            payload_text=payload_text,
            fund_name_fallback=resolved_ticker,
        )
        return self.persist_artifacts(
            fund_holdings=fund_holdings,
            requested_ticker=resolved_ticker,
            source_artifacts=[
                ArtifactPayload("profile_page.html", page_html),
                ArtifactPayload("holdings_payload.json", payload_text),
            ],
            metadata_extra={"resolution_mode": "ticker" if requested_ticker else "url"},
        )
