from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class Holding:
    ticker: str
    name: str
    weight: float
    sector: str | None = None
    asset_class: str | None = None
    market_value: float | None = None
    notional_value: float | None = None
    quantity: float | None = None
    price: float | None = None
    location: str | None = None
    exchange: str | None = None
    currency: str | None = None
    fx_rate: float | None = None
    accrual_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FundHoldings:
    url: str
    download_url: str
    fund_name: str
    as_of_date: str
    holdings: tuple[Holding, ...]
    artifact_directory: str | None = None

    def ticker_weights(self) -> dict[str, float]:
        weights: dict[str, float] = {}
        for holding in self.holdings:
            weights[holding.ticker] = round(weights.get(holding.ticker, 0.0) + holding.weight, 8)
        return weights

    def with_artifact_directory(self, artifact_directory: str) -> FundHoldings:
        return replace(self, artifact_directory=artifact_directory)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "url": self.url,
            "download_url": self.download_url,
            "fund_name": self.fund_name,
            "as_of_date": self.as_of_date,
            "holdings": [holding.to_dict() for holding in self.holdings],
            "ticker_weights": self.ticker_weights(),
        }
        if self.artifact_directory is not None:
            payload["artifact_directory"] = self.artifact_directory
        return payload
