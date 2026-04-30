# Architecture

This library has two responsibilities only:

1. extract ETF holdings weights from supported providers
2. register or refresh MainSequence holdings categories from already-registered assets

Everything else is support code for those two flows.

## Authoritative Model

`FundHoldings` is the authoritative model.

All provider adapters must normalize into:

- fund metadata
- holdings rows
- weights
- source provenance

Derived outputs such as `ticker -> weight` maps or component-symbol lists are downstream views of
`FundHoldings`.

## Responsibility 1: Weight Extraction

### Public surface

- `reader.py`
- `ETFHoldingsReader`
- `extract_ticker_weights(...)`
- `extract_many_ticker_weights(...)`
- `extract_ticker_weights_for_ticker(...)`

### Internal support code

- `providers/registry.py`: resolve provider implementations
- `providers/*.py`: provider-specific fetch and parse logic
- `providers/common.py`: shared parsing utilities
- `settings.py`: provider normalization and input rules
- `artifacts.py`: local debug evidence persistence

### Input rules

1. If the caller provides `provider`, use it.
2. If `provider` is omitted and a fund URL is available, infer the provider from the URL.
3. If the caller only provides a ticker, `provider` is required.

## Responsibility 2: Category Registration

### Public surface

- `mainsequence_categories.py`
- `build_holdings_asset_category_plan(...)`
- `sync_holdings_asset_category(...)`

### Behavior

This layer:

- derives component symbols from `FundHoldings`
- resolves existing MainSequence assets by ticker
- builds `HOLDINGS__<ETF>` category membership
- syncs category membership for already-registered assets

This layer does not redefine ETF holdings truth. It consumes extracted holdings.

## Support Features

These are intentionally secondary:

- artifact persistence under `data/temp/` for debugging extraction
- optional browser-backed fallback helpers behind a non-core dependency boundary

They support the two main responsibilities. They are not separate product scope.

## Non-Goals

This library does not own:

- asset registration
- FIGI resolution
- broker or tradability checks
- execution workflows
- broad orchestration beyond extraction and category registration
