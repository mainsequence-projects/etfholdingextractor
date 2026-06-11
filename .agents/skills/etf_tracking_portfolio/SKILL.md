---
name: etf-tracking-portfolio
description: Use this skill to publish or operate an ms-markets portfolio that tracks an ETF through the repository's holdings signal pipeline.
---

# ETF-Tracking Portfolio

## Overview

Use this skill when the user wants a portfolio that tracks an ETF (implementation task 0002,
ADRs 0003/0005/0006). The pipeline is: extraction (`FundHoldings`) → `ETFHoldingsSignal` (a
custom `msm_portfolios` `SignalWeights` that emits `(time_index, asset_identifier) →
signal_weight`) → `PortfoliosDataNode` with an explicit price source. Weights live in the
ms-markets portfolio tables — never on the asset category.

## Preferred Surfaces

- CLI:
  `etfh portfolio-publish --ticker <etf> (--fund-url <url> | --provider <provider>)
  [--price-source-table-uid <uid>] [--calendar-key NYSE] [--backtest-start-days 60]
  [--signal-validity-days 90] [--min-update-interval-days 1.0]
  [--register-missing] [--figi-filter '<json>' ...] [--no-run]`
- Python (deliberately NOT in `etfhextractor.__init__`):
  `from etfhextractor.portfolio_publish import publish_etf_tracking_portfolio`
- Self-sufficient end-to-end example (demo prices, schema prep, verification):
  `python examples/ivv_tracking_portfolio_full_workflow.py`

## Key Contracts (do not contradict these)

- **Identity**: the portfolio is the `Portfolio` row alone — `unique_identifier =
  etf_tracker_<ticker>` keys all portfolio storage; `PortfolioIndex` is only an optional
  published-index reference. The signal's `signal_uid` is **definition-scoped** (ADR 0005):
  `asset_list` is updater scope and is neutralized in the uid payload, so rebalances never
  rotate the series; changing definition fields (ticker, source, validity, backtest window,
  calendar) DOES rotate it.
- **Calendar is obligatory** (ms-markets >= 0.0.58): `PortfolioTable.calendar_uid` is a NOT NULL
  FK. `ensure_trading_calendar()` persists the calendar (msm util
  `Calendar.create_from_pandas_calendar`; always-open keys persist an always-open row) and
  publish attaches it; the rebalancer resolves the same key into the persisted sessions.
- **Session-grid observations** (ADR 0006): every signal observation is stamped on a market
  close of `calendar_key` (as-of date → that day's close; provider lag → latest completed
  close; at most one observation per session) — never at insertion wall-clock times.
- **Guards**: insert at most once per `min_update_interval_days`, only when weights changed —
  except unchanged weights are re-stamped shortly before `signal_validity_days` expires so a
  stable composition never starves the portfolio forward-fill. Validity must exceed the
  backtest window by >= 5 days (defaults 90/60).
- **Price source is never guessed**: pass `price_source_instance` (a DataNode, e.g. the
  project-owned `DemoBars`) or a registered `TimeIndexMetaTable` uid
  (`ETFH_PORTFOLIO_PRICE_SOURCE_TABLE_UID` env default). Bars must provide `close` and `volume`.

## This Skill Must Not Claim

- that a portfolio produced values/weights without reading them back from the platform
  (`PortfoliosTS` / `PortfolioWeightsTS` keyed by `portfolio_identifier`, signal rows by
  `signal_uid`)
- that the tracker reproduces historical baskets — the backtest bootstrap assumes the CURRENT
  composition over the backtest window
- that components without a unique FIGI mapping were registered or tracked

## Working Rules

1. Resolve the full component universe first; unresolved components block publication (a
   tracker on a partial universe misrepresents the ETF). Use `--register-missing` +
   `--figi-filter` for blockers.
2. Re-runs are safe: calendar persistence is write-frugal, the signal is guarded, and
   registration is delta-only.
3. Verify outcomes from platform rows, not return values (the example's verification step shows
   the pattern).
4. For extraction-only or category-only requests, route to
   `.agents/skills/weights_extraction/SKILL.md` /
   `.agents/skills/holdings_category_sync/SKILL.md`.

## Expected Outputs

- the publish payload: `portfolio_unique_identifier`, `portfolio_uid`, `calendar_key` +
  `calendar_uid`, `signal_uid`, `backtest_start_days`, price-source description, run summary
- read-back verification counts (signal weight rows, portfolio value rows, portfolio weight
  rows, the Portfolio row with its calendar FK and DataNode pointer uids)
