# ADR 0006: Tracking Portfolios Follow a Persisted Trading Calendar and Backtest a Bootstrap Window

- Status: Accepted; amended 2026-10-01 for ms-markets 2.x and 2026-10-26 for ms-markets 3.0 (see Amendments)
- Date: 2026-06-10

## Context

The first published IVV tracker used `calendar_key="24/7"` — msm's synthetic always-open
schedule. For a US-listed ETF that is wrong twice over: the portfolio index is the calendar's
session closes (`PortfoliosDataNode._generate_new_index` with the default
`portfolio_prices_frequency="1d"`), so a 24/7 calendar values the portfolio at **midnight UTC
every day, including weekends and holidays**, and the Portfolio row carried **no calendar
linkage at all** even though `PortfolioTable.calendar_uid` is a real FK to `CalendarTable.uid`
(`calendar_name` is the deprecated display alias).

Separately, the signal's first observation landed at the provider as-of date (≈ today), so a
freshly published tracker had no history: the backtest effectively started at publish time.

ms-markets already ships the right machinery:

- `Calendar.create_from_pandas_calendar(...)` (msm util) upserts the typed `Calendar` row and
  materializes `CalendarDate`/`CalendarSession` rows from **pandas_market_calendars** for a
  validity window.
- `resolve_rebalance_calendar(calendar_key)` (msm_portfolios) prefers that persisted calendar —
  matching `Calendar.unique_identifier` / `source_identifier` — and wraps it in a
  `PersistedCalendarSchedule` that reads sessions from the backend; raw pandas_market_calendars
  is only the legacy fallback, and `"24/7"` resolves synthetically.

## Decision

1. **US ETF trackers follow the US trading calendar.** `publish_etf_tracking_portfolio`
   defaults `calendar_key="NYSE"`. `ensure_trading_calendar()` persists the calendar through the
   msm util (`Calendar.create_from_pandas_calendar`, source `pandas_market_calendars`) and is
   write-frugal: if the persisted row already covers the required window
   (`[today - backtest - 30d buffer, today + 366d]`, `required_calendar_window()`), it is reused
   with zero writes; otherwise the validity window is merged (never shrunk) and re-materialized.
2. **The calendar is OBLIGATORY and attached to the Portfolio row by FK** (ms-markets >=
   0.0.58 portfolio architecture): `PortfolioTable.calendar_uid` is a **NOT NULL** FK to
   `CalendarTable.uid` with `ondelete=RESTRICT`, the typed `Portfolio` payloads require it
   (`PortfolioUpdate` rejects null), the legacy `calendar_name` field **no longer exists**
   (`extra="forbid"`), and `PortfoliosDataNode.run()`'s pointer update refuses rows without a
   calendar. `Portfolio.upsert(..., calendar_uid=calendar.uid)` therefore always carries the
   persisted calendar — including for always-open keys (`"24/7"`, `"CRYPTO_24_7"`), which the
   rebalancer still resolves synthetically but which now persist an always-open Calendar row
   (`_persist_always_open_calendar`: `Calendar.upsert` + msm's
   `build_always_open_calendar_materialization` + `materialize_calendar_rows`) to satisfy the FK.
   The rebalancer resolves the same `calendar_key` into the same persisted sessions, so the
   schedule the portfolio values on and the calendar the row points to cannot diverge.
3. **Signal observations live on the session grid — never at insertion wall-clock times.**
   Every stored observation is stamped on a market close of the signal's `calendar_key`
   (default NYSE, supplied by publish so the signal grid equals the portfolio valuation grid):
   the provider's as-of date describes end-of-day holdings, so it maps to that date's close
   (previous close when the as-of day is not a session, e.g. a weekend as-of); when the as-of
   close is not strictly newer than the stored series, the latest **completed** close is used;
   and at most **one observation per session** exists by construction. A wall-clock stamp (the
   first implementation backdated to `now - 60d`, which landed on a Saturday at the run's
   time-of-day) misaligns with the session-close valuation index and makes validity arithmetic
   depend on the minute the run started.
4. **The first run backtests a bootstrap window.** `ETFHoldingsSignalConfig.backtest_start_days`
   (default 60) stamps the signal's **first** observation on the session close at/before
   `now - backtest_start_days`, so the portfolio values the window `[now - 60d, now]` with the
   current composition before live tracking takes over. Runs with existing history never
   backdate, so the bootstrap can never rewrite or restart a live series.
5. **Validity must exceed the bootstrap with headroom, and unchanged weights re-stamp.** The
   portfolio forward-fills signal weights at most `signal_validity_days` past an observation
   (`interpolate_index` cuts off at `maximum_forward_fill()`), and its index legitimately
   reaches one session past "now" (price forward-fill) — so equality (60/60) ships a
   pre-expired bootstrap. The validator requires
   `signal_validity_days >= backtest_start_days + 5` (defaults 90/60). And because guard (b)
   ("insert only on change") would otherwise let a stable composition silently fall out of the
   forward-fill window and starve the portfolio forever, the signal **re-stamps unchanged
   weights** once the last observation approaches expiry
   (`now - last_time >= validity - max(2 x min_update_interval_days, 2d)`).

## Consequences

- Portfolio values land on real NYSE session closes (no weekend/holiday rows); the engine
  superset includes `CalendarDateTable` and `CalendarSessionTable` so one process-wide runtime
  serves calendar materialization and the rebalancer's session reads.
- `ensure_trading_calendar()` never returns None and `ms-markets>=0.0.58` is the dependency
  floor — older releases had optional calendar linkage and a `calendar_name` field that 0.0.58
  removed.
- A freshly published tracker has ~60 trading days of backtested history immediately; the
  backtest assumes the current composition over that window — the documented and accepted
  semantics of a bootstrap (the true historical baskets are unknown to the extractor).
- `backtest_start_days`, `calendar_key`, and the `signal_validity_days` default are
  **definition** fields (ADR 0005), so the stable IVV/ishares-defaults uid is
  `9305b5473bb338b394e2fd59b99506c7`; earlier uids (`6603c180…`, `190f4c64…`, `9f926f64…`, and
  `5bc0d9f2…` — the wall-clock-stamped interim series) are orphans to delete from the platform.
- The example publishes demo bars **on the same NYSE session closes** (pandas_market_calendars
  schedule), so the price index and valuation index align exactly; pandas-market-calendars is a
  runtime dependency of `etfhextractor`.
- `--calendar-key` / `--backtest-start-days` are exposed on the CLI (`etfh portfolio-publish`)
  and the example.

## Amendment (2026-10-01): ms-markets 2.x and Main Sequence SDK 9

ms-markets 1.0.6 and 1.0.7, carried into 2.0.0, moved execution and valuation timing out of the
rebalance strategy. The decisions above still hold, but their mechanism now reads as follows:

- **Rebalance strategies take no calendar.** `RebalanceStrategyBase` forbids extra fields and has
  no `calendar_key`, so the builder constructs `ImmediateSignal()`. It rebalances on the signal's
  observations, which decision 3 stamps on the `calendar_key` session closes; that is now how the
  calendar reaches execution.
- **Valuations follow the valuation source.** `PortfoliosDataNode` is valuation-only and values
  the portfolio on the valuation source's observations through `ValuationAlignmentPolicy`
  (default maximum staleness one day); it no longer builds an index from calendar sessions. With
  a session-close price source, such as the example's demo bars, valuations still land on
  session closes only. A price source with weekend or holiday rows now produces valuations on
  those rows.
- `resolve_rebalance_calendar` now serves calendar-relative strategies (`CalendarEventSignal`
  with `PortfolioCalendarEvents`), requires a persisted calendar, and no longer resolves `"24/7"`
  synthetically. `ImmediateSignal` portfolios do not call it.
- **Decision 2 is unchanged.** `PortfolioTable.calendar_uid` is still a NOT NULL FK and
  `PortfoliosDataNode.run()` still refuses a Portfolio row without it, so
  `ensure_trading_calendar()` and `Portfolio.upsert(..., calendar_uid=...)` keep persisting and
  attaching the calendar, including for always-open keys.
- **Decision 5's forward-fill mechanism is gone.** The 2.x portfolio path reads exact signal
  observations and no longer calls `SignalWeights.interpolate_index`, so `maximum_forward_fill()`
  no longer limits how long executed weights are held. The validator, the re-stamp guard, and the
  hashed `signal_validity_days` definition field are unchanged, so the signal identity (ADR 0005)
  does not rotate. Whether to keep that field and guard is a separate decision.
- Updater runs no longer take `debug_mode` or `force_update`: SDK 8.1 removed them, and every
  run executes immediately in-process. The builder and the example call `run()` without them.

The default IVV/ishares signal uid computes offline to `495a8b180d0a216e563cd3f83316da7f` on both
the ms-markets 1.0.2 / SDK 8.0.7 stack and the ms-markets 2.0.0 / SDK 9 stack, so the move to
ms-markets 2.x does not create a new signal series. The `9305b547…` value recorded above predates
ms-markets 1.0.2.

## Amendment (2026-10-26): ms-markets 3.0 and the Markets API

The decisions are unchanged. `ensure_trading_calendar` moved to the light
`etfhextractor.calendars` module (re-exported by `portfolio_publish`) and uses registry row calls
only, so under ms-markets' remote backend (ms-markets ADR 0047) it runs on the Markets API:
always-open calendars write their dates and sessions with `CalendarDate.upsert_many` and
`CalendarSession.upsert_many` on the same conflict keys as `materialize_calendar_rows`, which is
no longer called. The default IVV/ishares signal uid still computes offline to
`495a8b180d0a216e563cd3f83316da7f` on ms-markets 3.0.0.
