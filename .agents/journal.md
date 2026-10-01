# Journal

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
