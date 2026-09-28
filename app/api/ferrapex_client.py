import csv
import io

import httpx

from app.domain.email import Email
from app.domain.product import Product


def parse_catalog_csv(text: str) -> list[Product]:
    reader = csv.DictReader(io.StringIO(text.strip()))
    return [Product.model_validate({k.strip(): v.strip() for k, v in row.items()}) for row in reader]


class FerrapexClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def get_emails(self) -> list[Email]:
        response = await self._http.get("/emails", headers=self._headers)
        response.raise_for_status()
        return [Email.model_validate(item) for item in response.json()]

    async def get_catalog(self) -> list[Product]:
        response = await self._http.get("/catalog", headers=self._headers)
        response.raise_for_status()
        return parse_catalog_csv(response.text)

    async def aclose(self) -> None:
        await self._http.aclose()
