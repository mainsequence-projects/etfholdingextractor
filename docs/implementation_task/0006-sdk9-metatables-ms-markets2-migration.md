# 0006 — SDK 9, MetaTables client and ms-markets 2 migration

Status: implemented and verified offline. Regenerating `uv.lock` and `requirements.txt`, and
checking the backend migration state, are release steps: ms-markets 2.0.0 is not on PyPI yet.

## Goal

Move `etfhextractor` off the MetaTables code that shipped inside Main Sequence SDK 8 without
removing or bypassing any capability: provider extraction, holdings-category sync, FIGI
registration, `ETFHoldingsSignal`, the reusable portfolio builder and `etfh portfolio-publish`,
the demo-bars example, and the project migration provider.

## Dependency contract

- Python: `>=3.13,<3.14`
- `mainsequence>=9.0.1,<10`
- `mainsequence-metatable>=0.1.5,<0.2` (imported and run as `metatables`; the unrelated PyPI
  project named `metatables` must not be installed)
- `ms-markets>=2,<3`

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

## SDK changes checked between 8.0.7 and 9.0.x

- 8.1.0 removed the `Scheduler` client and the cadence-driven run controls, so the `run()` calls
  were migrated.
- 8.1.17 to 8.1.19 removed Agent `respond()`/`stream_response()`, `CodingAgentService`,
  `agent_type`, and caller-selected Environment inputs on Agent lists. This repository uses none
  of them.
- SDK 9 keeps the session in the operating-system credential store, reads only the endpoint from
  `.env`, and replaces `code-repository refresh-token` with `mainsequence refresh-token`. The
  README, the examples README, and AGENTS.md now say so.
- `LoggedUserContextMiddleware`, `_CURRENT_AUTH_HEADERS` and `_CURRENT_USER` are not used in
  code; the AGENTS.md identity rule was reworded.
- `mainsequence.logconf.logger`, used for FIGI-registration logs, is unchanged.

## Vendored skills

- `.agents/skills/metatables/` was copied with `metatables copy-metatables-skills --path .`
  (0.1.5).
- `.agents/skills/ms_markets/` was refreshed with `msm copy-msm-skills --path .` from ms-markets
  2.0.0. Its packaged examples still show `run(debug_mode=True, force_update=True)`, which the
  2.0.0 updaters reject.
- `.agents/skills/mainsequence/` is still the SDK 8.0.7 bundle. It was not refreshed
  (mainsequence-sdk#181), so its `data_publishing/` MetaTables skills are stale. AGENTS.md routes
  MetaTables work to the copied `metatables` skills.

## Known upstream issues

These are tracked upstream and are not worked around here.

- MetaTables#9: with `mainsequence-metatable` 0.1.5, compiling without an explicit
  `data_source_uid` raises `AttributeError`. msm builds its runtime context without one, so live
  msm reads and writes (category sync, ticker resolution, FIGI registration checks, portfolio
  runs) fail until it is fixed. The offline tests never run the real compiler.
- MetaTables#10: the wheel installs top-level `api` and `examples` packages. Nothing here imports
  `examples` as a package, and the example scripts run by path.
- MetaTables#11: table discovery is not Environment-scoped. The schema-prep example's lookup by
  physical table name (`TimeIndexMetaTable.filter_by_body`) goes through that discovery.
- MainSequenceMarkets#14: ms-markets ships a top-level `migrations` package.
- mainsequence-sdk#181: vendored SDK skills cannot be refreshed without a signed-in session.

## Validation

All checks ran offline, with every IP connection and DNS lookup blocked, loopback included:

```bash
uv run python -m metatables.sdk_compat
uv run ruff check --no-fix .
uv run pytest -q
python -c "from metatables import load_alembic_metatable_migration_provider as load; print(load('etfhextractor_migrations:migration').package)"
```

Not verified: the backend migration state
(`metatables migrations current --provider etfhextractor_migrations:migration`), live provider
extraction, and a live portfolio run. They need the platform and the regenerated lockfile.
