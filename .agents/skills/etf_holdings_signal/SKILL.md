---
name: etf-holdings-signal
description: Use this skill when the user wants the ETF-holdings tracking signal this library provides for the msm_portfolios pipeline.
---

# ETF Holdings Tracking Signal

## Overview

**What this library provides is a SIGNAL — `ETFHoldingsSignal` — and nothing more at the
portfolio layer.** It is a custom `msm_portfolios` `SignalWeights` TimeIndexTableUpdater whose update
re-extracts the ETF's holdings (same machinery as extraction/category sync) and emits the
canonical signal frame `(time_index, asset_identifier) → signal_weight` under one stable
`signal_uid`.

Portfolios, calendars, `Portfolio` rows, price wiring, and valuation are **ms-markets
(`msm_portfolios`) functionality, not this library's**. The repository demonstrates the full
assembly end-to-end in `examples/ivv_tracking_portfolio_full_workflow.py`, and ships
convenience wiring (`etfhextractor.portfolio_publish` / `etfh portfolio-publish`) that callers
MAY use — but those assemble ms-markets objects on the caller's behalf; they are not library
capabilities to claim.

## The Signal Contract (what we own)

- **Definition-scoped identity** (ADR 0005): `signal_uid` hashes only the definition
  (ticker, source, normalization, validity, backtest window, calendar grid, timeout).
  `asset_list` is updater scope, neutralized in the uid payload — composition changes never
  rotate the series.
- **Guards**: insert at most once per `min_update_interval_days`; only when the extracted
  weights actually changed; unchanged weights are re-stamped shortly before
  `signal_validity_days` expires so a stable composition never lets the forward-fill window
  lapse. Validity must exceed `backtest_start_days` by >= 5 days (defaults 90/60).
- **Session-grid observations** (ADR 0006): every observation is stamped on a market close of
  the configured `calendar_key` (as-of date → that day's close; provider lag → latest completed
  close; at most one observation per session) — never at insertion wall-clock times.
- **Backtest bootstrap**: the FIRST observation is stamped on the session close at/before
  `now - backtest_start_days`, assuming the current composition over that window.
- **Preflight scope**: `get_asset_list()` exposes the resolved component identifiers (required
  by msm_portfolios on first runs to derive the price window).

## Preferred Surfaces

- Python (deliberately NOT in `etfhextractor.__init__`):
  `from etfhextractor.portfolio_signal import ETFHoldingsSignal, ETFHoldingsSignalConfig,
  previous_session_close`
- Signal-only run (writes canonical `SignalWeightsTS` rows, no portfolio):
  `python examples/ivv_tracking_portfolio_full_workflow.py --signal-only`
- Full assembly demonstration (ms-markets objects assembled around the signal):
  `python examples/ivv_tracking_portfolio_full_workflow.py` and the convenience wiring
  `etfh portfolio-publish ...`

## This Skill Must Not Claim

- **that this library creates, owns, or operates portfolios** — portfolio construction,
  `Portfolio` rows, trading calendars, rebalancing, and valuation belong to ms-markets; this
  library contributes the signal those pipelines consume (the example shows the assembly)
- **that this library provides, sources, or validates market prices** — no pricing capability
  of any kind; the example's demo bars are synthetic data and an extension template only
- that the tracker reproduces historical baskets — the bootstrap assumes the CURRENT
  composition over the backtest window
- that components without a unique FIGI mapping were registered or tracked
- that signal rows were written without reading them back (`SignalWeightsTS` by `signal_uid`)

## Working Rules

1. Lead with the signal: configure `ETFHoldingsSignalConfig`, resolve the component universe
   (unresolved components block — a signal on a partial universe misrepresents the ETF; use
   `--register-missing` + `--figi-filter` via the category skill's machinery).
2. When the user wants the full portfolio around the signal, be explicit that the assembly is
   ms-markets functionality: route to the vendored ms-markets portfolio skills (e.g.
   `.agents/skills/ms_markets/portfolios/portfolio_workflow/SKILL.md`) and offer the example /
   convenience wiring as the demonstrated path — calendar, Portfolio row, and price source are
   the caller's ms-markets concerns there (pricing always supplied by the caller).
3. Re-runs are safe: the guards make the signal idempotent per session.
4. For extraction-only or category-only requests, route to
   `.agents/skills/weights_extraction/SKILL.md` /
   `.agents/skills/holdings_category_sync/SKILL.md`.

## Expected Outputs

- the signal definition summary: `signal_uid`, etf ticker, source, guard settings, calendar
  grid, backtest window, resolved component count
- signal run results verified from platform rows (`SignalWeightsTS` rows under the uid, their
  session-close `time_index` values)
- when the user proceeds to assembly: a clear statement that the portfolio objects are
  ms-markets', plus the example/wiring invocation used to demonstrate it
