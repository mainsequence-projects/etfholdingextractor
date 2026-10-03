"""Guard the MetaTables deployment-Job migration rule (implementation task 0007).

- The provider keeps explicit, package-local script and version locations.
- The schema-prep example writes only to a local runtime (`metatables --local ...`)
  and only verifies a hosted one.
- Repository-owned docs, examples and code never tell anyone to run a non-local
  `metatables migrations upgrade|downgrade`, and never cite the ms-markets provider
  or the generic top-level `migrations:migration`.
"""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PREP_PATH = REPO_ROOT / "examples" / "prepare_demo_bars_schema.py"
PROVIDER = "etfhextractor_migrations:migration"

# Vendored skill trees belong to their owners' copy commands, not to this repository.
VENDORED_SKILL_TREES = {"mainsequence", "mainsequence_platform", "metatables", "ms_markets"}
OWNED_SUFFIXES = {".md", ".py", ".json", ".toml", ".yaml", ".yml", ".mako"}

NON_LOCAL_MIGRATION = re.compile(
    r"\bmetatables((?:\s+--[a-z][a-z-]*)*)\s+migrations\s+(upgrade|downgrade)\b"
)
FOREIGN_PROVIDER = re.compile(
    r"(?<![A-Za-z0-9_.])(?:msm_migrations|msm\.migrations|migrations):migration\b"
)


def load_schema_prep() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "etfh_example_prepare_demo_bars_schema", SCHEMA_PREP_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repository_owned_files() -> list[Path]:
    skipped_roots = {
        ".venv", ".git", ".local", ".pytest_cache", ".ruff_cache", "build", "dist",
    }
    this_file = Path(__file__).resolve()
    files: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in OWNED_SUFFIXES:
            continue
        if path.resolve() == this_file:  # holds the patterns it checks for
            continue
        parts = path.relative_to(REPO_ROOT).parts
        if parts[0] in skipped_roots or "__pycache__" in parts:
            continue
        if any(part.endswith(".egg-info") for part in parts):
            continue
        if parts[:2] == (".agents", "skills") and len(parts) > 2:
            if parts[2] in VENDORED_SKILL_TREES:
                continue
        files.append(path)
    return files


class ProviderPlacementTests(unittest.TestCase):
    def test_provider_locations_stay_inside_the_project_package(self) -> None:
        from etfhextractor_migrations import migration

        self.assertEqual(migration.script_location, "etfhextractor_migrations:")
        self.assertTrue(migration.version_locations)
        for location in migration.version_locations:
            self.assertTrue(
                location.startswith("etfhextractor_migrations:versions/"),
                location,
            )


class SchemaPrepExampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_schema_prep()
        self.registered = mock.Mock(uid="demo-bars-uid")
        self.revision = Path("0001_etfhextractor_demo_bars.py")

    def test_local_run_applies_the_provider_with_the_local_flag(self) -> None:
        module = self.module
        with (
            mock.patch.object(module, "require_local_runtime", return_value={}) as require,
            mock.patch.object(module, "_find_revision_file", return_value=self.revision),
            mock.patch.object(
                module, "_find_time_index_meta_table", return_value=self.registered
            ),
            mock.patch.object(module, "_run_metatables") as run,
        ):
            result = module.prepare_demo_bars_schema(local=True)

        require.assert_called_once_with()
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [["--local", "migrations", "upgrade", "--provider", PROVIDER, "head"]],
        )
        self.assertTrue(result["applied"])
        self.assertEqual(result["runtime_mode"], "local")

    def test_hosted_run_only_verifies(self) -> None:
        module = self.module
        with (
            mock.patch.object(module, "require_local_runtime") as require,
            mock.patch.object(module, "_find_revision_file", return_value=self.revision),
            mock.patch.object(
                module, "_find_time_index_meta_table", return_value=self.registered
            ),
            mock.patch.object(module, "_run_metatables") as run,
        ):
            result = module.prepare_demo_bars_schema()

        require.assert_not_called()
        run.assert_not_called()
        self.assertFalse(result["applied"])
        self.assertEqual(result["runtime_mode"], "hosted")
        self.assertEqual(result["configured_storage_uid"], "demo-bars-uid")

    def test_hosted_run_stops_with_the_migration_rule_when_unregistered(self) -> None:
        module = self.module
        with (
            mock.patch.object(module, "_find_revision_file", return_value=self.revision),
            mock.patch.object(module, "_find_time_index_meta_table", return_value=None),
            mock.patch.object(module, "_run_metatables") as run,
        ):
            with self.assertRaises(RuntimeError) as raised:
                module.prepare_demo_bars_schema()

        run.assert_not_called()
        message = str(raised.exception)
        self.assertIn("migration Job", message)
        self.assertIn(PROVIDER, message)
        self.assertIn("--local", message)

    def test_cli_runner_refuses_commands_without_the_local_flag(self) -> None:
        module = self.module
        with mock.patch.object(module.subprocess, "run") as run:
            with self.assertRaises(RuntimeError):
                module._run_metatables(["migrations", "upgrade", "--provider", PROVIDER, "head"])
        run.assert_not_called()


class MigrationGuidanceTests(unittest.TestCase):
    def test_owned_files_never_migrate_a_hosted_runtime_by_hand(self) -> None:
        offenders = []
        for path in repository_owned_files():
            text = path.read_text(encoding="utf-8")
            for match in NON_LOCAL_MIGRATION.finditer(text):
                if "--local" not in match.group(1).split():
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
        self.assertEqual(offenders, [], "Use `metatables --local migrations ...` locally.")

    def test_owned_files_never_cite_another_application_provider(self) -> None:
        offenders = []
        for path in repository_owned_files():
            text = path.read_text(encoding="utf-8")
            for match in FOREIGN_PROVIDER.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
        self.assertEqual(offenders, [])

    def test_guard_patterns_catch_the_retired_guidance(self) -> None:
        self.assertIsNotNone(
            NON_LOCAL_MIGRATION.search("metatables migrations upgrade --provider x head")
        )
        self.assertIsNotNone(
            NON_LOCAL_MIGRATION.search("metatables --json migrations downgrade 0001")
        )
        local = NON_LOCAL_MIGRATION.search("metatables --local migrations upgrade --provider x")
        self.assertIn("--local", local.group(1).split())
        self.assertIsNotNone(FOREIGN_PROVIDER.search("--provider migrations:migration"))
        self.assertIsNotNone(FOREIGN_PROVIDER.search("`msm_migrations:migration`"))
        self.assertIsNone(FOREIGN_PROVIDER.search(f"--provider {PROVIDER}"))


if __name__ == "__main__":
    unittest.main()
