"""How this library reaches MainSequence Markets (ms-markets ADR 0047).

The library never chooses the ms-markets row backend; the application that imports it does,
once, at its composition root:

- **runtime** (the ms-markets default): `msm.api` row calls compile SQL against Markets tables
  attached in this process. The helpers below attach the Markets tables the library uses, once
  per process, exactly as earlier releases did.
- **remote** (`msm.api.remote.use_remote_backend(msm.client.LazyRemoteBackend())`, or
  `MSM_API_BACKEND=remote`): every `msm.api` row call (assets, OpenFIGI details, asset types,
  asset categories, calendars, portfolios, signal metadata, the portfolio dataset catalog,
  asset-snapshot publication) runs on the Markets API, so nothing is attached for them and the
  application needs no grant on the `mainsequence.markets` namespace for them.

One read has no Markets API route yet: asset snapshots by ticker or by asset identifier (the
ticker resolver and the FIGI-registration snapshot check). It keeps running on a runtime that
holds `AssetSnapshotsStorage` under both backends (`snapshot_context`).

Every helper imports ms-markets lazily, so importing this module stays platform-free.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def markets_api_selected() -> bool:
    """Whether the application selected the ms-markets remote row backend.

    Reads the choice; never makes it.
    """
    from msm.api.remote import active_remote_backend

    return active_remote_backend() is not None


def attach_markets_runtime(models: Sequence[Any], *, row_model_name: str) -> Any:
    """Reuse the process runtime when it already holds `models`, else start it with them.

    A process gets one `msm.start_engine` configuration; an application that attaches its own
    runtime first must include `models` in it.
    """
    from msm import start_engine
    from msm.bootstrap import resolve_runtime

    try:
        return resolve_runtime(models=list(models), row_model_name=row_model_name)
    except RuntimeError:
        return start_engine(models=list(models))


def registry_runtime(models: Sequence[Any], *, row_model_name: str) -> Any | None:
    """The runtime registry row calls need: `None` under the remote backend."""
    if markets_api_selected():
        return None
    return attach_markets_runtime(models, row_model_name=row_model_name)


def remote_snapshot_context(*, row_model_name: str) -> Any:
    """Repository context holding `AssetSnapshotsStorage` for a remote-backend process.

    Reuses the application's runtime when it attached the table, otherwise attaches the table
    alone with `msm.bootstrap.attach_schemas`, which does not compete with the application's
    `start_engine`. The workload needs read access to the table (and to the Asset table it
    references); this is the one direct Markets read left (see the module docstring).
    """
    from msm.bootstrap import attach_schemas, resolve_runtime
    from msm.time_index.assets.storage import AssetSnapshotsStorage

    try:
        return resolve_runtime(
            models=[AssetSnapshotsStorage], row_model_name=row_model_name
        ).context
    except RuntimeError:
        return attach_schemas(models=[AssetSnapshotsStorage]).context


__all__ = [
    "attach_markets_runtime",
    "markets_api_selected",
    "registry_runtime",
    "remote_snapshot_context",
]
