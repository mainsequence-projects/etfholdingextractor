# ADR 0001: Layered Weights Extraction and Fallback Storage

- Status: Proposed
- Date: 2026-04-28

## Context

The current extractor trusts the provider workbook's `Weight (%)` column directly. That is fast,
but it does not guarantee the semantics are always the ones the user wants. Providers may change
column names, embed multiple weight concepts, or publish exports whose meaning is only clear from
surrounding context.

We want a more defensive extraction flow that preserves the current deterministic path but adds a
second interpretation layer when a local LLM is available, and otherwise stores enough evidence for
human inspection and replay.

Current implementation status:

- provider-agnostic artifact persistence is implemented for all supported providers
- deterministic extraction remains the active runtime path
- the optional Ollama-assisted second layer remains future work

## Decision

The planned standard flow will be:

1. Download the source file from the ETF provider.
2. Extract a best-effort structured representation from the file.
3. Convert that best-effort representation into CSV as the first explicit artifact.
4. If `OLLAMA_URL` is set, call Ollama as a second layer of defense using:
   - the best-effort extraction
   - the raw downloaded file content or a normalized textual representation
   - a prompt that asks specifically for ticker-to-weight JSON
5. If `OLLAMA_URL` is not set, persist the extraction artifacts locally under `data/temp/`.
6. Return ticker-weight JSON to the user and make the supporting artifacts easy to inspect.

## Detailed Plan

### 1. Best-Effort CSV Extraction

The extractor should always emit a best-effort CSV regardless of whether the final answer comes
from deterministic parsing or from Ollama-assisted interpretation.

Planned requirements:

- Normalize obvious holdings headers such as ticker, symbol, weight, name, and market value.
- Preserve rows even when semantics are uncertain, instead of dropping ambiguous records early.
- Include enough surrounding columns to let a second pass reason about the file.
- Treat the CSV as an intermediate artifact, not the sole source of truth.

### 2. Optional Ollama Second Layer

If `OLLAMA_URL` exists in the environment, Ollama becomes part of the standard extraction flow.

Planned prompt inputs:

- provider URL
- downloaded filename
- best-effort parsed CSV or JSON preview
- raw source text or a loss-minimized normalized rendering of the downloaded file
- an instruction to return only ticker-weight JSON and to flag uncertainty when the source is
  semantically ambiguous

Planned role of Ollama:

- validate whether the deterministic interpretation of weights looks semantically correct
- recover weights when the provider file format shifts in ways the structured parser does not yet
  understand
- act as a second layer, not a replacement for deterministic extraction

### 3. Provider-Agnostic Local Artifact Persistence

The extractor persists recent extraction artifacts in `data/temp/` across supported providers.

Implemented artifacts per run:

- downloaded source file
- best-effort CSV
- JSON result returned to the user
- small metadata file with source URL, extraction timestamp, and parser mode

Implemented file naming:

- use a timestamp plus a fund slug or short hash to avoid collisions
- keep the layout easy to inspect manually

Git policy:

- `data/temp/` must stay ignored by git
- artifacts are local debugging evidence, not repository content

### 4. Agent Skill for Weights Requests

A repo-local skill should exist at `.agents/skills/weights_extraction/`.

Planned behavior for the skill:

- when the user asks for ETF or fund weights, follow the CLI path first
- inspect the downloaded file or the saved artifacts in `data/temp/`
- answer with JSON ticker weights
- prefer the extracted evidence over ad hoc reasoning
- mention uncertainty only when the file semantics are genuinely ambiguous

## Consequences

Positive:

- keeps deterministic extraction as the primary path
- adds a semantic backstop when Ollama is available
- preserves evidence locally when Ollama is not available
- gives agents a consistent operational playbook

Tradeoffs:

- more moving parts in the extraction pipeline
- local artifact management must be kept tidy
- Ollama prompts will need careful limits so large files do not explode token usage

## Implementation Notes

Artifact persistence is implemented and shared across providers.

The optional Ollama validation layer is still planned and is not part of the current runtime path.
