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
    signal_validity_days: int = 30
    min_update_interval_days: float = 1.0
    timeout: float = 30.0

    @model_validator(mode="after")
    def _require_extraction_source(self) -> ETFHoldingsSignalConfig:
        if self.provider is None and self.fund_url is None:
            raise ValueError(
                "Pass provider or fund_url so holdings can be extracted for the signal."
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

    def get_asset_list(self) -> None | list:
        # Signal-driven universe: the authoritative universe is the output frame.
        return None

    def dependencies(self) -> dict[str, Any]:
        return {}

    def get_explanation(self) -> str:
        config = self.etf_holdings_config
        source = config.fund_url or f"provider {config.provider!r}"
        return (
            f"<p>{self.__class__.__name__}: tracks ETF {config.etf_ticker} by extracting its "
            f"holdings weights from {source} and emitting them as signal weights. Updates run at "
            f"most every {config.min_update_interval_days} day(s) and insert only when the "
            f"weights changed.</p>"
        )

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

        # Guard (b): only insert when the weights actually changed.
        if last_weights and self._weights_unchanged(weights, last_weights):
            self._log_info(
                f"Skipping {config.etf_ticker} signal update: extracted weights are unchanged "
                f"since {last_time}."
            )
            return self._empty_signal_frame()

        time_index = self._observation_time(
            fund_holdings,
            last_time=last_time,
            fallback=now,
        )
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
        fallback: dt.datetime,
    ) -> dt.datetime:
        """Provider as-of date when parseable and strictly newer than the last
        stored observation; otherwise the extraction time (keeps the series
        monotonic when the provider's as-of lags a real weight change)."""
        parsed: dt.datetime | None = None
        if fund_holdings.as_of_date:
            try:
                parsed_ts = pd.to_datetime(fund_holdings.as_of_date, utc=True)
                parsed = None if pd.isna(parsed_ts) else parsed_ts.to_pydatetime()
            except (TypeError, ValueError):
                parsed = None
        if parsed is None:
            return fallback
        if last_time is not None and parsed <= last_time:
            return fallback
        return parsed

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
    "ETFHoldingsSignal",
    "ETFHoldingsSignalConfig",
    "WEIGHT_EQUALITY_TOLERANCE",
]
