# ADR 0005: Tracking-Signal Identity Is Definition-Scoped (No Rotation on Composition)

- Status: Accepted
- Date: 2026-06-10

## Context

`ETFHoldingsSignal` writes its series into the canonical `SignalWeightsTS` table keyed by
`(time_index, signal_uid, asset_identifier)`, where `signal_uid` is the hash of the signal
configuration. ms-markets >= 0.0.54 additionally requires the signal to expose a non-empty
preflight `get_asset_list()` on first portfolio runs (the portfolio derives its price-source
update window from it), which forced the resolved component identifiers (`asset_list`) into the
signal configuration.

Hashing `asset_list` into `signal_uid` was tried and immediately produced duplicate signals on
the platform: every configuration difference mints a new series. Left in place, **every IVV
rebalance, constituent change, or even resolution-order difference would rotate the uid** —
orphaning the prior series, resetting the insert guards (daily throttle and changed-weights both
read history *by uid*, so each rotation looks like a first run and re-inserts the full basket),
and churning the portfolio configuration hash.

## Decision

**The signal's identity is its definition, not its output.** A tracker's definition is the
process — "track this ETF from this source under these rules" — and the basket is the signal's
output *data*, which the storage schema already models as time-varying rows under one uid.

- `signal_uid` is derived only from the **definition fields**: `etf_ticker`, `provider` /
  `fund_url`, `allowed_asset_classes`, `renormalize_weights`, `signal_validity_days`,
  `min_update_interval_days`, `backtest_start_days`, `calendar_key` (ADR 0006), `timeout`.
  Changing any of these is a different signal and **does** rotate the uid (e.g. SPY vs IVV
  provably differ).
- `asset_list` is **updater scope**: it stays a declarative configuration field (visible,
  serialized, consumed by the preflight `get_asset_list()`), but it is **neutralized in the
  `signal_uid` payload** — `ETFHoldingsSignal._signal_uid_payload()` hashes the configuration as
  if the scope were unset. The invariance is pinned by a test using the real
  `compute_signal_uid`: no scope, scope A, and scope B hash identically; a different ETF does not.

## Rationale

1. **Portfolio continuity at the moment it matters.** At a rebalance the portfolio must compute
   turnover (`weights_before` vs `weights_current`) to liquidate leavers and charge fees; the
   portfolio reads the signal *by uid*, so rotating at the rebalance severs history exactly at
   the boundary where it is needed.
2. **The insert guards presuppose one series.** "Insert at most daily, only on change" compares
   against the last stored observation *for this uid*; rotation defeats both guards.
3. **msm's own design answers the question.** Dynamic-universe contrib signals (`MarketCap`
   top-N) change composition on every update under one uid; `ExternalWeights`' identity is the
   artifact location while the weights inside change freely. The one rotate-by-design signal,
   `FixedWeights`, is precisely the case where the weights *are* the definition — the opposite of
   a tracker.
4. **`asset_list` is not even composition-of-record** — it is a preflight hint for the price
   window; the authoritative universe is the signal output frame. An identity that changes when a
   hint is reordered, with byte-identical output, is a broken identity function.

## Consequences

- One stable series per ETF, forever; guards and portfolio turnover work across rebalances.
- Consumers must handle constituents entering/leaving within one series — inherent to trackers,
  and already handled by the msm pipeline (pivot + `fillna(0)`, liquidation via previous weights).
- The neutralized payload defines the stable uid for a given definition; signal-metadata rows
  minted by earlier configurations (the with-`asset_list`-hashed and pre-`asset_list` runs) are
  orphans and should be deleted from the platform.
- Definition changes still rotate by design: the backtest bootstrap, the session-close
  observation grid (`calendar_key`), and the validity defaults (ADR 0006) moved the
  IVV/ishares-defaults uid to `9305b5473bb338b394e2fd59b99506c7`, superseding `5bc0d9f2…`
  (wall-clock-stamped interim), `9f926f64…` (never ran to completion), and the earlier orphans
  `6603c180…` / `190f4c64…`.
- Signal display metadata (`get_explanation()`) is plain text, never HTML.
