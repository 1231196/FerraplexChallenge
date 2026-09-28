from datetime import date

from app.domain.order import ExtractedOrder, ExtractionIssue, OrderLine
from app.validation.order_validator import OrderValidator

validator = OrderValidator()


def make_order(**overrides) -> ExtractedOrder:
    data = dict(
        customer_email="compras@cliente.pt",
        requested_delivery_date=date(2026, 9, 21),
        lines=[OrderLine(reference="PRF-AGL-40", quantity=1200), OrderLine(reference="SIL-ACE-280", quantity=24)],
    )
    data.update(overrides)
    return ExtractedOrder(**data)


def types(issues) -> set[str]:
    return {i.type for i in issues}


def test_valid_order_has_no_issues(catalog):
    assert validator.validate(make_order(), catalog) == []


def test_order_without_lines_is_invalid(catalog):
    assert "no_lines" in types(validator.validate(make_order(lines=[]), catalog))


def test_quantity_must_be_positive(catalog):
    order = make_order(lines=[OrderLine(reference="PRF-AGL-40", quantity=0), OrderLine(reference="BCH-NYL-08", quantity=-3)])

    issues = validator.validate(order, catalog)

    assert [i.type for i in issues] == ["invalid_quantity", "invalid_quantity"]


def test_unknown_reference_is_invalid(catalog):
    order = make_order(lines=[OrderLine(reference="XXX-000-99", quantity=1)])

    assert "unknown_reference" in types(validator.validate(order, catalog))


def test_delivery_date_is_required(catalog):
    assert "missing_delivery_date" in types(validator.validate(make_order(requested_delivery_date=None), catalog))


def test_customer_email_is_required(catalog):
    assert "missing_customer_email" in types(validator.validate(make_order(customer_email="  "), catalog))


def test_duplicate_reference_is_flagged(catalog):
    order = make_order(lines=[OrderLine(reference="PRF-AGL-40", quantity=1), OrderLine(reference="PRF-AGL-40", quantity=2)])

    assert "duplicate_reference" in types(validator.validate(order, catalog))


def test_extraction_issues_are_carried_over(catalog):
    """Ambiguidades reportadas pelo extractor tornam a encomenda não-válida."""
    order = make_order(issues=[ExtractionIssue(type="ambiguous_quantity", message="?")])

    assert "ambiguous_quantity" in types(validator.validate(order, catalog))
