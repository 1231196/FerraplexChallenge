import json
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.order import ExtractedOrder, OrderLine
from app.persistence.repositories import EmailRepository, OrderRepository
from tests.conftest import make_email


def make_order() -> ExtractedOrder:
    return ExtractedOrder(
        customer_name="Loja",
        customer_email="compras@cliente.pt",
        requested_delivery_date=date(2026, 9, 21),
        lines=[OrderLine(reference="PRF-AGL-40", quantity=1200), OrderLine(reference="SIL-ACE-280", quantity=24)],
    )


def test_email_can_be_persisted(session):
    repo = EmailRepository(session)
    repo.add(make_email(id="e1"))
    session.commit()

    stored = repo.get_by_id("e1")
    assert stored.sender == "compras@cliente.pt"
    assert stored.processing_status == "pending"
    assert json.loads(stored.raw_json)["from"] == "compras@cliente.pt"
    assert stored.created_at is not None


def test_email_status_transitions(session):
    repo = EmailRepository(session)
    repo.add(make_email(id="e1"))

    repo.mark_needs_review("e1", "referência desconhecida")
    assert repo.get_by_id("e1").processing_status == "needs_review"
    assert repo.get_by_id("e1").processing_error == "referência desconhecida"

    repo.mark_failed("e1", "boom")
    assert repo.get_by_id("e1").processing_status == "failed"

    repo.mark_processed("e1")
    stored = repo.get_by_id("e1")
    assert stored.processing_status == "processed"
    assert stored.processing_error is None
    assert stored.processed_at is not None


def test_order_and_lines_can_be_persisted(session):
    EmailRepository(session).add(make_email(id="e1"))
    orders = OrderRepository(session)

    created = orders.create_order("e1", make_order(), status="processed", extraction_method="deterministic")
    session.commit()

    stored = orders.get_by_id(created.id)
    assert stored.source_email_id == "e1"
    assert stored.status == "processed"
    assert stored.extraction_method == "deterministic"
    assert stored.requested_delivery_date == date(2026, 9, 21)
    assert [(l.product_reference, l.quantity) for l in stored.lines] == [("PRF-AGL-40", 1200), ("SIL-ACE-280", 24)]
    assert orders.exists_for_email("e1") is True
    assert orders.exists_for_email("other") is False
    assert [o.id for o in orders.get_all()] == [created.id]


def test_duplicate_source_email_is_rejected(session):
    EmailRepository(session).add(make_email(id="e1"))
    orders = OrderRepository(session)
    orders.create_order("e1", make_order(), status="processed", extraction_method="deterministic")
    session.commit()

    with pytest.raises(IntegrityError):
        orders.create_order("e1", make_order(), status="processed", extraction_method="llm")
        session.commit()
