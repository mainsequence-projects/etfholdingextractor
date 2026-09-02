# Status

## Verified

- Release version is `0.4.1`; runtime is Python `3.13` with compatible lower bounds
  `mainsequence>=8.0.7` and `ms-markets>=1.0.2` in `pyproject.toml`.
- The SDK, platform, and ms-markets skill bundles are refreshed. Their schema-2 sentinel files
  match SDK `8.0.7` and ms-markets `1.0.2`.
- Provider URL/ticker extraction, holdings-category planning/sync, FIGI registration,
  `ETFHoldingsSignal`, portfolio publication, and the demo-bars updater remain present.
- `DemoBars` uses `_required_output_table()` and frame validation uses `output_table`.
- Registered portfolio price tables resolve through `TimeIndexTableRef.from_uid`; explicit
  `TimeIndexTableUpdater` dependencies remain executable updater instances.
- `build_etf_tracking_portfolio(...)` exposes the complete reusable calendar/signal/Portfolio/
  `PortfoliosDataNode` graph. `publish_etf_tracking_portfolio(...)` retains the existing JSON
  summary contract used by `etfh portfolio-publish`.
- The migration provider owns only `etfhextractor_markets__demobarsts`; `AssetTable` remains in
  metadata solely to close the foreign key graph and is excluded from provider DDL.
- CodeRepository UID `2b634665-d3c0-4cf4-a8ed-f4446eba7891`, branch `main`, resolved against
  commit `11219c045f9f92355e8f5a07c7fe17f475abb6c4` before publication.
- Backend migration is `0001 (head)`. The registry and demo-bars MetaTable finalized active with
  zero reserved or failed resources, and runtime attachment resolved `AssetTable` plus
  `DemoBarsStorage`.
- A live iShares IVV read on 2026-09-02 returned 508 holdings dated 2026-08-31.

## Validation

- Full pytest suite: 86 passed.
- Ruff: passed for the migrated code and tests.
- `uv lock --check`: passed.
- `uv pip check --python .venv/bin/python`: all installed packages compatible.

## Pending

- Publish the reviewed SDK 8 migration through the canonical CodeRepository sync workflow, then
  refresh downstream git dependency locks.
- A live portfolio `node.run()` still requires a caller-owned registered price source and a fully
  registered component universe; migration validation does not fabricate those inputs.
