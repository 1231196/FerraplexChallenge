from datetime import date

from app.domain.order import OrderLine
from app.extraction.deterministic_parser import DeterministicOrderParser
from tests.conftest import make_email

parser = DeterministicOrderParser()


def issue_types(order) -> set[str]:
    return {i.type for i in order.issues}


def test_parser_extracts_delivery_date(email, catalog):
    order = parser.parse(email, catalog)

    assert order.requested_delivery_date == date(2026, 9, 21)


def test_parser_extracts_multiple_order_lines(email, catalog):
    order = parser.parse(email, catalog)

    assert order.lines == [
        OrderLine(reference="PRF-AGL-40", quantity=1200),
        OrderLine(reference="BCH-NYL-08", quantity=800),
        OrderLine(reference="SIL-ACE-280", quantity=24),
    ]
    assert order.issues == []


def test_parser_sets_sender_as_customer_email(catalog):
    order = parser.parse(make_email(sender="Loja Silva <Compras@Silva.pt>"), catalog)

    assert order.customer_email == "compras@silva.pt"
    assert order.customer_name == "Loja Silva"


def test_parser_reports_missing_lines(catalog):
    body = "Bom dia, precisamos de mil e duzentos parafusos para o dia 21 de setembro. Obrigado."
    order = parser.parse(make_email(body=body), catalog)

    assert order.lines == []
    assert "no_lines_found" in issue_types(order)
    assert "delivery_date_not_found" in issue_types(order)


def test_parser_ignores_whitespace_variations(catalog):
    body = "Para entrega a 2026-09-21\n  prf-agl-40|1200  \nBCH-NYL-08  |  800\n"
    order = parser.parse(make_email(body=body), catalog)

    assert [(l.reference, l.quantity) for l in order.lines] == [("PRF-AGL-40", 1200), ("BCH-NYL-08", 800)]


def test_parser_reports_ambiguous_dates(catalog):
    body = "Para entrega a 2026-09-21 ou 2026-09-25:\nPRF-AGL-40 | 1200\n"
    order = parser.parse(make_email(body=body), catalog)

    assert order.requested_delivery_date is None
    assert "ambiguous_delivery_date" in issue_types(order)


def test_parser_reports_unparsed_lines_that_look_like_order_lines(catalog):
    body = "Para entrega a 2026-09-21:\nPRF-AGL-40 | 1200\nBCH-NYL-08 | oitocentos\n"
    order = parser.parse(make_email(body=body), catalog)

    assert [l.reference for l in order.lines] == ["PRF-AGL-40"]
    assert "unparsed_line" in issue_types(order)


def test_parser_does_not_filter_unknown_references(catalog):
    """O parser extrai; quem decide se a referência existe é o validator."""
    body = "Para entrega a 2026-09-21:\nXXX-000-99 | 5\n"
    order = parser.parse(make_email(body=body), catalog)

    assert order.lines == [OrderLine(reference="XXX-000-99", quantity=5)]
