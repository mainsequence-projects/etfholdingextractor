from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..exceptions import UnsupportedProviderError
from ..settings import normalize_provider_name
from .base import HoldingsProvider
from .invesco import InvescoHoldingsProvider
from .ishares import IsharesHoldingsProvider
from .state_street import StateStreetHoldingsProvider
from .vanguard import VanguardHoldingsProvider


PROVIDER_TYPES_BY_NAME = {
    "invesco": InvescoHoldingsProvider,
    "ishares": IsharesHoldingsProvider,
    "state_street": StateStreetHoldingsProvider,
    "vanguard": VanguardHoldingsProvider,
}


def supported_providers() -> tuple[str, ...]:
    return tuple(sorted(PROVIDER_TYPES_BY_NAME))


def infer_provider_name_from_url(url: str) -> str:
    return build_provider_from_url(url).provider_name


def build_provider(
    provider: str,
    *,
    timeout: float = 30.0,
    fetcher: Callable[[str], str] | None = None,
    binary_fetcher: Callable[[str], bytes] | None = None,
    artifact_root: Path | None = None,
    user_agent: str = "etfh-extractor/0.1.0",
) -> HoldingsProvider:
    normalized_provider = normalize_provider_name(provider)
    provider_type = PROVIDER_TYPES_BY_NAME.get(normalized_provider)
    if provider_type is None:
        supported = ", ".join(supported_providers())
        raise UnsupportedProviderError(
            f"Unsupported provider: {provider!r}. Supported providers: {supported}."
        )

    return provider_type(
        timeout=timeout,
        fetcher=fetcher,
        binary_fetcher=binary_fetcher,
        artifact_root=artifact_root,
        user_agent=user_agent,
    )


def build_provider_from_url(
    url: str,
    *,
    timeout: float = 30.0,
    fetcher: Callable[[str], str] | None = None,
    binary_fetcher: Callable[[str], bytes] | None = None,
    artifact_root: Path | None = None,
    user_agent: str = "etfh-extractor/0.1.0",
) -> HoldingsProvider:
    for provider_type in PROVIDER_TYPES_BY_NAME.values():
        if provider_type.supports_url(url):
            return provider_type(
                timeout=timeout,
                fetcher=fetcher,
                binary_fetcher=binary_fetcher,
                artifact_root=artifact_root,
                user_agent=user_agent,
            )

    supported = ", ".join(supported_providers())
    raise UnsupportedProviderError(
        "Only URLs for supported ETF providers are accepted right now. "
        f"Supported providers: {supported}."
    )
