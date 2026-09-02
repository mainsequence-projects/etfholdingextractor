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
- Main Sequence SDK: `8.0.7`
- ms-markets: `1.0.2`
- Migration namespace: `etfhextractor`
- Alembic head: `0001`
- Managed output table: `etfhextractor_markets__demobarsts`

## Contracts

- Provider extraction is independent from Main Sequence runtime attachment.
- Category synchronization and signal production require the ms-markets asset/snapshot runtime.
- Updaters declare `_required_output_table()`; registered read-only dependencies use
  `TimeIndexTableRef.from_uid`.
- The portfolio builder owns calendar, signal, Portfolio row, configuration, and
  `PortfoliosDataNode` assembly but never guesses or owns the caller's price source.
- MetaTable schema is migration-owned; runtime attachment does not create it.
