# etfhextractor

`etfhextractor` turns provider-published ETF holdings into Main Sequence / ms-markets state. It
has three capabilities, layered so each builds on the previous one:

1. **Extract** ETF holdings weights from supported providers (iShares, Invesco, State Street,
   Vanguard) into an authoritative `FundHoldings` model.
2. **Sync** a MainSequence `HOLDINGS__<ETF>` asset category from those holdings through the
   ms-markets snapshot layer, FIGI-registering missing components on demand (ADR 0004: no asset
   without a FIGI, one FIGI per ticker).
3. **Publish an ETF-tracking portfolio**: a custom `SignalWeights` node re-extracts the holdings
   (at most daily, only on change, observations stamped on trading-session closes) and feeds an
   `msm_portfolios.PortfoliosDataNode` with a persisted NYSE trading calendar attached to the
   `Portfolio` row by FK and a 60-day backtest bootstrap (ADRs 0003, 0005, 0006).

## Installation

The package is a normal wheel-installable distribution named `etfhextractor` (no src/ layout):

```bash
uv pip install etfhextractor            # from your index, or:
uv pip install -e .                     # working copy
```

Python >= 3.11. Key dependencies: `mainsequence` (SDK), `ms-markets >= 0.0.58` (typed MetaTable
rows; the obligatory-calendar portfolio architecture), `pandas-market-calendars` (trading
sessions). Capabilities 2 and 3 need an authenticated Main Sequence session
(`MAINSEQUENCE_ACCESS_TOKEN` / `MAINSEQUENCE_REFRESH_TOKEN`, e.g. via `.env`).

## CLI

One command path per capability (plus a legacy reader entry point):

```bash
# 1. Extraction — JSON ticker→weight (add --format full for fund metadata + rows)
etfh extract-url https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf
etfh extract-ticker --provider ishares --ticker IVV

# 2. Category sync — HOLDINGS__IVV from the extracted components
etfh category-sync --ticker IVV --provider ishares \
    --register-missing \
    --figi-filter '{"ticker": "BRKB", "figi_ticker": "BRK/B"}'

# 3. ETF-tracking portfolio — signal + portfolio pipeline against a registered bars table
etfh portfolio-publish --ticker IVV --provider ishares \
    --price-source-table-uid <TimeIndexMetaTable-uid> \
    --register-missing

# Legacy reader (URL → weights JSON)
etfh-read https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf
```

`portfolio-publish` defaults: NYSE calendar (`--calendar-key`), 60-day backtest window
(`--backtest-start-days`), 90-day signal validity (`--signal-validity-days`), daily update
throttle (`--min-update-interval-days`). The full flag reference lives in
[docs/library.md](docs/library.md).

## Python

```python
from etfhextractor import ETFHoldingsReader, build_holdings_asset_category_plan

fund = ETFHoldingsReader().read_ticker("IVV", provider="ishares")
print(fund.fund_name, fund.as_of_date)
print(fund.ticker_weights())
```

The portfolio surface is intentionally **not** exported from `etfhextractor.__init__` (pure
extraction never imports the msm_portfolios stack):

```python
from etfhextractor.portfolio_publish import publish_etf_tracking_portfolio

result = publish_etf_tracking_portfolio(
    etf_ticker="IVV",
    provider="ishares",
    price_source_table_uid="<uid>",   # or price_source_instance=<DataNode>
    register_missing=True,
)
```

## Environment

| variable | purpose |
|---|---|
| `MAINSEQUENCE_ACCESS_TOKEN` / `MAINSEQUENCE_REFRESH_TOKEN` | platform session (categories, portfolios) |
| `OPEN_FIGI_API_KEY` (Main Sequence secret) | FIGI registration (`--register-missing`) |
| `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID` | default price-source table for `portfolio-publish` |
| `MSM_AUTO_REGISTER_NAMESPACE` | tests/sandboxes only: override the `etfhextractor` table namespace |

## Documentation

- [Library guide](docs/library.md) — scope, layout, public API, full CLI reference, portfolio
  pipeline, FIGI rules, ms-markets extension convention (project-owned tables + migrations)
- [Reader guide](docs/reader.md) — extraction surface in detail
- [Examples](examples/README.md) — self-sufficient IVV tracking-portfolio workflow (demo bars on
  NYSE session closes, schema prep, verification)
- [ADRs](docs/adr/) — 0002 providers/categories split, 0003 weights live in ms-markets
  portfolios, 0004 FIGI-only registration, 0005 definition-scoped signal identity, 0006 trading
  calendar + session-grid observations + backtest bootstrap
- [Implementation tasks](docs/implementation_task/README.md) — decision logs for the ms-markets
  migration, the tracking portfolio, and FIGI registration
