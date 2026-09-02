# Implementation Task: ETF-Tracking Portfolio via a Custom msm_portfolios Signal

- Status: Implemented (pending live validation; follow-up to [0001](0001-migrate-to-ms-markets.md))
- Decision basis: [ADR 0003](../adr/0003-holdings-weights-live-in-ms-markets-portfolios.md)
- Authoritative skill: `.agents/skills/ms_markets/portfolios/portfolio_workflow/SKILL.md`

## 1. Objective

Create an ms-markets **portfolio that tracks an ETF** by feeding the extracted holdings weights
through the `msm_portfolios` signal pipeline. The mechanism is a **custom signal**: a
`SignalWeights` subclass whose update pulls the ETF's `ticker → weight` from the extraction layer
and emits them as the signal frame. `PortfoliosDataNode` then turns that signal plus an explicit
price source into the portfolio series:

```text
extraction (FundHoldings) ──> ETFHoldingsSignal (custom SignalWeights)
                                       │ signal frame: (time_index, asset_identifier) → signal_weight
price source TimeIndexTableUpdater ──> optional InterpolatedPrices ──┐
                                       └──> PortfoliosDataNode ──> portfolio that tracks the ETF
```

No account or virtual-fund machinery is involved; this is purely the portfolio-construction
pipeline. Each new extraction run appends a fresh dated weights row-set under the same
`signal_uid`, so the portfolio follows the ETF's holdings over time.

## 2. The pipeline, grounded in the installed code (msm_portfolios 0.0.49)

All contracts below were read from `.venv/.../msm_portfolios` source.

### 2.1 Custom signal contract (`msm_portfolios/data_nodes/signals/weights.py`)

A custom signal subclasses `SignalWeights` and provides:

- **`signal_configuration`** — a Pydantic config (subclass `PortfolioConfigBaseModel` from
  `msm_portfolios.configuration`). It is hashed into the deterministic **`signal_uid`**
  (`compute_signal_uid`), so the same config always maps to the same signal identity. All signal
  subclasses share the one canonical `SignalWeightsStorage` table; rows are dimensioned by
  `signal_uid`.
- **`_calculate_signal_weights() -> pd.DataFrame`** — the only required computation. Returns a
  frame with MultiIndex `("time_index", "asset_identifier")` and column `signal_weight`. The base
  `update()` normalizes it (`normalize_signal_weights_frame`), stamps `signal_uid`, validates
  against storage, and upserts signal metadata.
- **`maximum_forward_fill() -> timedelta`** — how long a weights observation stays economically
  valid when the portfolio interpolates between rebalances (`interpolate_index` invalidates fills
  older than this).
- **`get_asset_list()`** — preflight/context only; the authoritative universe is the signal output
  frame.
- **`dependencies()`** — `{}` for an external-source signal (reference: `ExternalWeights`, which
  pulls a CSV from an `Artifact`; ours pulls from the provider extraction instead).

Reference implementations: `contrib/signals/fixed_weights.py` (static, write-once) and
`contrib/signals/external_weights.py` (external source, repeated updates filtered by
`update_statistics.filter_df_by_latest_value`). `ETFHoldingsSignal` is the external-source shape.

**Identity note:** the signal frame keys assets by **`asset_identifier` =
`Asset.unique_identifier`** (string), not by asset uid. (`ExternalWeights` maps FIGI →
`unique_identifier` for exactly this reason.)

### 2.2 Portfolio build contract (`msm_portfolios/configuration.py`)

```python
PortfolioConfiguration(
    portfolio_build_configuration=PortfolioBuildConfiguration(
        valuation_source_instance=<TimeIndexTableUpdater | TimeIndexTableRef>,  # explicit dependency
        valuation_column="close",
        price_alignment_policy=PriceAlignmentPolicy(...),
        portfolio_prices_frequency="1d",
        execution_configuration=PortfolioExecutionConfiguration(commission_fee=...),
        backtesting_weights_configuration=BacktestingWeightsConfig(
            signal_weights_instance=<ETFHoldingsSignal instance>,   # direct injection
            rebalance_strategy_instance=<ImmediateSignal instance>, # msm_portfolios.rebalance_strategy
        ),
    ),
    portfolio_markets_configuration=PortfolioMarketsConfig(
        portfolio_name="ETF Tracker <TICKER>",
        front_end_details=FrontEndDetails(description=...),
    ),
)
```

- Valuations come from an **explicit** `valuation_source_instance` (skill rule: persistent
  interpolation is prepared upstream — `msm_portfolios.contrib.prices.InterpolatedPrices` — and
  passed in; `PortfoliosDataNode` never constructs prices internally). A registered source-bars
  table can be attached through `TimeIndexTableRef.from_uid(...)`, and
  `valuation_column` selects the numeric column consumed for valuation.
- The rebalance strategy starting point is `ImmediateSignal`
  (`msm_portfolios/rebalance_strategy/immediate_signal.py`): signal weights become executed weights
  at each rebalance.
- `PortfoliosDataNode` (`msm_portfolios/data_nodes/portfolios/__init__.py`) exposes
  `dependencies()` = `{signal_weights, valuation_source}`, runs the canonical `PortfolioWeights` node,
  and writes the portfolio series; portfolio identity hashes via
  `compute_portfolio_configuration_hash`. Display metadata syncs through
  `msm_portfolios.api.PortfolioMetadata` / `msm_portfolios.services.market_metadata`, and the core
  `msm.api.portfolios.Portfolio` row carries `signal_weights_data_node_uid` /
  `portfolio_weights_data_node_uid` / `portfolio_data_node_uid` links.

### 2.3 Bootstrap (`msm_portfolios/bootstrap.py`)

`msm_portfolios.start_engine(...)` wraps `msm.start_engine` and injects the portfolio model graph
(`portfolio_sqlalchemy_models`): `SignalWeightsStorage`, `PortfolioWeightsStorage`,
`PortfoliosStorage`, `SignalMetadata`, `RebalanceStrategyMetadata`, `PortfolioMetadata`, plus the
core tables. Use it instead of plain `msm.start_engine` for this workflow (one call, one runtime).
The SDK migration provider must have registered these MetaTables first (same rule as task 0001).

## 3. Scope

**In scope**
- `etfhextractor.portfolio_signal` (new module): `ETFHoldingsSignalConfig` +
  `ETFHoldingsSignal(SignalWeights)` — the custom signal that updates weights from an extraction.
- Ticker → `asset_identifier` resolution reusing task 0001's snapshot layer (see W-1).
- A portfolio-publish entry point (library function + `etfh portfolio-publish` CLI) that wires the
  signal into `PortfoliosDataNode` per §2.2 and runs the pipeline.
- Weight normalization: provider weights are percents; emit fractions (`/100`) and renormalize over
  the included components so each observation sums to 1 (cash/non-equity rows are excluded by the
  same filter as task 0001's planner; config flag `renormalize_weights: bool = True`).
- Tests with the msm boundary mocked (no live runtime), mirroring task 0001's `MsmBoundaryTests`.

**Out of scope**
- Accounts, target positions, and virtual funds (account-side machinery — not part of portfolio
  construction; see the portfolio_workflow skill boundary).
- Changing the extraction surface (`reader.py`, `providers/*`, `models.py`).
- Asset registration / FIGI resolution (unchanged non-goals; unresolvable tickers are blockers).
- Price-source provisioning: registering/migrating source-bars tables and the contributed
  interpolation storage is platform setup, not this library (this task consumes an existing
  registered table UID).

## 4. Work items

- [x] **W-1. Expose the shared extraction/resolution machinery for reuse.**
  *(file: `etfhextractor/mainsequence_categories.py`)*
  The signal must reuse the category-creation machinery, so factor it for sharing:
  - `derive_component_weights_from_holdings(fund_holdings, *, allowed_asset_classes) ->
    dict[str, float]` — the existing component filter (probable-security + asset-class predicate),
    accumulating weights per normalized ticker; `derive_component_symbols_from_holdings` becomes
    its key-set view, so category planning and the signal share one filter.
  - `resolve_asset_identifiers_by_ticker(*, component_symbols) -> tuple[dict[str, str], list[str],
    list[str]]` (existing/missing/ambiguous, same latest-snapshot rule): the signal frame needs the
    **`asset_identifier`** (= `Asset.unique_identifier`), not the uid, so split the snapshot scan
    out of `resolve_existing_assets_by_ticker` and let the uid-level function build on it.
  - Make `_ensure_msm_started` reuse an already-started superset runtime (try
    `msm.bootstrap.resolve_runtime(models=[...])` before `start_engine`): the portfolio path boots
    the engine once via `msm_portfolios.start_engine` with a superset model list, and a process can
    only call `start_engine` with one schema config.
  Effort: S · non-breaking.

- [x] **W-2. `ETFHoldingsSignalConfig` + `ETFHoldingsSignal`.**
  *(new file: `etfhextractor/portfolio_signal.py`; the package `__init__` does not import it, so pure
  extraction never imports the portfolio stack)*
  - **Reuse rule: the signal reuses the extraction machinery built for category creation** — the
    same `ETFHoldingsReader`, the same component filter (shared with
    `derive_component_symbols_from_holdings`), and the same snapshot-layer ticker resolution (W-1).
    No duplicated extraction or resolution logic in the signal module.
  - Config (`PortfolioConfigBaseModel`): `etf_ticker`, `provider` (or `fund_url`),
    `allowed_asset_classes=("Equity",)`, `renormalize_weights=True`,
    `signal_validity_days` (drives `maximum_forward_fill`), `min_update_interval_days=1.0`
    (drives guard G-a). The config is the signal identity — one ETF tracker per config hash.
  - `_calculate_signal_weights()`:
    1. **Guard G-a (daily throttle):** read the last stored observation for this `signal_uid`
       (`get_df_between_dates(dimension_filters={SIGNAL_UID: [self.signal_uid]})`, max
       `time_index`). If the last insertion is younger than `min_update_interval_days`, return the
       empty canonical frame (no extraction, no insert) — the signal runs **at most once a day**.
    2. extract: `ETFHoldingsReader().read_ticker(etf_ticker, provider=...)` (or `read(fund_url)`)
       → `FundHoldings` — the same reader the category plan uses;
    3. derive component weights with the shared filter (W-1's
       `derive_component_weights_from_holdings`);
    4. resolve tickers → `asset_identifier` via W-1; **missing/ambiguous tickers fail the update**
       with an explicit error listing them (a tracker portfolio with silently dropped names would
       misrepresent the ETF — escalate instead);
    5. normalize weights to fractions, renormalize to sum 1 when configured;
    6. **Guard G-b (changed-weights only):** compare the new `asset_identifier → weight` map
       against the last stored observation (same key set, values within tolerance). If unchanged,
       return the empty frame — **identical weights are never re-inserted**;
    7. `time_index` = parsed `FundHoldings.as_of_date` (UTC); if that is not strictly newer than
       the last stored observation, use the extraction time instead (keeps the series monotonic
       when the provider's as-of lags a real weight change). Return the frame indexed
       `(time_index, asset_identifier)` with `signal_weight`, passed through
       `update_statistics.filter_df_by_latest_value(...)` like `ExternalWeights` as the final
       backstop against duplicate observations.
  - `maximum_forward_fill()` = `timedelta(days=signal_validity_days)` (holdings stay valid until
    the next extraction; default ~30d).
  - `get_asset_list()` → `None` (universe is signal-driven, per the VFB skill this must be an
    intentional choice — it is); `dependencies()` → `{}`; `get_explanation()` describes the ETF and
    source provider.
  Effort: M.

- [x] **W-3. Portfolio wiring + publish entry point.**
  *(new: `etfhextractor/portfolio_publish.py` or extend `portfolio_signal.py`; CLI subcommand
  `etfh portfolio-publish`)*
  - `publish_etf_tracking_portfolio(*, etf_ticker, provider=None, fund_url=None,
    price_source_table_uid, run=True)`:
    1. `msm_portfolios.start_engine()` (portfolio model graph; replaces/extends task 0001's
       `_ensure_msm_started` for this path);
    2. build the price dependency from the registered table UID
       (`PricesConfiguration(source_time_index_meta_table_uid=...)` →
       `InterpolatedPrices`/`TimeIndexTableRef` per the equal-weight example);
    3. assemble `PortfolioConfiguration` exactly as §2.2 with
       `signal_weights_instance=ETFHoldingsSignal.from_signal_configuration(config)` and
       `rebalance_strategy_instance=ImmediateSignal(...)`;
    4. construct `PortfoliosDataNode`, `run(debug_mode=True, force_update=True)`, surface
       `error_on_last_update` as a hard error;
    5. report the resulting identifiers (portfolio configuration hash, signal_uid, data-node UIDs,
       synced `PortfolioMetadata` / `Portfolio` row) in the JSON output (UUIDs via `default=str`).
  - `price_source_table_uid` comes from CLI flag or env (`ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID`);
    fail with a clear message when absent — never invent a price table.
  - Follow `examples/msm_portfolios/portfolio_equal_weights_run.py` (referenced by the skill) for
    the node-wiring details, including the schema-prep step for contributed interpolation storage.
  Effort: M/L.

- [x] **W-4. Tests.** *(extend `tests/test_reader.py` or new `tests/test_portfolio_signal.py`)*
  - Signal frame contract: given a mocked extraction + mocked identifier resolution, the emitted
    frame has MultiIndex `(time_index, asset_identifier)`, `signal_weight` fractions summing to 1,
    and excluded/cash rows dropped.
  - Missing/ambiguous tickers raise with the offending symbols listed.
  - Config → `signal_uid` determinism (same config twice → same uid via `compute_signal_uid`).
  - Publish wiring: with `PortfoliosDataNode`/`start_engine` mocked, the build configuration
    receives our signal instance, `ImmediateSignal`, and the explicit price source.
  Effort: M.

- [x] **W-5. Docs.** Update `docs/library.md` (new capability), `AGENTS.md` capability list, and
  the README map; note in ADR 0003 that the mechanism is the custom-signal pipeline. Effort: S.

## 5. Open questions (small, deployment-level — the mechanism itself is decided)

1. **Which registered source-bars table** (the `source_time_index_meta_table_uid`, e.g. an
   `alpaca_1d_bars`-style `MarketsTimeSeries`) exists in this org and covers US equities? Needed
   before the first live run; the code takes it as config.
2. **`signal_validity_days` default** — how stale may holdings be before the tracker should stop
   forward-filling (proposed 30d)?
3. **Re-extraction cadence** — manual CLI runs first; a scheduled job (platform orchestration
   skill) can be a later follow-up.

## 5.5 Live-validation findings (ms-markets 0.0.54) — all implemented

The first live runs surfaced four contracts that now shape the implementation:

1. **Preflight asset scope is mandatory on first runs.** `PortfoliosDataNode` derives the
   price-source update window from the signal's `get_asset_list()` when no previous weights
   exist. `ETFHoldingsSignalConfig.asset_list` carries the resolved component identifiers
   (supplied by the publish preflight or the `asset_identifiers` parameter); publish fails fast
   with a clear message if no scope can be resolved.
2. **Signal identity is definition-scoped** ([ADR 0005](../adr/0005-tracking-signal-identity-is-definition-scoped.md)):
   `asset_list` is updater scope and is neutralized in the `signal_uid` payload
   (`_signal_uid_payload`), so rebalances/composition changes never rotate the series, reset the
   insert guards, or churn the portfolio configuration hash. Pinned by a `compute_signal_uid`
   invariance test.
3. **Portfolio identity must be pinned on both paths.** `run()` resolves identity from
   `node.target_portfolio`, but `update()`'s values normalizer reads
   `_explicit_portfolio_identifier` and otherwise demands an external `portfolio_resolver`;
   publish sets both to the same `etf_tracker_<ticker>` identity so no resolver is needed.
4. **Request economy.** Registration resolves smartly (ADR 0004 rule 3) and snapshot publication
   uses `BatchVerifiedAssetSnapshot` (duplicate-key verification in ONE batched read — plain
   `AssetSnapshot` issues one read per row, ~503 sequential reads for an ETF universe).
   Registration logs progress through the platform logger: mapping counts, registry-check split
   (already registered / to create / snapshots to publish), per-chunk creation percentages, and
   snapshot-publication markers.

## 5.6 Trading calendar and backtest bootstrap ([ADR 0006](../adr/0006-trading-calendar-and-backtest-bootstrap.md))

The portfolio index is the calendar's session closes, so a US ETF must follow the US trading
calendar — the original `"24/7"` key valued the tracker at midnight UTC every day including
weekends/holidays, and the Portfolio row carried no calendar linkage:

1. **Persisted NYSE calendar (default).** `ensure_trading_calendar()` persists the calendar
   through the msm util `Calendar.create_from_pandas_calendar` (typed `Calendar` row +
   `CalendarDate`/`CalendarSession` rows from pandas_market_calendars) and reuses a covering row
   with zero writes; the rebalancer's `resolve_rebalance_calendar` resolves the same key into the
   persisted sessions (`PersistedCalendarSchedule`).
2. **Calendar attached by FK — and obligatory.** ms-markets >= 0.0.58 makes the calendar a
   hard requirement of the portfolio architecture: `PortfolioTable.calendar_uid` is a NOT NULL FK
   to `CalendarTable.uid` (`ondelete=RESTRICT`), the typed payloads require it, the legacy
   `calendar_name` field was removed, and `run()`'s pointer update refuses rows without it.
   `Portfolio.upsert(..., calendar_uid=calendar.uid)`; always-open keys ("24/7") persist an
   always-open Calendar row for the FK while the rebalancer keeps resolving them synthetically.
3. **60-day backtest window.** `backtest_start_days` (default 60) stamps the signal's first
   observation on the session close at/before `now - 60d`; runs with existing history never
   backdate. The config validator enforces `signal_validity_days >= backtest_start_days + 5`
   (defaults 90/60) because weights forward-fill at most `maximum_forward_fill()` past an
   observation and the portfolio index reaches one session past "now" — equality ships a
   pre-expired bootstrap. This resolves open question 2 (§5): validity defaults to 90d.
3b. **Observations on the session grid + refresh heartbeat (live-run findings).** Signal
   observations are stamped on `calendar_key` market closes — as-of date => that day's close,
   provider lag => latest completed close, one observation per session — never at insertion
   wall-clock times (a Saturday 20:43:12 stamp made validity arithmetic depend on the run's
   start minute). Guard (b) re-stamps numerically unchanged weights when the last observation
   approaches validity expiry, so stable compositions can never starve the portfolio's
   forward-fill.
4. **Example alignment.** Demo bars are published on the same NYSE session closes, so the price
   index and the valuation index match exactly; `--calendar-key` / `--backtest-start-days` are
   exposed on the CLI and the example.

## 6. Sequencing

1. W-1 (resolver refactor, non-breaking) → W-2 (signal) with W-4 tests → W-3 (publish wiring) →
   W-5 (docs).
2. First live validation: `mainsequence project current --debug`, refresh token, then
   `etfh portfolio-publish --ticker IVV --provider ishares --price-source-table-uid <UID>` against
   a real registered bars table, verifying the portfolio series and metadata appear on the
   platform.
