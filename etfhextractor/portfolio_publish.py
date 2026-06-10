"""Publish an ETF-tracking ms-markets portfolio.

Wires `ETFHoldingsSignal` into the msm_portfolios pipeline
(`signal -> PortfoliosDataNode` with an explicit price source) and resolves the
portfolio identity through the typed `Index` / `Portfolio` rows
(implementation task 0002, W-3).

Not imported from `etfhextractor.__init__`; pure extraction stays free of the
portfolio stack.
"""

from __future__ import annotations

import os
from typing import Any

from .portfolio_signal import ETFHoldingsSignal, ETFHoldingsSignalConfig
from .providers.common import normalize_ticker

PRICE_SOURCE_TABLE_UID_ENV = "ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID"

ETF_TRACKER_IDENTIFIER_PREFIX = "etf_tracker_"


def build_etf_tracker_unique_identifier(etf_ticker: str) -> str:
    normalized_ticker = normalize_ticker(etf_ticker)
    if not normalized_ticker:
        raise ValueError("ETF ticker must not be empty.")
    return f"{ETF_TRACKER_IDENTIFIER_PREFIX}{normalized_ticker.lower()}"


def start_portfolio_engine(extra_models: list[Any] | None = None) -> Any:
    """Attach the markets runtime with the portfolio graph plus the snapshot and
    category tables, so the signal's ticker resolution and any category sync in
    the same process reuse this one runtime (a process can only call
    start_engine with one schema config).

    `extra_models` extends the list with additional backend table classes — e.g.
    the project-owned `DemoBarsStorage` when the example publishes demo prices.
    When a superset runtime is already attached, it is reused.
    """
    import msm_portfolios
    from msm.bootstrap import resolve_runtime
    from msm.data_nodes.assets.storage import AssetSnapshotsStorage
    from msm.models import (
        AssetCategoryMembershipTable,
        AssetCategoryTable,
        OpenFigiAssetDetailsTable,
    )
    from msm_portfolios.bootstrap import resolve_portfolio_models

    models = [
        *resolve_portfolio_models(None),
        OpenFigiAssetDetailsTable,
        AssetSnapshotsStorage,
        AssetCategoryTable,
        AssetCategoryMembershipTable,
        *(extra_models or []),
    ]
    try:
        return resolve_runtime(models=models, row_model_name="etfhextractor.portfolio_publish")
    except RuntimeError:
        return msm_portfolios.start_engine(models=models)


def publish_etf_tracking_portfolio(
    *,
    etf_ticker: str,
    provider: str | None = None,
    fund_url: str | None = None,
    price_source_table_uid: str | None = None,
    price_source_instance: Any | None = None,
    portfolio_name: str | None = None,
    description: str | None = None,
    signal_validity_days: int = 30,
    min_update_interval_days: float = 1.0,
    renormalize_weights: bool = True,
    commission_fee: float = 0.00018,
    calendar_key: str = "24/7",
    timeout: float = 30.0,
    run: bool = True,
    debug_mode: bool = True,
    register_missing: bool = False,
    figi_disambiguation_filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build (and by default run) the ETF-tracking portfolio pipeline.

    The price source must provide the `close` and `volume` columns the
    rebalance logic consumes. Pass either `price_source_instance` (an explicit
    DataNode/APIDataNode dependency, e.g. the project-owned `DemoBars` node) or
    `price_source_table_uid` (an already-registered TimeIndexMetaTable resolved
    through `APIDataNode.build_from_table_uid`; defaults to the
    `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID` environment variable). A price
    table is never guessed.

    With `register_missing=True`, a preflight extraction resolves the component
    tickers and FIGI-registers the missing ones (ADR 0004: FIGI-keyed only,
    unique mapping required). When registration leaves unmapped or ambiguous
    tickers, a `FigiRegistrationError` is raised naming them; pass
    `figi_disambiguation_filters` (e.g.
    `[{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}]`) to
    narrow the OpenFIGI query per ticker.
    """
    resolved_price_table_uid = price_source_table_uid or os.environ.get(
        PRICE_SOURCE_TABLE_UID_ENV
    )
    if price_source_instance is None and not resolved_price_table_uid:
        raise ValueError(
            "An ETF-tracking portfolio needs a price source: pass price_source_instance "
            "(a DataNode/APIDataNode) or a registered TimeIndexMetaTable uid via "
            f"price_source_table_uid / {PRICE_SOURCE_TABLE_UID_ENV}."
        )

    start_portfolio_engine()

    normalized_ticker_for_preflight = normalize_ticker(etf_ticker)
    registration_summary: dict[str, Any] | None = None
    if register_missing:
        from .asset_registration import (
            FigiRegistrationError,
            register_equity_assets_from_tickers,
        )
        from .mainsequence_categories import derive_component_weights_from_holdings
        from .mainsequence_categories import (
            resolve_asset_identifiers_by_ticker as _resolve_identifiers,
        )
        from .reader import ETFHoldingsReader

        reader = ETFHoldingsReader(timeout=timeout)
        fund_holdings = (
            reader.read(fund_url)
            if fund_url is not None
            else reader.read_ticker(normalized_ticker_for_preflight, provider=provider)
        )
        component_symbols = sorted(derive_component_weights_from_holdings(fund_holdings))
        _existing, missing, _ambiguous = _resolve_identifiers(
            component_symbols=component_symbols
        )
        if missing:
            registration = register_equity_assets_from_tickers(
                tickers=missing,
                disambiguation_filters=figi_disambiguation_filters,
            )
            registration_summary = registration.summary()
            if registration.has_failures():
                # Fail fast with the blocked tickers (and FIGI candidates for the
                # ambiguous ones) instead of failing later inside the signal.
                raise FigiRegistrationError(registration)

    from mainsequence.meta_tables import APIDataNode
    from msm.api.portfolios import Portfolio
    from msm_portfolios.configuration import (
        BacktestingWeightsConfig,
        FrontEndDetails,
        PortfolioBuildConfiguration,
        PortfolioConfiguration,
        PortfolioExecutionConfiguration,
        PortfolioMarketsConfig,
    )
    from msm_portfolios.data_nodes import PortfoliosDataNode
    from msm_portfolios.rebalance_strategy.immediate_signal import ImmediateSignal

    normalized_ticker = normalize_ticker(etf_ticker)
    signal_config = ETFHoldingsSignalConfig(
        etf_ticker=normalized_ticker,
        provider=provider,
        fund_url=fund_url,
        renormalize_weights=renormalize_weights,
        signal_validity_days=signal_validity_days,
        min_update_interval_days=min_update_interval_days,
        timeout=timeout,
    )
    signal = ETFHoldingsSignal.from_signal_configuration(signal_config)
    price_source = (
        price_source_instance
        if price_source_instance is not None
        else APIDataNode.build_from_table_uid(str(resolved_price_table_uid))
    )

    resolved_name = portfolio_name or f"ETF Tracker {normalized_ticker}"
    resolved_description = description or (
        f"Tracks ETF {normalized_ticker} from provider holdings extractions; signal weights "
        "update at most daily and only when the holdings change."
    )

    portfolio_configuration = PortfolioConfiguration(
        portfolio_build_configuration=PortfolioBuildConfiguration(
            price_source_instance=price_source,
            execution_configuration=PortfolioExecutionConfiguration(
                commission_fee=commission_fee
            ),
            backtesting_weights_configuration=BacktestingWeightsConfig(
                rebalance_strategy_instance=ImmediateSignal(calendar_key=calendar_key),
                signal_weights_instance=signal,
            ),
        ),
        portfolio_markets_configuration=PortfolioMarketsConfig(
            portfolio_name=resolved_name,
            front_end_details=FrontEndDetails(description=resolved_description),
        ),
    )

    # Portfolio identity is the Portfolio row alone (ms-markets >= 0.0.54):
    # PortfoliosDataNode uses the provided target_portfolio and keys all storage
    # by portfolio.unique_identifier. PortfolioIndex is now just an optional
    # published-index reference (Portfolio.published_index_uid) — never identity —
    # so this workflow does not create or rely on any Index row.
    portfolio_identifier = build_etf_tracker_unique_identifier(normalized_ticker)
    portfolio_row = Portfolio.upsert(unique_identifier=portfolio_identifier)

    node = PortfoliosDataNode(portfolio_configuration=portfolio_configuration)
    node.set_portfolio_configuration(
        portfolio_configuration,
        portfolio_description=resolved_description,
    )
    node.target_portfolio = portfolio_row

    payload: dict[str, Any] = {
        "etf_ticker": normalized_ticker,
        "portfolio_unique_identifier": portfolio_identifier,
        "portfolio_uid": portfolio_row.uid,
        "portfolio_name": resolved_name,
        "signal_uid": signal.signal_uid,
        "price_source_table_uid": (
            str(resolved_price_table_uid) if resolved_price_table_uid else None
        ),
        "price_source": type(price_source).__name__,
        "asset_registration": registration_summary,
        "ran": False,
        "run_result": None,
    }
    if run:
        run_result = node.run(debug_mode=debug_mode, force_update=True)
        payload["ran"] = True
        payload["run_result"] = _summarize_run_result(run_result)
    return payload


def _summarize_run_result(run_result: Any) -> Any:
    """Flatten DataNode run results to JSON-friendly summaries, raising on the
    (error_on_last_update, frame) failure contract."""
    if isinstance(run_result, dict):
        return {key: _summarize_run_result(value) for key, value in run_result.items()}
    if isinstance(run_result, tuple) and len(run_result) == 2:
        error_on_last_update, frame = run_result
        if error_on_last_update:
            raise RuntimeError("Portfolio pipeline update failed; see DataNode logs.")
        row_count = getattr(frame, "shape", (0,))[0] if frame is not None else 0
        return {"error": False, "rows": int(row_count)}
    if run_result is None:
        return None
    return str(run_result)


__all__ = [
    "ETF_TRACKER_IDENTIFIER_PREFIX",
    "PRICE_SOURCE_TABLE_UID_ENV",
    "build_etf_tracker_unique_identifier",
    "publish_etf_tracking_portfolio",
    "start_portfolio_engine",
]
