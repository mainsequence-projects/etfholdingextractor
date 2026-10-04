# Changelog

All notable changes to `etfhextractor` are recorded here. Earlier releases are described by
their Git tags and by the implementation tasks in `docs/implementation_task/`.

## [0.4.3] - 2026-10-04

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
  MetaTables 0.1.18 runtime. The re-run on MetaTables 0.1.20 and ms-markets 2.2.5 is pending.

### Fixed

- `.agents/agent_card.json` and the README version badge match the package version again; the
  0.4.2 release left them at 0.4.1, which failed the agent-card parity tests.

### Unchanged

- The provider `etfhextractor_migrations:migration`: package `etfhextractor`, namespace
  `etfhextractor`, version table `etfhextractor_markets__alembic_version`, revision `0001`.
- The `DemoBarsTS` foreign key to the ms-markets Asset table keeps `ON DELETE RESTRICT`, the
  action it was authored with and the one ms-markets' own asset-keyed time-series tables use.
- Every public name of the library, the `etfh` CLI and the agent card's skills.
