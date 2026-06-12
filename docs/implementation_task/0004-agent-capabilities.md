# Implementation Task: Agent Capabilities for `etfhextractor`

> Status: **Implemented** (2026-06-11). W-1..W-4 executed; W-5 (registry verification) is
> user-run/out-of-repo. Open-question defaults applied as recommended: OQ-1 name kept
> `etfholdingextractor-161`; OQ-2 `supportedInterfaces = HTTP+JSON / 1.0` (the skill template's
> base); OQ-3 tags remain empty. Override any of these by editing `.agents/agent_card.json`
> (the parity test pins version + skills, not these choices).

## 1. Objective

Make this repository a fully compliant Main Sequence **coding-agent** project: an agent
operating inside this repo discovers its capabilities through `.agents/` (AGENTS.md instruction
section, CLI-aligned skills, a registry-valid agent card) and serves them strictly through the
existing CLI/library surfaces. Per the skill's hard rule, this is a **coding-agent setup**:
**no `agents/` folder, no `agent.py`, no new runtime** — the deliverable is configuration and
documentation built around the capabilities that already exist.

## 2. Current state (checks performed, per the skill's Required Checks)

| # | Required check | Result |
|---|---|---|
| 1 | `AGENTS.md` has a `## Project-Specific Instruction` section | **PASS** — present (line 11), content matches the project: 4 capabilities (extraction, category sync, portfolio publication, FIGI registration) with ADR/task pointers |
| 2 | Section content matches project intention/documentation | **PASS with gaps** — see G-1, G-2 |
| 3 | Skills exist in `.agents/skills` (excluding `mainsequence/`) | **PASS** — `weights_extraction`, `holdings_category_sync`, `etf_holdings_signal` (all refreshed 2026-06-11) |
| 4 | Project has CLI capabilities at a documented location | **PASS** — `etfhextractor/cli/__init__.py`; entry points `etfh` and `etfh-read` in `pyproject.toml [project.scripts]`; documented in `docs/library.md` and `AGENTS.md` |
| 5 | All non-Main-Sequence skills relate to the project CLI | **PASS** — the three project skills map 1:1 to CLI commands; the vendored trees (`mainsequence/`, `ms_markets/`) are excluded from the check and from the card |
| 6 | Agent card exists at `.agents/agent_card.json` and meets criteria | **PARTIAL** — exists; version `0.3.3` matches `pyproject.toml`; skills list = exactly the three project skills; tags empty (per guardrail). Gaps: `supportedInterfaces` is `[]` (template prescribes an `HTTP+JSON / 1.0` binding) and the naming rule needs a user decision — see G-3, OQ-1 |

## 3. Gap list

- **G-1 — AGENTS.md skill routing is incomplete.** The "When serving those capabilities"
  list routes to `weights_extraction` and `holdings_category_sync` but not to the new
  `.agents/skills/etf_holdings_signal/SKILL.md` (and does not mention that FIGI-registration
  requests route through `holdings_category_sync`).
- **G-2 — No single agent-description sentence in AGENTS.md.** Card criteria 2 requires the
  card description to "align with the agent-specific description in AGENTS.md"; alignment is
  currently inferred from the capability list rather than stated. Add one canonical description
  line to `## Project-Specific Instruction` and make the card quote it.
- **G-3 — `supportedInterfaces` empty.** Template base prescribes
  `[{"protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}]` — the binding the A2A flow's
  `/api/a2a/chat` surface expects. Needs user confirmation (OQ-2) before setting.
- **G-4 — No drift guard.** Card version vs `pyproject.toml`, and card skills vs the
  `.agents/skills` tree, have already drifted once (card said 0.3.0 / 2 skills until today).
  Nothing prevents recurrence.

## 4. Work items (ordered; no code in this pass)

- [x] **W-1. AGENTS.md instruction refresh.** Add the `etf_holdings_signal` routing line and
  a FIGI-routing note (G-1); add the canonical one-line agent description (G-2); keep the
  section heading exactly `## Project-Specific Instruction`.
- [x] **W-2. Agent card finalization.** Apply the template base: set `supportedInterfaces`
  per OQ-2; resolve the name per OQ-1; description = the W-1 canonical sentence; keep
  `tags: []` everywhere until the user confirms tags (skill guardrail); skills array stays
  exactly the three project skills with CLI-faithful examples.
- [x] **W-3. Skill-card-CLI parity test.** Add `tests/test_agent_capabilities.py` asserting:
  (a) `agent_card.json` version == `etfhextractor.__version__`; (b) card skill ids == the
  directories under `.agents/skills/` excluding the vendored set (`mainsequence/`,
  `ms_markets/`); (c) every project SKILL.md
  names at least one real CLI command (`etfh …`/`etfh-read`) that the parser accepts
  (`build_parser().parse_args` smoke); (d) every skill has the `name`/`description`
  frontmatter. This is the standing drift guard for G-4.
- [x] **W-4. Release checklist note.** Add a short "agent capabilities" subsection to
  `docs/library.md` (or AGENTS.md): bumping `pyproject` version requires the card bump (caught
  by W-3); adding a CLI command requires a matching skill + card entry.
- [ ] **W-5. (Out-of-repo, user-run) Registry verification.** After W-1..W-3 land:
  `mainsequence agent search "ETF holdings extraction" --json` should surface this agent with
  the three skills, and an A2A request routed per
  `.agents/skills/mainsequence/a2a_communication/SKILL.md` should be answerable strictly
  through the CLI surfaces. This plan makes no claim of platform behavior — verification is
  observational, by the user or platform tooling.

## 5. Explicitly out of scope (skill guardrails)

- No `agents/` folder, no `agent.py`, no bespoke agent runtime — coding-agent setup only.
- No new capabilities, endpoints, or CLI behavior invented for the card; the card may only
  describe what `etfh`/`etfh-read` and the documented library surfaces already do.
- No platform-side registration, sharing, or orchestration changes from this repo.
- No edits to vendored skill trees (`mainsequence/**`, `ms_markets/**`) — no content changes
  and **no relocation**; they stay at their canonical paths.

## 6. Verification plan

1. `python -m unittest tests/test_agent_capabilities.py` (W-3) green.
2. `etfh --help` lists exactly the commands referenced by the three skills.
3. Manual re-run of the project_to_agent Required Checks 1–6: all PASS, no PARTIAL.
4. W-5 registry observation (user-run).

## 7. Open questions (user decisions required — skill forbids inventing these)

- **OQ-1 — Agent name.** The skill contradicts itself: criteria 1 says the card name "must
  match the project name and project ID" (current `etfholdingextractor-161` complies), while
  the template note says to use "a meaningful and brief name… do not use project name".
  Options: (a) keep `etfholdingextractor-161` (registry-matching, zero risk), or (b) a
  capability name such as `etf-holdings-and-tracking-agent`. Recommendation: (a) unless the
  registry displays human-facing names, then (b). **Decide before W-2.**
- **OQ-2 — Protocol binding.** Confirm `HTTP+JSON / 1.0` is the correct `supportedInterfaces`
  entry for this org's A2A runtime (the template default). **Decide before W-2.**
- **OQ-3 — Skill tags.** Tags stay `[]` per the guardrail. If discovery ranking needs them,
  propose: `etf`, `holdings`, `weights`, `figi`, `portfolio`, `ms-markets`. **Confirm or
  reject; default is no tags.**
