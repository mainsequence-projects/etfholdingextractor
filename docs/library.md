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
  __main__.py                 # python -m etfhextractor -> CLI
  _version.py
  artifacts.py                # debug evidence persistence (data/temp/)
  asset_registration.py       # FIGI-only smart asset registration (ADR 0004)
  cli/                        # etfh subcommands + legacy etfh-read parser
  exceptions.py
  mainsequence_categories.py  # snapshot-layer resolution + category sync (msm)
  markets_models.py           # project-owned ms-markets tables (extension convention)
  models.py                   # FundHoldings / Holding
  portfolio_publish.py        # calendar + Portfolio row + PortfoliosDataNode wiring
  portfolio_signal.py         # ETFHoldingsSignal (custom SignalWeights) + session-grid stamps
  providers/                  # provider-specific extraction code
  reader.py                   # ETFHoldingsReader
  settings.py                 # provider normalization and input rules
etfhextractor_migrations/     # SDK migration provider for the project-owned tables
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
    publish_etf_tracking_portfolio, ensure_trading_calendar,
    build_etf_tracker_unique_identifier, start_portfolio_engine,
    US_EQUITY_CALENDAR_KEY, PRICE_SOURCE_TABLE_UID_ENV,
)
from etfhextractor.portfolio_signal import (
    ETFHoldingsSignal, ETFHoldingsSignalConfig, previous_session_close,
    ALWAYS_OPEN_CALENDAR_KEYS, VALIDITY_HEADROOM_DAYS,
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

`etfh-read <url>` still works as the legacy extraction entrypoint
(`python -m etfhextractor --provider <p> --ticker <t>` is its module form).

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

- `ETFHoldingsSignal` is a custom `msm_portfolios` `SignalWeights` DataNode whose update
  re-extracts the ETF holdings (same `ETFHoldingsReader`, component filter, and snapshot-layer
  ticker resolution as category sync) and emits `(time_index, asset_identifier) → signal_weight`.
  Two guards protect the canonical signal table: insertions happen at most once per
  `min_update_interval_days` (default daily), and only when the weights actually changed.
- `publish_etf_tracking_portfolio(...)` (convenience wiring around ms-markets) connects the
  signal plus the CALLER's valuation source (`APIDataNode.build_from_table_uid`; pass the uid or set
  `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID`) into msm's `PortfoliosDataNode` as
  `PortfolioBuildConfiguration.valuation_source_instance`, resolving portfolio
  identity through the `Portfolio` row alone — its `unique_identifier` keys all portfolio storage; `PortfolioIndex` is only an optional published-index reference (`Portfolio.published_index_uid`, ms-markets >= 0.0.54) and is never created or relied on here. CLI: `etfh portfolio-publish`.
- **Signal identity is definition-scoped** (ticker/source/normalization/validity — see
  [ADR 0005](adr/0005-tracking-signal-identity-is-definition-scoped.md)):
  `ETFHoldingsSignalConfig.asset_list` is updater scope for the 0.0.54 preflight
  `get_asset_list()` requirement and is neutralized in the `signal_uid` payload, so composition
  changes never rotate the series. Signal descriptions are plain text.
- ms-markets >= 0.0.54 pinnings handled by `publish_etf_tracking_portfolio`: portfolio identity
  set on both resolution paths (`target_portfolio` + `_explicit_portfolio_identifier`), and the
  resolved component identifiers always supplied as the signal's preflight scope.
- **Trading calendar — an ms-markets contract the wiring honors**
  ([ADR 0006](adr/0006-trading-calendar-and-backtest-bootstrap.md)):
  ms-markets >= 0.0.58 requires every Portfolio row to reference a persisted Calendar
  (`calendar_uid` NOT NULL FK, `ondelete=RESTRICT`; the legacy `calendar_name` field is gone).
  `calendar_key` defaults to `NYSE` for US ETFs. `ensure_trading_calendar()` persists it through
  the msm util `Calendar.create_from_pandas_calendar` (Calendar + CalendarDate/CalendarSession
  rows generated from pandas_market_calendars) and reuses a covering row with zero writes;
  always-open keys ("24/7") persist an always-open Calendar row for the FK. Portfolio valuations
  therefore land on real session closes — never weekends/holidays.
- **Session-grid observations + backtest bootstrap** (ADR 0006): every signal observation is
  stamped on a `calendar_key` market close (as-of date => that day's close; provider lag =>
  latest completed close; one observation per session) — never at insertion wall-clock times.
  `backtest_start_days` (default 60) stamps the first observation on the close at/before
  `now - 60d` so the first run backtests that window; later runs never backdate. The validator
  enforces `signal_validity_days >= backtest_start_days + 5` headroom (defaults 90/60), and
  numerically unchanged weights are re-stamped before validity expires so stable compositions
  never starve the portfolio forward-fill. Knobs on the CLI: `--calendar-key`,
  `--backtest-start-days`, `--signal-validity-days`.
- These modules are not imported by `etfhextractor.__init__`, so pure extraction never loads
  the portfolio stack.

## FIGI Asset Registration (ADR 0004)

`etfhextractor/asset_registration.py` registers missing ETF components through OpenFIGI, under two
hard identity rules: **no FIGI → no registration** (`Asset.unique_identifier` is always the FIGI;
ticker-keyed assets are forbidden), and **a ticker must map to exactly one FIGI** — multiple
candidates stay unregistered blockers so same-ticker assets are never mixed.
`register_equity_assets_from_tickers(...)` resolves smartly — always: batched `query_figi`
(ticker→FIGI), then **one batch search** of all mapped FIGIs against the asset registry and one
against the snapshot table, then writes **only the deltas** (`Asset.upsert(unique_identifier=figi)`
+ `OpenFigiDetails.upsert` for missing FIGIs; one `AssetSnapshot` run for FIGIs lacking a
snapshot). A fully-registered universe re-runs with zero writes. Registered identity is the US
composite FIGI (e.g. MSFT → `BBG000BPH459`); ticker/share-class/venue live on `OpenFigiDetails`. Failures name the blocked tickers with their FIGI candidates
(`format_failures()` / `FigiRegistrationError`), and ambiguity is resolved explicitly with
per-ticker disambiguation filters, e.g.
`disambiguation_filters=[{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}]`
(CLI: repeatable `--figi-filter '<json>'`). Opt-in via `etfh category-sync --register-missing` /
`etfh portfolio-publish --register-missing`; requires the `OPEN_FIGI_API_KEY` secret.

## Project-Owned ms-markets Tables (Extension Rules)

This project owns exactly **one** ms-markets MetaTable, defined in
`etfhextractor/markets_models.py` per the extension convention below:

- `DemoBarsStorage` — logical id `etfhextractor.DemoBarsTS`, physical table
  `etfhextractor_markets__demobarsts`. Demo `close`/`volume` bars keyed by
  `(time_index, asset_identifier)` with the canonical FK to `AssetTable.unique_identifier`,
  published by the example's default self-sufficient mode (no external price table given)
  through the thin `DemoBars` (`AssetTimestampedDataNode`) node — bars land on the NYSE session
  closes — so the ETF-tracking portfolio can run end-to-end without an external market-data feed. It must be migrated/registered by the SDK migration provider before
  writes, like any other table.

Its migrations are owned by the project's SDK migration provider
**`etfhextractor_migrations:migration`** — generated with `mainsequence migrations scaffold`
(`build_alembic_version_metatable` + `build_metatable_migration_provider`, target metadata scoped
to the project tables only so autogenerate never diffs the built-in ms-markets graph). Create and
apply revisions through the SDK CLI exactly like ms-markets does:

```bash
python -m mainsequence migrations revision --provider etfhextractor_migrations:migration --autogenerate -m demo_bars
python -m mainsequence migrations upgrade  --provider etfhextractor_migrations:migration head
```

`examples/prepare_demo_bars_schema.py` wraps that find-or-generate → upgrade → verify flow (the
full workflow runs it automatically on the default self-sufficient run; skip with
`--skip-schema-prep`).

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
- Register/migrate through the SDK migration provider, then attach at runtime with
  `msm.start_engine(models=[MyDetailsTable, MyBarsStorage])` (backend classes, not strings or
  typed rows).
- For tests/examples only, set `MSM_AUTO_REGISTER_NAMESPACE` before importing the models; it
  overrides the mixin namespace without source changes.

## Agent Capabilities (coding-agent setup)

The repository is agent-ready per `.agents/skills/mainsequence/project_to_agent/SKILL.md`
(implementation task 0004): `AGENTS.md` carries the canonical agent description and skill
routing, the three project skills (`weights_extraction`, `holdings_category_sync`,
`etf_holdings_signal`) map 1:1 to the CLI surface, and `.agents/agent_card.json` lists exactly
those skills. There is no agent runtime in this repo — capabilities are served through the
existing CLI/library surfaces.

Maintenance rules (enforced by `tests/test_agent_capabilities.py`):

- bumping the `pyproject.toml` version requires the same bump in `.agents/agent_card.json`
  and in the README version badge;
- adding or renaming a CLI command requires a matching project skill and agent-card entry, and
  skills may only reference real `etfh` subcommands (or `etfh-read`);
- skill tags stay empty until explicitly confirmed;
- `.agents/skills/mainsequence/**` and `.agents/skills/ms_markets/**` are platform-vendored:
  never edited here and never listed in the agent card.

## Internal Modules

These are implementation details, not separate product responsibilities:

- `providers/`: provider-specific extraction code
- `artifacts.py`: local debug evidence persistence
- `settings.py`: provider normalization and input rules

## Non-Goals

This library does not own:

- **market prices or any pricing capability** — the portfolio's price source is always supplied
  by the caller (a registered bars table or their own DataNode); the project-owned `DemoBarsTS`
  holds deterministic synthetic values for the runnable example only and doubles as the
  extension template for whoever builds their own price table
- broad asset-master ownership (it registers **ETF component equities via FIGI only**, opt-in —
  ADR 0004; no other registration workflows)
- broker or tradability checks
- execution workflows
- general downstream orchestration
