"""Parity guard for the project's agent capabilities (implementation task 0004).

The agent card, the project skills, the CLI, and the package version drifted once
(card said 0.3.0 / 2 skills while the project shipped 0.3.x / 3 skills). These
tests pin the invariants so the drift cannot recur silently:

- card version == package version,
- card skills == the project skill directories (vendored trees excluded),
- every project skill documents at least one real CLI entry point,
- every project skill carries the name/description frontmatter.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import etfhextractor
from etfhextractor.cli import build_subcommand_parser

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"
AGENT_CARD_PATH = REPO_ROOT / ".agents" / "agent_card.json"

# Platform-vendored skill trees: never edited, never relocated, never listed in
# the agent card.
VENDORED_SKILL_TREES = {"mainsequence", "ms_markets"}

LEGACY_CLI_ENTRYPOINT = "etfh-read"


def project_skill_directories() -> list[Path]:
    return sorted(
        path
        for path in SKILLS_ROOT.iterdir()
        if path.is_dir() and path.name not in VENDORED_SKILL_TREES
    )


def cli_subcommands() -> set[str]:
    parser = build_subcommand_parser()
    for action in parser._actions:
        if hasattr(action, "choices") and isinstance(action.choices, dict):
            return set(action.choices)
    raise AssertionError("CLI parser exposes no subcommands.")


class AgentCardParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = json.loads(AGENT_CARD_PATH.read_text())

    def test_card_version_matches_package_version(self) -> None:
        self.assertEqual(self.card["version"], etfhextractor.__version__)

    def test_card_skills_match_project_skill_directories(self) -> None:
        card_skill_ids = sorted(skill["id"] for skill in self.card["skills"])
        directory_ids = sorted(path.name for path in project_skill_directories())
        self.assertEqual(card_skill_ids, directory_ids)

    def test_card_skills_have_no_unconfirmed_tags(self) -> None:
        # project_to_agent guardrail: tags stay empty until the user confirms them.
        for skill in self.card["skills"]:
            self.assertEqual(skill["tags"], [], skill["id"])

    def test_card_uses_template_interface_binding(self) -> None:
        self.assertIn(
            {"protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"},
            self.card["supportedInterfaces"],
        )

    def test_readme_version_badge_matches_package_version(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text()
        expected_badge = f"version-{etfhextractor.__version__}-blue"
        self.assertIn(
            expected_badge,
            readme,
            "README version badge is stale; update the shields.io version pill.",
        )


class ProjectSkillTests(unittest.TestCase):
    def test_every_project_skill_has_frontmatter(self) -> None:
        for directory in project_skill_directories():
            content = (directory / "SKILL.md").read_text()
            frontmatter = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
            self.assertIsNotNone(frontmatter, directory.name)
            self.assertIn("name:", frontmatter.group(1), directory.name)
            self.assertIn("description:", frontmatter.group(1), directory.name)

    def test_every_project_skill_references_a_real_cli_entrypoint(self) -> None:
        subcommands = cli_subcommands()
        for directory in project_skill_directories():
            content = (directory / "SKILL.md").read_text()
            referenced = {
                command for command in subcommands if f"etfh {command}" in content
            }
            if LEGACY_CLI_ENTRYPOINT in content:
                referenced.add(LEGACY_CLI_ENTRYPOINT)
            self.assertTrue(
                referenced,
                f"{directory.name}/SKILL.md references no real CLI entry point "
                f"(known subcommands: {sorted(subcommands)} or {LEGACY_CLI_ENTRYPOINT}).",
            )

    def test_skill_cli_references_are_not_stale(self) -> None:
        # Any `etfh <token>` mention in a project skill must be a real subcommand.
        subcommands = cli_subcommands()
        pattern = re.compile(r"`?etfh ([a-z][a-z0-9-]+)")
        for directory in project_skill_directories():
            content = (directory / "SKILL.md").read_text()
            for match in pattern.finditer(content):
                self.assertIn(
                    match.group(1),
                    subcommands,
                    f"{directory.name}/SKILL.md references unknown command "
                    f"'etfh {match.group(1)}'.",
                )


if __name__ == "__main__":
    unittest.main()
