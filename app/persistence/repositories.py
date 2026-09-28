from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.email import Email
from app.domain.order import ExtractedOrder
from app.persistence.models import EmailModel, OrderLineModel, OrderModel, utcnow


class EmailRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, email_id: str) -> EmailModel | None:
        return self._session.get(EmailModel, email_id)

    def get_all(self) -> list[EmailModel]:
        return list(self._session.scalars(select(EmailModel).order_by(EmailModel.received_at.desc())))

    def add(self, email: Email) -> EmailModel:
        model = EmailModel(
            id=email.id,
            sender=email.sender,
            recipient=email.recipient,
            received_at=email.received_at,
            subject=email.subject,
            body=email.body,
            raw_json=email.model_dump_json(by_alias=True),
            processing_status="pending",
        )
        self._session.add(model)
        self._session.flush()
        return model

    def mark_processed(self, email_id: str) -> None:
        self._set_status(email_id, "processed", None)

    def mark_needs_review(self, email_id: str, reason: str) -> None:
        self._set_status(email_id, "needs_review", reason)

    def mark_failed(self, email_id: str, error: str) -> None:
        self._set_status(email_id, "failed", error)

    def _set_status(self, email_id: str, status: str, error: str | None) -> None:
        model = self._session.get(EmailModel, email_id)
        if model is None:
            raise LookupError(f"Email {email_id} não existe.")
        model.processing_status = status
        model.processing_error = error
        model.processed_at = utcnow()
        self._session.flush()


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def exists_for_email(self, email_id: str) -> bool:
        return bool(self._session.scalar(select(exists().where(OrderModel.source_email_id == email_id))))

    def create_order(self, email_id: str, order: ExtractedOrder, status: str, extraction_method: str) -> OrderModel:
        model = OrderModel(
            source_email_id=email_id,
            customer_email=order.customer_email,
            customer_name=order.customer_name,
            requested_delivery_date=order.requested_delivery_date,
            status=status,
            extraction_method=extraction_method,
            lines=[OrderLineModel(product_reference=l.reference, quantity=l.quantity) for l in order.lines],
        )
        self._session.add(model)
        self._session.flush()
        return model

    def get_all(self, customer_email: str | None = None) -> list[OrderModel]:
        stmt = select(OrderModel).options(selectinload(OrderModel.lines)).order_by(OrderModel.id)
        if customer_email:
            stmt = stmt.where(OrderModel.customer_email == customer_email.strip().lower())
        return list(self._session.scalars(stmt))

    def list_customers(self) -> list[tuple[str, int]]:
        """Clientes identificados pelo email do remetente, com o nº de encomendas."""
        stmt = (
            select(OrderModel.customer_email, func.count(OrderModel.id))
            .group_by(OrderModel.customer_email)
            .order_by(OrderModel.customer_email)
        )
        return [(email, count) for email, count in self._session.execute(stmt)]

    def get_by_id(self, order_id: int) -> OrderModel | None:
        return self._session.get(OrderModel, order_id, options=[selectinload(OrderModel.lines)])
