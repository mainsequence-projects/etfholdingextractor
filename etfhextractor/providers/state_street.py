from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from ..artifacts import ArtifactPayload
from ..exceptions import FetchError, UnsupportedProviderError, WorkbookParseError
from ..models import FundHoldings
from ..settings import StateStreetHoldingsSource, get_state_street_holdings_source
from .base import HoldingsProvider
from .common import (
    find_labeled_row_value,
    normalize_ticker,
    parse_tabular_holdings_rows,
    parse_xlsx_rows,
)


class StateStreetHoldingsProvider(HoldingsProvider):
    provider_name = "state_street"
    download_href_pattern = re.compile(
        r"""href=["'](?P<href>[^"']*holdings-daily[^"']*\.xlsx)["']""",
        re.IGNORECASE,
    )

    @classmethod
    def supports_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and "ssga.com" in parsed.netloc.lower()

    @staticmethod
    def resolve_product_url_from_quick_info_text(
        quick_info_text: str,
        *,
        quick_info_url: str,
    ) -> str:
        payload = json.loads(quick_info_text)
        links = payload.get("link") or []
        if not links:
            raise FetchError(
                f"State Street did not publish a product link in {quick_info_url}."
            )
        return urljoin("https://www.ssga.com", str(links[0]))

    @classmethod
    def extract_holdings_download_url(
        cls,
        *,
        page_html: str,
        product_url: str,
    ) -> str | None:
        match = cls.download_href_pattern.search(page_html)
        if match is None:
            return None
        return urljoin(product_url, match.group("href"))

    @classmethod
    def parse_holdings_workbook(
        cls,
        *,
        source_url: str,
        download_url: str,
        workbook_bytes: bytes,
        fund_name_fallback: str,
    ) -> FundHoldings:
        rows = parse_xlsx_rows(workbook_bytes, worksheet_name="holdings")
        holdings = parse_tabular_holdings_rows(
            rows,
            ticker_headers=("Ticker", "Ticker Symbol", "Symbol"),
            name_headers=("Name", "Security Name"),
            weight_headers=("Weight", "Weight (%)", "% Weight"),
        )
        fund_name = find_labeled_row_value(rows, ("Fund Name:", "Fund Name", "Fund"))
        as_of_date = find_labeled_row_value(rows, ("As of Date", "Date", "Holdings Date")) or ""
        return FundHoldings(
            url=source_url,
            download_url=download_url,
            fund_name=fund_name or fund_name_fallback,
            as_of_date=as_of_date,
            holdings=tuple(holdings),
        )

    def read_ticker(self, ticker: str) -> FundHoldings:
        source = get_state_street_holdings_source(ticker)
        if source is None:
            raise UnsupportedProviderError("ETF ticker must not be empty.")

        quick_info_text = self.fetcher(source.quick_info_url)
        product_url = self.resolve_product_url_from_quick_info_text(
            quick_info_text,
            quick_info_url=source.quick_info_url,
        )
        page_html = self.fetcher(product_url)
        holdings_url = self.extract_holdings_download_url(
            page_html=page_html,
            product_url=product_url,
        )
        if holdings_url is None:
            raise WorkbookParseError(
                f"Could not find a State Street daily holdings download link for {source.requested_ticker}."
            )
        workbook_bytes = self.binary_fetcher(holdings_url)
        fund_holdings = self.parse_holdings_workbook(
            source_url=product_url,
            download_url=holdings_url,
            workbook_bytes=workbook_bytes,
            fund_name_fallback=source.requested_ticker,
        )
        return self.persist_artifacts(
            fund_holdings=fund_holdings,
            requested_ticker=source.requested_ticker,
            source_artifacts=[
                ArtifactPayload("quick_info.json", quick_info_text),
                ArtifactPayload("product_page.html", page_html),
                ArtifactPayload("holdings_export.xlsx", workbook_bytes),
            ],
            metadata_extra={"resolution_mode": "ticker"},
        )

    def read_url(self, url: str) -> FundHoldings:
        if not self.supports_url(url):
            raise UnsupportedProviderError(
                "Only supported State Street fund URLs are supported by the State Street provider."
            )

        page_url = url
        quick_info_text: str | None = None
        if "productquickinfo" in url:
            quick_info_text = self.fetcher(url)
            page_url = self.resolve_product_url_from_quick_info_text(
                quick_info_text,
                quick_info_url=url,
            )

        page_html = self.fetcher(page_url)
        holdings_url = self.extract_holdings_download_url(
            page_html=page_html,
            product_url=page_url,
        )
        if holdings_url is None:
            raise WorkbookParseError(
                "Could not find a State Street daily holdings download link on the provided page."
            )
        workbook_bytes = self.binary_fetcher(holdings_url)
        fund_holdings = self.parse_holdings_workbook(
            source_url=page_url,
            download_url=holdings_url,
            workbook_bytes=workbook_bytes,
            fund_name_fallback=normalize_ticker(page_url.rstrip("/").split("/")[-1]),
        )
        source_artifacts = [ArtifactPayload("product_page.html", page_html)]
        if quick_info_text is not None:
            source_artifacts.insert(0, ArtifactPayload("quick_info.json", quick_info_text))
        source_artifacts.append(ArtifactPayload("holdings_export.xlsx", workbook_bytes))
        return self.persist_artifacts(
            fund_holdings=fund_holdings,
            source_artifacts=source_artifacts,
            metadata_extra={"resolution_mode": "url"},
        )
