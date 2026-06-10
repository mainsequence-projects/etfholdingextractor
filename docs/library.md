# Library Scope

This library does two things only:

1. extract ETF holdings weights from supported providers
2. register or refresh MainSequence holdings categories from already-registered assets

Everything else in the package exists only to support those two responsibilities.

## Layout

```text
etfhextractor/
  __init__.py
  __main__.py
  _version.py
  artifacts.py
  exceptions.py
  mainsequence_categories.py
  models.py
  providers/
  reader.py
  settings.py
```

## Public API

```python
from etfhextractor import (
    ETFHoldingsReader,
    FundHoldings,
    Holding,
    build_holdings_asset_category_plan,
    extract_ticker_weights,
    sync_holdings_asset_category,
)
```

The package exposes two public surfaces:

- Extraction:
  `ETFHoldingsReader`, `extract_ticker_weights(...)`, `extract_many_ticker_weights(...)`, `extract_ticker_weights_for_ticker(...)`
- Category registration:
  `build_holdings_asset_category_plan(...)`, `sync_holdings_asset_category(...)`

## CLI Commands

The CLI now exposes one command path per surface:

- Extraction from URL:
  `etfh extract-url <fund-url> [<fund-url> ...]`
- Extraction from ticker plus provider:
  `etfh extract-ticker --provider <provider> --ticker <ticker> [--ticker <ticker> ...]`
- Category sync:
  `etfh category-sync --ticker <etf-ticker> --fund-url <fund-url>`

`etfh-read` still works as the legacy extraction entrypoint. `etfh` is the broader CLI surface.

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
    "existing_asset_ids_by_symbol": {"AAPL": 101, "MSFT": 102},
    "missing_registered_symbols": [],
    "ambiguous_registered_symbols": [],
    "has_blockers": false
  },
  "synced": true,
  "sync_result": {
    "unique_identifier": "HOLDINGS__IVV",
    "display_name": "HOLDINGS__IVV",
    "asset_ids": [101, 102]
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
print(plan.existing_asset_ids_by_symbol)
print(plan.missing_registered_symbols)
print(plan.ambiguous_registered_symbols)

if not plan.has_blockers():
    sync_result = sync_holdings_asset_category(
        etf_ticker="IVV",
        asset_ids=list(plan.existing_asset_ids_by_symbol.values()),
    )
    print(sync_result.asset_ids)
```

```json
{
  "category_unique_identifier": "HOLDINGS__IVV",
  "display_name": "HOLDINGS__IVV",
  "asset_ids": [101, 102]
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
  "existing_asset_ids_by_symbol": {"AAPL": 101, "MSFT": 102},
  "missing_registered_symbols": ["NVDA"],
  "ambiguous_registered_symbols": []
}
```

Core data model:

- `FundHoldings`: authoritative extracted fund metadata plus holdings rows
- `Holding`: one parsed holding row

## ETF-Tracking Portfolio (msm_portfolios)

`etfhextractor/portfolio_signal.py` and `etfhextractor/portfolio_publish.py` publish an
ms-markets portfolio that tracks an ETF (implementation task 0002, ADR 0003):

- `ETFHoldingsSignal` is a custom `msm_portfolios` `SignalWeights` DataNode whose update
  re-extracts the ETF holdings (same `ETFHoldingsReader`, component filter, and snapshot-layer
  ticker resolution as category sync) and emits `(time_index, asset_identifier) → signal_weight`.
  Two guards protect the canonical signal table: insertions happen at most once per
  `min_update_interval_days` (default daily), and only when the weights actually changed.
- `publish_etf_tracking_portfolio(...)` wires the signal plus an explicit registered
  price-source table (`APIDataNode.build_from_table_uid`; pass the uid or set
  `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID`) into `PortfoliosDataNode`, resolving portfolio
  identity through the `Portfolio` row alone — its `unique_identifier` keys all portfolio storage; `PortfolioIndex` is only an optional published-index reference (`Portfolio.published_index_uid`, ms-markets >= 0.0.54) and is never created or relied on here. CLI: `etfh portfolio-publish`.
- These modules are not imported by `etfhextractor.__init__`, so pure extraction never loads
  the portfolio stack.

## FIGI Asset Registration (ADR 0004)

`etfhextractor/asset_registration.py` registers missing ETF components through OpenFIGI, under two
hard identity rules: **no FIGI → no registration** (`Asset.unique_identifier` is always the FIGI;
ticker-keyed assets are forbidden), and **a ticker must map to exactly one FIGI** — multiple
candidates stay unregistered blockers so same-ticker assets are never mixed.
`register_equity_assets_from_tickers(...)` runs `query_figi` → `Asset.upsert(unique_identifier=figi)`
+ `OpenFigiDetails.upsert` + one `AssetSnapshot` publication (so the snapshot resolver finds the new
assets immediately). Failures name the blocked tickers with their FIGI candidates
(`format_failures()` / `FigiRegistrationError`), and ambiguity is resolved explicitly with
per-ticker disambiguation filters, e.g.
`disambiguation_filters=[{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}]`
(CLI: repeatable `--figi-filter '<json>'`). Opt-in via `etfh category-sync --register-missing` /
`etfh portfolio-publish --register-missing`; requires the `OPEN_FIGI_API_KEY` secret.

## Project-Owned ms-markets Tables (Extension Rules)

This project owns exactly **one** ms-markets MetaTable, defined in
`etfhextractor/markets_models.py` per the extension convention below:

- `DemoBarsStorage` — logical id `com.mainsequence.etfhextractor.DemoBarsTS`, physical table
  `etfhextractor_markets__demobarsts`. Demo `close`/`volume` bars keyed by
  `(time_index, asset_identifier)` with the canonical FK to `AssetTable.unique_identifier`,
  published by the example's `--demo-prices` mode through the thin `DemoBars`
  (`AssetTimestampedDataNode`) node so the ETF-tracking portfolio can run end-to-end without an
  external market-data feed. It must be migrated/registered by the SDK migration provider before
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
full workflow runs it automatically under `--demo-prices`).

Everything else goes through built-in `msm` / `msm_portfolios` models (the holdings signal uses
the canonical `SignalWeightsStorage`, dimensioned by `signal_uid`). Built-in tables are used
as-is; never set or override `__markets_storage_app__` on them.

Every project-owned table must follow the ms-markets extension convention —
one local abstract mixin reused by every project table:

```python
from msm.base import MarketsBase, MarketsMetaTableMixin, MarketsTimeIndexMetaTableMixin


class EtfhExtractorMarketsMetaTableMixin(MarketsMetaTableMixin):
    __abstract__ = True
    __metatable_namespace__ = "com.mainsequence.etfhextractor"
    __markets_storage_app__ = "etfhextractor_markets"


class EtfhExtractorMarketsStorageMixin(MarketsTimeIndexMetaTableMixin):
    __abstract__ = True
    __metatable_namespace__ = "com.mainsequence.etfhextractor"
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

- The stable logical identifier is `com.mainsequence.etfhextractor.<__markets_base_identifier__>`.
  Do **not** use table names as identity, do **not** build UID maps, do **not** call row
  `create_schemas()`.
- Register/migrate through the SDK migration provider, then attach at runtime with
  `msm.start_engine(models=[MyDetailsTable, MyBarsStorage])` (backend classes, not strings or
  typed rows).
- For tests/examples only, set `MSM_AUTO_REGISTER_NAMESPACE` before importing the models; it
  overrides the mixin namespace without source changes.

## Internal Modules

These are implementation details, not separate product responsibilities:

- `providers/`: provider-specific extraction code
- `artifacts.py`: local debug evidence persistence
- `settings.py`: provider normalization and input rules

## Non-Goals

This library does not own:

- broad asset-master ownership (it registers **ETF component equities via FIGI only**, opt-in —
  ADR 0004; no other registration workflows)
- broker or tradability checks
- execution workflows
- general downstream orchestration
