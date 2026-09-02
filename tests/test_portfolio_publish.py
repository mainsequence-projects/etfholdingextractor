from __future__ import annotations

import datetime as dt
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mainsequence.meta_tables import TimeIndexTableRef, TimeIndexTableUpdater

from etfhextractor.portfolio_publish import (
    CALENDAR_FUTURE_HORIZON_DAYS,
    CALENDAR_PAST_BUFFER_DAYS,
    US_EQUITY_CALENDAR_KEY,
    EtfTrackingPortfolioBuild,
    build_etf_tracker_unique_identifier,
    build_etf_tracking_portfolio,
    ensure_trading_calendar,
    publish_etf_tracking_portfolio,
    required_calendar_window,
)
from etfhextractor.portfolio_signal import ETFHoldingsSignal

TODAY = dt.date(2026, 6, 10)


def build_calendar_row(
    *,
    valid_from: dt.date,
    valid_to: dt.date,
    source_identifier: str | None = "NYSE",
) -> SimpleNamespace:
    return SimpleNamespace(
        uid=uuid.uuid4(),
        unique_identifier="NYSE",
        source_identifier=source_identifier,
        valid_from=valid_from,
        valid_to=valid_to,
    )


class RequiredCalendarWindowTests(unittest.TestCase):
    def test_window_covers_backtest_with_buffer_and_future_horizon(self) -> None:
        start, end = required_calendar_window(backtest_start_days=60, today=TODAY)
        self.assertEqual(start, TODAY - dt.timedelta(days=60 + CALENDAR_PAST_BUFFER_DAYS))
        self.assertEqual(end, TODAY + dt.timedelta(days=CALENDAR_FUTURE_HORIZON_DAYS))

    def test_zero_backtest_still_keeps_past_buffer(self) -> None:
        start, _end = required_calendar_window(backtest_start_days=0, today=TODAY)
        self.assertEqual(start, TODAY - dt.timedelta(days=CALENDAR_PAST_BUFFER_DAYS))


class EnsureTradingCalendarTests(unittest.TestCase):
    def test_always_open_keys_persist_a_calendar_row_for_the_obligatory_fk(self) -> None:
        # The rebalancer resolves "24/7" synthetically, but the Portfolio row's
        # calendar remains obligatory in ms-markets 1.x (NOT NULL calendar_uid FK),
        # so even always-open keys persist a Calendar row + sessions.
        materialization_rows = object()
        with (
            patch("msm.api.calendars.Calendar") as calendar_cls,
            patch("msm.bootstrap.resolve_runtime") as resolve_runtime,
            patch(
                "msm.services.calendars.build_always_open_calendar_materialization",
                return_value=materialization_rows,
            ) as build_rows,
            patch("msm.services.calendars.materialize_calendar_rows") as materialize,
        ):
            calendar_cls.filter.return_value = []
            created = build_calendar_row(
                valid_from=TODAY - dt.timedelta(days=90),
                valid_to=TODAY + dt.timedelta(days=CALENDAR_FUTURE_HORIZON_DAYS),
                source_identifier="24/7",
            )
            calendar_cls.upsert.return_value = created

            result = ensure_trading_calendar("24/7", backtest_start_days=60, today=TODAY)

        self.assertIs(result, created)
        upsert_kwargs = calendar_cls.upsert.call_args.kwargs
        self.assertEqual(upsert_kwargs["unique_identifier"], "24/7")
        self.assertEqual(upsert_kwargs["source"], "always_open")
        build_rows.assert_called_once_with(
            calendar_uid=created.uid,
            start_date=TODAY - dt.timedelta(days=60 + CALENDAR_PAST_BUFFER_DAYS),
            end_date=TODAY + dt.timedelta(days=CALENDAR_FUTURE_HORIZON_DAYS),
        )
        materialize.assert_called_once_with(
            resolve_runtime.return_value.context, materialization_rows
        )
        calendar_cls.create_from_pandas_calendar.assert_not_called()

    def test_covering_always_open_calendar_is_reused_without_writes(self) -> None:
        existing = build_calendar_row(
            valid_from=TODAY - dt.timedelta(days=400),
            valid_to=TODAY + dt.timedelta(days=400),
            source_identifier="24/7",
        )
        with patch("msm.api.calendars.Calendar") as calendar_cls:
            calendar_cls.filter.return_value = [existing]

            result = ensure_trading_calendar("24/7", backtest_start_days=60, today=TODAY)

        self.assertIs(result, existing)
        calendar_cls.upsert.assert_not_called()
        calendar_cls.create_from_pandas_calendar.assert_not_called()

    def test_covering_calendar_is_reused_without_writes(self) -> None:
        existing = build_calendar_row(
            valid_from=TODAY - dt.timedelta(days=400),
            valid_to=TODAY + dt.timedelta(days=400),
        )
        with patch("msm.api.calendars.Calendar") as calendar_cls:
            calendar_cls.filter.return_value = [existing]

            result = ensure_trading_calendar(
                US_EQUITY_CALENDAR_KEY, backtest_start_days=60, today=TODAY
            )

        self.assertIs(result, existing)
        calendar_cls.filter.assert_called_once_with(
            unique_identifier=US_EQUITY_CALENDAR_KEY, limit=1
        )
        calendar_cls.create_from_pandas_calendar.assert_not_called()

    def test_missing_calendar_is_created_from_pandas_market_calendars(self) -> None:
        with patch("msm.api.calendars.Calendar") as calendar_cls:
            calendar_cls.filter.return_value = []
            created = build_calendar_row(
                valid_from=TODAY - dt.timedelta(days=90),
                valid_to=TODAY + dt.timedelta(days=CALENDAR_FUTURE_HORIZON_DAYS),
            )
            calendar_cls.create_from_pandas_calendar.return_value = created

            result = ensure_trading_calendar(
                US_EQUITY_CALENDAR_KEY, backtest_start_days=60, today=TODAY
            )

        self.assertIs(result, created)
        kwargs = calendar_cls.create_from_pandas_calendar.call_args.kwargs
        self.assertEqual(kwargs["source_identifier"], US_EQUITY_CALENDAR_KEY)
        self.assertEqual(kwargs["unique_identifier"], US_EQUITY_CALENDAR_KEY)
        self.assertEqual(
            kwargs["valid_from"], TODAY - dt.timedelta(days=60 + CALENDAR_PAST_BUFFER_DAYS)
        )
        self.assertEqual(
            kwargs["valid_to"], TODAY + dt.timedelta(days=CALENDAR_FUTURE_HORIZON_DAYS)
        )

    def test_short_calendar_window_is_extended_by_merging(self) -> None:
        # Existing row covers a window that ends too early: the refresh must merge
        # (never shrink) the persisted validity and keep its source mapping.
        existing = build_calendar_row(
            valid_from=TODAY - dt.timedelta(days=700),
            valid_to=TODAY + dt.timedelta(days=10),
            source_identifier="XNYS",
        )
        with patch("msm.api.calendars.Calendar") as calendar_cls:
            calendar_cls.filter.return_value = [existing]
            calendar_cls.create_from_pandas_calendar.return_value = existing

            ensure_trading_calendar(US_EQUITY_CALENDAR_KEY, backtest_start_days=60, today=TODAY)

        kwargs = calendar_cls.create_from_pandas_calendar.call_args.kwargs
        self.assertEqual(kwargs["source_identifier"], "XNYS")
        self.assertEqual(kwargs["valid_from"], TODAY - dt.timedelta(days=700))
        self.assertEqual(
            kwargs["valid_to"], TODAY + dt.timedelta(days=CALENDAR_FUTURE_HORIZON_DAYS)
        )


class TrackerIdentifierTests(unittest.TestCase):
    def test_identifier_is_prefixed_and_lowercased(self) -> None:
        self.assertEqual(build_etf_tracker_unique_identifier("IVV"), "etf_tracker_ivv")


class PortfolioValuationSourceTests(unittest.TestCase):
    def _publish(self, *, return_build: bool = False, **kwargs):
        calendar = build_calendar_row(
            valid_from=TODAY - dt.timedelta(days=90),
            valid_to=TODAY + dt.timedelta(days=366),
        )
        portfolio = SimpleNamespace(
            uid=uuid.uuid4(),
            unique_identifier="etf_tracker_ivv",
        )
        signal = MagicMock(spec=ETFHoldingsSignal)
        signal.signal_uid = "ivv-signal"
        portfolio_node = MagicMock()

        with (
            patch("etfhextractor.portfolio_publish.start_portfolio_engine"),
            patch(
                "etfhextractor.portfolio_publish.ensure_trading_calendar",
                return_value=calendar,
            ),
            patch(
                "etfhextractor.portfolio_publish.ETFHoldingsSignal.from_signal_configuration",
                return_value=signal,
            ),
            patch("msm.api.portfolios.Portfolio.upsert", return_value=portfolio),
            patch(
                "msm_portfolios.data_nodes.PortfoliosDataNode",
                return_value=portfolio_node,
            ) as node_cls,
            patch(
                "mainsequence.meta_tables.TimeIndexTableRef.from_uid"
            ) as from_uid,
        ):
            from_uid.return_value = object.__new__(TimeIndexTableRef)
            builder = (
                build_etf_tracking_portfolio
                if return_build
                else publish_etf_tracking_portfolio
            )
            payload = builder(
                etf_ticker="IVV",
                provider="ishares",
                asset_identifiers=["BBG000B9XRY4"],
                run=False,
                **kwargs,
            )

        configuration = node_cls.call_args.kwargs["portfolio_configuration"]
        return payload, configuration, from_uid

    def test_registered_table_uid_uses_sdk8_time_index_table_ref(self) -> None:
        payload, configuration, from_uid = self._publish(
            price_source_table_uid="table-uid-1"
        )

        from_uid.assert_called_once_with("table-uid-1")
        self.assertIs(
            configuration.portfolio_build_configuration.valuation_source_instance,
            from_uid.return_value,
        )
        self.assertEqual(payload["valuation_source"], "TimeIndexTableRef")
        self.assertEqual(payload["price_source_table_uid"], "table-uid-1")

    def test_explicit_updater_is_preserved_without_table_ref_substitution(self) -> None:
        updater = MagicMock(spec=TimeIndexTableUpdater)

        payload, configuration, from_uid = self._publish(
            price_source_instance=updater
        )

        from_uid.assert_not_called()
        self.assertIs(
            configuration.portfolio_build_configuration.valuation_source_instance,
            updater,
        )
        self.assertIsNone(payload["price_source_table_uid"])

    def test_reusable_build_preserves_project_specific_portfolio_contract(self) -> None:
        updater = MagicMock(spec=TimeIndexTableUpdater)

        build, configuration, from_uid = self._publish(
            return_build=True,
            price_source_instance=updater,
            portfolio_unique_identifier="IVV_TRACKER_BARS_1D_SIP_ALL__ALPACA",
            valuation_column="adjusted_close",
            signal_name="IVV holdings signal",
            rebalance_strategy_name="ImmediateSignal",
            start_engine=False,
        )

        self.assertIsInstance(build, EtfTrackingPortfolioBuild)
        self.assertEqual(
            build.portfolio_unique_identifier,
            "IVV_TRACKER_BARS_1D_SIP_ALL__ALPACA",
        )
        self.assertIs(build.valuation_source, updater)
        self.assertFalse(build.ran)
        self.assertEqual(
            configuration.portfolio_build_configuration.valuation_column,
            "adjusted_close",
        )
        details = configuration.portfolio_markets_configuration.front_end_details
        self.assertEqual(details.signal_name, "IVV holdings signal")
        self.assertEqual(details.rebalance_strategy_name, "ImmediateSignal")
        from_uid.assert_not_called()


if __name__ == "__main__":
    unittest.main()
