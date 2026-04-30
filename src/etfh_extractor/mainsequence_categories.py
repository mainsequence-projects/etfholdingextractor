from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import FundHoldings
from .providers.registry import infer_provider_name_from_url
from .providers.common import is_probable_security_ticker, normalize_ticker
from .reader import ETFHoldingsReader


HOLDINGS_ASSET_CATEGORY_PREFIX = "HOLDINGS__"


def _load_mainsequence_client() -> Any:
    import mainsequence.client as msc

    return msc


def _coerce_asset_id(asset_or_id: int | object) -> int:
    if isinstance(asset_or_id, int):
        return asset_or_id

    asset_id = getattr(asset_or_id, "id", None)
    if isinstance(asset_id, int):
        return asset_id

    raise ValueError(f"Could not coerce asset id from {asset_or_id!r}")


def _coerce_asset_ticker(asset: Any) -> str | None:
    ticker = getattr(asset, "ticker", None)
    if ticker is None and getattr(asset, "current_snapshot", None) is not None:
        ticker = asset.current_snapshot.ticker
    if not ticker:
        return None
    return normalize_ticker(str(ticker))


def _component_symbols_from_holdings(
    fund_holdings: FundHoldings,
    *,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
) -> list[str]:
    allowed_asset_classes_normalized = (
        {asset_class.strip().lower() for asset_class in allowed_asset_classes}
        if allowed_asset_classes
        else None
    )

    component_symbols: set[str] = set()
    for holding in fund_holdings.holdings:
        ticker = normalize_ticker(holding.ticker)
        if not is_probable_security_ticker(ticker):
            continue
        if (
            allowed_asset_classes_normalized is not None
            and holding.asset_class
            and holding.asset_class.strip().lower() not in allowed_asset_classes_normalized
        ):
            continue
        component_symbols.add(ticker)

    return sorted(component_symbols)


@dataclass(frozen=True, slots=True)
class AssetCategorySyncResult:
    unique_identifier: str
    display_name: str
    asset_ids: list[int]


@dataclass(frozen=True, slots=True)
class HoldingsAssetCategoryPlan:
    etf_ticker: str
    provider: str
    category_unique_identifier: str
    fund_holdings: FundHoldings
    component_symbols: list[str]
    existing_asset_ids_by_symbol: dict[str, int]
    missing_registered_symbols: list[str]
    ambiguous_registered_symbols: list[str]

    def has_blockers(self) -> bool:
        return bool(self.missing_registered_symbols or self.ambiguous_registered_symbols)

    def summary(self) -> dict[str, Any]:
        return {
            "etf_ticker": self.etf_ticker,
            "provider": self.provider,
            "category_unique_identifier": self.category_unique_identifier,
            "fund_name": self.fund_holdings.fund_name,
            "as_of_date": self.fund_holdings.as_of_date,
            "source_url": self.fund_holdings.url,
            "download_url": self.fund_holdings.download_url,
            "component_symbol_count": len(self.component_symbols),
            "component_symbols": self.component_symbols,
            "existing_asset_ids_by_symbol": self.existing_asset_ids_by_symbol,
            "missing_registered_symbols": self.missing_registered_symbols,
            "ambiguous_registered_symbols": self.ambiguous_registered_symbols,
        }


def build_holdings_asset_category_unique_identifier(etf_ticker: str) -> str:
    normalized_ticker = normalize_ticker(etf_ticker)
    if not normalized_ticker:
        raise ValueError("ETF ticker must not be empty.")
    return f"{HOLDINGS_ASSET_CATEGORY_PREFIX}{normalized_ticker}"


def infer_holdings_component_provider(fund_url: str) -> str:
    return infer_provider_name_from_url(fund_url)


def derive_component_symbols_from_holdings(
    fund_holdings: FundHoldings,
    *,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
) -> list[str]:
    return _component_symbols_from_holdings(
        fund_holdings,
        allowed_asset_classes=allowed_asset_classes,
    )


def resolve_existing_assets_by_ticker(
    *,
    component_symbols: list[str],
) -> tuple[dict[str, int], list[str], list[str]]:
    if not component_symbols:
        return {}, [], []

    msc = _load_mainsequence_client()
    matching_assets = msc.Asset.filter(current_snapshot__ticker__in=component_symbols)
    assets_by_ticker: dict[str, list[Any]] = {}
    for asset in matching_assets:
        ticker = _coerce_asset_ticker(asset)
        if ticker is None:
            continue
        assets_by_ticker.setdefault(ticker, []).append(asset)

    existing_asset_ids_by_symbol: dict[str, int] = {}
    ambiguous_registered_symbols: list[str] = []
    missing_registered_symbols: list[str] = []

    for symbol in component_symbols:
        assets = assets_by_ticker.get(symbol, [])
        if not assets:
            missing_registered_symbols.append(symbol)
            continue
        if len(assets) != 1:
            ambiguous_registered_symbols.append(symbol)
            continue
        existing_asset_ids_by_symbol[symbol] = assets[0].id

    return (
        dict(sorted(existing_asset_ids_by_symbol.items())),
        sorted(missing_registered_symbols),
        sorted(ambiguous_registered_symbols),
    )


def build_holdings_asset_category_plan(
    *,
    etf_ticker: str,
    fund_url: str | None = None,
    component_provider: str | None = None,
    timeout: float = 30.0,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
    read_holdings_fn=None,
    resolve_existing_assets_by_ticker_fn=resolve_existing_assets_by_ticker,
) -> HoldingsAssetCategoryPlan:
    normalized_ticker = normalize_ticker(etf_ticker)
    if not normalized_ticker:
        raise ValueError("ETF ticker must not be empty.")

    if component_provider is not None:
        provider = component_provider
    elif fund_url is not None:
        provider = infer_holdings_component_provider(fund_url)
    else:
        raise ValueError(
            "Pass component_provider explicitly or pass fund_url so the provider can be inferred."
        )

    active_read_holdings_fn = read_holdings_fn
    if fund_url is not None:
        if active_read_holdings_fn is None:
            fund_holdings = ETFHoldingsReader(timeout=timeout).read(fund_url)
        else:
            fund_holdings = active_read_holdings_fn(fund_url, provider=provider)
    else:
        if active_read_holdings_fn is None:
            active_read_holdings_fn = ETFHoldingsReader(timeout=timeout).read_ticker
        fund_holdings = active_read_holdings_fn(normalized_ticker, provider=provider)

    component_symbols = derive_component_symbols_from_holdings(
        fund_holdings,
        allowed_asset_classes=allowed_asset_classes,
    )
    if not component_symbols:
        raise RuntimeError(
            f"No component symbols were extracted for {normalized_ticker} with provider {provider!r}."
        )

    existing_asset_ids_by_symbol, missing_registered_symbols, ambiguous_registered_symbols = (
        resolve_existing_assets_by_ticker_fn(component_symbols=component_symbols)
    )

    return HoldingsAssetCategoryPlan(
        etf_ticker=normalized_ticker,
        provider=provider,
        category_unique_identifier=build_holdings_asset_category_unique_identifier(
            normalized_ticker
        ),
        fund_holdings=fund_holdings,
        component_symbols=component_symbols,
        existing_asset_ids_by_symbol=existing_asset_ids_by_symbol,
        missing_registered_symbols=missing_registered_symbols,
        ambiguous_registered_symbols=ambiguous_registered_symbols,
    )


def sync_holdings_asset_category(
    *,
    etf_ticker: str,
    asset_ids: list[int],
) -> AssetCategorySyncResult:
    msc = _load_mainsequence_client()

    unique_identifier = build_holdings_asset_category_unique_identifier(etf_ticker)
    ordered_asset_ids = list(dict.fromkeys(_coerce_asset_id(asset_id) for asset_id in asset_ids))
    description = f"Published holdings assets for ETF {normalize_ticker(etf_ticker)}."

    category = msc.AssetCategory.get_or_create(
        display_name=unique_identifier,
        unique_identifier=unique_identifier,
        description=description,
    )

    current_asset_ids = [_coerce_asset_id(asset_or_id) for asset_or_id in category.assets]
    if current_asset_ids:
        category = category.remove_assets(current_asset_ids)
    if ordered_asset_ids:
        category.append_assets(asset_ids=ordered_asset_ids)

    category = msc.AssetCategory.get(unique_identifier=unique_identifier)
    return AssetCategorySyncResult(
        unique_identifier=category.unique_identifier,
        display_name=category.display_name,
        asset_ids=[_coerce_asset_id(asset_or_id) for asset_or_id in category.assets],
    )
