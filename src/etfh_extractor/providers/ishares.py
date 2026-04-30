from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from ..artifacts import ArtifactPayload
from ..exceptions import DownloadLinkNotFoundError, FetchError, UnsupportedProviderError, WorkbookParseError
from ..models import FundHoldings, Holding
from ..settings import IsharesHoldingsSource, get_ishares_holdings_source
from .base import HoldingsProvider
from .common import HEADER_MAP, normalize_token, parse_float, strip_tags


WORKSHEET_PATTERN = re.compile(
    r'<ss:Worksheet ss:Name="Holdings">(.*?)</ss:Worksheet>',
    re.S,
)
ROW_PATTERN = re.compile(r"<ss:Row\b[^>]*>(.*?)</ss:Row>", re.S)
CELL_PATTERN = re.compile(r"<ss:Cell\b([^>]*)>(.*?)</ss:Cell>", re.S)
DATA_PATTERN = re.compile(r"<ss:Data\b[^>]*>(.*?)</ss:Data>", re.S)
LINK_FALLBACK_PATTERN = re.compile(r'href="([^"]*fileType=xls[^"]*)"', re.I)


class DataDownloadParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.download_url: str | None = None
        self.current_href: str | None = None
        self.current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or self.download_url:
            return
        self.current_href = dict(attrs).get("href")
        self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None and not self.download_url:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self.current_href is None or self.download_url:
            return

        text = " ".join(part.strip() for part in self.current_text if part.strip()).lower()
        href = self.current_href
        if href and ("data download" in text or "filetype=xls" in href.lower()):
            self.download_url = urljoin(self.base_url, href)

        self.current_href = None
        self.current_text = []


class IsharesHoldingsProvider(HoldingsProvider):
    provider_name = "ishares"
    product_href_pattern_template = (
        r'href=["\'](?P<href>/us/products/[^"\']+)["\'][^>]*>{ticker}</a>'
    )

    @classmethod
    def supports_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and "ishares.com" in parsed.netloc.lower()

    @classmethod
    def resolve_product_url_from_listing(
        cls,
        *,
        listing_html: str,
        source: IsharesHoldingsSource,
    ) -> str | None:
        pattern = re.compile(
            cls.product_href_pattern_template.format(ticker=re.escape(source.holdings_ticker)),
            re.IGNORECASE,
        )
        match = pattern.search(listing_html)
        if match is None:
            return None
        return urljoin(source.product_listing_url, match.group("href"))

    def read_ticker(self, ticker: str) -> FundHoldings:
        source = get_ishares_holdings_source(ticker)
        if source is None:
            raise UnsupportedProviderError("ETF ticker must not be empty.")

        listing_html = self.fetcher(source.product_listing_url)
        product_url = self.resolve_product_url_from_listing(
            listing_html=listing_html,
            source=source,
        )
        if product_url is None:
            raise FetchError(
                f"Could not resolve the iShares product page for {source.requested_ticker} "
                f"from {source.product_listing_url}."
            )
        page_html = self.fetcher(product_url)
        download_url = self.extract_download_url(product_url, page_html)
        workbook_text = self.fetcher(download_url)
        fund_holdings = self.parse_workbook(product_url, download_url, workbook_text)
        return self.persist_artifacts(
            fund_holdings=fund_holdings,
            requested_ticker=source.requested_ticker,
            source_artifacts=[
                ArtifactPayload("listing_page.html", listing_html),
                ArtifactPayload("fund_page.html", page_html),
                ArtifactPayload("holdings_export.xls", workbook_text),
            ],
            metadata_extra={
                "listing_url": source.product_listing_url,
                "resolution_mode": "ticker",
            },
        )

    def read_url(self, url: str) -> FundHoldings:
        if not self.supports_url(url):
            raise UnsupportedProviderError(
                "Only full iShares fund page URLs are supported by the iShares provider."
            )
        page_html = self.fetcher(url)
        download_url = self.extract_download_url(url, page_html)
        workbook_text = self.fetcher(download_url)
        fund_holdings = self.parse_workbook(url, download_url, workbook_text)
        return self.persist_artifacts(
            fund_holdings=fund_holdings,
            source_artifacts=[
                ArtifactPayload("fund_page.html", page_html),
                ArtifactPayload("holdings_export.xls", workbook_text),
            ],
            metadata_extra={"resolution_mode": "url"},
        )

    def extract_download_url(self, page_url: str, page_html: str) -> str:
        parser = DataDownloadParser(page_url)
        parser.feed(page_html)
        if parser.download_url:
            return parser.download_url

        match = LINK_FALLBACK_PATTERN.search(page_html)
        if match:
            return urljoin(page_url, html.unescape(match.group(1)))

        raise DownloadLinkNotFoundError(
            f"Could not find an iShares holdings download link on {page_url}."
        )

    def parse_workbook(self, source_url: str, download_url: str, workbook_text: str) -> FundHoldings:
        match = WORKSHEET_PATTERN.search(workbook_text)
        if not match:
            raise WorkbookParseError("Could not find the Holdings worksheet in the iShares export.")

        parsed_rows = [self.parse_row(row) for row in ROW_PATTERN.findall(match.group(1))]
        header_index = self.find_header_index(parsed_rows)
        headers = [self.normalize_header(header) for header in parsed_rows[header_index]]

        holdings: list[Holding] = []
        for row in parsed_rows[header_index + 1 :]:
            if not any(row):
                continue
            holding = self.build_holding(headers, row)
            if holding is not None:
                holdings.append(holding)

        if not holdings:
            raise WorkbookParseError("The iShares export did not contain any holdings rows.")

        fund_name = self.metadata_value(parsed_rows, 1, 0)
        as_of_date = self.find_label_value(parsed_rows, "Fund Holdings as of") or self.metadata_value(
            parsed_rows,
            0,
            0,
        )

        return FundHoldings(
            url=source_url,
            download_url=download_url,
            fund_name=fund_name,
            as_of_date=as_of_date,
            holdings=tuple(holdings),
        )

    def parse_row(self, row_markup: str) -> list[str]:
        values: list[str] = []
        column_index = 1

        for attrs, cell_markup in CELL_PATTERN.findall(row_markup):
            index_match = re.search(r'ss:Index="(\d+)"', attrs)
            if index_match:
                column_index = int(index_match.group(1))

            while len(values) < column_index - 1:
                values.append("")

            data_match = DATA_PATTERN.search(cell_markup)
            cell_value = strip_tags(data_match.group(1)) if data_match else ""
            values.append(cell_value)
            column_index += 1

        return values

    def find_header_index(self, rows: list[list[str]]) -> int:
        for index, row in enumerate(rows):
            if "Ticker" in row and "Weight (%)" in row:
                return index
        raise WorkbookParseError("Could not find the holdings header row in the iShares export.")

    def normalize_header(self, header: str) -> str:
        token = normalize_token(header)
        return HEADER_MAP.get(token, token)

    def build_holding(self, headers: list[str], row: list[str]) -> Holding | None:
        padded_row = list(row) + [""] * max(0, len(headers) - len(row))
        row_data = dict(zip(headers, padded_row, strict=False))

        ticker = row_data.get("ticker", "").strip()
        name = row_data.get("name", "").strip()
        weight_raw = row_data.get("weight", "").strip()
        if not ticker or not name or not weight_raw:
            return None

        return Holding(
            ticker=ticker,
            name=name,
            weight=parse_float(weight_raw) or 0.0,
            sector=row_data.get("sector") or None,
            asset_class=row_data.get("asset_class") or None,
            market_value=parse_float(row_data.get("market_value", "")),
            notional_value=parse_float(row_data.get("notional_value", "")),
            quantity=parse_float(row_data.get("quantity", "")),
            price=parse_float(row_data.get("price", "")),
            location=row_data.get("location") or None,
            exchange=row_data.get("exchange") or None,
            currency=row_data.get("currency") or None,
            fx_rate=parse_float(row_data.get("fx_rate", "")),
            accrual_date=(row_data.get("accrual_date") or None),
        )

    def find_label_value(self, rows: list[list[str]], label: str) -> str | None:
        for row in rows:
            if len(row) >= 2 and row[0] == label:
                return row[1]
        return None

    def metadata_value(self, rows: list[list[str]], row_index: int, col_index: int) -> str:
        try:
            return rows[row_index][col_index]
        except IndexError as exc:
            raise WorkbookParseError(
                "The iShares export metadata rows were not in the expected format."
            ) from exc
