from importlib.metadata import PackageNotFoundError, version

from .exceptions import (
    DownloadLinkNotFoundError,
    ETFHoldingsError,
    FetchError,
    UnsupportedProviderError,
    WorkbookParseError,
)
from .models import FundHoldings, Holding
from .reader import ETFHoldingsReader, extract_many_ticker_weights, extract_ticker_weights

__all__ = [
    "DownloadLinkNotFoundError",
    "ETFHoldingsError",
    "ETFHoldingsReader",
    "FetchError",
    "FundHoldings",
    "Holding",
    "UnsupportedProviderError",
    "WorkbookParseError",
    "extract_many_ticker_weights",
    "extract_ticker_weights",
]

try:
    __version__ = version("etfh-extractor")
except PackageNotFoundError:
    __version__ = "0.0.0"
