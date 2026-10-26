"""MetaTables migration provider of the example application's own instances.

It owns only the four `etfhextractor-example` portfolio series instances declared in
`examples/example_instances.py`; the Markets tables they reference by foreign key stay visible
for the foreign keys and are never created here. Apply it to the laptop's local runtime with
`examples/prepare_demo_bars_schema.py --local` (the example's schema step); a hosted runtime is
migrated only by a deployment workflow's migration Job.
"""

from __future__ import annotations

from example_instances import EXAMPLE_INSTANCE_MODELS, EXAMPLE_NAMESPACE, ExampleBase
from metatables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
    build_metatable_model_registry,
    metadata_for_models,
)
from sqlalchemy import Table

PROJECT_TABLE_NAMES = frozenset(model.__table__.name for model in EXAMPLE_INSTANCE_MODELS)


def _migration_metadata():
    """The instance tables plus, for each Markets table they reference, only the referenced column.

    The factories copy each referenced Markets table whole into `ExampleBase.metadata`, with its
    own foreign keys to Markets tables that are not copied (`ms_markets__portfolio.calendar_uid`
    to `ms_markets__calendar`), so that metadata cannot be sorted for Alembic. The provider
    references Markets tables by physical name and key column only (ms-markets ADR 0047,
    decision 4) and never creates them (`_include_example_tables`).
    """
    metadata = metadata_for_models(EXAMPLE_INSTANCE_MODELS)
    for model in EXAMPLE_INSTANCE_MODELS:
        for foreign_key in model.__table__.foreign_keys:
            target = foreign_key.column
            table = metadata.tables.get(target.table.key)
            if table is None:
                table = Table(target.table.name, metadata, schema=target.table.schema)
            if target.name not in table.c:
                table.append_column(target._copy())
    return metadata


EXAMPLE_MIGRATION_METADATA = _migration_metadata()


def _include_example_tables(
    name: str | None,
    type_: str,
    parent_names: dict[str, object],
) -> bool:
    """Keep the copied Markets foreign-key targets visible without taking their DDL."""
    del parent_names
    return type_ != "table" or name in PROJECT_TABLE_NAMES


EtfhExampleAlembicVersion = build_alembic_version_metatable(
    class_name="EtfhExampleAlembicVersion",
    namespace=EXAMPLE_NAMESPACE,
    identifier=f"{EXAMPLE_NAMESPACE}.alembic_version",
    schema=None,
    table_name="etfh_example__alembic_version",
)

migration = build_metatable_migration_provider(
    package="etfhextractor_example",
    migration_namespace=EXAMPLE_NAMESPACE,
    script_location="etfh_example_migrations:",
    version_location_prefix="etfh_example_migrations:versions",
    target_metadata=EXAMPLE_MIGRATION_METADATA,
    alembic_registry=EtfhExampleAlembicVersion,
    metatable_models=build_metatable_model_registry(EXAMPLE_INSTANCE_MODELS, base=ExampleBase),
    include_name_hook=_include_example_tables,
)


__all__ = [
    "EXAMPLE_MIGRATION_METADATA",
    "EtfhExampleAlembicVersion",
    "PROJECT_TABLE_NAMES",
    "migration",
]
