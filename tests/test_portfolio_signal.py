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
    previous_session_close,
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

    def test_signal_validity_must_cover_backtest_window_with_headroom(self) -> None:
        # The portfolio forward-fills weights at most signal_validity_days past an
        # observation and its index reaches one session past "now", so equality
        # (60/60) leaves the bootstrap observation pre-expired — headroom required.
        with self.assertRaisesRegex(ValueError, "must cover backtest_start_days"):
            build_config(signal_validity_days=30, backtest_start_days=60)
        with self.assertRaisesRegex(ValueError, "headroom"):
            build_config(signal_validity_days=60, backtest_start_days=60)
        with self.assertRaisesRegex(ValueError, "backtest_start_days must be >= 0"):
            build_config(backtest_start_days=-1)


class ETFHoldingsSignalTests(unittest.TestCase):
    def test_first_run_emits_normalized_weights_on_as_of_session_close(self) -> None:
        # backtest_start_days=0 disables the bootstrap backdating: the first
        # observation lands on the as-of date's MARKET CLOSE (2026-04-27 is a
        # Monday => NYSE close 20:00 UTC), never at an insertion wall-clock time.
        signal = build_signal(build_config(backtest_start_days=0), stored=None)

        frame, _reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertEqual(list(frame.index.names), ["time_index", ASSET_IDENTIFIER])
        weights = frame["signal_weight"]
        self.assertAlmostEqual(float(weights.sum()), 1.0)
        self.assertAlmostEqual(float(weights.loc[(slice(None), AAPL_ID)].iloc[0]), 0.6)
        self.assertAlmostEqual(float(weights.loc[(slice(None), MSFT_ID)].iloc[0]), 0.4)
        observed_time = frame.index.get_level_values("time_index")[0]
        self.assertEqual(
            pd.Timestamp(observed_time),
            pd.Timestamp("2026-04-27 20:00", tz="UTC"),
        )

    def test_first_run_backdates_observation_to_a_session_close(self) -> None:
        # Default config: the first stored observation is stamped on the session
        # close at/before now - backtest_start_days, so the portfolio backtests
        # [now - 60d, now] on the same session grid it values on.
        signal = build_signal(build_config(), stored=None)

        before = dt.datetime.now(dt.timezone.utc)
        frame, _reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())
        after = dt.datetime.now(dt.timezone.utc)

        observed_time = pd.Timestamp(frame.index.get_level_values("time_index")[0])
        expected = {
            pd.Timestamp(previous_session_close(before - dt.timedelta(days=60))),
            pd.Timestamp(previous_session_close(after - dt.timedelta(days=60))),
        }
        self.assertIn(observed_time, expected)

    def test_backdating_applies_only_to_the_first_run(self) -> None:
        # With stored history the monotonic session-grid rule applies; the
        # backtest bootstrap never rewrites or restarts an existing series. The
        # provider as-of (2026-04-27) predates the stored observation, so the
        # latest COMPLETED session close is used.
        now = dt.datetime.now(dt.timezone.utc)
        last_time = now - dt.timedelta(days=10)
        stored = build_stored_frame(last_time, {AAPL_ID: 0.5, MSFT_ID: 0.5})
        signal = build_signal(build_config(), stored=stored)

        frame, _reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        observed_time = pd.Timestamp(frame.index.get_level_values("time_index")[0])
        self.assertGreater(observed_time, pd.Timestamp(last_time))
        self.assertEqual(observed_time, pd.Timestamp(previous_session_close(now)))

    def test_unchanged_weights_are_restamped_before_validity_expires(self) -> None:
        # Guard (b) must not starve the portfolio: when the last observation is
        # about to fall out of the signal_validity_days forward-fill window, the
        # signal re-stamps even though the weights are numerically unchanged.
        now = dt.datetime.now(dt.timezone.utc)
        last_time = now - dt.timedelta(days=89)  # validity 90, refresh margin 2 days
        stored = build_stored_frame(last_time, {AAPL_ID: 0.6, MSFT_ID: 0.4})
        signal = build_signal(build_config(), stored=stored)

        frame, _reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertEqual(len(frame), 2)
        observed_time = pd.Timestamp(frame.index.get_level_values("time_index")[0])
        # Monotonic and on the session grid: either the provider as-of close
        # (when still newer than the stored observation) or the latest completed
        # close — both extend the forward-fill coverage.
        self.assertGreater(observed_time, pd.Timestamp(last_time))
        self.assertIn(
            observed_time,
            {
                pd.Timestamp("2026-04-27 20:00", tz="UTC"),
                pd.Timestamp(previous_session_close(now)),
            },
        )

    def test_at_most_one_observation_per_session(self) -> None:
        # Changed weights whose session close is already covered do not insert:
        # observations live on the session grid, one per session by construction.
        # (min_update_interval_days=0 bypasses the daily throttle so the session
        # rule itself is exercised.)
        now = dt.datetime.now(dt.timezone.utc)
        last_time = previous_session_close(now)
        stored = build_stored_frame(last_time, {AAPL_ID: 0.5, MSFT_ID: 0.5})
        signal = build_signal(build_config(min_update_interval_days=0.0), stored=stored)

        frame, reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertTrue(frame.empty)
        reader_cls.return_value.read_ticker.assert_called_once()

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
        now = dt.datetime.now(dt.timezone.utc)
        last_time = now - dt.timedelta(days=10)
        stored = build_stored_frame(last_time, {AAPL_ID: 0.5, MSFT_ID: 0.5})
        signal = build_signal(build_config(), stored=stored)

        frame, _reader_cls = run_signal(signal, fund_holdings=build_fund_holdings())

        self.assertEqual(len(frame), 2)
        self.assertAlmostEqual(float(frame["signal_weight"].sum()), 1.0)
        observed_time = pd.Timestamp(frame.index.get_level_values("time_index")[0])
        # The provider as-of (2026-04-27) predates the last stored observation, so
        # the latest completed session close keeps the series monotonic.
        self.assertGreater(observed_time, pd.Timestamp(last_time))
        self.assertEqual(observed_time, pd.Timestamp(previous_session_close(now)))

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
        signal = build_signal(
            build_config(signal_validity_days=10, backtest_start_days=0), stored=None
        )
        self.assertEqual(signal.maximum_forward_fill(), dt.timedelta(days=10))

    def test_previous_session_close_snaps_to_market_close(self) -> None:
        # Saturday 2026-04-11 10:00 UTC -> Friday 2026-04-10 20:00 UTC (NYSE);
        # always-open keys close at UTC midnight.
        saturday = dt.datetime(2026, 4, 11, 10, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(
            previous_session_close(saturday),
            dt.datetime(2026, 4, 10, 20, 0, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(
            previous_session_close(saturday, calendar_key="24/7"),
            dt.datetime(2026, 4, 11, 0, 0, tzinfo=dt.timezone.utc),
        )

    def test_signal_uid_is_invariant_under_asset_list_scope(self) -> None:
        # asset_list is updater scope, never series identity: an ETF rebalance
        # must not rotate the signal_uid (no orphaned series, no guard resets,
        # no portfolio-config churn).
        from msm_portfolios.data_nodes import compute_signal_uid

        def make(asset_list: list[str] | None, ticker: str = "IVV") -> ETFHoldingsSignal:
            signal = ETFHoldingsSignal.__new__(ETFHoldingsSignal)
            signal.signal_configuration = ETFHoldingsSignalConfig(
                etf_ticker=ticker, provider="ishares", asset_list=asset_list
            )
            return signal

        uid_without_scope = compute_signal_uid(make(None))
        uid_scope_a = compute_signal_uid(make([AAPL_ID, MSFT_ID]))
        uid_scope_b = compute_signal_uid(make([AAPL_ID, MSFT_ID, "us_equity_nvda"]))
        self.assertEqual(uid_without_scope, uid_scope_a)
        self.assertEqual(uid_scope_a, uid_scope_b)
        # ...while real identity inputs still differentiate signals.
        self.assertNotEqual(uid_without_scope, compute_signal_uid(make(None, ticker="SPY")))

    def test_get_asset_list_returns_configured_scope(self) -> None:
        signal = build_signal(build_config(asset_list=[MSFT_ID, AAPL_ID]), stored=None)
        self.assertEqual(signal.get_asset_list(), sorted([AAPL_ID, MSFT_ID]))
        signal_without_scope = build_signal(build_config(), stored=None)
        self.assertIsNone(signal_without_scope.get_asset_list())

    def test_explanation_is_plain_text(self) -> None:
        signal = build_signal(build_config(), stored=None)
        explanation = signal.get_explanation()
        self.assertNotIn("<", explanation)
        self.assertNotIn(">", explanation)


if __name__ == "__main__":
    unittest.main()
