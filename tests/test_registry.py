from __future__ import annotations

import unittest

from etfh_extractor.exceptions import UnsupportedProviderError
from etfh_extractor.providers.registry import (
    build_provider,
    build_provider_from_url,
    supported_providers,
)


IVV_URL = "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf"


class ProviderRegistryTests(unittest.TestCase):
    def test_supported_providers_are_exposed_in_sorted_order(self) -> None:
        self.assertEqual(
            supported_providers(),
            ("invesco", "ishares", "state_street", "vanguard"),
        )

    def test_build_provider_normalizes_provider_name(self) -> None:
        provider = build_provider(" iShares ")

        self.assertEqual(provider.provider_name, "ishares")

    def test_build_provider_from_url_resolves_matching_provider(self) -> None:
        provider = build_provider_from_url(IVV_URL)

        self.assertEqual(provider.provider_name, "ishares")

    def test_build_provider_rejects_unsupported_provider(self) -> None:
        with self.assertRaisesRegex(UnsupportedProviderError, "Unsupported provider"):
            build_provider("unknown-provider")

    def test_build_provider_from_url_rejects_unsupported_url(self) -> None:
        with self.assertRaisesRegex(
            UnsupportedProviderError,
            "Only URLs for supported ETF providers are accepted right now",
        ):
            build_provider_from_url("https://example.com/funds/ivv")


if __name__ == "__main__":
    unittest.main()
