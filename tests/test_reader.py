from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from etfh_extractor import ETFHoldingsReader, extract_ticker_weights
from etfh_extractor.__main__ import main
from etfh_extractor.artifacts import ArtifactPayload, persist_extraction_artifacts
from etfh_extractor.exceptions import UnsupportedProviderError
from etfh_extractor.mainsequence_categories import (
    build_holdings_asset_category_plan,
    build_holdings_asset_category_unique_identifier,
    derive_component_symbols_from_holdings,
    infer_holdings_component_provider,
)
from etfh_extractor.models import FundHoldings, Holding

IVV_URL = "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf"
SAMPLE_DOWNLOAD_URL = "https://example.com/holdings_export.xls"


def build_sample_fund_holdings(*, url: str = IVV_URL) -> FundHoldings:
    return FundHoldings(
        url=url,
        download_url=SAMPLE_DOWNLOAD_URL,
        fund_name="iShares Core S&P 500 ETF",
        as_of_date="Apr 27, 2026",
        holdings=(
            Holding(ticker="AAPL", name="Apple Inc.", weight=7.0, asset_class="Equity"),
            Holding(ticker="MSFT", name="Microsoft Corp.", weight=6.5, asset_class="Equity"),
            Holding(ticker="NVDA", name="NVIDIA Corp.", weight=5.1, asset_class="Equity"),
        ),
    )


class ETFHoldingsReaderTests(unittest.TestCase):
    def test_read_delegates_to_provider_resolved_from_url(self) -> None:
        fund_holdings = build_sample_fund_holdings()
        provider = Mock()
        provider.read_url.return_value = fund_holdings

        with patch(
            "etfh_extractor.reader.build_provider_from_url",
            return_value=provider,
        ) as build_provider_from_url_mock:
            result = ETFHoldingsReader().read(IVV_URL)

        self.assertIs(result, fund_holdings)
        build_provider_from_url_mock.assert_called_once_with(
            IVV_URL,
            timeout=30.0,
            fetcher=None,
            binary_fetcher=None,
            artifact_root=None,
            user_agent="etfh-extractor/0.1.0",
        )
        provider.read_url.assert_called_once_with(IVV_URL)

    def test_extract_ticker_weights_from_url(self) -> None:
        provider = Mock()
        provider.read_url.return_value = build_sample_fund_holdings()

        with patch(
            "etfh_extractor.reader.build_provider_from_url",
            return_value=provider,
        ):
            weights = extract_ticker_weights(IVV_URL)

        self.assertEqual(
            weights,
            {
                "AAPL": 7.0,
                "MSFT": 6.5,
                "NVDA": 5.1,
            },
        )

    def test_cli_prints_json_weights_for_url(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read.return_value = build_sample_fund_holdings()

        with redirect_stdout(buffer):
            exit_code = main([IVV_URL], reader=reader)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["AAPL"], 7.0)
        self.assertEqual(payload["MSFT"], 6.5)

    def test_read_ticker_requires_provider(self) -> None:
        with self.assertRaisesRegex(
            UnsupportedProviderError,
            "Ticker-only extraction requires an explicit provider",
        ):
            ETFHoldingsReader().read_ticker("IVV")

    def test_read_ticker_delegates_to_explicit_provider(self) -> None:
        fund_holdings = build_sample_fund_holdings()
        provider = Mock()
        provider.read_ticker.return_value = fund_holdings

        with patch(
            "etfh_extractor.reader.build_provider",
            return_value=provider,
        ) as build_provider_mock:
            result = ETFHoldingsReader().read_ticker("IVV", provider="ishares")

        self.assertIs(result, fund_holdings)
        build_provider_mock.assert_called_once_with(
            "ishares",
            timeout=30.0,
            fetcher=None,
            binary_fetcher=None,
            artifact_root=None,
            user_agent="etfh-extractor/0.1.0",
        )
        provider.read_ticker.assert_called_once_with("IVV")

    def test_cli_supports_ticker_input(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read_ticker.return_value = build_sample_fund_holdings()

        with redirect_stdout(buffer):
            exit_code = main(["--provider", "ishares", "--ticker", "IVV"], reader=reader)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["AAPL"], 7.0)

    def test_cli_extract_url_subcommand_prints_weights(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read.return_value = build_sample_fund_holdings()

        with redirect_stdout(buffer):
            exit_code = main(["extract-url", IVV_URL], reader=reader)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["AAPL"], 7.0)
        self.assertEqual(payload["MSFT"], 6.5)

    def test_cli_extract_ticker_subcommand_prints_weights(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read_ticker.return_value = build_sample_fund_holdings()

        with redirect_stdout(buffer):
            exit_code = main(
                ["extract-ticker", "--provider", "ishares", "--ticker", "IVV"],
                reader=reader,
            )

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["AAPL"], 7.0)

    def test_cli_category_plan_subcommand_returns_plan_summary(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read.return_value = build_sample_fund_holdings()

        with patch(
            "etfh_extractor.__main__.build_holdings_asset_category_plan"
        ) as build_plan_mock, redirect_stdout(buffer):
            plan = Mock()
            plan.summary.return_value = {
                "category_unique_identifier": "HOLDINGS__IVV",
                "component_symbols": ["AAPL", "MSFT"],
            }
            plan.has_blockers.return_value = False
            build_plan_mock.return_value = plan

            exit_code = main(
                ["category-plan", "--ticker", "IVV", "--fund-url", IVV_URL],
                reader=reader,
            )

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["category_unique_identifier"], "HOLDINGS__IVV")
        self.assertFalse(payload["has_blockers"])

    def test_cli_category_sync_subcommand_chains_plan_and_sync(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read.return_value = build_sample_fund_holdings()

        with patch(
            "etfh_extractor.__main__.build_holdings_asset_category_plan"
        ) as build_plan_mock, patch(
            "etfh_extractor.__main__.sync_holdings_asset_category"
        ) as sync_category_mock, redirect_stdout(buffer):
            plan = Mock()
            plan.summary.return_value = {
                "category_unique_identifier": "HOLDINGS__IVV",
                "component_symbols": ["AAPL", "MSFT"],
            }
            plan.has_blockers.return_value = False
            plan.existing_asset_ids_by_symbol = {"AAPL": 101, "MSFT": 102}
            build_plan_mock.return_value = plan

            sync_result = Mock()
            sync_result.unique_identifier = "HOLDINGS__IVV"
            sync_result.display_name = "HOLDINGS__IVV"
            sync_result.asset_ids = [101, 102]
            sync_category_mock.return_value = sync_result

            exit_code = main(
                ["category-sync", "--ticker", "IVV", "--fund-url", IVV_URL],
                reader=reader,
            )

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["synced"])
        self.assertEqual(payload["sync_result"]["asset_ids"], [101, 102])

    def test_cli_category_sync_subcommand_returns_blockers_without_syncing(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read.return_value = build_sample_fund_holdings()

        with patch(
            "etfh_extractor.__main__.build_holdings_asset_category_plan"
        ) as build_plan_mock, patch(
            "etfh_extractor.__main__.sync_holdings_asset_category"
        ) as sync_category_mock, redirect_stdout(buffer):
            plan = Mock()
            plan.summary.return_value = {
                "category_unique_identifier": "HOLDINGS__IVV",
                "missing_registered_symbols": ["NVDA"],
            }
            plan.has_blockers.return_value = True
            plan.existing_asset_ids_by_symbol = {"AAPL": 101, "MSFT": 102}
            build_plan_mock.return_value = plan

            exit_code = main(
                ["category-sync", "--ticker", "IVV", "--fund-url", IVV_URL],
                reader=reader,
            )

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["synced"])
        self.assertIsNone(payload["sync_result"])
        sync_category_mock.assert_not_called()

    def test_persists_debug_artifacts_under_temp_directory(self) -> None:
        with TemporaryDirectory() as tempdir:
            persisted_fund_holdings = persist_extraction_artifacts(
                provider_name="ishares",
                fund_holdings=build_sample_fund_holdings(),
                source_artifacts=[
                    ArtifactPayload("fund_page.html", "<html></html>"),
                    ArtifactPayload("holdings_export.xls", b"placeholder"),
                ],
                requested_ticker="IVV",
                artifact_root=Path(tempdir),
            )

            self.assertIsNotNone(persisted_fund_holdings.artifact_directory)
            artifact_dir = Path(persisted_fund_holdings.artifact_directory or "")
            self.assertTrue(artifact_dir.exists())
            self.assertTrue((artifact_dir / "fund_page.html").exists())
            self.assertTrue((artifact_dir / "holdings_export.xls").exists())
            self.assertTrue((artifact_dir / "holdings.csv").exists())
            self.assertTrue((artifact_dir / "weights.json").exists())
            self.assertTrue((artifact_dir / "fund_holdings.json").exists())
            self.assertTrue((artifact_dir / "metadata.json").exists())


class HoldingsCategoryTests(unittest.TestCase):
    def test_build_holdings_asset_category_unique_identifier(self) -> None:
        self.assertEqual(build_holdings_asset_category_unique_identifier("ivv"), "HOLDINGS__IVV")

    def test_infer_holdings_component_provider(self) -> None:
        self.assertEqual(infer_holdings_component_provider(IVV_URL), "ishares")

    def test_derive_component_symbols_from_holdings_filters_to_probable_equities(self) -> None:
        fund_holdings = FundHoldings(
            url=IVV_URL,
            download_url=SAMPLE_DOWNLOAD_URL,
            fund_name="iShares Core S&P 500 ETF",
            as_of_date="Apr 27, 2026",
            holdings=(
                Holding(ticker="msft", name="Microsoft Corp.", weight=6.5, asset_class="Equity"),
                Holding(ticker="AAPL", name="Apple Inc.", weight=7.0, asset_class="Equity"),
                Holding(ticker="USD", name="USD CASH", weight=0.1, asset_class="Cash"),
                Holding(ticker="AAPL", name="Apple Inc.", weight=0.3, asset_class="Equity"),
            ),
        )

        self.assertEqual(
            derive_component_symbols_from_holdings(fund_holdings),
            ["AAPL", "MSFT"],
        )

    def test_build_holdings_asset_category_plan_uses_holdings_model(self) -> None:
        fund_holdings = FundHoldings(
            url=IVV_URL,
            download_url=SAMPLE_DOWNLOAD_URL,
            fund_name="iShares Core S&P 500 ETF",
            as_of_date="Apr 27, 2026",
            holdings=(
                Holding(ticker="AAPL", name="Apple Inc.", weight=7.0, asset_class="Equity"),
                Holding(ticker="MSFT", name="Microsoft Corp.", weight=6.5, asset_class="Equity"),
                Holding(ticker="USD", name="USD CASH", weight=0.1, asset_class="Cash"),
            ),
        )
        captured: dict[str, object] = {}

        def read_holdings_fn(ticker: str, *, provider: str | None = None) -> FundHoldings:
            captured["ticker"] = ticker
            captured["provider"] = provider
            return fund_holdings

        def resolve_existing_assets_by_ticker_fn(*, component_symbols):
            captured["component_symbols"] = component_symbols
            return {"AAPL": 1, "MSFT": 2}, [], []

        plan = build_holdings_asset_category_plan(
            etf_ticker="IVV",
            component_provider="ishares",
            read_holdings_fn=read_holdings_fn,
            resolve_existing_assets_by_ticker_fn=resolve_existing_assets_by_ticker_fn,
        )

        self.assertEqual(captured["ticker"], "IVV")
        self.assertEqual(captured["provider"], "ishares")
        self.assertEqual(captured["component_symbols"], ["AAPL", "MSFT"])
        self.assertEqual(plan.component_symbols, ["AAPL", "MSFT"])
        self.assertEqual(plan.existing_asset_ids_by_symbol, {"AAPL": 1, "MSFT": 2})
        self.assertEqual(plan.category_unique_identifier, "HOLDINGS__IVV")

    def test_build_holdings_asset_category_plan_infers_provider_from_url(self) -> None:
        fund_holdings = FundHoldings(
            url=IVV_URL,
            download_url=SAMPLE_DOWNLOAD_URL,
            fund_name="iShares Core S&P 500 ETF",
            as_of_date="Apr 27, 2026",
            holdings=(
                Holding(ticker="AAPL", name="Apple Inc.", weight=7.0, asset_class="Equity"),
                Holding(ticker="MSFT", name="Microsoft Corp.", weight=6.5, asset_class="Equity"),
            ),
        )
        captured: dict[str, object] = {}

        def read_holdings_fn(identifier: str, *, provider: str | None = None) -> FundHoldings:
            captured["identifier"] = identifier
            captured["provider"] = provider
            return fund_holdings

        plan = build_holdings_asset_category_plan(
            etf_ticker="IVV",
            fund_url=IVV_URL,
            read_holdings_fn=read_holdings_fn,
            resolve_existing_assets_by_ticker_fn=lambda *, component_symbols: (
                {"AAPL": 1, "MSFT": 2},
                [],
                [],
            ),
        )

        self.assertEqual(captured["identifier"], IVV_URL)
        self.assertEqual(captured["provider"], "ishares")
        self.assertEqual(plan.provider, "ishares")


if __name__ == "__main__":
    unittest.main()
