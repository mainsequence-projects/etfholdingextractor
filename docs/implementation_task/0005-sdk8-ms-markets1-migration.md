# 0005 — SDK 8 and ms-markets 1 migration

Status: implemented and backend migration verified; release publication is a separate operational
step.

## Goal

Migrate the complete `etfhextractor` package to Python 3.13, Main Sequence SDK 8, and
`ms-markets` 1 without removing or bypassing any supported capability:

1. provider URL and provider+ticker extraction;
2. strict holdings-category planning/sync and optional FIGI registration;
3. `ETFHoldingsSignal` publication;
4. `etfh portfolio-publish` with either a caller-supplied updater or a registered
   `TimeIndexMetaTable` UID;
5. the self-contained demo-bars example and its project-owned migration provider.

## Dependency contract

- Python: `>=3.13,<3.14`
- `mainsequence>=8.0.7`
- `ms-markets>=1.0.2`

The package declarations are compatible lower bounds. Exact reproducibility remains in
`uv.lock` and the exported `requirements.txt`.

## API migrations

| Legacy surface | SDK 8 / ms-markets 1 surface |
|---|---|
| `DataNode` terminology | `TimeIndexTableUpdater` |
| `_required_storage_table()` | `_required_output_table()` |
| instance `storage_table` | instance `output_table` |
| `APIDataNode.build_from_table_uid(uid)` | `TimeIndexTableRef.from_uid(uid)` |

The registered-table UID path and the explicit updater path are both regression-tested.
`build_etf_tracking_portfolio(...)` now exposes the assembled graph for project integrations;
`publish_etf_tracking_portfolio(...)` wraps that builder and retains its JSON return contract. The
builder still creates the same signal, calendar, Portfolio row, portfolio configuration, and
`PortfoliosDataNode`, and it accepts an explicit portfolio identifier so downstream projects do not
need to duplicate that functionality.

## MetaTable migration boundary

`etfhextractor_migrations:migration` continues to own only `DemoBarsStorage`. Its target metadata
also contains `AssetTable` so SQLAlchemy can resolve the foreign key, while an Alembic include hook
excludes that ms-markets-owned table from this provider's DDL and catalog-registration scope.

## Validation

Required checks:

```bash
uv lock --check
uv pip check --python .venv/bin/python
uv run ruff check etfhextractor etfhextractor_migrations examples tests
uv run pytest -q
python -m mainsequence migrations current --provider etfhextractor_migrations:migration
```

Live provider extraction should also be checked through:

```bash
etfh extract-ticker --provider ishares --ticker IVV --compact
```

The Streamlit dashboard in Alpaca Connectors is unrelated and is not changed by this package
migration.

## Verified backend state

On 2026-09-02, the authenticated CodeRepository resolved as UID
`2b634665-d3c0-4cf4-a8ed-f4446eba7891` on `main`. Applying
`etfhextractor_migrations:migration` finalized the Alembic registry and
`etfhextractor_markets__demobarsts` active with zero reserved or failed resources. A follow-up
`current` returned `0001 (head)`, and `msm.start_engine(models=[AssetTable, DemoBarsStorage])`
attached both registered tables successfully. A live iShares IVV extraction returned 508 holdings
dated 2026-08-31, confirming that provider extraction remains operational.
