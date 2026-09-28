from dataclasses import asdict
from datetime import date, datetime

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from app.dependencies import get_import_service, get_session_factory
from app.persistence.repositories import OrderRepository
from app.services.import_orders import OrderImportService
from app.web.routes import router as web_router


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_reference: str
    quantity: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_email_id: str
    customer_email: str
    customer_name: str | None
    requested_delivery_date: date | None
    status: str
    extraction_method: str
    created_at: datetime
    lines: list[OrderLineOut]


class SyncOut(BaseModel):
    fetched: int
    processed: int
    needs_review: int
    failed: int
    skipped: int


def create_app() -> FastAPI:
    app = FastAPI(title="Ferrapex Order Import")
    app.include_router(web_router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/sync", response_model=SyncOut)
    async def sync(service: OrderImportService = Depends(get_import_service)) -> SyncOut:
        return SyncOut(**asdict(await service.sync()))

    @app.get("/orders", response_model=list[OrderOut])
    def list_orders(session_factory: sessionmaker[Session] = Depends(get_session_factory)) -> list[OrderOut]:
        with session_factory() as session:
            return [OrderOut.model_validate(o) for o in OrderRepository(session).get_all()]

    @app.get("/orders/{order_id}", response_model=OrderOut)
    def get_order(order_id: int, session_factory: sessionmaker[Session] = Depends(get_session_factory)) -> OrderOut:
        with session_factory() as session:
            order = OrderRepository(session).get_by_id(order_id)
            if order is None:
                raise HTTPException(status_code=404, detail="Encomenda não encontrada")
            return OrderOut.model_validate(order)

    return app


app = create_app()
