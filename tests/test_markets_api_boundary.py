"""The library reaches Markets registries through `msm.api` row calls (ms-markets ADR 0047).

The application chooses the ms-markets row backend; the library never does. Under the remote
backend every registry read and write the library makes is one set-based call to the Markets
API, nothing Markets-owned is attached for registries, and no module compiles SQL on a Markets
table.

These tests select the remote backend with a recording fake, so they check exactly which
resource and operation each library call sends to Markets, offline.
"""

from __future__ import annotations

import ast
import datetime as dt
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "etfhextractor"
TODAY = dt.date(2026, 6, 10)


class RecordingBackend:
    """A remote row backend that records each call and answers from `responses`."""

    def __init__(self, responses: dict[tuple[str, str], Callable[[dict[str, Any]], Any]]):
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def call(self, resource: str, operation: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((resource, operation, arguments))
        try:
            respond = self.responses[(resource, operation)]
        except KeyError:
            raise AssertionError(f"unexpected Markets call {resource}/{operation}") from None
        return respond(arguments)

    def operations(self) -> list[tuple[str, str]]:
        return [(resource, operation) for resource, operation, _ in self.calls]


@pytest.fixture
def markets_api():
    """Select the remote backend for one test, as an application's composition root would."""
    from msm.api.remote import use_remote_backend, use_runtime_backend

    backends: list[RecordingBackend] = []

    def select(responses: dict[tuple[str, str], Callable[[dict[str, Any]], Any]]):
        backend = RecordingBackend(responses)
        backends.append(backend)
        use_remote_backend(backend)
        return backend

    try:
        yield select
    finally:
        use_runtime_backend()


@pytest.fixture
def no_engine(monkeypatch):
    """Fail if anything tries to attach the Markets runtime."""
    import msm
    import msm.bootstrap
    import msm_portfolios

    def refuse(**kwargs: Any) -> Any:
        raise AssertionError(f"start_engine called with {kwargs}")

    monkeypatch.setattr(msm, "start_engine", refuse)
    monkeypatch.setattr(msm.bootstrap, "start_engine", refuse)
    monkeypatch.setattr(msm_portfolios, "start_engine", refuse)


def _asset(unique_identifier: str) -> dict[str, Any]:
    return {"uid": str(uuid.uuid4()), "unique_identifier": unique_identifier, "asset_type": "equity"}


def _calendar(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = arguments.get("payload") or arguments
    return {
        "uid": str(uuid.uuid4()),
        "unique_identifier": payload.get("unique_identifier", "NYSE"),
        "display_name": payload.get("display_name", "calendar"),
        "calendar_type": "TRADING",
        "timezone": "UTC",
        "source": payload.get("source"),
        "source_identifier": payload.get("source_identifier"),
        "valid_from": str(payload.get("valid_from", TODAY)),
        "valid_to": str(payload.get("valid_to", TODAY)),
    }


def test_the_library_never_selects_the_row_backend() -> None:
    """Choosing the backend is the application's job: no package module does it."""
    selectors = {"use_remote_backend", "use_runtime_backend", "LazyRemoteBackend", "MarketsClient"}
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            names = set()
            if isinstance(node, ast.ImportFrom):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.Name | ast.Attribute):
                names = {getattr(node, "id", None) or getattr(node, "attr", None)}
            if names & selectors:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert offenders == []


def test_no_module_compiles_sql_on_a_markets_table() -> None:
    """No module builds a statement or calls a repository helper on a Markets table."""
    forbidden = {
        "search_model",
        "count_model",
        "bulk_upsert_model",
        "upsert_model",
        "create_model",
        "update_model",
        "delete_model",
        "get_model_by_uid",
        "get_model_by_unique_identifier",
        "materialize_calendar_rows",
        "execute_operation",
        "execute_markets_operation",
        "compile_markets_statement",
        "select",
    }
    found: set[tuple[str, str, str]] = set()
    paths = [*sorted(PACKAGE.rglob("*.py")), *sorted((REPO_ROOT / "examples").glob("*.py"))]
    for path in paths:
        tree = ast.parse(path.read_text())
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in forbidden:
                    found.add((path.name, function.name, name))
    assert found == set()


def test_registry_paths_attach_nothing_under_the_markets_api(markets_api, no_engine) -> None:
    from etfhextractor.mainsequence_categories import _ensure_msm_started

    markets_api({})

    assert _ensure_msm_started() is None


def test_category_sync_is_two_markets_calls(markets_api, no_engine) -> None:
    from etfhextractor.mainsequence_categories import sync_holdings_asset_category

    category_uid = str(uuid.uuid4())
    asset_uids = [uuid.uuid4(), uuid.uuid4()]
    backend = markets_api(
        {
            ("asset-category", "upsert"): lambda arguments: {
                "uid": category_uid,
                "unique_identifier": "HOLDINGS__IVV",
                "display_name": "HOLDINGS__IVV",
            },
            ("asset-category", "replace_memberships"): lambda arguments: [
                {"uid": str(uuid.uuid4()), "category_uid": category_uid, "asset_uid": str(uid)}
                for uid in arguments["asset_uids"]
            ],
        }
    )

    result = sync_holdings_asset_category(etf_ticker="ivv", asset_uids=[*asset_uids, asset_uids[0]])

    assert backend.operations() == [
        ("asset-category", "upsert"),
        ("asset-category", "replace_memberships"),
    ]
    assert backend.calls[1][2]["asset_uids"] == [str(uid) for uid in asset_uids]
    assert result.asset_uids == asset_uids


def _reference(identifier: str, ticker: str | None) -> dict[str, Any]:
    """An `AssetSnapshotReference` as the Markets API returns it."""
    return {
        "asset_uid": str(uuid.uuid5(uuid.NAMESPACE_URL, identifier)),
        "asset_identifier": identifier,
        "asset_type": "equity",
        "snapshot_time": None if ticker is None else "2026-05-01T00:00:00Z",
        "ticker": ticker,
    }


def test_ticker_resolution_is_one_latest_snapshot_read(markets_api, no_engine) -> None:
    from etfhextractor import mainsequence_categories

    backend = markets_api(
        {
            ("asset-snapshots", "latest"): lambda arguments: [
                _reference("AAPL_ID", "AAPL"),
                _reference("MSFT_ID", "MSFT"),
                # Carried NVDA once; its latest snapshot carries another ticker.
                _reference("OLD_NVDA_ID", "NVDA_OLD"),
            ],
        }
    )

    existing, missing, ambiguous = mainsequence_categories.resolve_existing_assets_by_ticker(
        component_symbols=["AAPL", "MSFT", "NVDA"]
    )
    identifiers, *_ = mainsequence_categories.resolve_asset_identifiers_by_ticker(
        component_symbols=["AAPL", "MSFT", "NVDA"]
    )

    assert existing == {
        "AAPL": uuid.uuid5(uuid.NAMESPACE_URL, "AAPL_ID"),
        "MSFT": uuid.uuid5(uuid.NAMESPACE_URL, "MSFT_ID"),
    }
    assert missing == ["NVDA"] and ambiguous == []
    assert identifiers == {"AAPL": "AAPL_ID", "MSFT": "MSFT_ID"}
    assert backend.operations() == [("asset-snapshots", "latest"), ("asset-snapshots", "latest")]
    assert backend.calls[0][2] == {"tickers": ["AAPL", "MSFT", "NVDA"]}


def test_figi_registration_writes_each_table_once(markets_api, no_engine) -> None:
    from etfhextractor import asset_registration

    figi_rows = [
        {
            "unique_identifier": figi,
            "figi": figi,
            "ticker": ticker,
            "name": f"{ticker} Inc.",
            "exchange_code": "US",
            "share_class": None,
            "raw_payload": {"figi": figi},
        }
        for ticker, figi in (("AAPL", "BBG000B9XRY4"), ("NVDA", "BBG000BBJQV0"), ("MSFT", "BBG000BPH459"))
    ]
    backend = markets_api(
        {
            ("asset", "get_many_by_unique_identifier"): lambda arguments: {
                "BBG000BPH459": _asset("BBG000BPH459")
            },
            ("asset-type", "upsert"): lambda arguments: {
                "uid": str(uuid.uuid4()),
                "asset_type": "equity",
                "display_name": "Equity",
            },
            ("asset", "upsert_many"): lambda arguments: [
                _asset(payload["unique_identifier"]) for payload in arguments["payloads"]
            ],
            ("open-figi-details", "upsert_many"): lambda arguments: [
                {"uid": payload["asset_uid"], "asset_uid": payload["asset_uid"]}
                for payload in arguments["payloads"]
            ],
            ("asset-snapshots", "latest"): lambda arguments: [
                # MSFT is registered and resolvable; NVDA exists without a snapshot.
                _reference(identifier, "MSFT" if identifier == "BBG000BPH459" else None)
                for identifier in arguments["asset_identifiers"]
                if identifier in {"BBG000BPH459"}
            ],
            ("asset-snapshots", "publish"): lambda arguments: len(arguments["snapshots"]),
        }
    )

    with patch("msm.services.assets.openfigi.query_figi", return_value=figi_rows):
        result = asset_registration.register_equity_assets_from_tickers(
            tickers=["AAPL", "NVDA", "MSFT"],
            snapshot_time=dt.datetime(2026, 6, 10, tzinfo=dt.UTC),
        )

    assert result.registered_figi_by_ticker == {"AAPL": "BBG000B9XRY4", "NVDA": "BBG000BBJQV0"}
    assert result.already_registered_figi_by_ticker == {"MSFT": "BBG000BPH459"}
    assert backend.operations() == [
        ("asset", "get_many_by_unique_identifier"),
        ("asset-snapshots", "latest"),
        ("asset-type", "upsert"),
        ("asset", "upsert_many"),
        ("open-figi-details", "upsert_many"),
        ("asset-snapshots", "publish"),
    ]
    arguments = {(resource, operation): args for resource, operation, args in backend.calls}
    assert arguments[("asset-snapshots", "latest")] == {
        "asset_identifiers": ["BBG000B9XRY4", "BBG000BBJQV0", "BBG000BPH459"]
    }
    assert [p["unique_identifier"] for p in arguments[("asset", "upsert_many")]["payloads"]] == [
        "BBG000B9XRY4",
        "BBG000BBJQV0",
    ]
    assert [row["ticker"] for row in arguments[("asset-snapshots", "publish")]["snapshots"]] == [
        "AAPL",
        "NVDA",
    ]


def test_always_open_calendar_is_four_markets_calls(markets_api, no_engine) -> None:
    from etfhextractor.calendars import ensure_trading_calendar

    backend = markets_api(
        {
            ("calendar", "filter"): lambda arguments: [],
            ("calendar", "upsert"): _calendar,
            ("calendar-date", "upsert_many"): lambda arguments: [],
            ("calendar-session", "upsert_many"): lambda arguments: [],
        }
    )

    calendar = ensure_trading_calendar("24/7", backtest_start_days=60, today=TODAY)

    assert calendar.unique_identifier == "24/7"
    assert backend.operations() == [
        ("calendar", "filter"),
        ("calendar", "upsert"),
        ("calendar-date", "upsert_many"),
        ("calendar-session", "upsert_many"),
    ]
    dates = backend.calls[2][2]["payloads"]
    assert len(dates) == len(backend.calls[3][2]["payloads"]) > 400
    assert {row["calendar_uid"] for row in dates} == {str(calendar.uid)}


def test_market_calendars_are_materialized_by_markets(markets_api, no_engine) -> None:
    from etfhextractor.calendars import ensure_trading_calendar

    backend = markets_api(
        {
            ("calendar", "filter"): lambda arguments: [],
            ("calendar", "create_from_pandas_calendar"): _calendar,
        }
    )

    ensure_trading_calendar("NYSE", backtest_start_days=60, today=TODAY)

    assert backend.operations() == [("calendar", "filter"), ("calendar", "create_from_pandas_calendar")]


def test_portfolio_runtime_attaches_no_registry_under_the_markets_api(markets_api) -> None:
    from msm_portfolios.time_index.portfolios.storage import (
        PortfolioRebalanceStateStorage,
        PortfoliosStorage,
        PortfolioWeightsStorage,
    )
    from msm_portfolios.time_index.signals.storage import SignalWeightsStorage

    from etfhextractor.markets_models import DemoBarsStorage
    from etfhextractor.portfolio_publish import portfolio_runtime_models

    markets_api({})

    assert portfolio_runtime_models([DemoBarsStorage]) == [
        SignalWeightsStorage,
        PortfolioWeightsStorage,
        PortfolioRebalanceStateStorage,
        PortfoliosStorage,
        DemoBarsStorage,
    ]


def test_portfolio_runtime_keeps_todays_tables_on_the_runtime_backend() -> None:
    from etfhextractor.portfolio_publish import portfolio_runtime_models

    names = {model.__name__ for model in portfolio_runtime_models()}

    assert {
        "AssetTable",
        "PortfolioTable",
        "CalendarTable",
        "CalendarDateTable",
        "CalendarSessionTable",
        "OpenFigiAssetDetailsTable",
        "AssetCategoryTable",
        "AssetCategoryMembershipTable",
        "AssetSnapshotsStorage",
        "SignalWeightsStorage",
        "PortfoliosStorage",
    } <= names


def test_injected_instances_leave_no_markets_table_attached(markets_api) -> None:
    """With every series bound to the application's instances, a publish on the Markets API
    attaches only the application's tables."""
    from etfhextractor.portfolio_publish import portfolio_runtime_models

    signal, weights, rebalance, values = (
        type(name, (), {}) for name in ("Signal", "Weights", "Rebalance", "Values")
    )
    markets_api({})

    assert portfolio_runtime_models(
        signal_output_table=signal,
        weights_output_table=weights,
        rebalance_output_table=rebalance,
        portfolio_output_table=values,
    ) == [signal, weights, rebalance, values]


def test_injected_instances_join_todays_tables_on_the_runtime_backend() -> None:
    from etfhextractor.portfolio_publish import portfolio_runtime_models

    values = type("Values", (), {})
    models = portfolio_runtime_models(portfolio_output_table=values)

    assert values in models
    assert "PortfoliosStorage" in {model.__name__ for model in models}


def test_a_signal_only_instance_is_one_catalog_call(markets_api) -> None:
    from etfhextractor.portfolio_publish import register_signal_dataset

    class SignalInstance:
        @staticmethod
        def get_meta_table_uid() -> str:
            return "signal-instance-uid"

    backend = markets_api(
        {
            ("portfolio-datasets", "register_signal"): lambda arguments: dict(
                arguments["registration"]
            ),
        }
    )

    registration = register_signal_dataset(
        signal_uid="ivv-signal", signal_output_table=SignalInstance
    )

    assert backend.calls == [
        (
            "portfolio-datasets",
            "register_signal",
            {
                "registration": {
                    "signal_uid": "ivv-signal",
                    "signal_meta_table_uid": "signal-instance-uid",
                }
            },
        )
    ]
    assert registration.signal_meta_table_uid == "signal-instance-uid"
