from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from .models import FundHoldings
from .providers.common import is_probable_security_ticker, normalize_ticker
from .providers.registry import infer_provider_name_from_url
from .reader import ETFHoldingsReader


HOLDINGS_ASSET_CATEGORY_PREFIX = "HOLDINGS__"

# Page size for scanning the ms-markets asset-snapshot MetaTable. We page through
# results explicitly instead of relying on the repository's default `limit`, so a
# large ETF universe (hundreds of components, each with multiple historical
# snapshot rows) is fully scanned. (Implementation task 0001 §10.6.)
_SNAPSHOT_SCAN_PAGE_SIZE = 1000

# Cached ms-markets runtime (set on first use by `_ensure_msm_started`).
_MSM_RUNTIME: Any = None


def _ensure_msm_started() -> Any:
    """Bootstrap the ms-markets runtime once and return it.

    ms-markets row and repository operations require a runtime attached to the
    already-registered markets MetaTables. This is intentionally lazy so importing
    ``etfhextractor`` and running pure extraction never starts the markets engine or
    requires MainSequence to be configured. ``start_engine`` is idempotent for an
    identical model list, so the module-level cache is just an optimization.
    (Implementation task 0001 §3 / A-1.)
    """
    global _MSM_RUNTIME
    if _MSM_RUNTIME is None:
        from msm import start_engine
        from msm.bootstrap import resolve_runtime
        from msm.data_nodes.assets.storage import AssetSnapshotsStorage
        from msm.models import (
            AssetCategoryMembershipTable,
            AssetCategoryTable,
            AssetTable,
            OpenFigiAssetDetailsTable,
        )

        models = [
            AssetTable,
            OpenFigiAssetDetailsTable,
            AssetSnapshotsStorage,
            AssetCategoryTable,
            AssetCategoryMembershipTable,
        ]
        try:
            # A process may only call start_engine with one schema config. When a
            # superset runtime is already attached (e.g. the portfolio-publish path
            # boots the msm_portfolios graph first), reuse it instead.
            _MSM_RUNTIME = resolve_runtime(
                models=models,
                row_model_name="etfhextractor.mainsequence_categories",
            )
        except RuntimeError:
            _MSM_RUNTIME = start_engine(models=models)
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


def _snapshot_time(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


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


def _search_snapshot_rows(
    context: Any,
    *,
    in_filters: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Page through the asset-snapshot MetaTable for the given `in_filters`."""
    from msm.api.base import operation_result_rows
    from msm.data_nodes.assets.storage import AssetSnapshotsStorage
    from msm.repositories.crud import search_model

    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = operation_result_rows(
            search_model(
                context,
                model=AssetSnapshotsStorage,
                in_filters=in_filters,
                limit=_SNAPSHOT_SCAN_PAGE_SIZE,
                offset=offset,
            )
        )
        rows.extend(page)
        if len(page) < _SNAPSHOT_SCAN_PAGE_SIZE:
            break
        offset += _SNAPSHOT_SCAN_PAGE_SIZE
    return rows


def _latest_ticker_by_identifier(
    context: Any,
    identifiers: set[str],
) -> dict[str, str | None]:
    """Map each asset_identifier to the ticker on its most recent snapshot."""
    if not identifiers:
        return {}

    rows = _search_snapshot_rows(
        context,
        in_filters={"asset_identifier": sorted(identifiers)},
    )
    latest: dict[str, tuple[dt.datetime, str | None]] = {}
    for row in rows:
        identifier = _clean_text(row.get("asset_identifier"))
        snapshot_time = _snapshot_time(row.get("time_index"))
        if identifier is None or snapshot_time is None:
            continue
        current = latest.get(identifier)
        if current is None or snapshot_time > current[0]:
            latest[identifier] = (snapshot_time, _clean_text(row.get("ticker")))
    return {identifier: ticker for identifier, (_, ticker) in latest.items()}


def _asset_uids_by_identifier(
    context: Any,
    identifiers: set[str],
) -> dict[str, uuid.UUID]:
    """Resolve asset unique_identifiers to their AssetTable uid."""
    if not identifiers:
        return {}

    from msm.api.base import operation_result_rows
    from msm.models import AssetTable
    from msm.repositories.crud import search_model

    ordered_identifiers = sorted(identifiers)
    rows = operation_result_rows(
        search_model(
            context,
            model=AssetTable,
            in_filters={"unique_identifier": ordered_identifiers},
            limit=max(len(ordered_identifiers), _SNAPSHOT_SCAN_PAGE_SIZE),
        )
    )
    uid_by_identifier: dict[str, uuid.UUID] = {}
    for row in rows:
        identifier = _clean_text(row.get("unique_identifier"))
        raw_uid = row.get("uid")
        if identifier is None or raw_uid is None:
            continue
        uid_by_identifier[identifier] = _as_uuid(raw_uid)
    return uid_by_identifier


def resolve_asset_identifiers_by_ticker(
    *,
    component_symbols: list[str],
) -> tuple[dict[str, str], list[str], list[str]]:
    """Resolve component tickers to ms-markets asset unique identifiers.

    Ticker resolution uses the ms-markets asset-snapshot layer
    (``AssetSnapshotsStorage.ticker``, the successor to the platform's old
    ``current_snapshot.ticker``): query snapshots whose ticker is one of the
    component symbols and keep the asset identifiers whose *latest* snapshot
    ticker still equals the symbol. Classify by count: zero → missing, one →
    existing, many → ambiguous. Returns
    ``(asset_identifiers_by_symbol, missing, ambiguous)``.

    The identifier is ``Asset.unique_identifier`` — the key used by signal
    frames and snapshot rows; `resolve_existing_assets_by_ticker` layers the
    asset-uid lookup on top for category membership writes.
    """
    if not component_symbols:
        return {}, [], []

    runtime = _ensure_msm_started()
    context = runtime.context

    snapshot_rows = _search_snapshot_rows(
        context,
        in_filters={"ticker": list(component_symbols)},
    )

    candidates_by_symbol: dict[str, set[str]] = {symbol: set() for symbol in component_symbols}
    for row in snapshot_rows:
        ticker = _clean_text(row.get("ticker"))
        identifier = _clean_text(row.get("asset_identifier"))
        if ticker is None or identifier is None:
            continue
        normalized = normalize_ticker(ticker)
        if normalized in candidates_by_symbol:
            candidates_by_symbol[normalized].add(identifier)

    all_candidates = {
        identifier for identifiers in candidates_by_symbol.values() for identifier in identifiers
    }
    latest_ticker_by_identifier = _latest_ticker_by_identifier(context, all_candidates)

    asset_identifiers_by_symbol: dict[str, str] = {}
    missing_registered_symbols: list[str] = []
    ambiguous_registered_symbols: list[str] = []

    for symbol in component_symbols:
        matched_identifiers = [
            identifier
            for identifier in sorted(candidates_by_symbol.get(symbol, set()))
            if (latest_ticker := latest_ticker_by_identifier.get(identifier)) is not None
            and normalize_ticker(latest_ticker) == symbol
        ]

        if not matched_identifiers:
            missing_registered_symbols.append(symbol)
        elif len(matched_identifiers) == 1:
            asset_identifiers_by_symbol[symbol] = matched_identifiers[0]
        else:
            ambiguous_registered_symbols.append(symbol)

    return (
        dict(sorted(asset_identifiers_by_symbol.items())),
        sorted(missing_registered_symbols),
        sorted(ambiguous_registered_symbols),
    )


def resolve_existing_assets_by_ticker(
    *,
    component_symbols: list[str],
) -> tuple[dict[str, uuid.UUID], list[str], list[str]]:
    """Resolve component tickers to registered ms-markets asset uids.

    Builds on `resolve_asset_identifiers_by_ticker` (snapshot-layer ticker
    resolution) and maps each resolved identifier to its ``AssetTable.uid`` for
    category membership writes. Returns
    ``(existing_asset_uids_by_symbol, missing, ambiguous)``.
    (Implementation task 0001 §10.1 / B-1.)
    """
    if not component_symbols:
        return {}, [], []

    asset_identifiers_by_symbol, missing_registered_symbols, ambiguous_registered_symbols = (
        resolve_asset_identifiers_by_ticker(component_symbols=component_symbols)
    )

    runtime = _ensure_msm_started()
    uid_by_identifier = _asset_uids_by_identifier(
        runtime.context,
        set(asset_identifiers_by_symbol.values()),
    )

    existing_asset_uids_by_symbol: dict[str, uuid.UUID] = {}
    missing = list(missing_registered_symbols)
    for symbol, identifier in asset_identifiers_by_symbol.items():
        uid = uid_by_identifier.get(identifier)
        if uid is None:
            missing.append(symbol)
        else:
            existing_asset_uids_by_symbol[symbol] = uid

    return (
        dict(sorted(existing_asset_uids_by_symbol.items())),
        sorted(missing),
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
    ``AssetCategory.replace_memberships`` (delete-all-then-insert). That two-step
    is **not** atomic (separate operations, see task 0001 §10.2), but it is
    idempotent — re-running restores the full set — so any failure is allowed to
    propagate and the caller must treat it as a hard error and re-run.
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
