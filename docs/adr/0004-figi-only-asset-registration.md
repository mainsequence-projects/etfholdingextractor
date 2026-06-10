# ADR 0004: FIGI-Only Registration of ETF Component Assets

- Status: Accepted
- Date: 2026-06-10
- Partially supersedes the "no asset registration" non-goal of ADR 0002

## Context

The category-sync and tracking-portfolio workflows resolve component tickers against the
ms-markets asset master (snapshot layer) and treat unresolved tickers as blockers. ADR 0002
declared asset registration a non-goal, so the project had **no production path to register
missing components** — on a fresh environment both capabilities block forever. The only stopgap
(the example's demo seeding) registered assets keyed by **ticker**, which violates the ms-markets
identity convention (`Asset.unique_identifier` is the FIGI; the human ticker lives on
`OpenFigiAssetDetailsTable`) and risked polluting the master.

ms-markets ships the registration machinery in `msm.services.assets.openfigi`: `query_figi`
(ticker → normalized OpenFIGI rows), `build_asset_snapshot_frame_from_openfigi_result`, plus the
typed `Asset` / `OpenFigiDetails` row APIs and the `AssetSnapshot` DataNode.

## Decision

ETF component assets may be registered by this project, under two hard identity rules:

1. **No FIGI → no registration.** An asset row is never created without an OpenFIGI mapping.
   `Asset.unique_identifier` is always the FIGI. Ticker-keyed asset creation is forbidden; the
   example's ticker-keyed seeding is removed.
2. **Unique mapping required.** A ticker must map to **exactly one** FIGI for the requested
   market sector / exchange scope. Multiple distinct FIGI candidates mean we could mix different
   assets that share a ticker, so the ticker is **not** registered; it is reported as ambiguous
   with its candidates and remains a blocker. Tickers OpenFIGI cannot map remain blockers too.

3. **Resolve smartly — always.** Never re-upsert assets one-by-one on every run. After the
   ticker→FIGI mapping, **one batch search** of all mapped FIGIs against the asset registry
   (`AssetTable.unique_identifier IN [figis]`) plus one batch search of the snapshot table decide
   the deltas; only FIGIs absent from the registry are created, and snapshots are published only
   for FIGIs that lack one (which also repairs interrupted earlier registrations).
   A fully-registered universe re-runs with **zero writes**.

The registration pattern (implemented in `etfhextractor/asset_registration.py`):

```python
# 1. ticker → FIGI (batched mapping: {"idType": "TICKER", "idValue": t,
#    "marketSecDes": "Equity", "exchCode": "US"}); exactly one FIGI per ticker, else blocker
rows = query_figi(missing_tickers, market_sector="Equity", exch_code="US")
# 2. ONE batch existence check against the registry + ONE against snapshots
existing = search(AssetTable, unique_identifier IN all_figis)
snapshotted = search(AssetSnapshotsTS, asset_identifier IN all_figis)
# 3. write only the deltas
asset = Asset.upsert(unique_identifier=figi, asset_type="equity")      # missing FIGIs only
OpenFigiDetails.upsert(asset_uid=asset.uid, figi=..., ticker=..., ...)  # missing FIGIs only
# one AssetSnapshot run for every mapped FIGI lacking a snapshot
```

**What gets registered (worked example — IVV holds ticker `MSFT`):** the mapping query
`{"idType": "TICKER", "idValue": "MSFT", "marketSecDes": "Equity", "exchCode": "US"}` returns
exactly one row — the **US composite-level FIGI**. Registered identity:
`Asset.unique_identifier = "BBG000BPH459"` (composite FIGI); `OpenFigiDetails` carries
`figi=BBG000BPH459`, `composite=BBG000BPH459`, `share_class=BBG001S5TD05`, `ticker=MSFT`,
`name=MICROSOFT CORP`, `exchange_code=US`, `security_type=Common Stock`; the `AssetSnapshot` row
(`asset_identifier=BBG000BPH459`, `ticker=MSFT`) is what makes the ticker resolvable by the
snapshot layer. Composite-level identity is precisely why `exchCode="US"` is the default: without
it, OpenFIGI returns one venue-level FIGI per exchange listing and every ticker would be
ambiguous.

Registration is **opt-in and explicit**: `etfh category-sync --register-missing`,
`etfh portfolio-publish --register-missing`, and the example's `--register-missing-assets`. It is
never performed implicitly by the signal's scheduled updates. It requires the `OPEN_FIGI_API_KEY`
Main Sequence secret.

## Consequences

- The pipeline is self-sufficient on fresh environments: missing components can be registered
  correctly (FIGI-mastered) instead of blocking forever or being seeded wrongly.
- Ambiguity is never auto-resolved, and failures always name the blocked tickers with their FIGI
  candidates. Operators resolve them explicitly with per-ticker disambiguation filters
  (CLI `--figi-filter`, function `disambiguation_filters=`):
  - **narrowing** the query: `{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}`
    (keys: `market_sector`, `exch_code`, `security_type`, `security_type_2`);
  - **aliasing** a provider ticker to the symbol OpenFIGI knows it by (`figi_ticker`), for
    share-class conventions: `{"ticker": "BRKB", "figi_ticker": "BRK/B"}` — the mapping query
    uses the alias as `idValue`, the result is keyed back to the requested ticker, and the
    published `AssetSnapshot` carries the **requested** (extraction-side) ticker so the snapshot
    resolver matches what providers actually produce; OpenFIGI's own symbol stays on
    `OpenFigiDetails.ticker`. Known IVV cases: `BRKB → BRK/B`, `BFB → BF/B`.
  Until disambiguated, those tickers stay blockers.
- ADR 0002's non-goal is narrowed, not removed: this project registers **ETF component equities
  via FIGI only**. Broader asset-master ownership, non-equity registration workflows, and FIGI
  re-mastering remain out of scope.
- The runtime model lists now include `OpenFigiAssetDetailsTable`.
