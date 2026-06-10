from __future__ import annotations

import html
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence

from ..models import Holding


HEADER_MAP = {
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
IGNORED_TICKER_VALUES = {"", "-", "--", "N/A", "CASH", "USD"}
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
HTML_TABLE_ROW_PATTERN = re.compile(r"<tr\b[^>]*>(?P<row>.*?)</tr>", re.IGNORECASE | re.DOTALL)
HTML_TABLE_CELL_PATTERN = re.compile(
    r"<(?:td|th)\b[^>]*>(?P<cell>.*?)</(?:td|th)>",
    re.IGNORECASE | re.DOTALL,
)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
XML_BARE_AMPERSAND_PATTERN = re.compile(
    r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9A-Fa-f]+;)"
)
INVALID_XML_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def normalize_token(value: str) -> str:
    token = re.sub(r"[^0-9a-zA-Z]+", "_", value.strip().lower())
    return re.sub(r"_+", "_", token).strip("_")


def normalize_ticker(value: str) -> str:
    return value.strip().upper()


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def parse_float(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip()
    if not cleaned or cleaned == "--":
        return None
    return float(cleaned.replace(",", "").replace("%", ""))


def is_probable_security_ticker(value: str) -> bool:
    normalized_value = normalize_ticker(value)
    if normalized_value in IGNORED_TICKER_VALUES:
        return False
    return bool(TICKER_PATTERN.fullmatch(normalized_value))


def clean_html_cell(raw_value: str) -> str:
    without_tags = HTML_TAG_PATTERN.sub(" ", raw_value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def parse_html_table_rows(page_html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for row_match in HTML_TABLE_ROW_PATTERN.finditer(page_html):
        row_html = row_match.group("row")
        cells = [
            clean_html_cell(cell_match.group("cell"))
            for cell_match in HTML_TABLE_CELL_PATTERN.finditer(row_html)
        ]
        if cells:
            rows.append(cells)
    return rows


def resolve_header_index(headers: Sequence[str], candidates: Sequence[str]) -> int | None:
    normalized_headers = {header.strip().lower(): idx for idx, header in enumerate(headers)}
    for candidate in candidates:
        idx = normalized_headers.get(candidate.strip().lower())
        if idx is not None:
            return idx
    return None


def _cell_value(row: Sequence[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _optional_float(row: Sequence[str], index: int | None) -> float | None:
    return parse_float(_cell_value(row, index))


def parse_tabular_holdings_rows(
    rows: Sequence[Sequence[str]],
    *,
    ticker_headers: Sequence[str] = ("Ticker", "Ticker Symbol", "Symbol"),
    name_headers: Sequence[str] = ("Name", "Security Name", "Holding Name"),
    weight_headers: Sequence[str] = ("Weight", "Weight (%)", "% Weight", "% of Net Assets"),
    sector_headers: Sequence[str] = ("Sector",),
    asset_class_headers: Sequence[str] = ("Asset Class", "AssetType", "Security Type"),
    market_value_headers: Sequence[str] = ("Market Value", "Market Value ($)", "Market Value(USD)"),
    quantity_headers: Sequence[str] = ("Quantity", "Shares", "Shares Held"),
    price_headers: Sequence[str] = ("Price", "Market Price"),
    location_headers: Sequence[str] = ("Location", "Country"),
    exchange_headers: Sequence[str] = ("Exchange",),
    currency_headers: Sequence[str] = ("Currency",),
    allowed_asset_classes: Sequence[str] | None = None,
) -> list[Holding]:
    if not rows:
        raise ValueError("No tabular holdings rows were found.")

    header_index = None
    header_row: Sequence[str] | None = None
    ticker_index = None
    weight_index = None

    for idx, row in enumerate(rows):
        ticker_idx = resolve_header_index(row, ticker_headers)
        weight_idx = resolve_header_index(row, weight_headers)
        if ticker_idx is None or weight_idx is None:
            continue
        header_index = idx
        header_row = row
        ticker_index = ticker_idx
        weight_index = weight_idx
        break

    if header_index is None or header_row is None or ticker_index is None or weight_index is None:
        raise ValueError("Could not locate a holdings header row containing ticker and weight.")

    allowed_asset_classes_normalized = (
        {value.strip().lower() for value in allowed_asset_classes}
        if allowed_asset_classes
        else None
    )
    name_index = resolve_header_index(header_row, name_headers)
    sector_index = resolve_header_index(header_row, sector_headers)
    asset_class_index = resolve_header_index(header_row, asset_class_headers)
    market_value_index = resolve_header_index(header_row, market_value_headers)
    quantity_index = resolve_header_index(header_row, quantity_headers)
    price_index = resolve_header_index(header_row, price_headers)
    location_index = resolve_header_index(header_row, location_headers)
    exchange_index = resolve_header_index(header_row, exchange_headers)
    currency_index = resolve_header_index(header_row, currency_headers)

    holdings: list[Holding] = []
    for row in rows[header_index + 1 :]:
        ticker = normalize_ticker(_cell_value(row, ticker_index))
        if not is_probable_security_ticker(ticker):
            continue
        weight = _optional_float(row, weight_index)
        if weight is None:
            continue
        asset_class = _cell_value(row, asset_class_index) or None
        if (
            allowed_asset_classes_normalized is not None
            and asset_class is not None
            and asset_class.strip().lower() not in allowed_asset_classes_normalized
        ):
            continue
        name = _cell_value(row, name_index) or ticker
        holdings.append(
            Holding(
                ticker=ticker,
                name=name,
                weight=weight,
                sector=_cell_value(row, sector_index) or None,
                asset_class=asset_class,
                market_value=_optional_float(row, market_value_index),
                quantity=_optional_float(row, quantity_index),
                price=_optional_float(row, price_index),
                location=_cell_value(row, location_index) or None,
                exchange=_cell_value(row, exchange_index) or None,
                currency=_cell_value(row, currency_index) or None,
            )
        )

    if not holdings:
        raise ValueError("No weighted holdings rows were parsed.")
    return holdings


def parse_html_table_holdings(
    page_html: str,
    **kwargs,
) -> list[Holding]:
    return parse_tabular_holdings_rows(parse_html_table_rows(page_html), **kwargs)


def parse_xlsx_rows(
    workbook_bytes: bytes,
    *,
    worksheet_name: str | None = None,
) -> list[list[str]]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook_zip:
        workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        relationships_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))

        rels_by_id = {
            relationship.get("Id"): relationship.get("Target")
            for relationship in relationships_root.findall(
                "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
            )
        }
        sheets = workbook_root.findall(".//x:sheets/x:sheet", namespace)
        if not sheets:
            raise ValueError("Could not find any worksheets in the xlsx workbook.")

        selected_sheet = None
        if worksheet_name is None:
            selected_sheet = sheets[0]
        else:
            for sheet in sheets:
                if (sheet.get("name") or "").strip().lower() == worksheet_name.strip().lower():
                    selected_sheet = sheet
                    break
        if selected_sheet is None:
            raise ValueError(f"Could not find worksheet {worksheet_name!r} in the xlsx workbook.")

        relation_id = selected_sheet.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        sheet_target = rels_by_id.get(relation_id)
        if not sheet_target:
            raise ValueError("Could not resolve the worksheet target in the xlsx workbook.")

        sheet_path = f"xl/{sheet_target.lstrip('/')}"

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_strings_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for string_item in shared_strings_root.findall("x:si", namespace):
                texts = [
                    text_node.text or ""
                    for text_node in string_item.findall(".//x:t", namespace)
                ]
                shared_strings.append("".join(texts))

        worksheet_root = ET.fromstring(workbook_zip.read(sheet_path))
        rows: list[list[str]] = []
        for row_element in worksheet_root.findall(".//x:sheetData/x:row", namespace):
            row: list[str] = []
            current_index = 1
            for cell_element in row_element.findall("x:c", namespace):
                cell_ref = cell_element.get("r") or ""
                column_letters = re.match(r"([A-Z]+)", cell_ref)
                if column_letters:
                    target_index = 0
                    for letter in column_letters.group(1):
                        target_index = target_index * 26 + (ord(letter) - ord("A") + 1)
                    while current_index < target_index:
                        row.append("")
                        current_index += 1

                cell_type = cell_element.get("t")
                value_element = cell_element.find("x:v", namespace)
                inline_text_element = cell_element.find("x:is/x:t", namespace)
                if inline_text_element is not None:
                    value = inline_text_element.text or ""
                elif value_element is None:
                    value = ""
                else:
                    raw_value = value_element.text or ""
                    if cell_type == "s":
                        value = shared_strings[int(raw_value)]
                    else:
                        value = raw_value

                row.append(value)
                current_index += 1
            rows.append(row)

        return rows


def find_labeled_row_value(
    rows: Sequence[Sequence[str]],
    labels: Sequence[str],
) -> str | None:
    normalized_labels = {label.strip().lower() for label in labels}
    for row in rows:
        if len(row) >= 2 and row[0].strip().lower() in normalized_labels and row[1].strip():
            return row[1].strip()
    return None


def find_first_string_value(
    payload: object,
    candidates: Sequence[str],
) -> str | None:
    normalized_candidates = {candidate.lower() for candidate in candidates}

    def walk(node: object) -> str | None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if str(key).strip().lower() in normalized_candidates and value not in (None, ""):
                    return str(value).strip()
            for value in node.values():
                result = walk(value)
                if result:
                    return result
        elif isinstance(node, list):
            for item in node:
                result = walk(item)
                if result:
                    return result
        return None

    return walk(payload)


def load_json_payload(payload_text: str) -> Mapping[str, object]:
    payload = json.loads(payload_text)
    if not isinstance(payload, Mapping):
        raise ValueError("Expected a JSON object payload.")
    return payload
