# Status

## Verified

- Release version is `0.4.1`; runtime is Python `3.13`. `pyproject.toml` declares
  `mainsequence>=9.0.1,<10`, `mainsequence-metatable>=0.1.5,<0.2` and `ms-markets>=2,<3`
  (implementation task 0006).
- On 2026-10-01 the migration was verified offline, with IP and DNS blocked including loopback,
  against `mainsequence` 9.0.2, `mainsequence-metatable` 0.1.5 and ms-markets 2.0.0. ms-markets
  2.0.0 was installed from its local `main` (b751b2c) because it is not on PyPI yet.
- The `metatables` 0.1.5 and ms-markets 2.0.0 skill bundles are copied. The SDK bundle under
  `.agents/skills/mainsequence/` is still the SDK `8.0.7` copy; it was not refreshed
  (mainsequence-sdk#181).
- Provider URL/ticker extraction, holdings-category planning/sync, FIGI registration,
  `ETFHoldingsSignal`, portfolio publication, and the demo-bars updater remain present.
- `DemoBars` uses `_required_output_table()` and frame validation uses `output_table`.
- MetaTables imports come from `metatables`. Registered portfolio price tables resolve through
  `metatables.TimeIndexTableRef.from_uid`; explicit `TimeIndexTableUpdater` dependencies remain
  executable updater instances. Updaters run with a bare `run()`.
- `build_etf_tracking_portfolio(...)` exposes the complete reusable calendar/signal/Portfolio/
  `PortfoliosDataNode` graph and builds `ImmediateSignal()` without a calendar key, as
  ms-markets 2.x requires. The Portfolio row still carries the persisted calendar FK.
  `publish_etf_tracking_portfolio(...)` retains the JSON summary contract used by
  `etfh portfolio-publish`.
- The migration provider owns only `etfhextractor_markets__demobarsts`, with the version table
  `etfhextractor_markets__alembic_version` and revision `0001`. `AssetTable` remains in the
  metadata solely to close the foreign-key graph and is excluded from provider DDL.
- The default IVV/ishares signal uid computes offline to `495a8b180d0a216e563cd3f83316da7f` on
  both the SDK 8 and the SDK 9 stacks.
- From 2026-09-02, under SDK 8: CodeRepository UID `2b634665-d3c0-4cf4-a8ed-f4446eba7891` and
  branch `main`. Backend migration `0001 (head)`; the registry and the demo-bars MetaTable were
  active. A live iShares IVV read returned 508 holdings dated 2026-08-31. None of this was
  re-checked under SDK 9.

## Validation

- Full pytest suite: 87 passed, with no network attempts.
- `ruff check --no-fix .` passed. Vendored `.agents/` skills are excluded from ruff.
- `python -m metatables.sdk_compat` passed.
- `uv pip check --python .venv/bin/python`: all installed packages compatible.
- `etfhextractor_migrations:migration` loads offline through
  `metatables.load_alembic_metatable_migration_provider`.

## Pending

- Regenerate `uv.lock` and `requirements.txt` once ms-markets 2.0.0 is on PyPI. They still
  record the SDK 8 resolution.
- Verify the backend with `metatables migrations current --provider
  etfhextractor_migrations:migration`. No migration was run against any database.
- Live msm SQL with `mainsequence-metatable` 0.1.5 is blocked by MetaTables#9.
- A live portfolio `node.run()` still requires a caller-owned registered price source and a fully
  registered component universe.
