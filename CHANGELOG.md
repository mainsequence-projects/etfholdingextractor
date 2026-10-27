# Changelog

All notable changes to `etfhextractor` are recorded here. Earlier releases are described by
their Git tags and by the implementation tasks in `docs/implementation_task/`.

## [0.5.1] - 2026-10-27

Moves the pin to ms-markets 3.0.1. The library's code and API are unchanged.

### Changed

- Require exactly `ms-markets==3.0.1`, the release the Markets deployment runs (the exact-pin
  policy of 0.4.4); its client API is unchanged from 3.0.0. Its Markets API no longer has the
  registry-writer allow-list, so an application that runs the library's calls on the remote
  backend needs only `reader` on the `MainSequenceMarkets` branch. `uv.lock` and
  `requirements.txt` resolve ms-markets 3.0.1; no other dependency moved.
- The docs no longer mention the `MARKETS_REGISTRY_WRITERS` constant (commit 805323e); the 0.5.0
  upgrade note that asks for it no longer applies.

## [0.5.0] - 2026-10-27

Moves the library to ms-markets 3.0.0 and its Markets API boundary (ms-markets ADR 0047), and
drops every compatibility layer. **Breaking for importers and `etfh` users** (see "Removed" and
"Upgrade notes"); hence a minor release rather than the 0.4.5 first prepared: the repository has
no written versioning policy, but its last breaking migration went from 0.3.x to 0.4.1, and
semantic versioning puts breaking changes of a 0.x package in the minor version.

### Changed

- Pin `ms-markets==3.0.0`, the release the Markets deployment runs once it moves to the Markets
  API boundary (the exact-pin policy of 0.4.4). ms-markets 3.0.0 requires `mainsequence>=9.0.29`
  and `mainsequence-metatable>=0.1.57`, which the ranges here already admit. `uv.lock` and
  `requirements.txt` resolve ms-markets 3.0.0, SDK 9.0.33 (9.0.31 is the first that parses the
  platform's Agent reads) and MetaTables 0.1.57.
- **Portfolio series go only to the application's own instances.** `build_etf_tracking_portfolio`
  and `publish_etf_tracking_portfolio` require `instances`, an
  `msm_portfolios.services.series_moves.PortfolioSeriesTables` with the application's
  `signal_weights`, `weights`, `rebalance_state` and `values` instances (ms-markets
  `contract_instances` factories); `require_portfolio_instances` refuses a missing slot or a
  Markets table. The build records them in the Markets catalog with `PortfolioDatasets.register`
  after the (optional) run, reconciling when it ran (`EtfTrackingPortfolioBuild.instances`,
  `.portfolio_datasets`, and `portfolio_datasets` in the summary). `ETFHoldingsSignal` requires
  `output_table=` (its update hash is unchanged: `signalweights_6c7728d4635eb499f1d517ecfc840275`
  computed offline before and after). `portfolio_runtime_models(instances, extra_models)` and
  `start_portfolio_engine(instances, extra_models)` attach the instances, plus on the runtime
  backend the Markets registry tables the row calls need and never a Markets portfolio series.
  `etfh portfolio-publish` requires `--instances MODULE:ATTRIBUTE`.
- Markets registries are reached only through `msm.api` row calls, and set-based ones where a
  call touches many rows. The library never selects the ms-markets row backend: the importing
  application does (`use_remote_backend(LazyRemoteBackend())` or `MSM_API_BACKEND=remote`), and
  on that backend every registry read and write runs on the Markets API and the library attaches
  no Markets table except the application's own.
  - Asset uids by identifier: one `Asset.get_many_by_unique_identifier` instead of
    `search_model` on `AssetTable`.
  - Ticker resolution (`resolve_asset_identifiers_by_ticker`, `resolve_existing_assets_by_ticker`,
    the signal's update, category planning): one `AssetSnapshots.latest(tickers=...)` instead of
    paging `search_model` over `AssetSnapshotsStorage` twice and then looking the asset uids up;
    an asset still matches a symbol only when its latest snapshot ticker does. The registration
    snapshot check is one `AssetSnapshots.latest(asset_identifiers=...)`.
  - FIGI registration: one `Asset.upsert_many` and one `OpenFigiDetails.upsert_many` instead of
    one `Asset.upsert` and one `OpenFigiDetails.upsert` per new asset, and
    `AssetSnapshots.publish`, whose ms-markets 3.0 updater verifies duplicate keys in one read.
  - Always-open calendars: `CalendarDate.upsert_many` and `CalendarSession.upsert_many` (the
    conflict keys of ms-markets' materialization) instead of `materialize_calendar_rows` on a
    runtime context.
- The calendar helpers (`ensure_trading_calendar`, `required_calendar_window` and the calendar
  constants) live in the light `etfhextractor.calendars` module, which imports neither ms-markets
  at import time nor the msm_portfolios stack.
- Imports use the ms-markets 3.0 names (`msm.time_index`, `msm_portfolios.time_index`,
  `PortfoliosUpdater`, `AssetTimestampedUpdater`, `AssetUpdaterConfiguration`);
  `msm rename-preflight scan` is clean.
- The example is an application with its own instances: `examples/example_instances.py`
  (namespace `etfhextractor-example`), their migration provider `examples/etfh_example_migrations`
  (revision `0001`) and `examples/prepare_example_instances_schema.py`. It verifies its run
  through the updaters that wrote the rows and `Portfolio.get_by_unique_identifier`.

### Added

- `require_portfolio_instances`, `register_portfolio_datasets`, `register_signal_dataset` (a
  signal run without a portfolio: `PortfolioDatasets.register_signal` after its run),
  `ETFHoldingsSignal.set_asset_identifier_resolver`, the build's `update_pointers` and
  `resolve_asset_identifiers_fn` options, and `etfhextractor.markets_runtime`.
- `tests/test_markets_api_boundary.py` runs the library against a recording remote backend: the
  resource and operation of every Markets call, nothing attached but the application's tables,
  the library never selecting the backend, no compiled SQL on a Markets table and no removed
  name re-exported. `tests/test_example_instances.py` pins the example instances, provider and
  revision. Another test pins the default IVV/ishares `signal_uid`.

### Removed (breaking)

- Writing the Markets core `SignalWeightsTS`, `PortfolioWeightsTS`, `PortfolioRebalanceStateTS`
  and `PortfoliosTS`: there is no default output table anywhere.
- `etfhextractor.markets_models.BatchVerifiedAssetSnapshot`.
- The re-exports of `ensure_trading_calendar`, `required_calendar_window`,
  `US_EQUITY_CALENDAR_KEY`, `ALWAYS_OPEN_CALENDAR_KEYS`, `CALENDAR_PAST_BUFFER_DAYS` and
  `CALENDAR_FUTURE_HORIZON_DAYS` from `etfhextractor.portfolio_publish`, and of
  `ALWAYS_OPEN_CALENDAR_KEYS` from `etfhextractor.portfolio_signal`: import them from
  `etfhextractor.calendars`.
- The `etfh-read` console script and the subcommand-less `etfh <url>` /
  `etfh --provider P --ticker T`: use `etfh extract-url` / `etfh extract-ticker`
  (`python -m etfhextractor` is `etfh`).
- The duplicate `price_source` key of the portfolio summary: use `valuation_source`.
- The ms-markets 0.0.54 workaround that set the private
  `PortfoliosUpdater._explicit_portfolio_identifier`; 3.0 resolves the identity from
  `target_portfolio`.

### Upgrade notes for applications

- Run 0.5.0 only in an Environment whose Markets deployment runs ms-markets 3.0.0 and has
  applied its revisions.
- Declare your own four portfolio instances, migrate them with your migration provider, grant
  the Markets workload `data_viewer` on them, and pass them as `instances` (or
  `--instances`). A portfolio with history in the core tables keeps it there until it is copied:
  pause its runs and move it with ms-markets' `PortfolioSeriesMove` (`msm series move`) before
  its first run on the instances; never recompute, ETF holdings cannot be re-extracted for past
  dates (`docs/library.md`, "Markets Access").
- On the remote backend, every workflow resource that calls the library needs
  `access.branches: [{repository: MainSequenceMarkets, policy: reader}]`. Its workload User uid
  must also be listed in the Environment's `MARKETS_REGISTRY_WRITERS` constant under the
  write-policy resources of the calls it makes: `asset-category`, `asset-type`, `asset`,
  `open-figi-details`, `asset-snapshots`, `calendar`, `calendar-date`, `calendar-session`,
  `portfolio`, `signal-metadata`, `portfolio-datasets`.
- On their first ms-markets 3.0 run, `ETFHoldingsSignal` and `PortfoliosUpdater` get a new
  `TimeIndexTableUpdate` (ms-markets 3.0 moved the modules their hashes name; bound to a new
  output table they get their own record anyway). `signal_uid` does not change: the default
  IVV/ishares uid still computes offline to `495a8b180d0a216e563cd3f83316da7f`.

### Unchanged

- The provider `etfhextractor_migrations:migration`, revision `0001`, `DemoBarsTS` and its
  identity.

### Not verified

- Everything was verified offline only (128 tests with outbound network blocked, against the
  published ms-markets 3.0.0): no run against a deployed Markets API or a local
  runtime, the example instances provider was never applied to a runtime, and the ms-markets
  2.2.10 local SQLite defects listed under 0.4.4 were not re-checked.

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
