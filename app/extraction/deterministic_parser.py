import re
from datetime import date
from email.utils import parseaddr

from app.domain.email import Email
from app.domain.order import ExtractedOrder, ExtractionIssue, OrderLine
from app.domain.product import Product

DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
LINE_RE = re.compile(r"^\s*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)\s*\|\s*(\d+)\s*$")


def parse_sender(sender: str) -> tuple[str | None, str]:
    name, address = parseaddr(sender)
    return (name.strip() or None), (address or sender).strip().lower()


def _attachment_name(attachment: object) -> str:
    if isinstance(attachment, dict):
        return str(attachment.get("name") or attachment.get("filename") or attachment)
    return str(attachment)


class DeterministicOrderParser:
    """Parser para o formato atual: data YYYY-MM-DD + linhas `REFERENCIA | QUANTIDADE`.

    Não valida contra o catálogo (isso é do OrderValidator); apenas extrai e
    reporta o que não consegue interpretar com segurança.
    """

    def parse(self, email: Email, catalog: list[Product]) -> ExtractedOrder:
        customer_name, customer_email = parse_sender(email.sender)
        issues: list[ExtractionIssue] = []

        delivery_date = self._parse_date(email.body, issues)
        lines = self._parse_lines(email.body, issues)
        if email.attachments:
            # Anexos ainda não são lidos: a encomenda pode estar (também) no anexo.
            names = ", ".join(_attachment_name(a) for a in email.attachments)
            issues.append(
                ExtractionIssue(type="attachments_not_supported", message=f"Email com anexos por processar: {names}.")
            )

        return ExtractedOrder(
            customer_name=customer_name,
            customer_email=customer_email,
            requested_delivery_date=delivery_date,
            lines=lines,
            issues=issues,
        )

    def _parse_date(self, body: str, issues: list[ExtractionIssue]) -> date | None:
        candidates = list(dict.fromkeys(DATE_RE.findall(body)))
        if not candidates:
            issues.append(ExtractionIssue(type="delivery_date_not_found", message="Nenhuma data YYYY-MM-DD encontrada."))
            return None
        if len(candidates) > 1:
            issues.append(
                ExtractionIssue(type="ambiguous_delivery_date", message=f"Várias datas encontradas: {', '.join(candidates)}.")
            )
            return None
        try:
            return date.fromisoformat(candidates[0])
        except ValueError:
            issues.append(ExtractionIssue(type="invalid_delivery_date", message=f"Data inválida: {candidates[0]}."))
            return None

    def _parse_lines(self, body: str, issues: list[ExtractionIssue]) -> list[OrderLine]:
        lines: list[OrderLine] = []
        for raw in body.splitlines():
            match = LINE_RE.match(raw)
            if match:
                lines.append(OrderLine(reference=match.group(1).upper(), quantity=int(match.group(2))))
            elif "|" in raw:
                issues.append(ExtractionIssue(type="unparsed_line", message=f"Linha não reconhecida: {raw.strip()!r}."))
        if not lines:
            issues.append(ExtractionIssue(type="no_lines_found", message="Nenhuma linha `REFERENCIA | QUANTIDADE` encontrada."))
        return lines
