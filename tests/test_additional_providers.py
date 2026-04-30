from __future__ import annotations

import io
import unittest
import zipfile

from etfh_extractor.providers.invesco import InvescoHoldingsProvider
from etfh_extractor.providers.state_street import StateStreetHoldingsProvider
from etfh_extractor.providers.vanguard import VanguardHoldingsProvider


def _build_state_street_workbook() -> bytes:
    workbook_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets>
        <sheet name="holdings" sheetId="1" r:id="rId1"/>
      </sheets>
    </workbook>
    """
    rels_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    </Relationships>
    """
    shared_strings_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="10" uniqueCount="10">
      <si><t>Fund Name:</t></si>
      <si><t>State Street SPY Test Fund</t></si>
      <si><t>Date</t></si>
      <si><t>2026-04-30</t></si>
      <si><t>Name</t></si>
      <si><t>Ticker</t></si>
      <si><t>Weight</t></si>
      <si><t>Apple Inc.</t></si>
      <si><t>AAPL</t></si>
      <si><t>Microsoft Corp.</t></si>
      <si><t>MSFT</t></si>
    </sst>
    """
    worksheet_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1">
          <c r="A1" t="s"><v>0</v></c>
          <c r="B1" t="s"><v>1</v></c>
        </row>
        <row r="2">
          <c r="A2" t="s"><v>2</v></c>
          <c r="B2" t="s"><v>3</v></c>
        </row>
        <row r="5">
          <c r="A5" t="s"><v>4</v></c>
          <c r="B5" t="s"><v>5</v></c>
          <c r="C5" t="s"><v>6</v></c>
        </row>
        <row r="6">
          <c r="A6" t="s"><v>7</v></c>
          <c r="B6" t="s"><v>8</v></c>
          <c r="C6"><v>7.1</v></c>
        </row>
        <row r="7">
          <c r="A7" t="s"><v>9</v></c>
          <c r="B7" t="s"><v>10</v></c>
          <c r="C7"><v>6.5</v></c>
        </row>
      </sheetData>
    </worksheet>
    """

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as workbook_zip:
        workbook_zip.writestr("[Content_Types].xml", "")
        workbook_zip.writestr("xl/workbook.xml", workbook_xml)
        workbook_zip.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        workbook_zip.writestr("xl/sharedStrings.xml", shared_strings_xml)
        workbook_zip.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return buffer.getvalue()


class AdditionalProviderTests(unittest.TestCase):
    def test_invesco_reads_weighted_holdings_payload(self) -> None:
        landing_url = (
            "https://www.invesco.com/us/financial-products/etfs/holdings"
            "?audienceType=Investor&ticker=QQQ"
        )
        api_url = "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/holdings/fund?idType=ticker&productType=ETF"
        responses = {
            landing_url: f'<div data-holdings-api="{api_url}"></div>',
            api_url: """
            {
              "fundName": "Invesco QQQ Trust",
              "asOfDate": "2026-04-30",
              "holdings": [
                {"ticker": "AAPL", "name": "Apple Inc.", "weight": 8.1, "securityTypeName": "Equity"},
                {"ticker": "MSFT", "name": "Microsoft Corp.", "weight": 7.4, "securityTypeName": "Equity"}
              ]
            }
            """,
        }
        provider = InvescoHoldingsProvider(fetcher=responses.__getitem__)
        fund = provider.read_ticker("QQQ")

        self.assertEqual(fund.fund_name, "Invesco QQQ Trust")
        self.assertEqual(fund.as_of_date, "2026-04-30")
        self.assertEqual(fund.ticker_weights(), {"AAPL": 8.1, "MSFT": 7.4})

    def test_vanguard_reads_weighted_holdings_payload(self) -> None:
        profile_url = (
            "https://investor.vanguard.com/investment-products/etfs/profile/vug#portfolio-composition"
        )
        payload_url = (
            "https://investor.vanguard.com/vmf/api/VUG/portfolio-holding/stock.json?asOfType=daily"
        )
        responses = {
            profile_url: "<html><title>Vanguard Growth ETF</title></html>",
            payload_url: """
            {
              "fund": {
                "name": "Vanguard Growth ETF",
                "asOfDate": "2026-04-30",
                "entity": [
                  {"ticker": "AAPL", "name": "Apple Inc.", "weight": 11.2},
                  {"ticker": "MSFT", "name": "Microsoft Corp.", "weight": 10.5}
                ]
              }
            }
            """,
        }
        provider = VanguardHoldingsProvider(fetcher=responses.__getitem__)
        fund = provider.read_ticker("VUG")

        self.assertEqual(fund.fund_name, "Vanguard Growth ETF")
        self.assertEqual(fund.as_of_date, "2026-04-30")
        self.assertEqual(fund.ticker_weights(), {"AAPL": 11.2, "MSFT": 10.5})

    def test_state_street_reads_weighted_holdings_workbook(self) -> None:
        quick_info_url = (
            "https://www.ssga.com/bin/v1/ssmp/fund/productquickinfo"
            "?country=us&language=en&role=intermediary&ticker%5B%5D=spy"
        )
        product_url = "https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy"
        workbook_url = (
            "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
        )
        text_responses = {
            quick_info_url: '{"link":["/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy"]}',
            product_url: f'<a href="{workbook_url}">Daily Holdings</a>',
        }
        binary_responses = {
            workbook_url: _build_state_street_workbook(),
        }
        provider = StateStreetHoldingsProvider(
            fetcher=text_responses.__getitem__,
            binary_fetcher=binary_responses.__getitem__,
        )
        fund = provider.read_ticker("SPY")

        self.assertEqual(fund.fund_name, "State Street SPY Test Fund")
        self.assertEqual(fund.as_of_date, "2026-04-30")
        self.assertEqual(fund.ticker_weights(), {"AAPL": 7.1, "MSFT": 6.5})


if __name__ == "__main__":
    unittest.main()
