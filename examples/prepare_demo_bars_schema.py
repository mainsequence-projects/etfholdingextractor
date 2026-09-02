"""Prepare the project-owned DemoBarsTS schema (revision + upgrade + verify).

Mirrors the ms-markets prepare-schema example
(`examples/msm_portfolios/portfolio_equal_weights_prepare_schema.py`): find or
generate the Alembic revision for the project migration provider, apply
`upgrade head`, then verify the registered `TimeIndexMetaTable`. The provider is
`etfhextractor_migrations:migration` (SDK-scaffolded, scoped to
`DemoBarsStorage` only — autogenerate never diffs the built-in ms-markets
graph).

Run standalone:

    python examples/prepare_demo_bars_schema.py
    python examples/prepare_demo_bars_schema.py --check-only

or let the full workflow run it (`--demo-prices` does, unless
`--skip-schema-prep`).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mainsequence.client.metatables import TimeIndexMetaTable  # noqa: E402
from mainsequence.meta_tables.migrations import namespace_version_location  # noqa: E402

ETFHEXTRACTOR_MIGRATION_PROVIDER = "etfhextractor_migrations:migration"
VERSION_LOCATION_PREFIX = "etfhextractor_migrations:versions"


def print_step(step: int, message: str) -> None:
    print(f"{step}. {message}", flush=True)


def print_detail(label: str, value: object) -> None:
    print(f"   {label}: {value}", flush=True)


def prepare_demo_bars_schema(
    *,
    check_only: bool = False,
    revision_message: str | None = None,
) -> dict[str, Any]:
    """Create/apply the DemoBarsTS Alembic revision and verify registration."""
    from etfhextractor_migrations import migration  # noqa: F401 — validates provider import
    from msm.settings import markets_configured_namespace

    from etfhextractor.markets_models import DemoBarsStorage

    table_name = DemoBarsStorage.__table__.name
    # The EFFECTIVE namespace (MSM_AUTO_REGISTER_NAMESPACE overrides the declared
    # mixin namespace) — revisions live in this namespace's versions directory.
    namespace = markets_configured_namespace(DemoBarsStorage.__metatable_namespace__)
    print_detail("provider", ETFHEXTRACTOR_MIGRATION_PROVIDER)
    print_detail("configured_storage_table", table_name)
    print_detail("configured_storage_identifier", DemoBarsStorage.__metatable_identifier__)

    print_step(1, "Checking the DemoBarsTS migration revision.")
    revision_file = _find_revision_file(table_name, namespace=namespace)
    existing = _find_time_index_meta_table(table_name)
    if check_only:
        if revision_file is None:
            raise RuntimeError(
                f"DemoBarsTS revision is missing and --check-only was set: {table_name}"
            )
        if existing is None:
            raise RuntimeError(
                f"DemoBarsTS MetaTable is not registered and --check-only was set: {table_name}"
            )
        print_detail("revision_file", revision_file)
        print_detail("time_index_meta_table_uid", existing.uid)
        return {
            "configured_storage_table": table_name,
            "configured_storage_uid": existing.uid,
            "created_revision": False,
        }

    created_revision = False
    if revision_file is None:
        print_step(2, "Generating the Alembic revision (autogenerate).")
        created_revision = True
        message = revision_message or "etfhextractor_demo_bars"
        _run_mainsequence(
            [
                "migrations",
                "revision",
                "--provider",
                ETFHEXTRACTOR_MIGRATION_PROVIDER,
                "--autogenerate",
                "-m",
                message,
            ]
        )
        revision_file = _find_revision_file(table_name, namespace=namespace)
        if revision_file is None:
            raise RuntimeError(
                "Alembic revision was generated, but no generated file contains the "
                f"CREATE TABLE operation for {table_name}."
            )
    print_detail("revision_file", revision_file)

    print_step(3, "Applying the migration (upgrade head).")
    _run_mainsequence(
        [
            "migrations",
            "upgrade",
            "--provider",
            ETFHEXTRACTOR_MIGRATION_PROVIDER,
            "head",
        ]
    )

    existing = _find_time_index_meta_table(table_name)
    if existing is None:
        raise RuntimeError(
            f"DemoBarsTS still is not registered after upgrade: {table_name}"
        )

    print_step(4, "DemoBarsTS is migrated and registered.")
    print_detail("time_index_meta_table_uid", existing.uid)
    print_detail("created_revision", created_revision)
    return {
        "configured_storage_table": table_name,
        "configured_storage_uid": existing.uid,
        "created_revision": created_revision,
    }


def _find_time_index_meta_table(table_name: str) -> Any | None:
    matches = TimeIndexMetaTable.filter_by_body(
        physical_table_name__in=[table_name],
        limit=1,
        offset=0,
    )
    return matches[0] if matches else None


def _find_revision_file(table_name: str, *, namespace: str) -> Path | None:
    versions_root = _active_version_directory(namespace)
    if not versions_root.exists():
        return None
    for path in sorted(versions_root.glob("**/*.py")):
        if path.name == "__init__.py":
            continue
        content = path.read_text(encoding="utf-8")
        if table_name in content and "op.create_table" in content:
            return path
    return None


def _active_version_directory(namespace: str) -> Path:
    version_location = namespace_version_location(namespace, prefix=VERSION_LOCATION_PREFIX)
    package_name, separator, resource_path = version_location.partition(":")
    if not separator or not package_name or not resource_path:
        raise RuntimeError(
            f"Migration provider returned an invalid version location: {version_location!r}"
        )
    traversable = resources.files(package_name)
    for part in resource_path.strip("/").split("/"):
        if part:
            traversable = traversable.joinpath(part)
    return Path(str(traversable))


def _run_mainsequence(args: list[str]) -> None:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    paths = [str(_PROJECT_ROOT)]
    if existing_pythonpath:
        paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    command = [sys.executable, "-m", "mainsequence", *args]
    print_detail("command", " ".join(command))
    result = subprocess.run(command, cwd=_PROJECT_ROOT, env=env, check=False, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create/apply the DemoBarsTS migration revision and verify registration.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify that the revision and registered MetaTable exist.",
    )
    parser.add_argument(
        "--revision-message",
        help="Custom Alembic revision message when a new revision is needed.",
    )
    args = parser.parse_args()
    prepare_demo_bars_schema(
        check_only=args.check_only,
        revision_message=args.revision_message,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
