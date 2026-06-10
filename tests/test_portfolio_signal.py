from __future__ import annotations

import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from etfhextractor.models import FundHoldings, Holding
from etfhextractor.portfolio_signal import (
    ETFHoldingsSignal,
    ETFHoldingsSignalConfig,
)
from msm_portfolios.data_nodes.constants import ASSET_IDENTIFIER

IVV_URL = "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf"
SIGNAL_UID_VALUE = "etf-holdings-signal-uid"

AAPL_ID = "us_equity_aapl"
MSFT_ID = "us_equity_msft"


def build_config(**overrides) -> ETFHoldingsSignalConfig:
    values = {"etf_ticker": "IVV", "provider": "ishares"}
    values.update(overrides)
    return ETFHoldingsSignalConfig(**values)


def build_signal(config: ETFHoldingsSignalConfig, *, stored: pd.DataFrame | None) -> ETFHoldingsSignal:
    signal = ETFHoldingsSignal.__new__(ETFHoldingsSignal)
    signal.signal_configuration = config
    signal._resolve_signal_uid = lambda: SIGNAL_UID_VALUE
    signal.update_statistics = SimpleNamespace(filter_df_by_latest_value=lambda frame: frame)
    signal.get_df_between_dates = Mock(
        return_value=stored if stored is not None else pd.DataFrame()
    )
    return signal


def build_stored_frame(time_index: dt.datetime, weights: dict[str, float]) -> pd.DataFrame:
    rows = [
        {
            "time_index": time_index,
            "signal_uid": SIGNAL_UID_VALUE,
            ASSET_IDENTIFIER: identifier,
            "signal_weight": weight,
        }
        for identifier, weight in weights.items()
    ]
    return pd.DataFrame(rows).set_index(["time_index", "signal_uid", ASSET_IDENTIFIER])


def build_fund_holdings(*, aapl_weight: float = 60.0, msft_weight: float = 40.0) -> FundHoldings:
    return FundHoldings(
        url=IVV_URL,
        download_url="https://example.com/holdings_export.xls",
        fund_name="iShares Core S&P 500 ETF",
        as_of_date="Apr 27, 2026",
        holdings=(
            Holding(ticker="AAPL", name="Apple Inc.", weight=aapl_weight, asset_class="Equity"),
            Holding(ticker="MSFT", name="Microsoft Corp.", weight=msft_weight, asset_class="Equity"),
            Holding(ticker="USD", name="USD CASH", weight=0.5, asset_class="Cash"),
        ),
    )


def run_signal(
    signal: ETFHoldingsSignal,
    *,
    fund_holdings: FundHoldings,
    identifiers: dict[str, str] | None = None,
    missing: list[str] | None = None,
    ambiguous: list[str] | None = None,
) -> tuple[pd.DataFrame, Mock]:
    resolved = identifiers if identifiers is not None else {"AAPL": AAPL_ID, "MSFT": MSFT_ID}
    with patch("etfhextractor.portfolio_signal.ETFHoldingsReader") as reader_cls, patch(
        "etfhextractor.portfolio_signal.resolve_asset_identifiers_by_ticker",
        return_value=(resolved, missing or [], ambiguous or []),
    ):
        reader_cls.return_value.read_ticker.return_value = fund_holdings
        reader_cls.return_value.read.return_value = fund_holdings
        frame = signal._calculate_signal_weights()
    return frame, reader_cls


class ETFHoldingsSignalConfigTests(unittest.TestCase):
    def test_requires_provider_or_fund_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider or fund_url"):
            ETFHoldingsSignalConfig(etf_ticker="IVV")


class ETFHoldingsSignalTests(unittest.TestCase):
    def test_first_run_emits_normalized_weights_at_as_of_date(self) -> None:
        signal = build_signal(build_config(), stored=None)

        frame, _reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertEqual(list(frame.index.names), ["time_index", ASSET_IDENTIFIER])
        weights = frame["signal_weight"]
        self.assertAlmostEqual(float(weights.sum()), 1.0)
        self.assertAlmostEqual(float(weights.loc[(slice(None), AAPL_ID)].iloc[0]), 0.6)
        self.assertAlmostEqual(float(weights.loc[(slice(None), MSFT_ID)].iloc[0]), 0.4)
        observed_time = frame.index.get_level_values("time_index")[0]
        self.assertEqual(
            pd.Timestamp(observed_time),
            pd.Timestamp("2026-04-27", tz="UTC"),
        )

    def test_daily_throttle_skips_without_extracting(self) -> None:
        last_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
        stored = build_stored_frame(last_time, {AAPL_ID: 0.6, MSFT_ID: 0.4})
        signal = build_signal(build_config(), stored=stored)

        frame, reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertTrue(frame.empty)
        reader_cls.assert_not_called()

    def test_unchanged_weights_are_not_reinserted(self) -> None:
        last_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)
        stored = build_stored_frame(last_time, {AAPL_ID: 0.6, MSFT_ID: 0.4})
        signal = build_signal(build_config(), stored=stored)

        frame, reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertTrue(frame.empty)
        reader_cls.return_value.read_ticker.assert_called_once_with("IVV", provider="ishares")

    def test_changed_weights_insert_with_monotonic_time_index(self) -> None:
        last_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)
        stored = build_stored_frame(last_time, {AAPL_ID: 0.5, MSFT_ID: 0.5})
        signal = build_signal(build_config(), stored=stored)

        frame, _reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertEqual(len(frame), 2)
        self.assertAlmostEqual(float(frame["signal_weight"].sum()), 1.0)
        observed_time = pd.Timestamp(frame.index.get_level_values("time_index")[0])
        # The provider as-of (2026-04-27) predates the last stored observation, so
        # the extraction time is used to keep the series monotonic.
        self.assertGreater(observed_time, pd.Timestamp(last_time))

    def test_unresolved_components_fail_the_update(self) -> None:
        signal = build_signal(build_config(), stored=None)

        with self.assertRaisesRegex(RuntimeError, r"missing=\['MSFT'\].*ambiguous=\['AAPL'\]"):
            run_signal(
                signal,
                fund_holdings=build_fund_holdings(),
                identifiers={},
                missing=["MSFT"],
                ambiguous=["AAPL"],
            )

    def test_renormalization_can_be_disabled(self) -> None:
        signal = build_signal(build_config(renormalize_weights=False), stored=None)

        frame, _reader_cls = run_signal(
            signal,
            fund_holdings=build_fund_holdings(aapl_weight=50.0, msft_weight=30.0),
        )

        weights = frame["signal_weight"]
        self.assertAlmostEqual(float(weights.loc[(slice(None), AAPL_ID)].iloc[0]), 0.5)
        self.assertAlmostEqual(float(weights.loc[(slice(None), MSFT_ID)].iloc[0]), 0.3)
        self.assertAlmostEqual(float(weights.sum()), 0.8)

    def test_maximum_forward_fill_follows_config(self) -> None:
        signal = build_signal(build_config(signal_validity_days=10), stored=None)
        self.assertEqual(signal.maximum_forward_fill(), dt.timedelta(days=10))


if __name__ == "__main__":
    unittest.main()
