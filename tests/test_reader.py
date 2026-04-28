from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from etfh_extractor import ETFHoldingsReader, extract_ticker_weights
from etfh_extractor.__main__ import main
from etfh_extractor.models import FundHoldings, Holding

MTUM_URL = "https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf"
MTUM_DOWNLOAD_URL = (
    "https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf/"
    "1521942788811.ajax?dataType=fund&fileName=iShares-MSCI-USA-Momentum-Factor-ETF_fund&fileType=xls"
)
MTUM_HTML = f"""
<html>
  <body>
    <a href="{MTUM_DOWNLOAD_URL}">Data Download</a>
  </body>
</html>
"""
MTUM_WORKBOOK = """<?xml version="1.0"?>
<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <ss:Worksheet ss:Name="Holdings">
    <ss:Table>
      <ss:Row><ss:Cell><ss:Data ss:Type="String">27-Apr-2026</ss:Data></ss:Cell></ss:Row>
      <ss:Row><ss:Cell><ss:Data ss:Type="String">iShares MSCI USA Momentum Factor ETF</ss:Data></ss:Cell></ss:Row>
      <ss:Row>
        <ss:Cell><ss:Data ss:Type="String">Fund Holdings as of</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Apr 27, 2026</ss:Data></ss:Cell>
      </ss:Row>
      <ss:Row><ss:Cell><ss:Data ss:Type="String"></ss:Data></ss:Cell></ss:Row>
      <ss:Row>
        <ss:Cell><ss:Data ss:Type="String">Ticker</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Name</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Sector</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Asset Class</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Market Value</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Weight (%)</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Notional Value</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Quantity</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Price</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Location</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Exchange</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Currency</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">FX Rate</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Accrual Date</ss:Data></ss:Cell>
      </ss:Row>
      <ss:Row>
        <ss:Cell><ss:Data ss:Type="String">MU</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">MICRON TECHNOLOGY INC</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Information Technology</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Equity</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1365036260</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">5.71228</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1365036260</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">2602250</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">524.56</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">United States</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">NASDAQ</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">USD</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">--</ss:Data></ss:Cell>
      </ss:Row>
      <ss:Row>
        <ss:Cell><ss:Data ss:Type="String">AVGO</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">BROADCOM INC</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Information Technology</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Equity</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1308309007.8</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">5.4749</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1308309007.8</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">3128429</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">418.2</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">United States</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">NASDAQ</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">USD</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">--</ss:Data></ss:Cell>
      </ss:Row>
      <ss:Row>
        <ss:Cell><ss:Data ss:Type="String">NVDA</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">NVIDIA CORP</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Information Technology</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">Equity</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1218281355.88</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">5.09816</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1218281355.88</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">5624308</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">216.61</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">United States</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">NASDAQ</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">USD</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="Number">1</ss:Data></ss:Cell>
        <ss:Cell><ss:Data ss:Type="String">--</ss:Data></ss:Cell>
      </ss:Row>
    </ss:Table>
  </ss:Worksheet>
</ss:Workbook>
"""


class ETFHoldingsReaderTests(unittest.TestCase):
    def _reader(self) -> ETFHoldingsReader:
        responses = {
            MTUM_URL: MTUM_HTML,
            MTUM_DOWNLOAD_URL: MTUM_WORKBOOK,
        }
        return ETFHoldingsReader(fetcher=responses.__getitem__)

    def test_reads_mtum_url_and_returns_fund_payload(self) -> None:
        fund = self._reader().read(MTUM_URL)

        self.assertIsInstance(fund, FundHoldings)
        self.assertEqual(fund.url, MTUM_URL)
        self.assertEqual(fund.download_url, MTUM_DOWNLOAD_URL)
        self.assertEqual(fund.fund_name, "iShares MSCI USA Momentum Factor ETF")
        self.assertEqual(fund.as_of_date, "Apr 27, 2026")
        self.assertEqual(len(fund.holdings), 3)
        self.assertIsInstance(fund.holdings[0], Holding)
        self.assertEqual(fund.holdings[0].ticker, "MU")

    def test_extract_ticker_weights_from_mtum_url(self) -> None:
        weights = extract_ticker_weights(MTUM_URL, fetcher=self._reader().fetcher)

        self.assertEqual(
            weights,
            {
                "AVGO": 5.4749,
                "MU": 5.71228,
                "NVDA": 5.09816,
            },
        )

    def test_cli_prints_json_weights_for_mtum_url(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main([MTUM_URL], reader=self._reader())

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["MU"], 5.71228)
        self.assertEqual(payload["AVGO"], 5.4749)


if __name__ == "__main__":
    unittest.main()
