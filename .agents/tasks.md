# Tasks

## Open

### Publish SDK 8 migration and refresh consumers

- Run the canonical `mainsequence code-repository sync` only after reviewing the complete diff.
- Update consumer locks to the published `etfhextractor 0.4.x` commit and rerun their full suites.

### Live portfolio execution

- Supply a registered price `TimeIndexTableUpdater` or `TimeIndexTableRef` containing `close` (or
  the configured valuation column) for a fully registered ETF component universe.
- Run `etfh portfolio-publish`, then verify signal, value, and weight rows plus the Portfolio row.

## Completed

### Migrate to Main Sequence SDK 8 and ms-markets 1

- Migrated dependencies, updater output contracts, registered-table references, provider-scoped
  MetaTable migrations, reusable portfolio assembly, docs, examples, skills, and agent metadata.
- Applied backend revision `0001`, finalized the managed tables, attached the runtime, and verified
  live iShares extraction.
