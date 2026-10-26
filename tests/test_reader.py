from __future__ import annotations

import io
import json
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from etfhextractor import ETFHoldingsReader, extract_ticker_weights
from etfhextractor.__main__ import main
from etfhextractor._version import DEFAULT_USER_AGENT
from etfhextractor.artifacts import ArtifactPayload, persist_extraction_artifacts
from etfhextractor.exceptions import UnsupportedProviderError
from etfhextractor.mainsequence_categories import (
    build_holdings_asset_category_plan,
    build_holdings_asset_category_unique_identifier,
    derive_component_symbols_from_holdings,
    derive_component_weights_from_holdings,
    infer_holdings_component_provider,
    resolve_asset_identifiers_by_ticker,
    resolve_existing_assets_by_ticker,
    sync_holdings_asset_category,
)
from etfhextractor.models import FundHoldings, Holding

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
            "etfhextractor.reader.build_provider_from_url",
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
            user_agent=DEFAULT_USER_AGENT,
        )
        provider.read_url.assert_called_once_with(IVV_URL)

    def test_extract_ticker_weights_from_url(self) -> None:
        provider = Mock()
        provider.read_url.return_value = build_sample_fund_holdings()

        with patch(
            "etfhextractor.reader.build_provider_from_url",
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
            "etfhextractor.reader.build_provider",
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
            user_agent=DEFAULT_USER_AGENT,
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

    def test_cli_category_sync_subcommand_chains_plan_and_sync(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read.return_value = build_sample_fund_holdings()

        aapl_uid = uuid.uuid4()
        msft_uid = uuid.uuid4()

        with patch("etfhextractor.cli.build_holdings_asset_category_plan") as build_plan_mock, patch(
            "etfhextractor.cli.sync_holdings_asset_category"
        ) as sync_category_mock, redirect_stdout(buffer):
            plan = Mock()
            plan.summary.return_value = {
                "category_unique_identifier": "HOLDINGS__IVV",
                "component_symbols": ["AAPL", "MSFT"],
            }
            plan.has_blockers.return_value = False
            plan.existing_asset_uids_by_symbol = {"AAPL": aapl_uid, "MSFT": msft_uid}
            build_plan_mock.return_value = plan

            sync_result = Mock()
            sync_result.unique_identifier = "HOLDINGS__IVV"
            sync_result.display_name = "HOLDINGS__IVV"
            sync_result.asset_uids = [aapl_uid, msft_uid]
            sync_category_mock.return_value = sync_result

            exit_code = main(
                ["category-sync", "--ticker", "IVV", "--fund-url", IVV_URL],
                reader=reader,
            )

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["synced"])
        # UUIDs are serialized as strings via json.dumps(default=str).
        self.assertEqual(
            payload["sync_result"]["asset_uids"],
            [str(aapl_uid), str(msft_uid)],
        )
        sync_category_mock.assert_called_once_with(
            etf_ticker="IVV",
            asset_uids=[aapl_uid, msft_uid],
        )

    def test_cli_category_sync_subcommand_returns_blockers_without_syncing(self) -> None:
        buffer = io.StringIO()
        reader = Mock()
        reader.read.return_value = build_sample_fund_holdings()

        with patch("etfhextractor.cli.build_holdings_asset_category_plan") as build_plan_mock, patch(
            "etfhextractor.cli.sync_holdings_asset_category"
        ) as sync_category_mock, redirect_stdout(buffer):
            plan = Mock()
            plan.summary.return_value = {
                "category_unique_identifier": "HOLDINGS__IVV",
                "missing_registered_symbols": ["NVDA"],
            }
            plan.has_blockers.return_value = True
            plan.existing_asset_uids_by_symbol = {"AAPL": uuid.uuid4(), "MSFT": uuid.uuid4()}
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

    def test_derive_component_weights_accumulates_with_same_filter(self) -> None:
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

        weights = derive_component_weights_from_holdings(fund_holdings)

        self.assertEqual(weights, {"AAPL": 7.3, "MSFT": 6.5})
        # The symbols view and the weights view share one filter.
        self.assertEqual(
            sorted(weights),
            derive_component_symbols_from_holdings(fund_holdings),
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
        aapl_uid = uuid.uuid4()
        msft_uid = uuid.uuid4()

        def read_holdings_fn(ticker: str, *, provider: str | None = None) -> FundHoldings:
            captured["ticker"] = ticker
            captured["provider"] = provider
            return fund_holdings

        def resolve_existing_assets_by_ticker_fn(*, component_symbols):
            captured["component_symbols"] = component_symbols
            return {"AAPL": aapl_uid, "MSFT": msft_uid}, [], []

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
        self.assertEqual(plan.existing_asset_uids_by_symbol, {"AAPL": aapl_uid, "MSFT": msft_uid})
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
                {"AAPL": uuid.uuid4(), "MSFT": uuid.uuid4()},
                [],
                [],
            ),
        )

        self.assertEqual(captured["identifier"], IVV_URL)
        self.assertEqual(captured["provider"], "ishares")
        self.assertEqual(plan.provider, "ishares")


class MsmBoundaryTests(unittest.TestCase):
    """Cover the ms-markets boundary in mainsequence_categories with msm mocked.

    `_ensure_msm_started` is replaced so no real markets runtime is started, and
    the lazily-imported msm calls are patched at their source modules (the lazy
    `from msm... import ...` re-reads the patched attribute at call time). Ticker
    resolution is one `AssetSnapshots.latest(tickers=...)` row call that returns
    each asset that ever carried a ticker with its LATEST snapshot.
    """

    @staticmethod
    def _references() -> list[SimpleNamespace]:
        def reference(identifier: str, ticker: str | None) -> SimpleNamespace:
            return SimpleNamespace(
                asset_uid=uuid.uuid4(),
                asset_identifier=identifier,
                ticker=ticker,
                snapshot_time=None if ticker is None else "2026-05-01T00:00:00Z",
            )

        return [
            reference("AAPL_ID", "AAPL"),
            reference("MSFT_ID_1", "MSFT"),
            reference("MSFT_ID_2", "MSFT"),
            # Carried GOOG once; its latest snapshot moved to another ticker.
            reference("OLD_GOOG_ID", "GOOGL_OLD"),
        ]

    def _resolve(self, resolver):
        references = self._references()
        with patch(
            "etfhextractor.mainsequence_categories._ensure_msm_started",
            return_value=SimpleNamespace(context=object()),
        ), patch(
            "msm.repositories.crud.search_model",
            side_effect=AssertionError("compiled SQL on a Markets table"),
        ), patch(
            "msm.api.assets.AssetSnapshots.latest", return_value=references
        ) as latest:
            result = resolver(component_symbols=["AAPL", "MSFT", "NVDA", "GOOG"])
        latest.assert_called_once_with(tickers=["AAPL", "MSFT", "NVDA", "GOOG"])
        return result, references

    def test_resolve_existing_assets_by_ticker_classifies_zero_one_many(self) -> None:
        (existing, missing, ambiguous), references = self._resolve(
            resolve_existing_assets_by_ticker
        )

        # The uid comes with the snapshot reference: no second lookup per asset.
        self.assertEqual(existing, {"AAPL": references[0].asset_uid})
        self.assertEqual(missing, ["GOOG", "NVDA"])
        self.assertEqual(ambiguous, ["MSFT"])

    def test_resolve_asset_identifiers_by_ticker_returns_unique_identifiers(self) -> None:
        (existing, missing, ambiguous), _references = self._resolve(
            resolve_asset_identifiers_by_ticker
        )

        self.assertEqual(existing, {"AAPL": "AAPL_ID"})
        self.assertEqual(missing, ["GOOG", "NVDA"])
        self.assertEqual(ambiguous, ["MSFT"])

    def test_sync_holdings_asset_category_upserts_then_replaces(self) -> None:
        category_uid = uuid.uuid4()
        aapl_uid = uuid.uuid4()
        msft_uid = uuid.uuid4()

        category = SimpleNamespace(
            uid=category_uid,
            unique_identifier="HOLDINGS__IVV",
            display_name="HOLDINGS__IVV",
        )
        memberships = [
            SimpleNamespace(asset_uid=aapl_uid),
            SimpleNamespace(asset_uid=msft_uid),
        ]
        asset_category_cls = Mock()
        asset_category_cls.upsert.return_value = category
        asset_category_cls.replace_memberships.return_value = memberships

        with patch(
            "etfhextractor.mainsequence_categories._ensure_msm_started",
            return_value=SimpleNamespace(context=object()),
        ), patch("msm.api.assets.AssetCategory", asset_category_cls):
            result = sync_holdings_asset_category(
                etf_ticker="ivv",
                # duplicate uid to confirm de-duplication while preserving order
                asset_uids=[aapl_uid, msft_uid, aapl_uid],
            )

        asset_category_cls.upsert.assert_called_once_with(
            unique_identifier="HOLDINGS__IVV",
            display_name="HOLDINGS__IVV",
            description="Published holdings assets for ETF IVV.",
        )
        replace_kwargs = asset_category_cls.replace_memberships.call_args.kwargs
        self.assertEqual(replace_kwargs["category_uid"], category_uid)
        self.assertEqual(replace_kwargs["asset_uids"], [aapl_uid, msft_uid])
        self.assertEqual(result.unique_identifier, "HOLDINGS__IVV")
        self.assertEqual(result.asset_uids, [aapl_uid, msft_uid])


if __name__ == "__main__":
    unittest.main()
