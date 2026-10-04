"""Apply (local runtime) or verify (hosted runtime) the project-owned DemoBarsTS schema.

`DemoBarsTS` belongs to the project migration provider
`etfhextractor_migrations:migration` (scoped to `DemoBarsStorage` only, so
autogenerate never diffs the built-in ms-markets graph). Who applies it depends
on the runtime:

- **Local development** (`--local`): the script selects the laptop's running
  local MetaTables API (one per laptop, shared by every checkout), checks that
  it is an initialized local SQLite runtime, applies the provider exactly like
  `metatables --local migrations upgrade --provider etfhextractor_migrations:migration head`,
  and verifies the registered `TimeIndexMetaTable`. Start the local API first
  (`metatables init --local`, `metatables serve --local`,
  `metatables --local runtime initialize`). The local runtime must already hold
  the ms-markets tables: `DemoBarsTS` has a foreign key to the ms-markets Asset
  table, and this repository never applies the ms-markets provider.
- **Hosted environments**: nobody migrates them by hand. A hosted runtime is
  migrated only by the migration Job of a deployment workflow, and
  etfholdingextractor has no deployment: the application that deploys code
  using these tables applies `etfhextractor_migrations:migration` in its own
  migration Job (`metatables.upgrade_application(...)`). Without `--local` this
  script only verifies that `DemoBarsTS` is registered and explains how it gets
  migrated when it is not.

Run standalone:

    python examples/prepare_demo_bars_schema.py --local                # apply + verify
    python examples/prepare_demo_bars_schema.py --local --check-only   # verify locally
    python examples/prepare_demo_bars_schema.py                        # verify (hosted)

or let the full workflow run it (default demo-prices run, unless
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

from metatables import TimeIndexMetaTable  # noqa: E402
from metatables.migrations import namespace_version_location  # noqa: E402

ETFHEXTRACTOR_MIGRATION_PROVIDER = "etfhextractor_migrations:migration"
VERSION_LOCATION_PREFIX = "etfhextractor_migrations:versions"
LOCAL_RUNTIME_SETUP = (
    "metatables init --local; metatables serve --local; "
    "metatables --local runtime initialize"
)


def print_step(step: int, message: str) -> None:
    print(f"{step}. {message}", flush=True)


def print_detail(label: str, value: object) -> None:
    print(f"   {label}: {value}", flush=True)


def require_local_runtime() -> dict[str, Any]:
    """Select the laptop's local MetaTables API and refuse anything but local SQLite.

    `configure_local_client()` points this process (and the CLI subprocesses it
    starts) at the laptop's running loopback API, which every checkout shares
    through `server.json` in the local storage directory; it never falls back to
    hosted discovery. The runtime must then report Local mode, the SQLite dialect
    and an initialized runtime DataSource before anything is written.
    """
    from metatables import configure_local_client, get_runtime_status

    configure_local_client()
    state = get_runtime_status()
    source = state.get("data_source") or {}
    bootstrap = state.get("bootstrap") or {}
    if not (
        state.get("local_mode") is True
        and state.get("dialect") == "sqlite"
        and source.get("uid")
        and bootstrap.get("active") is True
        and bootstrap.get("status") == "ready"
        and not state.get("data_source_error")
    ):
        raise RuntimeError(
            "--local needs the laptop's running local MetaTables API with an "
            f"initialized SQLite runtime ({LOCAL_RUNTIME_SETUP}). Runtime reported "
            f"local_mode={state.get('local_mode')!r}, dialect={state.get('dialect')!r}, "
            f"bootstrap={bootstrap.get('status')!r}, "
            f"data_source_error={state.get('data_source_error')!r}."
        )
    print_detail("runtime", f"local {state.get('dialect')} DataSource {source.get('uid')}")
    return state


def prepare_demo_bars_schema(
    *,
    local: bool = False,
    check_only: bool = False,
    revision_message: str | None = None,
) -> dict[str, Any]:
    """Apply the DemoBarsTS provider to the local runtime, or verify its registration.

    With ``local=True`` the provider is applied to the laptop's local MetaTables
    runtime (find-or-generate the revision, ``upgrade head``, verify). Without it,
    or with ``check_only=True``, nothing is generated or applied: the function
    verifies that the revision ships with the package and that the
    ``TimeIndexMetaTable`` is registered, and raises with the migration rule when
    it is not.
    """
    from etfhextractor_migrations import migration  # noqa: F401 — validates provider import
    from msm.settings import markets_configured_namespace

    from etfhextractor.markets_models import DemoBarsStorage

    table_name = DemoBarsStorage.__table__.name
    # The EFFECTIVE namespace (MSM_AUTO_REGISTER_NAMESPACE overrides the declared
    # mixin namespace) — revisions live in this namespace's versions directory.
    namespace = markets_configured_namespace(DemoBarsStorage.__metatable_namespace__)
    print_detail("provider", ETFHEXTRACTOR_MIGRATION_PROVIDER)
    print_detail("runtime_mode", "local" if local else "hosted (verify only)")
    print_detail("configured_storage_table", table_name)
    print_detail("configured_storage_identifier", DemoBarsStorage.__metatable_identifier__)
    if local:
        require_local_runtime()

    print_step(1, "Checking the DemoBarsTS migration revision and registration.")
    revision_file = _find_revision_file(table_name, namespace=namespace)
    if check_only or not local:
        if revision_file is None:
            raise RuntimeError(
                f"No DemoBarsTS revision for namespace {namespace!r} in "
                f"{VERSION_LOCATION_PREFIX}: {table_name}. Author it against the local "
                "runtime with --local."
            )
        existing = _find_time_index_meta_table(table_name)
        if existing is None:
            raise RuntimeError(_not_registered_message(table_name, local=local))
        print_detail("revision_file", revision_file)
        print_detail("time_index_meta_table_uid", existing.uid)
        return {
            "configured_storage_table": table_name,
            "configured_storage_uid": existing.uid,
            "created_revision": False,
            "applied": False,
            "runtime_mode": "local" if local else "hosted",
        }

    created_revision = False
    if revision_file is None:
        print_step(2, "Generating the Alembic revision against the local runtime.")
        created_revision = True
        message = revision_message or "etfhextractor_demo_bars"
        _run_metatables(
            [
                "--local",
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

    print_step(3, "Applying the provider to the local runtime (upgrade head).")
    _run_metatables(
        [
            "--local",
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
            f"DemoBarsTS still is not registered after the local upgrade: {table_name}"
        )

    print_step(4, "DemoBarsTS is migrated and registered in the local runtime.")
    print_detail("time_index_meta_table_uid", existing.uid)
    print_detail("created_revision", created_revision)
    return {
        "configured_storage_table": table_name,
        "configured_storage_uid": existing.uid,
        "created_revision": created_revision,
        "applied": True,
        "runtime_mode": "local",
    }


def _not_registered_message(table_name: str, *, local: bool) -> str:
    if local:
        return (
            f"DemoBarsTS is not registered in the local runtime: {table_name}. Rerun with "
            "--local and without --check-only to apply "
            f"{ETFHEXTRACTOR_MIGRATION_PROVIDER} there."
        )
    return (
        f"DemoBarsTS is not registered in this runtime: {table_name}. Hosted runtimes are "
        "migrated only by a deployment workflow's migration Job. etfholdingextractor has "
        "no deployment, so the application that deploys code using these tables applies "
        f"{ETFHEXTRACTOR_MIGRATION_PROVIDER} in its own migration Job. For local "
        f"development, start the local MetaTables API ({LOCAL_RUNTIME_SETUP}) and rerun "
        "with --local, or pass --price-source-table-uid to the full workflow to use a "
        "registered price table instead."
    )


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


def _run_metatables(args: list[str]) -> None:
    if args[:1] != ["--local"]:
        # Hosted runtimes are migrated only by a deployment workflow's migration Job.
        raise RuntimeError("This example runs metatables commands only with --local.")
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    paths = [str(_PROJECT_ROOT)]
    if existing_pythonpath:
        paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    # `metatables` CLI (mainsequence-metatable) under this interpreter, so the
    # provider imports from the same environment as the example.
    command = [sys.executable, "-m", "metatables.cli.app", *args]
    print_detail("command", " ".join(command))
    result = subprocess.run(command, cwd=_PROJECT_ROOT, env=env, check=False, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the DemoBarsTS provider to the laptop's local MetaTables runtime "
            "(--local), or verify that a hosted runtime already has it."
        ),
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "Use the laptop's running local MetaTables API (local SQLite) and apply "
            f"{ETFHEXTRACTOR_MIGRATION_PROVIDER} there. Without it the script only "
            "verifies: hosted runtimes are migrated by a deployment workflow's "
            "migration Job."
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify that the revision and registered MetaTable exist.",
    )
    parser.add_argument(
        "--revision-message",
        help=(
            "Alembic revision message used with --local when the selected namespace "
            "has no DemoBarsTS revision yet."
        ),
    )
    args = parser.parse_args()
    prepare_demo_bars_schema(
        local=args.local,
        check_only=args.check_only,
        revision_message=args.revision_message,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
