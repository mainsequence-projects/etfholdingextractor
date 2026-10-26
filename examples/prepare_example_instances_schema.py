"""Apply (local runtime) or verify (hosted runtime) the example application's portfolio instances.

The example application keeps every portfolio series in its own `etfhextractor-example`
namespace (`examples/example_instances.py`), migrated by its own provider
`etfh_example_migrations:migration`, whose revision `0001` ships in
`examples/etfh_example_migrations/versions/`.

- **Local development** (`--local`): select the laptop's running local MetaTables API, check
  that it is an initialized local SQLite runtime, apply the provider exactly like
  `metatables --local migrations upgrade --provider etfh_example_migrations:migration head`
  (with `examples/` on `PYTHONPATH`), and verify the four registered `TimeIndexMetaTable`s. The
  local runtime must already hold the ms-markets tables the instances reference.
- **Hosted environments**: nobody migrates them by hand; an application's own deployment
  workflow migrates its instances in its migration Job. Without `--local` this script only
  verifies that the four tables are registered.

Run standalone:

    python examples/prepare_example_instances_schema.py --local                # apply + verify
    python examples/prepare_example_instances_schema.py --local --check-only   # verify locally
    python examples/prepare_example_instances_schema.py                        # verify (hosted)

or let the full workflow run it (unless `--skip-schema-prep`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_EXAMPLES_DIR = Path(__file__).resolve().parent
if str(_EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_DIR))

from prepare_demo_bars_schema import (  # noqa: E402
    LOCAL_RUNTIME_SETUP,
    _find_time_index_meta_table,
    _run_metatables,
    print_detail,
    print_step,
    require_local_runtime,
)

EXAMPLE_MIGRATION_PROVIDER = "etfh_example_migrations:migration"


def prepare_example_instances_schema(*, local: bool = False, check_only: bool = False) -> dict[str, Any]:
    """Apply the example instances provider locally, or verify the instances are registered."""
    from example_instances import EXAMPLE_INSTANCE_MODELS

    table_names = [model.__table__.name for model in EXAMPLE_INSTANCE_MODELS]
    print_detail("provider", EXAMPLE_MIGRATION_PROVIDER)
    print_detail("runtime_mode", "local" if local else "hosted (verify only)")
    print_detail("instance_tables", ", ".join(table_names))
    if local:
        require_local_runtime()

    applied = local and not check_only
    if applied:
        print_step(1, "Applying the example instances provider to the local runtime (upgrade head).")
        _run_metatables(
            ["--local", "migrations", "upgrade", "--provider", EXAMPLE_MIGRATION_PROVIDER, "head"]
        )

    print_step(2, "Checking the registered example instances.")
    registered = {name: _find_time_index_meta_table(name) for name in table_names}
    missing = sorted(name for name, meta_table in registered.items() if meta_table is None)
    if missing:
        raise RuntimeError(_not_registered_message(missing, local=local))
    for name, meta_table in registered.items():
        print_detail(name, meta_table.uid)
    return {
        "instance_table_uids": {name: meta_table.uid for name, meta_table in registered.items()},
        "applied": applied,
        "runtime_mode": "local" if local else "hosted",
    }


def _not_registered_message(missing: list[str], *, local: bool) -> str:
    if local:
        return (
            f"The example instances are not registered in the local runtime: {missing}. Rerun "
            f"with --local and without --check-only to apply {EXAMPLE_MIGRATION_PROVIDER}."
        )
    return (
        f"The example instances are not registered in this runtime: {missing}. Hosted runtimes "
        "are migrated only by a deployment workflow's migration Job, so an application applies "
        "the provider of its own instances there. For local development, start the local "
        f"MetaTables API ({LOCAL_RUNTIME_SETUP}) and rerun with --local."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the example application's portfolio instances provider to the laptop's local "
            "MetaTables runtime (--local), or verify that a hosted runtime already has them."
        ),
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help=f"Use the laptop's local MetaTables API and apply {EXAMPLE_MIGRATION_PROVIDER}.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify that the four instances are registered.",
    )
    args = parser.parse_args()
    prepare_example_instances_schema(local=args.local, check_only=args.check_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
