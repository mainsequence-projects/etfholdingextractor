"""The example application's own portfolio series tables (ms-markets ADR 0047).

etfhextractor never writes the Markets core portfolio tables. An application declares
contract instances in its own MetaTables namespace with the ms-markets factories in
`msm_portfolios.time_index.contract_instances`, migrates them with its own migration provider,
and passes them to `etfhextractor.portfolio_publish.build_etf_tracking_portfolio(instances=...)`.

This example application does exactly that: the four instances below live in the
`etfhextractor-example` namespace (physical tables `etfh_example__<contract>__main`) and are
migrated by `etfh_example_migrations:migration` (`examples/etfh_example_migrations/`); the
Markets tables they reference by foreign key (Portfolio, Asset, SignalMetadata) are copied into
`ExampleBase.metadata` and are never created by that provider. Import this module with the
`examples/` directory on `sys.path`, as the example scripts do.
"""

from __future__ import annotations

from metatables import sqlalchemy_naming_convention
from msm_portfolios.services.series_moves import PortfolioSeriesTables
from msm_portfolios.time_index.contract_instances import (
    configured_portfolio_rebalance_state_storage,
    configured_portfolio_weights_storage,
    configured_portfolios_storage,
    configured_signal_weights_storage,
)
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

EXAMPLE_NAMESPACE = "etfhextractor-example"
EXAMPLE_STORAGE_APP = "etfh_example"
EXAMPLE_INSTANCE_KEY = "main"


class ExampleBase(DeclarativeBase):
    """The example application's own declarative base for its instances."""

    metadata = MetaData(naming_convention=sqlalchemy_naming_convention())


_INSTANCE = {
    "instance_key": EXAMPLE_INSTANCE_KEY,
    "namespace": EXAMPLE_NAMESPACE,
    "storage_app": EXAMPLE_STORAGE_APP,
    "base": ExampleBase,
}

ExampleSignalWeightsStorage = configured_signal_weights_storage(**_INSTANCE)
ExamplePortfolioWeightsStorage = configured_portfolio_weights_storage(**_INSTANCE)
ExamplePortfolioRebalanceStateStorage = configured_portfolio_rebalance_state_storage(**_INSTANCE)
ExamplePortfoliosStorage = configured_portfolios_storage(**_INSTANCE)

EXAMPLE_INSTANCE_MODELS = [
    ExampleSignalWeightsStorage,
    ExamplePortfolioWeightsStorage,
    ExamplePortfolioRebalanceStateStorage,
    ExamplePortfoliosStorage,
]


def example_instances() -> PortfolioSeriesTables:
    """The example application's `PortfolioSeriesTables` (`etfh portfolio-publish --instances`)."""
    return PortfolioSeriesTables(
        values=ExamplePortfoliosStorage,
        weights=ExamplePortfolioWeightsStorage,
        rebalance_state=ExamplePortfolioRebalanceStateStorage,
        signal_weights=ExampleSignalWeightsStorage,
    )


__all__ = [
    "EXAMPLE_INSTANCE_KEY",
    "EXAMPLE_INSTANCE_MODELS",
    "EXAMPLE_NAMESPACE",
    "EXAMPLE_STORAGE_APP",
    "ExampleBase",
    "ExamplePortfolioRebalanceStateStorage",
    "ExamplePortfolioWeightsStorage",
    "ExamplePortfoliosStorage",
    "ExampleSignalWeightsStorage",
    "example_instances",
]
