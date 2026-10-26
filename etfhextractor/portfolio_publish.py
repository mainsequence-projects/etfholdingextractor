"""Publish an ETF-tracking ms-markets portfolio.

Wires `ETFHoldingsSignal` into the msm_portfolios pipeline
(`signal -> PortfoliosUpdater` with an explicit valuation source) and resolves the
portfolio identity through the typed `Index` / `Portfolio` rows
(implementation task 0002, W-3).

Not imported from `etfhextractor.__init__`; pure extraction stays free of the
portfolio stack.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

# Calendar helpers live in the light `etfhextractor.calendars` module (registry row calls only,
# no msm_portfolios import); they are re-exported here for existing imports.
from .calendars import (
    ALWAYS_OPEN_CALENDAR_KEYS,
    CALENDAR_FUTURE_HORIZON_DAYS,
    CALENDAR_PAST_BUFFER_DAYS,
    US_EQUITY_CALENDAR_KEY,
    ensure_trading_calendar,
    required_calendar_window,
)
from .portfolio_signal import (
    ETFHoldingsSignal,
    ETFHoldingsSignalConfig,
)
from .providers.common import normalize_ticker

if TYPE_CHECKING:
    from msm_portfolios.services.series_moves import PortfolioSeriesTables

PRICE_SOURCE_TABLE_UID_ENV = "ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID"

ETF_TRACKER_IDENTIFIER_PREFIX = "etf_tracker_"


@dataclass(frozen=True, slots=True)
class EtfTrackingPortfolioBuild:
    """Reusable ETF portfolio graph and the rows created for it.

    The CLI-facing publisher returns :meth:`summary`; project integrations can
    consume this object directly without rebuilding the ms-markets graph.
    """

    etf_ticker: str
    instances: Any
    """The application's `PortfolioSeriesTables` the build writes."""
    portfolio_unique_identifier: str
    portfolio_name: str
    calendar_key: str
    backtest_start_days: int
    calendar_row: Any
    portfolio_row: Any
    signal: Any
    valuation_source: Any
    price_source_table_uid: str | None
    asset_registration: dict[str, Any] | None
    portfolio_configuration: Any
    portfolio_node: Any
    ran: bool
    run_result: Any | None
    portfolio_datasets: Any
    """The Markets catalog row (`PortfolioDatasetState`) registered for the instances."""

    def summary(self) -> dict[str, Any]:
        return {
            "etf_ticker": self.etf_ticker,
            "portfolio_unique_identifier": self.portfolio_unique_identifier,
            "portfolio_uid": self.portfolio_row.uid,
            "portfolio_name": self.portfolio_name,
            "calendar_key": self.calendar_key,
            "calendar_uid": self.calendar_row.uid,
            "backtest_start_days": self.backtest_start_days,
            "signal_uid": self.signal.signal_uid,
            "price_source_table_uid": self.price_source_table_uid,
            "valuation_source": type(self.valuation_source).__name__,
            "asset_registration": self.asset_registration,
            "ran": self.ran,
            "run_result": _summarize_run_result(self.run_result),
            "portfolio_datasets": _summarize_datasets(self.portfolio_datasets),
        }


def build_etf_tracker_unique_identifier(etf_ticker: str) -> str:
    normalized_ticker = normalize_ticker(etf_ticker)
    if not normalized_ticker:
        raise ValueError("ETF ticker must not be empty.")
    return f"{ETF_TRACKER_IDENTIFIER_PREFIX}{normalized_ticker.lower()}"


_INSTANCE_SLOTS = ("signal_weights", "weights", "rebalance_state", "values")


def require_portfolio_instances(instances: PortfolioSeriesTables) -> PortfolioSeriesTables:
    """Check that `instances` names the application's own tables for every series a publish writes.

    `instances` is an `msm_portfolios.services.series_moves.PortfolioSeriesTables` whose
    `signal_weights`, `weights`, `rebalance_state` and `values` slots hold `SignalWeightsTS`,
    `PortfolioWeightsTS`, `PortfolioRebalanceStateTS` and `PortfoliosTS` instances built with the
    `msm_portfolios.time_index.contract_instances` factories in the application's namespace
    (ms-markets ADR 0047). The Markets core tables are refused: this library never writes them.
    """
    from msm.settings import markets_namespace

    missing = [slot for slot in _INSTANCE_SLOTS if getattr(instances, slot, None) is None]
    if missing:
        raise ValueError(
            "instances must name the application's own SignalWeightsTS, PortfolioWeightsTS, "
            "PortfolioRebalanceStateTS and PortfoliosTS instances (PortfolioSeriesTables built "
            f"with the msm_portfolios.time_index.contract_instances factories); missing {missing}."
        )
    core = [
        slot
        for slot in _INSTANCE_SLOTS
        if (getattr(getattr(instances, slot), "__table__", None) is not None)
        and (getattr(instances, slot).__table__.info or {}).get("namespace")
        in (None, "", markets_namespace())
    ]
    if core:
        raise ValueError(
            f"instances {core} are Markets tables; pass instances in the application's own "
            "namespace."
        )
    return instances


def portfolio_runtime_models(
    instances: PortfolioSeriesTables,
    extra_models: list[Any] | None = None,
) -> list[Any]:
    """Tables a portfolio publish attaches in this process, for the selected backend.

    Always the four `instances` (see `require_portfolio_instances`) and `extra_models` (e.g. the
    project-owned `DemoBarsStorage` price source). On the remote backend (selected by the
    application, ADR 0047) that is all: every registry runs on the Markets API. On the runtime
    backend the registry row calls run in this process, so the Markets registry tables of the
    msm_portfolios graph, the OpenFIGI, asset-snapshot, category and calendar date/session tables
    are attached as well; no Markets time series is.

    A process gets one `start_engine` configuration: an application that attaches its own
    tables at its composition root includes these models in that call and passes
    `start_engine=False` to `build_etf_tracking_portfolio`.
    """
    from .markets_runtime import markets_api_selected

    require_portfolio_instances(instances)
    models: list[Any] = [getattr(instances, slot) for slot in _INSTANCE_SLOTS]
    if not markets_api_selected():
        from msm.base import MarketsTimeIndexMetaTableMixin
        from msm.models import (
            AssetCategoryMembershipTable,
            AssetCategoryTable,
            CalendarDateTable,
            CalendarSessionTable,
            OpenFigiAssetDetailsTable,
        )
        from msm.time_index.assets.storage import AssetSnapshotsStorage
        from msm_portfolios.bootstrap import resolve_portfolio_models

        registries = [
            model
            for model in resolve_portfolio_models(None)
            if not issubclass(model, MarketsTimeIndexMetaTableMixin)
        ]
        models = [
            *registries,
            OpenFigiAssetDetailsTable,
            AssetSnapshotsStorage,
            AssetCategoryTable,
            AssetCategoryMembershipTable,
            CalendarDateTable,
            CalendarSessionTable,
            *models,
        ]
    return [*models, *(extra_models or [])]


def start_portfolio_engine(
    instances: PortfolioSeriesTables,
    extra_models: list[Any] | None = None,
) -> Any:
    """Attach the markets runtime with `portfolio_runtime_models(instances, extra_models)`.

    When a superset runtime is already attached, it is reused. The row backend is the
    application's choice; this only attaches what that choice leaves in-process.
    """
    import msm_portfolios
    from msm.bootstrap import resolve_runtime

    models = portfolio_runtime_models(instances, extra_models)
    try:
        return resolve_runtime(models=models, row_model_name="etfhextractor.portfolio_publish")
    except RuntimeError:
        return msm_portfolios.start_engine(models=models)


def build_etf_tracking_portfolio(
    *,
    etf_ticker: str,
    instances: PortfolioSeriesTables,
    provider: str | None = None,
    fund_url: str | None = None,
    price_source_table_uid: str | None = None,
    price_source_instance: Any | None = None,
    portfolio_unique_identifier: str | None = None,
    portfolio_name: str | None = None,
    description: str | None = None,
    valuation_column: str = "close",
    signal_name: str | None = None,
    rebalance_strategy_name: str | None = None,
    signal_validity_days: int = 90,
    min_update_interval_days: float = 1.0,
    renormalize_weights: bool = True,
    commission_fee: float = 0.00018,
    calendar_key: str = US_EQUITY_CALENDAR_KEY,
    backtest_start_days: int = 60,
    timeout: float = 30.0,
    run: bool = True,
    register_missing: bool = False,
    figi_disambiguation_filters: list[dict[str, Any]] | None = None,
    asset_identifiers: list[str] | None = None,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
    start_engine: bool = True,
    update_pointers: bool = True,
    resolve_asset_identifiers_fn: Callable[..., Any] | None = None,
) -> EtfTrackingPortfolioBuild:
    """Build (and by default run) the ETF-tracking portfolio pipeline.

    The valuation source must provide the `close` column consumed by portfolio
    valuation. Pass either `price_source_instance` (an explicit
    TimeIndexTableUpdater/TimeIndexTableRef dependency, e.g. the project-owned
    `DemoBars` updater) or `price_source_table_uid` (an already-registered
    TimeIndexMetaTable resolved through `TimeIndexTableRef.from_uid`; defaults to the
    `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID` environment variable). A price
    table is never guessed.

    With `register_missing=True`, a preflight extraction resolves the component
    tickers and FIGI-registers the missing ones (ADR 0004: FIGI-keyed only,
    unique mapping required). When registration leaves unmapped or ambiguous
    tickers, a `FigiRegistrationError` is raised naming them; pass
    `figi_disambiguation_filters` (e.g.
    `[{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}]`) to
    narrow the OpenFIGI query per ticker.

    The calendar is OBLIGATORY in the portfolio architecture (ms-markets >=
    0.0.58: `PortfolioTable.calendar_uid` is a NOT NULL FK). `calendar_key`
    (default NYSE for US-listed ETFs) is persisted through the msm util
    `Calendar.create_from_pandas_calendar` and attached to the Portfolio row by
    FK (`calendar_uid`), and the signal stamps every observation on the same
    key's session closes. `ImmediateSignal` rebalances on those observations and
    ms-markets values the portfolio on the valuation source's observations
    (ms-markets >= 1.0.6), so a session-close price source keeps valuations off
    weekends and holidays. Always-open keys ("24/7") also persist a Calendar row
    to satisfy the FK. `backtest_start_days` (default 60) backdates the
    signal's first observation so the first run backtests that window with the
    current composition before live tracking takes over.

    Every series the build writes goes to the application's own tables (ms-markets ADR 0047):
    `instances` (a `PortfolioSeriesTables`, checked by `require_portfolio_instances`) binds
    `ETFHoldingsSignal` to its `signal_weights` instance and `PortfoliosUpdater` (with the
    `PortfolioWeights` and `PortfolioRebalance` updaters it builds) to its `values`, `weights`
    and `rebalance_state` instances. After the (optional) run the build records them in the
    Markets portfolio catalog with `PortfolioDatasets.register` (reconciling when it ran), which
    also binds the signal instance. Registries (calendar, Portfolio, SignalMetadata, the
    catalog) are row calls, which run on the Markets API when the application selected the
    remote backend. Output tables enter neither `update_hash` nor `signal_uid`, but a fresh
    signal instance has no history: copy existing rows in before its first run
    (`docs/library.md`, "Moving the series to your own instances").

    - `update_pointers=False` leaves the Portfolio row's table-update pointers untouched.
    - `resolve_asset_identifiers_fn` replaces the asset-snapshot ticker resolver
      (`resolve_asset_identifiers_by_ticker`, same signature and return value) in the
      preflight and in the signal, for an application that resolves tickers its own way.
    """
    require_portfolio_instances(instances)
    resolved_price_table_uid = price_source_table_uid or os.environ.get(
        PRICE_SOURCE_TABLE_UID_ENV
    )
    if price_source_instance is None and not resolved_price_table_uid:
        raise ValueError(
            "An ETF-tracking portfolio needs a price source: pass price_source_instance "
            "(a TimeIndexTableUpdater/TimeIndexTableRef) or a registered "
            "TimeIndexMetaTable uid via "
            f"price_source_table_uid / {PRICE_SOURCE_TABLE_UID_ENV}."
        )

    if start_engine:
        start_portfolio_engine(instances)

    # Persist (or reuse) the trading calendar BEFORE any portfolio wiring: the
    # rebalance schedule and the Portfolio row both hang off it.
    calendar_row = ensure_trading_calendar(
        calendar_key, backtest_start_days=backtest_start_days
    )

    normalized_ticker_for_preflight = normalize_ticker(etf_ticker)
    registration_summary: dict[str, Any] | None = None
    # Preflight extract+resolve when the caller did not precompute the updater
    # scope, or when missing components should be FIGI-registered first.
    if register_missing or asset_identifiers is None:
        from .mainsequence_categories import (
            derive_component_weights_from_holdings,
            resolve_asset_identifiers_by_ticker,
        )
        from .reader import ETFHoldingsReader

        _resolve_identifiers = resolve_asset_identifiers_fn or resolve_asset_identifiers_by_ticker

        reader = ETFHoldingsReader(timeout=timeout)
        fund_holdings = (
            reader.read(fund_url)
            if fund_url is not None
            else reader.read_ticker(normalized_ticker_for_preflight, provider=provider)
        )
        component_symbols = sorted(
            derive_component_weights_from_holdings(
                fund_holdings,
                allowed_asset_classes=allowed_asset_classes,
            )
        )
        existing_identifiers, missing, _ambiguous = _resolve_identifiers(
            component_symbols=component_symbols
        )
        if register_missing and missing:
            from .asset_registration import (
                FigiRegistrationError,
                register_equity_assets_from_tickers,
            )

            registration = register_equity_assets_from_tickers(
                tickers=missing,
                disambiguation_filters=figi_disambiguation_filters,
            )
            registration_summary = registration.summary()
            if registration.has_failures():
                # Fail fast with the blocked tickers (and FIGI candidates for the
                # ambiguous ones) instead of failing later inside the signal.
                raise FigiRegistrationError(registration)
            existing_identifiers, _missing, _ambiguous = _resolve_identifiers(
                component_symbols=component_symbols
            )
        if asset_identifiers is None:
            asset_identifiers = sorted(existing_identifiers.values())

    from metatables import TimeIndexTableRef
    from msm.api.portfolios import Portfolio
    from msm_portfolios.configuration import (
        BacktestingWeightsConfig,
        FrontEndDetails,
        PortfolioBuildConfiguration,
        PortfolioConfiguration,
        PortfolioExecutionConfiguration,
        PortfolioMarketsConfig,
    )
    from msm_portfolios.rebalance_strategy.immediate_signal import ImmediateSignal
    from msm_portfolios.time_index import PortfoliosUpdater

    normalized_ticker = normalize_ticker(etf_ticker)
    if not asset_identifiers:
        raise ValueError(
            "An ETF-tracking portfolio needs the resolved component asset identifiers "
            "as updater scope (ms-markets >= 0.0.54 derives the price window from the "
            "signal's preflight asset list on first runs). Pass asset_identifiers, or "
            "use register_missing=True so the preflight resolves them."
        )
    signal_config = ETFHoldingsSignalConfig(
        etf_ticker=normalized_ticker,
        provider=provider,
        fund_url=fund_url,
        renormalize_weights=renormalize_weights,
        allowed_asset_classes=allowed_asset_classes,
        signal_validity_days=signal_validity_days,
        min_update_interval_days=min_update_interval_days,
        backtest_start_days=backtest_start_days,
        # The signal stamps observations on the SAME session grid the portfolio
        # values on (previous market close), so weights and prices align exactly.
        calendar_key=calendar_key,
        timeout=timeout,
        # Updater scope; neutralized in the signal_uid payload, so the signal
        # stays one stable series per ETF across composition changes.
        asset_list=sorted(asset_identifiers),
    )
    signal = ETFHoldingsSignal.from_signal_configuration(
        signal_config, output_table=instances.signal_weights
    )
    if resolve_asset_identifiers_fn is not None:
        signal.set_asset_identifier_resolver(resolve_asset_identifiers_fn)
    valuation_source = (
        price_source_instance
        if price_source_instance is not None
        else TimeIndexTableRef.from_uid(str(resolved_price_table_uid))
    )

    resolved_name = portfolio_name or f"ETF Tracker {normalized_ticker}"
    resolved_description = description or (
        f"Tracks ETF {normalized_ticker} from provider holdings extractions; signal weights "
        "update at most daily and only when the holdings change."
    )

    portfolio_configuration = PortfolioConfiguration(
        portfolio_build_configuration=PortfolioBuildConfiguration(
            valuation_source_instance=valuation_source,
            valuation_column=valuation_column,
            execution_configuration=PortfolioExecutionConfiguration(
                commission_fee=commission_fee
            ),
            backtesting_weights_configuration=BacktestingWeightsConfig(
                # ms-markets >= 1.0.7 strategies take no calendar_key; the signal
                # carries the calendar through its session-close stamps.
                rebalance_strategy_instance=ImmediateSignal(),
                signal_weights_instance=signal,
            ),
        ),
        portfolio_markets_configuration=PortfolioMarketsConfig(
            portfolio_name=resolved_name,
            front_end_details=FrontEndDetails(
                description=resolved_description,
                signal_name=signal_name,
                rebalance_strategy_name=rebalance_strategy_name,
            ),
        ),
    )

    # Portfolio identity is the Portfolio row alone (ms-markets >= 0.0.54):
    # PortfoliosUpdater uses the provided target_portfolio and keys all storage
    # by portfolio.unique_identifier. PortfolioIndex is now just an optional
    # published-index reference (Portfolio.published_index_uid) — never identity —
    # so this workflow does not create or rely on any Index row. The calendar is
    # OBLIGATORY (ms-markets 1.x): PortfolioTable.calendar_uid is a NOT NULL
    # FK to CalendarTable.uid (ondelete=RESTRICT) and the run() pointer update
    # refuses rows without it; the legacy calendar_name field no longer exists.
    portfolio_identifier = (
        portfolio_unique_identifier
        or build_etf_tracker_unique_identifier(normalized_ticker)
    )
    portfolio_row = Portfolio.upsert(
        unique_identifier=portfolio_identifier,
        calendar_uid=calendar_row.uid,
    )

    node = PortfoliosUpdater(
        portfolio_configuration=portfolio_configuration,
        output_table=instances.values,
        weights_output_table=instances.weights,
        rebalance_output_table=instances.rebalance_state,
    )
    node.set_portfolio_configuration(
        portfolio_configuration,
        portfolio_description=resolved_description,
    )
    node.target_portfolio = portfolio_row
    # ms-markets 0.0.54: run() resolves identity from target_portfolio, but
    # update()'s values normalizer reads _explicit_portfolio_identifier and
    # otherwise demands an external portfolio_resolver. Pin both to the same
    # Portfolio row identity so no resolver is needed.
    node._explicit_portfolio_identifier = portfolio_identifier

    run_result = None
    if run:
        # SDK >= 8.1 / metatables: updater runs always execute in-process and
        # immediately; the removed debug_mode/force_update controls are not passed.
        run_result = node.run(update_pointers=update_pointers)
    # After the run, so the Portfolio row carries its signal_uid and registration binds
    # SignalMetadata to the signal instance; re-registering is idempotent.
    portfolio_datasets = register_portfolio_datasets(
        portfolio_uid=portfolio_row.uid, instances=instances, reconcile=run
    )
    return EtfTrackingPortfolioBuild(
        etf_ticker=normalized_ticker,
        instances=instances,
        portfolio_unique_identifier=portfolio_identifier,
        portfolio_name=resolved_name,
        calendar_key=calendar_key,
        backtest_start_days=backtest_start_days,
        calendar_row=calendar_row,
        portfolio_row=portfolio_row,
        signal=signal,
        valuation_source=valuation_source,
        price_source_table_uid=(
            str(resolved_price_table_uid) if resolved_price_table_uid else None
        ),
        asset_registration=registration_summary,
        portfolio_configuration=portfolio_configuration,
        portfolio_node=node,
        ran=run,
        run_result=run_result,
        portfolio_datasets=portfolio_datasets,
    )


def register_signal_dataset(*, signal_uid: str, signal_output_table: Any) -> Any:
    """Record the `SignalWeightsTS` instance that holds one signal in the Markets catalog.

    One `msm_portfolios.api.datasets.PortfolioDatasets.register_signal` row call (write-policy
    resource `portfolio-datasets` under the remote backend) for a signal whose instance no
    portfolio registration binds, e.g. an `ETFHoldingsSignal` run without a portfolio. Markets
    verifies the table against the signal-weights contract (its workload needs `data_viewer` on
    it) and needs the signal's `SignalMetadata` row, which the signal's run writes.
    """
    from msm_portfolios.api.datasets import PortfolioDatasets

    return PortfolioDatasets.register_signal(
        {
            "signal_uid": str(signal_uid),
            "signal_meta_table_uid": _meta_table_uid(signal_output_table),
        }
    )


def register_portfolio_datasets(
    *,
    portfolio_uid: Any,
    instances: PortfolioSeriesTables,
    reconcile: bool = True,
) -> Any:
    """Record a portfolio's values, weights and signal instances in the Markets catalog.

    One `msm_portfolios.api.datasets.PortfolioDatasets.register` row call (write-policy resource
    `portfolio-datasets` under the remote backend). Markets verifies each table against its
    contract and, with `reconcile=True`, refreshes the population state; the Markets workload
    needs `data_viewer` on each table. The rebalance-state instance is not catalogued by Markets.
    """
    from msm_portfolios.api.datasets import PortfolioDatasets

    require_portfolio_instances(instances)
    return PortfolioDatasets.register(
        {
            "portfolio_uid": portfolio_uid,
            "values_meta_table_uid": _meta_table_uid(instances.values),
            "weights_meta_table_uid": _meta_table_uid(instances.weights),
            "signal_meta_table_uid": _meta_table_uid(instances.signal_weights),
        },
        reconcile=reconcile,
    )


def _meta_table_uid(table: Any) -> str:
    uid = table.get_meta_table_uid()
    if not uid:
        raise RuntimeError(
            f"{getattr(table, '__name__', table)!r} has no MetaTable uid: attach it (start_engine) "
            "after its migration Job registered it."
        )
    return str(uid)


def publish_etf_tracking_portfolio(
    *,
    etf_ticker: str,
    instances: PortfolioSeriesTables,
    provider: str | None = None,
    fund_url: str | None = None,
    price_source_table_uid: str | None = None,
    price_source_instance: Any | None = None,
    portfolio_unique_identifier: str | None = None,
    portfolio_name: str | None = None,
    description: str | None = None,
    valuation_column: str = "close",
    signal_name: str | None = None,
    rebalance_strategy_name: str | None = None,
    signal_validity_days: int = 90,
    min_update_interval_days: float = 1.0,
    renormalize_weights: bool = True,
    commission_fee: float = 0.00018,
    calendar_key: str = US_EQUITY_CALENDAR_KEY,
    backtest_start_days: int = 60,
    timeout: float = 30.0,
    run: bool = True,
    register_missing: bool = False,
    figi_disambiguation_filters: list[dict[str, Any]] | None = None,
    asset_identifiers: list[str] | None = None,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
    start_engine: bool = True,
    update_pointers: bool = True,
    resolve_asset_identifiers_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Build an ETF-tracking portfolio and return its JSON-friendly summary.

    Takes the arguments of `build_etf_tracking_portfolio`.
    """
    build = build_etf_tracking_portfolio(
        etf_ticker=etf_ticker,
        instances=instances,
        provider=provider,
        fund_url=fund_url,
        price_source_table_uid=price_source_table_uid,
        price_source_instance=price_source_instance,
        portfolio_unique_identifier=portfolio_unique_identifier,
        portfolio_name=portfolio_name,
        description=description,
        valuation_column=valuation_column,
        signal_name=signal_name,
        rebalance_strategy_name=rebalance_strategy_name,
        signal_validity_days=signal_validity_days,
        min_update_interval_days=min_update_interval_days,
        renormalize_weights=renormalize_weights,
        commission_fee=commission_fee,
        calendar_key=calendar_key,
        backtest_start_days=backtest_start_days,
        timeout=timeout,
        run=run,
        register_missing=register_missing,
        figi_disambiguation_filters=figi_disambiguation_filters,
        asset_identifiers=asset_identifiers,
        allowed_asset_classes=allowed_asset_classes,
        start_engine=start_engine,
        update_pointers=update_pointers,
        resolve_asset_identifiers_fn=resolve_asset_identifiers_fn,
    )
    return build.summary()


def _summarize_datasets(state: Any) -> Any:
    dump = getattr(state, "model_dump", None)
    return dump(mode="json") if callable(dump) else state


def _summarize_run_result(run_result: Any) -> Any:
    """Flatten updater run results to JSON-friendly summaries, raising on the
    (error_on_last_update, frame) failure contract."""
    if isinstance(run_result, dict):
        return {key: _summarize_run_result(value) for key, value in run_result.items()}
    if isinstance(run_result, tuple) and len(run_result) == 2:
        error_on_last_update, frame = run_result
        if error_on_last_update:
            raise RuntimeError("Portfolio pipeline update failed; see the updater logs.")
        row_count = getattr(frame, "shape", (0,))[0] if frame is not None else 0
        return {"error": False, "rows": int(row_count)}
    if run_result is None:
        return None
    return str(run_result)


__all__ = [
    "ALWAYS_OPEN_CALENDAR_KEYS",
    "CALENDAR_FUTURE_HORIZON_DAYS",
    "CALENDAR_PAST_BUFFER_DAYS",
    "ETF_TRACKER_IDENTIFIER_PREFIX",
    "EtfTrackingPortfolioBuild",
    "PRICE_SOURCE_TABLE_UID_ENV",
    "US_EQUITY_CALENDAR_KEY",
    "build_etf_tracker_unique_identifier",
    "build_etf_tracking_portfolio",
    "ensure_trading_calendar",
    "portfolio_runtime_models",
    "publish_etf_tracking_portfolio",
    "register_portfolio_datasets",
    "register_signal_dataset",
    "require_portfolio_instances",
    "required_calendar_window",
    "start_portfolio_engine",
]
