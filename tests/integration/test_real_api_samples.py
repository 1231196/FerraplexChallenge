"""Pipeline completo com os dados de exemplo reais da API (guardados em tests/fixtures)."""

import json
from datetime import date
from pathlib import Path

from app.api.ferrapex_client import parse_catalog_csv
from app.domain.email import Email
from app.persistence.repositories import OrderRepository
from app.services.import_orders import OrderImportService
from tests.conftest import FakeExtractor, FakeFerrapexClient

FIXTURES = Path(__file__).parents[1] / "fixtures"


async def test_sample_emails_are_all_processed_deterministically(session_factory):
    catalog = parse_catalog_csv((FIXTURES / "catalog.csv").read_text())
    emails = [Email.model_validate(e) for e in json.loads((FIXTURES / "emails.json").read_text())]
    extractor = FakeExtractor()

    result = await OrderImportService(
        client=FakeFerrapexClient(emails, catalog), session_factory=session_factory, llm_extractor=extractor
    ).sync()

    assert extractor.calls == []
    assert (result.processed, result.needs_review, result.failed) == (3, 0, 0)

    with session_factory() as s:
        orders = {o.source_email_id: o for o in OrderRepository(s).get_all()}
    assert orders["1-02"].customer_email == "paulo.monteiro@serralhariamonteiro.pt"
    assert orders["1-02"].requested_delivery_date == date(2026, 9, 18)
    assert [(l.product_reference, l.quantity) for l in orders["1-03"].lines] == [
        ("DOB-080-ZNC", 30),
        ("PRF-AGL-60", 1000),
        ("FER-FIT-8", 2),
    ]
