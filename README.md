# etfhextractor

[![Package](https://img.shields.io/badge/package-etfhextractor-black.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/version-0.4.1-blue.svg)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![ms-markets](https://img.shields.io/badge/ms--markets-%3E%3D1.0.2-black.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-85%20passing-green.svg)](tests/)
[![Maintained](https://img.shields.io/badge/maintained-actively-green.svg)](docs/)

`etfhextractor` turns provider-published ETF holdings into Main Sequence / ms-markets
state. It has three capabilities, layered so each builds on the previous one:

1. **Extract** ETF holdings weights from supported providers (iShares, Invesco, State Street,
   Vanguard) into an authoritative `FundHoldings` model.
2. **Sync** a MainSequence `HOLDINGS__<ETF>` asset category from those holdings through the
   ms-markets snapshot layer, FIGI-registering missing components on demand (ADR 0004: no asset
   without a FIGI, one FIGI per ticker).
3. **Provide an ETF-holdings tracking SIGNAL**: `ETFHoldingsSignal`, a custom
   `msm_portfolios` `SignalWeights` that re-extracts the holdings (at most daily, only on
   change, observations stamped on trading-session closes) under one definition-scoped
   `signal_uid` (ADRs 0003, 0005, 0006). Portfolio assembly — `Portfolio` rows, calendars,
   prices, `PortfoliosDataNode` — is **ms-markets functionality**; the repository demonstrates
   it end-to-end in the example, and `etfh portfolio-publish` is convenience wiring for that
   assembly (prices always supplied by the caller).

The Python distribution and import package are both named `etfhextractor`:

```python
import etfhextractor
```

The signal surface imports explicitly from `etfhextractor.portfolio_signal` (it is deliberately
kept out of `__init__` so pure extraction never loads the msm_portfolios stack).

## Project Status

- Current package version: `0.4.1`
- Python: `>=3.13,<3.14`
- Key dependencies: `mainsequence >= 8.0.7`, `ms-markets >= 1.0.2` (typed MetaTable rows;
  obligatory-calendar portfolio architecture), `pandas-market-calendars` (trading sessions)
- License: [Apache License 2.0](LICENSE)
- Documentation: [docs/library.md](docs/library.md) · [docs/reader.md](docs/reader.md) ·
  [examples/README.md](examples/README.md) · [docs/adr/](docs/adr/)
- Agent capabilities: coding-agent setup per `.agents/agent_card.json` (three CLI-aligned
  skills; parity-tested)

## Installation

```bash
uv pip install etfhextractor            # from your index, or:
uv pip install -e .                     # working copy
```

Capabilities 2 and 3 need an authenticated Main Sequence session
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

# 3. Tracking signal + ms-markets assembly wiring (caller-supplied bars table)
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

The signal (and the example-grade assembly wiring) is intentionally **not** exported from
`etfhextractor.__init__` (pure extraction never imports the msm_portfolios stack):

```python
from etfhextractor.portfolio_publish import publish_etf_tracking_portfolio

result = publish_etf_tracking_portfolio(
    etf_ticker="IVV",
    provider="ishares",
    price_source_table_uid="<uid>",   # or price_source_instance=<TimeIndexTableUpdater>
    register_missing=True,
)
```

Project integrations that need the assembled calendar, signal, Portfolio row, configuration,
valuation source, and `PortfoliosDataNode` can call `build_etf_tracking_portfolio(...)`; the
publisher above wraps that same builder and returns its JSON-friendly summary.

## Environment

| variable | purpose |
|---|---|
| `MAINSEQUENCE_ACCESS_TOKEN` / `MAINSEQUENCE_REFRESH_TOKEN` | platform session (categories, signal/portfolio runs) |
| `OPEN_FIGI_API_KEY` (Main Sequence secret) | FIGI registration (`--register-missing`) |
| `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID` | default price-source table for `portfolio-publish` |
| `MSM_AUTO_REGISTER_NAMESPACE` | tests/sandboxes only: override the `etfhextractor` table namespace |

## Documentation

- [Library guide](docs/library.md) — scope, layout, public API, full CLI reference, the
  tracking signal, FIGI rules, ms-markets extension convention (project-owned tables +
  migrations), agent capabilities
- [Reader guide](docs/reader.md) — extraction surface in detail
- [Examples](examples/README.md) — self-sufficient IVV tracking workflow (demo bars on NYSE
  session closes, schema prep, verification)
- [ADRs](docs/adr/) — 0002 providers/categories split, 0003 weights live in ms-markets
  portfolios, 0004 FIGI-only registration, 0005 definition-scoped signal identity, 0006 trading
  calendar + session-grid observations + backtest bootstrap

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
Copyright 2026 MainSequence GmbH.
