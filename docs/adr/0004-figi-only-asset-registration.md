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

The registration pattern (implemented in `etfhextractor/asset_registration.py`):

```python
rows = query_figi(missing_tickers, market_sector="Equity", exch_code="US")
# exactly one FIGI per ticker, else blocker
asset = Asset.upsert(unique_identifier=row["unique_identifier"], asset_type="equity")
OpenFigiDetails.upsert(asset_uid=asset.uid, figi=..., ticker=..., isin=..., ...)
# one AssetSnapshot run publishes ticker/name/exchange so the snapshot resolver finds the assets
```

Registration is **opt-in and explicit**: `etfh category-sync --register-missing`,
`etfh portfolio-publish --register-missing`, and the example's `--register-missing-assets`. It is
never performed implicitly by the signal's scheduled updates. It requires the `OPEN_FIGI_API_KEY`
Main Sequence secret.

## Consequences

- The pipeline is self-sufficient on fresh environments: missing components can be registered
  correctly (FIGI-mastered) instead of blocking forever or being seeded wrongly.
- Ambiguity is never auto-resolved, and failures always name the blocked tickers with their FIGI
  candidates. Operators resolve them explicitly with per-ticker disambiguation filters — e.g.
  `{"ticker": "USO", "market_sector": "Equity", "exch_code": "US"}` (CLI `--figi-filter`, function
  `disambiguation_filters=`; allowed keys: `market_sector`, `exch_code`, `security_type`,
  `security_type_2`) — or master the asset upstream; until then those tickers stay blockers.
- ADR 0002's non-goal is narrowed, not removed: this project registers **ETF component equities
  via FIGI only**. Broader asset-master ownership, non-equity registration workflows, and FIGI
  re-mastering remain out of scope.
- The runtime model lists now include `OpenFigiAssetDetailsTable`.
