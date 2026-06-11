"""ETF-tracking signal for the msm_portfolios pipeline.

`ETFHoldingsSignal` is a custom `SignalWeights` DataNode whose update pulls the
ETF's holdings weights from the extraction layer (the same machinery used by
the category-sync workflow) and emits them as the canonical signal frame
`(time_index, asset_identifier) -> signal_weight`. Consumed by
`PortfoliosDataNode`, this produces a portfolio that tracks the ETF
(implementation task 0002).

This module is intentionally not imported from `etfhextractor.__init__`, so
pure extraction never imports the msm_portfolios stack.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
from pydantic import model_validator

from msm_portfolios.configuration import PortfolioConfigBaseModel
from msm_portfolios.data_nodes import SignalWeights
from msm_portfolios.data_nodes.constants import ASSET_IDENTIFIER, SIGNAL_UID

from .mainsequence_categories import (
    derive_component_weights_from_holdings,
    resolve_asset_identifiers_by_ticker,
)
from .models import FundHoldings
from .reader import ETFHoldingsReader

# Stored weights are float64 roundtripped through the MetaTable backend; this
# tolerance treats re-extracted, numerically identical weights as unchanged.
WEIGHT_EQUALITY_TOLERANCE = 1e-9

# Calendar keys whose sessions are synthetic always-open days (close = UTC midnight).
ALWAYS_OPEN_CALENDAR_KEYS = ("24/7", "CRYPTO_24_7")

# Coverage margin (days) the signal validity must keep over the backtest window:
# the portfolio index legitimately reaches price-end + forward-fill (one session)
# and session snapping can add weekend/holiday gaps, so equality is never enough.
VALIDITY_HEADROOM_DAYS = 5


def previous_session_close(
    moment: dt.datetime,
    *,
    calendar_key: str = "NYSE",
) -> dt.datetime:
    """Last completed market close at or before `moment` (UTC).

    Signal observations are stamped on the trading-session grid — the same
    `market_close` timestamps the portfolio values on — never at arbitrary
    wall-clock insertion times. Always-open keys close at UTC midnight.
    """
    if moment.tzinfo is None:
        raise ValueError("previous_session_close requires a timezone-aware moment.")
    moment = moment.astimezone(dt.timezone.utc)
    if calendar_key in ALWAYS_OPEN_CALENDAR_KEYS:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)

    import pandas_market_calendars as mcal

    # 21 calendar days comfortably cover any holiday cluster around `moment`.
    schedule = mcal.get_calendar(calendar_key).schedule(
        start_date=(moment - dt.timedelta(days=21)).date().isoformat(),
        end_date=moment.date().isoformat(),
    )
    closes = [close.to_pydatetime() for close in schedule["market_close"] if close <= moment]
    if not closes:
        raise RuntimeError(
            f"No {calendar_key} session close found in the 21 days before {moment}."
        )
    return closes[-1]


class ETFHoldingsSignalConfig(PortfolioConfigBaseModel):
    """Identity and behavior of one ETF-tracking holdings signal.

    The config is hashed into the deterministic ``signal_uid``, so one config
    equals one tracked ETF series in the canonical SignalWeights table.
    """

    etf_ticker: str
    provider: str | None = None
    fund_url: str | None = None
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",)
    renormalize_weights: bool = True
    signal_validity_days: int = 90
    min_update_interval_days: float = 1.0
    timeout: float = 30.0
    # Backtest bootstrap: the FIRST stored observation is stamped this many days
    # in the past (snapped to the previous session close), so the portfolio
    # backtests the window [now - backtest_start_days, now] with the current
    # composition before live tracking takes over. 0 disables backdating (the
    # first observation lands on the as-of date's session close).
    backtest_start_days: int = 60
    # Trading-session grid for observation timestamps: every stored observation
    # is stamped on this calendar's market close (never an arbitrary insertion
    # wall-clock time), matching the portfolio valuation index.
    calendar_key: str = "NYSE"
    # Updater scope: the resolved component asset identifiers, consumed by the
    # portfolio's preflight get_asset_list() (required on first runs by
    # ms-markets >= 0.0.54). Declarative config, but NEUTRALIZED in the
    # signal_uid payload (_signal_uid_payload below): an ETF rebalance must not
    # rotate the series identity, reset the insert guards, or churn the
    # portfolio configuration hash.
    asset_list: list[str] | None = None

    @model_validator(mode="after")
    def _require_extraction_source(self) -> ETFHoldingsSignalConfig:
        if self.provider is None and self.fund_url is None:
            raise ValueError(
                "Pass provider or fund_url so holdings can be extracted for the signal."
            )
        if self.backtest_start_days < 0:
            raise ValueError("backtest_start_days must be >= 0.")
        if self.backtest_start_days > 0 and (
            self.signal_validity_days < self.backtest_start_days + VALIDITY_HEADROOM_DAYS
        ):
            # The portfolio forward-fills signal weights at most signal_validity_days
            # past an observation, and its index legitimately reaches one session past
            # "now" (price forward-fill); equality leaves zero headroom and the
            # bootstrap observation arrives pre-expired.
            raise ValueError(
                "signal_validity_days must cover backtest_start_days plus "
                f"{VALIDITY_HEADROOM_DAYS} days of headroom (got validity="
                f"{self.signal_validity_days}, backtest={self.backtest_start_days})."
            )
        return self


class ETFHoldingsSignal(SignalWeights):
    """Signal weights that track an ETF's extracted holdings.

    Each update re-extracts the ETF holdings, resolves component tickers to
    asset identifiers through the snapshot layer, and emits the normalized
    weights — guarded so the canonical table is written at most once per
    ``min_update_interval_days`` and only when the weights actually changed.
    """

    @property
    def etf_holdings_config(self) -> ETFHoldingsSignalConfig:
        if not isinstance(self.signal_configuration, ETFHoldingsSignalConfig):
            raise TypeError(
                "ETFHoldingsSignal requires ETFHoldingsSignalConfig as signal_configuration."
            )
        return self.signal_configuration

    def maximum_forward_fill(self) -> dt.timedelta:
        return dt.timedelta(days=self.etf_holdings_config.signal_validity_days)

    def _signal_uid_payload(self) -> dict[str, Any]:
        """Signal identity payload with the updater scope neutralized.

        ``asset_list`` is updater scope, not series identity: the signal_uid
        must stay one stable series per ETF across composition changes
        (rebalances, new registrations). The payload hashes the config as if
        ``asset_list`` were unset, mirroring how msm treats scope fields.
        """
        payload = super()._signal_uid_payload()
        config = payload.get("config")
        if isinstance(config, ETFHoldingsSignalConfig) and config.asset_list is not None:
            payload = {**payload, "config": config.model_copy(update={"asset_list": None})}
        return payload

    def get_asset_list(self) -> None | list:
        # Preflight scope for the portfolio's price-source window (required on
        # first runs by ms-markets >= 0.0.54). The authoritative universe is
        # still the signal output frame.
        asset_list = self.etf_holdings_config.asset_list
        return sorted({str(identifier) for identifier in asset_list}) if asset_list else None

    def dependencies(self) -> dict[str, Any]:
        return {}

    def get_explanation(self) -> str:
        config = self.etf_holdings_config
        source = config.fund_url or f"provider {config.provider}"
        explanation = (
            f"Tracks ETF {config.etf_ticker}: extracts holdings weights from {source} and "
            f"emits them as signal weights. Updates at most every "
            f"{config.min_update_interval_days} day(s), inserting only when the weights changed."
        )
        explanation += (
            f" Observations are stamped on {config.calendar_key} session closes."
        )
        if config.backtest_start_days > 0:
            explanation += (
                f" The first observation is backdated {config.backtest_start_days} days so the "
                "portfolio backtests that window with the current composition."
            )
        return explanation

    def _calculate_signal_weights(self) -> pd.DataFrame:
        config = self.etf_holdings_config
        last_time, last_weights = self._last_stored_weights()
        now = dt.datetime.now(dt.timezone.utc)

        # Guard (a): at most one insertion per min_update_interval_days.
        if last_time is not None and now - last_time < dt.timedelta(
            days=config.min_update_interval_days
        ):
            self._log_info(
                f"Skipping {config.etf_ticker} signal update: last observation at {last_time} is "
                f"within the {config.min_update_interval_days}-day update interval."
            )
            return self._empty_signal_frame()

        fund_holdings = self._extract_fund_holdings()
        weights_by_symbol = derive_component_weights_from_holdings(
            fund_holdings,
            allowed_asset_classes=config.allowed_asset_classes,
        )
        if not weights_by_symbol:
            raise RuntimeError(
                f"No component weights were extracted for {config.etf_ticker}; refusing to emit "
                "an empty tracking signal."
            )

        identifiers_by_symbol, missing, ambiguous = resolve_asset_identifiers_by_ticker(
            component_symbols=sorted(weights_by_symbol),
        )
        if missing or ambiguous:
            raise RuntimeError(
                f"ETF {config.etf_ticker} cannot be tracked: unresolved components would "
                f"misrepresent the ETF. missing={missing} ambiguous={ambiguous}"
            )

        # Provider weights are percents; emit fractions.
        weights = {
            identifiers_by_symbol[symbol]: weight / 100.0
            for symbol, weight in weights_by_symbol.items()
        }
        if config.renormalize_weights:
            total = sum(weights.values())
            if total <= 0:
                raise RuntimeError(
                    f"Extracted weights for {config.etf_ticker} sum to {total}; cannot renormalize."
                )
            weights = {identifier: weight / total for identifier, weight in weights.items()}

        # Guard (b): only insert when the weights actually changed — UNLESS the
        # last observation is close to falling out of the validity window. The
        # portfolio forward-fills at most signal_validity_days past an
        # observation, so an unchanged-but-aging series must re-stamp before it
        # expires or the portfolio starves on stable compositions.
        if last_weights and self._weights_unchanged(weights, last_weights):
            refresh_after = dt.timedelta(days=config.signal_validity_days) - dt.timedelta(
                days=max(2.0 * config.min_update_interval_days, 2.0)
            )
            if last_time is not None and now - last_time >= refresh_after:
                self._log_info(
                    f"Re-stamping unchanged {config.etf_ticker} weights: last observation at "
                    f"{last_time} is approaching the {config.signal_validity_days}-day validity."
                )
            else:
                self._log_info(
                    f"Skipping {config.etf_ticker} signal update: extracted weights are "
                    f"unchanged since {last_time}."
                )
                return self._empty_signal_frame()

        # Observations live on the trading-session grid (previous market close),
        # never at arbitrary insertion wall-clock times — they must align with
        # the portfolio's session-close valuation index.
        if last_time is None and config.backtest_start_days > 0:
            # Backtest bootstrap (first run only): backdate the observation so the
            # portfolio values the last backtest_start_days sessions with the
            # current composition before live tracking takes over.
            time_index = previous_session_close(
                now - dt.timedelta(days=config.backtest_start_days),
                calendar_key=config.calendar_key,
            )
            self._log_info(
                f"First {config.etf_ticker} observation backdated to the session close "
                f"{time_index} ({config.backtest_start_days}-day backtest bootstrap)."
            )
        else:
            time_index = self._observation_time(
                fund_holdings,
                last_time=last_time,
                now=now,
                calendar_key=config.calendar_key,
            )
            if time_index is None:
                # Both the as-of close and the latest completed close are already
                # covered: at most one observation per session, by construction.
                self._log_info(
                    f"Skipping {config.etf_ticker} signal update: an observation for the "
                    f"current session already exists at {last_time}."
                )
                return self._empty_signal_frame()
        frame = pd.DataFrame(
            {"signal_weight": list(weights.values())},
            index=pd.MultiIndex.from_arrays(
                [[time_index] * len(weights), list(weights.keys())],
                names=["time_index", ASSET_IDENTIFIER],
            ),
        ).sort_index()

        update_statistics = getattr(self, "update_statistics", None)
        if update_statistics is not None:
            frame = update_statistics.filter_df_by_latest_value(frame)
        return frame

    def _extract_fund_holdings(self) -> FundHoldings:
        config = self.etf_holdings_config
        reader = ETFHoldingsReader(timeout=config.timeout)
        if config.fund_url is not None:
            return reader.read(config.fund_url)
        return reader.read_ticker(config.etf_ticker, provider=config.provider)

    def _last_stored_weights(self) -> tuple[dt.datetime | None, dict[str, float]]:
        """Latest stored observation for this signal_uid: (time, identifier→weight)."""
        existing = self.get_df_between_dates(dimension_filters={SIGNAL_UID: [self.signal_uid]})
        if existing is None or existing.empty:
            return None, {}

        flat = existing.reset_index()
        flat["time_index"] = pd.to_datetime(flat["time_index"], utc=True)
        last_time = flat["time_index"].max()
        last_rows = flat[flat["time_index"] == last_time]
        last_weights = {
            str(row[ASSET_IDENTIFIER]): float(row["signal_weight"])
            for _, row in last_rows.iterrows()
            if pd.notna(row["signal_weight"])
        }
        return last_time.to_pydatetime(), last_weights

    @staticmethod
    def _weights_unchanged(
        new_weights: dict[str, float],
        old_weights: dict[str, float],
        *,
        tolerance: float = WEIGHT_EQUALITY_TOLERANCE,
    ) -> bool:
        if set(new_weights) != set(old_weights):
            return False
        return all(
            abs(new_weights[identifier] - old_weights[identifier]) <= tolerance
            for identifier in new_weights
        )

    @staticmethod
    def _observation_time(
        fund_holdings: FundHoldings,
        *,
        last_time: dt.datetime | None,
        now: dt.datetime,
        calendar_key: str,
    ) -> dt.datetime | None:
        """Session close the observation belongs to, or None when that session
        is already covered.

        The provider's as-of date describes END-OF-DAY holdings, so the natural
        timestamp is that date's market close (previous close when the as-of
        day is not a session). When the as-of close is not strictly newer than
        the last stored observation — the provider lagging a real weight change
        — the latest completed close is used instead. Observations never land
        at insertion wall-clock times, and never more than one per session."""
        candidate: dt.datetime | None = None
        if fund_holdings.as_of_date:
            try:
                parsed_ts = pd.to_datetime(fund_holdings.as_of_date, utc=True)
                parsed = None if pd.isna(parsed_ts) else parsed_ts.to_pydatetime()
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                end_of_as_of_day = parsed.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
                candidate = previous_session_close(
                    min(end_of_as_of_day, now), calendar_key=calendar_key
                )
        if candidate is None:
            candidate = previous_session_close(now, calendar_key=calendar_key)
        if last_time is None or candidate > last_time:
            return candidate
        latest_completed = previous_session_close(now, calendar_key=calendar_key)
        if latest_completed > last_time:
            return latest_completed
        return None

    @staticmethod
    def _empty_signal_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=["time_index", ASSET_IDENTIFIER, "signal_weight"])

    def _log_info(self, message: str) -> None:
        # The DataNode logger property requires initialized node state; guard so
        # the guards also work on partially-constructed instances (tests).
        try:
            logger = self.logger
        except Exception:
            logger = None
        if logger is not None:
            logger.info(message)


__all__ = [
    "ALWAYS_OPEN_CALENDAR_KEYS",
    "ETFHoldingsSignal",
    "ETFHoldingsSignalConfig",
    "VALIDITY_HEADROOM_DAYS",
    "WEIGHT_EQUALITY_TOLERANCE",
    "previous_session_close",
]
