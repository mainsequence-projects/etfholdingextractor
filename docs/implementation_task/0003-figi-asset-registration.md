# Implementation Task: FIGI Registration of Missing ETF Components

- Status: Implemented (pending live validation)
- Decision basis: [ADR 0004](../adr/0004-figi-only-asset-registration.md)

## 1. Objective

Close the gap found in review: the project resolved component tickers against the ms-markets
asset master but had **no production path to register missing components** — and the example's
stopgap seeded ticker-keyed assets, violating the FIGI identity convention. This task adds
FIGI-only registration using the ms-markets machinery, under ADR 0004's two hard rules:

1. **No FIGI → no registration** (`Asset.unique_identifier` is always the FIGI).
2. **Unique mapping required** — a ticker mapping to more than one FIGI is never registered
   (risk of mixing same-ticker assets); it stays a blocker with its candidates reported.

## 2. What was built

- **`etfhextractor/asset_registration.py`** — `register_equity_assets_from_tickers(*, tickers,
  market_sector="Equity", exch_code="US", api_key=None, snapshot_time=None) ->
  FigiAssetRegistrationResult`:
  1. `msm.services.assets.openfigi.query_figi(tickers, market_sector=, exch_code=)` →
     normalized rows, grouped per requested ticker by **distinct FIGI**;
  2. 0 candidates → `unmapped_tickers`; >1 → `ambiguous_figi_candidates_by_ticker`; exactly 1 →
     register: `Asset.upsert(unique_identifier=figi, asset_type="equity")` (after
     `AssetType.upsert("equity")`) + `OpenFigiDetails.upsert(asset_uid=..., figi, composite,
     share_class, isin, ticker, name, exchange_code, security_type*, security_market_sector,
     security_description, unique_id*, metadata_text, raw_payload)`;
  3. one `AssetSnapshot` run publishes all snapshot frames
     (`build_asset_snapshot_frame_from_openfigi_result`) so the snapshot-layer ticker resolver
     finds the new assets immediately — no resolver changes needed.
  - `FigiAssetRegistrationResult(registered_figi_by_ticker, unmapped_tickers,
    ambiguous_figi_candidates_by_ticker)` with `has_failures()` / `summary()`.
- **Runtime models** — `OpenFigiAssetDetailsTable` added to `_ensure_msm_started` and
  `start_portfolio_engine` model lists.
- **Ambiguity surfacing + disambiguation filters** — `FigiAssetRegistrationResult.format_failures()`
  names every blocked ticker with its FIGI candidates and the fix; `FigiRegistrationError` carries
  it (raised by the publish preflight; printed to stderr by `category-sync`). Every entrypoint
  accepts per-ticker OpenFIGI disambiguation filters so ambiguous mappings can be resolved
  explicitly: `disambiguation_filters=[{"ticker": "USO", "market_sector": "Equity",
  "exch_code": "US"}]` (allowed keys: `ticker`, `market_sector`, `exch_code`, `security_type`,
  `security_type_2`; unknown keys raise). Tickers are batched per effective filter set, one
  `query_figi` call per group.
- **CLI** — `etfh category-sync --register-missing` (plan → register missing → re-plan reusing the
  extracted holdings → sync; registration summary in the JSON payload, failures echoed to stderr)
  and `etfh portfolio-publish --register-missing` (preflight extract/resolve/register before
  publishing; raises `FigiRegistrationError` on unmapped/ambiguous). Both take repeatable
  `--figi-filter '{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}'` arguments
  (validated before any extraction or platform call).
- **Example** — the ticker-keyed `--seed-missing-assets` is **removed**; replaced by
  `--register-missing-assets` calling the FIGI registration.
- **Tests** — `tests/test_asset_registration.py`: unique mapping registers FIGI-keyed; no FIGI →
  unmapped, nothing written; multiple FIGIs → ambiguous, nothing written; duplicate same-FIGI rows
  collapse to unique; mixed batches register only the unique mappings.

## 3. Operational requirements

- `OPEN_FIGI_API_KEY` Main Sequence secret (read by `msm.services.assets.openfigi`; clean
  configuration error otherwise). Rate limiting is handled by the msm batching helpers.
- Registration is opt-in (flags above); the signal's scheduled updates never register implicitly.
- Defaults scope the OpenFIGI query to `market_sector="Equity"`, `exch_code="US"` — narrow or
  widen explicitly per use.

## 4. Pending

- Live validation: run `etfh category-sync --ticker IVV --fund-url <url> --register-missing`
  against the platform with the secret configured; confirm registered assets resolve through the
  snapshot layer and the category/portfolio runs unblock.
