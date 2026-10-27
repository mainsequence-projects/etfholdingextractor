# etfhextractor

[![Package](https://img.shields.io/badge/package-etfhextractor-black.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![ms-markets](https://img.shields.io/badge/ms--markets-%3D%3D2.2.10-black.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-101%20passing-green.svg)](tests/)
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
   prices, `PortfoliosUpdater` — is **ms-markets functionality**; the repository demonstrates
   it end-to-end in the example, and `etfh portfolio-publish` is convenience wiring for that
   assembly (prices always supplied by the caller).

The Python distribution and import package are both named `etfhextractor`:

```python
import etfhextractor
```

The signal surface imports explicitly from `etfhextractor.portfolio_signal` (it is deliberately
kept out of `__init__` so pure extraction never loads the msm_portfolios stack).

## Project Status

- Current package version: `0.5.0` (unreleased)
- Python: `>=3.13,<3.14`
- Key dependencies: `mainsequence >=9.0.22,<10` (identity, secrets, logging),
  `mainsequence-metatable >=0.1.35,<0.2` (the MetaTables client, imported as `metatables`),
  `ms-markets ==3.0.0` (typed rows, on the Markets API when the application selects it;
  obligatory-calendar portfolio architecture; pinned to the release the deployed MainSequence
  Markets runs),
  `pandas-market-calendars` (trading sessions)
- License: [Apache License 2.0](LICENSE)
- Documentation: [docs/library.md](docs/library.md) · [docs/reader.md](docs/reader.md) ·
  [examples/README.md](examples/README.md) · [docs/adr/](docs/adr/) ·
  [CHANGELOG.md](CHANGELOG.md)
- Agent capabilities: coding-agent setup per `.agents/agent_card.json` (three CLI-aligned
  skills; parity-tested)

## Installation

```bash
uv pip install etfhextractor            # from your index, or:
uv pip install -e .                     # working copy
```

Capabilities 2 and 3 need an authenticated Main Sequence session. SDK 9 keeps it in the
operating-system credential store after `mainsequence login`; renew it with
`mainsequence refresh-token`. A CodeRepository `.env` holds no credentials.

## CLI

One command path per capability:

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
    --instances my_app.instances:portfolio_instances \
    --price-source-table-uid <TimeIndexMetaTable-uid> \
    --register-missing
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
    instances=my_portfolio_instances,  # your PortfolioSeriesTables (see below)
    provider="ishares",
    price_source_table_uid="<uid>",   # or price_source_instance=<TimeIndexTableUpdater>
    register_missing=True,
)
```

Project integrations that need the assembled calendar, signal, Portfolio row, configuration,
valuation source, and `PortfoliosUpdater` can call `build_etf_tracking_portfolio(...)`; the
publisher above wraps that same builder and returns its JSON-friendly summary.

### Markets access (ms-markets ADR 0047)

The library never chooses how it reaches MainSequence Markets; the application that imports it
does. With ms-markets' remote row backend selected
(`use_remote_backend(LazyRemoteBackend())`, or `MSM_API_BACKEND=remote`, which also covers
`etfh`), every Markets registry call the library makes (assets, OpenFIGI details, snapshots
publication, categories, calendars, portfolios, the portfolio catalog) runs on the Markets API,
and the application needs `reader` on the `MainSequenceMarkets` branch instead of grants on
`mainsequence.markets`. Ticker resolution reads the latest asset snapshots the same way.

The library never writes the Markets core portfolio tables: `build_etf_tracking_portfolio`,
`publish_etf_tracking_portfolio` and `etfh portfolio-publish` require `instances`, an
`msm_portfolios.services.series_moves.PortfolioSeriesTables` with the application's own
signal-weights, portfolio-weights, rebalance-state and portfolio-values instances (ms-markets
`contract_instances` factories, migrated by the application), and register them in the Markets
portfolio catalog after each build. `examples/example_instances.py` shows one. Details and
moving existing history: [docs/library.md](docs/library.md) ("Markets Access").

## Environment

| variable | purpose |
|---|---|
| `MAINSEQUENCE_ACCESS_TOKEN` / `MAINSEQUENCE_REFRESH_TOKEN` | optional process-environment override of the saved SDK 9 session (categories, signal/portfolio runs); never stored in `.env` |
| `OPEN_FIGI_API_KEY` (Main Sequence secret) | FIGI registration (`--register-missing`) |
| `ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID` | default price-source table for `portfolio-publish` |
| `MSM_API_BACKEND=remote` | set by the application (or for `etfh`): run Markets registry calls on the Markets API (ms-markets ADR 0047) |
| `MARKETS_API_URL` / `MARKETS_API_TOKEN` | local development: call this Markets API instead of discovering the Environment's |
| `MSM_AUTO_REGISTER_NAMESPACE` | tests/sandboxes only: override the `etfhextractor` table namespace |

## Migrations

The package owns one MetaTables migration provider, `etfhextractor_migrations:migration`, for
its single table `DemoBarsTS` (the example's demo price source; version table
`etfhextractor_markets__alembic_version`, head `0001`).

- **Hosted environments** are migrated only by the migration Job of a deployment workflow.
  etfholdingextractor is a library with no deployment of its own, so the application that
  deploys code using `DemoBarsTS` applies `etfhextractor_migrations:migration` in its own
  migration Job (`metatables.upgrade_application("etfhextractor_migrations:migration")`). The
  ms-markets schema, which `DemoBarsTS` references by foreign key, is migrated by the ms-markets
  deployment, not by this package or its consumers. A consumer that locks this package runs its
  migration Job with `mainsequence-metatable` 0.1.35, so before it pushes:
  - the Environment's hosted MetaTables API runs 0.1.32 or later (it runs 0.1.34 in Production
    and development); older APIs reject the table metadata the client sends with finalization;
  - the migration Job declares `access.branches: [{repository: MetaTables, level: view}]`;
  - the Team that owns the `etfhextractor` namespace in that Environment has Writer on it, and its
    members include the Job's workload User and every workload that reads or writes `DemoBarsTS`.
    Otherwise registration fails with `403` `namespace_not_writable` or `table_not_editable`.

  The 0.1.19 requirement of 0.4.3 no longer applies: since MetaTables 0.1.21 the client ignores
  runtime-context fields it does not know
  ([MetaTables#33](https://github.com/mainsequence-projects/MetaTables/issues/33)).
- **Local development** uses the laptop's local MetaTables runtime (local SQLite):

  ```bash
  metatables init --local
  metatables serve --local                # another terminal; needs `mainsequence login`
  metatables --local runtime initialize   # once per new local runtime
  metatables --local migrations upgrade --provider etfhextractor_migrations:migration head
  metatables --local migrations current --provider etfhextractor_migrations:migration
  ```

  A laptop runs one local MetaTables API, shared by every checkout. When one is already
  running, from this project or any other, `serve --local` reports it and exits, and the
  `--local` commands connect to it. Commits and branch switches need no API restart. The local
  API always runs Local; it has no switch to a hosted runtime.

  The local runtime must already hold the ms-markets tables: MetaTables finalizes `DemoBarsTS`
  only once its foreign-key target, the ms-markets Asset table, is an active MetaTable there.
  Since ms-markets 2.2.2 that schema applies to a fresh local runtime; the
  [ms-markets getting-started guide](https://mainsequence-projects.github.io/MainSequenceMarkets/getting-started/#first-market-setup)
  shows how. This package never applies the ms-markets provider.

Nothing migrates at import or start-up. Details: [docs/library.md](docs/library.md)
("Who applies the provider").

## Development and releases

Since `mainsequence` 9.0.5, `mainsequence code-repository sync` only refreshes local
dependencies (`uv lock`, `uv sync`, `uv export --locked --no-dev --no-hashes`); it no longer
bumps, tags, commits or pushes. Releasing is repository work: bump the version in
`pyproject.toml`, `.agents/agent_card.json` and the README badge, refresh `uv.lock` (the sync
does it), add a [CHANGELOG.md](CHANGELOG.md) entry, commit, and publish with a plain `git push`
plus the version tag. Workflow files decide what a push deploys; this repository declares none.

```bash
uv run pytest -q
uv run ruff check --no-fix .
```

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
