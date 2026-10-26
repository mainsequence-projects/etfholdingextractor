# Library Scope

This library does three things, layered so each builds on the previous one:

1. extract ETF holdings weights from supported providers
2. register or refresh MainSequence `HOLDINGS__<ETF>` asset categories from those holdings
   (FIGI-registering missing components on demand — ADR 0004)
3. provide an **ETF-holdings tracking signal** (`ETFHoldingsSignal`, a custom
   `msm_portfolios` `SignalWeights`) for the ms-markets portfolio pipeline
   (ADRs 0003 / 0005 / 0006) — portfolio assembly itself is ms-markets functionality,
   demonstrated end-to-end in the example

Everything else in the package exists only to support those responsibilities.

## Layout

```text
etfhextractor/
  __init__.py                 # public exports (extraction + categories + FIGI registration)
  __main__.py                 # python -m etfhextractor -> etfh
  _version.py
  artifacts.py                # debug evidence persistence (data/temp/)
  asset_registration.py       # FIGI-only smart asset registration (ADR 0004)
  calendars.py                # persisted trading calendars (registry row calls only)
  cli/                        # etfh subcommands
  exceptions.py
  mainsequence_categories.py  # snapshot-layer resolution + category sync (msm)
  markets_models.py           # project-owned ms-markets tables (extension convention)
  markets_runtime.py          # reads the application's ms-markets row backend (ADR 0047)
  models.py                   # FundHoldings / Holding
  portfolio_publish.py        # Portfolio row + PortfoliosUpdater wiring + instance seams
  portfolio_signal.py         # ETFHoldingsSignal (custom SignalWeights) + session-grid stamps
  providers/                  # provider-specific extraction code
  reader.py                   # ETFHoldingsReader
  settings.py                 # provider normalization and input rules
etfhextractor_migrations/     # MetaTables migration provider for the project-owned tables
```

## Public API

```python
from etfhextractor import (
    # extraction
    ETFHoldingsReader, FundHoldings, Holding, SUPPORTED_PROVIDERS,
    extract_ticker_weights, extract_many_ticker_weights, extract_ticker_weights_for_ticker,
    # holdings -> components (shared by categories and the signal)
    derive_component_weights_from_holdings, derive_component_symbols_from_holdings,
    infer_holdings_component_provider,
    # snapshot-layer resolution
    resolve_asset_identifiers_by_ticker, resolve_existing_assets_by_ticker,
    # category sync
    HOLDINGS_ASSET_CATEGORY_PREFIX, HoldingsAssetCategoryPlan, AssetCategorySyncResult,
    build_holdings_asset_category_plan, build_holdings_asset_category_unique_identifier,
    sync_holdings_asset_category,
    # FIGI registration (ADR 0004)
    FigiAssetRegistrationResult, FigiRegistrationError, register_equity_assets_from_tickers,
    # exceptions
    ETFHoldingsError, FetchError, DownloadLinkNotFoundError, WorkbookParseError,
    UnsupportedProviderError,
)
```

The **portfolio surface is deliberately not exported from `__init__`** (pure extraction never
imports the msm_portfolios stack); import it explicitly:

```python
from etfhextractor.portfolio_publish import (
    EtfTrackingPortfolioBuild, build_etf_tracking_portfolio,
    publish_etf_tracking_portfolio, ensure_trading_calendar,
    build_etf_tracker_unique_identifier, start_portfolio_engine, portfolio_runtime_models,
    register_portfolio_datasets, register_signal_dataset,
    US_EQUITY_CALENDAR_KEY, PRICE_SOURCE_TABLE_UID_ENV,
)
from etfhextractor.portfolio_signal import (
    ETFHoldingsSignal, ETFHoldingsSignalConfig, previous_session_close,
    ALWAYS_OPEN_CALENDAR_KEYS, VALIDITY_HEADROOM_DAYS,
)
```

The calendar helpers also live in the light `etfhextractor.calendars` module, which imports
neither the msm_portfolios stack nor ms-markets at import time; `portfolio_publish` re-exports
them:

```python
from etfhextractor.calendars import (
    ensure_trading_calendar, required_calendar_window,
    US_EQUITY_CALENDAR_KEY, ALWAYS_OPEN_CALENDAR_KEYS,
    CALENDAR_PAST_BUFFER_DAYS, CALENDAR_FUTURE_HORIZON_DAYS,
)
```

## CLI Commands

One command path per surface (`etfh --help` for the live reference; `--compact` prints compact
JSON, `--timeout` sets the HTTP timeout on every command):

- **Extraction from URL** — `etfh extract-url <fund-url> [...] [--format weights|full]`
- **Extraction from ticker + provider** —
  `etfh extract-ticker --provider <provider> --ticker <ticker> [--ticker ...] [--format weights|full]`
- **Category sync** —
  `etfh category-sync --ticker <etf> (--fund-url <url> | --provider <provider>)
  [--register-missing] [--figi-filter '<json>' ...]`
  `--register-missing` FIGI-registers unresolved components first (re-plans with the cached
  holdings, no re-extraction); repeatable `--figi-filter` narrows OpenFIGI per ticker or aliases
  a provider ticker (`'{"ticker": "BRKB", "figi_ticker": "BRK/B"}'`).
- **Portfolio publish** —
  `etfh portfolio-publish --ticker <etf> (--fund-url <url> | --provider <provider>)`
  with:
  - `--price-source-table-uid <uid>` — registered bars table with `close`+`volume`
    (default: `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID`)
  - `--portfolio-name <name>` — display name (default `ETF Tracker <TICKER>`)
  - `--calendar-key <key>` — trading calendar (default `NYSE`); persisted via the msm util and
    attached to the Portfolio row by FK
  - `--backtest-start-days <n>` — first-observation backtest window (default `60`; `0` disables)
  - `--signal-validity-days <n>` — forward-fill validity (default `90`; must exceed the backtest
    window by ≥ 5 days of headroom)
  - `--min-update-interval-days <f>` — signal insert throttle (default `1.0`)
  - `--register-missing` / `--figi-filter '<json>'` — as in category-sync
  - `--no-run` — wire and register without running the data nodes

`python -m etfhextractor` is the module form of `etfh`.

### CLI Response Examples

```bash
etfh extract-url https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf
```

```json
{
  "AAPL": 7.12,
  "MSFT": 6.84,
  "NVDA": 6.21
}
```

```bash
etfh extract-ticker --provider ishares --ticker IVV
```

```json
{
  "AAPL": 7.12,
  "MSFT": 6.84,
  "NVDA": 6.21
}
```

```bash
etfh category-sync --ticker IVV --fund-url https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf
```

```json
{
  "plan": {
    "category_unique_identifier": "HOLDINGS__IVV",
    "component_symbols": ["AAPL", "MSFT"],
    "existing_asset_uids_by_symbol": {
      "AAPL": "0f2f3f7a-6e1c-4b62-9a51-3f4d2f9b1c10",
      "MSFT": "7c9e2d44-8b1a-4f3e-bb02-91d34e7a55fe"
    },
    "missing_registered_symbols": [],
    "ambiguous_registered_symbols": [],
    "has_blockers": false
  },
  "synced": true,
  "sync_result": {
    "unique_identifier": "HOLDINGS__IVV",
    "display_name": "HOLDINGS__IVV",
    "asset_uids": ["0f2f3f7a-6e1c-4b62-9a51-3f4d2f9b1c10", "7c9e2d44-8b1a-4f3e-bb02-91d34e7a55fe"]
  }
}
```

### Extraction Examples

```python
from etfhextractor import ETFHoldingsReader, extract_ticker_weights

reader = ETFHoldingsReader()
fund = reader.read("https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf")
print(fund.fund_name)
print(fund.ticker_weights())
```

```json
{
  "fund_name": "iShares Core S&P 500 ETF",
  "url": "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf",
  "ticker_weights": {
    "AAPL": 7.12,
    "MSFT": 6.84,
    "NVDA": 6.21
  }
}
```

```python
from etfhextractor import extract_ticker_weights

weights = extract_ticker_weights("https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf")
print(weights["AAPL"])
```

```json
{
  "AAPL": 7.12,
  "MSFT": 6.84,
  "NVDA": 6.21
}
```

```python
from etfhextractor import extract_many_ticker_weights

weights_by_url = extract_many_ticker_weights(
    [
        "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf",
        "https://provider.example.com/etf-fund-page",
    ]
)
```

```json
{
  "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf": {
    "AAPL": 7.12,
    "MSFT": 6.84,
    "NVDA": 6.21
  },
  "https://provider.example.com/etf-fund-page": {
    "AAPL": 1.14,
    "MSFT": 0.98
  }
}
```

```python
from etfhextractor import extract_ticker_weights_for_ticker

weights = extract_ticker_weights_for_ticker("IVV", provider="ishares")
```

```json
{
  "AAPL": 7.12,
  "MSFT": 6.84,
  "NVDA": 6.21
}
```

### Category Registration Examples

```python
from etfhextractor import (
    build_holdings_asset_category_plan,
    sync_holdings_asset_category,
)

plan = build_holdings_asset_category_plan(
    etf_ticker="IVV",
    fund_url="https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf",
)
print(plan.category_unique_identifier)
print(plan.component_symbols)
print(plan.existing_asset_uids_by_symbol)
print(plan.missing_registered_symbols)
print(plan.ambiguous_registered_symbols)

if not plan.has_blockers():
    sync_result = sync_holdings_asset_category(
        etf_ticker="IVV",
        asset_uids=list(plan.existing_asset_uids_by_symbol.values()),
    )
    print(sync_result.asset_uids)
```

```json
{
  "unique_identifier": "HOLDINGS__IVV",
  "display_name": "HOLDINGS__IVV",
  "asset_uids": ["0f2f3f7a-6e1c-4b62-9a51-3f4d2f9b1c10", "7c9e2d44-8b1a-4f3e-bb02-91d34e7a55fe"]
}
```

```python
from etfhextractor import build_holdings_asset_category_plan

plan = build_holdings_asset_category_plan(
    etf_ticker="IVV",
    component_provider="ishares",
    fund_url="https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf",
)

if plan.has_blockers():
    # category sync should be delayed until symbols are registered
    print("blockers", plan.missing_registered_symbols, plan.ambiguous_registered_symbols)
```

```json
{
  "category_unique_identifier": "HOLDINGS__IVV",
  "component_symbols": ["AAPL", "MSFT", "NVDA"],
  "existing_asset_uids_by_symbol": {
    "AAPL": "0f2f3f7a-6e1c-4b62-9a51-3f4d2f9b1c10",
    "MSFT": "7c9e2d44-8b1a-4f3e-bb02-91d34e7a55fe"
  },
  "missing_registered_symbols": ["NVDA"],
  "ambiguous_registered_symbols": []
}
```

Core data model:

- `FundHoldings`: authoritative extracted fund metadata plus holdings rows
- `Holding`: one parsed holding row

## ETF Holdings Tracking Signal (msm_portfolios)

**The library's product at this layer is the SIGNAL.** `etfhextractor/portfolio_signal.py`
defines `ETFHoldingsSignal`; portfolios, calendars, `Portfolio` rows, and prices are ms-markets
(`msm_portfolios`) concerns. `etfhextractor/portfolio_publish.py` and `etfh portfolio-publish`
are **convenience wiring** that assemble those ms-markets objects around the signal — the same
assembly the example demonstrates — not a library capability claim (implementation task 0002,
ADR 0003):

- `ETFHoldingsSignal` is a custom `msm_portfolios` `SignalWeights` TimeIndexTableUpdater whose update
  re-extracts the ETF holdings (same `ETFHoldingsReader`, component filter, and snapshot-layer
  ticker resolution as category sync) and emits `(time_index, asset_identifier) → signal_weight`.
  Two guards protect the canonical signal table: insertions happen at most once per
  `min_update_interval_days` (default daily), and only when the weights actually changed.
- `build_etf_tracking_portfolio(...)` (reusable convenience wiring around ms-markets) connects the
  signal plus the CALLER's valuation source (`TimeIndexTableRef.from_uid`; pass the uid or set
  `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID`) into msm's `PortfoliosUpdater` as
  `PortfolioBuildConfiguration.valuation_source_instance`, resolving portfolio
  identity through the `Portfolio` row alone. It returns `EtfTrackingPortfolioBuild`, exposing the
  calendar, signal, portfolio row, configuration, node, valuation source, and run result to project
  integrations. Callers may supply their own `portfolio_unique_identifier`, valuation column, and
  frontend labels without rebuilding the graph. `publish_etf_tracking_portfolio(...)` wraps the
  same builder and returns the stable JSON-friendly summary used by CLI `etfh portfolio-publish`.
  `PortfolioIndex` remains only an optional published-index reference
  (`Portfolio.published_index_uid`) and is never created or relied on here.
- **Signal identity is definition-scoped** (ticker/source/normalization/validity — see
  [ADR 0005](adr/0005-tracking-signal-identity-is-definition-scoped.md)):
  `ETFHoldingsSignalConfig.asset_list` is updater scope for the 0.0.54 preflight
  `get_asset_list()` requirement and is neutralized in the `signal_uid` payload, so composition
  changes never rotate the series. Signal descriptions are plain text.
- ms-markets 1.x/2.x contracts handled by the reusable builder: portfolio identity
  set on both resolution paths (`target_portfolio` + `_explicit_portfolio_identifier`), the
  resolved component identifiers always supplied as the signal's preflight scope, and
  `ImmediateSignal()` built without a calendar key (ms-markets >= 1.0.7 rebalance strategies take
  none). Updaters run with a bare `run()`: SDK 8.1 removed the `debug_mode`/`force_update`
  controls, and every run executes immediately in-process.
- **Trading calendar — an ms-markets contract the wiring honors**
  ([ADR 0006](adr/0006-trading-calendar-and-backtest-bootstrap.md)):
  ms-markets 1.x and 2.x require every Portfolio row to reference a persisted Calendar
  (`calendar_uid` NOT NULL FK, `ondelete=RESTRICT`; the legacy `calendar_name` field is gone).
  `calendar_key` defaults to `NYSE` for US ETFs. `ensure_trading_calendar()`
  (`etfhextractor.calendars`) persists it through the msm util
  `Calendar.create_from_pandas_calendar` (Calendar + CalendarDate/CalendarSession rows generated
  from pandas_market_calendars) and reuses a covering row with zero writes; always-open keys
  ("24/7") persist an always-open Calendar row for the FK, with its dates and sessions written by
  one `CalendarDate.upsert_many` and one `CalendarSession.upsert_many`. Since ms-markets
  1.0.6 the portfolio executes on the signal's observations and values on the valuation source's
  observations, so with a session-close price source (the example's demo bars) valuations land
  on real session closes — never weekends/holidays.
- **Session-grid observations + backtest bootstrap** (ADR 0006): every signal observation is
  stamped on a `calendar_key` market close (as-of date => that day's close; provider lag =>
  latest completed close; one observation per session) — never at insertion wall-clock times.
  `backtest_start_days` (default 60) stamps the first observation on the close at/before
  `now - 60d` so the first run backtests that window; later runs never backdate. The validator
  enforces `signal_validity_days >= backtest_start_days + 5` headroom (defaults 90/60), and
  numerically unchanged weights are re-stamped before validity expires so stable compositions
  never starve the portfolio forward-fill (ms-markets 2.x no longer bounds that forward-fill by
  the signal validity; the guard is unchanged — see the ADR 0006 amendment). Knobs on the CLI:
  `--calendar-key`, `--backtest-start-days`, `--signal-validity-days`.
- These modules are not imported by `etfhextractor.__init__`, so pure extraction never loads
  the portfolio stack.

## FIGI Asset Registration (ADR 0004)

`etfhextractor/asset_registration.py` registers missing ETF components through OpenFIGI, under two
hard identity rules: **no FIGI → no registration** (`Asset.unique_identifier` is always the FIGI;
ticker-keyed assets are forbidden), and **a ticker must map to exactly one FIGI** — multiple
candidates stay unregistered blockers so same-ticker assets are never mixed.
`register_equity_assets_from_tickers(...)` resolves smartly — always: batched `query_figi`
(ticker→FIGI), then **one batch lookup** of all mapped FIGIs in the asset registry
(`Asset.get_many_by_unique_identifier`) and one read of their latest snapshots
(`AssetSnapshots.latest(asset_identifiers=...)`), then writes **only
the deltas**, set-based (one `Asset.upsert_many` of `unique_identifier=figi` and one
`OpenFigiDetails.upsert_many` for the missing FIGIs; one `AssetSnapshots.publish` for the FIGIs
lacking a snapshot). A fully-registered universe re-runs with zero writes. Registered identity is the US
composite FIGI (e.g. MSFT → `BBG000BPH459`); ticker/share-class/venue live on `OpenFigiDetails`. Failures name the blocked tickers with their FIGI candidates
(`format_failures()` / `FigiRegistrationError`), and ambiguity is resolved explicitly with
per-ticker disambiguation filters, e.g.
`disambiguation_filters=[{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}]`
(CLI: repeatable `--figi-filter '<json>'`). Opt-in via `etfh category-sync --register-missing` /
`etfh portfolio-publish --register-missing`; requires the `OPEN_FIGI_API_KEY` secret.

## Markets Access (ms-markets ADR 0047)

ms-markets 3.0 makes the Markets API the boundary between applications and the Markets
registries ([ms-markets ADR 0047](https://github.com/mainsequence-projects/MainSequenceMarkets)).
This package is a library, so it **never chooses** how it reaches Markets: the application that
imports it selects the ms-markets row backend once, at its composition root, and every
`msm.api` row call the library makes follows that choice (`etfhextractor.markets_runtime` only
reads it):

```python
from msm.api.remote import use_remote_backend
from msm.client import LazyRemoteBackend

use_remote_backend(LazyRemoteBackend())   # or MSM_API_BACKEND=remote, which also covers `etfh`
```

- **Runtime backend** (the ms-markets default): row calls compile SQL against Markets tables
  attached in the process, as in earlier releases. The library attaches the same tables as before
  (`_ensure_msm_started`, `start_portfolio_engine`).
- **Remote backend**: every registry read and write below is one call to the Markets API, and the
  library attaches no registry table. The application needs no grant on `mainsequence.markets`
  for these calls.

| Library call | Markets row calls | Write-policy resources |
|---|---|---|
| `resolve_existing_assets_by_ticker`, `resolve_asset_identifiers_by_ticker`, `build_holdings_asset_category_plan` | `AssetSnapshots.latest(tickers=...)` (each asset that ever carried a ticker, with its latest snapshot; kept when that ticker still matches) | none (reads) |
| `sync_holdings_asset_category` | `AssetCategory.upsert`, `AssetCategory.replace_memberships` | `asset-category` |
| `register_equity_assets_from_tickers` | `Asset.get_many_by_unique_identifier`, `AssetType.upsert`, `Asset.upsert_many`, `OpenFigiDetails.upsert_many`, `AssetSnapshots.latest(asset_identifiers=...)`, `AssetSnapshots.publish` | `asset-type`, `asset`, `open-figi-details`, `asset-snapshots` |
| `ensure_trading_calendar` | `Calendar.filter`; `Calendar.create_from_pandas_calendar`, or for always-open keys `Calendar.upsert`, `CalendarDate.upsert_many`, `CalendarSession.upsert_many` | `calendar`, `calendar-date`, `calendar-session` |
| `build_etf_tracking_portfolio`, `publish_etf_tracking_portfolio` | the calendar and (with `register_missing`) registration calls, `Portfolio.upsert` (the row and, after a run, its pointers), `SignalMetadata.upsert` (by the signal updater), `PortfolioDatasets.register` or, for a signal-only instance, `PortfolioDatasets.register_signal` when registering | `portfolio`, `signal-metadata`, `portfolio-datasets`, plus those of the calls it makes |

An application that runs these calls on the remote backend needs:

1. `access.branches: [{repository: MainSequenceMarkets, policy: reader}]` on every workflow
   resource that makes them, so `LazyRemoteBackend` can discover the Markets API (`api` release)
   in its Environment (`MARKETS_API_URL` points a local run at a local API);
2. its workload User uid listed in the Environment's `MARKETS_REGISTRY_WRITERS` constant under
   each write-policy resource of the calls it makes; otherwise the write raises
   `msm.api.remote.MarketsAccessError` (a `PermissionError`, HTTP 403);
3. an Environment whose Markets deployment runs ms-markets 3.0.0 and has applied its revisions.

### Direct Markets access that remains

No module compiles SQL on a Markets table; `tests/test_markets_api_boundary.py` guards it.
What still uses MetaTables on a Markets table:

- **Portfolio time series by default.** Unless the seams below bind them elsewhere, the signal
  weights, portfolio weights, rebalance state and portfolio values are written to the core
  ms-markets tables with MetaTables, which needs write access to those tables.
- `BatchVerifiedAssetSnapshot` (`markets_models.py`) writes the Markets snapshot table directly.
  The library no longer uses it; it is kept unchanged for callers that import it.

### Moving the series to your own instances

`build_etf_tracking_portfolio` (and `publish_etf_tracking_portfolio`) take injection seams;
every default keeps the earlier behaviour:

| Argument | Effect |
|---|---|
| `signal_output_table` | `ETFHoldingsSignal` writes and reads its history in this `SignalWeightsTS` instance |
| `portfolio_output_table`, `weights_output_table`, `rebalance_output_table` | `PortfoliosUpdater(output_table=, weights_output_table=, rebalance_output_table=)` |
| `register_datasets` | after the run: `PortfolioDatasets.register` with `portfolio_output_table` (reconciling when it ran; it binds the signal instance too), else `PortfolioDatasets.register_signal` for a `signal_output_table` alone (only after a run, which writes the signal's `SignalMetadata` row); default: whenever one of those tables is given |
| `update_pointers` | `False` leaves the Portfolio row's table-update pointers alone |
| `resolve_asset_identifiers_fn` | replaces the snapshot ticker resolver in the preflight and in the signal (`ETFHoldingsSignal.set_asset_identifier_resolver`) |

`portfolio_runtime_models(...)` and `start_portfolio_engine(...)` take the same output tables:
on the remote backend an instance replaces the core table it stands for, on the runtime backend
the instances join the usual set. Output tables never enter `update_hash` or `signal_uid`; MetaTables keys each update
record by update hash and output table, so a bound updater gets its own record.

The library owns no instances (it has no deployment), so the application moves a portfolio:

1. Declare the instances in its own namespace with the ms-markets factories in
   `msm_portfolios.time_index.contract_instances` (`configured_signal_weights_storage`,
   `configured_portfolios_storage`, `configured_portfolio_weights_storage`,
   `configured_portfolio_rebalance_state_storage`; `instance_key`, `namespace`, `storage_app`,
   `base`), add them to its own migration provider in a new revision, and let its deployment's
   migration Job create them.
2. Grant the Markets workload `data_viewer` on the four instance tables: catalog registration
   verifies them and Markets reads values and weights from them.
3. Pause the portfolio's scheduled runs.
4. **Backfill by copying, before the first bound run.** Copy the signal's rows (its
   `signal_uid`) from the core `SignalWeightsTS`, and the portfolio's rows (its
   `portfolio_identifier`) from the core `PortfoliosTS`, `PortfolioWeightsTS` and
   `PortfolioRebalanceStateTS`, into the instances. Never recompute: ETF holdings are extracted
   as of today and cannot be re-extracted for past dates. A fresh signal instance keeps the
   `signal_uid` but has no rows, so `ETFHoldingsSignal` would treat its first bound run as a
   first run (a backdated bootstrap observation with today's composition) and the portfolio
   history would be lost. Check that the copied row counts and time bounds match the source.
5. Attach the instances (include `portfolio_runtime_models(...)` with the output tables in the
   application's one `start_engine` call) and publish with the four output tables and
   `start_engine=False`. With `portfolio_output_table` the build registers the instances in the
   Markets catalog after the run; `build.portfolio_datasets` (and the summary's
   `portfolio_datasets`) shows the reconciled state, which should be `populated`. A signal moved
   on its own (core portfolio tables, or no portfolio) is bound with
   `PortfolioDatasets.register_signal` after its first bound run (`build.signal_dataset`, or
   `register_signal_dataset(signal_uid=..., signal_output_table=...)` after a signal-only run).
6. Resume the scheduled runs. Readers get values and weights through the Markets API
   (`msm.client.MarketsClient.portfolio_values` / `portfolio_weights`). Markets never deletes
   rows in a table another application owns; leave the core rows in place until the move is
   verified.

### ms-markets 3.0 identities

- `ETFHoldingsSignal` and `PortfoliosUpdater` hash through ms-markets classes whose modules moved
  in 3.0 (`msm_portfolios.time_index`), so, per the ms-markets upgrade guide, their first run on
  3.0 creates a new `TimeIndexTableUpdate` that continues from the output table's last
  observation. `DemoBars` keeps its hash (it has its own configuration class; same guide).
- `signal_uid` does not change: the default IVV/ishares uid still computes offline to
  `495a8b180d0a216e563cd3f83316da7f` (`tests/test_portfolio_signal.py` pins it).

## Project-Owned ms-markets Tables (Extension Rules)

This project owns exactly **one** ms-markets MetaTable, defined in
`etfhextractor/markets_models.py` per the extension convention below:

- `DemoBarsStorage` — logical id `etfhextractor.DemoBarsTS`, physical table
  `etfhextractor_markets__demobarsts`. Demo `close`/`volume` bars keyed by
  `(time_index, asset_identifier)` with the canonical FK to `AssetTable.unique_identifier`,
  published by the example's default self-sufficient mode (no external price table given)
  through the thin `DemoBars` (`AssetTimestampedUpdater`/`TimeIndexTableUpdater`) updater — bars land on the NYSE session
  closes — so the ETF-tracking portfolio can run end-to-end without an external market-data feed. It must be migrated/registered by the project's MetaTables migration provider before
  writes, like any other table.

Its migrations are owned by the project's MetaTables migration provider
**`etfhextractor_migrations:migration`** — originally scaffolded with the SDK 8
`mainsequence migrations scaffold`, now built with `metatables.migrations`
(`build_alembic_version_metatable` + `build_metatable_migration_provider`, target metadata scoped
to the project tables only so autogenerate never diffs the built-in ms-markets graph). The SDK 9
move kept its package, namespace, version table (`etfhextractor_markets__alembic_version`) and
revisions. The provider passes explicit `script_location="etfhextractor_migrations:"` and
`version_location_prefix="etfhextractor_migrations:versions"`, so it never resolves another
distribution's top-level `migrations` package.

### Who applies the provider

Since MetaTables 0.1.14 a hosted runtime is migrated only from a deployment workflow
(implementation task [0007](implementation_task/0007-deployment-job-migrations.md)):

- **Hosted environments.** The migration Job of a deployment workflow runs
  `metatables.upgrade_application(...)` for each provider the deployed application needs, from
  the candidate image, before anything that uses the tables rolls out. etfholdingextractor has
  **no deployment** (no `.mainsequence/workflows/` file, no migration Job), so the application
  that deploys code reading or writing `DemoBarsTS` applies `etfhextractor_migrations:migration`
  in its own migration Job. That Job does not apply the ms-markets provider: the ms-markets
  deployment migrates the ms-markets schema, which `DemoBarsTS` references by foreign key.
  Nobody runs a hosted upgrade or downgrade by hand.

  This package requires `mainsequence-metatable` 0.1.35 (0.1.34 in 0.4.4), the client a consumer's
  migration Job then runs. Before that consumer pushes:
  - the Environment's hosted MetaTables API must run 0.1.32 or later. Since 0.1.32 the client
    sends changed table and column descriptions and labels with finalization
    (`authored_metadata`), even at an unchanged revision, and an older API rejects the field.
    MetaTables runs 0.1.34 in Production and development (checked 2026-10-11);
  - the migration Job declares `access.branches: [{repository: MetaTables, level: view}]`, without
    which it cannot discover the MetaTables API;
  - one Team per Environment owns the provider's tables (MetaTables 0.1.27): it has Writer on the
    `etfhextractor` namespace, where both `DemoBarsTS` and the version table are registered, and
    its members are the migration Job's workload User and the workload User of every resource
    that reads or writes `DemoBarsTS`. Without it the Job fails with `403`
    `namespace_not_writable` or `table_not_editable`. A namespace registered before its Team
    existed may list only a retired workload User as Writer; an Organization admin grants the
    Team Writer on it.

  The 0.1.19 prerequisite of 0.4.3 is gone: MetaTables 0.1.21 made the client ignore
  runtime-context fields it does not know, so either side can be upgraded first
  ([MetaTables#33](https://github.com/mainsequence-projects/MetaTables/issues/33)).
- **Local development.** Use the laptop's local MetaTables runtime (local SQLite) through the
  `metatables` CLI installed by `mainsequence-metatable`:

  ```bash
  metatables init --local
  metatables serve --local                # another terminal; needs `mainsequence login`
  metatables --local runtime initialize   # once per new local runtime
  metatables --local migrations revision --provider etfhextractor_migrations:migration -m <change>
  metatables --local migrations upgrade  --provider etfhextractor_migrations:migration head
  metatables --local migrations current  --provider etfhextractor_migrations:migration
  ```

  A laptop runs one local MetaTables API, shared by every checkout. `serve --local` reports an
  API that is already running, from this project or any other, and exits; the `--local`
  commands and `metatables.configure_local_client()` connect to it through `server.json` in the
  local storage directory. Commits and branch switches need no API restart. The local API always
  runs Local; hosted data is reached through the deployed API, never by switching the local one.

  The local runtime must already hold the ms-markets tables: finalization preflights every
  foreign-key target, so MetaTables finalizes `DemoBarsTS` only when the ms-markets Asset table is
  an active MetaTable in the same runtime. Since ms-markets 2.2.2 (which needs
  `mainsequence-metatable` 0.1.17 or later) that schema applies to a fresh local runtime; the
  [ms-markets getting-started guide](https://mainsequence-projects.github.io/MainSequenceMarkets/getting-started/#first-market-setup)
  shows how. This package never applies the ms-markets provider.

  With ms-markets 2.2.10 (not re-checked on 3.0.0) a local SQLite runtime cannot yet run the
  asset-writing workflows end to end: inserting Asset rows, keeping `HOLDINGS__<ETF>` memberships and the final portfolio
  pointer update fail there, because of ms-markets defects in its SQLite path. Migrations, demo
  bars, the signal, portfolio values and weights work. Implementation task
  [0007](implementation_task/0007-deployment-job-migrations.md) ("Local end-to-end run on
  0.4.4") has the details.
- **Never at start-up.** The library, the `etfh` CLI and the examples never migrate on import or
  start-up; runtime code only attaches with `msm.start_engine(models=[...])`, and on the
  ms-markets remote backend it attaches no Markets registry (see "Markets Access").
- **Backward-compatible revisions.** Applied revisions are immutable: never edit a revision ID or
  `down_revision`, and add a new revision for every change. The previous release keeps serving
  while a deploying application's Job migrates, so add tables and nullable or defaulted columns
  first and drop or rename in a later release. Raw PostgreSQL SQL must branch on
  `op.get_bind().dialect.name` so the revision also runs on local SQLite; revision `0001` uses
  portable DDL only.

`examples/prepare_demo_bars_schema.py` wraps the local flow (`--local`: find-or-generate →
`metatables --local migrations upgrade` → verify) and only verifies a hosted runtime. The full
workflow runs it on the default self-sufficient run; skip it with `--skip-schema-prep`.

Everything else goes through built-in `msm` / `msm_portfolios` models (the holdings signal uses
the canonical `SignalWeightsStorage`, dimensioned by `signal_uid`). Built-in tables are used
as-is; never set or override `__markets_storage_app__` on them.

Every project-owned table must follow the ms-markets extension convention —
one local abstract mixin reused by every project table:

```python
from msm.base import MarketsBase, MarketsMetaTableMixin, MarketsTimeIndexMetaTableMixin


class EtfhExtractorMarketsMetaTableMixin(MarketsMetaTableMixin):
    __abstract__ = True
    __metatable_namespace__ = "etfhextractor"
    __markets_storage_app__ = "etfhextractor_markets"


class EtfhExtractorMarketsStorageMixin(MarketsTimeIndexMetaTableMixin):
    __abstract__ = True
    __metatable_namespace__ = "etfhextractor"
    __markets_storage_app__ = "etfhextractor_markets"


class MyDetailsTable(EtfhExtractorMarketsMetaTableMixin, MarketsBase):
    __markets_base_identifier__ = "MyDetails"
    __metatable_description__ = "..."


class MyBarsStorage(EtfhExtractorMarketsStorageMixin, MarketsBase):
    __markets_base_identifier__ = "MyBarsTS"
    __metatable_description__ = "..."
    __time_index_name__ = "time_index"
    __index_names__ = ["time_index", "asset_identifier"]
```

Rules:

- The stable logical identifier is `etfhextractor.<__markets_base_identifier__>`.
  Do **not** use table names as identity, do **not** build UID maps, do **not** call row
  `create_schemas()`.
- Register/migrate through the project's MetaTables migration provider (locally
  `metatables --local migrations upgrade --provider etfhextractor_migrations:migration`; on hosted
  runtimes the deploying application's migration Job), then attach at runtime with
  `msm.start_engine(models=[MyDetailsTable, MyBarsStorage])` (backend classes, not strings or
  typed rows).
- Give each foreign key the `ondelete` action its rows need. MetaTables 0.1.17 and later accept
  `CASCADE`, `SET NULL` and `SET DEFAULT` as well as `RESTRICT`, and since 0.1.18 write on a table
  depends only on that table's own grants. `DemoBarsTS` keeps `ondelete="RESTRICT"` on its asset
  key, as ms-markets' own asset-keyed time-series tables do. Before deleting or re-keying
  referenced rows, `table.get_impact(action="delete_rows")` (or `update_keys`, `drop_table`)
  shows what the action reaches.
- For tests/examples only, set `MSM_AUTO_REGISTER_NAMESPACE` before importing the models; it
  overrides the mixin namespace without source changes.

## Agent Capabilities (coding-agent setup)

The repository is agent-ready per the platform-owned code-repository-to-agent skill
(implementation task 0004): `AGENTS.md` carries the canonical agent description and skill
routing, the three project skills (`weights_extraction`, `holdings_category_sync`,
`etf_holdings_signal`) map 1:1 to the CLI surface, and `.agents/agent_card.json` lists exactly
those skills. There is no agent runtime in this repo — capabilities are served through the
existing CLI/library surfaces.

Maintenance rules (enforced by `tests/test_agent_capabilities.py`):

- bumping the `pyproject.toml` version requires the same bump in `.agents/agent_card.json`
  and in the README version badge;
- adding or renaming a CLI command requires a matching project skill and agent-card entry, and
  skills may only reference real `etfh` subcommands;
- skill tags stay empty until explicitly confirmed;
- `.agents/skills/mainsequence/**`, `.agents/skills/mainsequence_platform/**` (present only
  after the authenticated `mainsequence code-repository update-platform-skills`),
  `.agents/skills/metatables/**` and `.agents/skills/ms_markets/**` are vendored by their
  owners' copy commands: never edited here (apart from the package-relative `skills_path` in each
  `PINNED_FROM.txt`) and never listed in the agent card.

## Internal Modules

These are implementation details, not separate product responsibilities:

- `providers/`: provider-specific extraction code
- `artifacts.py`: local debug evidence persistence
- `settings.py`: provider normalization and input rules

## Non-Goals

This library does not own:

- **market prices or any pricing capability** — the portfolio's price source is always supplied
  by the caller (a registered bars table or their own TimeIndexTableUpdater); the project-owned `DemoBarsTS`
  holds deterministic synthetic values for the runnable example only and doubles as the
  extension template for whoever builds their own price table
- broad asset-master ownership (it registers **ETF component equities via FIGI only**, opt-in —
  ADR 0004; no other registration workflows)
- broker or tradability checks
- execution workflows
- general downstream orchestration
