"""Pin the migration provider identity that consuming applications depend on.

Applications that deploy code using `DemoBarsTS` run `etfhextractor_migrations:migration` in
their own migration Jobs, and the MetaTables catalog binds the provider's tables by its package,
namespace, provider key, version table and physical names. Changing any of them would make a
consumer's next migration register different tables instead of reusing the existing ones.

A dependency upgrade must also never imply a schema change: the models must still produce
exactly the schema of revision `0001`, checked the way the MetaTables migration environment
compares them (provider filters, type and server-default comparison).
"""

from __future__ import annotations

import importlib.util
import io
import unittest
from pathlib import Path

import etfhextractor_migrations
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from etfhextractor_migrations import EtfhExtractorAlembicVersion, migration
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from etfhextractor.markets_models import DemoBarsStorage

PACKAGE_DIR = Path(etfhextractor_migrations.__file__).resolve().parent
VERSIONS_DIR = PACKAGE_DIR / "versions" / "etfhextractor"
REVISION_0001 = VERSIONS_DIR / "0001_etfhextractor_demo_bars.py"
DEMO_BARS_TABLE = "etfhextractor_markets__demobarsts"
DEMO_BARS_FOREIGN_KEY = "fk__etfhextractor_markets__demobarsts__asset_identif_aa195e0879"
DEMO_BARS_UNIQUE_INDEX = "uix__etfhextractor_markets__demobarsts__time_index_6c1d0165ee"


def load_revision_0001():
    spec = importlib.util.spec_from_file_location("etfh_revision_0001", REVISION_0001)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProviderIdentityTests(unittest.TestCase):
    def test_provider_identity_is_unchanged(self) -> None:
        self.assertEqual(migration.package, "etfhextractor")
        self.assertEqual(migration.migration_namespace, "etfhextractor")
        self.assertEqual(migration.migration_provider_key, "etfhextractor:etfhextractor")
        self.assertEqual(migration.script_location, "etfhextractor_migrations:")
        self.assertEqual(
            list(migration.version_locations),
            ["etfhextractor_migrations:versions/etfhextractor"],
        )
        self.assertEqual(list(migration.metatable_models), [DemoBarsStorage])
        self.assertEqual(migration.version_table, "etfhextractor_markets__alembic_version")
        self.assertIsNone(migration.version_table_schema)
        self.assertEqual(
            EtfhExtractorAlembicVersion.__metatable_identifier__,
            "etfhextractor.alembic_version",
        )

    def test_history_is_the_single_revision_0001(self) -> None:
        config = Config()
        config.set_main_option("path_separator", "os")
        config.set_main_option("script_location", str(PACKAGE_DIR))
        config.set_main_option("version_locations", str(VERSIONS_DIR))
        script = ScriptDirectory.from_config(config)
        self.assertEqual(script.get_heads(), ["0001"])
        self.assertEqual([rev.revision for rev in script.walk_revisions()], ["0001"])

    def test_demo_bars_storage_identity_is_unchanged(self) -> None:
        table = DemoBarsStorage.__table__
        self.assertEqual(DemoBarsStorage.__metatable_identifier__, "etfhextractor.DemoBarsTS")
        self.assertEqual(table.name, DEMO_BARS_TABLE)
        self.assertIsNone(table.schema)
        self.assertEqual(
            [(fk.name, fk.ondelete) for fk in table.foreign_key_constraints],
            [(DEMO_BARS_FOREIGN_KEY, "RESTRICT")],
        )
        self.assertEqual(
            [(index.name, [c.name for c in index.columns], index.unique) for index in table.indexes],
            [(DEMO_BARS_UNIQUE_INDEX, ["time_index", "asset_identifier"], True)],
        )


class RevisionDriftTests(unittest.TestCase):
    def test_models_match_revision_0001_on_sqlite(self) -> None:
        revision = load_revision_0001()
        engine = sa.create_engine("sqlite://")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                revision.upgrade()
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_name": migration.include_name,
                    "include_object": migration.include_object,
                    "version_table": migration.version_table,
                    "compare_type": True,
                    "compare_server_default": True,
                },
            )
            self.assertEqual(compare_metadata(context, migration.target_metadata), [])

    def test_models_match_revision_0001_ddl_on_postgresql(self) -> None:
        revision = load_revision_0001()
        output = io.StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
        )
        with Operations.context(context):
            revision.upgrade()
        dialect = postgresql.dialect()
        table = DemoBarsStorage.__table__
        model_ddl = [CreateTable(table).compile(dialect=dialect)]
        model_ddl += [CreateIndex(index).compile(dialect=dialect) for index in table.indexes]
        self.assertEqual(
            " ".join(output.getvalue().split()),
            " ".join(" ".join(f"{str(statement).strip()};" for statement in model_ddl).split()),
        )


if __name__ == "__main__":
    unittest.main()
