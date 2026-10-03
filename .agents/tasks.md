# Tasks

## Open

### Publish 0.4.3 and refresh consumers

- Merge the 0.4.3 branch, tag `v0.4.3`, and publish with a plain `git push`. Since SDK 9.0.5,
  `mainsequence code-repository sync` only refreshes local dependencies; it does not bump, tag,
  commit or push.
- Update consumer locks (e.g. Alpaca Connectors: `uv lock --upgrade-package etfhextractor`). An
  application that deploys code reading or writing `DemoBarsTS` lists
  `etfhextractor_migrations:migration` in its own migration Job.
- Install the platform-owned skills under `.agents/skills/mainsequence_platform/` with the
  authenticated `mainsequence code-repository update-platform-skills --path .` if the owner asks
  for it.

### Local proof against the real ms-markets schema

- Once ms-markets ships a provider that finalizes on MetaTables 0.1.14 (no cascading foreign
  keys, secondary-index names within 63 characters), apply it to a fresh local runtime, then
  rerun `metatables --local migrations upgrade --provider etfhextractor_migrations:migration head`
  and `python examples/ivv_tracking_portfolio_full_workflow.py --local`.

### Signal validity under ms-markets 2.x

- ms-markets 2.x no longer bounds the portfolio forward-fill by `maximum_forward_fill()`. Decide
  whether `signal_validity_days` and the re-stamp guard stay (ADR 0006 amendment).

### Live portfolio execution

- Supply a registered price `TimeIndexTableUpdater` or `TimeIndexTableRef` containing `close` (or
  the configured valuation column) for a fully registered ETF component universe.
- Run `etfh portfolio-publish`, then verify signal, value, and weight rows plus the Portfolio row.

## Completed

### Adopt MetaTables 0.1.14 deployment-Job migrations (0.4.3)

- Required `mainsequence` 9.0.5, `mainsequence-metatable` 0.1.14 and ms-markets 2.1.1,
  regenerated the lock and `requirements.txt`, refreshed the SDK, `metatables` and ms-markets
  skills, documented who applies the provider, made the schema-prep example local-only for
  writes, and proved the provider on isolated local SQLite (implementation task 0007).

### Require mainsequence 9.0.2 and mainsequence-metatable 0.1.6

- Raised the floors, re-copied the `metatables` 0.1.6 skills, and refreshed the SDK skills and
  the managed AGENTS.md block offline. Removed the notes about MetaTables#9, #10 and #11 and
  mainsequence-sdk#181, which those releases fix. Verified offline only.

### Migrate to Main Sequence SDK 9, metatables and ms-markets 2

- Migrated the MetaTables imports, migration commands, updater run calls, and the portfolio
  rebalance strategy. Kept the migration provider and its history unchanged, copied the client
  skills, and updated the docs. Verified offline only.

### Migrate to Main Sequence SDK 8 and ms-markets 1

- Migrated dependencies, updater output contracts, registered-table references, provider-scoped
  MetaTable migrations, reusable portfolio assembly, docs, examples, skills, and agent metadata.
- Applied backend revision `0001`, finalized the managed tables, attached the runtime, and verified
  live iShares extraction.
