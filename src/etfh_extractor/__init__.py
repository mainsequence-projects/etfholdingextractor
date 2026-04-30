from importlib.metadata import PackageNotFoundError, version

from .exceptions import (
    DownloadLinkNotFoundError,
    ETFHoldingsError,
    FetchError,
    UnsupportedProviderError,
    WorkbookParseError,
)
from .mainsequence_categories import (
    AssetCategorySyncResult,
    HOLDINGS_ASSET_CATEGORY_PREFIX,
    HoldingsAssetCategoryPlan,
    build_holdings_asset_category_plan,
    build_holdings_asset_category_unique_identifier,
    derive_component_symbols_from_holdings,
    infer_holdings_component_provider,
    resolve_existing_assets_by_ticker,
    sync_holdings_asset_category,
)
from .models import FundHoldings, Holding
from .reader import (
    ETFHoldingsReader,
    extract_many_ticker_weights,
    extract_ticker_weights,
    extract_ticker_weights_for_ticker,
)
from .settings import SUPPORTED_PROVIDERS

__all__ = [
    "AssetCategorySyncResult",
    "DownloadLinkNotFoundError",
    "ETFHoldingsError",
    "ETFHoldingsReader",
    "FetchError",
    "FundHoldings",
    "HOLDINGS_ASSET_CATEGORY_PREFIX",
    "Holding",
    "HoldingsAssetCategoryPlan",
    "SUPPORTED_PROVIDERS",
    "UnsupportedProviderError",
    "WorkbookParseError",
    "build_holdings_asset_category_plan",
    "build_holdings_asset_category_unique_identifier",
    "derive_component_symbols_from_holdings",
    "extract_many_ticker_weights",
    "extract_ticker_weights",
    "extract_ticker_weights_for_ticker",
    "infer_holdings_component_provider",
    "resolve_existing_assets_by_ticker",
    "sync_holdings_asset_category",
]

try:
    __version__ = version("etfh-extractor")
except PackageNotFoundError:
    __version__ = "0.0.0"
