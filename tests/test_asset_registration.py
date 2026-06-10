from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pandas as pd

from etfhextractor.asset_registration import register_equity_assets_from_tickers

AAPL_FIGI = "BBG000B9XRY4"
MSFT_FIGI_1 = "BBG000BPH459"
MSFT_FIGI_2 = "BBG000BPH460"


def figi_row(ticker: str, figi: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "unique_identifier": figi,
        "figi": figi,
        "composite": None,
        "share_class": None,
        "isin": None,
        "ticker": ticker,
        "name": f"{ticker} Inc.",
        "exchange_code": "US",
        "security_type": "Common Stock",
        "security_type_2": "Common Stock",
        "security_market_sector": "Equity",
        "security_description": ticker,
        "unique_id": None,
        "unique_id_fut_opt": None,
        "metadata": None,
        "raw_payload": {"figi": figi, "ticker": ticker},
    }
    row.update(overrides)
    return row


def run_registration(
    *,
    tickers: list[str],
    figi_rows: list[dict[str, Any]] | Any,
    disambiguation_filters: list[dict[str, Any]] | None = None,
    existing_figis: dict[str, Any] | None = None,
    figis_with_snapshots: set[str] | None = None,
) -> tuple[Any, dict[str, Mock]]:
    asset_cls = Mock()
    asset_cls.upsert.side_effect = lambda **kwargs: SimpleNamespace(
        uid=uuid.uuid4(), unique_identifier=kwargs["unique_identifier"]
    )
    asset_type_cls = Mock()
    details_cls = Mock()
    snapshot_cls = Mock()
    snapshot_node = snapshot_cls.return_value
    snapshot_node.set_frame.return_value = snapshot_node
    snapshot_node.run.return_value = (False, pd.DataFrame())

    query_figi_mock = (
        Mock(return_value=figi_rows) if isinstance(figi_rows, list) else Mock(side_effect=figi_rows)
    )

    with patch(
        "etfhextractor.asset_registration._ensure_msm_started",
        return_value=SimpleNamespace(context=object()),
    ), patch(
        "etfhextractor.asset_registration._existing_asset_uids_by_figi",
        return_value=dict(existing_figis or {}),
    ), patch(
        "etfhextractor.asset_registration._figis_with_snapshots",
        return_value=set(figis_with_snapshots or set()),
    ), patch("msm.services.assets.openfigi.query_figi", query_figi_mock), patch(
        "msm.services.assets.openfigi.build_asset_snapshot_frame_from_openfigi_result",
        side_effect=lambda normalized, *, time_index: pd.DataFrame(
            [{"asset_identifier": normalized["unique_identifier"]}]
        ),
    ), patch("msm.api.assets.Asset", asset_cls), patch(
        "msm.api.assets.AssetType", asset_type_cls
    ), patch("msm.api.assets.OpenFigiDetails", details_cls), patch(
        "msm.data_nodes.assets.AssetSnapshot", snapshot_cls
    ):
        result = register_equity_assets_from_tickers(
            tickers=tickers,
            disambiguation_filters=disambiguation_filters,
        )

    mocks = {
        "Asset": asset_cls,
        "AssetType": asset_type_cls,
        "OpenFigiDetails": details_cls,
        "AssetSnapshot": snapshot_cls,
        "snapshot_node": snapshot_node,
        "query_figi": query_figi_mock,
    }
    return result, mocks


class FigiAssetRegistrationTests(unittest.TestCase):
    def test_unique_mapping_registers_figi_keyed_asset(self) -> None:
        result, mocks = run_registration(
            tickers=["AAPL"],
            figi_rows=[figi_row("AAPL", AAPL_FIGI)],
        )

        self.assertEqual(result.registered_figi_by_ticker, {"AAPL": AAPL_FIGI})
        self.assertEqual(result.unmapped_tickers, [])
        self.assertEqual(result.ambiguous_figi_candidates_by_ticker, {})
        self.assertFalse(result.has_failures())

        # Asset identity is the FIGI, never the ticker.
        asset_kwargs = mocks["Asset"].upsert.call_args.kwargs
        self.assertEqual(asset_kwargs["unique_identifier"], AAPL_FIGI)
        self.assertEqual(asset_kwargs["asset_type"], "equity")

        details_kwargs = mocks["OpenFigiDetails"].upsert.call_args.kwargs
        self.assertEqual(details_kwargs["figi"], AAPL_FIGI)
        self.assertEqual(details_kwargs["ticker"], "AAPL")
        self.assertIn("asset_uid", details_kwargs)

        mocks["snapshot_node"].run.assert_called_once()

    def test_no_figi_means_no_registration(self) -> None:
        result, mocks = run_registration(tickers=["NVDA"], figi_rows=[])

        self.assertEqual(result.registered_figi_by_ticker, {})
        self.assertEqual(result.unmapped_tickers, ["NVDA"])
        self.assertTrue(result.has_failures())
        mocks["Asset"].upsert.assert_not_called()
        mocks["OpenFigiDetails"].upsert.assert_not_called()
        mocks["AssetSnapshot"].assert_not_called()

    def test_multiple_figis_for_one_ticker_block_registration(self) -> None:
        result, mocks = run_registration(
            tickers=["MSFT"],
            figi_rows=[
                figi_row("MSFT", MSFT_FIGI_1),
                figi_row("MSFT", MSFT_FIGI_2),
            ],
        )

        self.assertEqual(result.registered_figi_by_ticker, {})
        self.assertEqual(
            result.ambiguous_figi_candidates_by_ticker,
            {"MSFT": [MSFT_FIGI_1, MSFT_FIGI_2]},
        )
        self.assertTrue(result.has_failures())
        mocks["Asset"].upsert.assert_not_called()
        mocks["AssetSnapshot"].assert_not_called()

    def test_duplicate_rows_with_same_figi_count_as_unique(self) -> None:
        result, mocks = run_registration(
            tickers=["AAPL"],
            figi_rows=[
                figi_row("AAPL", AAPL_FIGI),
                figi_row("AAPL", AAPL_FIGI, exchange_code="UN"),
            ],
        )

        self.assertEqual(result.registered_figi_by_ticker, {"AAPL": AAPL_FIGI})
        self.assertFalse(result.has_failures())
        self.assertEqual(mocks["Asset"].upsert.call_count, 1)

    def test_mixed_batch_registers_only_unique_mappings(self) -> None:
        result, mocks = run_registration(
            tickers=["AAPL", "MSFT", "NVDA"],
            figi_rows=[
                figi_row("AAPL", AAPL_FIGI),
                figi_row("MSFT", MSFT_FIGI_1),
                figi_row("MSFT", MSFT_FIGI_2),
            ],
        )

        self.assertEqual(result.registered_figi_by_ticker, {"AAPL": AAPL_FIGI})
        self.assertEqual(result.unmapped_tickers, ["NVDA"])
        self.assertEqual(
            result.ambiguous_figi_candidates_by_ticker,
            {"MSFT": [MSFT_FIGI_1, MSFT_FIGI_2]},
        )
        self.assertEqual(mocks["Asset"].upsert.call_count, 1)

    def test_empty_ticker_list_is_a_no_op(self) -> None:
        result = register_equity_assets_from_tickers(tickers=[])
        self.assertEqual(result.registered_figi_by_ticker, {})
        self.assertFalse(result.has_failures())

    def test_already_registered_assets_cost_zero_writes(self) -> None:
        result, mocks = run_registration(
            tickers=["AAPL"],
            figi_rows=[figi_row("AAPL", AAPL_FIGI)],
            existing_figis={AAPL_FIGI: uuid.uuid4()},
            figis_with_snapshots={AAPL_FIGI},
        )

        self.assertEqual(result.registered_figi_by_ticker, {})
        self.assertEqual(result.already_registered_figi_by_ticker, {"AAPL": AAPL_FIGI})
        self.assertEqual(result.snapshots_published_for_figis, [])
        self.assertFalse(result.has_failures())
        # The whole re-run is read-only: no asset writes, no snapshot run.
        mocks["Asset"].upsert.assert_not_called()
        mocks["OpenFigiDetails"].upsert.assert_not_called()
        mocks["AssetSnapshot"].assert_not_called()

    def test_existing_asset_without_snapshot_gets_snapshot_repair_only(self) -> None:
        result, mocks = run_registration(
            tickers=["AAPL"],
            figi_rows=[figi_row("AAPL", AAPL_FIGI)],
            existing_figis={AAPL_FIGI: uuid.uuid4()},
            figis_with_snapshots=set(),
        )

        # Asset exists (e.g. an interrupted earlier registration) — only the
        # snapshot is published so the ticker becomes resolvable.
        self.assertEqual(result.registered_figi_by_ticker, {})
        self.assertEqual(result.already_registered_figi_by_ticker, {"AAPL": AAPL_FIGI})
        self.assertEqual(result.snapshots_published_for_figis, [AAPL_FIGI])
        mocks["Asset"].upsert.assert_not_called()
        mocks["snapshot_node"].run.assert_called_once()

    def test_mixed_existing_and_new_assets_write_only_the_delta(self) -> None:
        result, mocks = run_registration(
            tickers=["AAPL", "NVDA"],
            figi_rows=[
                figi_row("AAPL", AAPL_FIGI),
                figi_row("NVDA", "BBG000NVDA01"),
            ],
            existing_figis={AAPL_FIGI: uuid.uuid4()},
            figis_with_snapshots={AAPL_FIGI},
        )

        self.assertEqual(result.registered_figi_by_ticker, {"NVDA": "BBG000NVDA01"})
        self.assertEqual(result.already_registered_figi_by_ticker, {"AAPL": AAPL_FIGI})
        self.assertEqual(result.snapshots_published_for_figis, ["BBG000NVDA01"])
        self.assertEqual(mocks["Asset"].upsert.call_count, 1)
        self.assertEqual(
            mocks["Asset"].upsert.call_args.kwargs["unique_identifier"],
            "BBG000NVDA01",
        )

    def test_failure_message_names_ambiguous_tickers_and_candidates(self) -> None:
        result, _mocks = run_registration(
            tickers=["MSFT", "NVDA"],
            figi_rows=[
                figi_row("MSFT", MSFT_FIGI_1),
                figi_row("MSFT", MSFT_FIGI_2),
            ],
        )

        message = result.format_failures()
        self.assertIsNotNone(message)
        self.assertIn("MSFT", message)
        self.assertIn(MSFT_FIGI_1, message)
        self.assertIn(MSFT_FIGI_2, message)
        self.assertIn("NVDA", message)
        # The message teaches the fix: a per-ticker disambiguation filter.
        self.assertIn('{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}', message)

    def test_disambiguation_filter_routes_ticker_through_its_own_query(self) -> None:
        def fake_query_figi(tickers, *, market_sector, exch_code=None, security_type=None, **_):
            if "USO" in tickers:
                assert market_sector == "Equity"
                assert exch_code == "UP"
                assert security_type == "ETP"
                return [figi_row("USO", "BBG000QWM6Y9")]
            return [figi_row("AAPL", AAPL_FIGI)]

        result, mocks = run_registration(
            tickers=["AAPL", "USO"],
            figi_rows=fake_query_figi,
            disambiguation_filters=[
                {"ticker": "USO", "market_sector": "Equity", "exch_code": "UP", "security_type": "ETP"},
            ],
        )

        self.assertEqual(
            result.registered_figi_by_ticker,
            {"AAPL": AAPL_FIGI, "USO": "BBG000QWM6Y9"},
        )
        self.assertFalse(result.has_failures())
        # Two query groups: the defaults batch and the USO override batch.
        self.assertEqual(mocks["query_figi"].call_count, 2)

    def test_disambiguation_filter_requires_ticker_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "'ticker' key"):
            register_equity_assets_from_tickers(
                tickers=["USO"],
                disambiguation_filters=[{"market_sector": "Equity"}],
            )

    def test_disambiguation_filter_rejects_unknown_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown disambiguation filter keys"):
            register_equity_assets_from_tickers(
                tickers=["USO"],
                disambiguation_filters=[{"ticker": "USO", "exchange": "US"}],
            )


if __name__ == "__main__":
    unittest.main()
