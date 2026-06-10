from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import FundHoldings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "data" / "temp"
ARTIFACT_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"


@dataclass(frozen=True, slots=True)
class ArtifactPayload:
    filename: str
    content: str | bytes


def _slugify(value: str) -> str:
    token = re.sub(r"[^0-9a-zA-Z]+", "-", value.strip().lower())
    token = re.sub(r"-+", "-", token).strip("-")
    return token or "etf"


def _build_artifact_label(
    *,
    requested_ticker: str | None,
    fund_holdings: FundHoldings,
) -> str:
    if requested_ticker:
        return _slugify(requested_ticker)

    parsed_url = urlparse(fund_holdings.url)
    url_slug = parsed_url.path.rstrip("/").split("/")[-1]
    if url_slug:
        return _slugify(url_slug)

    if fund_holdings.fund_name:
        return _slugify(fund_holdings.fund_name)

    return "etf"


def _holdings_csv_text(fund_holdings: FundHoldings) -> str:
    fieldnames = [
        "ticker",
        "name",
        "weight",
        "sector",
        "asset_class",
        "market_value",
        "notional_value",
        "quantity",
        "price",
        "location",
        "exchange",
        "currency",
        "fx_rate",
        "accrual_date",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for holding in fund_holdings.holdings:
        writer.writerow(holding.to_dict())
    return buffer.getvalue()


def _write_artifact_file(path: Path, content: str | bytes) -> None:
    if isinstance(content, bytes):
        path.write_bytes(content)
        return
    path.write_text(content, encoding="utf-8")


def persist_extraction_artifacts(
    *,
    provider_name: str,
    fund_holdings: FundHoldings,
    source_artifacts: list[ArtifactPayload],
    requested_ticker: str | None = None,
    artifact_root: Path | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> FundHoldings:
    active_artifact_root = artifact_root or DEFAULT_ARTIFACT_ROOT
    active_artifact_root.mkdir(parents=True, exist_ok=True)

    persisted_at = datetime.now(timezone.utc)
    persisted_at_str = persisted_at.strftime(ARTIFACT_TIMESTAMP_FORMAT)
    artifact_label = _build_artifact_label(
        requested_ticker=requested_ticker,
        fund_holdings=fund_holdings,
    )
    artifact_hash = hashlib.sha1(
        "\n".join(
            [
                provider_name,
                requested_ticker or "",
                fund_holdings.url,
                fund_holdings.download_url,
                fund_holdings.fund_name,
                fund_holdings.as_of_date,
            ]
        ).encode("utf-8")
    ).hexdigest()[:8]
    artifact_dir = active_artifact_root / (
        f"{persisted_at_str}_{provider_name}_{artifact_label}_{artifact_hash}"
    )
    artifact_dir.mkdir(parents=True, exist_ok=False)

    persisted_fund_holdings = fund_holdings.with_artifact_directory(str(artifact_dir))

    for artifact in source_artifacts:
        _write_artifact_file(artifact_dir / artifact.filename, artifact.content)

    _write_artifact_file(
        artifact_dir / "holdings.csv",
        _holdings_csv_text(persisted_fund_holdings),
    )
    _write_artifact_file(
        artifact_dir / "weights.json",
        json.dumps(persisted_fund_holdings.ticker_weights(), indent=2, sort_keys=True),
    )
    _write_artifact_file(
        artifact_dir / "fund_holdings.json",
        json.dumps(persisted_fund_holdings.to_dict(), indent=2, sort_keys=True),
    )

    metadata = {
        "artifact_version": 1,
        "persisted_at_utc": persisted_at_str,
        "provider_name": provider_name,
        "requested_ticker": requested_ticker,
        "fund_name": persisted_fund_holdings.fund_name,
        "as_of_date": persisted_fund_holdings.as_of_date,
        "source_url": persisted_fund_holdings.url,
        "download_url": persisted_fund_holdings.download_url,
        "artifact_directory": persisted_fund_holdings.artifact_directory,
        "parser_mode": "deterministic",
        "source_artifact_filenames": [artifact.filename for artifact in source_artifacts],
        "generated_artifact_filenames": [
            "holdings.csv",
            "weights.json",
            "fund_holdings.json",
            "metadata.json",
        ],
    }
    if metadata_extra:
        metadata.update(metadata_extra)
    _write_artifact_file(
        artifact_dir / "metadata.json",
        json.dumps(metadata, indent=2, sort_keys=True),
    )

    return persisted_fund_holdings
