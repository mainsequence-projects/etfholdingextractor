# Library Layout

The project is a normal Python library under `src/etfh_extractor`:

```text
src/
  etfh_extractor/
    __init__.py
    __main__.py
    exceptions.py
    models.py
    reader.py
```

## Public API

Import the library with:

```python
from etfh_extractor import ETFHoldingsReader, FundHoldings, Holding, extract_ticker_weights
```

The package exposes:

- `ETFHoldingsReader`: URL-based iShares extractor.
- `extract_ticker_weights(...)`: convenience function for one URL.
- `extract_many_ticker_weights(...)`: convenience function for multiple URLs.
- `FundHoldings`: parsed fund metadata plus holdings rows.
- `Holding`: one parsed holding row.

## What Changed

- The generic top-level Python package named `src` was removed as a public import.
- The old template `agents`, `api`, `dashboards`, and data-node scaffold files were removed.
- The library is now centered on iShares URL extraction rather than local file normalization.
- A CLI entry point is available as `etfh-read`.
