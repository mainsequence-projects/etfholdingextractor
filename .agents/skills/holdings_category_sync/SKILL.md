---
name: holdings-category-sync
description: Use this skill to plan or sync MainSequence HOLDINGS__<ETF> asset categories from extracted ETF holdings, optionally FIGI-registering missing components.
---

# Holdings Category Sync

## Overview

Use this skill when the user wants to build or sync a `HOLDINGS__<ETF>` asset category from ETF
holdings that this repository can already extract. Category writes go through the ms-markets
(`msm`) typed-row API; ticker→asset resolution goes through the msm asset-snapshot layer; asset
identity is UUID-based (`asset_uids`), and registered assets are keyed by their US composite
FIGI (ADR 0004).

## Preferred Surfaces

Prefer these repository interfaces:

- CLI:
  `etfh category-sync --ticker <etf> (--fund-url <url> | --provider <provider>)
  [--register-missing] [--figi-filter '<json>' ...]`
- Python:
  `build_holdings_asset_category_plan(...)`
- Python:
  `sync_holdings_asset_category(etf_ticker=..., asset_uids=[...])`
- Python (missing components):
  `register_equity_assets_from_tickers(tickers=[...], disambiguation_filters=[...])`

## This Skill Can Do

- build a holdings asset category plan from extracted fund holdings
- identify missing or ambiguous registered symbols before sync
- FIGI-register missing components on demand (`--register-missing`, ADR 0004: no asset without
  a FIGI; a ticker must map to exactly ONE FIGI; needs the `OPEN_FIGI_API_KEY` secret) — smart
  delta-only flow: batched `query_figi`, one registry search, one snapshot search, writes only
  what is missing, logs progress percentages
- resolve OpenFIGI ambiguity or provider-symbology mismatches with per-ticker filters, e.g.
  `--figi-filter '{"ticker": "USO", "exch_code": "US"}'` or the alias form
  `--figi-filter '{"ticker": "BRKB", "figi_ticker": "BRK/B"}'`
- sync a holdings asset category when the required `asset_uids` are resolved
- distinguish category planning from the final category sync action

## This Skill Must Not Claim

- that ambiguous tickers were auto-registered (multiple FIGI candidates always stay blockers —
  they require explicit disambiguation filters)
- that an asset was registered without a FIGI (ticker-keyed assets are forbidden)
- that platform access is available unless it was verified
- that extraction providers can be inferred without either `fund_url` or an explicit provider

## Working Rules

1. Treat extraction as a prerequisite and reuse the repository extraction surface.
2. Surface blockers explicitly:
   `missing_registered_symbols` and `ambiguous_registered_symbols`.
3. With `--register-missing`, registration failures name the blocked tickers and their FIGI
   candidates (`format_failures()` / `FigiRegistrationError`); never bypass them.
4. Do not present a category as synced when the plan still has blockers.
5. If the user only needs holdings or weights, route back to
   `.agents/skills/weights_extraction/SKILL.md`; if they want the tracking signal (or its
   ms-markets portfolio assembly), route to `.agents/skills/etf_holdings_signal/SKILL.md`.

## Expected Outputs

- a category plan summary (`existing_asset_uids_by_symbol`, blockers)
- a registration summary when `--register-missing` ran (registered / already-registered /
  snapshots published / unmapped / ambiguous)
- a sync result (`unique_identifier`, `asset_uids`) only when the repository surface actually
  performed the sync
