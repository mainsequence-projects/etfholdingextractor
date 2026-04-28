# AGENTS.md

When the user requests ETF holdings or weights, the primary task of agents in this repository is
to return those holdings by extracting them from provider web services and related downloadable
source files, using the repository tools and the `.agents/skills/weights_extraction/SKILL.md`
skill.

For other requests, agents should follow the user's actual task instead of forcing the
holdings-extraction workflow.

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
