# Reader Guide

The reader is the extraction surface of this library.

Its job is narrow:

1. fetch provider-published ETF holdings data
2. normalize it into authoritative `FundHoldings`

## Supported Providers

The current provider registry supports:

- `ishares`
- `invesco`
- `vanguard`
- `state_street`

## Input Modes

The reader supports two input modes.

### 1. Direct fund URL

Use a provider fund page URL when you have it. The provider is inferred from the URL.

```text
https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf
```

### 2. Explicit provider plus ticker

Use `(provider, ticker)` when you do not have the fund URL.

Ticker-only calls must provide `provider`. Provider inference is supported from URLs, not from ETF
tickers.

## Behavior

For every supported provider, the reader:

1. resolves the provider implementation
2. fetches the provider source page or file
3. parses provider-specific source data into `Holding` rows
4. returns a `FundHoldings` object as the canonical result
5. optionally persists debug artifacts for inspection under `data/temp/`

Artifact persistence is a support feature for debugging extraction. It is not a separate library
responsibility.

## Python Examples

### Read from a fund URL

```python
from etfh_extractor import ETFHoldingsReader

reader = ETFHoldingsReader(timeout=30.0)
fund = reader.read(
    "https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf"
)

print(fund.fund_name)
print(fund.ticker_weights())
print(fund.artifact_directory)
```

### Read from provider plus ticker

```python
from etfh_extractor import ETFHoldingsReader

reader = ETFHoldingsReader(timeout=30.0)
fund = reader.read_ticker("IVV", provider="ishares")

print(fund.url)
print(fund.holdings[0].ticker, fund.holdings[0].weight)
```

### Override the artifact root

```python
from pathlib import Path

from etfh_extractor import ETFHoldingsReader

reader = ETFHoldingsReader(artifact_root=Path("tmp/etf-artifacts"))
fund = reader.read_ticker("IVV", provider="ishares")

print(fund.artifact_directory)
```

## CLI Examples

### Extraction from URL

```bash
etfh extract-url https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf
etfh extract-url https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf --format full
```

```json
{
  "AAPL": 7.12,
  "MSFT": 6.84,
  "NVDA": 6.21
}
```

### Extraction from ticker plus provider

```bash
etfh extract-ticker --provider ishares --ticker IVV
etfh extract-ticker --provider ishares --ticker IVV --format full
```

```json
{
  "AAPL": 7.12,
  "MSFT": 6.84,
  "NVDA": 6.21
}
```

### Legacy extraction entrypoint

```bash
etfh-read https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf
python -m etfh_extractor --provider ishares --ticker IVV
```

## Output Contract

`ETFHoldingsReader.read(...)` and `ETFHoldingsReader.read_ticker(...)` always return
`FundHoldings`. Symbol-only outputs are derived views of that model, not a separate source of
truth.

## Boundary

The reader does not:

- register assets
- resolve FIGIs
- sync MainSequence categories
- run downstream execution workflows

Category registration lives in [mainsequence_categories.py](/Users/jose/mainsequence/main-sequence-workbench/projects/etfholdingextractor-161/src/etfh_extractor/mainsequence_categories.py).
