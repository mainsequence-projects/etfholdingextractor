# Record

## Stable paths

- Project instructions: `AGENTS.md`
- Library package: `etfhextractor/`
- CLI entrypoint: `etfhextractor/cli/__init__.py`
- Portfolio builder/publisher: `etfhextractor/portfolio_publish.py`
- Holdings signal: `etfhextractor/portfolio_signal.py`
- Project migration provider: `etfhextractor_migrations:migration`
- Migration revisions: `etfhextractor_migrations/versions/etfhextractor/`
- Library docs: `docs/library.md`
- Release notes: `CHANGELOG.md`
- Package version source: `pyproject.toml`

## Platform context

- CodeRepository UID: `2b634665-d3c0-4cf4-a8ed-f4446eba7891`
- CodeRepositoryBranch UID for `main`: `41ddaf20-9077-4e42-bc24-cace28efd5d7`
- Python: `3.13`
- Main Sequence SDK: `>=9.0.5,<10` (locked and verified with `9.0.5`)
- MetaTables client: `mainsequence-metatable>=0.1.14,<0.2` (import and CLI `metatables`; locked
  and verified with `0.1.14`)
- ms-markets: `>=2.1.1,<3` (locked and verified with `2.1.1`)
- Deployment: none. No `.mainsequence/workflows/` file and no migration Job.
- Migration namespace: `etfhextractor`
- Alembic head: `0001`
- Managed output table: `etfhextractor_markets__demobarsts`

## Contracts

- Provider extraction is independent from Main Sequence runtime attachment.
- Category synchronization and signal production require the ms-markets asset/snapshot runtime.
- Updaters declare `_required_output_table()`; registered read-only dependencies use
  `metatables.TimeIndexTableRef.from_uid`. Updater runs take no `debug_mode`/`force_update`.
- A session migrates only the local runtime:
  `metatables --local migrations <command> --provider etfhextractor_migrations:migration`.
  Hosted runtimes are migrated only by the migration Job of the application that deploys code
  using `DemoBarsTS`; this repository never applies the ms-markets provider
  (implementation task 0007). The old `mainsequence migrations` commands are gone.
- The portfolio builder owns calendar, signal, Portfolio row, configuration, and
  `PortfoliosDataNode` assembly but never guesses or owns the caller's price source.
- MetaTable schema is migration-owned; runtime attachment does not create it.
