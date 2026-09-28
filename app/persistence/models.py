from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.persistence.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailModel(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    sender: Mapped[str] = mapped_column(String(320))
    recipient: Mapped[str] = mapped_column(String(320))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[str] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_email_id: Mapped[str] = mapped_column(ForeignKey("emails.id"), unique=True)
    customer_email: Mapped[str] = mapped_column(String(320), index=True)  # identifica o cliente
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # processed | needs_review
    extraction_method: Mapped[str] = mapped_column(String(20))  # deterministic | llm
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lines: Mapped[list["OrderLineModel"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderLineModel.id"
    )


class OrderLineModel(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_reference: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)

    order: Mapped[OrderModel] = relationship(back_populates="lines")
