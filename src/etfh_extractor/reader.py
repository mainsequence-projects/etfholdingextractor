from __future__ import annotations

import html
import ssl
from collections.abc import Callable, Iterable
from html.parser import HTMLParser
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import certifi

from .exceptions import (
    DownloadLinkNotFoundError,
    FetchError,
    UnsupportedProviderError,
    WorkbookParseError,
)
from .models import FundHoldings, Holding

_WORKSHEET_PATTERN = re.compile(r'<ss:Worksheet ss:Name="Holdings">(.*?)</ss:Worksheet>', re.S)
_ROW_PATTERN = re.compile(r"<ss:Row\b[^>]*>(.*?)</ss:Row>", re.S)
_CELL_PATTERN = re.compile(r"<ss:Cell\b([^>]*)>(.*?)</ss:Cell>", re.S)
_DATA_PATTERN = re.compile(r"<ss:Data\b[^>]*>(.*?)</ss:Data>", re.S)
_LINK_FALLBACK_PATTERN = re.compile(r'href="([^"]*fileType=xls[^"]*)"', re.I)

_HEADER_MAP = {
    "ticker": "ticker",
    "name": "name",
    "sector": "sector",
    "asset_class": "asset_class",
    "market_value": "market_value",
    "weight": "weight",
    "notional_value": "notional_value",
    "quantity": "quantity",
    "price": "price",
    "location": "location",
    "exchange": "exchange",
    "currency": "currency",
    "fx_rate": "fx_rate",
    "accrual_date": "accrual_date",
}


def _normalize_token(value: str) -> str:
    token = re.sub(r"[^0-9a-zA-Z]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", token).strip("_")


def _strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _parse_float(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned or cleaned == "--":
        return None
    return float(cleaned.replace(",", ""))


class _DataDownloadParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.download_url: str | None = None
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a" or self.download_url:
            return
        self._current_href = dict(attrs).get("href")
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None and not self.download_url:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None or self.download_url:
            return

        text = " ".join(part.strip() for part in self._current_text if part.strip()).lower()
        href = self._current_href
        if href and ("data download" in text or "filetype=xls" in href.lower()):
            self.download_url = urljoin(self.base_url, href)

        self._current_href = None
        self._current_text = []


class ETFHoldingsReader:
    """Extract holdings from iShares fund page URLs."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        fetcher: Callable[[str], str] | None = None,
        user_agent: str = "etfh-extractor/0.1.0",
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.fetcher = fetcher or self._fetch_text

    def read(self, url: str) -> FundHoldings:
        self._validate_url(url)
        page_html = self.fetcher(url)
        download_url = self._extract_download_url(url, page_html)
        workbook_text = self.fetcher(download_url)
        return self._parse_workbook(url, download_url, workbook_text)

    def read_many(self, urls: Iterable[str]) -> list[FundHoldings]:
        return [self.read(url) for url in urls]

    def extract_ticker_weights(self, url: str) -> dict[str, float]:
        return self.read(url).ticker_weights()

    def extract_many_ticker_weights(self, urls: Iterable[str]) -> dict[str, dict[str, float]]:
        return {result.url: result.ticker_weights() for result in self.read_many(urls)}

    def _fetch_text(self, url: str) -> str:
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

        return payload.decode(charset, errors="replace").lstrip("\ufeff")

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or "ishares.com" not in parsed.netloc.lower():
            raise UnsupportedProviderError(
                "Only full iShares fund page URLs are supported right now."
            )

    def _extract_download_url(self, page_url: str, page_html: str) -> str:
        parser = _DataDownloadParser(page_url)
        parser.feed(page_html)
        if parser.download_url:
            return parser.download_url

        match = _LINK_FALLBACK_PATTERN.search(page_html)
        if match:
            return urljoin(page_url, html.unescape(match.group(1)))

        raise DownloadLinkNotFoundError(
            f"Could not find an iShares holdings download link on {page_url}."
        )

    def _parse_workbook(self, source_url: str, download_url: str, workbook_text: str) -> FundHoldings:
        match = _WORKSHEET_PATTERN.search(workbook_text)
        if not match:
            raise WorkbookParseError("Could not find the Holdings worksheet in the iShares export.")

        parsed_rows = [self._parse_row(row) for row in _ROW_PATTERN.findall(match.group(1))]
        header_index = self._find_header_index(parsed_rows)
        headers = [self._normalize_header(header) for header in parsed_rows[header_index]]

        holdings: list[Holding] = []
        for row in parsed_rows[header_index + 1 :]:
            if not any(row):
                continue
            holding = self._build_holding(headers, row)
            if holding is not None:
                holdings.append(holding)

        if not holdings:
            raise WorkbookParseError("The iShares export did not contain any holdings rows.")

        fund_name = self._metadata_value(parsed_rows, 1, 0)
        as_of_date = self._find_label_value(parsed_rows, "Fund Holdings as of") or self._metadata_value(
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

    def _parse_row(self, row_markup: str) -> list[str]:
        values: list[str] = []
        column_index = 1

        for attrs, cell_markup in _CELL_PATTERN.findall(row_markup):
            index_match = re.search(r'ss:Index="(\d+)"', attrs)
            if index_match:
                column_index = int(index_match.group(1))

            while len(values) < column_index - 1:
                values.append("")

            data_match = _DATA_PATTERN.search(cell_markup)
            cell_value = _strip_tags(data_match.group(1)) if data_match else ""
            values.append(cell_value)
            column_index += 1

        return values

    def _find_header_index(self, rows: list[list[str]]) -> int:
        for index, row in enumerate(rows):
            if "Ticker" in row and "Weight (%)" in row:
                return index
        raise WorkbookParseError("Could not find the holdings header row in the iShares export.")

    def _normalize_header(self, header: str) -> str:
        token = _normalize_token(header)
        return _HEADER_MAP.get(token, token)

    def _build_holding(self, headers: list[str], row: list[str]) -> Holding | None:
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
            weight=_parse_float(weight_raw) or 0.0,
            sector=row_data.get("sector") or None,
            asset_class=row_data.get("asset_class") or None,
            market_value=_parse_float(row_data.get("market_value", "")),
            notional_value=_parse_float(row_data.get("notional_value", "")),
            quantity=_parse_float(row_data.get("quantity", "")),
            price=_parse_float(row_data.get("price", "")),
            location=row_data.get("location") or None,
            exchange=row_data.get("exchange") or None,
            currency=row_data.get("currency") or None,
            fx_rate=_parse_float(row_data.get("fx_rate", "")),
            accrual_date=(row_data.get("accrual_date") or None),
        )

    def _find_label_value(self, rows: list[list[str]], label: str) -> str | None:
        for row in rows:
            if len(row) >= 2 and row[0] == label:
                return row[1]
        return None

    def _metadata_value(self, rows: list[list[str]], row_index: int, col_index: int) -> str:
        try:
            return rows[row_index][col_index]
        except IndexError as exc:
            raise WorkbookParseError("The iShares export metadata rows were not in the expected format.") from exc


def extract_ticker_weights(url: str, **kwargs: Any) -> dict[str, float]:
    return ETFHoldingsReader(**kwargs).extract_ticker_weights(url)


def extract_many_ticker_weights(
    urls: Iterable[str],
    **kwargs: Any,
) -> dict[str, dict[str, float]]:
    return ETFHoldingsReader(**kwargs).extract_many_ticker_weights(urls)
