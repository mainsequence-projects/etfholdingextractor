from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from .models import FundHoldings
from .providers.common import is_probable_security_ticker, normalize_ticker
from .providers.registry import infer_provider_name_from_url
from .reader import ETFHoldingsReader

HOLDINGS_ASSET_CATEGORY_PREFIX = "HOLDINGS__"

# Cached ms-markets runtime (set on first use by `_ensure_msm_started`).
_MSM_RUNTIME: Any = None

_ROW_MODEL_NAME = "etfhextractor.mainsequence_categories"


def _category_runtime_models() -> list[Any]:
    """Markets tables the category and registration paths use on the runtime backend."""
    from msm.models import (
        AssetCategoryMembershipTable,
        AssetCategoryTable,
        AssetTable,
        OpenFigiAssetDetailsTable,
    )
    from msm.time_index.assets.storage import AssetSnapshotsStorage

    return [
        AssetTable,
        OpenFigiAssetDetailsTable,
        AssetSnapshotsStorage,
        AssetCategoryTable,
        AssetCategoryMembershipTable,
    ]


def _ensure_msm_started() -> Any:
    """Attach the ms-markets runtime for registry row calls once; ``None`` under the API.

    The application chooses the ms-markets row backend (ADR 0047; see
    ``etfhextractor.markets_runtime``). Under the remote backend every ``msm.api`` row call
    used here runs on the Markets API, so nothing is attached and this returns ``None``.
    Under the runtime backend (the default) it attaches the asset, OpenFIGI, snapshot and
    category tables, reusing a superset runtime when one is already attached (a process may
    only call ``start_engine`` with one schema config; the portfolio-publish path boots the
    msm_portfolios graph first). It is lazy so importing ``etfhextractor`` and running pure
    extraction never starts the markets engine or requires MainSequence to be configured.
    (Implementation task 0001 §3 / A-1.)
    """
    from .markets_runtime import attach_markets_runtime, markets_api_selected

    global _MSM_RUNTIME
    if markets_api_selected():
        return None
    if _MSM_RUNTIME is None:
        _MSM_RUNTIME = attach_markets_runtime(
            _category_runtime_models(), row_model_name=_ROW_MODEL_NAME
        )
    return _MSM_RUNTIME


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _component_weights_from_holdings(
    fund_holdings: FundHoldings,
    *,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
) -> dict[str, float]:
    allowed_asset_classes_normalized = (
        {asset_class.strip().lower() for asset_class in allowed_asset_classes}
        if allowed_asset_classes
        else None
    )

    component_weights: dict[str, float] = {}
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
        component_weights[ticker] = component_weights.get(ticker, 0.0) + holding.weight

    return dict(sorted(component_weights.items()))


def _component_symbols_from_holdings(
    fund_holdings: FundHoldings,
    *,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
) -> list[str]:
    return sorted(
        _component_weights_from_holdings(
            fund_holdings,
            allowed_asset_classes=allowed_asset_classes,
        )
    )


@dataclass(frozen=True, slots=True)
class AssetCategorySyncResult:
    unique_identifier: str
    display_name: str
    asset_uids: list[uuid.UUID]


@dataclass(frozen=True, slots=True)
class HoldingsAssetCategoryPlan:
    etf_ticker: str
    provider: str
    category_unique_identifier: str
    fund_holdings: FundHoldings
    component_symbols: list[str]
    existing_asset_uids_by_symbol: dict[str, uuid.UUID]
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
            "existing_asset_uids_by_symbol": self.existing_asset_uids_by_symbol,
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


def derive_component_weights_from_holdings(
    fund_holdings: FundHoldings,
    *,
    allowed_asset_classes: tuple[str, ...] | None = ("Equity",),
) -> dict[str, float]:
    """Accumulated provider weights per component symbol, using the same filter
    as `derive_component_symbols_from_holdings` (shared by category planning and
    the ETF-tracking portfolio signal)."""
    return _component_weights_from_holdings(
        fund_holdings,
        allowed_asset_classes=allowed_asset_classes,
    )


def _latest_snapshots_by_symbol(
    component_symbols: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Resolve component tickers to the assets whose latest snapshot still carries them.

    One ``AssetSnapshots.latest(tickers=...)`` row call (on the Markets API under the remote
    backend): it returns every asset that ever had one of the tickers, each with its latest
    snapshot; an asset matches a symbol only when that latest ticker normalizes to it. Classify
    by count: zero → missing, one → existing, many → ambiguous. Returns
    ``(reference_by_symbol, missing, ambiguous)`` with ``AssetSnapshotReference`` values.
    """
    from msm.api.assets import AssetSnapshots

    _ensure_msm_started()
    references = AssetSnapshots.latest(tickers=list(component_symbols))

    matches_by_symbol: dict[str, dict[str, Any]] = {symbol: {} for symbol in component_symbols}
    for reference in references:
        ticker = _clean_text(reference.ticker)
        identifier = _clean_text(reference.asset_identifier)
        if ticker is None or identifier is None:
            continue
        symbol = normalize_ticker(ticker)
        if symbol in matches_by_symbol:
            matches_by_symbol[symbol][identifier] = reference

    reference_by_symbol: dict[str, Any] = {}
    missing_registered_symbols: list[str] = []
    ambiguous_registered_symbols: list[str] = []
    for symbol in component_symbols:
        matched = matches_by_symbol.get(symbol, {})
        if not matched:
            missing_registered_symbols.append(symbol)
        elif len(matched) == 1:
            reference_by_symbol[symbol] = next(iter(matched.values()))
        else:
            ambiguous_registered_symbols.append(symbol)
    return (
        reference_by_symbol,
        sorted(missing_registered_symbols),
        sorted(ambiguous_registered_symbols),
    )


def _asset_uids_by_identifier(identifiers: set[str]) -> dict[str, uuid.UUID]:
    """Resolve asset unique_identifiers to their Asset uid in one batch row call.

    ``Asset.get_many_by_unique_identifier`` runs on the Markets API under the remote backend
    and on the attached runtime otherwise.
    """
    if not identifiers:
        return {}

    from msm.api.assets import Asset

    rows = Asset.get_many_by_unique_identifier(sorted(identifiers))
    uid_by_identifier: dict[str, uuid.UUID] = {}
    for identifier, row in rows.items():
        cleaned = _clean_text(identifier)
        if cleaned is None or row.uid is None:
            continue
        uid_by_identifier[cleaned] = _as_uuid(row.uid)
    return uid_by_identifier


def resolve_asset_identifiers_by_ticker(
    *,
    component_symbols: list[str],
) -> tuple[dict[str, str], list[str], list[str]]:
    """Resolve component tickers to ms-markets asset unique identifiers.

    Ticker resolution uses the ms-markets asset-snapshot layer
    (``AssetSnapshotsStorage.ticker``, the successor to the platform's old
    ``current_snapshot.ticker``) through one ``AssetSnapshots.latest(tickers=...)``
    row call: the assets that had one of the component symbols, kept when their
    *latest* snapshot ticker still equals the symbol. Classify by count: zero →
    missing, one → existing, many → ambiguous. Returns
    ``(asset_identifiers_by_symbol, missing, ambiguous)``.

    The identifier is ``Asset.unique_identifier`` — the key used by signal
    frames and snapshot rows; `resolve_existing_assets_by_ticker` returns the
    asset uids of the same resolution for category membership writes.
    """
    if not component_symbols:
        return {}, [], []

    reference_by_symbol, missing, ambiguous = _latest_snapshots_by_symbol(component_symbols)
    asset_identifiers_by_symbol = {
        symbol: str(reference.asset_identifier) for symbol, reference in reference_by_symbol.items()
    }
    return dict(sorted(asset_identifiers_by_symbol.items())), missing, ambiguous


def resolve_existing_assets_by_ticker(
    *,
    component_symbols: list[str],
) -> tuple[dict[str, uuid.UUID], list[str], list[str]]:
    """Resolve component tickers to registered ms-markets asset uids.

    The same snapshot-layer resolution as `resolve_asset_identifiers_by_ticker`,
    returning each resolved asset's ``uid`` (carried by ``AssetSnapshots.latest``, so
    no second lookup) for category membership writes. Returns
    ``(existing_asset_uids_by_symbol, missing, ambiguous)``.
    (Implementation task 0001 §10.1 / B-1.)
    """
    if not component_symbols:
        return {}, [], []

    reference_by_symbol, missing, ambiguous = _latest_snapshots_by_symbol(component_symbols)
    existing_asset_uids_by_symbol = {
        symbol: _as_uuid(reference.asset_uid) for symbol, reference in reference_by_symbol.items()
    }
    return dict(sorted(existing_asset_uids_by_symbol.items())), missing, ambiguous


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

    existing_asset_uids_by_symbol, missing_registered_symbols, ambiguous_registered_symbols = (
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
        existing_asset_uids_by_symbol=existing_asset_uids_by_symbol,
        missing_registered_symbols=missing_registered_symbols,
        ambiguous_registered_symbols=ambiguous_registered_symbols,
    )


def sync_holdings_asset_category(
    *,
    etf_ticker: str,
    asset_uids: list[uuid.UUID],
) -> AssetCategorySyncResult:
    """Create/refresh the ``HOLDINGS__<ETF>`` category membership in ms-markets.

    Uses the ms-markets typed-row API: ``AssetCategory.upsert`` then
    ``AssetCategory.replace_memberships`` (delete-all-then-insert), on the Markets API under
    the remote backend. That two-step is **not** atomic (separate operations, see task
    0001 §10.2), but it is idempotent — re-running restores the full set — so any failure
    is allowed to propagate and the caller must treat it as a hard error and re-run.
    """
    from msm.api.assets import AssetCategory

    _ensure_msm_started()

    unique_identifier = build_holdings_asset_category_unique_identifier(etf_ticker)
    ordered_asset_uids = list(dict.fromkeys(_as_uuid(asset_uid) for asset_uid in asset_uids))
    description = f"Published holdings assets for ETF {normalize_ticker(etf_ticker)}."

    category = AssetCategory.upsert(
        unique_identifier=unique_identifier,
        display_name=unique_identifier,
        description=description,
    )
    memberships = AssetCategory.replace_memberships(
        category_uid=category.uid,
        asset_uids=ordered_asset_uids,
    )

    return AssetCategorySyncResult(
        unique_identifier=category.unique_identifier,
        display_name=category.display_name,
        asset_uids=[_as_uuid(membership.asset_uid) for membership in memberships],
    )
