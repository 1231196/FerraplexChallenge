import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from app.dependencies import get_import_service, get_session_factory
from app.persistence.repositories import EmailRepository, OrderRepository
from app.services.import_orders import OrderImportService

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def home(request: Request, session_factory: sessionmaker[Session] = Depends(get_session_factory)):
    return _render_home(request, session_factory)


@router.post("/ui/sync", response_class=HTMLResponse)
async def ui_sync(
    request: Request,
    service: OrderImportService = Depends(get_import_service),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
):
    try:
        result = asdict(await service.sync())
    except Exception as exc:
        logger.exception("Sync falhou")
        return _render_home(request, session_factory, sync_error=f"{type(exc).__name__}: {exc}", status_code=502)
    return _render_home(request, session_factory, sync_result=result)


@router.get("/ui/orders/{order_id}", response_class=HTMLResponse)
def order_detail(
    request: Request, order_id: int, session_factory: sessionmaker[Session] = Depends(get_session_factory)
):
    with session_factory() as session:
        order = OrderRepository(session).get_by_id(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Encomenda não encontrada")
        email = EmailRepository(session).get_by_id(order.source_email_id)
        return templates.TemplateResponse(request, "order_detail.html", {"order": order, "email": email})


@router.get("/ui/emails", response_class=HTMLResponse)
def emails_page(request: Request, session_factory: sessionmaker[Session] = Depends(get_session_factory)):
    with session_factory() as session:
        return templates.TemplateResponse(request, "emails.html", {"emails": EmailRepository(session).get_all()})


def _render_home(request, session_factory, sync_result=None, sync_error=None, status_code=200):
    with session_factory() as session:
        return templates.TemplateResponse(
            request,
            "orders.html",
            {"orders": OrderRepository(session).get_all(), "sync_result": sync_result, "sync_error": sync_error},
            status_code=status_code,
        )
