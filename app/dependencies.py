from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from app.api.ferrapex_client import FerrapexClient
from app.config import get_settings
from app.extraction.ollama import OllamaOrderExtractor
from app.persistence.database import create_db_engine, create_session_factory, init_db
from app.services.import_orders import OrderImportService


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    engine = create_db_engine(get_settings().database_url)
    init_db(engine)
    return create_session_factory(engine)


@asynccontextmanager
async def import_service(session_factory: sessionmaker[Session]) -> AsyncIterator[OrderImportService]:
    settings = get_settings()
    client = FerrapexClient(settings.ferrapex_api_base_url, settings.ferrapex_api_key.get_secret_value())
    extractor = OllamaOrderExtractor(settings.ollama_base_url, settings.ollama_model)
    try:
        yield OrderImportService(client=client, session_factory=session_factory, llm_extractor=extractor)
    finally:
        await client.aclose()
        await extractor.aclose()


async def get_import_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> AsyncIterator[OrderImportService]:
    async with import_service(session_factory) as service:
        yield service
