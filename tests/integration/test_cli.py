from contextlib import asynccontextmanager

import httpx
import pytest
from pydantic import ValidationError

from app import cli
from app.config import Settings
from app.services.import_orders import OrderImportService
from tests.conftest import FakeExtractor, FakeFerrapexClient, make_email


@pytest.fixture
def wired(monkeypatch, session_factory, catalog):
    """Liga o CLI a uma BD em memória e a uma API falsa; regista chamadas a uvicorn/browser."""
    state = {"client": FakeFerrapexClient([make_email(id="e1")], catalog), "served": [], "opened": []}

    @asynccontextmanager
    async def fake_import_service(_session_factory):
        yield OrderImportService(client=state["client"], session_factory=session_factory, llm_extractor=FakeExtractor())

    monkeypatch.setattr(cli, "get_settings", lambda: None)
    monkeypatch.setattr(cli, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(cli, "import_service", fake_import_service)
    monkeypatch.setattr(cli, "run_server", lambda host, port: state["served"].append((host, port)))
    monkeypatch.setattr(cli, "open_browser", lambda url: state["opened"].append(url))
    return state


def test_sync_command_imports_and_prints_summary(wired, capsys):
    assert cli.main(["sync"]) == 0

    out = capsys.readouterr().out
    assert "processadas: 1" in out


def test_orders_command_lists_saved_orders(wired, capsys):
    cli.main(["sync"])
    capsys.readouterr()

    assert cli.main(["orders"]) == 0

    out = capsys.readouterr().out
    assert "e1" in out and "processed" in out and "2026-09-21" in out
    assert "PRF-AGL-40 x 1200" in out


def test_default_command_syncs_then_serves_and_opens_browser(wired, capsys):
    assert cli.main([]) == 0

    assert "processadas: 1" in capsys.readouterr().out
    assert wired["served"] == [("127.0.0.1", 8000)]
    assert wired["opened"] == ["http://127.0.0.1:8000"]


def test_default_command_still_serves_when_api_is_unreachable(wired, capsys):
    class Down(FakeFerrapexClient):
        async def get_catalog(self):
            raise httpx.ConnectError("sem rede")

    wired["client"] = Down([], [])

    assert cli.main(["--no-browser"]) == 0

    assert "Não foi possível contactar a API" in capsys.readouterr().err
    assert wired["served"] and not wired["opened"]


def test_expired_key_gives_clear_message(wired, capsys):
    class Unauthorized(FakeFerrapexClient):
        async def get_catalog(self):
            request = httpx.Request("GET", "https://api.test/catalog")
            raise httpx.HTTPStatusError("401", request=request, response=httpx.Response(401, request=request))

    wired["client"] = Unauthorized([], [])

    assert cli.main(["sync"]) == 1
    assert "chave inválida ou expirada" in capsys.readouterr().err


def test_missing_configuration_gives_clear_message(wired, monkeypatch, capsys):
    def no_config():
        return Settings(_env_file=None)

    monkeypatch.delenv("FERRAPEX_API_KEY", raising=False)
    monkeypatch.delenv("FERRAPEX_API_BASE_URL", raising=False)
    monkeypatch.setattr(cli, "get_settings", no_config)

    assert cli.main([]) == 2

    err = capsys.readouterr().err
    assert ".env" in err and "FERRAPEX_API_KEY" in err
    assert wired["served"] == []


def test_orders_command_filters_by_customer(wired, capsys):
    cli.main(["sync"])
    capsys.readouterr()

    cli.main(["orders", "--customer", "outro@x.pt"])
    assert "Ainda não há encomendas" in capsys.readouterr().out

    cli.main(["orders", "--customer", "compras@cliente.pt"])
    assert "e1" in capsys.readouterr().out
