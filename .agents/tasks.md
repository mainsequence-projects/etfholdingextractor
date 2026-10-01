# Tasks

## Open

### Release the SDK 9 migration and refresh consumers

- After ms-markets 2.0.0 is on PyPI, regenerate `uv.lock` and `requirements.txt`
  (implementation task 0006) and rerun the offline checks.
- Run the canonical `mainsequence code-repository sync` only after reviewing the complete diff.
- Verify the backend state with `metatables migrations current --provider
  etfhextractor_migrations:migration`.
- Refresh `.agents/skills/mainsequence/` and the managed AGENTS.md block once SDK skill copying
  works without sign-in (mainsequence-sdk#181).
- Update consumer locks (e.g. Alpaca Connectors: `uv lock --upgrade-package etfhextractor`).

### Signal validity under ms-markets 2.x

- ms-markets 2.x no longer bounds the portfolio forward-fill by `maximum_forward_fill()`. Decide
  whether `signal_validity_days` and the re-stamp guard stay (ADR 0006 amendment).

### Live portfolio execution

- Supply a registered price `TimeIndexTableUpdater` or `TimeIndexTableRef` containing `close` (or
  the configured valuation column) for a fully registered ETF component universe.
- Run `etfh portfolio-publish`, then verify signal, value, and weight rows plus the Portfolio row.

## Completed

### Migrate to Main Sequence SDK 9, metatables and ms-markets 2

- Migrated the MetaTables imports, migration commands, updater run calls, and the portfolio
  rebalance strategy. Kept the migration provider and its history unchanged, copied the client
  skills, and updated the docs. Verified offline only.

### Migrate to Main Sequence SDK 8 and ms-markets 1

- Migrated dependencies, updater output contracts, registered-table references, provider-scoped
  MetaTable migrations, reusable portfolio assembly, docs, examples, skills, and agent metadata.
- Applied backend revision `0001`, finalized the managed tables, attached the runtime, and verified
  live iShares extraction.
