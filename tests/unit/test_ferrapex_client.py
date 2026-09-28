import httpx
import pytest

from app.api.ferrapex_client import FerrapexClient

EMAILS_JSON = [
    {
        "id": "e1",
        "from": "compras@cliente.pt",
        "to": "encomendas@ferrapex.pt",
        "received_at": "2026-09-01T10:00:00Z",
        "subject": "Encomenda",
        "body": "Para entrega a 2026-09-21:\n\nPRF-AGL-40 | 1200",
        "attachments": [],
    }
]
CATALOG_CSV = "referencia,descricao,familia,unidade,preco_eur\nPRF-AGL-40,Parafuso aglomerado,Fixacao,un,0.031\n"


def make_client(handler) -> FerrapexClient:
    http = httpx.AsyncClient(base_url="https://api.test", transport=httpx.MockTransport(handler))
    return FerrapexClient(base_url="https://api.test", api_key="secret-key", http_client=http)


async def test_get_emails_sends_bearer_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=EMAILS_JSON)

    emails = await make_client(handler).get_emails()

    assert seen[0].headers["Authorization"] == "Bearer secret-key"
    assert seen[0].url.path == "/emails"
    assert emails[0].sender == "compras@cliente.pt"


async def test_get_catalog_parses_csv():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=CATALOG_CSV, headers={"content-type": "text/csv"})

    products = await make_client(handler).get_catalog()

    assert seen[0].headers["Authorization"] == "Bearer secret-key"
    assert seen[0].url.path == "/catalog"
    assert products[0].reference == "PRF-AGL-40"


async def test_http_errors_are_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(httpx.HTTPStatusError):
        await make_client(handler).get_emails()
