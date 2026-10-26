"""The example application keeps every portfolio series in its own namespace (ADR 0047).

`examples/example_instances.py` declares the four contract instances in the
`etfhextractor-example` namespace and `examples/etfh_example_migrations` migrates exactly those
tables; the Markets tables they reference are never created by it. Revision `0001` must stay the
schema of the instances, checked the way the MetaTables migration environment compares them.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

import example_instances  # noqa: E402
from etfh_example_migrations import migration  # noqa: E402

PROVIDER_DIR = EXAMPLES_DIR / "etfh_example_migrations"
VERSIONS_DIR = PROVIDER_DIR / "versions" / "etfhextractor_example"
REVISION_0001 = VERSIONS_DIR / "0001_etfhextractor_example_portfolio_instances.py"
INSTANCE_TABLES = {
    "etfh_example__signalweightsts__main": "etfhextractor-example.SignalWeightsTS.main",
    "etfh_example__portfolioweightsts__main": "etfhextractor-example.PortfolioWeightsTS.main",
    "etfh_example__portfoliorebalancestatets__main": (
        "etfhextractor-example.PortfolioRebalanceStateTS.main"
    ),
    "etfh_example__portfoliosts__main": "etfhextractor-example.PortfoliosTS.main",
}


def load_revision_0001():
    spec = importlib.util.spec_from_file_location("etfh_example_revision_0001", REVISION_0001)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExampleInstanceTests(unittest.TestCase):
    def test_instances_live_in_the_example_namespace(self) -> None:
        from etfhextractor.portfolio_publish import require_portfolio_instances

        instances = require_portfolio_instances(example_instances.example_instances())
        tables = {
            getattr(instances, slot).__table__.name: getattr(instances, slot)
            for slot in ("signal_weights", "weights", "rebalance_state", "values")
        }
        self.assertEqual(set(tables), set(INSTANCE_TABLES))
        for name, model in tables.items():
            self.assertEqual(model.__metatable_identifier__, INSTANCE_TABLES[name])
            self.assertEqual(model.__table__.info["namespace"], "etfhextractor-example")

    def test_provider_owns_exactly_the_instances(self) -> None:
        self.assertEqual(migration.migration_namespace, "etfhextractor-example")
        self.assertEqual(migration.migration_provider_key, "etfhextractor_example:etfhextractor-example")
        self.assertEqual(
            list(migration.version_locations),
            ["etfh_example_migrations:versions/etfhextractor_example"],
        )
        self.assertEqual(migration.version_table, "etfh_example__alembic_version")
        self.assertEqual(
            list(migration.metatable_models), list(example_instances.EXAMPLE_INSTANCE_MODELS)
        )

    def test_history_is_the_single_revision_0001(self) -> None:
        config = Config()
        config.set_main_option("path_separator", "os")
        config.set_main_option("script_location", str(PROVIDER_DIR))
        config.set_main_option("version_locations", str(VERSIONS_DIR))
        script = ScriptDirectory.from_config(config)
        self.assertEqual(script.get_heads(), ["0001"])

    def test_models_match_revision_0001_on_sqlite(self) -> None:
        revision = load_revision_0001()
        engine = sa.create_engine("sqlite://")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                revision.upgrade()
            created = set(sa.inspect(connection).get_table_names())
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
        # Only the instances: the referenced Markets tables are never created here.
        self.assertEqual(created, set(INSTANCE_TABLES))


class InstanceSchemaStepTests(unittest.TestCase):
    def setUp(self) -> None:
        import prepare_example_instances_schema

        self.module = prepare_example_instances_schema
        self.registered = mock.Mock(uid="instance-uid")

    def test_local_run_applies_the_example_provider_with_the_local_flag(self) -> None:
        module = self.module
        with (
            mock.patch.object(module, "require_local_runtime", return_value={}) as require,
            mock.patch.object(
                module, "_find_time_index_meta_table", return_value=self.registered
            ),
            mock.patch.object(module, "_run_metatables") as run,
        ):
            result = module.prepare_example_instances_schema(local=True)

        require.assert_called_once_with()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                [
                    "--local",
                    "migrations",
                    "upgrade",
                    "--provider",
                    "etfh_example_migrations:migration",
                    "head",
                ]
            ],
        )
        self.assertTrue(result["applied"])
        self.assertEqual(set(result["instance_table_uids"]), set(INSTANCE_TABLES))

    def test_hosted_run_only_verifies_and_names_the_missing_tables(self) -> None:
        module = self.module
        with (
            mock.patch.object(module, "_find_time_index_meta_table", return_value=None),
            mock.patch.object(module, "_run_metatables") as run,
        ):
            with self.assertRaises(RuntimeError) as raised:
                module.prepare_example_instances_schema()

        run.assert_not_called()
        self.assertIn("migration Job", str(raised.exception))
        self.assertIn("etfh_example__portfoliosts__main", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
