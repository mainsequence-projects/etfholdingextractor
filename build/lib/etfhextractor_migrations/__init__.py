from __future__ import annotations

from mainsequence.meta_tables.migrations import (
    build_alembic_version_metatable,
    build_metatable_migration_provider,
)
from msm.settings import markets_configured_namespace

from etfhextractor.markets_models import (
    ETFHEXTRACTOR_METATABLE_NAMESPACE,
    ETFHEXTRACTOR_MIGRATION_METADATA,
)
from etfhextractor_migrations.registry import metatable_provider_models

# Env-aware like the ms-markets provider: MSM_AUTO_REGISTER_NAMESPACE overrides
# the project namespace for isolated tests/examples without source changes.
_NAMESPACE = markets_configured_namespace(ETFHEXTRACTOR_METATABLE_NAMESPACE)


EtfhExtractorAlembicVersion = build_alembic_version_metatable(
    class_name="EtfhExtractorAlembicVersion",
    namespace=_NAMESPACE,
    identifier=f"{_NAMESPACE}.alembic_version",
    schema=None,
    table_name="etfhextractor_markets__alembic_version",
)

migration = build_metatable_migration_provider(
    package="etfhextractor",
    migration_namespace=_NAMESPACE,
    script_location="etfhextractor_migrations:",
    version_location_prefix="etfhextractor_migrations:versions",
    target_metadata=ETFHEXTRACTOR_MIGRATION_METADATA,
    alembic_registry=EtfhExtractorAlembicVersion,
    metatable_models=metatable_provider_models(),
)


__all__ = ["EtfhExtractorAlembicVersion", "migration"]
