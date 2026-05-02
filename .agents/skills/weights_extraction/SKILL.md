---
name: weights-extraction
description: Use this skill to extract ETF holdings weights from supported providers through the repository CLI and library surfaces.
---

# ETF Holdings Weights Extraction

## Overview

Use this skill when the user wants ETF holdings, weights, or fund-level extraction results.

This repository supports two extraction entrypoints:

- provider fund URLs
- explicit `provider + ticker` inputs

## Preferred Surfaces

Prefer these repository interfaces:

- CLI:
  `etfh extract-url <fund-url> [<fund-url> ...]`
- CLI:
  `etfh extract-ticker --provider <provider> --ticker <ticker> [--ticker <ticker> ...]`
- Python:
  `ETFHoldingsReader`
- Python:
  `extract_ticker_weights(...)`
- Python:
  `extract_many_ticker_weights(...)`
- Python:
  `extract_ticker_weights_for_ticker(...)`

## This Skill Can Do

- extract ticker weights from a supported fund URL
- extract ticker weights from an explicit provider and ETF ticker
- return either weights-only or full parsed holdings payloads
- route users to the documented CLI or Python surface that already exists in the repository

## This Skill Must Not Claim

- that unsupported providers work
- that ticker-only extraction can infer the provider
- that holdings category sync happened
- that MainSequence platform state was checked

## Working Rules

1. Prefer URL-based extraction when the user already has the fund page URL.
2. Require an explicit provider for ticker-only extraction.
3. Keep responses grounded in the supported public API documented in `docs/library.md`.
4. If the request turns into category planning or category sync, route to `.agents/skills/holdings_category_sync/SKILL.md`.

## Expected Outputs

- weights JSON keyed by component ticker
- full parsed holdings payload when the user explicitly wants richer fund metadata
- concise guidance on the correct CLI invocation when the user needs a runnable command
