# Journal

## 2026-09-02

- Migrated the complete package to Python 3.13, Main Sequence SDK 8.0.7, and ms-markets 1.0.2
  without removing extraction, category sync, FIGI registration, holdings signals, portfolio
  publication, or demo-bars behavior.
- Replaced `_required_storage_table`/`storage_table` with the SDK 8 output-table contract and
  replaced removed `APIDataNode` registered-table dependencies with `TimeIndexTableRef`.
- Added a reusable `EtfTrackingPortfolioBuild` result and `build_etf_tracking_portfolio(...)`;
  the existing publisher and CLI retain their JSON response while downstream projects can reuse
  the actual graph with custom portfolio identity and valuation metadata.
- Scoped Alembic ownership to the project demo-bars table, applied revision `0001`, finalized both
  managed resources active, and verified runtime attachment.
- Live iShares IVV extraction returned 508 holdings dated 2026-08-31.
- Refreshed the SDK/platform/ms-markets skills and updated repository docs and state records.

## 2026-04-30

Initialized repository-local agent scaffolding for `etfholdingextractor-161`.

- Added a project-specific instruction section to `AGENTS.md`.
- Added repo-local skills for ETF holdings extraction and holdings category sync.
- Created `.agents/agent_card.json`.
- Initialized `.agents` state files for future maintenance passes.
