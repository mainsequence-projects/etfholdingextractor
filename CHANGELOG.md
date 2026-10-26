# Changelog

All notable changes to `etfhextractor` are recorded here. Earlier releases are described by
their Git tags and by the implementation tasks in `docs/implementation_task/`.

## [0.4.5] - Unreleased

Moves the library to ms-markets 3.0.0 and its Markets API boundary (ms-markets ADR 0047). Not
tagged yet: `uv.lock` and `requirements.txt` still resolve ms-markets 2.2.10 and are regenerated
once 3.0.0 is on PyPI.

### Changed

- Markets registries are reached only through `msm.api` row calls, and set-based ones where a
  call touches many rows. The library never selects the ms-markets row backend: the importing
  application does (`use_remote_backend(LazyRemoteBackend())` or `MSM_API_BACKEND=remote`), and
  on that backend every registry read and write runs on the Markets API and the library attaches
  no Markets registry table. On the default runtime backend it attaches the same tables as
  before.
  - Asset uids by identifier: one `Asset.get_many_by_unique_identifier` instead of
    `search_model` on `AssetTable`.
  - FIGI registration: one `Asset.upsert_many` and one `OpenFigiDetails.upsert_many` instead of
    one `Asset.upsert` and one `OpenFigiDetails.upsert` per new asset, and
    `AssetSnapshots.publish` instead of running `BatchVerifiedAssetSnapshot`. The snapshot rows
    are now written by ms-markets' own `AssetSnapshot` updater, which since 3.0 verifies
    duplicate keys in one read.
  - Always-open calendars: `CalendarDate.upsert_many` and `CalendarSession.upsert_many` (the
    conflict keys of ms-markets' materialization) instead of `materialize_calendar_rows` on a
    runtime context.
  - The example verifies its run through the updaters that wrote the rows and
    `Portfolio.get_by_unique_identifier` instead of `search_model` on the core tables.
- `start_portfolio_engine` attaches `portfolio_runtime_models(...)`: today's set on the runtime
  backend; on the remote backend only the portfolio time series, the asset snapshots and
  `extra_models`.
- Imports use the ms-markets 3.0 names (`msm.time_index`, `msm_portfolios.time_index`,
  `PortfoliosUpdater`, `AssetTimestampedUpdater`, `AssetUpdaterConfiguration`);
  `msm rename-preflight scan` is clean.
- The calendar helpers (`ensure_trading_calendar`, `required_calendar_window` and the calendar
  constants) moved to the light `etfhextractor.calendars` module, which imports neither ms-markets
  at import time nor the msm_portfolios stack. `etfhextractor.portfolio_publish` re-exports them
  and `etfhextractor.portfolio_signal` still exports `ALWAYS_OPEN_CALENDAR_KEYS`.

### Added

- Injection seams on `build_etf_tracking_portfolio` and `publish_etf_tracking_portfolio`, each
  defaulting to the earlier behaviour: `signal_output_table`, `portfolio_output_table`,
  `weights_output_table` and `rebalance_output_table` bind the signal and `PortfoliosUpdater`
  (and its weights and rebalance updaters) to an application's own contract instances;
  `register_datasets` records them in the Markets catalog with `PortfolioDatasets.register`
  after the run (by default when `portfolio_output_table` is given); `update_pointers=False`
  leaves the Portfolio pointers alone; `resolve_asset_identifiers_fn` replaces the
  asset-snapshot ticker resolver.
- `ETFHoldingsSignal.set_asset_identifier_resolver`, `portfolio_runtime_models`,
  `register_portfolio_datasets`, `EtfTrackingPortfolioBuild.portfolio_datasets` (in the summary
  only when registered), and `etfhextractor.markets_runtime`.
- `tests/test_markets_api_boundary.py` runs the library against a recording remote backend. It
  checks the resource and operation of every Markets call, that nothing is attached for
  registries, and that the library never selects the backend. It also guards that the
  asset-snapshot read is the only compiled SQL left on a Markets table. Another test pins the
  default IVV/ishares `signal_uid`.

### Upgrade notes for applications

- Run 0.4.5 only in an Environment whose Markets deployment runs ms-markets 3.0.0 and has
  applied its revisions.
- On the remote backend, every workflow resource that calls the library needs
  `access.branches: [{repository: MainSequenceMarkets, policy: reader}]`. Its workload User uid
  must also be listed in the Environment's `MARKETS_REGISTRY_WRITERS` constant under the
  write-policy resources of the calls it makes: `asset-category`, `asset-type`, `asset`,
  `open-figi-details`, `asset-snapshots`, `calendar`, `calendar-date`, `calendar-session`,
  `portfolio`, `signal-metadata`, `portfolio-datasets` (`docs/library.md`, "Markets Access").
- Still direct MetaTables access: the asset-snapshot read (ticker resolution and the
  registration snapshot check), which needs read access to `AssetSnapshotsStorage`, because no
  Markets API route serves it yet; and, unless instances are injected, the writes to the core
  signal-weights, portfolio-weights, rebalance-state and portfolio-values tables.
- A fresh signal instance keeps the `signal_uid` but has no history: copy the existing rows into
  the instances before the first bound run, never recompute (runbook in `docs/library.md`).
- On their first ms-markets 3.0 run, `ETFHoldingsSignal` and `PortfoliosUpdater` get a new
  `TimeIndexTableUpdate` (ms-markets 3.0 moved the modules their hashes name) and continue from
  their output table's last observation. `signal_uid` does not change: the default IVV/ishares
  uid still computes offline to `495a8b180d0a216e563cd3f83316da7f`.

### Unchanged

- The provider `etfhextractor_migrations:migration`, revision `0001`, `DemoBarsTS` and its
  identity; `BatchVerifiedAssetSnapshot` (no longer used by the library, kept for importers);
  every public name of the library and the `etfh` CLI.

### Not verified

- Everything was verified offline only (tests with outbound network blocked, against ms-markets
  3.0.0 installed from its development source): no run against a deployed Markets API or a local
  runtime, and the ms-markets 2.2.10 local SQLite defects listed under 0.4.4 were not re-checked.

## [0.4.4] - 2026-10-11

The first release after 0.4.2. It also ships everything listed under 0.4.3, which was never
published.

### Changed

- Require `mainsequence>=9.0.22,<10` and `mainsequence-metatable>=0.1.34,<0.2`, and pin
  `ms-markets==2.2.10`, the release the deployed MainSequence Markets runs. A consumer that locks
  this package resolves exactly ms-markets 2.2.10; moving Markets needs a new release.
  `requires-python` stays `>=3.13,<3.14`. `uv.lock` resolves 9.0.22, 0.1.34 and 2.2.10, and
  `requirements.txt` was regenerated from it. The MetaTables client now requires
  `mainsequence[mcp]` and `fastembed`, so `mcp`, `onnxruntime`, `tokenizers` and
  `huggingface-hub` are new transitive dependencies.
- Hosted prerequisites for a consumer's migration Job, which now runs the 0.1.34 client:
  - the Environment's MetaTables API must run 0.1.32 or later, because the client sends changed
    table and column metadata with finalization and older APIs reject it. MetaTables runs 0.1.34
    in Production and development;
  - the Job declares view access to the MetaTables repository;
  - the Team that owns the `etfhextractor` namespace in that Environment (MetaTables 0.1.27) has
    Writer on it, with the Job's workload User and every workload that reads or writes
    `DemoBarsTS` as members.

  The 0.1.19 prerequisite of 0.4.3 is gone: MetaTables 0.1.21 made the client ignore
  runtime-context fields it does not know
  ([MetaTables#33](https://github.com/mainsequence-projects/MetaTables/issues/33)).
- ms-markets 2.2.6 to 2.2.10 add revisions `0019` and `0020` to the ms-markets history, which
  the ms-markets deployment applies; this package's provider and models are unchanged. All 63
  imports from `msm`, `msm_portfolios`, `metatables` and `mainsequence` resolve on the new
  stack, and `python -m metatables.sdk_compat` passes on SDK 9.0.22.
- Refreshed the vendored skills: SDK 9.0.22 (`.agents/skills/mainsequence/`), `metatables`
  0.1.34, which adds `metatables-table-discovery`, and ms-markets 2.2.10. The managed AGENTS.md
  block was not regenerated; 9.0.22 changes one routing line in it, and that update is explicit.

### Added

- `tests/test_provider_identity.py`, which pins the provider's package, namespace, provider key,
  locations, model, version table and single revision `0001`, `DemoBarsTS`'s identifier,
  physical table, foreign key and unique index, and checks that the models still produce exactly
  revision `0001` on SQLite and PostgreSQL.
- The local migration proof re-run on MetaTables 0.1.34 with ms-markets 2.2.10 and SDK 9.0.22,
  and a local end-to-end run of the library, both recorded in implementation task
  [0007](docs/implementation_task/0007-deployment-job-migrations.md).

### Known issues

On a local SQLite runtime, three ms-markets 2.2.10 defects stop the asset-writing workflows:
Asset inserts are refused, `HOLDINGS__<ETF>` memberships are deleted right after they are
written, and a portfolio run fails on its final `Portfolio` pointer update after writing its
rows. They are in ms-markets (present in 2.2.5 too) and are described in implementation task
0007, "Local end-to-end run on 0.4.4".

### Unchanged

- The provider `etfhextractor_migrations:migration`: package and namespace `etfhextractor`,
  provider key `etfhextractor:etfhextractor`, version table
  `etfhextractor_markets__alembic_version`, revision `0001`.
- `DemoBarsTS` (`etfhextractor.DemoBarsTS`, `etfhextractor_markets__demobarsts`) and its
  `ON DELETE RESTRICT` foreign key to the ms-markets Asset table.
- Every public name of the library, the `etfh` CLI and the agent card's skills.

## [0.4.3] - 2026-10-04 (not published)

Never tagged on origin; these changes were first released in 0.4.4.

### Changed

- Require `mainsequence>=9.0.6,<10`, `mainsequence-metatable>=0.1.20,<0.2` and
  `ms-markets>=2.2.5,<3`. `uv.lock` resolves 9.0.6, 0.1.20 and 2.2.5, and `requirements.txt` was
  regenerated from it.
  - MetaTables 0.1.17 allows cascading foreign keys and adds the `get_impact` pre-flight, and
    0.1.18 makes write on a table depend only on that table's own grants. 0.1.19 runs one local
    API per laptop, which every checkout reaches through `server.json` in the local storage
    directory, so commits and branch switches no longer need an API restart; it also removes the
    launcher's Local/Hosted switch. 0.1.20 requires SDK 9.0.6 and retries runtime-access
    requests that time out.
  - Before a consumer that locks 0.4.3 pushes, its Environment's hosted MetaTables API must run
    0.1.19 or later. The 0.1.20 client rejects the runtime context of an older API, which still
    sends the runtime-switch fields that 0.1.19 removed, so the consumer's migration Job fails
    before it migrates anything
    ([MetaTables#33](https://github.com/mainsequence-projects/MetaTables/issues/33)).
  - SDK 9.0.6 retries only read-only requests, within one timeout budget, and never replays a
    write; caller verification no longer needs a `server` extra. This package has no retry logic
    of its own and installs no extra.
  - ms-markets 2.2.2 requires MetaTables 0.1.17 or later and gives `PortfolioEventLedgerTS` an
    explicit storage layout, so the ms-markets schema applies to a fresh local runtime. 2.2.3
    reports cascade impact in the bulk-delete preflights, and 2.2.4 and 2.2.5 omit unset fields
    from the Command Center contract models; the models and migrations are unchanged since
    2.2.2. This package imports nothing that ms-markets 2.2.0 removed (`msm_command_center`, the
    `apps/v1` re-exports).
- Adopt the MetaTables deployment-Job migration recommendation (introduced in 0.1.14). Hosted
  runtimes are migrated only by a deployment workflow's migration Job. etfholdingextractor has no
  deployment, so the application that deploys code using `DemoBarsTS` applies
  `etfhextractor_migrations:migration` in its own migration Job. Local development uses
  `metatables --local migrations upgrade --provider etfhextractor_migrations:migration head`.
  Neither this package nor its consumers apply the ms-markets provider; the ms-markets deployment
  migrates that schema.
- `examples/prepare_demo_bars_schema.py` no longer migrates hosted runtimes. `--local` applies
  the provider to the laptop's local MetaTables runtime after checking that it is an initialized
  local SQLite runtime; without `--local` the script only verifies that `DemoBarsTS` is
  registered.
- `examples/ivv_tracking_portfolio_full_workflow.py` gained `--local` and no longer cites the
  generic top-level `migrations` provider or hosted upgrades.
- README, `docs/library.md`, `examples/README.md` and the AGENTS.md project text document who
  applies the provider, and that since SDK 9.0.5 `mainsequence code-repository sync` only
  refreshes local dependencies; publishing is a plain `git push` plus the version tag. README,
  `docs/library.md`, `examples/README.md` and both examples describe the laptop's one local
  MetaTables API, which every checkout shares.
- Refreshed the vendored skills: SDK 9.0.6 (`.agents/skills/mainsequence/`, plus the managed
  AGENTS.md block), `metatables` 0.1.20 and ms-markets 2.2.5. The ms-markets refresh drops the
  Command Center Asset Monitor skills, which ms-markets 2.2.0 removed.

### Added

- `tests/test_migration_guidance.py`, which pins the provider's package-local locations, the
  example's local-only writes, the absence of non-local upgrade or downgrade instructions in
  repository-owned files, and the absence of the retired per-project local API and Local/Hosted
  switch.
- Implementation task [0007](docs/implementation_task/0007-deployment-job-migrations.md),
  including the local SQLite proof of the provider against the real ms-markets 2.2.2 schema on a
  MetaTables 0.1.18 runtime, and its re-run on MetaTables 0.1.20 and ms-markets 2.2.5, which
  passed on 2026-10-04.

### Fixed

- `.agents/agent_card.json` and the README version badge match the package version again; the
  0.4.2 release left them at 0.4.1, which failed the agent-card parity tests.

### Unchanged

- The provider `etfhextractor_migrations:migration`: package `etfhextractor`, namespace
  `etfhextractor`, version table `etfhextractor_markets__alembic_version`, revision `0001`.
- The `DemoBarsTS` foreign key to the ms-markets Asset table keeps `ON DELETE RESTRICT`, the
  action it was authored with and the one ms-markets' own asset-keyed time-series tables use.
- Every public name of the library, the `etfh` CLI and the agent card's skills.
