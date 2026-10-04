# Status

## Verified

- Release version is `0.4.3`; runtime is Python `3.13`. `pyproject.toml` declares
  `mainsequence>=9.0.6,<10`, `mainsequence-metatable>=0.1.20,<0.2` and `ms-markets>=2.2.5,<3`;
  `uv.lock` resolves 9.0.6, 0.1.20 and 2.2.5, and `requirements.txt` was regenerated from it
  (implementation task 0007).
- Migrations follow the MetaTables deployment-Job rule, introduced in 0.1.14. This repository
  has no deployment and no workflow file; the application that deploys code using `DemoBarsTS`
  applies `etfhextractor_migrations:migration` in its own migration Job, and local development
  uses `metatables --local migrations ...` against the laptop's one local MetaTables API, which
  every checkout shares (MetaTables 0.1.19). Nothing migrates at import or start-up.
- `examples/prepare_demo_bars_schema.py` applies the provider only with `--local`, after checking
  that the runtime is an initialized local SQLite runtime, and only verifies a hosted runtime.
  The full workflow example has `--local` and no longer cites the generic top-level
  `migrations` provider.
- The migration provider owns only `etfhextractor_markets__demobarsts`, with the version table
  `etfhextractor_markets__alembic_version`, revision `0001`, and explicit package-local
  `script_location` and `version_location_prefix`. `AssetTable` remains in the metadata solely
  to close the foreign-key graph and is excluded from provider DDL.
- `DemoBarsTS` keeps `ON DELETE RESTRICT` on its asset key, the action it was authored with and
  the one ms-markets' own asset-keyed time-series tables use. MetaTables 0.1.17 and later allow
  cascading foreign keys, and 0.1.18 makes write on a table depend only on its own grants.
- On 2026-10-03, on an isolated local SQLite runtime with MetaTables 0.1.18 (system revision
  `0010_cascade_targets`), the ms-markets 2.2.2 schema was applied first as a local-only
  prerequisite (62 tables active). Then `0001` applied and both provider tables finalized
  active; `migrations current` reported `0001 (head)` and a repeated upgrade was a no-op. The
  catalog rows were active, and `get_impact(action="delete_rows")` on `ms_markets__asset`
  reported the `DemoBarsTS` foreign key as a `restrict` edge and no blockers. The schema-prep
  example passed with `--local` and `--local --check-only`, and
  `upgrade_application("etfhextractor_migrations:migration")` through `configure_local_client()`
  was a no-op.
- On 2026-10-04 the same proof passed on MetaTables 0.1.20 with ms-markets 2.2.5 and SDK 9.0.6,
  against the development backend, on a fresh isolated local SQLite runtime with its own local
  API (stopped afterwards). System revision `0010_cascade_targets`; ms-markets `0018 (head)` with
  62 tables active; `0001` applied with 2 tables finalized and active (0 reserved, 0 failed),
  `migrations current` reported `0001 (head)` and a repeated upgrade was a no-op. All 64 catalog
  rows were active. `get_impact(action="delete_rows")` on `ms_markets__asset` reported no
  blockers and 34 edges (6 `cascade_delete`, 28 `restrict`), with the `DemoBarsTS` foreign key a
  `restrict` edge. Both schema-prep runs passed, and
  `upgrade_application("etfhextractor_migrations:migration")` through `configure_local_client()`
  reported `0001`, `migrated: False` and 2 active tables (implementation task 0007, "Re-run on
  MetaTables 0.1.20").
- The SDK 9.0.6, `metatables` 0.1.20 and ms-markets 2.2.5 skill bundles are copied and the
  managed AGENTS.md block was regenerated (already current), all offline. Platform-owned skills
  (`.agents/skills/mainsequence_platform/`) are not installed, because that update needs a
  signed-in session.
- Read in the MetaTables source: the 0.1.20 client validates `/runtime-context/` against a
  `RuntimeContext` that forbids extra fields, and an API on 0.1.18 or older still sends
  `runtime_switch_available`, `runtime_switch_error` and `hosted_environment_target`. A consumer
  that locks 0.4.3 therefore needs its Environment's hosted MetaTables API on 0.1.19 or later
  before it pushes, or its migration Job fails before migrating
  ([MetaTables#33](https://github.com/mainsequence-projects/MetaTables/issues/33)). README,
  `docs/library.md`, `examples/README.md`, the CHANGELOG, implementation task 0007 and the
  publish task say so.
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

- Full pytest suite: 96 passed, offline.
- `ruff check --no-fix .` passed. Vendored `.agents/` skills are excluded from ruff.
- `python -m metatables.sdk_compat` passed (distribution 9.0.6).
- All 51 distinct `msm` and `msm_portfolios` imports resolve on ms-markets 2.2.5.

## Pending

- Publishing: the local annotated tag `v0.4.3` still points at `ceabfb9`, the commit with the
  SDK 9.0.5, MetaTables 0.1.18 and ms-markets 2.2.2 floors, and is not on origin. Move it to the
  merged commit before pushing it (`.agents/tasks.md`, "Publish 0.4.3 and refresh consumers").
- No hosted state was read or migrated in this pass.
- The full example has not run against a local runtime (`--local`); it needs live iShares and
  OpenFIGI calls.
- Exercise live msm SQL (category sync, ticker resolution, FIGI registration checks) under SDK 9.
- A live portfolio `node.run()` still requires a caller-owned registered price source and a fully
  registered component universe.
