# ADR 0003: Holdings Weights Live in ms-markets Portfolios, Not Category Metadata

- Status: Accepted
- Date: 2026-06-09

## Context

[Implementation task 0001](../implementation_task/0001-migrate-to-ms-markets.md) moves the
MainSequence holdings-category sync from the (now-removed) `mainsequence.client.Asset` /
`AssetCategory` surface onto the `ms-markets` (`msm`) layer. In `msm`:

- `AssetCategoryMembershipTable` is keyed only by `(category_uid, asset_uid)` — a membership edge.
  It **cannot** carry a weight.
- `AssetCategory` exposes a `metadata_json` JSON column, so weights *could* technically be stuffed
  into category metadata.

ADR 0002 set the non-goal that this library does not own asset registration or platform-side truth
beyond `HOLDINGS__<ETF>` category membership, and that `FundHoldings` remains the canonical home for
weights. So the question is: now that `metadata_json` is available, do we persist per-holding
weights (or a weights snapshot / provenance blob) on the platform via the category, or keep weights
out of the platform in this library?

## Decision

Holdings **weights are not persisted through the category-sync path.**

- `etfhextractor`'s `sync_holdings_asset_category` writes membership only. It does **not** set
  `AssetCategory.metadata_json` with weights or provenance. The `HOLDINGS__<ETF>` category stays a
  pure membership set over already-registered assets, consistent with ADR 0002.
- `FundHoldings` remains the canonical in-process representation of weights.
- The canonical **platform** home for weights is an **`ms-markets` portfolio**, populated by a
  separate, opt-in workflow — see [implementation task 0002](../implementation_task/0002-ms-markets-portfolio-weights.md).
  Weights belong to the portfolio domain (a weighted basket with rebalancing semantics), not to an
  asset-category membership edge.
- The mechanism is the `msm_portfolios` signal pipeline: a custom `SignalWeights` subclass whose
  update pulls the extracted ETF weights and emits the canonical signal frame, consumed by
  `PortfoliosDataNode` with an explicit price source — i.e. a portfolio that tracks the ETF.

## Rationale

- **Right model for the data.** A category answers "which assets belong to this ETF's holdings"; a
  portfolio answers "with what weights." Encoding weights in category `metadata_json` would overload
  the membership concept and create a second, unmanaged source of weight truth.
- **Avoids silent platform writes of derived data.** Weights are derived from provider exports and
  change at each as-of date; a portfolio with explicit rebalancing/as-of semantics models that
  history correctly, whereas a JSON blob on a category does not.
- **Keeps task 0001 small and non-controversial.** Membership-only sync has no product question to
  resolve; weight publishing is a deliberate, separately-scoped capability.

## Consequences

- Task 0001 sets no `metadata_json` on the category (membership only).
- A follow-up (task 0002) builds the ms-markets portfolio carrying the actual weights; until then,
  weights are available only via the local extraction surface (`FundHoldings` / `etfh` CLI
  `--format full`).
- Provenance (`as_of_date`, `source_url`, `download_url`) is likewise not pushed onto the category;
  if platform-side provenance is wanted later, it should live with the portfolio publication, not on
  the membership category.
- If a future requirement genuinely needs lightweight provenance on the category, it can be revisited
  in a new ADR; this ADR only rules out weights/provenance on the category for now.
