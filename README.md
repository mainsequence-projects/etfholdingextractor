# etfh_extractor

`etfh_extractor` extracts ticker weights from iShares ETF fund pages.

## Installation

```bash
pip install -e .
```

## CLI

```bash
etfh-read https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf
```

That prints JSON like:

```json
{
  "AVGO": 5.4749,
  "MU": 5.71228,
  "NVDA": 5.09816
}
```

Use `--format full` to include fund metadata and the full parsed holdings rows.

## Python

```python
from etfh_extractor import ETFHoldingsReader

url = "https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf"
reader = ETFHoldingsReader()
fund = reader.read(url)

print(fund.fund_name)
print(fund.as_of_date)
print(fund.ticker_weights())
```

## What It Does

- Fetches the iShares fund page.
- Resolves the actual `Data Download` export link from the page HTML.
- Parses the holdings workbook.
- Returns ticker-to-weight JSON or a full holdings payload.

Additional documentation:

- [Library Layout](docs/library.md)
- [Reader Guide](docs/reader.md)
