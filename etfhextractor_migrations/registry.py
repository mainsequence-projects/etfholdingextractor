from __future__ import annotations

from typing import Any

from mainsequence.meta_tables.migrations import build_metatable_model_registry

from msm.base import MarketsBase


def _metatable_model_sources() -> list[type[Any]]:
    from etfhextractor.markets_models import etfhextractor_metatable_provider_models

    return list(etfhextractor_metatable_provider_models())


def metatable_provider_models() -> list[type[Any]]:
    return build_metatable_model_registry(_metatable_model_sources(), base=MarketsBase)


__all__ = ["metatable_provider_models"]
