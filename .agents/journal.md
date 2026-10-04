# Journal

## 2026-10-04

- Ran the pending local migration proof on MetaTables 0.1.20 and ms-markets 2.2.5, signed in to
  the development backend, on a fresh isolated local SQLite runtime with its own local API. It
  passed: ms-markets `0018 (head)` with 62 tables active, then `0001` with 2 tables finalized
  and active, 64 catalog rows active, the impact pre-flight unchanged (34 edges, 6
  `cascade_delete`, 28 `restrict`), both schema-prep runs green and `upgrade_application` a
  no-op at `0001`. The API was stopped and its `server.json` removed. No hosted runtime was
  touched; no push, tag or sync.
- Moved the unreleased 0.4.3 to `mainsequence` 9.0.6, `mainsequence-metatable` 0.1.20 and
  ms-markets 2.2.5, the latest releases. Relocked with `uv lock --upgrade-package` for the three
  packages and regenerated `requirements.txt`; the lock no longer carries the SDK's `server`
  extra, which 9.0.6 folded into the base package.
- Refreshed the SDK 9.0.6, `metatables` 0.1.20 and ms-markets 2.2.5 skills offline; the managed
  AGENTS.md block was already current.
- MetaTables 0.1.19 runs one local API per laptop and removed the launcher's Local/Hosted switch.
  README, `docs/library.md`, `examples/README.md` and both examples described a per-project
  local API; they now describe the shared one, and `tests/test_migration_guidance.py` fails on
  the retired wording. No code changed.
- The local migration proof on 0.1.20 could not run: the local API resolves the developer
  through the platform at startup, and the local backend did not answer. The 2026-10-03 proof on
  0.1.18 stands; the re-run is pending. Nothing ran against a hosted runtime.
- Documented the hosted prerequisite of the 0.1.20 lock. The 0.1.20 client rejects the runtime
  context of a MetaTables API on 0.1.18 or older (`RuntimeContext` forbids the runtime-switch
  fields such an API still sends), so a consumer that locks 0.4.3 needs its Environment's hosted
  MetaTables API on 0.1.19 or later before it pushes (MetaTables#33). README,
  `docs/library.md`, `examples/README.md`, the CHANGELOG, implementation task 0007 and the
  publish task now say so.
- The publish task now says that the local annotated tag `v0.4.3` points at `ceabfb9`, which
  still has the SDK 9.0.5, MetaTables 0.1.18 and ms-markets 2.2.2 floors, and must move to the
  merged commit before it is pushed. No tag was created or moved.
- The record no longer calls the 9.0.6, 0.1.20 and 2.2.5 locks verified: only offline checks ran.
  The local backend still did not answer, so the local proof stays pending.

## 2026-10-03

- Released 0.4.3 on `mainsequence` 9.0.5, `mainsequence-metatable` 0.1.14 and ms-markets 2.1.1
  (implementation task 0007). Relocked with `uv lock --upgrade-package` for the three packages
  and regenerated `requirements.txt`.
- Adopted the MetaTables 0.1.14 migration recommendation. The repository has no deployment, so
  it gets no workflow or migration Job; the docs now say that the application deploying code
  using `DemoBarsTS` applies `etfhextractor_migrations:migration` in its own migration Job and
  that local development uses `metatables --local`. The schema-prep example no longer migrates
  hosted runtimes, and the full workflow example gained `--local`.
- Refreshed the SDK 9.0.5, `metatables` 0.1.14 and ms-markets 2.1.1 skills and the managed
  AGENTS.md block, offline.
- Proved the provider on an isolated local SQLite runtime. The real ms-markets 2.1.1 provider
  cannot finalize on a MetaTables 0.1.14 API (70-character secondary-index name, cascading
  foreign keys), so `DemoBarsTS` was finalized against a scratch replica of `ms_markets__asset`.
  Nothing ran against a hosted runtime.
- Moved 0.4.3 to `mainsequence-metatable` 0.1.18 and ms-markets 2.2.2 before release. MetaTables
  0.1.17 allows cascading foreign keys and 0.1.18 makes write depend only on a table's own grants;
  ms-markets 2.2.2 fixes the 70-character index name. Refreshed the `metatables` and ms-markets
  skills (the refresh drops the Asset Monitor skills). `DemoBarsTS` keeps its original
  `ON DELETE RESTRICT`, so no revision changed.
- Proved the provider again on a fresh isolated local SQLite runtime at system revision
  `0010_cascade_targets`, this time against the real ms-markets 2.2.2 schema, which was applied
  first as a local-only prerequisite; the scratch replica is no longer needed. Nothing ran
  against a hosted runtime.

## 2026-10-01

- Moved the package to Main Sequence SDK 9, the `metatables` client (`mainsequence-metatable`
  0.1.5) and ms-markets 2. The MetaTables imports in the models, migration provider, portfolio
  builder, schema-prep example and tests now come from `metatables`, and the migration commands
  are `metatables migrations ... --provider etfhextractor_migrations:migration`.
- Dropped the `run(debug_mode=..., force_update=...)` controls that SDK 8.1 removed, the
  `ImmediateSignal(calendar_key=...)` argument that ms-markets 1.0.7 removed, and the no-op
  `debug_mode` parameter of the portfolio builder and publisher.
- Copied the `metatables` 0.1.5 skills and refreshed the ms-markets 2.0.0 skills. The SDK skills
  were not refreshed (mainsequence-sdk#181).
- Verified offline: sdk_compat, imports, provider loading, ruff, 87 tests. Nothing was run against
  the platform or a database.
- Raised the floors to `mainsequence>=9.0.2` and `mainsequence-metatable>=0.1.6`, the releases
  ms-markets 2.0.0 now requires. 0.1.6 takes the DataSource and dialect from the
  Environment-selected MetaTables runtime, so the MetaTables#9 failure on live msm SQL no longer
  applies; no product code changed.
- Re-copied the `metatables` 0.1.6 skills, replaced `.agents/skills/mainsequence/` with the SDK
  9.0.2 bundle, and regenerated the managed AGENTS.md block, all offline. Platform skills were not
  installed.
- Verified offline again: sdk_compat (9.0.2), provider loading, ruff, 87 tests.

## 2026-09-02

- Migrated the complete package to Python 3.13, Main Sequence SDK 8.0.7, and ms-markets 1.0.2
  without removing extraction, category sync, FIGI registration, holdings signals, portfolio
  publication, or demo-bars behavior.
- Replaced `_required_storage_table`/`storage_table` with the SDK 8 output-table contract and
  replaced removed `APIDataNode` registered-table dependencies with `TimeIndexTableRef`.
- Added a reusable `EtfTrackingPortfolioBuild` result and `build_etf_tracking_portfolio(...)`;
  the existing publisher and CLI retain their JSON response while downstream projects can reuse
  the actual graph with custom portfolio identity and valuation metadata.
- Scoped Alembic ownership to the project demo-bars table, applied revision `0001`, finalized both
  managed resources active, and verified runtime attachment.
- Live iShares IVV extraction returned 508 holdings dated 2026-08-31.
- Refreshed the SDK/platform/ms-markets skills and updated repository docs and state records.

## 2026-04-30

Initialized repository-local agent scaffolding for `etfholdingextractor-161`.

- Added a project-specific instruction section to `AGENTS.md`.
- Added repo-local skills for ETF holdings extraction and holdings category sync.
- Created `.agents/agent_card.json`.
- Initialized `.agents` state files for future maintenance passes.
