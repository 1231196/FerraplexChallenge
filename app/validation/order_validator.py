from app.domain.order import ExtractedOrder, ExtractionIssue
from app.domain.product import Product


class OrderValidator:
    """Única fonte de verdade sobre se uma encomenda extraída é aceitável.

    Devolve as issues reportadas pelo extractor mais as regras de negócio
    violadas. Lista vazia => encomenda válida.
    """

    def validate(self, order: ExtractedOrder, catalog: list[Product]) -> list[ExtractionIssue]:
        issues = list(order.issues)
        known = {p.reference for p in catalog}

        if not order.customer_email or not order.customer_email.strip():
            issues.append(ExtractionIssue(type="missing_customer_email", message="Email do cliente em falta."))
        if order.requested_delivery_date is None:
            issues.append(ExtractionIssue(type="missing_delivery_date", message="Data de entrega em falta."))
        if not order.lines:
            issues.append(ExtractionIssue(type="no_lines", message="A encomenda não tem linhas."))

        seen: set[str] = set()
        for line in order.lines:
            if line.reference not in known:
                issues.append(ExtractionIssue(type="unknown_reference", message=f"Referência inexistente no catálogo: {line.reference}."))
            if line.quantity <= 0:
                issues.append(ExtractionIssue(type="invalid_quantity", message=f"Quantidade inválida para {line.reference}: {line.quantity}."))
            if line.reference in seen:
                issues.append(ExtractionIssue(type="duplicate_reference", message=f"Referência repetida: {line.reference}."))
            seen.add(line.reference)

        return issues
