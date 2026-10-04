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
- Main Sequence SDK: `>=9.0.6,<10` (locked with `9.0.6`; local migration proof passed
  2026-10-04)
- MetaTables client: `mainsequence-metatable>=0.1.20,<0.2` (import and CLI `metatables`; locked
  with `0.1.20`; local migration proof on isolated SQLite passed 2026-10-04)
- ms-markets: `>=2.2.5,<3` (locked with `2.2.5`; applied as a local prerequisite in the
  2026-10-04 proof, 62 tables active)
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
  The laptop runs one local MetaTables API, shared by every checkout through `server.json` in
  the local storage directory (MetaTables 0.1.19); `serve --local` reports a running one and
  exits.
  Hosted runtimes are migrated only by the migration Job of the application that deploys code
  using `DemoBarsTS`; this repository never applies the ms-markets provider
  (implementation task 0007). The old `mainsequence migrations` commands are gone.
- A consumer that locks 0.4.3 (`mainsequence-metatable` 0.1.20) needs its Environment's hosted
  MetaTables API on 0.1.19 or later before it pushes; the 0.1.20 client rejects an older API's
  runtime context, so the migration Job fails before migrating (MetaTables#33).
- The portfolio builder owns calendar, signal, Portfolio row, configuration, and
  `PortfoliosDataNode` assembly but never guesses or owns the caller's price source.
- MetaTable schema is migration-owned; runtime attachment does not create it.
