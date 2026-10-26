from __future__ import annotations

import datetime as dt
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from metatables import TimeIndexTableRef, TimeIndexTableUpdater
from msm_portfolios.rebalance_strategy.immediate_signal import ImmediateSignal

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
        # Rebalance strategies take no calendar in ms-markets 2.x, but the Portfolio
        # row's calendar remains obligatory (NOT NULL calendar_uid FK), so even
        # always-open keys persist a Calendar row + dates and sessions — through
        # set-based registry row calls, never a runtime context.
        materialization_rows = SimpleNamespace(
            dates=[{"local_date": TODAY}], sessions=[{"local_date": TODAY}]
        )
        with (
            patch("msm.api.calendars.Calendar") as calendar_cls,
            patch("msm.api.calendars.CalendarDate") as calendar_date_cls,
            patch("msm.api.calendars.CalendarSession") as calendar_session_cls,
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
        calendar_date_cls.upsert_many.assert_called_once_with(materialization_rows.dates)
        calendar_session_cls.upsert_many.assert_called_once_with(materialization_rows.sessions)
        resolve_runtime.assert_not_called()
        materialize.assert_not_called()
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
                "msm_portfolios.time_index.PortfoliosUpdater",
                return_value=portfolio_node,
            ) as node_cls,
            patch("metatables.TimeIndexTableRef.from_uid") as from_uid,
        ):
            from_uid.return_value = object.__new__(TimeIndexTableRef)
            builder = (
                build_etf_tracking_portfolio
                if return_build
                else publish_etf_tracking_portfolio
            )
            kwargs.setdefault("run", False)
            payload = builder(
                etf_ticker="IVV",
                provider="ishares",
                asset_identifiers=["BBG000B9XRY4"],
                **kwargs,
            )

        configuration = node_cls.call_args.kwargs["portfolio_configuration"]
        return payload, configuration, from_uid

    def test_registered_table_uid_uses_metatables_time_index_table_ref(self) -> None:
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
        # ms-markets >= 1.0.7: the strategy carries no calendar_key; the signal's
        # session-close stamps carry the calendar.
        strategy = (
            configuration.portfolio_build_configuration
            .backtesting_weights_configuration.rebalance_strategy_instance
        )
        self.assertIsInstance(strategy, ImmediateSignal)
        from_uid.assert_not_called()

    def test_run_calls_the_portfolio_node_without_removed_run_controls(self) -> None:
        updater = MagicMock(spec=TimeIndexTableUpdater)

        build, _configuration, _from_uid = self._publish(
            return_build=True,
            price_source_instance=updater,
            run=True,
        )

        self.assertTrue(build.ran)
        # SDK >= 8.1 / metatables runs take no debug_mode/force_update controls;
        # the Portfolio pointers are updated by default.
        build.portfolio_node.run.assert_called_once_with(update_pointers=True)
        self.assertIs(build.run_result, build.portfolio_node.run.return_value)
        self.assertIsNone(build.portfolio_datasets)
        self.assertNotIn("portfolio_datasets", build.summary())


class InjectionSeamTests(unittest.TestCase):
    """ADR 0047 seams: every default keeps the earlier behaviour; injected instances, catalog
    registration, pointer updates and ticker resolution reach the ms-markets objects."""

    def _build(self, **kwargs):
        calendar = build_calendar_row(
            valid_from=TODAY - dt.timedelta(days=90),
            valid_to=TODAY + dt.timedelta(days=366),
        )
        portfolio = SimpleNamespace(uid=uuid.uuid4(), unique_identifier="etf_tracker_ivv")
        signal = MagicMock(spec=ETFHoldingsSignal)
        signal.signal_uid = "ivv-signal"
        mocks = SimpleNamespace(signal=signal, portfolio=portfolio)
        with (
            patch("etfhextractor.portfolio_publish.start_portfolio_engine") as engine,
            patch(
                "etfhextractor.portfolio_publish.ensure_trading_calendar",
                return_value=calendar,
            ),
            patch(
                "etfhextractor.portfolio_publish.ETFHoldingsSignal.from_signal_configuration",
                return_value=signal,
            ) as from_config,
            patch("msm.api.portfolios.Portfolio.upsert", return_value=portfolio),
            patch("msm_portfolios.time_index.PortfoliosUpdater") as node_cls,
            patch("msm_portfolios.api.datasets.PortfolioDatasets.register") as register,
            patch(
                "msm_portfolios.api.datasets.PortfolioDatasets.register_signal"
            ) as register_signal,
        ):
            kwargs.setdefault("asset_identifiers", ["BBG000B9XRY4"])
            build = build_etf_tracking_portfolio(
                etf_ticker="IVV",
                provider="ishares",
                price_source_instance=MagicMock(spec=TimeIndexTableUpdater),
                **kwargs,
            )
        mocks.engine = engine
        mocks.from_config = from_config
        mocks.node_cls = node_cls
        mocks.register = register
        mocks.register_signal = register_signal
        return build, mocks

    @staticmethod
    def _table(uid: str) -> MagicMock:
        table = MagicMock()
        table.get_meta_table_uid.return_value = uid
        return table

    def test_defaults_write_the_core_tables_and_register_nothing(self) -> None:
        build, mocks = self._build(run=True)

        self.assertEqual(mocks.from_config.call_args.kwargs, {})
        self.assertEqual(
            set(mocks.node_cls.call_args.kwargs), {"portfolio_configuration"}
        )
        mocks.register.assert_not_called()
        mocks.register_signal.assert_not_called()
        self.assertNotIn("signal_dataset", build.summary())
        mocks.signal.set_asset_identifier_resolver.assert_not_called()
        engine_kwargs = mocks.engine.call_args.kwargs
        self.assertIsNone(engine_kwargs["portfolio_output_table"])

    def test_instances_bind_every_updater_and_register_the_catalog_after_the_run(self) -> None:
        values, weights, rebalance, signal_table = (
            self._table("values-uid"),
            self._table("weights-uid"),
            self._table("rebalance-uid"),
            self._table("signal-uid"),
        )

        build, mocks = self._build(
            run=True,
            portfolio_output_table=values,
            weights_output_table=weights,
            rebalance_output_table=rebalance,
            signal_output_table=signal_table,
        )

        self.assertIs(mocks.from_config.call_args.kwargs["output_table"], signal_table)
        node_kwargs = mocks.node_cls.call_args.kwargs
        self.assertIs(node_kwargs["output_table"], values)
        self.assertIs(node_kwargs["weights_output_table"], weights)
        self.assertIs(node_kwargs["rebalance_output_table"], rebalance)
        engine_kwargs = mocks.engine.call_args.kwargs
        self.assertIs(engine_kwargs["portfolio_output_table"], values)
        self.assertIs(engine_kwargs["signal_output_table"], signal_table)
        mocks.register.assert_called_once_with(
            {
                "portfolio_uid": mocks.portfolio.uid,
                "values_meta_table_uid": "values-uid",
                "weights_meta_table_uid": "weights-uid",
                "signal_meta_table_uid": "signal-uid",
            },
            reconcile=True,
        )
        self.assertIs(build.portfolio_datasets, mocks.register.return_value)
        # The portfolio registration binds the signal instance too.
        mocks.register_signal.assert_not_called()

    def test_a_signal_only_instance_is_bound_after_the_run(self) -> None:
        signal_table = self._table("signal-uid")

        build, mocks = self._build(run=True, signal_output_table=signal_table)

        mocks.register.assert_not_called()
        mocks.register_signal.assert_called_once_with(
            {"signal_uid": "ivv-signal", "signal_meta_table_uid": "signal-uid"}
        )
        self.assertIs(build.signal_dataset, mocks.register_signal.return_value)
        self.assertIsNone(build.portfolio_datasets)

    def test_a_signal_only_instance_waits_for_a_run(self) -> None:
        build, mocks = self._build(run=False, signal_output_table=self._table("signal-uid"))

        mocks.register_signal.assert_not_called()
        self.assertIsNone(build.signal_dataset)

    def test_explicit_signal_only_registration_without_a_run_fails_before_any_write(self) -> None:
        with (
            patch("etfhextractor.portfolio_publish.start_portfolio_engine") as engine,
            patch("etfhextractor.portfolio_publish.ensure_trading_calendar") as calendar,
        ):
            with self.assertRaisesRegex(ValueError, "run=True"):
                build_etf_tracking_portfolio(
                    etf_ticker="IVV",
                    provider="ishares",
                    price_source_table_uid="table-uid-1",
                    asset_identifiers=["BBG000B9XRY4"],
                    signal_output_table=self._table("signal-uid"),
                    register_datasets=True,
                    run=False,
                )
        engine.assert_not_called()
        calendar.assert_not_called()

    def test_registration_without_a_run_does_not_reconcile(self) -> None:
        _build, mocks = self._build(run=False, portfolio_output_table=self._table("values-uid"))

        registration, = mocks.register.call_args.args
        self.assertIsNone(registration["weights_meta_table_uid"])
        self.assertFalse(mocks.register.call_args.kwargs["reconcile"])

    def test_registration_can_be_switched_off(self) -> None:
        _build, mocks = self._build(
            run=False,
            portfolio_output_table=self._table("values-uid"),
            register_datasets=False,
        )

        mocks.register.assert_not_called()

    def test_registration_needs_an_instance_and_fails_before_any_write(self) -> None:
        with (
            patch("etfhextractor.portfolio_publish.start_portfolio_engine") as engine,
            patch("etfhextractor.portfolio_publish.ensure_trading_calendar") as calendar,
        ):
            with self.assertRaisesRegex(ValueError, "portfolio_output_table or signal_output_table"):
                build_etf_tracking_portfolio(
                    etf_ticker="IVV",
                    provider="ishares",
                    price_source_table_uid="table-uid-1",
                    asset_identifiers=["BBG000B9XRY4"],
                    register_datasets=True,
                )
        engine.assert_not_called()
        calendar.assert_not_called()

    def test_pointer_updates_can_be_left_to_the_caller(self) -> None:
        build, _mocks = self._build(run=True, update_pointers=False)

        build.portfolio_node.run.assert_called_once_with(update_pointers=False)

    def test_ticker_resolver_replaces_the_snapshot_read(self) -> None:
        resolver = MagicMock(return_value=({"AAPL": "BBG000B9XRY4"}, [], []))
        holdings = SimpleNamespace(holdings=[], fund_name="IVV", as_of_date=None)
        with (
            patch("etfhextractor.reader.ETFHoldingsReader") as reader_cls,
            patch(
                "etfhextractor.mainsequence_categories.derive_component_weights_from_holdings",
                return_value={"AAPL": 100.0},
            ),
            patch(
                "etfhextractor.mainsequence_categories.resolve_asset_identifiers_by_ticker"
            ) as snapshot_resolver,
        ):
            reader_cls.return_value.read_ticker.return_value = holdings
            build, mocks = self._build(
                run=False, asset_identifiers=None, resolve_asset_identifiers_fn=resolver
            )

        resolver.assert_called_once_with(component_symbols=["AAPL"])
        snapshot_resolver.assert_not_called()
        mocks.signal.set_asset_identifier_resolver.assert_called_once_with(resolver)


if __name__ == "__main__":
    unittest.main()
