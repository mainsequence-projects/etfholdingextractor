# 0007 — SDK 9.0.5, MetaTables 0.1.18 and deployment-Job migrations

Status: implemented in 0.4.3. The provider was proven on an isolated local SQLite runtime against
the real ms-markets 2.2.2 schema. No hosted runtime was read or migrated.

## Goal

Move `etfhextractor` to `mainsequence` 9.0.5, `mainsequence-metatable` 0.1.18 and ms-markets
2.2.2, and adopt the MetaTables migration recommendation introduced in 0.1.14
(`docs/client/deploy-application-migrations.md` in the vendored `metatables` skills):

1. Develop locally: author and apply revisions with `metatables --local migrations ...`.
2. Commit each revision with the code that needs it.
3. Deploy: the application's `.mainsequence/workflows/` file runs a migration Job that calls
   `metatables.upgrade_application(...)` for its providers, in dependency order, before the
   resources that use the tables roll out. Hosted runtimes are migrated only by that Job.

## Dependency contract

- `mainsequence>=9.0.5,<10` (locked 9.0.5)
- `mainsequence-metatable>=0.1.18,<0.2` (locked 0.1.18)
- `ms-markets>=2.2.2,<3` (locked 2.2.2)

`uv lock --upgrade-package` moved only these packages; `mainsequence` 9.0.5 is the latest
release. `requirements.txt` was regenerated with the command in its header.

## The recommendation, applied to a library

etfholdingextractor has no deployment, so it has no `.mainsequence/workflows/` file and no
migration Job. Its provider, `etfhextractor_migrations:migration`, is unchanged: package
`etfhextractor`, namespace `etfhextractor`, version table
`etfhextractor_markets__alembic_version`, revision `0001`, explicit
`script_location="etfhextractor_migrations:"` and
`version_location_prefix="etfhextractor_migrations:versions"`. The top-level package name is
specific to this application, which the MetaTables provider-placement rule allows.

- The application that deploys code reading or writing `DemoBarsTS` applies
  `etfhextractor_migrations:migration` in its own migration Job. It does not apply the
  ms-markets provider: since ms-markets 2.1.1 only the ms-markets deployment migrates the
  ms-markets schema.
- Local development applies the provider with
  `metatables --local migrations upgrade --provider etfhextractor_migrations:migration head`.
- Nothing migrates at import or start-up. The package has no API, lifespan or start-up hook;
  runtime code only attaches with `msm.start_engine(models=[...])`.
- Revision `0001` uses portable DDL only (`op.create_table`, `op.create_index`), so it needs no
  dialect branch. Future revisions that run raw PostgreSQL SQL must branch on
  `op.get_bind().dialect.name`.

README, `docs/library.md` ("Who applies the provider"), `examples/README.md`, the AGENTS.md
project text and `.agents/` state files say so.

## Examples

`examples/prepare_demo_bars_schema.py` used to run the `metatables` CLI's `upgrade` without
`--local`, so it migrated whatever runtime the Environment selected: a hosted migration by
hand. Now:

- `--local` selects the project's running local MetaTables API with
  `metatables.configure_local_client()`, refuses unless the runtime reports Local mode, the
  SQLite dialect and an initialized DataSource, then runs
  `metatables --local migrations upgrade --provider etfhextractor_migrations:migration head`
  and verifies the registered `TimeIndexMetaTable`. Revision generation, needed only for a
  sandbox namespace without a revision, also runs with `--local`.
- Without `--local` the script only verifies the revision and the registration. When the table
  is missing it stops with the migration rule instead of migrating.
- `_run_metatables` refuses any command that does not start with `--local`.

`examples/ivv_tracking_portfolio_full_workflow.py` gained `--local` (select and verify the local
runtime before any client call, then apply the provider in step 0) and no longer cites the
generic top-level `migrations` provider or hosted upgrades. Its prerequisite is a
runtime that already holds the ms-markets tables. The VS Code launch entry for the schema step
passes `--local`.

## ms-markets 2.1.1 to 2.2.2

- 2.1.1 renamed `cli` and `command_center` to `msm_cli` and `msm_command_center`. This
  repository imports neither, and its own CLI is the subpackage `etfhextractor.cli`.
- 2.2.0 removed `msm_command_center`, the `apps/v1` re-export modules, the Asset Monitor frame
  and workspace builders, and the fixed income `response_mappings`. This repository uses none of
  them: all 51 distinct `msm` and `msm_portfolios` imports in the package, the migration
  provider, the examples and the tests resolve on 2.2.2.
- 2.2.2 requires `mainsequence-metatable>=0.1.17` and gives `PortfolioEventLedgerTS` an explicit
  `__storage_layout__`, whose lookup index name fits PostgreSQL's 63-character limit, so the
  ms-markets provider finalizes on a fresh runtime.
- The history is one revision, `0018_initial_schema`. Consumers never apply it.
- `.agents/skills/ms_markets/` was refreshed with `msm copy-msm-skills --path .`. The refresh
  removed the Command Center Asset Monitor skills, which 2.2.0 dropped. Its
  `metatable_migrations` skill states the same migration rule.

## MetaTables 0.1.17 and 0.1.18

- 0.1.17 allows foreign keys with `ON DELETE` and `ON UPDATE` `CASCADE`, `SET NULL` and
  `SET DEFAULT` (amendment of 2026-10-03 to API ADR 0007). The catalog records each table's
  cascade targets (system migration `0010_cascade_targets`), and
  `MetaTable.get_impact(action="delete_rows" | "update_keys" | "drop_table")` previews what an
  action reaches (API ADR 0016).
- 0.1.18 removes the 0.1.17 cascade write narrowing. Write on a table depends only on that
  table's own grants, and the pre-flight reports cascade effects as information, never as
  blockers.
- The only foreign key in this repository, `DemoBarsTS.asset_identifier` →
  `ms_markets__asset.unique_identifier`, has been `ON DELETE RESTRICT` since the table was
  introduced. The asset keys of ms-markets' own time-series tables (`AssetSnapshotsTS`,
  `ExternalPricesTS`, `SignalWeightsTS`, `PortfolioCashFlowsTS` and others) use the same action.
  It was never changed to work around MetaTables, so there is nothing to restore, and revision
  `0001` is unchanged.
- `.agents/skills/metatables/` was refreshed with `metatables copy-metatables-skills --path .`.

## SDK 9.0.5

`mainsequence code-repository sync` only refreshes local dependencies (`uv lock`, `uv sync`,
`uv export --locked --no-dev --no-hashes`). It no longer bumps, tags, commits or pushes.
Publishing is a plain `git push` plus the version tag, and workflow files decide what deploys;
this repository declares none. `.agents/skills/mainsequence/` is the SDK 9.0.5 bundle (it adds
`mainsequence-inference`) and the managed AGENTS.md block was regenerated, both offline.

## Local migration proof

Run on 2026-10-03 with `mainsequence-metatable` 0.1.18 and ms-markets 2.2.2. Every command used
`METATABLES_LOCAL_STORAGE_DIR` set to a fresh scratch directory, a dedicated local API port, a
scratch launcher configuration (`local_mode_available: true`, credential keys in a scratch
directory) and `metatables --local` only.

1. `metatables --local runtime initialize` applied the system migrations `0001_initial` through
   `0010_cascade_targets`. Status then reported `local_mode: true`, `dialect: sqlite`, bootstrap
   `ready` and a local SQLite DataSource.
2. As a local-only prerequisite, the ms-markets 2.2.2 provider was applied to the same runtime:
   `Running upgrade  -> 0018, initial schema`, then 62 tables finalized, 62 active and 0 failed,
   including `ms_markets__asset` and `ms_markets__portfolioeventledgerts`. On hosted runtimes the
   ms-markets deployment applies that schema; this repository's docs and its consumers' Jobs do
   not.
3. This repository's provider finalized with the ms-markets cascades in place:

   ```text
   $ metatables --local migrations upgrade --provider etfhextractor_migrations:migration head
   [alembic] INFO alembic.runtime.migration: Running upgrade  -> 0001, etfhextractor_demo_bars
   ok: True
   finalized_count: 2
   active_count: 2
   reserved_count: 0
   failed_count: 0
   revision: 0001
   migrated: True
   $ metatables --local migrations current --provider etfhextractor_migrations:migration
   0001 (head)
   ```

   The ms-markets provider reported `0018 (head)`. A repeated upgrade reported
   `migrated: False` with both tables active.
4. The catalog rows for `etfhextractor_markets__alembic_version`,
   `etfhextractor_markets__demobarsts` and `ms_markets__asset` were `active` in the local
   DataSource. `DemoBarsTS` is a `TimeIndexMetaTable` with index names
   `["time_index", "asset_identifier"]`.
5. `get_impact(action="delete_rows")` on `ms_markets__asset` returned `allowed: true` and no
   blockers. Of its 34 foreign-key edges, 6 were `cascade_delete` and 28 `restrict`, including
   `etfhextractor_markets__demobarsts` → `ms_markets__asset`.
6. `examples/prepare_demo_bars_schema.py --local --check-only` and `--local` both passed. Run
   through `configure_local_client()`,
   `metatables.upgrade_application("etfhextractor_migrations:migration")`, the call a consuming
   application's migration Job makes, reported `ok: True`, `migrated: False` and 2 active tables.

Finalization preflights every foreign-key target: the target must be an active MetaTable in the
same DataSource, with a primary-key or unique target column set. `DemoBarsTS` therefore
finalizes only in a runtime that already holds the ms-markets Asset table. The first draft of
this task proved the provider against a scratch replica of `ms_markets__asset`, because the
ms-markets 2.1.1 schema could not be applied to a fresh runtime then. The replica is no longer
needed.

## Validation

```bash
uv run pytest -q
uv run ruff check --no-fix .
uv run python -m metatables.sdk_compat
```

Not verified: the hosted migration state, live provider extraction, a live portfolio run, and
the full example against the local runtime, which needs live iShares and OpenFIGI calls.
