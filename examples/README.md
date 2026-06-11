# Examples

Runnable end-to-end workflows for `etfhextractor` against the Main Sequence / ms-markets
platform.

## ivv_tracking_portfolio_full_workflow.py

Creates an ms-markets **portfolio that tracks an ETF** (default `IVV`) through the
`msm_portfolios` signal pipeline (implementation task
[0002](../docs/implementation_task/0002-ms-markets-portfolio-weights.md), ADR
[0003](../docs/adr/0003-holdings-weights-live-in-ms-markets-portfolios.md)):

```text
extraction (FundHoldings) ──> ETFHoldingsSignal (custom SignalWeights)
                                      │ (time_index, asset_identifier) → signal_weight
registered bars table ── APIDataNode ─┴──> PortfoliosDataNode ──> ETF-tracking portfolio
```

The script is stepwise and honest about platform state: extract → resolve component
tickers through the asset-snapshot layer (blockers stop the run) → optional category
sync → signal/portfolio publication → read-back verification of the rows actually
written (`SignalWeightsTS`, `PortfoliosTS`, `PortfolioWeightsTS`, and the `Portfolio` row).

### Prerequisites

**Only two:** an authenticated Main Sequence session (`mainsequence project current
--debug`, refresh the token before live runs) and the built-in ms-markets MetaTables
registered by the SDK migration provider. Everything else is handled by the example
itself on the default run:

- **Missing component assets** are FIGI-registered automatically (ADR 0004: no asset
  without a FIGI, only unique ticker→FIGI mappings register; reads the
  `OPEN_FIGI_API_KEY` Main Sequence secret). Disable with `--no-register-missing`;
  resolve ambiguous tickers with `--figi-filter`.
- **The price source** defaults to the **project-owned** `DemoBarsTS` table
  (`etfhextractor/markets_models.py`, logical id
  `etfhextractor.DemoBarsTS`, ms-markets extension-mixin convention):
  the example prepares its schema the way the ms-markets examples do
  ([prepare_demo_bars_schema.py](prepare_demo_bars_schema.py) — find-or-generate the
  Alembic revision via the project provider `etfhextractor_migrations:migration`,
  `mainsequence migrations upgrade head`, verify the registered `TimeIndexMetaTable`)
  and publishes deterministic demo bars **on the NYSE session closes**
  (pandas_market_calendars), aligned with the portfolio's valuation index. Pass
  `--price-source-table-uid <UID>` (or set `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID`)
  to use a real registered bars table with `close` and `volume` instead. For isolated
  sandboxes set `MSM_AUTO_REGISTER_NAMESPACE` before running.
- **The trading calendar** ([ADR 0006](../docs/adr/0006-trading-calendar-and-backtest-bootstrap.md)):
  a US ETF follows the US trading calendar, so the example persists the **NYSE**
  calendar as ms-markets `Calendar`/`CalendarSession` rows (msm util
  `Calendar.create_from_pandas_calendar`) and attaches it to the `Portfolio` row by FK
  (`calendar_uid`). Portfolio values land on real session closes only — no weekend or
  holiday rows. Override with `--calendar-key`.
- **The backtest window**: the signal's first observation is stamped on the NYSE session
  close at/before `now - --backtest-start-days` (default 60), so the first run backtests
  `[now - 60d, now]` with the current composition before live tracking takes over. All signal
  observations live on session closes (as-of date => that day's close; at most one observation
  per session) — never at insertion wall-clock times (ADR 0006).

### Usage

```bash
# Everything, self-sufficient: FIGI-register missing components, prepare DemoBarsTS,
# publish demo bars, build + verify the IVV tracking portfolio.
python examples/ivv_tracking_portfolio_full_workflow.py

# No writes: extract IVV, resolve components, report blockers.
python examples/ivv_tracking_portfolio_full_workflow.py --plan-only

# Write only the signal weights (no price source involved).
python examples/ivv_tracking_portfolio_full_workflow.py --signal-only

# Use a real registered bars table instead of demo bars, and sync the category too.
python examples/ivv_tracking_portfolio_full_workflow.py \
    --price-source-table-uid <UID> --with-category-sync

# Disambiguate a ticker that maps to multiple FIGIs, or alias a provider ticker
# to its OpenFIGI symbol (share-class conventions). Repeat per ticker.
python examples/ivv_tracking_portfolio_full_workflow.py \
    --figi-filter '{"ticker": "BRKB", "figi_ticker": "BRK/B"}' \
    --figi-filter '{"ticker": "BFB", "figi_ticker": "BF/B"}'
```

The signal is guarded (task 0002): re-running inserts at most once per day, at most one
observation per session, and only when the extracted weights actually changed — except that
unchanged weights are re-stamped shortly before the `--signal-validity-days` forward-fill
window would expire, so a stable composition never starves the portfolio. The example is safe
to re-run.
