from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .mainsequence_categories import (
    build_holdings_asset_category_plan,
    sync_holdings_asset_category,
)
from .reader import ETFHoldingsReader


SUBCOMMAND_NAMES = {
    "extract-url",
    "extract-ticker",
    "category-plan",
    "category-sync",
}


def _add_compact_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty JSON.",
    )


def _add_timeout_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds.",
    )


def _add_output_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("weights", "full"),
        default="weights",
        help="Return only ticker weights or the full parsed payload.",
    )


def build_subcommand_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ETF holdings extraction and MainSequence holdings-category CLI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_url_parser = subparsers.add_parser(
        "extract-url",
        help="Extract holdings from one or more provider fund URLs.",
    )
    extract_url_parser.add_argument(
        "urls",
        nargs="+",
        help="One or more supported ETF fund page URLs.",
    )
    _add_output_format_arg(extract_url_parser)
    _add_timeout_arg(extract_url_parser)
    _add_compact_arg(extract_url_parser)

    extract_ticker_parser = subparsers.add_parser(
        "extract-ticker",
        help="Extract holdings from one or more ETF tickers plus an explicit provider.",
    )
    extract_ticker_parser.add_argument(
        "--ticker",
        dest="tickers",
        action="append",
        required=True,
        help="ETF ticker to resolve through the provider layer. Repeat for multiple tickers.",
    )
    extract_ticker_parser.add_argument(
        "--provider",
        required=True,
        help="Explicit provider for ticker-based workflows.",
    )
    _add_output_format_arg(extract_ticker_parser)
    _add_timeout_arg(extract_ticker_parser)
    _add_compact_arg(extract_ticker_parser)

    category_plan_parser = subparsers.add_parser(
        "category-plan",
        help="Build a MainSequence holdings-category plan from ETF holdings.",
    )
    category_plan_parser.add_argument(
        "--ticker",
        required=True,
        help="ETF ticker used for the HOLDINGS__<ETF> category identifier.",
    )
    category_plan_parser.add_argument(
        "--fund-url",
        help="Supported ETF fund URL. If omitted, --provider is required.",
    )
    category_plan_parser.add_argument(
        "--provider",
        help="Explicit provider. If omitted, the provider is inferred from --fund-url.",
    )
    _add_timeout_arg(category_plan_parser)
    _add_compact_arg(category_plan_parser)

    category_sync_parser = subparsers.add_parser(
        "category-sync",
        help="Extract holdings, build a category plan, and sync the category when there are no blockers.",
    )
    category_sync_parser.add_argument(
        "--ticker",
        required=True,
        help="ETF ticker used for the HOLDINGS__<ETF> category identifier.",
    )
    category_sync_parser.add_argument(
        "--fund-url",
        help="Supported ETF fund URL. If omitted, --provider is required.",
    )
    category_sync_parser.add_argument(
        "--provider",
        help="Explicit provider. If omitted, the provider is inferred from --fund-url.",
    )
    _add_timeout_arg(category_sync_parser)
    _add_compact_arg(category_sync_parser)

    return parser


def build_legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract ETF holdings weights from supported fund URLs or from provider+ticker inputs."
        )
    )
    parser.add_argument("urls", nargs="*", help="One or more supported ETF fund page URLs.")
    parser.add_argument(
        "--ticker",
        dest="tickers",
        action="append",
        default=[],
        help="ETF ticker to resolve through the provider layer. Repeat for multiple tickers.",
    )
    parser.add_argument(
        "--provider",
        help="Explicit provider for --ticker workflows. Required when using --ticker.",
    )
    _add_output_format_arg(parser)
    _add_timeout_arg(parser)
    _add_compact_arg(parser)
    return parser


def _serialize_url_results(
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


def _serialize_ticker_results(
    reader: ETFHoldingsReader,
    tickers: Sequence[str],
    *,
    provider: str | None,
    output_format: str,
) -> dict[str, object] | dict[str, float]:
    if len(tickers) == 1:
        result = reader.read_ticker(tickers[0], provider=provider)
        if output_format == "full":
            return result.to_dict()
        return result.ticker_weights()

    payload: dict[str, object] = {}
    for ticker in tickers:
        result = reader.read_ticker(ticker, provider=provider)
        normalized_ticker = ticker.strip().upper()
        if output_format == "full":
            payload[normalized_ticker] = result.to_dict()
        else:
            payload[normalized_ticker] = result.ticker_weights()
    return payload


def _serialize_category_plan_result(plan) -> dict[str, object]:
    payload = plan.summary()
    payload["has_blockers"] = plan.has_blockers()
    return payload


def _serialize_category_sync_result(
    *,
    plan,
    sync_result=None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan": _serialize_category_plan_result(plan),
        "synced": sync_result is not None,
    }
    if sync_result is None:
        payload["sync_result"] = None
    else:
        payload["sync_result"] = {
            "unique_identifier": sync_result.unique_identifier,
            "display_name": sync_result.display_name,
            "asset_ids": sync_result.asset_ids,
        }
    return payload


def _print_json(payload: object, *, compact: bool) -> None:
    json_kwargs = {"sort_keys": True}
    if not compact:
        json_kwargs["indent"] = 2
    print(json.dumps(payload, **json_kwargs))


def _build_category_read_holdings_fn(
    reader: ETFHoldingsReader | None,
    *,
    fund_url: str | None,
):
    if reader is None:
        return None

    if fund_url is not None:
        return lambda identifier, provider=None: reader.read(identifier)

    return lambda identifier, provider=None: reader.read_ticker(identifier, provider=provider)


def _run_subcommand(
    argv: Sequence[str],
    *,
    reader: ETFHoldingsReader | None = None,
) -> int:
    args = build_subcommand_parser().parse_args(argv)

    if args.command == "extract-url":
        active_reader = reader or ETFHoldingsReader(timeout=args.timeout)
        payload = _serialize_url_results(active_reader, args.urls, args.format)
        _print_json(payload, compact=args.compact)
        return 0

    if args.command == "extract-ticker":
        active_reader = reader or ETFHoldingsReader(timeout=args.timeout)
        payload = _serialize_ticker_results(
            active_reader,
            args.tickers,
            provider=args.provider,
            output_format=args.format,
        )
        _print_json(payload, compact=args.compact)
        return 0

    if args.fund_url is None and args.provider is None:
        raise SystemExit(
            "Category commands require --fund-url or --provider. "
            "If you do not pass --fund-url, pass --provider explicitly."
        )

    read_holdings_fn = _build_category_read_holdings_fn(
        reader,
        fund_url=args.fund_url,
    )
    plan = build_holdings_asset_category_plan(
        etf_ticker=args.ticker,
        fund_url=args.fund_url,
        component_provider=args.provider,
        timeout=args.timeout,
        read_holdings_fn=read_holdings_fn,
    )

    if args.command == "category-plan":
        _print_json(_serialize_category_plan_result(plan), compact=args.compact)
        return 0

    if plan.has_blockers():
        _print_json(
            _serialize_category_sync_result(plan=plan, sync_result=None),
            compact=args.compact,
        )
        return 1

    sync_result = sync_holdings_asset_category(
        etf_ticker=args.ticker,
        asset_ids=list(plan.existing_asset_ids_by_symbol.values()),
    )
    _print_json(
        _serialize_category_sync_result(plan=plan, sync_result=sync_result),
        compact=args.compact,
    )
    return 0


def _run_legacy_cli(
    argv: Sequence[str],
    *,
    reader: ETFHoldingsReader | None = None,
) -> int:
    args = build_legacy_parser().parse_args(argv)
    if not args.urls and not args.tickers:
        raise SystemExit("Pass one or more fund URLs or one or more --ticker values.")
    if args.urls and args.tickers:
        raise SystemExit("Pass either fund URLs or --ticker values, not both.")
    if args.provider and not args.tickers:
        raise SystemExit("--provider can only be used with --ticker.")
    if args.tickers and not args.provider:
        raise SystemExit(
            "--ticker requires --provider. Provider inference is supported from URLs only."
        )

    active_reader = reader or ETFHoldingsReader(timeout=args.timeout)
    if args.tickers:
        payload = _serialize_ticker_results(
            active_reader,
            args.tickers,
            provider=args.provider,
            output_format=args.format,
        )
    else:
        payload = _serialize_url_results(active_reader, args.urls, args.format)
    _print_json(payload, compact=args.compact)
    return 0


def main(
    argv: Sequence[str] | None = None,
    reader: ETFHoldingsReader | None = None,
) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if effective_argv and effective_argv[0] in SUBCOMMAND_NAMES:
        return _run_subcommand(effective_argv, reader=reader)
    return _run_legacy_cli(effective_argv, reader=reader)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
