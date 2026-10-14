# Status

## Verified

- Release version is `0.4.4`, the first release after 0.4.2; 0.4.3 was never published. Runtime
  is Python `3.13`. `pyproject.toml` declares `mainsequence>=9.0.22,<10`,
  `mainsequence-metatable>=0.1.35,<0.2` and `ms-markets==2.2.10` (the release the deployed
  MainSequence Markets runs); `uv.lock` resolves 9.0.22, 0.1.35 and 2.2.10, and
  `requirements.txt` was regenerated from it (implementation task 0007).
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
  `etfhextractor_markets__alembic_version`, revision `0001`, provider key
  `etfhextractor:etfhextractor`, and explicit package-local `script_location` and
  `version_location_prefix`. `AssetTable` remains in the metadata solely to close the
  foreign-key graph and is excluded from provider DDL. `tests/test_provider_identity.py` pins
  this identity and checks, on SQLite and PostgreSQL, that the models still produce exactly
  revision `0001` on the installed stack.
- `DemoBarsTS` keeps `ON DELETE RESTRICT` on its asset key, the action it was authored with and
  the one ms-markets' own asset-keyed time-series tables use. MetaTables 0.1.17 and later allow
  cascading foreign keys, and 0.1.18 makes write on a table depend only on its own grants.
- The local migration proof passed on 2026-10-03 (MetaTables 0.1.18, ms-markets 2.2.2) and
  2026-10-04 (0.1.20, 2.2.5), each on a fresh isolated local SQLite runtime.
- On 2026-10-11 it passed on MetaTables 0.1.34 with ms-markets 2.2.10 and SDK 9.0.22, against the
  development backend, on a fresh isolated runtime with its own local API on a free port
  (scratch storage directory and configuration; stopped afterwards; the laptop's shared local
  API and runtime file untouched). System revision `0012_table_creator`; ms-markets
  `0020 (head) (mergepoint)` with 62 tables active; `0001` applied with 2 tables finalized and
  active (0 reserved, 0 failed), `migrations current` reported `0001 (head)` and a repeated
  upgrade was a no-op. All 64 catalog rows were active. `get_impact(action="delete_rows")` on
  `ms_markets__asset` reported no blockers and 34 edges (6 `cascade_delete`, 28 `restrict`), with
  the `DemoBarsTS` foreign key a `restrict` edge. Both schema-prep runs passed, and
  `upgrade_application("etfhextractor_migrations:migration")` through `configure_local_client()`
  reported `0001`, `migrated: False` and 2 active tables (implementation task 0007, "Re-run on
  MetaTables 0.1.34").
- On the same runtime the library ran end to end with fixtures replacing only the provider
  extraction and OpenFIGI: one shared runtime for the portfolio and category paths (36 models,
  `DemoBarsStorage` attached), FIGI registration and ticker resolution, category planning, the
  NYSE calendar, 375 demo bars, and a portfolio update that wrote 3 signal-weight rows on the
  backtest-bootstrap close, 42 value rows and 3 weight rows, with no new rows on re-runs. Three
  ms-markets 2.2.10 defects on local SQLite stopped the rest: Asset inserts are refused (an
  unbound `ms_markets__interpolatedpricests`; worked around in the scratch catalog only),
  `replace_memberships` deletes what it upserted, and the portfolio pointer upsert fails after
  the rows are written (implementation task 0007, "Local end-to-end run on 0.4.4").
- The SDK 9.0.22, `metatables` 0.1.35 and ms-markets 2.2.10 skill bundles are copied, offline.
  The managed AGENTS.md block was not regenerated: the 9.0.22 block differs by one routing line,
  and that update is explicit. Platform-owned skills (`.agents/skills/mainsequence_platform/`)
  are not installed, because that update needs a signed-in session.
- Read in the MetaTables source: since 0.1.21 the runtime-context models ignore unknown fields
  (MetaTables#33), so the 0.1.19 prerequisite of 0.4.3 is gone; since 0.1.32 the client sends
  `authored_metadata` with finalization, which an API before 0.1.32 rejects. A consumer that
  locks 0.4.4 therefore needs its Environment's hosted MetaTables API on 0.1.32 or later (it runs
  0.1.34 in Production and development), MetaTables view access on its migration Job, and the
  Team that owns the `etfhextractor` namespace with that Job's workload User as a member.
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

- Full pytest suite: 101 passed, offline.
- `ruff check --no-fix .` passed. Vendored `.agents/` skills are excluded from ruff.
- `python -m metatables.sdk_compat` passed (distribution 9.0.22).
- All 63 distinct `msm`, `msm_portfolios`, `metatables` and `mainsequence` imports resolve on the
  new stack.

## Pending

- Publishing 0.4.4: push, then tag the pushed commit `v0.4.4` and push that tag on its own
  (`.agents/tasks.md`, "Publish 0.4.4 and refresh consumers"). The local annotated tag `v0.4.3`
  points at `e925fa3`, is not on origin and must not be pushed.
- No hosted state was read or migrated in this pass.
- The three ms-markets defects above block the full example with `--local` on local SQLite.
- Live provider extraction and OpenFIGI were not exercised, and live msm SQL (category sync,
  ticker resolution, FIGI registration) is still unverified on a hosted runtime under SDK 9.
- A live portfolio `node.run()` still requires a caller-owned registered price source and a fully
  registered component universe.
