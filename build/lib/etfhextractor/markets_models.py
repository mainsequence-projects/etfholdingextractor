"""Project-owned ms-markets tables for etfhextractor.

Follows the ms-markets extension convention (docs/library.md "Project-Owned
ms-markets Tables"): one local abstract mixin setting the project namespace and
storage app, concrete tables identified by ``__markets_base_identifier__``. The
stable logical identifier is ``com.mainsequence.etfhextractor.<identifier>`` —
never table names, UID maps, or row ``create_schemas()``.

Tables must be migrated/registered through the SDK migration provider before a
process writes through their DataNodes; runtime only attaches via
``msm.start_engine(models=[...])``. For isolated tests/examples, set
``MSM_AUTO_REGISTER_NAMESPACE`` before importing this module — it overrides the
mixin namespace without source changes.

This module imports the msm model layer, so it is intentionally not imported
from ``etfhextractor.__init__`` (pure extraction stays platform-free).
"""

from __future__ import annotations

import datetime

import pandas as pd
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from msm.base import MarketsBase, MarketsTimeIndexMetaTableMixin
from msm.data_nodes.assets import AssetDataNodeConfiguration, AssetTimestampedDataNode
from msm.models.assets.core import AssetTable
from msm.settings import ASSET_IDENTIFIER_DIMENSION

ETFHEXTRACTOR_METATABLE_NAMESPACE = "com.mainsequence.etfhextractor"
ETFHEXTRACTOR_MARKETS_STORAGE_APP = "etfhextractor_markets"


class EtfhExtractorMarketsStorageMixin(MarketsTimeIndexMetaTableMixin):
    """Abstract mixin for every etfhextractor-owned time-series markets table."""

    __abstract__ = True
    __metatable_namespace__ = ETFHEXTRACTOR_METATABLE_NAMESPACE
    __markets_storage_app__ = ETFHEXTRACTOR_MARKETS_STORAGE_APP


class DemoBarsStorage(EtfhExtractorMarketsStorageMixin, MarketsBase):
    """Demo close/volume bars used as the example price source."""

    __markets_base_identifier__ = "DemoBarsTS"
    __metatable_description__ = (
        "Demo daily price bars (close, volume) keyed by (time_index, "
        "asset_identifier), published by the etfhextractor example workflows as a "
        "project-owned price source so the ETF-tracking portfolio pipeline can run "
        "end-to-end without an external market-data feed. Not a production price "
        "table."
    )
    __time_index_name__ = "time_index"
    __index_names__ = ["time_index", ASSET_IDENTIFIER_DIMENSION]

    time_index: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info={"label": "Time Index", "description": "UTC timestamp for the demo bar."},
    )
    asset_identifier: Mapped[str] = mapped_column(
        String(255),
        ForeignKey(
            f"{AssetTable.__table__.fullname}.unique_identifier",
            ondelete="RESTRICT",
        ),
        nullable=False,
        info={
            "label": "Asset Identifier",
            "description": "Asset unique identifier from the Asset MetaTable.",
        },
    )
    close: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        info={"label": "Close", "description": "Demo close price for the bar."},
    )
    volume: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        info={"label": "Volume", "description": "Demo traded volume for the bar."},
    )


def etfhextractor_metatable_provider_models() -> list[type[MarketsBase]]:
    """Project-owned MetaTable models managed by the project's SDK Alembic provider."""
    return [DemoBarsStorage]


def _migration_metadata():
    from mainsequence.meta_tables.migrations import metadata_for_models

    return metadata_for_models(etfhextractor_metatable_provider_models())


# Scoped to the project-owned tables only, so Alembic autogenerate never diffs
# the built-in ms-markets graph.
ETFHEXTRACTOR_MIGRATION_METADATA = _migration_metadata()


class DemoBarsConfiguration(AssetDataNodeConfiguration):
    """Update-scoped configuration for the demo bars DataNode."""


class DemoBars(AssetTimestampedDataNode):
    """Thin storage-bound DataNode publishing demo bars rows."""

    configuration_class = DemoBarsConfiguration

    @classmethod
    def _required_storage_table(cls) -> type[DemoBarsStorage]:
        return DemoBarsStorage

    @classmethod
    def build_frame(cls, rows: list[dict]) -> pd.DataFrame:
        return cls.validate_frame(pd.DataFrame(rows))

    def set_bars(self, rows: list[dict]) -> DemoBars:
        return self.set_frame(self.build_frame(rows))


__all__ = [
    "ETFHEXTRACTOR_MARKETS_STORAGE_APP",
    "ETFHEXTRACTOR_METATABLE_NAMESPACE",
    "DemoBars",
    "DemoBarsConfiguration",
    "DemoBarsStorage",
    "EtfhExtractorMarketsStorageMixin",
]
