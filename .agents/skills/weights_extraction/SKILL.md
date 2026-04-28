---
name: weights-extraction
description: Use when the user asks for ETF, fund, or holdings weights. Follow the local CLI extraction path first, inspect the downloaded file or `data/temp/` artifacts, and answer with JSON ticker weights.
---

# Weights Extraction

Use this skill when the user wants ticker weights from an ETF or holdings source.

## Workflow

1. Run the local CLI path first.
2. Inspect the downloaded source file or the saved artifacts in `data/temp/` when the weights need
   verification.
3. Prefer evidence from the extracted file over assumptions from page text.
4. Respond with JSON ticker weights.

## Expected Operator Behavior

- Treat the CLI output as the first-pass answer.
- If the source semantics look ambiguous, inspect the downloaded file before answering.
- If `OLLAMA_URL` is available in the environment and the CLI flow supports it, treat that as the
  second semantic-validation layer.
- If `OLLAMA_URL` is not available, use the locally saved `data/temp/` artifacts for inspection.

## Response Shape

Return JSON of the form:

```json
{
  "TICKER": 1.23,
  "OTHER": 0.45
}
```

If confidence is low because the provider file uses unclear weight semantics, say that explicitly
and point to the inspected artifact.
