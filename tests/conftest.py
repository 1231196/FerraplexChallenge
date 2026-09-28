from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.email import Email
from app.domain.product import Product


@pytest.fixture
def catalog() -> list[Product]:
    return [
        Product(reference="PRF-AGL-40", description="Parafuso aglomerado 4.0", family="Parafusos", unit="un", price_eur=Decimal("0.05")),
        Product(reference="BCH-NYL-08", description="Bucha nylon 8mm", family="Buchas", unit="un", price_eur=Decimal("0.03")),
        Product(reference="SIL-ACE-280", description="Silicone acético 280ml", family="Selantes", unit="un", price_eur=Decimal("4.50")),
    ]


def make_email(
    id: str = "email-1",
    body: str = "Para entrega a 2026-09-21:\n\nPRF-AGL-40 | 1200\nBCH-NYL-08 | 800\nSIL-ACE-280 | 24\n",
    sender: str = "compras@cliente.pt",
) -> Email:
    return Email.model_validate(
        {
            "id": id,
            "from": sender,
            "to": "encomendas@ferrapex.pt",
            "received_at": datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            "subject": "Encomenda",
            "body": body,
            "attachments": [],
        }
    )


@pytest.fixture
def email() -> Email:
    return make_email()


@pytest.fixture
def session_factory():
    from app.persistence.database import create_db_engine, create_session_factory, init_db

    engine = create_db_engine("sqlite://")
    init_db(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


class FakeFerrapexClient:
    def __init__(self, emails: list[Email], catalog: list[Product]) -> None:
        self.emails = emails
        self.catalog = catalog

    async def get_emails(self) -> list[Email]:
        return list(self.emails)

    async def get_catalog(self) -> list[Product]:
        return list(self.catalog)


class FakeExtractor:
    """Stub do OllamaOrderExtractor: devolve respostas pré-definidas por email id."""

    def __init__(self, responses: dict | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    async def extract(self, email: Email, catalog: list[Product]):
        self.calls.append(email.id)
        response = self.responses[email.id]
        if isinstance(response, Exception):
            raise response
        return response
