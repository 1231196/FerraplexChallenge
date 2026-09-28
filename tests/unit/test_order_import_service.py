from datetime import date

import httpx
import pytest

from app.domain.order import ExtractedOrder, ExtractionIssue, OrderLine
from app.persistence.repositories import EmailRepository, OrderRepository
from app.services.import_orders import OrderImportService
from tests.conftest import FakeExtractor, FakeFerrapexClient, make_email

NATURAL_LANGUAGE_BODY = "Bom dia, queria 1200 parafusos PRF-AGL-40 e 24 silicones SIL-ACE-280 para 21 de setembro de 2026."


def llm_order(**overrides) -> ExtractedOrder:
    data = dict(
        customer_email="compras@cliente.pt",
        requested_delivery_date=date(2026, 9, 21),
        lines=[OrderLine(reference="PRF-AGL-40", quantity=1200), OrderLine(reference="SIL-ACE-280", quantity=24)],
    )
    data.update(overrides)
    return ExtractedOrder(**data)


def build(session_factory, catalog, emails, extractor) -> OrderImportService:
    return OrderImportService(
        client=FakeFerrapexClient(emails, catalog), session_factory=session_factory, llm_extractor=extractor
    )


def stored(session_factory, email_id):
    with session_factory() as s:
        email = EmailRepository(s).get_by_id(email_id)
        order = next((o for o in OrderRepository(s).get_all() if o.source_email_id == email_id), None)
        return email, order


async def test_valid_deterministic_parse_does_not_call_llm(session_factory, catalog):
    extractor = FakeExtractor()

    result = await build(session_factory, catalog, [make_email(id="e1")], extractor).sync()

    email, order = stored(session_factory, "e1")
    assert extractor.calls == []
    assert result.processed == 1
    assert email.processing_status == "processed"
    assert order.status == "processed"
    assert order.extraction_method == "deterministic"
    assert len(order.lines) == 3


async def test_parser_failure_uses_llm_fallback(session_factory, catalog):
    extractor = FakeExtractor({"e1": llm_order()})

    result = await build(session_factory, catalog, [make_email(id="e1", body=NATURAL_LANGUAGE_BODY)], extractor).sync()

    email, order = stored(session_factory, "e1")
    assert extractor.calls == ["e1"]
    assert result.processed == 1
    assert email.processing_status == "processed"
    assert order.extraction_method == "llm"
    assert [(l.product_reference, l.quantity) for l in order.lines] == [("PRF-AGL-40", 1200), ("SIL-ACE-280", 24)]


async def test_llm_result_is_validated_before_persistence(session_factory, catalog):
    invented = llm_order(lines=[OrderLine(reference="PRF-INVENTADO-99", quantity=10)])
    extractor = FakeExtractor({"e1": invented})

    await build(session_factory, catalog, [make_email(id="e1", body=NATURAL_LANGUAGE_BODY)], extractor).sync()

    email, order = stored(session_factory, "e1")
    assert order.status == "needs_review"
    assert email.processing_status == "needs_review"
    assert "unknown_reference" in email.processing_error


async def test_invalid_llm_result_is_marked_needs_review(session_factory, catalog):
    ambiguous = llm_order(
        requested_delivery_date=None,
        issues=[ExtractionIssue(type="ambiguous_delivery_date", message="'fim do mês' não é uma data concreta")],
    )
    extractor = FakeExtractor({"e1": ambiguous})

    result = await build(session_factory, catalog, [make_email(id="e1", body=NATURAL_LANGUAGE_BODY)], extractor).sync()

    email, order = stored(session_factory, "e1")
    assert result.needs_review == 1
    assert order.status == "needs_review"
    assert order.extraction_method == "llm"
    assert "missing_delivery_date" in email.processing_error


async def test_business_rule_violation_goes_to_review_without_llm(session_factory, catalog):
    extractor = FakeExtractor()
    body = "Para entrega a 2026-09-21:\nXXX-000-99 | 5\n"

    await build(session_factory, catalog, [make_email(id="e1", body=body)], extractor).sync()

    _, order = stored(session_factory, "e1")
    assert extractor.calls == []
    assert order.status == "needs_review"
    assert order.extraction_method == "deterministic"


async def test_sender_is_authoritative_customer_email_over_llm(session_factory, catalog):
    extractor = FakeExtractor({"e1": llm_order(customer_email="alguem@inventado.pt")})

    await build(session_factory, catalog, [make_email(id="e1", body=NATURAL_LANGUAGE_BODY)], extractor).sync()

    _, order = stored(session_factory, "e1")
    assert order.customer_email == "compras@cliente.pt"


async def test_http_error_fetching_catalog_is_raised_and_llm_not_called(session_factory, catalog):
    class BrokenClient(FakeFerrapexClient):
        async def get_catalog(self):
            raise httpx.ConnectError("down")

    extractor = FakeExtractor()
    service = OrderImportService(
        client=BrokenClient([make_email()], catalog), session_factory=session_factory, llm_extractor=extractor
    )

    with pytest.raises(httpx.ConnectError):
        await service.sync()
    assert extractor.calls == []


async def test_llm_technical_error_marks_email_failed(session_factory, catalog):
    extractor = FakeExtractor({"e1": httpx.ConnectError("ollama down")})

    result = await build(session_factory, catalog, [make_email(id="e1", body=NATURAL_LANGUAGE_BODY)], extractor).sync()

    email, order = stored(session_factory, "e1")
    assert result.failed == 1
    assert email.processing_status == "failed"
    assert "ollama down" in email.processing_error
    assert order is None


async def test_llm_response_outside_schema_is_marked_needs_review(session_factory, catalog):
    from app.extraction.ollama import LLMExtractionError

    extractor = FakeExtractor({"e1": LLMExtractionError("schema inválido")})

    result = await build(session_factory, catalog, [make_email(id="e1", body=NATURAL_LANGUAGE_BODY)], extractor).sync()

    email, order = stored(session_factory, "e1")
    assert result.needs_review == 1
    assert order.status == "needs_review"
    assert "llm_invalid_response" in email.processing_error


async def test_email_with_attachments_is_marked_needs_review_without_llm(session_factory, catalog):
    extractor = FakeExtractor()
    emails = [
        make_email(id="e1", attachments=[{"name": "encomenda.xlsx"}]),  # corpo válido + anexo
        make_email(id="e2", body="Segue encomenda em anexo.", attachments=[{"name": "encomenda.pdf"}]),
    ]

    result = await build(session_factory, catalog, emails, extractor).sync()

    assert extractor.calls == []
    assert result.needs_review == 2
    for email_id in ("e1", "e2"):
        email, order = stored(session_factory, email_id)
        assert order.status == "needs_review"
        assert "attachments_not_supported" in email.processing_error


async def test_llm_result_without_evidence_in_email_goes_to_review(session_factory, catalog):
    """O LLM inventou a quantidade: o validator aceita (referência existe, qtd > 0), o grounding não."""
    body = "Mandem umas caixas de PRF-AGL-40 para dia 21 de setembro de 2026."
    extractor = FakeExtractor({"e1": llm_order(lines=[OrderLine(reference="PRF-AGL-40", quantity=1)])})

    await build(session_factory, catalog, [make_email(id="e1", body=body)], extractor).sync()

    email, order = stored(session_factory, "e1")
    assert order.status == "needs_review"
    assert "quantity_not_in_email" in email.processing_error
