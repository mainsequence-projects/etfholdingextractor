"""FIGI-based registration of ETF component assets in ms-markets.

Identity rules (ADR 0004):

1. **No FIGI → no registration.** An asset row is never created without an
   OpenFIGI mapping; `Asset.unique_identifier` is always the FIGI.
2. **Unique mapping required.** A ticker must map to exactly one FIGI for the
   requested market sector / exchange; multiple candidates mean we could mix
   different assets sharing a ticker, so the ticker stays an unregistered
   blocker and the candidates are reported.

Registration uses the ms-markets machinery directly: `query_figi` (ticker →
normalized OpenFIGI rows), then set-based row calls — `Asset.upsert_many`,
`OpenFigiDetails.upsert_many` — and one `AssetSnapshots.publish` so the
snapshot-layer ticker resolver finds the new assets immediately. Under the
ms-markets remote backend (ADR 0047), which the application selects, every write
runs on the Markets API (write-policy resources `asset-type`, `asset`,
`open-figi-details` and `asset-snapshots`).

Requires the `OPEN_FIGI_API_KEY` Main Sequence secret (or an explicit
`api_key`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .mainsequence_categories import _ensure_msm_started
from .providers.common import normalize_ticker

# OpenFIGI mapping filters that a disambiguation entry may override per ticker.
DISAMBIGUATION_FILTER_KEYS = ("market_sector", "exch_code", "security_type", "security_type_2")

# Per-ticker idValue alias: the symbol OpenFIGI knows the ticker by, when the
# provider's convention differs (e.g. iShares "BRKB" vs OpenFIGI "BRK/B").
DISAMBIGUATION_ALIAS_KEY = "figi_ticker"

DISAMBIGUATION_EXAMPLE = '{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}'
DISAMBIGUATION_ALIAS_EXAMPLE = '{"ticker": "BRKB", "figi_ticker": "BRK/B"}'


@dataclass(frozen=True, slots=True)
class FigiAssetRegistrationResult:
    """Outcome of one FIGI registration pass.

    `registered_figi_by_ticker` holds only the assets actually created this
    pass; `already_registered_figi_by_ticker` holds the tickers whose FIGI was
    found in the asset registry by the batch existence check (no writes).
    """

    registered_figi_by_ticker: dict[str, str] = field(default_factory=dict)
    already_registered_figi_by_ticker: dict[str, str] = field(default_factory=dict)
    snapshots_published_for_figis: list[str] = field(default_factory=list)
    unmapped_tickers: list[str] = field(default_factory=list)
    ambiguous_figi_candidates_by_ticker: dict[str, list[str]] = field(default_factory=dict)

    def has_failures(self) -> bool:
        return bool(self.unmapped_tickers or self.ambiguous_figi_candidates_by_ticker)

    def summary(self) -> dict[str, Any]:
        return {
            "registered_count": len(self.registered_figi_by_ticker),
            "already_registered_count": len(self.already_registered_figi_by_ticker),
            "snapshots_published_count": len(self.snapshots_published_for_figis),
            "registered_figi_by_ticker": self.registered_figi_by_ticker,
            "already_registered_figi_by_ticker": self.already_registered_figi_by_ticker,
            "unmapped_tickers": self.unmapped_tickers,
            "ambiguous_figi_candidates_by_ticker": self.ambiguous_figi_candidates_by_ticker,
        }

    def format_failures(self) -> str | None:
        """Human-readable failure report naming every blocked ticker."""
        if not self.has_failures():
            return None
        parts: list[str] = []
        if self.ambiguous_figi_candidates_by_ticker:
            ambiguous = "; ".join(
                f"{ticker} -> {candidates}"
                for ticker, candidates in self.ambiguous_figi_candidates_by_ticker.items()
            )
            parts.append(f"ambiguous ticker→FIGI mappings: {ambiguous}")
        if self.unmapped_tickers:
            parts.append(f"no FIGI mapping for: {self.unmapped_tickers}")
        return (
            "FIGI registration incomplete — "
            + "; ".join(parts)
            + ". Narrow ambiguous tickers with a disambiguation filter, e.g. "
            + DISAMBIGUATION_EXAMPLE
            + '; map unmapped tickers to their OpenFIGI symbol with "figi_ticker", e.g. '
            + DISAMBIGUATION_ALIAS_EXAMPLE
            + "."
        )


class FigiRegistrationError(RuntimeError):
    """Raised when FIGI registration leaves unmapped or ambiguous tickers."""

    def __init__(self, result: FigiAssetRegistrationResult) -> None:
        super().__init__(result.format_failures() or "FIGI registration failed.")
        self.result = result


def _normalize_disambiguation_filters(
    disambiguation_filters: Sequence[Mapping[str, Any]] | None,
) -> dict[str, dict[str, str]]:
    """Validate per-ticker filter entries into {ticker: {filter: value}}.

    Besides the OpenFIGI query filters, an entry may carry `figi_ticker` — the
    idValue alias OpenFIGI knows the symbol by (e.g. `BRKB` → `BRK/B`).
    """
    overrides_by_ticker: dict[str, dict[str, str]] = {}
    for entry in disambiguation_filters or []:
        if "ticker" not in entry or not str(entry["ticker"]).strip():
            raise ValueError(
                f"Each disambiguation filter needs a 'ticker' key, e.g. {DISAMBIGUATION_EXAMPLE}."
            )
        unknown = set(entry) - {"ticker", DISAMBIGUATION_ALIAS_KEY, *DISAMBIGUATION_FILTER_KEYS}
        if unknown:
            raise ValueError(
                f"Unknown disambiguation filter keys {sorted(unknown)}; allowed: "
                f"ticker, {DISAMBIGUATION_ALIAS_KEY}, {', '.join(DISAMBIGUATION_FILTER_KEYS)}."
            )
        ticker = normalize_ticker(str(entry["ticker"]))
        overrides = {
            key: str(entry[key])
            for key in DISAMBIGUATION_FILTER_KEYS
            if entry.get(key) not in (None, "")
        }
        if entry.get(DISAMBIGUATION_ALIAS_KEY) not in (None, ""):
            overrides[DISAMBIGUATION_ALIAS_KEY] = normalize_ticker(
                str(entry[DISAMBIGUATION_ALIAS_KEY])
            )
        overrides_by_ticker[ticker] = overrides
    return overrides_by_ticker


def register_equity_assets_from_tickers(
    *,
    tickers: list[str],
    market_sector: str = "Equity",
    exch_code: str | None = "US",
    disambiguation_filters: Sequence[Mapping[str, Any]] | None = None,
    api_key: str | None = None,
    snapshot_time: dt.datetime | None = None,
) -> FigiAssetRegistrationResult:
    """Resolve tickers to FIGIs and register only the missing assets.

    Smart-resolution flow (always):

    1. tickers → FIGIs in batched `query_figi` mapping calls
       (`{"idType": "TICKER", "idValue": <ticker>, "marketSecDes": <sector>,
       "exchCode": <code>}`); per ticker exactly one FIGI must come back —
       `unmapped_tickers` / `ambiguous_figi_candidates_by_ticker` otherwise,
       and neither is registered.
    2. **ONE batch lookup** of all mapped FIGIs in the asset registry
       (`Asset.get_many_by_unique_identifier(figis)`) plus one batch read of
       their latest snapshots (`AssetSnapshots.latest(asset_identifiers=figis)`).
    3. Write only the deltas, set-based: one `Asset.upsert_many` of
       `{unique_identifier: figi, asset_type: "equity"}` and one
       `OpenFigiDetails.upsert_many` for the FIGIs not in the registry, and one
       `AssetSnapshots.publish` covering every mapped FIGI that lacks a snapshot
       (repairs interrupted earlier registrations). Already-registered FIGIs
       cost zero writes on re-runs.

    `disambiguation_filters` narrows the OpenFIGI query per ticker so ambiguous
    mappings can be resolved explicitly, e.g.::

        disambiguation_filters=[
            {"ticker": "USO", "market_sector": "Equity", "exch_code": "US"},
        ]

    Allowed filter keys: market_sector, exch_code, security_type,
    security_type_2 (others raise). Tickers without an entry use the
    function-level `market_sector` / `exch_code` defaults.
    """
    requested = sorted({normalize_ticker(ticker) for ticker in tickers if ticker.strip()})
    if not requested:
        return FigiAssetRegistrationResult()

    overrides_by_ticker = _normalize_disambiguation_filters(disambiguation_filters)

    # Build the full query plan (and validate alias collisions) BEFORE touching
    # the platform: batch tickers per effective OpenFIGI filter set — defaults
    # for most, per-ticker disambiguation overrides for the rest. The mapping
    # idValue per ticker is the user-provided `figi_ticker` alias when set
    # (BRKB → BRK/B), otherwise the ticker itself.
    tickers_by_filters: dict[tuple[str | None, ...], list[str]] = {}
    requested_by_query_value: dict[str, str] = {}
    for ticker in requested:
        overrides = dict(overrides_by_ticker.get(ticker, {}))
        query_value = overrides.pop(DISAMBIGUATION_ALIAS_KEY, ticker)
        previous = requested_by_query_value.get(query_value)
        if previous is not None and previous != ticker:
            raise ValueError(
                f"figi_ticker alias collision: {previous!r} and {ticker!r} both map to "
                f"OpenFIGI symbol {query_value!r}."
            )
        requested_by_query_value[query_value] = ticker
        effective = {
            "market_sector": market_sector,
            "exch_code": exch_code,
            "security_type": None,
            "security_type_2": None,
        }
        effective.update(overrides)
        filter_key = tuple(effective[key] for key in DISAMBIGUATION_FILTER_KEYS)
        tickers_by_filters.setdefault(filter_key, []).append(query_value)

    _ensure_msm_started()

    from mainsequence.logconf import logger as _ms_logger
    from msm.api.assets import Asset, AssetSnapshots, AssetType, OpenFigiDetails
    from msm.constants import ASSET_TYPE_EQUITY
    from msm.services.assets.openfigi import query_figi

    log = _ms_logger.bind(sub_application="etfhextractor", component="asset_registration")

    log.info(
        f"FIGI mapping: {len(requested)} tickers in {len(tickers_by_filters)} "
        "OpenFIGI filter group(s)..."
    )
    rows: list[dict[str, Any]] = []
    for filter_key, group_query_values in tickers_by_filters.items():
        group_filters = dict(zip(DISAMBIGUATION_FILTER_KEYS, filter_key))
        rows.extend(
            query_figi(
                group_query_values,
                market_sector=group_filters["market_sector"],
                exch_code=group_filters["exch_code"],
                security_type=group_filters["security_type"],
                security_type_2=group_filters["security_type_2"],
                api_key=api_key,
            )
        )

    rows_by_ticker: dict[str, dict[str, dict[str, Any]]] = {ticker: {} for ticker in requested}
    for row in rows:
        row_ticker = normalize_ticker(str(row.get("ticker") or ""))
        requested_ticker = requested_by_query_value.get(row_ticker)
        figi = row.get("figi")
        if not figi or requested_ticker is None:
            continue
        # Keyed by FIGI: identical FIGIs collapse; distinct FIGIs mean ambiguity.
        rows_by_ticker[requested_ticker].setdefault(str(figi), row)

    figi_by_ticker: dict[str, str] = {}
    normalized_by_figi: dict[str, dict[str, Any]] = {}
    requested_ticker_by_figi: dict[str, str] = {}
    unmapped_tickers: list[str] = []
    ambiguous_by_ticker: dict[str, list[str]] = {}

    for ticker in requested:
        candidates = rows_by_ticker[ticker]
        if not candidates:
            unmapped_tickers.append(ticker)
        elif len(candidates) > 1:
            ambiguous_by_ticker[ticker] = sorted(candidates)
        else:
            figi, normalized = next(iter(candidates.items()))
            figi_by_ticker[ticker] = figi
            normalized_by_figi[figi] = normalized
            requested_ticker_by_figi[figi] = ticker

    log.info(
        f"FIGI mapping done: {len(figi_by_ticker)} unique, "
        f"{len(unmapped_tickers)} unmapped, {len(ambiguous_by_ticker)} ambiguous."
    )

    # Resolve smartly: ONE batch lookup of every mapped FIGI against the asset
    # registry, then write only the deltas — never one-by-one re-upserts of
    # assets that already exist.
    all_figis = sorted(normalized_by_figi)
    existing_uid_by_figi = _existing_asset_uids_by_figi(all_figis)
    figis_with_snapshots = _figis_with_snapshots(all_figis)

    already_registered_figi_by_ticker = {
        ticker: figi
        for ticker, figi in figi_by_ticker.items()
        if figi in existing_uid_by_figi
    }
    registered_figi_by_ticker = {
        ticker: figi
        for ticker, figi in figi_by_ticker.items()
        if figi not in existing_uid_by_figi
    }
    log.info(
        f"Registry batch check: {len(already_registered_figi_by_ticker)} already "
        f"registered, {len(registered_figi_by_ticker)} to create, "
        f"{len(all_figis) - len(figis_with_snapshots)} snapshots to publish."
    )

    if registered_figi_by_ticker:
        AssetType.upsert(asset_type=ASSET_TYPE_EQUITY, display_name="Equity")
        to_create = [
            normalized_by_figi[figi] for _ticker, figi in sorted(registered_figi_by_ticker.items())
        ]
        assets = Asset.upsert_many(
            [
                {
                    "unique_identifier": normalized["unique_identifier"],
                    "asset_type": ASSET_TYPE_EQUITY,
                }
                for normalized in to_create
            ]
        )
        uid_by_identifier = {str(asset.unique_identifier): asset.uid for asset in assets}
        unwritten = sorted(
            str(normalized["unique_identifier"])
            for normalized in to_create
            if str(normalized["unique_identifier"]) not in uid_by_identifier
        )
        if unwritten:
            raise RuntimeError(f"Asset registration returned no row for FIGIs {unwritten}.")
        OpenFigiDetails.upsert_many(
            [
                _openfigi_details_payload(
                    normalized,
                    asset_uid=uid_by_identifier[str(normalized["unique_identifier"])],
                )
                for normalized in to_create
            ]
        )
        log.info(f"Registered {len(to_create)} new assets with their OpenFIGI details.")

    # Snapshots make assets resolvable by ticker; publish them for every mapped
    # FIGI that lacks one (covers assets created here AND assets that exist but
    # were never snapshotted, e.g. an interrupted earlier registration).
    snapshot_target_figis = [figi for figi in all_figis if figi not in figis_with_snapshots]
    if snapshot_target_figis:
        log.info(f"Publishing {len(snapshot_target_figis)} asset snapshots in one batch...")
        resolved_snapshot_time = snapshot_time or dt.datetime.now(dt.UTC).replace(microsecond=0)
        # The snapshot carries the REQUESTED ticker (the provider/extraction
        # convention, e.g. BRKB), not OpenFIGI's symbol (BRK/B) — the snapshot
        # layer resolves extraction tickers, so an aliased symbol must be stored
        # under the form extractions actually produce. OpenFIGI's own symbol
        # stays on OpenFigiDetails.ticker.
        AssetSnapshots.publish(
            [
                _snapshot_row(
                    normalized_by_figi[figi],
                    ticker=requested_ticker_by_figi[figi],
                    time_index=resolved_snapshot_time,
                )
                for figi in snapshot_target_figis
            ]
        )
        log.info(f"Snapshots published: {len(snapshot_target_figis)} assets now resolvable.")

    return FigiAssetRegistrationResult(
        registered_figi_by_ticker=dict(sorted(registered_figi_by_ticker.items())),
        already_registered_figi_by_ticker=dict(sorted(already_registered_figi_by_ticker.items())),
        snapshots_published_for_figis=sorted(snapshot_target_figis),
        unmapped_tickers=sorted(unmapped_tickers),
        ambiguous_figi_candidates_by_ticker=dict(sorted(ambiguous_by_ticker.items())),
    )


def _openfigi_details_payload(normalized: Mapping[str, Any], *, asset_uid: Any) -> dict[str, Any]:
    """`OpenFigiDetails` upsert payload for one normalized OpenFIGI row."""
    return {
        "asset_uid": asset_uid,
        "figi": normalized.get("figi"),
        "composite": normalized.get("composite"),
        "share_class": normalized.get("share_class"),
        "isin": normalized.get("isin"),
        "ticker": normalized.get("ticker"),
        "name": normalized.get("name"),
        "exchange_code": normalized.get("exchange_code"),
        "security_type": normalized.get("security_type"),
        "security_type_2": normalized.get("security_type_2"),
        "security_market_sector": normalized.get("security_market_sector"),
        "security_description": normalized.get("security_description"),
        "unique_id": normalized.get("unique_id"),
        "unique_id_fut_opt": normalized.get("unique_id_fut_opt"),
        "metadata_text": normalized.get("metadata"),
        "raw_payload": normalized.get("raw_payload"),
    }


def _snapshot_row(
    normalized: Mapping[str, Any],
    *,
    ticker: str,
    time_index: dt.datetime,
) -> dict[str, Any]:
    """One `AssetSnapshots.publish` row, as ms-markets builds it from an OpenFIGI result."""
    return {
        "time_index": time_index,
        "asset_identifier": normalized["unique_identifier"],
        "name": normalized.get("name") or "",
        "ticker": ticker,
        "exchange_code": normalized.get("exchange_code") or "",
        "asset_ticker_group_id": normalized.get("share_class") or "",
    }


def _existing_asset_uids_by_figi(figis: list[str]) -> dict[str, Any]:
    """ONE batch row call against the asset registry: which FIGIs already exist."""
    if not figis:
        return {}
    from .mainsequence_categories import _asset_uids_by_identifier

    return _asset_uids_by_identifier(set(figis))


def _figis_with_snapshots(figis: list[str]) -> set[str]:
    """ONE batch read of the latest snapshots: which FIGIs are already resolvable.

    ``AssetSnapshots.latest(asset_identifiers=...)`` leaves out FIGIs with no asset and gives
    assets without a snapshot ``snapshot_time=None``.
    """
    if not figis:
        return set()
    from msm.api.assets import AssetSnapshots

    return {
        str(reference.asset_identifier)
        for reference in AssetSnapshots.latest(asset_identifiers=list(figis))
        if reference.snapshot_time is not None
    }


__all__ = [
    "DISAMBIGUATION_FILTER_KEYS",
    "FigiAssetRegistrationResult",
    "FigiRegistrationError",
    "register_equity_assets_from_tickers",
]
