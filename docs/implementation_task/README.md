# Implementation Tasks

Scoped, execution-ready implementation tasks for `etfhextractor`. Each task is a
self-contained plan: objective, current state, target architecture, ordered work
items, a verified symbol reference, a testing/validation plan, and open questions.

| Task | Status | Summary |
|---|---|---|
| [0001 — Migrate category sync to ms-markets](0001-migrate-to-ms-markets.md) | Implemented | Route asset resolution and `HOLDINGS__<ETF>` category sync through `ms-markets` (`msm`) instead of `mainsequence.client` (which no longer exposes `Asset`/`AssetCategory` in SDK 4.3.16, so the current path is already broken). Ticker→asset resolver: the msm asset-snapshot layer (§10.1). |
| [0002 — ETF-tracking portfolio via custom signal](0002-ms-markets-portfolio-weights.md) | Implemented + live-validated (findings folded into §5.5–§5.6, ADRs 0005/0006) | Follow-up to 0001: `ETFHoldingsSignal` (custom `msm_portfolios` `SignalWeights`) updates weights from the extraction — guarded to insert at most daily and only on change — and `PortfoliosDataNode` builds a portfolio that tracks the ETF (weights do not live on the category — see [ADR 0003](../adr/0003-holdings-weights-live-in-ms-markets-portfolios.md)). |
| [0003 — FIGI registration of missing components](0003-figi-asset-registration.md) | Implemented + live-validated (503/503 IVV components registered) | Register unresolved component tickers through OpenFIGI under [ADR 0004](../adr/0004-figi-only-asset-registration.md): no FIGI → no registration, and only unique ticker→FIGI mappings register (ambiguity stays a blocker). Opt-in via `--register-missing`. |
| [0004 — Agent capabilities](0004-agent-capabilities.md) | Implemented | Coding-agent setup per the project_to_agent skill: AGENTS.md routing refresh, vendored-skill relocation, agent-card finalization (name/interfaces pending user decisions), and a parity test guarding card↔skills↔CLI↔version drift. No agent runtime — capabilities are served through the existing CLI. |
