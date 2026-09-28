from datetime import date

import pytest

from app.domain.order import ExtractedOrder, OrderLine
from app.validation.grounding import check_grounding

BODY = "Bom dia, para 25/09/2026 preciso de 1.200 PRF-AGL-40 e 30 pares de dobradiças 80x60 zincadas."


def order(lines, delivery=date(2026, 9, 25)) -> ExtractedOrder:
    return ExtractedOrder(
        customer_email="c@x.pt",
        requested_delivery_date=delivery,
        lines=[OrderLine(reference=r, quantity=q) for r, q in lines],
    )


def types(issues) -> list[str]:
    return [i.type for i in issues]


def test_literal_reference_quantity_and_date_are_grounded():
    assert check_grounding(order([("PRF-AGL-40", 1200)]), BODY) == []


def test_quantity_not_written_in_email_is_flagged():
    assert types(check_grounding(order([("PRF-AGL-40", 1)]), BODY)) == ["quantity_not_in_email"]


def test_reference_inferred_from_description_needs_confirmation():
    issues = check_grounding(order([("DOB-080-ZNC", 30)]), BODY)

    assert types(issues) == ["reference_not_in_email"]
    assert "DOB-080-ZNC" in issues[0].message


@pytest.mark.parametrize(
    "body, delivery",
    [
        ("entrega a 2026-09-21", date(2026, 9, 21)),
        ("entrega 21/09/2026", date(2026, 9, 21)),
        ("entrega 1-10-2026", date(2026, 10, 1)),
        ("para o dia 21 de setembro de 2026", date(2026, 9, 21)),
        ("para dia 3 de Março", date(2027, 3, 3)),
        ("Delivery on September 30, 2026", date(2026, 9, 30)),
        ("delivery 30 september", date(2026, 9, 30)),
    ],
)
def test_date_with_evidence_in_email_is_grounded(body, delivery):
    assert check_grounding(order([], delivery), body) == []


@pytest.mark.parametrize(
    "body",
    ["para a próxima sexta-feira", "lá para o fim do mês", "entrega 22/09/2026", "até dia 21"],
)
def test_date_without_evidence_is_flagged(body):
    assert types(check_grounding(order([], date(2026, 9, 21)), body)) == ["delivery_date_not_in_email"]


def test_missing_date_is_left_to_the_validator():
    assert check_grounding(order([], delivery=None), "sem data") == []


def test_catalog_reference_written_in_email_but_missing_from_lines_is_flagged():
    body = "Para 30/09/2026: 10 FER-MRT-500 e 50 FER-BRC-18."
    catalog_refs = {"FER-MRT-500", "FER-BRC-18", "PRF-AGL-40"}

    issues = check_grounding(order([("FER-MRT-500", 10)], date(2026, 9, 30)), body, catalog_refs)

    assert types(issues) == ["reference_missing_from_order"]
    assert "FER-BRC-18" in issues[0].message
