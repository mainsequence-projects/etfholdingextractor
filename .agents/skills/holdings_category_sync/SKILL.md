---
name: holdings-category-sync
description: Use this skill to plan or sync MainSequence holdings categories from extracted ETF holdings.
---

# Holdings Category Sync

## Overview

Use this skill when the user wants to build or sync a `HOLDINGS__<ETF>` asset category from ETF
holdings that this repository can already extract.

## Preferred Surfaces

Prefer these repository interfaces:

- CLI:
  `etfh category-sync --ticker <etf-ticker> --fund-url <fund-url>`
- Python:
  `build_holdings_asset_category_plan(...)`
- Python:
  `sync_holdings_asset_category(...)`

## This Skill Can Do

- build a holdings asset category plan from extracted fund holdings
- identify missing or ambiguous registered symbols before sync
- sync a holdings asset category when the required asset ids are known
- distinguish category planning from the final category sync action

## This Skill Must Not Claim

- that asset registration exists for missing symbols
- that platform access is available unless it was verified
- that extraction providers can be inferred without either `fund_url` or explicit `component_provider`

## Working Rules

1. Treat extraction as a prerequisite and reuse the repository extraction surface.
2. Surface blockers explicitly:
   `missing_registered_symbols` and `ambiguous_registered_symbols`.
3. Do not present a category as synced when the plan still has blockers.
4. If the user only needs holdings or weights, route back to `.agents/skills/weights_extraction/SKILL.md`.

## Expected Outputs

- a category plan summary
- a blocker summary when symbols are missing or ambiguous
- a sync result only when the repository surface actually performs the sync
