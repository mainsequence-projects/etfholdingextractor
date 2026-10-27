"""Persisted trading calendars for ETF-tracking portfolios (ADR 0006).

Every ms-markets Portfolio row references a persisted Calendar (`calendar_uid` NOT NULL FK), so
`ensure_trading_calendar` always returns a Calendar row. It uses Markets registry row calls only
(`Calendar`, `CalendarDate`, `CalendarSession`), which run on the Markets API when the
application selected the ms-markets remote backend (ADR 0047) and on the attached runtime
otherwise.

This module imports ms-markets lazily and never the `msm_portfolios` stack, so applications that
only need calendars can import it without the portfolio layer.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# US-listed ETFs trade on US equity sessions; the rebalance index and portfolio
# valuations must follow that trading calendar, not a synthetic 24/7 one.
US_EQUITY_CALENDAR_KEY = "NYSE"

# Calendar keys whose sessions are synthetic always-open days (close = UTC midnight).
ALWAYS_OPEN_CALENDAR_KEYS = ("24/7", "CRYPTO_24_7")

# NOTE: ms-markets >= 1.0.7 rebalance strategies take no calendar: ImmediateSignal
# rebalances on the signal's observations, which ETFHoldingsSignal stamps on
# calendar_key session closes. The Portfolio row's calendar stays obligatory
# (PortfolioTable.calendar_uid is a NOT NULL FK), so even ALWAYS_OPEN_CALENDAR_KEYS
# persist a row.
# Materialized session coverage around "today": enough past for the backtest
# bootstrap plus headroom, and enough future for scheduled updates without
# re-materializing on every publish.
CALENDAR_PAST_BUFFER_DAYS = 30
CALENDAR_FUTURE_HORIZON_DAYS = 366


def required_calendar_window(
    *,
    backtest_start_days: int,
    today: dt.date,
) -> tuple[dt.date, dt.date]:
    """Session window the persisted calendar must cover for one publish."""
    start = today - dt.timedelta(days=max(backtest_start_days, 0) + CALENDAR_PAST_BUFFER_DAYS)
    end = today + dt.timedelta(days=CALENDAR_FUTURE_HORIZON_DAYS)
    return start, end


def ensure_trading_calendar(
    calendar_key: str,
    *,
    backtest_start_days: int = 0,
    today: dt.date | None = None,
) -> Any:
    """Ensure a persisted ms-markets Calendar exists for `calendar_key`.

    The calendar is obligatory in the portfolio architecture (ms-markets >=
    0.0.58): every Portfolio row must reference a persisted Calendar through the
    NOT NULL `calendar_uid` FK, so this ALWAYS returns a Calendar row.

    Market keys use the msm util `Calendar.create_from_pandas_calendar`, which
    upserts the typed Calendar row and materializes CalendarDate/CalendarSession
    rows from pandas_market_calendars — exactly what ms-markets'
    `resolve_rebalance_calendar` resolves into a `PersistedCalendarSchedule`.
    Always-open keys ("24/7") persist an always-open calendar row for the FK.

    Idempotent and write-frugal: when the persisted calendar already covers the
    required window, the existing row is returned with zero writes; otherwise
    the window is extended (merged) and re-materialized.
    """
    from msm.api.calendars import Calendar, CalendarType

    resolved_today = today or dt.datetime.now(dt.timezone.utc).date()
    needed_from, needed_to = required_calendar_window(
        backtest_start_days=backtest_start_days, today=resolved_today
    )

    existing = Calendar.filter(unique_identifier=calendar_key, limit=1)
    calendar = existing[0] if existing else None
    if calendar is not None:
        if calendar.valid_from <= needed_from and calendar.valid_to >= needed_to:
            return calendar

    valid_from = min(needed_from, calendar.valid_from) if calendar is not None else needed_from
    valid_to = max(needed_to, calendar.valid_to) if calendar is not None else needed_to

    if calendar_key in ALWAYS_OPEN_CALENDAR_KEYS:
        return _persist_always_open_calendar(
            calendar_key=calendar_key, valid_from=valid_from, valid_to=valid_to
        )

    source_identifier = calendar_key
    if calendar is not None and calendar.source_identifier:
        source_identifier = calendar.source_identifier
    return Calendar.create_from_pandas_calendar(
        source_identifier=source_identifier,
        unique_identifier=calendar_key,
        display_name=f"{calendar_key} trading sessions",
        calendar_type=CalendarType.TRADING,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _persist_always_open_calendar(
    *,
    calendar_key: str,
    valid_from: dt.date,
    valid_to: dt.date,
) -> Any:
    """Persist an always-open Calendar row + dates and sessions for the Portfolio FK.

    msm ships the materialization builder but no one-call util for always-open
    calendars; the Portfolio row still needs a persisted calendar to satisfy the
    obligatory FK. The rows are written with one set-based `upsert_many` per
    table, on the same conflict keys as ms-markets' own materialization.
    """
    from msm.api.calendars import Calendar, CalendarDate, CalendarSession, CalendarType
    from msm.services.calendars import build_always_open_calendar_materialization

    calendar = Calendar.upsert(
        unique_identifier=calendar_key,
        display_name=f"{calendar_key} always-open sessions",
        calendar_type=CalendarType.TRADING,
        timezone="UTC",
        source="always_open",
        source_identifier=calendar_key,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    rows = build_always_open_calendar_materialization(
        calendar_uid=calendar.uid,
        start_date=valid_from,
        end_date=valid_to,
    )
    CalendarDate.upsert_many(rows.dates)
    CalendarSession.upsert_many(rows.sessions)
    return calendar


__all__ = [
    "ALWAYS_OPEN_CALENDAR_KEYS",
    "CALENDAR_FUTURE_HORIZON_DAYS",
    "CALENDAR_PAST_BUFFER_DAYS",
    "US_EQUITY_CALENDAR_KEY",
    "ensure_trading_calendar",
    "required_calendar_window",
]
