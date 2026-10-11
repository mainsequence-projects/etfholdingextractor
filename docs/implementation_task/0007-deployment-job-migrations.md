# 0007 — SDK 9.0.22, MetaTables 0.1.34 and deployment-Job migrations

Status: implemented in 0.4.3, which was never published, and released in 0.4.4 on the newer
dependencies below. The provider was proven on isolated local SQLite runtimes against the real
ms-markets schema: on 2026-10-03 with MetaTables 0.1.18 and ms-markets 2.2.2, on 2026-10-04 with
0.1.20 and 2.2.5, and on 2026-10-11 with MetaTables 0.1.34, ms-markets 2.2.10 and SDK 9.0.22 (see
"Local migration proof"). No hosted runtime was read or migrated.

## Goal

Move `etfhextractor` to `mainsequence` 9.0.22, `mainsequence-metatable` 0.1.34 and ms-markets
2.2.10 (0.4.4; the unpublished 0.4.3 had 9.0.6, 0.1.20 and 2.2.5), and adopt the MetaTables
migration recommendation introduced in 0.1.14
(`docs/client/deploy-application-migrations.md` in the vendored `metatables` skills):

1. Develop locally: author and apply revisions with `metatables --local migrations ...`.
2. Commit each revision with the code that needs it.
3. Deploy: the application's `.mainsequence/workflows/` file runs a migration Job that calls
   `metatables.upgrade_application(...)` for its providers, in dependency order, before the
   resources that use the tables roll out. Hosted runtimes are migrated only by that Job.

## Dependency contract

- `mainsequence>=9.0.22,<10` (locked 9.0.22)
- `mainsequence-metatable>=0.1.34,<0.2` (locked 0.1.34)
- `ms-markets==2.2.10`, exactly the release the deployed MainSequence Markets runs. 2.2.11 is
  declared in the ms-markets repository but is not used; moving to it needs a new release of
  this package.
- `requires-python >=3.13,<3.14`, which ms-markets 2.2.10 requires.

`uv lock --upgrade-package` moved only these three packages. The new packages in the lock come
from the targets: the MetaTables client requires `mainsequence[mcp]` (since 0.1.24) and
`fastembed`, which bring `mcp`, `onnxruntime`, `tokenizers` and `huggingface-hub`. In 0.4.3 the
lock had dropped the SDK's `server` extra, which 9.0.6 folded into the base package.
`requirements.txt` was regenerated with the command in its header.

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
- Before that application pushes a lock on 0.4.4, which brings the `mainsequence-metatable`
  0.1.34 client into its migration Job:
  - its Environment's hosted MetaTables API must run 0.1.32 or later. Since 0.1.32 the client
    sends changed authored descriptions, labels and column metadata in each finalization batch
    (`authored_metadata`), also at an unchanged revision, and the API's `FinalizeManagedRequest`
    forbids unknown fields, so an older API rejects the request. MetaTables runs 0.1.34 in
    Production and development (checked 2026-10-11);
  - the migration Job declares `access.branches: [{repository: MetaTables, level: view}]`;
  - the Team that owns the application's tables in that Environment (MetaTables 0.1.27) has
    Writer on the `etfhextractor` namespace, which holds both `DemoBarsTS` and the version table,
    and its members include the migration Job's workload User and every workload that reads or
    writes `DemoBarsTS`. Otherwise reservation fails with `403` `namespace_not_writable` or
    `table_not_editable`.

  The 0.1.19 prerequisite of 0.4.3 no longer applies. A 0.1.20 client rejected the runtime
  context of an API on 0.1.18 or older, because `RuntimeContext` forbade the runtime-switch
  fields such an API still sends. MetaTables 0.1.21 made the runtime-context models ignore
  unknown fields, so either side can be upgraded first
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
- In 2.2.5 the history is one revision, `0018_initial_schema`. Consumers never apply it.
- `.agents/skills/ms_markets/` was refreshed with `msm copy-msm-skills --path .`. The 2.2.2
  refresh removed the Command Center Asset Monitor skills, which 2.2.0 dropped; the 2.2.5 refresh
  changed only the pin. Its `metatable_migrations` skill states the same migration rule.

## ms-markets 2.2.5 to 2.2.10 (0.4.4)

- 2.2.6 requires `mainsequence>=9.0.19` and `mainsequence-metatable>=0.1.33`, adds revision
  `0019` (it removes the portfolio event ledger's unique constraint that excluded the
  TimescaleDB partition key), installs the SDK request identity in the Markets API, and gives the
  Markets workloads Writer on the `mainsequence.markets` namespace through
  `scripts/bootstrap_metatables_access.py` and the Team `ms-markets-<environment>`.
- 2.2.7 adds the anchor `0017_legacy_schema_anchor` and the merge revision `0020`, so populated
  databases at the retired `0017` head upgrade forward. A fresh runtime now reports
  `0020 (head) (mergepoint)`. Consumers still never apply this history.
- 2.2.8 to 2.2.10 give the Markets migration Job and API startup a 300-second MetaTables
  discovery budget and retry transient startup failures.
- This repository uses none of these surfaces. All 63 distinct imports from `msm`,
  `msm_portfolios`, `metatables` and `mainsequence` in the package, the migration provider, the
  examples and the tests resolve on 2.2.10, 0.1.34 and 9.0.22 (51 of them from `msm` and
  `msm_portfolios`, as before).
- The pin is exact (`==2.2.10`) because the deployed MainSequence Markets runs 2.2.10; a
  consumer that locks this package resolves the same release.
- `.agents/skills/ms_markets/` was refreshed to 2.2.10; its `metatable_migrations` skill now
  says every Environment needs the Markets MetaTables access bootstrap.

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

## MetaTables 0.1.20 to 0.1.34 (0.4.4)

- 0.1.21 makes the runtime-context models ignore fields they do not know, so client and API can
  be upgraded in either order (MetaTables#33), and its hosted API installs the SDK request
  identity.
- New system migrations: `0011_table_search` (0.1.22) and `0012_table_creator`. A fresh local
  runtime on 0.1.34 initializes through `0012_table_creator`. The laptop's shared local file is
  at the newest system migration any project applied, so a project whose client predates it
  must upgrade `mainsequence-metatable`.
- 0.1.24 requires `mainsequence[mcp]>=9.0.19`; with `fastembed` this brings `mcp`,
  `onnxruntime`, `tokenizers` and `huggingface-hub` into every consumer's environment.
- 0.1.27: one platform Team per Environment owns an application's tables, with the
  application's workload Users as members. A table registered in a namespace the caller already
  writes gets no grant of its own, and a refused registration answers `403`
  `namespace_not_writable` or `table_not_editable` with the caller's User UID.
- The client finalizes at most 10 tables per request, the version table first (0.1.28); hosted
  migration connections pin `search_path=public` and misplaced provider tables are refused
  (0.1.29); inventories and inspections are batched, a waking API gets up to 300 seconds, and
  unchanged contracts cause no catalog writes (0.1.31).
- 0.1.32 sends changed authored descriptions, labels and column metadata with finalization, also
  at an unchanged revision. This needs an API on 0.1.32 or later (see "The recommendation,
  applied to a library"). 0.1.33 changes no source, and 0.1.34 changes only the API, which
  re-owns populated time-index tables before TimescaleDB hypertable conversion.
- `DemoBarsTS` keeps `ON DELETE RESTRICT`, and revision `0001` is unchanged.
- `.agents/skills/metatables/` was refreshed to 0.1.34, which adds the
  `metatables-table-discovery` skill.

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

## SDK 9.0.6 to 9.0.22 (0.4.4)

- This package calls the SDK directly only through `mainsequence.logconf`; everything else goes
  through the ms-markets and MetaTables clients. `python -m metatables.sdk_compat` finds
  compatible interfaces on 9.0.22.
- The 9.0.22 skill bundle adds guidance on serving MCP tools and requester-bound calls
  (`api_surfaces`), on `acts_for_requester` (`access_control_and_sharing`), on the 90-second A2A
  Message limit and on named provider credentials. None of it applies to a library without an
  API or an Agent. No skill folder was added or removed.
- The 9.0.22 managed AGENTS.md block differs from the committed one by one routing line: the
  access-control route also covers whether an application uses its own grants or acts for its
  requester. The block was not regenerated, because the AGENTS.md rules make
  `mainsequence code-repository update AGENTS.md --path .` a separate, explicit update.
- The copy commands of all three packages write an absolute site-packages `skills_path` into
  `PINNED_FROM.txt`; it was set back to the package-relative path, as before.

## Provider identity (0.4.4)

`tests/test_provider_identity.py` pins what consumers' migration Jobs depend on: package and
namespace `etfhextractor`, provider key `etfhextractor:etfhextractor`, script and version
locations inside `etfhextractor_migrations`, `DemoBarsStorage` as the only model, version table
`etfhextractor_markets__alembic_version` (`etfhextractor.alembic_version`), a history of exactly
`0001`, and `DemoBarsTS`'s identifier, physical table, foreign key and unique index. Two tests
check that the models still produce exactly revision `0001` on the installed stack: Alembic's
autogenerate comparison on SQLite, with the provider's include filters and the type and
server-default comparison the MetaTables migration environment uses, reports no difference, and
on PostgreSQL the offline DDL of `0001` equals the DDL compiled from the model. A column added to
the physical table makes the SQLite check report it, so the filters do not hide the table.

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

### Re-run on MetaTables 0.1.34 (0.4.4)

On 2026-10-11, signed in to the development backend, the proof passed with `mainsequence`
9.0.22, `mainsequence-metatable` 0.1.34 and ms-markets 2.2.10. Every command used a fresh scratch
`METATABLES_LOCAL_STORAGE_DIR`, a scratch configuration (`local_mode_available: true`, credential
keys in a scratch directory rather than the Keychain) and `metatables --local` only. The API was
`metatables serve --local --port <free port> --configuration <scratch configuration>`, started
from this checkout because 0.1.34 requires a Git checkout there; it wrote nothing into the
checkout. The laptop's shared local API and runtime file were not touched. The API was stopped
afterwards and removed its `server.json`.

1. Before initialization, `runtime status` reported `local_mode: true`, the scratch SQLite file
   as candidate, and `0001_initial` through `0012_table_creator` pending.
   `metatables --local runtime initialize` reported bootstrap `ready`, revision
   `0012_table_creator` and nothing pending; status then reported `local_mode: true`,
   `dialect: sqlite` and a local SQLite DataSource.
2. The ms-markets 2.2.10 provider applied as a local-only prerequisite: `-> 0018`,
   `0018 -> 0019`, `0018 -> 0017` and `0017, 0019 -> 0020`; 62 tables finalized, 62 active,
   0 reserved and 0 failed; `migrations current` reported `0020 (head) (mergepoint)`.
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

   Both catalog rows carry migration package and namespace `etfhextractor`, provider key
   `etfhextractor:etfhextractor` and revision `0001`: `etfhextractor.alembic_version` on
   `etfhextractor_markets__alembic_version`, and the time-indexed `etfhextractor.DemoBarsTS` on
   `etfhextractor_markets__demobarsts`. A repeated upgrade reported `migrated: False`,
   `finalized_count: 0` and both tables active.
4. The catalog held 64 MetaTables, all `active` (62 `ms_markets`, 2 `etfhextractor_markets`).
   `DemoBarsTS` is a `TimeIndexMetaTable` with index names `["time_index", "asset_identifier"]`
   and time index `time_index`.
5. `get_impact(action="delete_rows")` on `ms_markets__asset` returned `allowed: true`, no
   blockers, 23 nodes and 34 foreign-key edges (6 `cascade_delete`, 28 `restrict`), including
   `etfhextractor_markets__demobarsts` → `ms_markets__asset` through
   `fk__etfhextractor_markets__demobarsts__asset_identif_aa195e0879` (`on_delete=restrict`). On
   `etfhextractor_markets__demobarsts` it returned `allowed: true` and no edges.
6. `examples/prepare_demo_bars_schema.py --local --check-only` and `--local` both passed (the
   second was a no-op upgrade). Through `configure_local_client()`,
   `metatables.upgrade_application("etfhextractor_migrations:migration")` reported revision
   `0001`, `ok: True`, `migrated: False`, 2 active, 0 reserved and 0 failed.

The results match the earlier proofs: the provider is unchanged, and the new ms-markets
revisions and MetaTables system migrations do not touch `DemoBarsTS`.

## Local end-to-end run on 0.4.4

On the same scratch runtime the library's own code then ran end to end. Two external calls were
replaced by deterministic fixtures, so nothing left the laptop: the provider extraction
(`ETFHoldingsReader.read_ticker` returned a fund `ETFHPROOF` holding `ETFHA` 40, `ETFHB` 35,
`ETFHC` 25 and a cash row) and the OpenFIGI mapping (`query_figi` returned the synthetic FIGIs
`BBGETFH00001` to `BBGETFH00003`).

What passed:

- Shared runtime model composition. `start_portfolio_engine(extra_models=[DemoBarsStorage])`
  attached one runtime with 36 models, and both the category path (`_ensure_msm_started`) and
  `start_portfolio_engine()` without extra models reused it instead of starting another engine.
- FIGI registration and snapshot-layer resolution, with the workaround in item 1 below: three
  assets registered with their OpenFIGI details and snapshots, the three tickers then resolved,
  and a second registration wrote nothing.
- Category planning: `HOLDINGS__ETFHPROOF` with three components and no blockers;
  `sync_holdings_asset_category` returned the three members on both runs (but see item 2).
- `ensure_trading_calendar("NYSE", backtest_start_days=60)` persisted the NYSE calendar
  (2026-07-13 to 2027-10-12), and a second call reused it.
- Demo bars: 375 rows (125 NYSE session closes for 3 assets) in `DemoBarsTS`; publishing them
  again added no row.
- Portfolio publishing: the graph `build_etf_tracking_portfolio` assembles wrote 3 signal-weight
  rows (0.40, 0.35 and 0.25 after renormalization) on the 2026-08-12 NYSE close, the 60-day
  backtest bootstrap; 42 portfolio value rows on session closes (the first close 0.99982 after
  the 0.00018 commission); and 3 portfolio weight rows. The `Portfolio` row
  `etf_tracker_etfhproof` references the NYSE calendar. Two further runs added no row (the
  signal's same-day guard) and kept the same `signal_uid` and Portfolio UID.

What failed, in ms-markets 2.2.10 itself. Each was reproduced without etfhextractor code, and
the code involved is identical in 2.2.5:

1. Every insert into the Asset table fails on local SQLite with `400`
   `compiled_sql_database_error: access to ms_markets__interpolatedpricests.asset_identifier is
   prohibited`. Revision `0018_initial_schema` creates `ms_markets__interpolatedpricests` with a
   foreign key to `ms_markets__asset`, but the ms-markets provider does not register
   `InterpolatedPricesStorage` (it registers 61 models), so the table has no catalog binding.
   SQLite's foreign-key check for an upsert into the parent reads it, and the local API's SQL
   authorizer refuses tables without a binding. Importing that relation into the scratch catalog
   with `MetaTable.import_from_data_source(..., relation_names=["ms_markets__interpolatedpricests"])`
   made plain `Asset.upsert` and `Asset.create` succeed; the rest of the run used it.
2. `AssetCategory.replace_memberships` leaves the category empty on SQLite while returning the
   upserted rows. Its stale-row delete binds `category_uid` as 32-character hex, as stored, but
   the `NOT IN` asset UIDs as dashed strings, so it deletes every row it has just upserted.
   `sync_holdings_asset_category` therefore reports three members and none are stored.
3. `PortfoliosDataNode.run()` fails after the whole update tree has run: its
   `_update_portfolio_pointers` passes `str(uid)` values into `Uuid(as_uuid=True)` columns of the
   Portfolio table, and SQLite's character-based UUID processor raises
   `'str' object has no attribute 'hex'`. `build_etf_tracking_portfolio(run=True)`, and with it
   `etfh portfolio-publish`, raise on a local runtime after the rows are written, and the
   `Portfolio` row's `signal_uid` and data-node pointers stay empty. The same graph run with
   `node.run(update_pointers=False)` completes.

PostgreSQL enforces foreign keys inside the database and stores UUIDs natively, so these paths
are expected to work on hosted runtimes; that was not verified here. They belong to ms-markets,
and this package does not work around them.

## Validation

```bash
uv run pytest -q                # 101 passed
uv run ruff check --no-fix .
uv run python -m metatables.sdk_compat
```

Not verified: the hosted migration state, live provider extraction and OpenFIGI calls, and any
run against a hosted runtime.
