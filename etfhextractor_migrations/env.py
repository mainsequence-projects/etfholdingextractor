from __future__ import annotations

from mainsequence.meta_tables.migrations.env import run_mainsequence_alembic_env

from etfhextractor_migrations import migration


run_mainsequence_alembic_env(default_provider=migration)
