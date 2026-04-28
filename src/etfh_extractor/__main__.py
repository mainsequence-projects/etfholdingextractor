from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .reader import ETFHoldingsReader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract ticker weights from one or more iShares ETF fund URLs."
    )
    parser.add_argument("urls", nargs="+", help="One or more iShares fund page URLs.")
    parser.add_argument(
        "--format",
        choices=("weights", "full"),
        default="weights",
        help="Return only ticker weights or the full parsed payload.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty JSON.",
    )
    return parser


def _serialize_results(
    reader: ETFHoldingsReader,
    urls: Sequence[str],
    output_format: str,
) -> dict[str, object] | dict[str, float]:
    if len(urls) == 1:
        result = reader.read(urls[0])
        if output_format == "full":
            return result.to_dict()
        return result.ticker_weights()

    results = reader.read_many(urls)
    if output_format == "full":
        return {result.url: result.to_dict() for result in results}
    return {result.url: result.ticker_weights() for result in results}


def main(
    argv: Sequence[str] | None = None,
    reader: ETFHoldingsReader | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    active_reader = reader or ETFHoldingsReader(timeout=args.timeout)
    payload = _serialize_results(active_reader, args.urls, args.format)
    json_kwargs = {"sort_keys": True}
    if not args.compact:
        json_kwargs["indent"] = 2
    print(json.dumps(payload, **json_kwargs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
