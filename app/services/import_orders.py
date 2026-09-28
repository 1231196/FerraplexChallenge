import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.domain.email import Email
from app.domain.order import ExtractedOrder, ExtractionIssue
from app.domain.product import Product
from app.extraction.base import OrderExtractor
from app.extraction.deterministic_parser import DeterministicOrderParser
from app.extraction.fallback import should_use_llm
from app.extraction.ollama import LLMExtractionError
from app.persistence.repositories import EmailRepository, OrderRepository
from app.validation.grounding import check_grounding
from app.validation.order_validator import OrderValidator

logger = logging.getLogger(__name__)

Outcome = Literal["processed", "needs_review", "failed", "skipped"]


class FerrapexSource(Protocol):
    async def get_emails(self) -> list[Email]: ...
    async def get_catalog(self) -> list[Product]: ...


@dataclass
class SyncResult:
    fetched: int = 0
    processed: int = 0
    needs_review: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass
class _Extraction:
    order: ExtractedOrder
    method: Literal["deterministic", "llm"]
    issues: list[ExtractionIssue]


class OrderImportService:
    def __init__(
        self,
        client: FerrapexSource,
        session_factory: sessionmaker[Session],
        llm_extractor: OrderExtractor,
        parser: DeterministicOrderParser | None = None,
        validator: OrderValidator | None = None,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._llm = llm_extractor
        self._parser = parser or DeterministicOrderParser()
        self._validator = validator or OrderValidator()

    async def sync(self) -> SyncResult:
        # Erros ao obter catálogo/emails são técnicos: propagam, nunca vão ao LLM.
        catalog = await self._client.get_catalog()
        emails = await self._client.get_emails()

        result = SyncResult(fetched=len(emails))
        for email in emails:
            try:
                outcome = await self._process_email(email, catalog)
            except Exception:
                # Última rede de segurança (ex.: BD indisponível ao marcar failed).
                logger.exception("Erro inesperado ao processar email %s", email.id)
                outcome = "failed"
            setattr(result, outcome, getattr(result, outcome) + 1)
        return result

    async def _process_email(self, email: Email, catalog: list[Product]) -> Outcome:
        with self._session_factory() as session:
            emails = EmailRepository(session)
            orders = OrderRepository(session)

            if orders.exists_for_email(email.id):
                return "skipped"
            if emails.get_by_id(email.id) is None:
                emails.add(email)
            session.commit()

            try:
                extraction = await self._extract(email, catalog)
                status = "needs_review" if extraction.issues else "processed"
                orders.create_order(email.id, extraction.order, status=status, extraction_method=extraction.method)
                if status == "processed":
                    emails.mark_processed(email.id)
                else:
                    emails.mark_needs_review(email.id, _summarize(extraction.issues))
                session.commit()
                return status
            except Exception as exc:
                session.rollback()
                logger.warning("Falha técnica no email %s: %s", email.id, exc)
                emails.mark_failed(email.id, f"{type(exc).__name__}: {exc}")
                session.commit()
                return "failed"

    async def _extract(self, email: Email, catalog: list[Product]) -> _Extraction:
        parsed = self._parser.parse(email, catalog)
        issues = self._validator.validate(parsed, catalog)
        if not issues or not should_use_llm(parsed, issues):
            return _Extraction(parsed, "deterministic", issues)

        try:
            llm_order = await self._llm.extract(email, catalog)
        except LLMExtractionError as exc:
            # Não é falha técnica: o LLM não conseguiu extrair com segurança -> revisão humana.
            issue = ExtractionIssue(type="llm_invalid_response", message=str(exc))
            return _Extraction(parsed, "llm", [*issues, issue])

        # O remetente é a fonte de verdade para o cliente; não confiar no LLM aqui.
        llm_order = llm_order.model_copy(
            update={
                "customer_email": parsed.customer_email,
                "customer_name": llm_order.customer_name or parsed.customer_name,
            }
        )
        issues = self._validator.validate(llm_order, catalog) + check_grounding(
            llm_order, email.body, {p.reference for p in catalog}
        )
        return _Extraction(llm_order, "llm", issues)


def _summarize(issues: list[ExtractionIssue]) -> str:
    return "; ".join(f"{i.type}: {i.message}" for i in issues)
