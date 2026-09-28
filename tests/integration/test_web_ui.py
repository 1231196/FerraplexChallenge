from fastapi.testclient import TestClient

from app.main import create_app, get_import_service, get_session_factory
from app.services.import_orders import OrderImportService
from tests.conftest import FakeExtractor, FakeFerrapexClient, make_email

REVIEW_BODY = "Para entrega a 2026-09-21:\nXXX-000-99 | 5\n"


def make_client(session_factory, catalog) -> TestClient:
    emails = [make_email(id="e1"), make_email(id="e2", body=REVIEW_BODY)]
    service = OrderImportService(
        client=FakeFerrapexClient(emails, catalog), session_factory=session_factory, llm_extractor=FakeExtractor()
    )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_import_service] = lambda: service
    return TestClient(app)


def test_home_page_renders_empty_state(session_factory, catalog):
    response = make_client(session_factory, catalog).get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Sincronizar" in response.text
    assert "Ainda não há encomendas" in response.text


def test_ui_sync_runs_import_and_shows_result(session_factory, catalog):
    response = make_client(session_factory, catalog).post("/ui/sync")

    assert response.status_code == 200
    assert 'data-testid="sync-processed">1<' in response.text
    assert 'data-testid="sync-needs-review">1<' in response.text


def test_home_lists_orders_with_status(session_factory, catalog):
    client = make_client(session_factory, catalog)
    client.post("/ui/sync")

    html = client.get("/").text

    assert "e1" in html and "e2" in html
    assert "processed" in html and "needs_review" in html


def test_order_detail_page_shows_lines_and_review_notes(session_factory, catalog):
    client = make_client(session_factory, catalog)
    client.post("/ui/sync")

    ok = client.get("/ui/orders/1").text
    assert "PRF-AGL-40" in ok and "1200" in ok and "2026-09-21" in ok

    review = client.get("/ui/orders/2").text
    assert "unknown_reference" in review


def test_unknown_order_page_returns_404(session_factory, catalog):
    assert make_client(session_factory, catalog).get("/ui/orders/999").status_code == 404


def test_emails_page_shows_processing_status(session_factory, catalog):
    client = make_client(session_factory, catalog)
    client.post("/ui/sync")

    html = client.get("/ui/emails").text

    assert "compras@cliente.pt" in html
    assert "needs_review" in html


def test_sync_error_is_shown_instead_of_crashing(session_factory, catalog):
    import httpx

    class BrokenClient(FakeFerrapexClient):
        async def get_catalog(self):
            raise httpx.ConnectError("API indisponível")

    service = OrderImportService(client=BrokenClient([], catalog), session_factory=session_factory, llm_extractor=FakeExtractor())
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_import_service] = lambda: service

    response = TestClient(app).post("/ui/sync")

    assert response.status_code == 502
    assert "API indisponível" in response.text


def test_customers_page_lists_customers_with_order_counts(session_factory, catalog):
    client = make_client(session_factory, catalog)
    client.post("/ui/sync")

    html = client.get("/ui/customers").text

    assert "compras@cliente.pt" in html
    assert 'href="/?customer=compras%40cliente.pt"' in html
    assert 'data-testid="orders-count">2<' in html


def test_home_can_filter_orders_by_customer(session_factory, catalog):
    client = make_client(session_factory, catalog)
    client.post("/ui/sync")

    assert "e1" in client.get("/", params={"customer": "compras@cliente.pt"}).text
    assert "Ainda não há encomendas" in client.get("/", params={"customer": "outro@x.pt"}).text


def test_customer_filter_works_with_plus_addresses(session_factory, catalog):
    service = OrderImportService(
        client=FakeFerrapexClient([make_email(id="e9", sender="compras+obra@cliente.pt")], catalog),
        session_factory=session_factory,
        llm_extractor=FakeExtractor(),
    )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_import_service] = lambda: service
    client = TestClient(app)
    client.post("/ui/sync")

    link = 'href="/?customer=compras%2Bobra%40cliente.pt"'
    assert link in client.get("/ui/customers").text
    assert "e9" in client.get("/?customer=compras%2Bobra%40cliente.pt").text
