# Reader Guide

`etfh_extractor` reads iShares fund page URLs and returns holdings data.

## Supported Input

Right now the reader supports iShares fund pages such as:

```text
https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf
```

## Behavior

- The reader fetches the fund page HTML.
- It extracts the `Data Download` link from the page.
- It downloads the iShares holdings workbook.
- It parses the `Holdings` worksheet into `Holding` objects.
- It can return just `ticker -> weight` or the full parsed payload.

## Example

```python
from etfh_extractor import ETFHoldingsReader

reader = ETFHoldingsReader(timeout=30.0)
fund = reader.read("https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf")

print(fund.ticker_weights())
print(fund.holdings[0].ticker, fund.holdings[0].weight)
```

## CLI

```bash
etfh-read https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf
python -m etfh_extractor https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf --format full
```
