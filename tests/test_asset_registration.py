from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

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


def _upserted_assets(payloads: list[dict[str, Any]]) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(uid=uuid.uuid4(), unique_identifier=payload["unique_identifier"])
        for payload in payloads
    ]


def run_registration(
    *,
    tickers: list[str],
    figi_rows: list[dict[str, Any]] | Any,
    disambiguation_filters: list[dict[str, Any]] | None = None,
    existing_figis: dict[str, Any] | None = None,
    figis_with_snapshots: set[str] | None = None,
) -> tuple[Any, dict[str, Mock]]:
    asset_cls = Mock()
    asset_cls.upsert_many.side_effect = _upserted_assets
    asset_type_cls = Mock()
    details_cls = Mock()
    snapshots_cls = Mock()
    snapshots_cls.publish.side_effect = len

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
        "msm.api.assets.Asset", asset_cls
    ), patch("msm.api.assets.AssetType", asset_type_cls), patch(
        "msm.api.assets.OpenFigiDetails", details_cls
    ), patch("msm.api.assets.AssetSnapshots", snapshots_cls):
        result = register_equity_assets_from_tickers(
            tickers=tickers,
            disambiguation_filters=disambiguation_filters,
        )

    mocks = {
        "Asset": asset_cls,
        "AssetType": asset_type_cls,
        "OpenFigiDetails": details_cls,
        "AssetSnapshots": snapshots_cls,
        "query_figi": query_figi_mock,
    }
    return result, mocks


def upserted(mock: Mock) -> list[dict[str, Any]]:
    """Every payload passed to `upsert_many` on a mocked row class."""
    return [payload for call in mock.upsert_many.call_args_list for payload in call.args[0]]


def published(mock: Mock) -> list[dict[str, Any]]:
    """Every row passed to a mocked `AssetSnapshots.publish`."""
    return [row for call in mock.publish.call_args_list for row in call.args[0]]


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

        # Asset identity is the FIGI, never the ticker; one set-based write per table.
        mocks["Asset"].upsert.assert_not_called()
        mocks["Asset"].upsert_many.assert_called_once()
        self.assertEqual(
            upserted(mocks["Asset"]), [{"unique_identifier": AAPL_FIGI, "asset_type": "equity"}]
        )

        mocks["OpenFigiDetails"].upsert.assert_not_called()
        (details,) = upserted(mocks["OpenFigiDetails"])
        self.assertEqual(details["figi"], AAPL_FIGI)
        self.assertEqual(details["ticker"], "AAPL")
        self.assertIsNotNone(details["asset_uid"])

        # Snapshots are published through the Markets publication composite.
        mocks["AssetSnapshots"].publish.assert_called_once()
        (snapshot,) = published(mocks["AssetSnapshots"])
        self.assertEqual(snapshot["asset_identifier"], AAPL_FIGI)
        self.assertEqual(snapshot["ticker"], "AAPL")

    def test_no_figi_means_no_registration(self) -> None:
        result, mocks = run_registration(tickers=["NVDA"], figi_rows=[])

        self.assertEqual(result.registered_figi_by_ticker, {})
        self.assertEqual(result.unmapped_tickers, ["NVDA"])
        self.assertTrue(result.has_failures())
        mocks["Asset"].upsert_many.assert_not_called()
        mocks["OpenFigiDetails"].upsert_many.assert_not_called()
        mocks["AssetSnapshots"].publish.assert_not_called()

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
        mocks["Asset"].upsert_many.assert_not_called()
        mocks["AssetSnapshots"].publish.assert_not_called()

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
        self.assertEqual(len(upserted(mocks["Asset"])), 1)

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
        self.assertEqual(len(upserted(mocks["Asset"])), 1)

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
        # The whole re-run is read-only: no asset writes, no snapshot publication.
        mocks["AssetType"].upsert.assert_not_called()
        mocks["Asset"].upsert_many.assert_not_called()
        mocks["OpenFigiDetails"].upsert_many.assert_not_called()
        mocks["AssetSnapshots"].publish.assert_not_called()

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
        mocks["Asset"].upsert_many.assert_not_called()
        mocks["AssetSnapshots"].publish.assert_called_once()

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
        self.assertEqual(
            [payload["unique_identifier"] for payload in upserted(mocks["Asset"])],
            ["BBG000NVDA01"],
        )
        self.assertEqual(
            [row["asset_identifier"] for row in published(mocks["AssetSnapshots"])],
            ["BBG000NVDA01"],
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

    def test_figi_ticker_alias_maps_provider_symbol_to_openfigi_symbol(self) -> None:
        def fake_query_figi(tickers, *, market_sector, exch_code=None, **_):
            # The alias is what goes to OpenFIGI as idValue.
            assert "BRK/B" in tickers and "BRKB" not in tickers
            return [figi_row("BRK/B", "BBG000DWG505")]

        result, mocks = run_registration(
            tickers=["BRKB"],
            figi_rows=fake_query_figi,
            disambiguation_filters=[{"ticker": "BRKB", "figi_ticker": "BRK/B"}],
        )

        # Result keys by the REQUESTED ticker; identity is the FIGI.
        self.assertEqual(result.registered_figi_by_ticker, {"BRKB": "BBG000DWG505"})
        self.assertEqual(upserted(mocks["Asset"])[0]["unique_identifier"], "BBG000DWG505")
        # OpenFIGI's own symbol stays on the details row...
        self.assertEqual(upserted(mocks["OpenFigiDetails"])[0]["ticker"], "BRK/B")
        # ...but the snapshot carries the extraction-side ticker so the snapshot
        # resolver can match what providers actually produce.
        self.assertEqual(published(mocks["AssetSnapshots"])[0]["ticker"], "BRKB")

    def test_figi_ticker_alias_collision_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "alias collision"):
            register_equity_assets_from_tickers(
                tickers=["BRKB", "BRK/B"],
                disambiguation_filters=[{"ticker": "BRKB", "figi_ticker": "BRK/B"}],
            )

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
