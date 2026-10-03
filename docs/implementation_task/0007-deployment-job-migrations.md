# 0007 — SDK 9.0.5, MetaTables 0.1.14 and deployment-Job migrations

Status: implemented in 0.4.3. The provider was proven on an isolated local SQLite runtime. No
hosted runtime was read or migrated.

## Goal

Move `etfhextractor` to `mainsequence` 9.0.5, `mainsequence-metatable` 0.1.14 and ms-markets
2.1.1, and adopt the MetaTables 0.1.14 migration recommendation
(`docs/client/deploy-application-migrations.md` in the vendored `metatables` skills):

1. Develop locally: author and apply revisions with `metatables --local migrations ...`.
2. Commit each revision with the code that needs it.
3. Deploy: the application's `.mainsequence/workflows/` file runs a migration Job that calls
   `metatables.upgrade_application(...)` for its providers, in dependency order, before the
   resources that use the tables roll out. Hosted runtimes are migrated only by that Job.

## Dependency contract

- `mainsequence>=9.0.5,<10` (locked 9.0.5)
- `mainsequence-metatable>=0.1.14,<0.2` (locked 0.1.14)
- `ms-markets>=2.1.1,<3` (locked 2.1.1)

`uv lock --upgrade-package` moved only these three packages. `requirements.txt` was regenerated
with the command in its header.

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

## ms-markets 2.1.1

- `cli` and `command_center` were renamed `msm_cli` and `msm_command_center`. This repository
  imports neither, and its own CLI is the subpackage `etfhextractor.cli`.
- The history is one revision, `0018_initial_schema`. Consumers never apply it.
- `.agents/skills/ms_markets/` was refreshed with `msm copy-msm-skills --path .`; its
  `metatable_migrations` skill states the same rule.

## SDK 9.0.5

`mainsequence code-repository sync` only refreshes local dependencies (`uv lock`, `uv sync`,
`uv export --locked --no-dev --no-hashes`). It no longer bumps, tags, commits or pushes.
Publishing is a plain `git push` plus the version tag, and workflow files decide what deploys;
this repository declares none. `.agents/skills/mainsequence/` is the SDK 9.0.5 bundle (it adds
`mainsequence-inference`) and the managed AGENTS.md block was regenerated, both offline.

## Local migration proof

Every run used `METATABLES_LOCAL_STORAGE_DIR` set to an isolated scratch directory, a dedicated
local API port, and `metatables --local` only. The runtime reported `local_mode: true`,
`dialect: sqlite` and system revision `0009_timescale_policies` after
`metatables --local runtime initialize`.

`DemoBarsTS` has a foreign key to `ms_markets__asset`, and MetaTables finalization preflights
every foreign-key target. The provider therefore finalizes only in a runtime where the ms-markets
Asset table is a finalized MetaTable:

1. Standalone, in an empty runtime: Alembic applied `0001` on SQLite and the version registry
   became active, but `DemoBarsTS` stayed reserved with
   `physical_contract_reconciliation_failed`, because its foreign-key target does not exist in
   that runtime.
2. With the real ms-markets 2.1.1 schema: the MetaTables 0.1.14 API rejects the ms-markets
   provider, so its tables never finalize (see the next section). `DemoBarsTS` then failed with
   `foreign_key_target_columns_not_unique`; `migrations current` reported `0001 (head)`.
3. With a scratch-only stand-in provider that registers an exact replica of `ms_markets__asset`
   (msm's own `AssetTable` model, which has no outgoing foreign keys):

   ```text
   $ metatables --local migrations upgrade --provider etfhextractor_migrations:migration head
   [alembic] INFO alembic.runtime.migration: Running upgrade  -> 0001, etfhextractor_demo_bars
   ok: True
   finalized_count: 2
   active_count: 2
   failed_count: 0
   revision: 0001
   migrated: True
   $ metatables --local migrations current --provider etfhextractor_migrations:migration
   0001 (head)
   ```

   A repeated upgrade reported `migrated: False` with both tables active, and `DemoBarsTS` was
   registered as a `TimeIndexMetaTable` with index names `["time_index", "asset_identifier"]`.
   `examples/prepare_demo_bars_schema.py --local --check-only` and `--local` both passed against
   that runtime.

## Known upstream issues

The ms-markets 2.1.1 provider cannot finalize on a MetaTables 0.1.14 API. This is not worked
around here:

- `PortfolioEventLedgerStorage` has four identity dimensions, so the API's default
  secondary-index name is 70 characters long. Reservation fails with 422
  `secondary index name must be a valid PostgreSQL identifier` (63 characters at most).
- The `0018_initial_schema` tables declare cascading foreign keys. Finalization fails with 400
  `cascading_foreign_key_unsupported`; MetaTables 0.1.14 accepts only `RESTRICT` and
  `NO ACTION` on every backend.

Until ms-markets ships a fix, a fresh local runtime cannot hold a finalized ms-markets schema,
so the local example run and the end-to-end local proof of `DemoBarsTS` against the real
ms-markets tables remain open.

## Validation

```bash
uv run pytest -q
uv run ruff check --no-fix .
uv run python -m metatables.sdk_compat
```

Not verified: the hosted migration state, live provider extraction, and a live portfolio run.
