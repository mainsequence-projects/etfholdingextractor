# 0007 — SDK 9.0.6, MetaTables 0.1.20 and deployment-Job migrations

Status: implemented in 0.4.3. On 2026-10-03 the provider was proven on an isolated local SQLite
runtime with MetaTables 0.1.18 against the real ms-markets 2.2.2 schema, and on 2026-10-04 the
re-run on MetaTables 0.1.20 and ms-markets 2.2.5 passed (see "Local migration proof"). No hosted
runtime was read or migrated.

## Goal

Move `etfhextractor` to `mainsequence` 9.0.6, `mainsequence-metatable` 0.1.20 and ms-markets
2.2.5, and adopt the MetaTables migration recommendation introduced in 0.1.14
(`docs/client/deploy-application-migrations.md` in the vendored `metatables` skills):

1. Develop locally: author and apply revisions with `metatables --local migrations ...`.
2. Commit each revision with the code that needs it.
3. Deploy: the application's `.mainsequence/workflows/` file runs a migration Job that calls
   `metatables.upgrade_application(...)` for its providers, in dependency order, before the
   resources that use the tables roll out. Hosted runtimes are migrated only by that Job.

## Dependency contract

- `mainsequence>=9.0.6,<10` (locked 9.0.6)
- `mainsequence-metatable>=0.1.20,<0.2` (locked 0.1.20)
- `ms-markets>=2.2.5,<3` (locked 2.2.5)

`uv lock --upgrade-package` moved only these packages, each to its latest release. The lock no
longer carries the SDK's `server` extra, which 9.0.6 folded into the base package (PyJWT with
cryptography is now a plain dependency). `requirements.txt` was regenerated with the command in
its header.

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
- Before that application pushes a lock on 0.4.3, its Environment's hosted MetaTables API must
  run 0.1.19 or later. The `mainsequence-metatable` 0.1.20 client validates
  `/runtime-context/` against a `RuntimeContext` that forbids extra fields, and an API on
  0.1.18 or older still sends `runtime_switch_available`, `runtime_switch_error` and
  `hosted_environment_target`, so the migration Job fails before it reserves or migrates
  anything and the rollout stops
  ([MetaTables#33](https://github.com/mainsequence-projects/MetaTables/issues/33)).
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

- `--local` selects the laptop's running local MetaTables API with
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

## ms-markets 2.1.1 to 2.2.5

- 2.1.1 renamed `cli` and `command_center` to `msm_cli` and `msm_command_center`. This
  repository imports neither, and its own CLI is the subpackage `etfhextractor.cli`.
- 2.2.0 removed `msm_command_center`, the `apps/v1` re-export modules, the Asset Monitor frame
  and workspace builders, and the fixed income `response_mappings`. This repository uses none of
  them: all 51 distinct `msm` and `msm_portfolios` imports in the package, the migration
  provider, the examples and the tests resolve on 2.2.5.
- 2.2.2 requires `mainsequence-metatable>=0.1.17` and gives `PortfolioEventLedgerTS` an explicit
  `__storage_layout__`, whose lookup index name fits PostgreSQL's 63-character limit, so the
  ms-markets provider finalizes on a fresh runtime.
- 2.2.3 adds the MetaTables `delete_rows` impact to the portfolio, portfolio-group and
  asset-category bulk-delete preflights (`msm.api.http`, `msm.services`), and 2.2.4 and 2.2.5
  omit unset optional fields from the bulk-action and tabular-frame contract models. This
  repository uses none of them. The models and the migration history are unchanged since 2.2.2.
- The history is one revision, `0018_initial_schema`. Consumers never apply it.
- `.agents/skills/ms_markets/` was refreshed with `msm copy-msm-skills --path .`. The 2.2.2
  refresh removed the Command Center Asset Monitor skills, which 2.2.0 dropped; the 2.2.5 refresh
  changed only the pin. Its `metatable_migrations` skill states the same migration rule.

## MetaTables 0.1.17 to 0.1.20

- 0.1.17 allows foreign keys with `ON DELETE` and `ON UPDATE` `CASCADE`, `SET NULL` and
  `SET DEFAULT` (amendment of 2026-10-03 to API ADR 0007). The catalog records each table's
  cascade targets (system migration `0010_cascade_targets`), and
  `MetaTable.get_impact(action="delete_rows" | "update_keys" | "drop_table")` previews what an
  action reaches (API ADR 0016).
- 0.1.18 removes the 0.1.17 cascade write narrowing. Write on a table depends only on that
  table's own grants, and the pre-flight reports cascade effects as information, never as
  blockers.
- 0.1.19 runs one local API per laptop (amendment of 2026-10-03 to client ADR 0011). The
  launcher publishes its address, private token and process in `server.json` in the local
  storage directory (`METATABLES_LOCAL_STORAGE_DIR`, by default `~/.local/share/metatables`)
  instead of a per-project connection file under `.local/`. `metatables --local` and
  `configure_local_client()` read it from any checkout, `serve --local` reports an API that is
  already running and exits, and the API no longer rejects clients from another checkout or
  branch, so commits need no restart. 0.1.19 also removes the launcher's Local/Hosted switch
  (amendment to API ADR 0001): the local API always runs Local, and hosted data is reached
  through the deployed API.
- 0.1.20 requires SDK 9.0.6 and retries runtime-access requests that time out during hosted
  endpoint discovery.
- README, `docs/library.md`, `examples/README.md` and both examples described a per-project
  local API; they now describe the laptop's one local API, and
  `tests/test_migration_guidance.py` fails on the retired wording. No code changed: the
  examples already call `configure_local_client()` without arguments (0.1.19 removed its
  `project` parameter), and the runtime still reports `local_mode`, which `--local` requires
  together with the SQLite dialect and a ready bootstrap.
- The only foreign key in this repository, `DemoBarsTS.asset_identifier` →
  `ms_markets__asset.unique_identifier`, has been `ON DELETE RESTRICT` since the table was
  introduced. The asset keys of ms-markets' own time-series tables (`AssetSnapshotsTS`,
  `ExternalPricesTS`, `SignalWeightsTS`, `PortfolioCashFlowsTS` and others) use the same action.
  It was never changed to work around MetaTables, so there is nothing to restore, and revision
  `0001` is unchanged.
- `.agents/skills/metatables/` was refreshed with `metatables copy-metatables-skills --path .`
  (0.1.20).

## SDK 9.0.5 and 9.0.6

- Since 9.0.5, `mainsequence code-repository sync` only refreshes local dependencies (`uv lock`,
  `uv sync`, `uv export --locked --no-dev --no-hashes`). It no longer bumps, tags, commits or
  pushes. Publishing is a plain `git push` plus the version tag, and workflow files decide what
  deploys; this repository declares none.
- 9.0.6 retries only read-only requests, with exponential backoff inside one timeout budget,
  and never replays a POST, PUT, PATCH or DELETE. This package has no retry logic of its own.
  Caller verification's PyJWT and cryptography moved into the base package, so the `server`
  extra is gone; this package never installed it. 9.0.6 also documents that a workflow
  declaration owns its target (ADR-077) and that a matching tag deploys the commit it points at.
  Neither applies to a repository without a workflow file.
- `.agents/skills/mainsequence/` is the SDK 9.0.6 bundle; 9.0.6 changed its
  `code_repository_maintenance` and `orchestration_and_releases` skills. The managed AGENTS.md
  block, regenerated offline, was already current. Each vendored `PINNED_FROM.txt` keeps a
  package-relative `skills_path`.

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

### Re-run on MetaTables 0.1.20

A first attempt on 2026-10-04 could not start. Before the local API reports ready, its worker
resolves the developer through the platform (`/api/v1/users/me/`) with the saved SDK session, and
the Main Sequence backend did not answer, so the launcher's 45-second startup deadline passed.

Later on 2026-10-04, signed in to the development backend, the re-run passed with
`mainsequence` 9.0.6, `mainsequence-metatable` 0.1.20 and ms-markets 2.2.5. It used a fresh
scratch `METATABLES_LOCAL_STORAGE_DIR` for every command, its own
`metatables serve --local --port <free port> --configuration <scratch configuration>` (so
`--local` read that directory's `server.json`, never the laptop's default local API), and
`metatables --local` only. The API was stopped afterwards and its `server.json` was removed.

1. `metatables --local runtime initialize` reported bootstrap `ready`, system revision
   `0010_cascade_targets` with no pending revisions, and a local SQLite DataSource; runtime
   status reported `local_mode: true` and `dialect: sqlite`.
2. The ms-markets 2.2.5 provider applied to the same runtime as a
   local-only prerequisite: revision `0018`, 62 tables finalized, 62 active, 0 reserved and
   0 failed; `migrations current` reported `0018 (head)`.
3. This repository's provider finalized:

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

   A repeated upgrade reported `migrated: False`, `finalized_count: 0` and both tables active.
4. The catalog held 64 MetaTables, all `active` (62 `ms_markets`, 2 `etfhextractor_markets`),
   none reserved or failed. `etfhextractor_markets__alembic_version`,
   `etfhextractor_markets__demobarsts` and `ms_markets__asset` were active in the local
   DataSource, and `DemoBarsTS` is a `TimeIndexMetaTable` with index names
   `["time_index", "asset_identifier"]` and time index `time_index`.
5. `get_impact(action="delete_rows")` on `ms_markets__asset` returned `allowed: true`, no
   blockers, 23 nodes and 34 foreign-key edges: 6 `cascade_delete` and 28 `restrict`, including
   `etfhextractor_markets__demobarsts` → `ms_markets__asset` (`on_delete=restrict`). On
   `etfhextractor_markets__demobarsts` it returned `allowed: true` and no edges.
6. `examples/prepare_demo_bars_schema.py --local --check-only` and `--local` both passed (the
   second was a no-op upgrade). Run through `configure_local_client()`,
   `metatables.upgrade_application("etfhextractor_migrations:migration")`, the call a consuming
   application's migration Job makes, reported revision `0001`, `ok: True`, `migrated: False`,
   2 active, 0 reserved and 0 failed.

The 0.1.20 runtime therefore reproduces the 0.1.18 proof for this repository, as expected:
neither provider changed, ms-markets 2.2.5 has the same models and migration history as 2.2.2,
and MetaTables 0.1.19 and 0.1.20 add no system migration.

## Validation

```bash
uv run pytest -q
uv run ruff check --no-fix .
uv run python -m metatables.sdk_compat
```

Not verified: the hosted migration state, live provider extraction, a live portfolio run, and
the full example against the local runtime, which needs live iShares and OpenFIGI calls.
