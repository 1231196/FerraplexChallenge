from typing import Protocol

from app.domain.email import Email
from app.domain.order import ExtractedOrder
from app.domain.product import Product


class OrderExtractor(Protocol):
    async def extract(self, email: Email, catalog: list[Product]) -> ExtractedOrder: ...
