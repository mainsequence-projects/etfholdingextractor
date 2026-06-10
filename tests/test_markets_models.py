from __future__ import annotations

import datetime as dt
import unittest

from etfhextractor.markets_models import (
    ETFHEXTRACTOR_MARKETS_STORAGE_APP,
    ETFHEXTRACTOR_METATABLE_NAMESPACE,
    DemoBars,
    DemoBarsStorage,
    EtfhExtractorMarketsStorageMixin,
)


class DemoBarsStorageConventionTests(unittest.TestCase):
    """Pin the ms-markets extension-table convention (ADR/library rules)."""

    def test_project_mixin_sets_namespace_and_storage_app(self) -> None:
        self.assertTrue(EtfhExtractorMarketsStorageMixin.__abstract__)
        self.assertEqual(
            EtfhExtractorMarketsStorageMixin.__metatable_namespace__,
            "com.mainsequence.etfhextractor",
        )
        self.assertEqual(
            EtfhExtractorMarketsStorageMixin.__markets_storage_app__,
            "etfhextractor_markets",
        )
        self.assertEqual(ETFHEXTRACTOR_METATABLE_NAMESPACE, "com.mainsequence.etfhextractor")
        self.assertEqual(ETFHEXTRACTOR_MARKETS_STORAGE_APP, "etfhextractor_markets")

    def test_logical_identifier_is_namespace_plus_base_identifier(self) -> None:
        self.assertEqual(DemoBarsStorage.__markets_base_identifier__, "DemoBarsTS")
        # The stable logical identity — never the physical table name.
        self.assertEqual(
            DemoBarsStorage.__metatable_identifier__,
            "com.mainsequence.etfhextractor.DemoBarsTS",
        )
        # Physical naming uses the project storage app, separate from identity.
        self.assertTrue(DemoBarsStorage.__table__.name.startswith("etfhextractor_markets__"))

    def test_storage_declares_time_index_asset_identifier_and_value_columns(self) -> None:
        self.assertEqual(DemoBarsStorage.__time_index_name__, "time_index")
        self.assertEqual(DemoBarsStorage.__index_names__, ["time_index", "asset_identifier"])
        self.assertEqual(
            [column.name for column in DemoBarsStorage.__table__.columns],
            ["time_index", "asset_identifier", "close", "volume"],
        )

    def test_asset_identifier_has_canonical_asset_table_foreign_key(self) -> None:
        foreign_keys = {
            f"{fk.parent.name}->{fk.column.table.name}.{fk.column.name}"
            for fk in DemoBarsStorage.__table__.foreign_keys
        }
        self.assertIn("asset_identifier->ms_markets__asset.unique_identifier", foreign_keys)

    def test_node_is_storage_bound(self) -> None:
        self.assertIs(DemoBars._required_storage_table(), DemoBarsStorage)

    def test_migration_provider_is_sdk_shaped_and_scoped_to_project_tables(self) -> None:
        from etfhextractor_migrations import EtfhExtractorAlembicVersion, migration

        self.assertEqual(type(migration).__name__, "AlembicMetaTableMigration")
        provider_models = list(
            getattr(migration, "metatable_models", None) or getattr(migration, "models", [])
        )
        # Scoped to project-owned tables only — never the built-in msm graph.
        self.assertEqual(provider_models, [DemoBarsStorage])
        self.assertEqual(
            EtfhExtractorAlembicVersion.__name__,
            "EtfhExtractorAlembicVersion",
        )

    def test_build_frame_validates_demo_bar_rows(self) -> None:
        now = dt.datetime(2026, 6, 10, tzinfo=dt.UTC)
        frame = DemoBars.build_frame(
            [
                {
                    "time_index": now,
                    "asset_identifier": "BBG000B9XRY4",
                    "close": 100.5,
                    "volume": 1_000_000.0,
                },
                {
                    "time_index": now - dt.timedelta(days=1),
                    "asset_identifier": "BBG000B9XRY4",
                    "close": 100.0,
                    "volume": 1_000_000.0,
                },
            ]
        )
        self.assertEqual(len(frame), 2)
        self.assertIn("close", frame.columns)
        self.assertIn("volume", frame.columns)


if __name__ == "__main__":
    unittest.main()
