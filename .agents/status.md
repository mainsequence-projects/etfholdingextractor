# Status

## Verified

- Release version is `0.4.3`; runtime is Python `3.13`. `pyproject.toml` declares
  `mainsequence>=9.0.5,<10`, `mainsequence-metatable>=0.1.14,<0.2` and `ms-markets>=2.1.1,<3`;
  `uv.lock` resolves 9.0.5, 0.1.14 and 2.1.1, and `requirements.txt` was regenerated from it
  (implementation task 0007).
- Migrations follow the MetaTables 0.1.14 rule. This repository has no deployment and no
  workflow file; the application that deploys code using `DemoBarsTS` applies
  `etfhextractor_migrations:migration` in its own migration Job, and local development uses
  `metatables --local migrations ...`. Nothing migrates at import or start-up.
- `examples/prepare_demo_bars_schema.py` applies the provider only with `--local`, after checking
  that the runtime is an initialized local SQLite runtime, and only verifies a hosted runtime.
  The full workflow example has `--local` and no longer cites the generic top-level
  `migrations` provider.
- The migration provider owns only `etfhextractor_markets__demobarsts`, with the version table
  `etfhextractor_markets__alembic_version`, revision `0001`, and explicit package-local
  `script_location` and `version_location_prefix`. `AssetTable` remains in the metadata solely
  to close the foreign-key graph and is excluded from provider DDL.
- On 2026-10-03, on an isolated local SQLite runtime, `0001` applied and both provider tables
  finalized active once the foreign-key target `ms_markets__asset` was a finalized MetaTable (a
  scratch-only replica of the msm `AssetTable`); `migrations current` reported `0001 (head)`
  and a repeated upgrade was a no-op. The schema-prep example passed with `--local` and
  `--local --check-only` against that runtime.
- The SDK 9.0.5, `metatables` 0.1.14 and ms-markets 2.1.1 skill bundles are copied and the
  managed AGENTS.md block was regenerated, all offline. Platform-owned skills
  (`.agents/skills/mainsequence_platform/`) are not installed, because that update needs a
  signed-in session.
- Product code passes no `data_source_uid`, so msm SQL takes the DataSource and dialect from the
  MetaTables runtime of the caller's Organization Environment (implementation task 0006,
  "Runtime DataSource").
- Provider URL/ticker extraction, holdings-category planning/sync, FIGI registration,
  `ETFHoldingsSignal`, portfolio publication, and the demo-bars updater remain present.
- From 2026-09-02, under SDK 8: CodeRepository UID `2b634665-d3c0-4cf4-a8ed-f4446eba7891` and
  branch `main`. Backend migration `0001 (head)`; the registry and the demo-bars MetaTable were
  active. A live iShares IVV read returned 508 holdings dated 2026-08-31. None of this was
  re-checked under SDK 9.

## Validation

- Full pytest suite: 95 passed, offline.
- `ruff check --no-fix .` passed. Vendored `.agents/` skills are excluded from ruff.
- `python -m metatables.sdk_compat` passed (distribution 9.0.5).

## Pending

- The ms-markets 2.1.1 provider cannot finalize on a MetaTables 0.1.14 API: a 70-character
  default secondary-index name on `PortfolioEventLedgerStorage` (422 at reservation) and
  cascading foreign keys in `0018_initial_schema` (400 `cascading_foreign_key_unsupported` at
  finalization). Until ms-markets fixes both, a fresh local runtime cannot hold the real
  ms-markets schema, so the local example run and the local `DemoBarsTS` proof against the real
  ms-markets tables remain open.
- No hosted state was read or migrated in this pass.
- Exercise live msm SQL (category sync, ticker resolution, FIGI registration checks) under SDK 9.
- A live portfolio `node.run()` still requires a caller-owned registered price source and a fully
  registered component universe.
