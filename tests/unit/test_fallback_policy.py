from datetime import date

import pytest

from app.domain.order import ExtractedOrder, ExtractionIssue, OrderLine
from app.extraction.fallback import should_use_llm

ORDER = ExtractedOrder(
    customer_email="c@x.pt",
    requested_delivery_date=date(2026, 9, 21),
    lines=[OrderLine(reference="PRF-AGL-40", quantity=1)],
)


def issue(t: str) -> ExtractionIssue:
    return ExtractionIssue(type=t, message=t)


def test_valid_order_does_not_use_llm():
    assert should_use_llm(ORDER, []) is False


@pytest.mark.parametrize(
    "issue_type",
    ["no_lines_found", "delivery_date_not_found", "ambiguous_delivery_date", "invalid_delivery_date", "unparsed_line"],
)
def test_parse_failures_use_llm(issue_type):
    assert should_use_llm(ORDER, [issue(issue_type)]) is True


@pytest.mark.parametrize("issue_type", ["unknown_reference", "invalid_quantity", "duplicate_reference", "missing_customer_email"])
def test_business_rule_violations_on_well_parsed_email_do_not_use_llm(issue_type):
    """O conteúdo foi lido corretamente; o LLM não pode 'corrigir' referências ou quantidades."""
    assert should_use_llm(ORDER, [issue(issue_type)]) is False


def test_emails_with_attachments_never_use_llm():
    """O LLM não vê os anexos; chamá-lo só daria uma encomenda possivelmente incompleta."""
    issues = [issue("no_lines_found"), issue("attachments_not_supported")]

    assert should_use_llm(ORDER, issues) is False
