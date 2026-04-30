# ADR 0002: Extension Into Providers and MainSequence Categories

- Status: Accepted
- Date: 2026-04-30

## Context

This repository now provides a provider-aware ETF holdings workflow:

- `src/etfh_extractor/reader.py` reads supported fund URLs or explicit `(provider, ticker)` inputs
- provider modules download and parse provider-specific source data
- `FundHoldings` preserves holdings rows, weights, fund metadata, and download provenance
- `src/etfh_extractor/mainsequence_categories.py` provides a narrow MainSequence category planning and sync layer
- extraction artifacts are persisted under `data/temp/` across supported providers

That design keeps weighted holdings as the source of truth while supporting provider growth and
downstream category workflows.

The next step is to turn this into a provider-aware holdings library and a narrow
MainSequence-category service without weakening the current data model.

## Current Strengths

This repository already has the right canonical data model for holdings truth.

- `FundHoldings` and `Holding` preserve weights, names, dates, workbook provenance, and row-level
  fields.
- the current CLI and reader are small, deterministic, and easy to reason about
- ADR 0001 already points toward provider artifacts and evidence retention instead of returning only
  a lossy symbol list

That is the architectural advantage to preserve.

## Implemented Scope

The following scope is implemented in this repository:

- provider registry and provider-specific modules for `ishares`, `invesco`, `vanguard`, and `state_street`
- direct URL workflows plus explicit `(provider, ticker)` workflows
- URL-based provider inference
- provider artifact persistence shared across supported providers
- derived symbol expansion from authoritative `FundHoldings`
- MainSequence category planning and sync for already-registered assets
- provider parsing fixtures, registry tests, category-plan tests, and symbol-derivation tests

## Decision

This repository will extend into a provider-aware weighted-holdings library with an optional
MainSequence category layer.

The design rules are:

1. `FundHoldings` remains the canonical extraction result.
2. Provider-specific code must normalize into weighted holdings, not only ticker lists.
3. Symbol-only expansion must be derived from `FundHoldings`, not become the primary parse output.
4. MainSequence category planning and sync must consume extracted holdings and remain independent of
   downstream registration or execution concerns.
5. Browser automation may exist as an optional fallback for specific providers, but it must not be
   required by the default iShares path.
6. Provider configuration must be validated against the registered extractors at load time.
7. ETF registration planning and execution are explicitly out of scope for this repository.

## Implemented Design

### Phase 1: Provider abstraction

The original iShares logic has been moved behind a provider layer.

Implemented structure:

- `src/etfh_extractor/providers/common.py`
- `src/etfh_extractor/providers/base.py`
- `src/etfh_extractor/providers/registry.py`
- `src/etfh_extractor/providers/ishares.py`

Implemented behavior:

- keep the current `ETFHoldingsReader` public API as a compatibility façade
- make the reader delegate to a registered provider implementation
- move parsing helpers that are useful across providers into `providers/common.py`
- keep iShares as the first provider and preserve current behavior

### Phase 2: Provider source resolution and input ownership

The repository owns provider handling rules explicitly.

Implemented structure:

- `src/etfh_extractor/settings.py`

Implemented behavior:

- support both direct URL inputs and explicit `(provider, ticker)` inputs
- infer provider from fund URL only
- do not maintain a ticker-to-provider lookup table in code or data
- keep ticker-based workflows explicit so provider ownership does not drift into configuration

### Phase 3: Additional providers without regressing the core model

Implemented providers:

- `invesco`
- `vanguard`
- `state_street`

Implemented rules:

- every provider must return `FundHoldings`
- the provider should preserve weight-bearing holdings rows whenever the source publishes them
- if a provider only exposes component membership cleanly at first, the gap must be explicit in the
  result model and documentation rather than hidden
- browser-backed fallback should live behind an optional dependency boundary, for example a separate
  helper module or extra install target

### Phase 4: MainSequence holdings-category services

The repository includes a MainSequence-facing module with a narrow planning and sync boundary.

Implemented structure:

- `src/etfh_extractor/mainsequence_categories.py`

Implemented APIs:

- `build_holdings_asset_category_unique_identifier(...)`
- `infer_holdings_component_provider(...)`
- `build_holdings_asset_category_plan(...)`
- `resolve_existing_assets_by_ticker(...)`
- `sync_holdings_asset_category(...)`

Implemented rules:

- `HOLDINGS__<ETF>` means provider-published ETF membership mapped onto existing MainSequence assets
- category planning uses extracted holdings as source truth
- the caller may provide the provider explicitly
- if the provider is not provided, infer it from the fund URL when a fund URL is available
- ticker-based category planning without a fund URL still requires an explicit provider
- provider inference is valid from fund URLs, not from ETF tickers
- only valid component assets are synced into the category
- weights stay available in the extracted holdings result even if `AssetCategory` itself only stores
  assets
- no asset registration orchestration, broker availability logic, or FIGI resolution is part of
  this module

### Phase 5: Provider-agnostic artifacts and evidence

ADR 0001 artifact handling is implemented in provider-agnostic form.

Implemented behavior:

- downloaded source artifacts, normalized intermediate tables, and JSON outputs should use the same
  storage policy across providers
- ambiguity review should happen against provider-specific artifacts, not against ad hoc parsing
- if LLM-assisted validation is added later, it should operate on the normalized provider result and
  saved evidence rather than on provider-specific control flow

### Phase 6: Tests and documentation

Implemented tests:

- provider registry resolution
- provider-config validation
- provider-specific parsing fixtures
- derived symbol expansion from `FundHoldings`
- MainSequence category planning with stubbed asset lookups

Implemented documentation:

- provider architecture
- direct URL versus provider-and-ticker workflows
- category planning and sync boundaries
- the rule that downstream consumers use ETF outputs later, but do not redefine ETF holdings

## Rejected Alternative

Do not broaden the package by making symbol-only expansion or category sync the primary model.

That would weaken the current design by:

- discarding provider weights too early
- making downstream projections look authoritative
- increasing the risk of config drift and hidden extraction gaps
- mixing extraction concerns with downstream orchestration concerns

The correct move is to keep weighted holdings as the source of truth and make all other views
downstream of that model.

## Consequences

Positive:

- multi-provider support can be added without rewriting the public reader API
- MainSequence category sync becomes available without coupling ETF truth to downstream execution
  logic
- weights, names, dates, and source provenance remain first-class data
- provider growth becomes testable and configurable in one place

Tradeoffs:

- the package will gain more modules and a more explicit service boundary
- some providers may require optional browser-backed fallback support
- the project will need a clearer distinction between extraction completeness and category-sync
  readiness

## Non-Goals

This ADR does not introduce:

- FIGI resolution
- broker tradability filtering
- ETF registration orchestration
- downstream execution logic that consumes ETF outputs

Those concerns may consume this repository's outputs later, but they must not be reintroduced into
the extraction or category layers here.

## Outcome

The implemented architecture keeps `FundHoldings` authoritative, makes providers pluggable, keeps
artifacts inspectable, and limits MainSequence category functionality to a downstream projection of
already-extracted holdings.

## Implementation Tasks

### Phase 1: Provider Abstraction

- [x] Create `src/etfh_extractor/providers/base.py` with the provider interface that returns `FundHoldings`.
- [x] Create `src/etfh_extractor/providers/common.py` for reusable parsing and normalization helpers.
- [x] Create `src/etfh_extractor/providers/registry.py` to resolve provider implementations by normalized provider name.
- [x] Move the existing iShares fetch and parse logic into `src/etfh_extractor/providers/ishares.py`.
- [x] Keep `ETFHoldingsReader` as the public compatibility facade and delegate through the provider registry.
- [x] Keep the current CLI behavior unchanged for direct iShares fund URLs.

### Phase 2: Provider Configuration

- [x] Create `src/etfh_extractor/settings.py` for provider configuration, URL builders, and provider inference helpers.
- [x] Support provider inference from fund URLs only.
- [x] Support explicit providers and fall back to URL-based inference when a fund URL is available.
- [x] Require explicit providers for ticker-based workflows that do not include a fund URL.
- [x] Validate unsupported provider names through the provider registry.
- [x] Add explicit error messages for unsupported configured providers and unsupported ticker-only calls without a provider.
- [x] Extend the public API to support provider-and-ticker inputs in addition to direct fund URLs.

### Phase 3: Additional Providers

- [x] Add `src/etfh_extractor/providers/invesco.py`.
- [x] Add `src/etfh_extractor/providers/vanguard.py`.
- [x] Add `src/etfh_extractor/providers/state_street.py`.
- [x] Normalize each new provider into `FundHoldings` rather than symbol-only outputs.
- [x] Introduce optional browser-backed fallback helpers behind a non-core dependency boundary for providers that need them.
- [x] Document any provider that is temporarily membership-only or missing trustworthy weight extraction.

Provider implementation note:

- current provider implementations aim to return weighted `FundHoldings` only
- they do not intentionally degrade into symbol-only membership outputs
- if a provider response does not expose a trustworthy weight field in a supported structure, the
  extractor should fail rather than silently fabricate zero-weight holdings

### Phase 4: MainSequence Categories

- [x] Create `src/etfh_extractor/mainsequence_categories.py`.
- [x] Implement `build_holdings_asset_category_unique_identifier(...)`.
- [x] Implement `infer_holdings_component_provider(...)`.
- [x] Implement `resolve_existing_assets_by_ticker(...)`.
- [x] Implement `build_holdings_asset_category_plan(...)` using extracted holdings as the source truth.
- [x] Implement `sync_holdings_asset_category(...)` to create or refresh `HOLDINGS__<ETF>` categories.
- [x] Ensure the category path stays independent from downstream validation and registration flows.
- [x] Keep category APIs limited to planning and syncing categories from already-registered MainSequence assets.

### Phase 5: Artifacts and Evidence

- [x] Generalize ADR 0001 artifact persistence so it works across all supported providers.
- [x] Persist downloaded provider files, normalized intermediate outputs, result JSON, and run metadata under `data/temp/`.
- [x] Standardize artifact naming with timestamps plus provider or ticker identifiers.
- [x] Make artifact inspection part of provider debugging and ambiguity resolution.

### Phase 6: Tests and Documentation

- [x] Add unit tests for provider registry resolution and unsupported-provider validation.
- [x] Add provider fixture tests for iShares, Invesco, Vanguard, and State Street parsing behavior.
- [x] Add tests for derived symbol expansion from `FundHoldings`.
- [x] Add tests for MainSequence category planning with stubbed asset lookups.
- [x] Update [reader.md](/Users/jose/mainsequence/main-sequence-workbench/projects/etfholdingextractor-161/docs/reader.md) for provider-aware workflows.
- [x] Add a new architecture doc describing provider boundaries and category boundaries.
- [x] Update ADR 0001 to reference provider-agnostic artifact handling once implementation begins.
- [x] Document the non-goal boundary clearly so future work does not reintroduce registration or execution concerns here.
