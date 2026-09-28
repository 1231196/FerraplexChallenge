from app.domain.order import ExtractedOrder, ExtractionIssue

# Issues que significam "o parser não conseguiu interpretar o formato".
# Violações de regras de negócio (referência desconhecida, quantidade <= 0, ...)
# num email bem interpretado NÃO justificam o LLM: vão para revisão humana.
# Erros técnicos (HTTP, BD, config) são exceções e nunca chegam aqui.
PARSE_FAILURE_ISSUES = frozenset(
    {
        "no_lines_found",
        "delivery_date_not_found",
        "ambiguous_delivery_date",
        "invalid_delivery_date",
        "unparsed_line",
    }
)


def should_use_llm(order: ExtractedOrder, issues: list[ExtractionIssue]) -> bool:
    return any(issue.type in PARSE_FAILURE_ISSUES for issue in issues)
