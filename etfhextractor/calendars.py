"""Stored trading calendars for ETF-tracking portfolios and their assets (ADR 0006).

Every ms-markets Portfolio row references a stored Calendar (`calendar_uid` NOT NULL FK), and since
ms-markets 4.0.0 every asset that has price bars is linked to one (`AssetCalendar`, ms-markets
ADR 0056). `ensure_trading_calendar` returns the stored Calendar of a key, writing it once when it
is missing. It uses Markets registry row calls only (`Calendar.filter`,
`Calendar.create_from_pandas_calendar`), which run on the Markets API when the application
selected the ms-markets remote backend (ADR 0047) and on the attached runtime otherwise.

A stored calendar is session rules and exceptions written to the last date pandas-market-calendars
can answer for (ms-markets ADR 0055), so nothing extends it as time passes.

This module imports ms-markets lazily and never the `msm_portfolios` stack, so applications that
only need calendars can import it without the portfolio layer.
"""

from __future__ import annotations

from typing import Any

# US-listed ETFs and their US components trade on US equity sessions; the rebalance index,
# portfolio valuations and the components' price bars follow that calendar.
US_EQUITY_CALENDAR_KEY = "NYSE"

# Stored calendar keys whose sessions are the library's always-open `24/7` calendar: every day,
# closing at the next UTC midnight.
ALWAYS_OPEN_CALENDAR_KEYS = ("24/7", "CRYPTO_24_7")

_ALWAYS_OPEN_LIBRARY_CALENDAR = "24/7"


def ensure_trading_calendar(calendar_key: str) -> Any:
    """Return the stored ms-markets Calendar whose `unique_identifier` is `calendar_key`.

    One `Calendar.filter` read when it exists. A missing one is written once with
    `Calendar.create_from_pandas_calendar`: from the library calendar of the same name, or from
    the library's `24/7` calendar for `ALWAYS_OPEN_CALENDAR_KEYS`. An existing calendar is never
    written again: taking it to a newer library release is the Markets deployment's
    `resync-calendars` Job.
    """
    from msm.api.calendars import Calendar, CalendarType

    existing = Calendar.filter(unique_identifier=calendar_key, limit=1)
    if existing:
        return existing[0]
    always_open = calendar_key in ALWAYS_OPEN_CALENDAR_KEYS
    return Calendar.create_from_pandas_calendar(
        _ALWAYS_OPEN_LIBRARY_CALENDAR if always_open else calendar_key,
        calendar_key,
        display_name=(
            f"{calendar_key} always-open sessions"
            if always_open
            else f"{calendar_key} trading sessions"
        ),
        calendar_type=CalendarType.TRADING,
    )


__all__ = [
    "ALWAYS_OPEN_CALENDAR_KEYS",
    "US_EQUITY_CALENDAR_KEY",
    "ensure_trading_calendar",
]
