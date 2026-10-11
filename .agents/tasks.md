# Tasks

## Open

### Publish 0.4.4 and refresh consumers

- Publish with a plain `git push` of `main`, then tag the pushed commit with an annotated
  `v0.4.4` (message `v0.4.4`, like earlier tags) and push that tag on its own. Since SDK 9.0.5,
  `mainsequence code-repository sync` only refreshes local dependencies; it does not bump, tag,
  commit or push. Check that `git show v0.4.4:pyproject.toml` has version `0.4.4`.
- 0.4.3 was never published: origin's latest tag is `v0.4.2`. A local annotated `v0.4.3` points
  at `e925fa3` and must not be pushed.
- Re-pin consumers. Alpaca Connectors names the Git source without a revision in
  `[tool.uv.sources]`; pin it to the tag
  (`etfhextractor = { git = "https://github.com/mainsequence-projects/etfholdingextractor", tag = "v0.4.4" }`),
  run `uv lock --upgrade-package etfhextractor` and regenerate its `requirements.txt`. Locking
  0.4.4 also requires `mainsequence>=9.0.22`, `mainsequence-metatable>=0.1.34` and exactly
  ms-markets 2.2.10.
- An application that deploys code reading or writing `DemoBarsTS` lists
  `etfhextractor_migrations:migration` in its own migration Job. Before it pushes, its
  Environment's hosted MetaTables API must run 0.1.32 or later, the Job needs MetaTables view
  access, and the Team that owns the `etfhextractor` namespace needs Writer on it with the Job's
  workload User as a member. Alpaca Connectors does not use `DemoBarsTS` today, so it does not
  need the provider.
- Install the platform-owned skills under `.agents/skills/mainsequence_platform/` with the
  authenticated `mainsequence code-repository update-platform-skills --path .` if the owner asks
  for it. Refresh the managed AGENTS.md block
  (`mainsequence code-repository update AGENTS.md --path .`) when asked; the 9.0.22 block differs
  by one routing line.

### ms-markets defects on local SQLite

- Report to ms-markets, with the reproductions in implementation task 0007 ("Local end-to-end
  run on 0.4.4"): `ms_markets__interpolatedpricests` is created by `0018` but never registered,
  so Asset inserts are refused on local SQLite; `replace_memberships` binds the `NOT IN` asset
  UIDs as dashed strings and deletes what it upserted; `PortfoliosDataNode` upserts `str` UUIDs
  into `Uuid` columns when it updates the Portfolio pointers.
- After a fix, run `python examples/ivv_tracking_portfolio_full_workflow.py --local` against a
  local runtime that holds the ms-markets tables (it needs live iShares and OpenFIGI calls).

### Signal validity under ms-markets 2.x

- ms-markets 2.x no longer bounds the portfolio forward-fill by `maximum_forward_fill()`. Decide
  whether `signal_validity_days` and the re-stamp guard stay (ADR 0006 amendment).

### Live portfolio execution

- Supply a registered price `TimeIndexTableUpdater` or `TimeIndexTableRef` containing `close` (or
  the configured valuation column) for a fully registered ETF component universe.
- Run `etfh portfolio-publish`, then verify signal, value, and weight rows plus the Portfolio row.

## Completed

### Move to SDK 9.0.22, MetaTables 0.1.34 and ms-markets 2.2.10 (0.4.4)

- Required `mainsequence` 9.0.22 and `mainsequence-metatable` 0.1.34, pinned ms-markets 2.2.10
  exactly, relocked, refreshed the SDK, `metatables` and ms-markets skills, and pinned the
  provider identity with `tests/test_provider_identity.py`. Replaced the 0.1.19 hosted
  prerequisite with the 0.1.32 API floor, MetaTables view access and the namespace Team. The
  local migration proof passed on 0.1.34 and ms-markets 2.2.10 on 2026-10-11, and a local
  end-to-end run found three ms-markets SQLite defects (implementation task 0007).

### Move to SDK 9.0.6, MetaTables 0.1.20 and ms-markets 2.2.5 (0.4.3)

- Required `mainsequence` 9.0.6, `mainsequence-metatable` 0.1.20 and ms-markets 2.2.5,
  relocked, refreshed the SDK, `metatables` and ms-markets skills, and rewrote the local
  development notes for the laptop's one local MetaTables API (MetaTables 0.1.19), which every
  checkout shares and which has no Local/Hosted switch. `tests/test_migration_guidance.py`
  guards against the retired wording. The local migration proof passed on 0.1.20 and ms-markets
  2.2.5 on 2026-10-04 (implementation task 0007).

### Move to MetaTables 0.1.18 and ms-markets 2.2.2 (0.4.3)

- Required `mainsequence-metatable` 0.1.18 and ms-markets 2.2.2, relocked, refreshed the
  `metatables` and ms-markets skills, removed the notes that cascading foreign keys block the
  ms-markets schema, and proved the provider against the real ms-markets 2.2.2 schema on an
  isolated local runtime. `DemoBarsTS` keeps its original `ON DELETE RESTRICT`.

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
