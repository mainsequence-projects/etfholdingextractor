# Changelog

All notable changes to `etfhextractor` are recorded here. Earlier releases are described by
their Git tags and by the implementation tasks in `docs/implementation_task/`.

## [0.4.3] - 2026-10-03

### Changed

- Require `mainsequence>=9.0.5,<10`, `mainsequence-metatable>=0.1.14,<0.2` and
  `ms-markets>=2.1.1,<3`. `uv.lock` resolves 9.0.5, 0.1.14 and 2.1.1, and `requirements.txt` was
  regenerated from it.
- Adopt the MetaTables 0.1.14 migration recommendation. Hosted runtimes are migrated only by a
  deployment workflow's migration Job. etfholdingextractor has no deployment, so the application
  that deploys code using `DemoBarsTS` applies `etfhextractor_migrations:migration` in its own
  migration Job. Local development uses
  `metatables --local migrations upgrade --provider etfhextractor_migrations:migration head`.
  Neither this package nor its consumers apply the ms-markets provider; the ms-markets deployment
  migrates that schema.
- `examples/prepare_demo_bars_schema.py` no longer migrates hosted runtimes. `--local` applies
  the provider to the project's local MetaTables runtime after checking that it is an
  initialized local SQLite runtime; without `--local` the script only verifies that `DemoBarsTS`
  is registered.
- `examples/ivv_tracking_portfolio_full_workflow.py` gained `--local` and no longer cites the
  generic top-level `migrations` provider or hosted upgrades.
- README, `docs/library.md`, `examples/README.md` and the AGENTS.md project text document who
  applies the provider, and that since SDK 9.0.5 `mainsequence code-repository sync` only
  refreshes local dependencies; publishing is a plain `git push` plus the version tag.
- Refreshed the vendored skills: SDK 9.0.5 (`.agents/skills/mainsequence/`, plus the managed
  AGENTS.md block), `metatables` 0.1.14 and ms-markets 2.1.1.

### Added

- `tests/test_migration_guidance.py`, which pins the provider's package-local locations, the
  example's local-only writes, and the absence of non-local upgrade or downgrade instructions in
  repository-owned files.
- Implementation task [0007](docs/implementation_task/0007-deployment-job-migrations.md),
  including the local SQLite proof of the provider.

### Fixed

- `.agents/agent_card.json` and the README version badge match the package version again; the
  0.4.2 release left them at 0.4.1, which failed the agent-card parity tests.

### Unchanged

- The provider `etfhextractor_migrations:migration`: package `etfhextractor`, namespace
  `etfhextractor`, version table `etfhextractor_markets__alembic_version`, revision `0001`.
- Every public name of the library, the `etfh` CLI and the agent card's skills.

### Known issues

- The ms-markets 2.1.1 provider cannot finalize on a MetaTables 0.1.14 API (a 70-character
  default secondary-index name on `PortfolioEventLedgerStorage`, and cascading foreign keys), so
  a fresh local runtime cannot yet hold the real ms-markets schema that `DemoBarsTS` references.
