from __future__ import annotations

import html
import re
from collections.abc import Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from ..artifacts import ArtifactPayload
from ..exceptions import FetchError, UnsupportedProviderError, WorkbookParseError
from ..models import FundHoldings, Holding
from ..settings import InvescoHoldingsSource, get_invesco_holdings_source
from .base import HoldingsProvider
from .browser import capture_response_text_with_playwright, fetch_page_html_with_playwright
from .common import (
    find_first_string_value,
    is_probable_security_ticker,
    load_json_payload,
    normalize_ticker,
    parse_float,
)


class InvescoHoldingsProvider(HoldingsProvider):
    provider_name = "invesco"
    about_href_pattern = re.compile(
        r'href=["\'](?P<href>[^"\']*/about\.html(?:#[^"\']*)?)["\']',
        re.IGNORECASE,
    )
    holdings_api_pattern = re.compile(
        r'data-[^=]*holding(?:s)?-api=["\'](?P<url>https://[^"\']+/holdings/fund[^"\']*)["\']',
        re.IGNORECASE,
    )
    holdings_api_template_pattern = re.compile(
        r"https://dng-api\.invesco\.com/cache/v1/accounts/\{locale\}/shareclasses/\{id\}/holdings/fund\?idType=\{uniqueIdentifier\}[^\"']*productType=ETF",
        re.IGNORECASE,
    )
    meta_content_pattern_template = r'<meta\s+name="{name}"\s+content="(?P<value>[^"]+)"'
    json_value_pattern_template = r'"{name}"\s*:\s*"(?P<value>[^"]+)"'
    weight_key_candidates = (
        "weight",
        "weighting",
        "percentWeight",
        "weightPercent",
        "portfolioWeight",
        "percentage",
    )
    name_key_candidates = (
        "name",
        "holdingName",
        "securityName",
        "issuerName",
        "description",
    )
    ticker_key_candidates = ("ticker", "symbol")
    asset_class_key_candidates = ("assetClass", "securityTypeName", "assetType")

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        fetcher: Callable[[str], str] | None = None,
        binary_fetcher: Callable[[str], bytes] | None = None,
        artifact_root=None,
        user_agent: str = "etfh-extractor/0.1.0",
        browser_fetcher: Callable[..., str] | None = None,
        browser_response_fetcher: Callable[..., str] | None = None,
    ) -> None:
        super().__init__(
            timeout=timeout,
            fetcher=fetcher,
            binary_fetcher=binary_fetcher,
            artifact_root=artifact_root,
            user_agent=user_agent,
        )
        self.browser_fetcher = browser_fetcher or fetch_page_html_with_playwright
        self.browser_response_fetcher = (
            browser_response_fetcher or capture_response_text_with_playwright
        )

    @classmethod
    def supports_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and "invesco.com" in parsed.netloc.lower()

    @staticmethod
    def normalize_holdings_api_url(api_url: str) -> str:
        parsed = urlparse(html.unescape(api_url))
        query_items = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key != "loadType"
        ]
        return urlunparse(parsed._replace(query=urlencode(query_items)))

    @classmethod
    def extract_holdings_api_url(cls, page_html: str) -> str | None:
        match = cls.holdings_api_pattern.search(page_html)
        if match is None:
            return None
        return cls.normalize_holdings_api_url(match.group("url"))

    @classmethod
    def extract_meta_content(cls, *, page_html: str, name: str) -> str | None:
        match = re.search(
            cls.meta_content_pattern_template.format(name=re.escape(name)),
            page_html,
            re.IGNORECASE,
        )
        if match is None:
            return None
        return html.unescape(match.group("value")).strip()

    @classmethod
    def extract_json_value(cls, *, page_html: str, name: str) -> str | None:
        unescaped_html = html.unescape(page_html)
        match = re.search(
            cls.json_value_pattern_template.format(name=re.escape(name)),
            unescaped_html,
            re.IGNORECASE,
        )
        if match is None:
            return None
        return match.group("value").strip()

    @classmethod
    def extract_holdings_api_url_from_model(cls, page_html: str) -> str | None:
        unescaped_html = html.unescape(page_html)
        template_match = cls.holdings_api_template_pattern.search(unescaped_html)
        if template_match is None:
            return None

        unique_identifier = cls.extract_json_value(
            page_html=page_html,
            name="uniqueIdentifier",
        )
        locale = cls.extract_json_value(page_html=page_html, name="locale") or "en_US"
        ticker = cls.extract_meta_content(page_html=page_html, name="ticker")
        shareclass = cls.extract_meta_content(page_html=page_html, name="shareclass")
        cusip = cls.extract_json_value(page_html=page_html, name="cusip")

        identifier_values = {
            "ticker": ticker,
            "cusip": cusip,
            "shareClassIdentifier": shareclass,
        }
        identifier_value = identifier_values.get(unique_identifier or "")
        if not unique_identifier or not identifier_value:
            return None

        return cls.normalize_holdings_api_url(
            template_match.group(0)
            .replace("{locale}", locale)
            .replace("{id}", identifier_value)
            .replace("{uniqueIdentifier}", unique_identifier)
        )

    @classmethod
    def extract_about_page_url(cls, *, page_html: str, page_url: str) -> str | None:
        match = cls.about_href_pattern.search(page_html)
        if match is None:
            return None
        return urljoin(page_url, html.unescape(match.group("href")))

    def resolve_payload_from_page(
        self,
        *,
        page_url: str,
        page_html: str,
    ) -> tuple[str, str | None, str | None]:
        holdings_api_url = self.extract_holdings_api_url(page_html)
        if holdings_api_url is not None:
            return self.fetcher(holdings_api_url), holdings_api_url, None

        holdings_api_url = self.extract_holdings_api_url_from_model(page_html)
        if holdings_api_url is not None:
            return self.fetcher(holdings_api_url), holdings_api_url, None

        about_page_url = self.extract_about_page_url(page_html=page_html, page_url=page_url)
        if about_page_url is not None:
            about_page_html = self.fetcher(about_page_url)
            holdings_api_url = self.extract_holdings_api_url(about_page_html)
            if holdings_api_url is None:
                holdings_api_url = self.extract_holdings_api_url_from_model(about_page_html)
            if holdings_api_url is not None:
                return self.fetcher(holdings_api_url), holdings_api_url, about_page_html

        payload_text = self.browser_response_fetcher(
            page_url,
            response_url_substring="/holdings/fund",
            exclude_response_url_substring="loadType=initial",
            timeout=self.timeout,
        )
        return payload_text, "browser://holdings/fund", None

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
        raw_holdings = payload.get("holdings")
        if not isinstance(raw_holdings, list):
            raise WorkbookParseError("The Invesco holdings payload did not contain a holdings list.")

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
            raise WorkbookParseError("No weighted holdings were parsed from the Invesco payload.")

        fund_name = (
            find_first_string_value(payload, ("fundName", "productName", "shareClassName"))
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
        source = get_invesco_holdings_source(ticker)
        if source is None:
            raise UnsupportedProviderError("ETF ticker must not be empty.")
        return self.read_url(source.landing_url, requested_ticker=source.requested_ticker)

    def read_url(self, url: str, requested_ticker: str | None = None) -> FundHoldings:
        if not self.supports_url(url):
            raise UnsupportedProviderError(
                "Only supported Invesco fund URLs are supported by the Invesco provider."
            )

        page_html = self.fetcher(url)
        payload_text, payload_source_url, about_page_html = self.resolve_payload_from_page(
            page_url=url,
            page_html=page_html,
        )
        fund_name_fallback = (
            self.extract_meta_content(page_html=page_html, name="ticker")
            or requested_ticker
            or "Invesco ETF"
        )
        fund_holdings = self.parse_holdings_payload(
            source_url=url,
            download_url=payload_source_url or url,
            payload_text=payload_text,
            fund_name_fallback=fund_name_fallback,
        )

        source_artifacts = [ArtifactPayload("landing_page.html", page_html)]
        if about_page_html is not None:
            source_artifacts.append(ArtifactPayload("about_page.html", about_page_html))
        source_artifacts.append(ArtifactPayload("holdings_payload.json", payload_text))
        return self.persist_artifacts(
            fund_holdings=fund_holdings,
            source_artifacts=source_artifacts,
            requested_ticker=requested_ticker,
            metadata_extra={"resolution_mode": "ticker" if requested_ticker else "url"},
        )
