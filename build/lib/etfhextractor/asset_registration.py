"""FIGI-based registration of ETF component assets in ms-markets.

Identity rules (ADR 0004):

1. **No FIGI → no registration.** An asset row is never created without an
   OpenFIGI mapping; `Asset.unique_identifier` is always the FIGI.
2. **Unique mapping required.** A ticker must map to exactly one FIGI for the
   requested market sector / exchange; multiple candidates mean we could mix
   different assets sharing a ticker, so the ticker stays an unregistered
   blocker and the candidates are reported.

Registration uses the ms-markets machinery directly: `query_figi` (ticker →
normalized OpenFIGI rows), `Asset.upsert(unique_identifier=figi)`,
`OpenFigiDetails.upsert(asset_uid=...)` and one `AssetSnapshot` publication so
the snapshot-layer ticker resolver finds the new assets immediately.

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

DISAMBIGUATION_EXAMPLE = '{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}'


@dataclass(frozen=True, slots=True)
class FigiAssetRegistrationResult:
    """Outcome of one FIGI registration pass."""

    registered_figi_by_ticker: dict[str, str] = field(default_factory=dict)
    unmapped_tickers: list[str] = field(default_factory=list)
    ambiguous_figi_candidates_by_ticker: dict[str, list[str]] = field(default_factory=dict)

    def has_failures(self) -> bool:
        return bool(self.unmapped_tickers or self.ambiguous_figi_candidates_by_ticker)

    def summary(self) -> dict[str, Any]:
        return {
            "registered_count": len(self.registered_figi_by_ticker),
            "registered_figi_by_ticker": self.registered_figi_by_ticker,
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
    """Validate per-ticker filter entries into {ticker: {filter: value}}."""
    overrides_by_ticker: dict[str, dict[str, str]] = {}
    for entry in disambiguation_filters or []:
        if "ticker" not in entry or not str(entry["ticker"]).strip():
            raise ValueError(
                f"Each disambiguation filter needs a 'ticker' key, e.g. {DISAMBIGUATION_EXAMPLE}."
            )
        unknown = set(entry) - {"ticker", *DISAMBIGUATION_FILTER_KEYS}
        if unknown:
            raise ValueError(
                f"Unknown disambiguation filter keys {sorted(unknown)}; allowed: "
                f"ticker, {', '.join(DISAMBIGUATION_FILTER_KEYS)}."
            )
        ticker = normalize_ticker(str(entry["ticker"]))
        overrides_by_ticker[ticker] = {
            key: str(entry[key])
            for key in DISAMBIGUATION_FILTER_KEYS
            if entry.get(key) not in (None, "")
        }
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
    """Register equity assets for `tickers` through OpenFIGI, FIGI-keyed.

    Per ticker: exactly one FIGI mapping → `Asset.upsert(unique_identifier=figi,
    asset_type="equity")` + `OpenFigiDetails.upsert(asset_uid=...)` + an
    `AssetSnapshot` row (ticker/name/exchange) published in one DataNode run.
    Tickers with no mapping are returned in `unmapped_tickers`; tickers with
    more than one distinct FIGI candidate are returned in
    `ambiguous_figi_candidates_by_ticker`. Neither is registered.

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

    _ensure_msm_started()

    import pandas as pd

    from msm.api.assets import Asset, AssetType, OpenFigiDetails
    from msm.constants import ASSET_TYPE_EQUITY
    from msm.data_nodes.assets import AssetSnapshot
    from msm.services.assets.openfigi import (
        build_asset_snapshot_frame_from_openfigi_result,
        query_figi,
    )

    # Batch tickers per effective OpenFIGI filter set: defaults for most, the
    # per-ticker disambiguation overrides for the rest.
    tickers_by_filters: dict[tuple[str | None, ...], list[str]] = {}
    for ticker in requested:
        effective = {
            "market_sector": market_sector,
            "exch_code": exch_code,
            "security_type": None,
            "security_type_2": None,
        }
        effective.update(overrides_by_ticker.get(ticker, {}))
        filter_key = tuple(effective[key] for key in DISAMBIGUATION_FILTER_KEYS)
        tickers_by_filters.setdefault(filter_key, []).append(ticker)

    rows: list[dict[str, Any]] = []
    for filter_key, group_tickers in tickers_by_filters.items():
        group_filters = dict(zip(DISAMBIGUATION_FILTER_KEYS, filter_key))
        rows.extend(
            query_figi(
                group_tickers,
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
        figi = row.get("figi")
        if not figi or row_ticker not in rows_by_ticker:
            continue
        # Keyed by FIGI: identical FIGIs collapse; distinct FIGIs mean ambiguity.
        rows_by_ticker[row_ticker].setdefault(str(figi), row)

    registered_figi_by_ticker: dict[str, str] = {}
    unmapped_tickers: list[str] = []
    ambiguous_by_ticker: dict[str, list[str]] = {}
    to_register: list[tuple[str, dict[str, Any]]] = []

    for ticker in requested:
        candidates = rows_by_ticker[ticker]
        if not candidates:
            unmapped_tickers.append(ticker)
        elif len(candidates) > 1:
            ambiguous_by_ticker[ticker] = sorted(candidates)
        else:
            figi, normalized = next(iter(candidates.items()))
            to_register.append((ticker, normalized))
            registered_figi_by_ticker[ticker] = figi

    if to_register:
        resolved_snapshot_time = snapshot_time or dt.datetime.now(dt.UTC).replace(microsecond=0)
        AssetType.upsert(asset_type=ASSET_TYPE_EQUITY, display_name="Equity")

        snapshot_frames = []
        for _ticker, normalized in to_register:
            asset = Asset.upsert(
                unique_identifier=normalized["unique_identifier"],
                asset_type=ASSET_TYPE_EQUITY,
            )
            OpenFigiDetails.upsert(
                asset_uid=asset.uid,
                figi=normalized.get("figi"),
                composite=normalized.get("composite"),
                share_class=normalized.get("share_class"),
                isin=normalized.get("isin"),
                ticker=normalized.get("ticker"),
                name=normalized.get("name"),
                exchange_code=normalized.get("exchange_code"),
                security_type=normalized.get("security_type"),
                security_type_2=normalized.get("security_type_2"),
                security_market_sector=normalized.get("security_market_sector"),
                security_description=normalized.get("security_description"),
                unique_id=normalized.get("unique_id"),
                unique_id_fut_opt=normalized.get("unique_id_fut_opt"),
                metadata_text=normalized.get("metadata"),
                raw_payload=normalized.get("raw_payload"),
            )
            snapshot_frames.append(
                build_asset_snapshot_frame_from_openfigi_result(
                    normalized,
                    time_index=resolved_snapshot_time,
                )
            )

        snapshot_node = AssetSnapshot().set_frame(pd.concat(snapshot_frames))
        error_on_last_update, _frame = snapshot_node.run(debug_mode=True, force_update=True)
        if error_on_last_update:
            raise RuntimeError(
                "AssetSnapshot update failed while publishing FIGI-registered assets."
            )

    return FigiAssetRegistrationResult(
        registered_figi_by_ticker=dict(sorted(registered_figi_by_ticker.items())),
        unmapped_tickers=sorted(unmapped_tickers),
        ambiguous_figi_candidates_by_ticker=dict(sorted(ambiguous_by_ticker.items())),
    )


__all__ = [
    "DISAMBIGUATION_FILTER_KEYS",
    "FigiAssetRegistrationResult",
    "FigiRegistrationError",
    "register_equity_assets_from_tickers",
]
