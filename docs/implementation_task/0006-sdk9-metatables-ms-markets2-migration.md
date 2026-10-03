# 0006 — SDK 9, MetaTables client and ms-markets 2 migration

Status: implemented and verified offline. Regenerating `uv.lock` and `requirements.txt`, and
checking the backend migration state, are release steps: ms-markets 2.0.0 is not on PyPI yet.

Superseded for migrations by [0007](0007-deployment-job-migrations.md): since 0.4.3 a session
migrates only a local runtime (`metatables --local migrations ...`), and hosted runtimes are
migrated only by the migration Job of the application that deploys these tables.

## Goal

Move `etfhextractor` off the MetaTables code that shipped inside Main Sequence SDK 8 without
removing or bypassing any capability: provider extraction, holdings-category sync, FIGI
registration, `ETFHoldingsSignal`, the reusable portfolio builder and `etfh portfolio-publish`,
the demo-bars example, and the project migration provider.

## Dependency contract

- Python: `>=3.13,<3.14`
- `mainsequence>=9.0.2,<10`
- `mainsequence-metatable>=0.1.6,<0.2` (imported and run as `metatables`; the unrelated PyPI
  project named `metatables` must not be installed)
- `ms-markets>=2,<3`

The migration first shipped with `mainsequence>=9.0.1` and `mainsequence-metatable>=0.1.5`. The
floors moved to the releases that ms-markets 2.0.0 also requires:

- `mainsequence` 9.0.2 copies the SDK-owned skills offline, without a signed-in session.
- `mainsequence-metatable` 0.1.6 takes the DataSource and the SQL dialect from the runtime that
  the caller's Organization Environment selects (see [Runtime DataSource](#runtime-datasource)),
  ships only `metatables` packages, and scopes hosted table discovery to the Environment.

## API migrations

| SDK 8 / ms-markets 1.0.2 | SDK 9 / `metatables` / ms-markets 2 |
|---|---|
| `mainsequence.meta_tables.TimeIndexTableRef`, `TimeIndexTableUpdater` | `metatables.TimeIndexTableRef`, `metatables.TimeIndexTableUpdater` |
| `mainsequence.meta_tables.migrations` helpers | `metatables.migrations` (same names and keywords) |
| `mainsequence.meta_tables.migrations.env.run_mainsequence_alembic_env` | `metatables.migrations.env.run_mainsequence_alembic_env` |
| `mainsequence.client.metatables.TimeIndexMetaTable` | `metatables.TimeIndexMetaTable` |
| `mainsequence migrations <command>` | `metatables migrations <command> --provider etfhextractor_migrations:migration` |
| `updater.run(debug_mode=True, force_update=True)` | `updater.run()`: SDK 8.1 removed both controls, and every run executes immediately in-process |
| `ImmediateSignal(calendar_key=...)` | `ImmediateSignal()`: ms-markets 1.0.7 removed calendar keys from rebalance strategies ([ADR 0006 amendment](../adr/0006-trading-calendar-and-backtest-bootstrap.md)) |

`build_etf_tracking_portfolio(...)` and `publish_etf_tracking_portfolio(...)` no longer accept
`debug_mode`. SDK 8.0.7 already forced it to `True`, and the SDK 9 updater `run()` rejects it.
No other public name changed. `examples/prepare_demo_bars_schema.py` runs the CLI as
`python -m metatables.cli.app` under its own interpreter, because the package has no
`python -m metatables` entry point.

The repository never used the removed SQL-scope interfaces (`compile_markets_statement` scope
arguments, `scope_table`, `reserved_policy`), so the ms-markets 2.0.0 compiler changes need no
edits here.

## Migration provider

`etfhextractor_migrations:migration` keeps its package (`etfhextractor`), namespace
(`etfhextractor`, overridable through `MSM_AUTO_REGISTER_NAMESPACE`), model registry
(`DemoBarsStorage` only), version table `etfhextractor_markets__alembic_version`, and revision
`0001`. Only its imports changed.

## Runtime DataSource

Neither this package nor msm passes a `data_source_uid`: `msm.start_engine(...)` and
`msm.bootstrap.resolve_runtime(...)` build the runtime context without one. From
`mainsequence-metatable` 0.1.6 the compiler then takes the DataSource and the SQL dialect
together from the runtime of the MetaTables API that the caller's Organization Environment
selects. No API URL or DataSource setting is needed; `METATABLES_API_URL` only selects a loopback
development API. A runtime without a usable DataSource raises
`metatables.DataSourceResolutionError`. Hosted table discovery, including the schema-prep
example's lookup by physical table name (`TimeIndexMetaTable.filter_by_body`), is scoped to the
same Environment.

The offline tests replace the markets runtime and never run the real compiler, so they need no
runtime stub.

## SDK changes checked between 8.0.7 and 9.0.x

- 8.1.0 removed the `Scheduler` client and the cadence-driven run controls, so the `run()` calls
  were migrated.
- 8.1.17 to 8.1.19 removed Agent `respond()`/`stream_response()`, `CodingAgentService`,
  `agent_type`, and caller-selected Environment inputs on Agent lists. This repository uses none
  of them.
- SDK 9 keeps the session in the operating-system credential store, reads only the endpoint from
  `.env`, and replaces `code-repository refresh-token` with `mainsequence refresh-token`. The
  README and the examples README now say so.
- `LoggedUserContextMiddleware`, `_CURRENT_AUTH_HEADERS` and `_CURRENT_USER` are not used in
  code.
- `mainsequence.logconf.logger`, used for FIGI-registration logs, is unchanged.
- 9.0.2 makes `update-agent-skills` an offline copy of the installed SDK bundle that replaces all
  of `.agents/skills/mainsequence/`, and moves platform-owned skills to
  `.agents/skills/mainsequence_platform/` (authenticated `update-platform-skills`).

## Vendored skills

- `.agents/skills/metatables/` is the `mainsequence-metatable` 0.1.6 bundle, copied with
  `uv run metatables copy-metatables-skills --path .`. Its reference examples now live under
  `references/src/metatables/examples/`.
- `.agents/skills/ms_markets/` was refreshed with `msm copy-msm-skills --path .` from ms-markets
  2.0.0. Its packaged examples still show `run(debug_mode=True, force_update=True)`, which the
  2.0.0 updaters reject.
- `.agents/skills/mainsequence/` is the SDK 9.0.2 bundle, copied with
  `uv run --offline mainsequence code-repository update-agent-skills --path .`. The retired
  `data_access/` and `data_publishing/` MetaTable skills are gone,
  `maintenance/metatables_transition` was added, and the platform-owned skills are no longer
  mirrored into this namespace. The authenticated `update-platform-skills`, which installs them
  under `.agents/skills/mainsequence_platform/`, was not run.
- The managed AGENTS.md block was regenerated from the SDK 9.0.2 template with
  `uv run --offline mainsequence code-repository update AGENTS.md --path .`, replacing the
  earlier hand edits; it routes MetaTables work to `.agents/skills/metatables/`. The
  project-specific instructions outside the managed markers are unchanged.
- Every `PINNED_FROM.txt` records a package-relative `skills_path` instead of a local path.

## Known upstream issues

This is tracked upstream and is not worked around here.

- MainSequenceMarkets#14: ms-markets ships a top-level `migrations` package.

## Validation

All checks ran offline, with every IP connection and DNS lookup blocked, loopback included. They
were rerun against `mainsequence` 9.0.2 and `mainsequence-metatable` 0.1.6 (`sdk_compat` reports
distribution 9.0.2):

```bash
uv run python -m metatables.sdk_compat
uv run ruff check --no-fix .
uv run pytest -q
python -c "from metatables import load_alembic_metatable_migration_provider as load; print(load('etfhextractor_migrations:migration').package)"
```

Not verified: the backend migration state
(`metatables migrations current --provider etfhextractor_migrations:migration`), live provider
extraction, and a live portfolio run. They need the platform and the regenerated lockfile.
