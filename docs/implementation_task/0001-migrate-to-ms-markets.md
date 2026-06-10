# Implementation Task: Migrate `etfh_extractor` Category Sync from `mainsequence.client` to `ms-markets` (`msm`) Typed Rows

> **Status: Implemented (2026-06-09).** The refactor below was applied, and as part of the same
> change the package was renamed from `etfh_extractor` (src layout) to a top-level **`etfhextractor/`**
> package (`import etfhextractor`, distribution `etfhextractor` 0.2.0). Where this document says
> `src/etfh_extractor/<file>`, the file now lives at `etfhextractor/<file>`. The ticker→asset resolver
> uses the ms-markets asset-snapshot layer (§10.1); weights/provenance are deferred to
> [0002](0002-ms-markets-portfolio-weights.md) per [ADR 0003](../adr/0003-holdings-weights-live-in-ms-markets-portfolios.md).
> The 26-test suite (`python -m unittest discover -s tests`) passes, including new msm-boundary tests.

## 1. Objective

Refactor `etfh_extractor` so that its only MainSequence-coupled module, `src/etfh_extractor/mainsequence_categories.py`, stops importing `mainsequence.client` directly and instead routes all asset resolution and `HOLDINGS__<ETF>` asset-category mutation through the installed `ms-markets` (`msm`) typed-row API (declared as `ms-markets>=0.0.49`, verified installed at `0.0.49`, currently declared-but-unused). The extraction surface (`reader.py`, `providers/*`, `models.py`) is untouched: `FundHoldings` remains the canonical extraction model and weights stay out of MainSequence. The two-step `msm` category contract (`AssetCategory.upsert(...)` then `AssetCategory.replace_memberships(...)`) replaces the current `get_or_create` + `remove_assets` + `append_assets` + re-`get` sequence, and asset ids change from `int` to UUID/`str`. The dependency-injection seams (`read_holdings_fn`, `resolve_existing_assets_by_ticker_fn`) are preserved so tests run without a live platform runtime.

> NOTE: One central design decision (the ticker→asset identity contract, see §10) is unresolved and **must be confirmed with the platform owner before the breaking work item B-1 is implemented.** Everything before it can land non-breaking.
>
> **Update (revision after the 10.1 review):** the installed SDK (`mainsequence==4.3.16`) no longer exposes `mainsequence.client.Asset` / `AssetCategory`, so the current category-sync path is **already broken** and this refactor is **mandatory, not cosmetic**. The ticker→asset resolver is now **decided**: the `msm` asset-**snapshot** layer (`AssetSnapshotsStorage.ticker`). See the §2 critical finding and the §10.1 decision record.

## 2. Background / current state

All MainSequence coupling lives in `src/etfh_extractor/mainsequence_categories.py`. The rest of the package never imports MainSequence; `cli/__init__.py`, `__init__.py`, and `pyproject.toml` only reference it transitively. The module lazily imports the SDK so that importing `etfh_extractor` and running pure extraction never requires MainSequence to be configured (constraint preserved by ADR 0002 rule 4).

Exact current call sites (verified against the file):

- `_load_mainsequence_client()` — `import mainsequence.client as msc` (line 16), the **only** direct SDK import.
- `resolve_existing_assets_by_ticker(*, component_symbols)` (lines 128–162):
  - `msc.Asset.filter(current_snapshot__ticker__in=component_symbols)` (line 136) — Django-style batch lookup.
  - `_coerce_asset_ticker(asset)` reads `asset.ticker` then falls back to `asset.current_snapshot.ticker` (lines 32–38).
  - `assets[0].id` (line 156) — `int` id.
  - Returns `(dict[str, int], list[str], list[str])` → existing-by-symbol, missing, ambiguous (the plan "blockers").
- `sync_holdings_asset_category(*, etf_ticker, asset_ids)` (lines 226–254):
  - `msc.AssetCategory.get_or_create(display_name=, unique_identifier=, description=)` (lines 237–241).
  - reads `category.assets` (lines 243, 253).
  - `category.remove_assets(current_asset_ids)` (line 245) then `category.append_assets(asset_ids=ordered_asset_ids)` (line 247) — full-replace.
  - `msc.AssetCategory.get(unique_identifier=...)` (line 249) — re-fetch to build the result.
  - `_coerce_asset_id(...)` accepts an `int` or an object exposing `.id` (lines 21–29).

Identifier convention (keep): `unique_identifier == display_name == f"HOLDINGS__{NORMALIZED_ETF_TICKER}"` (`HOLDINGS_ASSET_CATEGORY_PREFIX = "HOLDINGS__"`); `description = f"Published holdings assets for ETF {ticker}."`. Public result/plan types: `AssetCategorySyncResult(unique_identifier, display_name, asset_ids: list[int])` and `HoldingsAssetCategoryPlan(..., existing_asset_ids_by_symbol: dict[str, int], ...)`.

The CLI `category-sync` subcommand (`src/etfh_extractor/cli/__init__.py`) drives `build_holdings_asset_category_plan` then, only if `not plan.has_blockers()`, calls `sync_holdings_asset_category`, and serializes `{plan, synced, sync_result}` to JSON. There is **no** `start_engine` call anywhere, and no test exercises the `msc` call sites at all (`tests/test_reader.py` patches `etfh_extractor.cli.build_holdings_asset_category_plan` / `sync_holdings_asset_category` with `Mock`s).

> ⚠ **Critical finding (verified against the installed environment, this revision).** The installed SDK is `mainsequence==4.3.16`, and `mainsequence.client` exposes **no `Asset` and no `AssetCategory`** symbol: there is no `class Asset` / `class AssetCategory` anywhere in the `mainsequence` package, and `client/__init__.py` only star-imports `command_center`, `metatables`, `models_foundry`, `models_helpers`, `models_user`, `utils`. Consequently **both** current call paths — `resolve_existing_assets_by_ticker` (`msc.Asset.filter(...)`) and `sync_holdings_asset_category` (`msc.AssetCategory.get_or_create(...)`) — raise `AttributeError` on first use *today*. This went unnoticed only because no test exercises those call sites. The asset/category domain moved out of the core SDK into the `ms-markets` library across the recent `upgraded sdk` commit. **Implication:** this migration is required to make `category-sync` work at all; it is not optional modernization. It also means there is no "keep it on the old API" fallback for §10.1 option (c).

## 3. Target architecture

Move to the `msm` typed-row API (frozen Pydantic `MarketsMetaTableRow` subclasses) backed by registered SQLAlchemy MetaTables. `msm` holds **no** credentials — it executes through the ambient `mainsequence.client` MetaTable session configured by the platform SDK — so auth is unchanged; only a one-time, per-process bootstrap is newly required.

Verified import paths (from symbol verification, all `exists=true`):

```python
from msm import start_engine                                   # bootstrap (returns MarketsRuntime)
from msm.models import (                                        # backend tables for start_engine(models=[...])
    AssetTable, AssetCategoryTable, AssetCategoryMembershipTable,
)
from msm.data_nodes.assets.storage import AssetSnapshotsStorage # ticker→asset resolver table (§10.1)
from msm.repositories.crud import search_model                  # snapshot query by ticker
from msm.repositories.assets import get_asset_by_unique_identifier
from msm.api.base import operation_result_rows                  # normalize operation result -> rows
from msm.api.assets import AssetCategory, AssetCategoryMembership  # typed category write API
```

Canonical flow this refactor adopts:

1. **Bootstrap once.** Call `msm.start_engine(models=[AssetTable, AssetSnapshotsStorage, AssetCategoryTable, AssetCategoryMembershipTable])` exactly once per process before any row op, and keep the returned `MarketsRuntime` — its `.context` (a `MarketsRepositoryContext`) is what the snapshot queries use. Pass **backend SQLAlchemy table/storage classes**, not typed row APIs, per the bootstrap-registration skill (`from msm.models import AssetTable, AssetCategoryTable, AssetCategoryMembershipTable`; `from msm.data_nodes.assets.storage import AssetSnapshotsStorage`). Signature (verified): `start_engine(*, management_mode='platform_managed', namespace=None, models=None, timeout=None) -> MarketsRuntime`. Calling it again with an identical `models` list is **idempotent** (returns the cached runtime, no raise); it raises a `RuntimeError` only when re-invoked with *different* schema args. Typed row ops (`Asset`, `AssetCategory`, …) resolve the runtime internally via `cls._active_context()` → `msm.bootstrap.resolve_runtime()` and raise a guidance `RuntimeError` if the engine was never started. `start_engine` resolves already-registered MetaTables and does **not** migrate/create schema — the SDK migration provider must have registered them first, including the `AssetSnapshotsTS` time-index table.
2. **Resolve assets by ticker via the snapshot layer (DECIDED — §10.1).** `AssetTable` is `{uid, unique_identifier, asset_type}` with **no `ticker`** (verified in `msm/models/assets/core.py`) and `MarketsMetaTableRow.filter` calls `_require_column`, so `current_snapshot__ticker__in` cannot be ported. Ticker resolution goes through `AssetSnapshotsStorage` (cols: `time_index`, `asset_identifier` → FK `AssetTable.unique_identifier`, `name`, `ticker`, `exchange_code`, `asset_ticker_group_id`). Batch-query snapshots by ticker, then map the asset identifier to its `uid`:
   ```python
   from msm.repositories.crud import search_model
   from msm.repositories.assets import get_asset_by_unique_identifier
   from msm.data_nodes.assets.storage import AssetSnapshotsStorage
   from msm.api.base import operation_result_rows

   rows = operation_result_rows(search_model(
       runtime.context, model=AssetSnapshotsStorage,
       in_filters={"ticker": component_symbols}, limit=500,   # page with offset= for large universes
   ))
   # group rows by ticker; per symbol keep asset_identifiers whose LATEST snapshot ticker == symbol;
   # uid = get_asset_by_unique_identifier(runtime.context, unique_identifier=asset_identifier)["uid"]
   ```
   `in_filters` resolves the whole holdings list in one (paged) query instead of N round-trips. Counts give the classification: 0 → missing, 1 → existing, >1 → ambiguous. (The old `current_snapshot.ticker` concept maps directly onto this snapshot row; `msm.services.asset_master_lists` reconstructs the same `current_snapshot` shape from it.)
3. **Category create + membership.** `AssetCategory.upsert(unique_identifier=, display_name=, description=, metadata_json=)` returns an `AssetCategory` with `.uid` (UUID); `__upsert_keys__=('unique_identifier',)`. Then `AssetCategory.replace_memberships(*, category_uid=category.uid, asset_uids=[...]) -> list[AssetCategoryMembership]` — both args keyword-only; implemented as delete-all-for-category then per-asset insert (delegates to `msm.repositories.asset_categories.replace_asset_category_memberships`); it is a full-replace but **not atomic** (separate operations — see §10.2), matching the current remove-then-append semantics. This eliminates the `get_or_create`/`remove`/`append`/re-`get` dance and the 4 client calls.
4. **Membership holds no weights.** `AssetCategoryMembershipTable` keys only `(category_uid, asset_uid)` — it cannot hold weights (verified). Weights stay in `FundHoldings` and, per §10.5, are **not** persisted on the platform by this task (no `metadata_json` provenance set). Weights get a proper home in a follow-up that builds an `ms-markets` portfolio — see [0002](0002-ms-markets-portfolio-weights.md) and ADR [0003](../adr/0003-holdings-weights-live-in-ms-markets-portfolios.md).

Type consequence: `Asset.uid` / `AssetCategoryMembership.asset_uid` are `uuid.UUID`, so the public fields are renamed and retyped — `AssetCategorySyncResult.asset_uids: list[uuid.UUID]` and `HoldingsAssetCategoryPlan.existing_asset_uids_by_symbol: dict[str, uuid.UUID]` (were `…_ids…: …int`), and the CLI JSON output emits `str(uuid)` via `json.dumps(default=str)` (§10.4).

## 4. Scope

**In scope** (respects the two responsibilities: extract holdings weights; register/refresh `HOLDINGS__<ETF>` categories from already-registered assets):
- Replace direct `mainsequence.client` usage in `mainsequence_categories.py` with `msm` typed rows (asset resolution + category create/sync).
- Add a single lazy `msm.start_engine` bootstrap helper, replacing `_load_mainsequence_client`.
- Change public asset-id types `int → uuid.UUID|str` on `AssetCategorySyncResult`, `HoldingsAssetCategoryPlan`, and the CLI JSON shape.
- Stale-state cleanups surfaced by the audit: User-Agent string, `pyproject` dep hygiene, version drift in `agent_card.json` / `.agents/status.md`, stale `etfholdingextractor-161` doc paths.
- Update ADR/docs/skills and tests (including new `msm`-boundary coverage).

**Out of scope** (stated non-goals across `docs/architecture.md`, ADR 0002, `mapping_notes`):
- Asset registration for missing/ambiguous symbols (lookup-only; they remain blockers).
- FIGI resolution as a runtime concern. `OpenFigiDetails` / `msm.services.assets.openfigi.*` are **not used** — the owner rejected the OpenFIGI resolver (§10.1); ticker→asset goes through the snapshot layer instead.
- Persisting per-holding weights anywhere on the platform (do **not** set `metadata_json` or introduce a DataNode/storage table here). Weights are handled by the follow-up [0002](0002-ms-markets-portfolio-weights.md) (ms-markets portfolio) per ADR [0003](../adr/0003-holdings-weights-live-in-ms-markets-portfolios.md).
- Broker/tradability checks, ETF registration orchestration, execution workflows.
- Any change to the extraction surface (`reader.py`, `providers/*`, `models.py`, `settings.py`, `artifacts.py`) or the `weights_extraction` skill.

## 5. Work items

Ordered so non-breaking refactors land first. Effort: S/M/L. "Breaking?" = changes a public contract or output shape.

### Area A — Non-breaking prep (land first)

- [ ] **A-1. Add lazy `msm` bootstrap helper (replace `_load_mainsequence_client`).** *(file: `src/etfh_extractor/mainsequence_categories.py`)*
  - Before: `_load_mainsequence_client()` returns `import mainsequence.client as msc` (line 16).
  - After: a module-level `_ensure_msm_started() -> MarketsRuntime` that imports `from msm import start_engine`, the backend tables `from msm.models import AssetTable, AssetCategoryTable, AssetCategoryMembershipTable`, and `from msm.data_nodes.assets.storage import AssetSnapshotsStorage` **inside the function** (preserve the lazy quarantine), calls `start_engine(models=[AssetTable, AssetSnapshotsStorage, AssetCategoryTable, AssetCategoryMembershipTable])` once, and caches/returns the `MarketsRuntime` (its `.context` is needed for the B-1 snapshot queries). Pass backend table/storage classes, not typed row APIs (bootstrap-registration rule). Calling `start_engine` again with an identical `models` list is idempotent — it returns the cached runtime and does **not** raise — so a simple module-level once-guard is sufficient; it only raises `RuntimeError` when re-invoked with *different* schema args, which this single fixed call site cannot trigger. Invoke it at the top of `resolve_existing_assets_by_ticker` and `sync_holdings_asset_category`. Importing `etfh_extractor` and running extraction must never trigger it.
  - Risk: medium · Effort: S · Breaking? No (internal helper).
  - Note: keep `_load_mainsequence_client` removed only after B-1/B-2 no longer reference it.

- [ ] **A-2. Fix stale default User-Agent.** *(files: `src/etfh_extractor/providers/base.py`, plus the `user_agent='etfh-extractor/0.1.0'` default on `ETFHoldingsReader` in `src/etfh_extractor/reader.py`)*
  - Before: hard-coded `'etfh-extractor/0.1.0'` while `pyproject` is `0.1.7`.
  - After: derive from the package version, e.g. `f"etfh-extractor/{__version__}"` using the existing `importlib.metadata` resolution in `__init__.py` (fall back to the literal if import is undesirable in `providers/base.py`).
  - Risk: low · Effort: S · Breaking? No.

- [ ] **A-3. Sync version drift in agent state.** *(files: `.agents/agent_card.json`, `.agents/status.md`)*
  - Before: both state `0.1.5`; `pyproject.toml` is `0.1.7` (and will bump on this refactor).
  - After: set to the `pyproject` version at the time this refactor is cut. Leave the empty placeholders (`provider.organization`, `provider.url`, `documentationUrl`, `supportedInterfaces`) as-is per `tasks.md` items 2–3.
  - Risk: low · Effort: S · Breaking? No.

- [ ] **A-4. Fix stale doc paths.** *(files: `docs/reader.md` line 147; `docs/adr/0002-extension-into-providers-and-mainsequence-categories.md` line 284)*
  - Before: reference `.../etfholdingextractor-161/...` under base `/Users/jose/mainsequence/...` (note: not the current `/Users/jose/mainsequence-dev/...` base).
  - After: current project dir slug `etfholdingextractor-c55732f8-009a-4663-a03d-ce0de87d5b24` and the correct base, or convert to a relative/placeholder path to avoid future drift. The fix must correct both the project-dir slug (`161` → `c55732f8-...`) and the base path.
  - Risk: low · Effort: S · Breaking? No.

### Area B — Core `msm` migration (breaking; requires §10 decision confirmed first)

- [ ] **B-1. Rewrite `resolve_existing_assets_by_ticker` onto the msm snapshot layer.** *(file: `src/etfh_extractor/mainsequence_categories.py`, lines 128–162)* — resolver **DECIDED** (§10.1: msm asset-snapshot layer).
  - Before: `msc.Asset.filter(current_snapshot__ticker__in=component_symbols)`, group by `_coerce_asset_ticker`, read `.id` (int) — broken today (no `mainsequence.client.Asset` in SDK 4.3.16).
  - After: `runtime = _ensure_msm_started()`; one batched `operation_result_rows(search_model(runtime.context, model=AssetSnapshotsStorage, in_filters={"ticker": component_symbols}, limit=500))` (page with `offset=` / chunk the list if the universe + snapshot history exceeds 500). Group rows by `ticker`; for each symbol keep the distinct `asset_identifier`s whose **latest** snapshot ticker still equals that symbol (confirm latest per identifier, mirroring `_latest_asset_snapshot_by_unique_identifier` in `msm.services.asset_master_lists`); resolve each surviving identifier with `get_asset_by_unique_identifier(runtime.context, unique_identifier=identifier)["uid"]`. Classify by count: 0 → `missing_registered_symbols`, 1 → `existing_asset_uids_by_symbol[symbol] = uid`, >1 → `ambiguous_registered_symbols` (zero/one/many preserved).
  - Drop `_coerce_asset_ticker` and the `.current_snapshot` attribute logic (the snapshot row replaces it). Change the return tuple + `existing_asset_uids_by_symbol` value type to `dict[str, uuid.UUID]` (`str` in JSON). **Keep the keyword signature `(*, component_symbols)`** so `resolve_existing_assets_by_ticker_fn` injection is unchanged.
  - Imports: `from msm.repositories.crud import search_model`, `from msm.repositories.assets import get_asset_by_unique_identifier`, `from msm.data_nodes.assets.storage import AssetSnapshotsStorage`, `from msm.api.base import operation_result_rows` (lazy, inside the function).
  - Risk: high · Effort: M · Breaking? Yes (return id type).
  - Sub-risks (§10.1): snapshot recency confirmation, and whether `AssetSnapshotsTS` is actually populated with tickers for the component universe (else all symbols resolve to `missing`).

- [ ] **B-2. Rewrite `sync_holdings_asset_category` body.** *(file: `src/etfh_extractor/mainsequence_categories.py`, lines 226–254)*
  - Before: `get_or_create` → read `category.assets` → `remove_assets` → `append_assets` → `get` → read `category.assets`.
  - After (signature becomes `sync_holdings_asset_category(*, etf_ticker, asset_uids)`):
    ```python
    from msm.api.assets import AssetCategory  # lazy, inside the function
    _ensure_msm_started()
    unique_identifier = build_holdings_asset_category_unique_identifier(etf_ticker)
    ordered_asset_uids = list(dict.fromkeys(asset_uids))  # de-dup, preserve order; UUIDs
    category = AssetCategory.upsert(
        unique_identifier=unique_identifier,
        display_name=unique_identifier,
        description=f"Published holdings assets for ETF {normalize_ticker(etf_ticker)}.",
    )  # no metadata_json — weights/provenance are out of scope (§10.5)
    memberships = AssetCategory.replace_memberships(
        category_uid=category.uid, asset_uids=ordered_asset_uids
    )
    return AssetCategorySyncResult(
        unique_identifier=category.unique_identifier,
        display_name=category.display_name,
        asset_uids=[m.asset_uid for m in memberships],  # from returned memberships, not a re-fetch
    )
    ```
  - Drop `_coerce_asset_id`. Preserve `dict.fromkeys` de-dup/order. Rename the param `asset_ids → asset_uids` and `AssetCategorySyncResult.asset_ids → asset_uids: list[uuid.UUID]`. The two-step is non-atomic (§10.2): let any failure propagate so the CLI exits non-zero (no `synced: true` on partial failure).
  - Risk: medium · Effort: M · Breaking? Yes (uid type + field rename + result population source).

- [ ] **B-3. Update public type annotations and `__init__` surface.** *(files: `src/etfh_extractor/mainsequence_categories.py`, `src/etfh_extractor/__init__.py`)*
  - `AssetCategorySyncResult.asset_ids: list[int]` → `asset_uids: list[uuid.UUID]`; `HoldingsAssetCategoryPlan.existing_asset_ids_by_symbol: dict[str, int]` → `existing_asset_uids_by_symbol: dict[str, uuid.UUID]`. Update `summary()` keys accordingly. No change to `__all__` membership. Add `import uuid` as needed.
  - Risk: low · Effort: S · Breaking? Yes (type).

- [ ] **B-4. CLI JSON output: serialize UUIDs.** *(file: `src/etfh_extractor/cli/__init__.py`)*
  - `_print_json` uses `json.dumps(..., sort_keys=True, indent=2)`; UUIDs are not JSON-serializable. Coerce asset uids to `str(uuid)` before serialization (in the plan/result `to_dict`/`summary` paths, or via a `default=str` argument to `json.dumps`). Surface the `start_engine` guidance `RuntimeError` as a clean `category-sync` error message (non-zero exit) rather than a traceback. No auth code change (platform SDK session is ambient).
  - Risk: medium · Effort: S · Breaking? Yes (output shape: int → str uuid).

### Area C — Dependency & docs follow-on (after B lands)

- [ ] **C-1. Remove the direct SDK import / dep hygiene.** *(files: `src/etfh_extractor/mainsequence_categories.py`, `pyproject.toml`)* — see §7. Risk: low · Effort: S · Breaking? No.
- [ ] **C-2. ADR + docs + skills updates.** — see §8. Risk: low · Effort: M · Breaking? No.
- [ ] **C-3. Tests.** — see §9. Risk: medium · Effort: M · Breaking? Yes (assertion updates).

## 6. ms-markets symbol reference

All symbols below were verified (`exists=true`) in the symbol-verification pass against `.venv/.../msm`. Use exactly these import paths.

| Symbol | Verified import / call form | Status |
|---|---|---|
| `start_engine` | `from msm import start_engine` (re-export of `msm.bootstrap.start_engine`); `start_engine(*, management_mode='platform_managed', namespace=None, models=None, timeout=None)` | verified |
| `msm.bootstrap.start_engine` | `from msm.bootstrap import start_engine` | verified |
| `msm.bootstrap.resolve_runtime` | `from msm.bootstrap import resolve_runtime` (`*, models, row_model_name=None, timeout=None`) | verified |
| `MarketsRuntime` | `from msm.bootstrap import MarketsRuntime` (frozen dataclass) | verified |
| `MarketsMetaTableRow` | `from msm.api.base import MarketsMetaTableRow` | verified |
| `MarketsMetaTableRow.filter` | `Asset.filter(*, limit=500, **filters)` (classmethod) | verified |
| `MarketsMetaTableRow.start_engine` | `Asset.start_engine(**kwargs)` (delegates with `cls.__required_tables__`) | verified |
| `operation_result_rows` | `from msm.api.base import operation_result_rows` | verified |
| `Asset` | `from msm.api.assets import Asset` | verified |
| `Asset.upsert` | `Asset.upsert(payload=None, **kwargs)` | verified |
| `Asset.get_by_unique_identifier` | `Asset.get_by_unique_identifier(unique_identifier) -> Asset|None` (inherited) | verified |
| `Asset.filter` | `Asset.filter(*, limit=500, **filters)` (inherited) | verified |
| `AssetCategory` | `from msm.api.assets import AssetCategory` | verified |
| `AssetCategory.upsert` | `AssetCategory.upsert(payload=None, **kwargs)`; `__upsert_keys__=('unique_identifier',)` | verified |
| `AssetCategory.replace_memberships` | `AssetCategory.replace_memberships(*, category_uid, asset_uids) -> list[AssetCategoryMembership]` | verified |
| `AssetCategoryMembership` | `from msm.api.assets import AssetCategoryMembership`; `__upsert_keys__=('category_uid','asset_uid')` | verified |
| `OpenFigiDetails` | `from msm.api.assets import OpenFigiDetails` (fields incl. `ticker`, `isin`, `figi`, `asset_uid`) | verified |
| `replace_asset_category_memberships` | `from msm.repositories.asset_categories import replace_asset_category_memberships` (`context, *, category_uid, asset_uids`) | verified (delegate; not called directly by this refactor) |
| `query_figi` | `from msm.services.assets.openfigi import query_figi` (`tickers, *, market_sector, ...`) | verified (only if §10 option (a)) |
| `query_by_isin` | `from msm.services.assets.openfigi import query_by_isin` | verified (only if §10 option (a)) |
| `AssetTable` | `from msm.models.assets.core import AssetTable` (cols: `uid`, `unique_identifier`, `asset_type`) | verified (evidence for "no ticker column") |
| `AssetSnapshotsStorage` | `from msm.data_nodes.assets.storage import AssetSnapshotsStorage` (cols: `time_index`, `asset_identifier`, `name`, `ticker`, `exchange_code`, `asset_ticker_group_id`) | verified (**chosen ticker→asset resolver**, §10.1) |
| `search_model` | `from msm.repositories.crud import search_model` (`context, *, model, filters=, in_filters=, contains_filters=, limit=500, offset=0`) | verified |
| `get_asset_by_unique_identifier` | `from msm.repositories.assets import get_asset_by_unique_identifier` (`context, *, unique_identifier`) → dict incl. `uid` | verified |
| `AssetCategoryTable`, `AssetCategoryMembershipTable` | `from msm.models import AssetCategoryTable, AssetCategoryMembershipTable` (backend classes for `start_engine(models=[...])`) | verified |
| `MarketsRuntime.context` | `start_engine(...).context` → `MarketsRepositoryContext` (passed to `search_model`) | verified |

No unverified symbols are relied upon. The OpenFIGI helpers (`OpenFigiDetails`, `query_figi`, `query_by_isin`) and the typed `Asset.get_by_unique_identifier` / `Asset.filter` lookups remain in the table for reference but are **not used by the chosen resolver** — ticker→asset goes through `AssetSnapshotsStorage` + `search_model` (§10.1).

## 7. Dependency & packaging notes

- `pyproject.toml` currently declares `mainsequence>=3.18.17` (line 13) **and** `ms-markets>=0.0.49` (line 14). After B-1/B-2 land, **remove** the direct `import mainsequence.client as msc` so `etfh_extractor` depends on `mainsequence` **only transitively via `msm`** (`msm` executes through the ambient `mainsequence.client` MetaTable session, so the SDK must remain installed).
- Keep both deps declared: keep/pin `ms-markets>=0.0.49`; keep `mainsequence` (consumed indirectly, never imported directly by `etfh_extractor`).
- No new runtime deps — `msm` is already present (`0.0.49` confirmed installed).
- Bump the package version in `pyproject.toml` for this refactor and propagate it to `.agents/agent_card.json` / `.agents/status.md` (A-3) and the User-Agent (A-2).
- Two console scripts (`etfh`, `etfh-read`) are unchanged.

## 8. Docs / skills / AGENTS.md updates required

- **New ADR (or supersede ADR 0002).** Document: the move from `mainsequence.client` to `msm` typed rows; the chosen ticker-identity contract (§10); the `int → uuid.UUID|str` id change; the `upsert` + `replace_memberships` two-step. Reaffirm (do **not** change) ADR 0002 `HOLDINGS__<ETF>` semantics: membership onto **existing** assets, weights stay in `FundHoldings`, no asset registration, no FIGI resolution at runtime.
- **`docs/library.md` and `docs/reader.md`.** Replace `get_or_create`/`append`/`remove` + int-id descriptions with `AssetCategory.upsert` + `AssetCategory.replace_memberships`, UUID asset ids, and the note that auth comes from the ambient platform session via `msm.start_engine`. Fix stale `etfholdingextractor-161` paths (A-4).
- **`.agents/skills/holdings_category_sync/SKILL.md`.** Update to reference `msm` symbols and the new uid-based result shape; keep its rules (surface `missing_registered_symbols` / `ambiguous_registered_symbols`; never present a category as synced while blockers remain; route weights-only requests to `weights_extraction`).
- **`weights_extraction` skill: unchanged** (extraction surface is untouched).
- **`AGENTS.md`.** Keep the two-capability Project-Specific Instruction section; reflect that category sync now goes through `msm` and requires a one-time `start_engine` bootstrap (auth still via the platform SDK session).

## 9. Testing & validation plan

**Define success up front** (AGENTS.md convention):
1. `etfh_extractor` imports and pure extraction run with **no** MainSequence runtime started (lazy quarantine preserved).
2. `resolve_existing_assets_by_ticker` maps zero / one / many matches to `missing` / `existing` / `ambiguous` correctly with UUID ids.
3. `sync_holdings_asset_category` calls `AssetCategory.upsert` then `AssetCategory.replace_memberships` (the previously-untested call sites are now covered).
4. The DI seams `read_holdings_fn` and `resolve_existing_assets_by_ticker_fn` still let the plan build with no live runtime; `cli.main(argv, reader=...)` injection still works.
5. CLI `category-sync` emits valid JSON with `str(uuid)` asset ids and exits 1 (no sync) when blockers exist, 0 on success.
6. `agent_card.json` / `status.md` version matches `pyproject.toml`.

**Unit tests** *(file: `tests/test_reader.py`, `HoldingsCategoryTests` + `ETFHoldingsReaderTests`)*:
- Update existing category-sync chain test assertions from `int` ids to `uuid.UUID`/`str`.
- Add an `msm`-boundary test that monkeypatches the classmethods on the frozen Pydantic rows — `Asset.get_by_unique_identifier` (or `Asset.filter`), `AssetCategory.upsert`, `AssetCategory.replace_memberships` — to assert: (a) zero/one/many → missing/existing/ambiguous; (b) sync calls `upsert` then `replace_memberships` with `category_uid=` and the de-duped ordered `asset_uids`. **Ensure `msm.start_engine` is never invoked in unit tests** — monkeypatch `_ensure_msm_started` to a no-op (or guard it) so no live runtime is required.
- Keep `build_holdings_asset_category_plan` driven by injected `read_holdings_fn` + `resolve_existing_assets_by_ticker_fn` (no signature change), both via `component_provider` and via `fund_url` inference.

**Live validation (manual, before any real category sync)** — the CLI/standalone path relies on the ambient platform SDK session that `msm` executes through (see §10 open question on session config):
- `mainsequence project current --debug` — confirm the active project/session.
- `mainsequence project refresh_token --path .` (or the platform's token-refresh command) — ensure credentials are valid before a write.
- Then a dry run: `etfh category-sync --ticker IVV --fund-url <url>` and confirm `start_engine` resolves the registered MetaTables and that a blocker-free plan syncs and returns UUID asset ids.

> Confirm the exact platform credential/env setup and that `management_mode='platform_managed'` is the right mode for this standalone tool before running a live sync.

## 10. Open questions / risks

1. **Asset identity contract — DECIDED (resolver = msm asset-snapshot layer).** `AssetTable` is `{uid, unique_identifier, asset_type}` with no `ticker`. Owner's decision: resolve ticker→asset through `AssetSnapshotsStorage` — batch `search_model(runtime.context, model=AssetSnapshotsStorage, in_filters={"ticker": symbols})`, take the latest snapshot per `asset_identifier`, map `asset_identifier` → asset `uid` via `get_asset_by_unique_identifier`. Preserves 0/1/many → missing/existing/ambiguous. Implemented in §3 step 2 and B-1.
   - **Rejected:** option (a) OpenFIGI-based resolution (`OpenFigiDetails` is exported but not a usable path here per the owner); and option (c)-as-written ("thin `mainsequence.client` lookup" — no `mainsequence.client.Asset` exists in SDK 4.3.16, see §2).
   - **Residual sub-questions to confirm before/while implementing B-1:**
     - (i) **Recency semantics** — the resolver should match an asset's *current/latest* snapshot ticker; an asset whose ticker historically equalled the symbol but has since changed must not match. Confirm the latest-per-`asset_identifier` rule (and tie-breaking on equal `time_index`) is correct.
     - (ii) **Data availability** — confirm `AssetSnapshotsTS` is actually populated with tickers for the component universe in the target project; if it is empty, every symbol resolves to `missing_registered_symbols`.
     - (iii) **Scale/paging** — `search_model` defaults to `limit=500` and snapshots are time-series (multiple rows per asset), so a ~500-name ETF can exceed the limit; page with `offset=` or chunk `component_symbols` (see §10.6).
2. **`replace_memberships` semantics — ANSWERED FROM CODE (non-atomic; accept idempotent re-run).** `AssetCategory.replace_memberships` (`msm/api/assets.py:542`) delegates to `replace_asset_category_memberships` (`msm/repositories/asset_categories.py:331`), which builds one *delete-all-for-category* op plus one *insert* op per `asset_uid` and runs **each as a separate `MetaTable.execute_operation`** in a plain Python loop (`msm/repositories/base.py:170`). There is **no enclosing transaction** in `0.0.49`, so a failure after the delete (or partway through the inserts) leaves the category partially populated — worst case emptied. **Decision: accept it.** The whole sync (`upsert` → `replace_memberships`) is idempotent — re-running restores the full set — so the CLI must treat any failure as a hard error (non-zero exit, never report `synced: true` on partial failure) and the operator re-runs. Do not document this as atomic.
3. **Session/credentials in CLI/standalone — ASSUMED PRESENT (per owner).** Treat the ambient `mainsequence` platform session as already configured wherever `category-sync` runs (same assumption as any `msm`-using project); `management_mode='platform_managed'` (the `start_engine` default) is correct. Not a blocker. The only code obligation: surface a clean error if `start_engine`/row ops raise because the runtime/session isn't available (B-4).
4. **UUID id contract — ACCEPTED (no `int` ids anywhere).** Per the owner, the project no longer uses integer ids, and field/param names drop `id` for `uid`: `AssetCategorySyncResult.asset_uids: list[uuid.UUID]`, `HoldingsAssetCategoryPlan.existing_asset_uids_by_symbol: dict[str, uuid.UUID]`, `sync_holdings_asset_category(asset_uids=...)`, and the CLI JSON emits `str(uuid)` (via `json.dumps(default=str)`). Intended breaking change.
5. **Provenance / weights — NOT in `metadata_json`; deferred to follow-ups.** Do **not** stash weights or provenance in `AssetCategory.metadata_json` in this task; B-2 sets no `metadata_json`. Weights get a proper home in a **follow-up**: build an `ms-markets` **portfolio** carrying the actual holdings weights — see [0002-ms-markets-portfolio-weights.md](0002-ms-markets-portfolio-weights.md). The placement decision is captured in a **follow-up ADR**: [docs/adr/0003-holdings-weights-live-in-ms-markets-portfolios.md](../adr/0003-holdings-weights-live-in-ms-markets-portfolios.md).
6. **Large universes.** ETF holdings can be ~500 names. The chosen resolver issues one batched `search_model(..., in_filters={"ticker": symbols})` (not N round-trips), but `search_model` defaults to `limit=500` and snapshots are time-series (multiple rows per asset), so the result set can exceed the limit — page with `offset=` or chunk `component_symbols`. The latest-ticker confirmation may add a bounded number of per-candidate lookups. Performance risk, not correctness.

## 11. Rollout / sequencing

1. **Area A (non-breaking):** A-1 bootstrap helper (lazy, once-guarded), A-2 User-Agent, A-3 version sync, A-4 doc paths. These can merge before Area B because A-1 only adds an unused helper path until B wires it in.
2. **Gate:** the §10.1 resolver is decided (snapshot layer); before/while implementing B, confirm its residual sub-questions (snapshot recency, data availability, paging) plus the remaining open questions §10.2–§10.6 (replace-memberships partial-failure window, session/credentials config, UUID-contract acceptance, provenance policy) with the platform owner.
3. **Area B (breaking, atomic together):** B-1 (`resolve_existing_assets_by_ticker`), B-2 (`sync_holdings_asset_category`), B-3 (type annotations), B-4 (CLI UUID serialization + clean `start_engine` error). Land as one change so the public id type flips consistently across module, package surface, and CLI output.
4. **Area C (follow-on):** C-1 remove the direct `mainsequence.client` import + dep-hygiene note, C-3 test updates (must accompany B to keep CI green — practically land C-3 with B), C-2 ADR/docs/skills.
5. **Validate:** run the unit suite (no live runtime), then the §9 live-validation CLI checks before the first real `category-sync` against the platform.

## Relevant files

- `src/etfh_extractor/mainsequence_categories.py`
- `src/etfh_extractor/cli/__init__.py`
- `src/etfh_extractor/__init__.py`
- `src/etfh_extractor/reader.py`
- `src/etfh_extractor/providers/base.py`
- `pyproject.toml`
- `tests/test_reader.py`
- `.agents/agent_card.json`
- `.agents/status.md`
- `docs/library.md`
- `docs/reader.md`
- `docs/adr/0002-extension-into-providers-and-mainsequence-categories.md`
- `.agents/skills/holdings_category_sync/SKILL.md`
- `AGENTS.md`
