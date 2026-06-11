# ADR 0006: Tracking Portfolios Follow a Persisted Trading Calendar and Backtest a Bootstrap Window

- Status: Accepted
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
