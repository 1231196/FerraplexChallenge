"""Verifica que o que o LLM devolveu tem evidência no texto do email.

O OrderValidator garante que a encomenda é aceitável para o catálogo; isto garante que
não foi inventada. Nos testes com qwen3:8b, o modelo inventou quantidades ("umas caixas" → 1),
datas ("próxima sexta") e mapeou produtos inexistentes para o mais parecido do catálogo.
"""

import re
import unicodedata
from datetime import date

from app.domain.order import ExtractedOrder, ExtractionIssue

MONTHS = {
    1: ("janeiro", "january", "jan"),
    2: ("fevereiro", "february", "fev", "feb"),
    3: ("marco", "march", "mar"),
    4: ("abril", "april", "abr", "apr"),
    5: ("maio", "may", "mai"),
    6: ("junho", "june", "jun"),
    7: ("julho", "july", "jul"),
    8: ("agosto", "august", "ago", "aug"),
    9: ("setembro", "september", "set", "sep", "sept"),
    10: ("outubro", "october", "out", "oct"),
    11: ("novembro", "november", "nov"),
    12: ("dezembro", "december", "dez", "dec"),
}
MONTH_RE = "|".join(sorted({name for names in MONTHS.values() for name in names}, key=len, reverse=True))
MONTH_NUMBER = {name: number for number, names in MONTHS.items() for name in names}

NUMBER_RE = re.compile(r"(?<![\d.])\d{1,3}(?:[.\s]\d{3})+(?![\d.])|\d+")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2}|\d{4}))?\b")
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DAY_MONTH_RE = re.compile(rf"\b(\d{{1,2}})(?:º|o)?\s+(?:de\s+)?({MONTH_RE})\b(?:\s+(?:de\s+)?(\d{{4}}))?")
MONTH_DAY_RE = re.compile(rf"\b({MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?")


def check_grounding(
    order: ExtractedOrder, body: str, catalog_references: set[str] | None = None
) -> list[ExtractionIssue]:
    text = _normalize(body)
    issues: list[ExtractionIssue] = []

    extracted = {line.reference for line in order.lines}
    for reference in sorted(catalog_references or ()):
        if reference not in extracted and re.search(rf"\b{re.escape(reference.lower())}\b", text):
            issues.append(
                ExtractionIssue(
                    type="reference_missing_from_order",
                    message=f"{reference} está escrita no email mas não foi extraída.",
                )
            )

    numbers = {int(re.sub(r"[.\s]", "", n)) for n in NUMBER_RE.findall(text)}
    for line in order.lines:
        if line.reference.lower() not in text:
            issues.append(
                ExtractionIssue(
                    type="reference_not_in_email",
                    message=f"{line.reference} foi inferida de uma descrição; confirmar o produto.",
                )
            )
        if line.quantity not in numbers:
            issues.append(
                ExtractionIssue(
                    type="quantity_not_in_email",
                    message=f"A quantidade {line.quantity} de {line.reference} não aparece no email.",
                )
            )

    delivery = order.requested_delivery_date
    if delivery is not None and not _date_has_evidence(delivery, text):
        issues.append(
            ExtractionIssue(
                type="delivery_date_not_in_email",
                message=f"A data {delivery.isoformat()} não está escrita no email (data relativa ou inferida).",
            )
        )
    return issues


def _date_has_evidence(target: date, text: str) -> bool:
    def matches(day: int, month: int, year: str | None) -> bool:
        if (day, month) != (target.day, target.month):
            return False
        return year is None or int(year) % 100 == target.year % 100

    if any((int(y), int(m), int(d)) == (target.year, target.month, target.day) for y, m, d in ISO_DATE_RE.findall(text)):
        return True
    if any(matches(int(d), int(m), y or None) for d, m, y in NUMERIC_DATE_RE.findall(text)):
        return True
    if any(matches(int(d), MONTH_NUMBER[m], y or None) for d, m, y in DAY_MONTH_RE.findall(text)):
        return True
    return any(matches(int(d), MONTH_NUMBER[m], y or None) for m, d, y in MONTH_DAY_RE.findall(text))


def _normalize(text: str) -> str:
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return without_accents.lower()
