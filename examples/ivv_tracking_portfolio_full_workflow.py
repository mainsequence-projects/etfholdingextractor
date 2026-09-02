"""Full workflow: create an ms-markets portfolio that tracks an ETF (default IVV).

Pipeline (implementation task 0002 / ADR 0003 — the msm_portfolios signal path):

    extraction (FundHoldings) ──> ETFHoldingsSignal (custom SignalWeights)
                                          │ (time_index, asset_identifier) → signal_weight
    registered bars table ── TimeIndexTableRef ─┴──> PortfoliosDataNode ──> ETF-tracking portfolio

**Self-sufficient by default** — the only prerequisites are an authenticated Main
Sequence session and the built-in ms-markets MetaTables registered by the SDK
migration provider. The flag-free run does everything else itself:

0. Prepare the **project-owned** `DemoBarsTS` price-table schema the way the
   ms-markets examples do (`examples/prepare_demo_bars_schema.py`): find-or-generate
   the Alembic revision through the project provider
   (`etfhextractor_migrations:migration`), `mainsequence migrations upgrade head`,
   verify the registered `TimeIndexMetaTable` (skip with `--skip-schema-prep`; not
   needed when `--price-source-table-uid` supplies an external price table).
1. Attach the markets runtime once (`msm_portfolios.start_engine` superset: portfolio
   graph + asset snapshots + category tables + `DemoBarsStorage`).
2. Extract the ETF holdings with the same `ETFHoldingsReader` the category workflow uses.
3. Derive component weights (shared equity filter) and resolve tickers to ms-markets
   asset identifiers through the snapshot layer.
4. FIGI-register missing components (default; disable with `--no-register-missing`):
   `query_figi` → `Asset.upsert(unique_identifier=figi)` + `OpenFigiDetails.upsert` +
   `AssetSnapshot` rows (ADR 0004 — no asset without a FIGI, and a ticker must map to
   exactly one FIGI; unmapped/ambiguous tickers stay blockers, disambiguate with
   `--figi-filter`). Reads the `OPEN_FIGI_API_KEY` Main Sequence secret.
5. Optionally sync the `HOLDINGS__<ETF>` asset category (`--with-category-sync`).
5.5. Publish deterministic demo bars into `DemoBarsTS`
   (`etfhextractor/markets_models.py`, extension-mixin convention, logical id
   `etfhextractor.DemoBarsTS`) and use that TimeIndexTableUpdater as the portfolio
   price source — no external market-data feed required. Bars land on the
   **NYSE session closes** (pandas_market_calendars), aligned with the
   portfolio's valuation index.
6. Publish the tracking portfolio: the `ETFHoldingsSignal` (insert at most once per day,
   only on weight changes) wired into `PortfoliosDataNode` with the price source —
   demo bars by default, or a registered table when `--price-source-table-uid` /
   `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID` is given; or run the signal node alone
   with `--signal-only`. A US ETF follows the US trading calendar: the NYSE
   calendar is persisted as ms-markets Calendar/CalendarSession rows (msm util
   `Calendar.create_from_pandas_calendar`) and attached to the Portfolio row by
   FK (`calendar_uid`), so valuations land on real session closes only. The
   signal's first observation is backdated `--backtest-start-days` (default 60)
   so the portfolio backtests that window before live tracking takes over.
7. Verify by reading back the platform rows: signal weights, portfolio values,
   portfolio weights, and the `Portfolio` identity row (including its calendar FK).

For isolated sandboxes set `MSM_AUTO_REGISTER_NAMESPACE` before running.

Run:

    python examples/ivv_tracking_portfolio_full_workflow.py                  # everything
    python examples/ivv_tracking_portfolio_full_workflow.py --plan-only      # no writes
    python examples/ivv_tracking_portfolio_full_workflow.py --signal-only
    python examples/ivv_tracking_portfolio_full_workflow.py \
        --price-source-table-uid <UID> --with-category-sync
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from etfhextractor import (
    ETFHoldingsReader,
    build_holdings_asset_category_plan,
    derive_component_weights_from_holdings,
    resolve_asset_identifiers_by_ticker,
    sync_holdings_asset_category,
)
from etfhextractor.models import FundHoldings
from etfhextractor.portfolio_publish import (
    PRICE_SOURCE_TABLE_UID_ENV,
    US_EQUITY_CALENDAR_KEY,
    build_etf_tracker_unique_identifier,
    publish_etf_tracking_portfolio,
    start_portfolio_engine,
)
from etfhextractor.portfolio_signal import ETFHoldingsSignal, ETFHoldingsSignalConfig


def _log(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def _extract_holdings(
    *,
    etf_ticker: str,
    provider: str | None,
    fund_url: str | None,
    timeout: float,
) -> FundHoldings:
    reader = ETFHoldingsReader(timeout=timeout)
    if fund_url is not None:
        return reader.read(fund_url)
    return reader.read_ticker(etf_ticker, provider=provider)


def _register_missing_assets_via_figi(
    *,
    missing_symbols: list[str],
    figi_disambiguation_filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """FIGI-register unresolved components (ADR 0004).

    No asset is registered without a FIGI, and a ticker must map to exactly one
    FIGI — multiple candidates would risk mixing different assets that share a
    ticker, so those stay blockers. Ambiguity is resolved explicitly through
    per-ticker disambiguation filters, e.g.
    `{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}`.
    Requires the `OPEN_FIGI_API_KEY` secret.
    """
    from etfhextractor.asset_registration import register_equity_assets_from_tickers

    registration = register_equity_assets_from_tickers(
        tickers=missing_symbols,
        disambiguation_filters=figi_disambiguation_filters,
    )
    _log(
        "register",
        f"FIGI-registered {len(registration.registered_figi_by_ticker)} new assets "
        f"({len(registration.already_registered_figi_by_ticker)} already registered, "
        f"{len(registration.snapshots_published_for_figis)} snapshots published); "
        f"unmapped={registration.unmapped_tickers} "
        f"ambiguous={sorted(registration.ambiguous_figi_candidates_by_ticker)}",
    )
    failure_message = registration.format_failures()
    if failure_message is not None:
        _log("register", failure_message)
    return registration.summary()


def _trading_session_closes(*, calendar_key: str, days: int) -> list[Any]:
    """Session-close timestamps for the past `days` days from pandas_market_calendars."""
    import datetime as dt

    import pandas_market_calendars as mcal

    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=days)
    schedule = mcal.get_calendar(calendar_key).schedule(
        start_date=start.isoformat(), end_date=end.isoformat()
    )
    return [close.to_pydatetime() for close in schedule["market_close"]]


def _publish_demo_bars(
    *,
    asset_identifiers: list[str],
    calendar_key: str,
    days: int = 180,
) -> Any:
    """Publish deterministic demo bars into the project-owned `DemoBarsTS` table.

    `DemoBarsStorage` is etfhextractor's own ms-markets table, defined per the
    extension-mixin convention (`etfhextractor/markets_models.py`, logical id
    `etfhextractor.DemoBarsTS`); it must be migrated/registered
    by the SDK migration provider before this write. Bars carry `close` and
    `volume` (the columns the rebalance logic consumes), one row per
    (session close, asset) on the SAME trading calendar the portfolio is
    scheduled on — so the valuation index and the price index align exactly,
    with no rows on weekends or holidays. Prices are deterministic per
    identifier so re-runs are stable.
    """
    import hashlib

    from etfhextractor.markets_models import DemoBars

    session_closes = _trading_session_closes(calendar_key=calendar_key, days=days)
    if not session_closes:
        raise RuntimeError(
            f"No {calendar_key} sessions found in the last {days} days; cannot publish demo bars."
        )
    rows: list[dict[str, Any]] = []
    for identifier in asset_identifiers:
        digest = int(hashlib.sha1(identifier.encode("utf-8")).hexdigest()[:8], 16)
        base_price = 50.0 + (digest % 100)
        daily_drift = ((digest % 7) - 3) * 1e-4
        for session_index, session_close in enumerate(session_closes):
            rows.append(
                {
                    "time_index": session_close,
                    "asset_identifier": identifier,
                    "close": round(base_price * (1.0 + daily_drift * session_index), 6),
                    "volume": 1_000_000.0,
                }
            )

    bars_node = DemoBars().set_bars(rows)
    error_on_last_update, _frame = bars_node.run(debug_mode=True, force_update=True)
    if error_on_last_update:
        raise RuntimeError("DemoBars update failed while publishing demo prices.")
    _log(
        "prices",
        f"Published {len(rows)} demo bars ({len(session_closes)} {calendar_key} session "
        f"closes x {len(asset_identifiers)} assets) into etfhextractor.DemoBarsTS.",
    )
    return bars_node


def _run_signal_only(
    *,
    etf_ticker: str,
    provider: str | None,
    fund_url: str | None,
    timeout: float,
) -> dict[str, Any]:
    """Run only the holdings signal node — writes canonical SignalWeights rows."""
    signal_config = ETFHoldingsSignalConfig(
        etf_ticker=etf_ticker,
        provider=provider,
        fund_url=fund_url,
        timeout=timeout,
    )
    signal = ETFHoldingsSignal.from_signal_configuration(signal_config)
    run_result = signal.run(debug_mode=True, force_update=True)
    if isinstance(run_result, tuple) and len(run_result) == 2:
        error_on_last_update, frame = run_result
        if error_on_last_update:
            raise RuntimeError("ETFHoldingsSignal update failed.")
        rows = 0 if frame is None else int(getattr(frame, "shape", (0,))[0])
    else:
        rows = None
    return {"signal_uid": signal.signal_uid, "signal_rows_written": rows}


def _verify_platform_rows(
    *,
    portfolio_identifier: str,
    signal_uid: str | None,
) -> dict[str, Any]:
    """Read back what the run produced, straight from the MetaTables."""
    from msm.api.base import operation_result_rows
    from msm.api.portfolios import Portfolio
    from msm.bootstrap import get_runtime
    from msm.repositories.crud import search_model
    from msm_portfolios.data_nodes.portfolios.storage import (
        PortfoliosStorage,
        PortfolioWeightsStorage,
    )
    from msm_portfolios.data_nodes.signals.storage import SignalWeightsStorage

    context = get_runtime().context
    verification: dict[str, Any] = {}

    if signal_uid is not None:
        signal_rows = operation_result_rows(
            search_model(
                context,
                model=SignalWeightsStorage,
                filters={"signal_uid": signal_uid},
                limit=500,
            )
        )
        verification["signal_weight_rows"] = len(signal_rows)
        verification["signal_weight_sample"] = signal_rows[:3]

    portfolio_values_rows = operation_result_rows(
        search_model(
            context,
            model=PortfoliosStorage,
            filters={"portfolio_identifier": portfolio_identifier},
            limit=500,
        )
    )
    verification["portfolio_value_rows"] = len(portfolio_values_rows)
    verification["portfolio_value_sample"] = portfolio_values_rows[:3]

    portfolio_weight_rows = operation_result_rows(
        search_model(
            context,
            model=PortfolioWeightsStorage,
            # ms-markets >= 0.0.54: portfolio weights are keyed by the portfolio
            # unique identifier (PortfolioIndex is just a reference, never identity).
            filters={"portfolio_identifier": portfolio_identifier},
            limit=500,
        )
    )
    verification["portfolio_weight_rows"] = len(portfolio_weight_rows)

    portfolio_row = Portfolio.get_by_unique_identifier(portfolio_identifier)
    verification["portfolio_row"] = None if portfolio_row is None else portfolio_row.model_dump()
    return verification


def run_full_workflow(
    *,
    etf_ticker: str = "IVV",
    provider: str | None = "ishares",
    fund_url: str | None = None,
    price_source_table_uid: str | None = None,
    prepare_schema: bool = True,
    revision_message: str | None = None,
    plan_only: bool = False,
    signal_only: bool = False,
    with_category_sync: bool = False,
    register_missing_assets: bool = True,
    figi_disambiguation_filters: list[dict[str, Any]] | None = None,
    calendar_key: str = US_EQUITY_CALENDAR_KEY,
    backtest_start_days: int = 60,
    timeout: float = 30.0,
) -> dict[str, Any]:
    etf_ticker = etf_ticker.strip().upper()
    summary: dict[str, Any] = {"etf_ticker": etf_ticker}

    # Self-sufficient by default: when no external price table is given, the
    # example owns the price source end-to-end (DemoBarsTS schema + demo bars).
    resolved_price_table_uid = price_source_table_uid or os.environ.get(
        PRICE_SOURCE_TABLE_UID_ENV
    )
    # plan-only performs no writes and never touches prices, so the project price
    # table stays out of schema prep AND the runtime attach in that mode.
    use_demo_prices = (
        resolved_price_table_uid is None and not signal_only and not plan_only
    )
    summary["price_source_mode"] = (
        "signal_only"
        if signal_only
        else ("demo_bars" if use_demo_prices else "registered_table")
    )

    # 0. Demo prices need the project-owned DemoBarsTS schema migrated/registered
    #    first — same pattern as the ms-markets examples: find-or-generate the
    #    Alembic revision through the project provider, upgrade head, verify.
    if use_demo_prices and prepare_schema and not plan_only:
        _log("schema", "Preparing the DemoBarsTS schema (revision + upgrade + verify)...")
        from prepare_demo_bars_schema import prepare_demo_bars_schema

        summary["schema_preparation"] = prepare_demo_bars_schema(
            revision_message=revision_message,
        )

    # 1. One runtime for the whole workflow (portfolio graph + snapshots + categories).
    #    A process gets one start_engine config, so the project-owned demo bars
    #    table must be in this first attach when demo prices are used.
    extra_models: list[Any] = []
    if use_demo_prices:
        from etfhextractor.markets_models import DemoBarsStorage

        extra_models.append(DemoBarsStorage)
    _log("engine", "Attaching markets runtime (msm_portfolios superset)...")
    start_portfolio_engine(extra_models=extra_models or None)

    # 2. Extract holdings — the same reader the category workflow uses.
    _log("extract", f"Extracting {etf_ticker} holdings...")
    fund_holdings = _extract_holdings(
        etf_ticker=etf_ticker,
        provider=provider,
        fund_url=fund_url,
        timeout=timeout,
    )
    summary["fund_name"] = fund_holdings.fund_name
    summary["as_of_date"] = fund_holdings.as_of_date
    summary["holdings_rows"] = len(fund_holdings.holdings)
    _log(
        "extract",
        f"{fund_holdings.fund_name} as of {fund_holdings.as_of_date}: "
        f"{len(fund_holdings.holdings)} holdings rows.",
    )

    # 3. Component weights + snapshot-layer resolution (shared machinery).
    weights_by_symbol = derive_component_weights_from_holdings(fund_holdings)
    summary["component_count"] = len(weights_by_symbol)
    _log("resolve", f"{len(weights_by_symbol)} equity components; resolving tickers...")
    existing, missing, ambiguous = resolve_asset_identifiers_by_ticker(
        component_symbols=sorted(weights_by_symbol),
    )
    _log(
        "resolve",
        f"existing={len(existing)} missing={len(missing)} ambiguous={len(ambiguous)}",
    )

    # 4. Optional FIGI registration for missing assets (ADR 0004: FIGI-keyed only,
    #    unique mapping required). Snapshot ambiguity is never auto-fixed.
    if missing and register_missing_assets and not plan_only:
        _log(
            "register",
            f"FIGI-registering {len(missing)} components (2 row ops each; on remote "
            "databases this can take several seconds per asset)...",
        )
        summary["asset_registration"] = _register_missing_assets_via_figi(
            missing_symbols=missing,
            figi_disambiguation_filters=figi_disambiguation_filters,
        )
        existing, missing, ambiguous = resolve_asset_identifiers_by_ticker(
            component_symbols=sorted(weights_by_symbol),
        )
        _log(
            "resolve",
            f"after FIGI registration: existing={len(existing)} missing={len(missing)} "
            f"ambiguous={len(ambiguous)}",
        )

    summary["missing_registered_symbols"] = missing
    summary["ambiguous_registered_symbols"] = ambiguous
    if missing or ambiguous:
        summary["blocked"] = True
        _log(
            "blocked",
            "Unresolved components — a tracker built on a partial universe would "
            f"misrepresent {etf_ticker}. missing={missing} ambiguous={ambiguous}",
        )
        if not register_missing_assets and missing:
            _log(
                "blocked",
                "Missing components were not registered because --no-register-missing "
                "was set; drop the flag to FIGI-register them.",
            )
        return summary
    summary["blocked"] = False

    if plan_only:
        _log("plan", "Plan-only mode: no platform writes performed.")
        return summary

    # 5. Optional: keep the HOLDINGS__<ETF> category in sync (capability 2),
    #    reusing the already-extracted holdings.
    if with_category_sync:
        plan = build_holdings_asset_category_plan(
            etf_ticker=etf_ticker,
            fund_url=fund_url,
            component_provider=provider,
            read_holdings_fn=lambda identifier, provider=None: fund_holdings,
        )
        if plan.has_blockers():
            raise RuntimeError(
                "Category plan has blockers despite resolved identifiers: "
                f"{plan.missing_registered_symbols} {plan.ambiguous_registered_symbols}"
            )
        sync_result = sync_holdings_asset_category(
            etf_ticker=etf_ticker,
            asset_uids=list(plan.existing_asset_uids_by_symbol.values()),
        )
        summary["category"] = {
            "unique_identifier": sync_result.unique_identifier,
            "member_count": len(sync_result.asset_uids),
        }
        _log(
            "category",
            f"{sync_result.unique_identifier} synced with "
            f"{len(sync_result.asset_uids)} members.",
        )

    # 5.5. Demo prices: publish the project-owned bars table (DemoBarsTS, ADR/library
    #      extension convention) so the portfolio pipeline has a price source.
    demo_bars_node = None
    if use_demo_prices:
        demo_bars_node = _publish_demo_bars(
            asset_identifiers=sorted(existing.values()),
            calendar_key=calendar_key,
            # Cover the backtest window with margin so the first portfolio run
            # has prices for every backdated session.
            days=max(180, backtest_start_days + 60),
        )
        summary["demo_prices"] = {
            "storage": "etfhextractor.DemoBarsTS",
            "asset_count": len(existing),
            "calendar_key": calendar_key,
        }

    # 6. Signal (+ portfolio) publication.
    portfolio_identifier = build_etf_tracker_unique_identifier(etf_ticker)
    if signal_only:
        _log("signal", "Signal-only mode: running ETFHoldingsSignal without a portfolio...")
        signal_result = _run_signal_only(
            etf_ticker=etf_ticker,
            provider=provider,
            fund_url=fund_url,
            timeout=timeout,
        )
        summary["signal"] = signal_result
        signal_uid = signal_result["signal_uid"]
    else:
        _log(
            "portfolio",
            f"Publishing the ETF-tracking portfolio pipeline ({calendar_key} trading "
            f"calendar attached by FK; {backtest_start_days}-day backtest window)...",
        )
        publish_result = publish_etf_tracking_portfolio(
            etf_ticker=etf_ticker,
            provider=provider,
            fund_url=fund_url,
            price_source_table_uid=price_source_table_uid,
            price_source_instance=demo_bars_node,
            # Updater scope for the signal's preflight get_asset_list() — already
            # resolved in steps 3/4, so publish does not re-extract.
            asset_identifiers=sorted(existing.values()),
            # US ETF => persisted US trading calendar (Calendar row + sessions
            # from pandas_market_calendars) drives the rebalance schedule and is
            # attached to the Portfolio row (calendar_uid FK).
            calendar_key=calendar_key,
            # Backtest: the signal's first observation is backdated this many
            # days, so the portfolio values the window [now - N, now] instead of
            # starting at the publish time.
            backtest_start_days=backtest_start_days,
            timeout=timeout,
            run=True,
        )
        summary["portfolio_publish"] = publish_result
        signal_uid = publish_result["signal_uid"]

    # 7. Verify on-platform state instead of trusting return values.
    _log("verify", "Reading back platform rows...")
    summary["verification"] = _verify_platform_rows(
        portfolio_identifier=portfolio_identifier,
        signal_uid=signal_uid,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an ms-markets portfolio that tracks an ETF (default IVV).",
    )
    parser.add_argument("--ticker", default="IVV", help="ETF ticker (default IVV).")
    parser.add_argument("--provider", default="ishares", help="Provider (default ishares).")
    parser.add_argument("--fund-url", help="Fund URL alternative to --provider.")
    parser.add_argument(
        "--price-source-table-uid",
        help=(
            "Optional registered bars TimeIndexMetaTable uid with close+volume "
            "(defaults to the ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID environment "
            "variable). When omitted, the example is self-sufficient: it prepares the "
            "project-owned DemoBarsTS schema (Alembic revision + upgrade) and publishes "
            "deterministic demo bars as the price source."
        ),
    )
    parser.add_argument(
        "--skip-schema-prep",
        action="store_true",
        help=(
            "Skip DemoBarsTS schema preparation. Use only when the table has already "
            "been migrated and registered."
        ),
    )
    parser.add_argument(
        "--revision-message",
        help="Optional Alembic revision message for the DemoBarsTS schema step.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Extract and resolve only; no platform writes.",
    )
    parser.add_argument(
        "--signal-only",
        action="store_true",
        help="Run the holdings signal node without building the portfolio.",
    )
    parser.add_argument(
        "--with-category-sync",
        action="store_true",
        help="Also sync the HOLDINGS__<ETF> asset category.",
    )
    parser.add_argument(
        "--no-register-missing",
        action="store_true",
        help=(
            "Do NOT FIGI-register missing components (default registers them; needs the "
            "OPEN_FIGI_API_KEY secret; only unique ticker-to-FIGI mappings register)."
        ),
    )
    parser.add_argument(
        "--figi-filter",
        dest="figi_filters",
        action="append",
        metavar="JSON",
        help=(
            "Per-ticker OpenFIGI disambiguation filter as JSON; repeat per ticker. "
            'Narrow: \'{"ticker": "USO", "exch_code": "US"}\'; alias a provider ticker '
            'to its OpenFIGI symbol: \'{"ticker": "BRKB", "figi_ticker": "BRK/B"}\'.'
        ),
    )
    parser.add_argument(
        "--calendar-key",
        default=US_EQUITY_CALENDAR_KEY,
        help=(
            "Trading calendar for the portfolio (default NYSE for US ETFs). Persisted "
            "as ms-markets Calendar/CalendarSession rows from pandas_market_calendars "
            "and attached to the Portfolio row by FK."
        ),
    )
    parser.add_argument(
        "--backtest-start-days",
        type=int,
        default=60,
        help=(
            "Backdate the signal's first observation this many days so the portfolio "
            "backtests that window (default 60; 0 starts at the provider as-of date)."
        ),
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds.")
    args = parser.parse_args(argv)

    summary = run_full_workflow(
        etf_ticker=args.ticker,
        provider=args.provider,
        fund_url=args.fund_url,
        price_source_table_uid=args.price_source_table_uid,
        prepare_schema=not args.skip_schema_prep,
        revision_message=args.revision_message,
        plan_only=args.plan_only,
        signal_only=args.signal_only,
        with_category_sync=args.with_category_sync,
        register_missing_assets=not args.no_register_missing,
        figi_disambiguation_filters=(
            [json.loads(raw) for raw in args.figi_filters] if args.figi_filters else None
        ),
        calendar_key=args.calendar_key,
        backtest_start_days=args.backtest_start_days,
        timeout=args.timeout,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 1 if summary.get("blocked") else 0


if __name__ == "__main__":
    sys.exit(main())
