# AGENTS.md

When the user requests ETF holdings or weights, the primary task of agents in this repository is
to return those holdings by extracting them from provider web services and related downloadable
source files, using the repository tools and the `.agents/skills/weights_extraction/SKILL.md`
skill.

For other requests, agents should follow the user's actual task instead of forcing the
holdings-extraction workflow.

## Project-Specific Instruction

This repository exposes two project-specific agent capabilities and agents should stay within
those boundaries:

1. ETF holdings extraction from supported provider URLs or explicit `provider + ticker` inputs.
2. MainSequence holdings category planning and sync from already-supported extraction results.

When serving those capabilities:

- Prefer the repository CLI surface before inventing ad hoc flows:
  `etfh extract-url`, `etfh extract-ticker`, and `etfh category-sync`.
- Use `.agents/skills/weights_extraction/SKILL.md` for holdings and weight extraction requests.
- Use `.agents/skills/holdings_category_sync/SKILL.md` for holdings-category planning or sync
  requests.
- Limit claims to supported providers and existing library surfaces documented in `docs/library.md`.
- Distinguish clearly between local extraction work and MainSequence platform-dependent category
  sync work. Do not imply platform state has been verified unless it was actually checked.

<!-- mainsequence-agent-scaffold:start schema=1 source=agent_scaffold -->
## Main Sequence Agent Scaffold

This block is managed by `mainsequence project update AGENTS.md`.

For Main Sequence work in this repository:

1. Start with `.agents/skills/project_builder/SKILL.md`.
2. Route domain work to the relevant skill under `.agents/skills/`.
3. Use `.agents/skills/maintenance/local_journal/SKILL.md` after material changes.

Refresh reusable scaffold instructions with:

`mainsequence project update_agent_skills --path .`
<!-- mainsequence-agent-scaffold:end -->

The durable Main Sequence behavior lives in the scaffold skills under
`agent_scaffold/skills/` and should be refreshed into projects with
`mainsequence project update_agent_skills --path .`.
