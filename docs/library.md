# Library Scope

This library does two things only:

1. extract ETF holdings weights from supported providers
2. register or refresh MainSequence holdings categories from already-registered assets

Everything else in the package exists only to support those two responsibilities.

## Layout

```text
src/
  etfh_extractor/
    __init__.py
    __main__.py
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
from etfh_extractor import (
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
from etfh_extractor import ETFHoldingsReader, extract_ticker_weights

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
from etfh_extractor import extract_ticker_weights

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
from etfh_extractor import extract_many_ticker_weights

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
from etfh_extractor import extract_ticker_weights_for_ticker

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
from etfh_extractor import (
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
from etfh_extractor import build_holdings_asset_category_plan

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

## Internal Modules

These are implementation details, not separate product responsibilities:

- `providers/`: provider-specific extraction code
- `artifacts.py`: local debug evidence persistence
- `settings.py`: provider normalization and input rules

## Non-Goals

This library does not own:

- asset registration
- FIGI resolution
- broker or tradability checks
- execution workflows
- general downstream orchestration
