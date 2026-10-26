# AGENTS.md

When the user requests ETF holdings or weights, the primary task of agents in this repository is
to return those holdings by extracting them from provider web services and related downloadable
source files, using the repository tools and the `.agents/skills/weights_extraction/SKILL.md`
skill.

For other requests, agents should follow the user's actual task instead of forcing the
holdings-extraction workflow.

## Project-Specific Instruction

Agent description (canonical — `.agents/agent_card.json` quotes this sentence): Agent for
extracting ETF holdings weights from supported providers, planning or syncing MainSequence
HOLDINGS__<ETF> asset categories (FIGI-registering missing components on demand), and providing
an ETF-holdings tracking SIGNAL for the ms-markets portfolio pipeline — portfolio assembly
itself is ms-markets functionality, demonstrated in the repository example.

This repository exposes four project-specific agent capabilities and agents should stay within
those boundaries:

1. ETF holdings extraction from supported provider URLs or explicit `provider + ticker` inputs.
2. MainSequence holdings category planning and sync from already-supported extraction results.
3. An ETF-holdings tracking SIGNAL for the `msm_portfolios` pipeline (`ETFHoldingsSignal`;
   weights insert at most daily, only on change, stamped on session closes — see
   `docs/implementation_task/0002-ms-markets-portfolio-weights.md`). Portfolio assembly itself
   (Portfolio rows, calendars, prices, `PortfoliosUpdater`) is ms-markets functionality;
   `etfh portfolio-publish` and the example are convenience wiring that demonstrate it, with
   prices always supplied by the caller.
4. FIGI registration of missing ETF components (opt-in `--register-missing`): no asset is
   registered without a FIGI, and only unique ticker→FIGI mappings register — ambiguity stays a
   blocker (see `docs/adr/0004-figi-only-asset-registration.md`).

When serving those capabilities:

- Prefer the repository CLI surface before inventing ad hoc flows:
  `etfh extract-url`, `etfh extract-ticker`, `etfh category-sync`, and `etfh portfolio-publish`.
- Use `.agents/skills/weights_extraction/SKILL.md` for holdings and weight extraction requests.
- Use `.agents/skills/holdings_category_sync/SKILL.md` for holdings-category planning or sync
  requests — FIGI registration of missing components (`--register-missing`, `--figi-filter`)
  routes through this skill as well.
- Use `.agents/skills/etf_holdings_signal/SKILL.md` for the ETF-holdings tracking signal and
  for requests about the ms-markets portfolio assembly demonstrated around it.
- Limit claims to supported providers and existing library surfaces documented in `docs/library.md`.
- This project owns exactly one ms-markets MetaTable — `DemoBarsStorage`
  (`etfhextractor.DemoBarsTS` in `etfhextractor/markets_models.py`, the example's
  demo price source); everything else uses built-in `msm`/`msm_portfolios` models. Every
  project-owned table must follow the extension-mixin convention in `docs/library.md`
  ("Project-Owned ms-markets Tables"): local abstract mixin with
  `__metatable_namespace__`/`__markets_storage_app__`, identity via `__markets_base_identifier__`,
  MetaTables-provider migration (`etfhextractor_migrations:migration`),
  `msm.start_engine(models=[...])` attachment — never table-name identity, UID maps, or
  `create_schemas()`.
- Migrations follow the MetaTables deployment-Job rule, introduced in 0.1.14 (`docs/library.md`,
  "Who applies the provider").
  Run the provider yourself only against the local runtime:
  `metatables --local migrations upgrade --provider etfhextractor_migrations:migration head`.
  Hosted runtimes are migrated only by a deployment workflow's migration Job, never from a
  developer or agent session. This repository has no deployment and no workflow file, so the
  application that deploys code using `DemoBarsTS` applies `etfhextractor_migrations:migration`
  in its own migration Job. The ms-markets schema belongs to the ms-markets deployment; this
  repository never applies the ms-markets provider. Nothing migrates at import or start-up.
- Markets access follows ms-markets ADR 0047 (`docs/library.md`, "Markets Access"). The library
  never selects the ms-markets row backend; the importing application does (`LazyRemoteBackend`
  or `MSM_API_BACKEND=remote`). Markets registries (assets, OpenFIGI details, asset types and
  snapshots, categories, calendars, portfolios, signal metadata, the portfolio catalog) are
  reached only through set-based `msm.api` row calls, never compiled SQL, `search_model` or
  repository helpers on a Markets table. The one exception is the asset-snapshot read in
  `mainsequence_categories._search_snapshot_rows`, which has no Markets API route yet;
  `tests/test_markets_api_boundary.py` guards both rules. Portfolio and signal time series go to
  an application's own instances through the seams of `build_etf_tracking_portfolio`
  (`*_output_table`, `register_datasets`, `update_pointers`, `resolve_asset_identifiers_fn`);
  the defaults write the core ms-markets tables as before.
- `ms-markets` is pinned exactly to the release the Markets deployment runs (CHANGELOG 0.4.4), so
  moving Markets needs a new release of this package.
- Since SDK 9.0.5, `mainsequence code-repository sync` only refreshes local dependencies
  (`uv lock`, `uv sync`, `uv export --locked --no-dev --no-hashes`); it never bumps, tags,
  commits or pushes. Publishing is a plain `git push` plus the version tag, and this repository
  declares no workflow file, so a push deploys nothing.
- Distinguish clearly between local extraction work and MainSequence platform-dependent category
  sync work. Do not imply platform state has been verified unless it was actually checked.

<!-- mainsequence-agent-scaffold:start schema=1 source=agent_scaffold -->
## Main Sequence Instructions

Use this managed section to select the correct Main Sequence skill. Detailed
procedures belong in those skills and their referenced documentation.

## Authority

- Repository-specific instructions above this block define local intent and
  repository conventions.
- The installed SDK code, CLI help, SDK-owned skills, and version-matched SDK
  documentation define client behavior.
- Installed platform-owned skills and backend-advertised schemas, templates,
  and capabilities define the current platform contract.
- The public documentation site is supplemental when its SDK version differs
  from the installed package:
  `https://mainsequence-sdk.github.io/mainsequence-sdk/`
- If the installed client and platform contract disagree, do not guess or
  update automatically. Use the bug-auditor skill to record the evidence and
  identify the owning side.

## Updates Are Explicit

Do not run any of these commands unless the user explicitly requests that
specific update:

- `mainsequence code-repository update-sdk --path .`
- `mainsequence code-repository update-agent-skills --path .`
- `mainsequence code-repository update-platform-skills --path .`
- `mainsequence code-repository update AGENTS.md --path .`
- `uv run ms-tau skills sync --path .`

A missing or mismatched `.agents/skills/mainsequence/PINNED_FROM.txt` is state
to report, not permission to mutate the repository. The same rule applies to
`.agents/skills/ms_tau_sdk/PINNED_FROM.txt`. When a Main Sequence update is
requested, use the `code_repository_maintenance` skill. The `mainsequence` CLI
never owns or updates the `ms_tau_sdk` namespace.

The SDK owns all of `.agents/skills/mainsequence/`. Its skill copy is local,
requires no sign-in, and deletes everything absent from the installed SDK
bundle. Platform skills are installed separately under
`.agents/skills/mainsequence_platform/` by the authenticated platform update.

## Route By Task

- Product architecture, platform ontology, and CodeRepository Blueprint work:
  use the matching platform-owned design skill declared by the installed
  platform catalog. Do not assume its filesystem path.
- CodeRepository context, local SDK execution, repository structure, and
  implementation routing:
  `.agents/skills/mainsequence/sdk_code_repository_execution/SKILL.md`
- Local environment repair, authentication, explicitly requested updates,
  dependency sync after a dependency change, and publishing with Git:
  `.agents/skills/mainsequence/maintenance/code_repository_maintenance/SKILL.md`
- Blocker analysis, failure classification, and SDK/platform contract mismatches:
  `.agents/skills/mainsequence/maintenance/bug_auditor/SKILL.md`
- MetaTable modeling, queries, external registration, table updates, Alembic
  schema changes, and data discovery: use the skills the `metatables` package
  installs under `.agents/skills/metatables/` and its documentation.
- Code that still imports `mainsequence.meta_tables` or
  `mainsequence.client.metatables`, or calls the retired `mainsequence` table
  and migration commands:
  `.agents/skills/mainsequence/maintenance/metatables_transition/SKILL.md`
- FastAPI APIs serving the Command Center frontend:
  `.agents/skills/mainsequence/application_surfaces/api_surfaces/SKILL.md`
- Jobs, schedules, images, resources, releases, and Artifacts:
  `.agents/skills/mainsequence/platform_operations/orchestration_and_releases/SKILL.md`
- RBAC, sharing, constants, secrets, and access verification:
  `.agents/skills/mainsequence/platform_operations/access_control_and_sharing/SKILL.md`
- Direct recorded model calls, structured extraction, thinking/provider options,
  inference history and idempotent replay:
  `.agents/skills/mainsequence/mainsequence-inference/SKILL.md`
- A2A session discovery, messages, files, and SDK response handling:
  `.agents/skills/mainsequence/a2a_sdk_execution/SKILL.md`
- Turning a CodeRepository into a platform coding agent or selecting other
  platform-owned capabilities: use the matching skill declared by the installed
  platform catalog. Do not hardcode a platform-owned skill path.
- Implementing or debugging a TAU-based Harness Agent: after the platform skill
  establishes the platform contract, use the version-matched skills under
  `.agents/skills/ms_tau_sdk/`. If they are absent and the user requested the
  update, run `uv run ms-tau skills sync --path .`; do not reconstruct those
  SDK instructions from platform documentation.

## Core Working Rules

- Read the relevant skill before acting on a Main Sequence domain.
- Use the current Git checkout as repository, branch, and commit identity. Do
  not ask users to inject CodeRepositoryBranch or Environment identity.
- Use the `mainsequence` CLI as the default platform control surface. Prefer
  `--json` when output will be parsed or used as evidence.
- Use the owning domain package before designing against an unfamiliar domain contract.
- Keep reusable business logic under `src/` and keep API, job, and other
  integration layers thin.
- Verify only the platform objects relevant to the requested outcome.
- Separate verified facts from assumptions and report blockers with the exact
  failing operation.

## Completion

Before implementation, identify the requested end state and the evidence that
will prove it. Do not claim completion until the relevant code or documentation
checks pass and any required platform state has been verified. If live
verification is unavailable, state what remains unverified.
<!-- mainsequence-agent-scaffold:end -->

The durable Main Sequence behavior lives in the scaffold skills under
`agent_scaffold/skills/` and should be refreshed into projects with
`mainsequence code-repository update-agent-skills --path .`.
