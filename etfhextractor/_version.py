from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("etfhextractor")
except PackageNotFoundError:  # not installed (e.g. running from a source checkout)
    __version__ = "0.0.0"

# Default HTTP User-Agent for provider fetches, derived from the package version
# so it never drifts from pyproject.toml.
DEFAULT_USER_AGENT = f"etfhextractor/{__version__}"
