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
- Package version source: `pyproject.toml`

## Platform context

- CodeRepository UID: `2b634665-d3c0-4cf4-a8ed-f4446eba7891`
- CodeRepositoryBranch UID for `main`: `41ddaf20-9077-4e42-bc24-cace28efd5d7`
- Python: `3.13`
- Main Sequence SDK: `>=9.0.2,<10` (verified offline with `9.0.2`)
- MetaTables client: `mainsequence-metatable>=0.1.6,<0.2` (import and CLI `metatables`; verified
  offline with `0.1.6`)
- ms-markets: `>=2,<3` (verified offline with `2.0.0`)
- Migration namespace: `etfhextractor`
- Alembic head: `0001`
- Managed output table: `etfhextractor_markets__demobarsts`

## Contracts

- Provider extraction is independent from Main Sequence runtime attachment.
- Category synchronization and signal production require the ms-markets asset/snapshot runtime.
- Updaters declare `_required_output_table()`; registered read-only dependencies use
  `metatables.TimeIndexTableRef.from_uid`. Updater runs take no `debug_mode`/`force_update`.
- Migrations run through `metatables migrations <command> --provider
  etfhextractor_migrations:migration`; the old `mainsequence migrations` commands are gone.
- The portfolio builder owns calendar, signal, Portfolio row, configuration, and
  `PortfoliosDataNode` assembly but never guesses or owns the caller's price source.
- MetaTable schema is migration-owned; runtime attachment does not create it.
