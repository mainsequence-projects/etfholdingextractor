from __future__ import annotations

from metatables.migrations.env import run_mainsequence_alembic_env

from etfh_example_migrations import migration

run_mainsequence_alembic_env(default_provider=migration)
