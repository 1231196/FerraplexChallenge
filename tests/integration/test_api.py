from fastapi.testclient import TestClient

from app.main import create_app, get_import_service, get_session_factory
from app.services.import_orders import OrderImportService
from tests.conftest import FakeExtractor, FakeFerrapexClient, make_email


def make_client(session_factory, catalog) -> TestClient:
    app = create_app()
    service = OrderImportService(
        client=FakeFerrapexClient([make_email(id="e1")], catalog),
        session_factory=session_factory,
        llm_extractor=FakeExtractor(),
    )
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_import_service] = lambda: service
    return TestClient(app)


def test_sync_then_list_orders(session_factory, catalog):
    client = make_client(session_factory, catalog)

    sync = client.post("/sync")
    assert sync.status_code == 200
    assert sync.json()["processed"] == 1

    orders = client.get("/orders").json()
    assert len(orders) == 1
    assert orders[0]["source_email_id"] == "e1"
    assert orders[0]["extraction_method"] == "deterministic"
    assert orders[0]["lines"][0] == {"product_reference": "PRF-AGL-40", "quantity": 1200}

    detail = client.get(f"/orders/{orders[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["requested_delivery_date"] == "2026-09-21"


def test_unknown_order_returns_404(session_factory, catalog):
    assert make_client(session_factory, catalog).get("/orders/999").status_code == 404
