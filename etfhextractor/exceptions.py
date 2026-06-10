class ETFHoldingsError(Exception):
    """Base exception for ETF holdings extraction failures."""


class UnsupportedProviderError(ETFHoldingsError):
    """Raised when a fund URL does not point to a supported provider."""


class FetchError(ETFHoldingsError):
    """Raised when a fund page or holdings export cannot be fetched."""


class DownloadLinkNotFoundError(ETFHoldingsError):
    """Raised when the iShares fund page does not expose a holdings download link."""


class WorkbookParseError(ETFHoldingsError):
    """Raised when the downloaded iShares holdings workbook cannot be parsed."""
