import json
from datetime import date

import httpx
import pytest

from app.domain.order import ExtractedOrder
from app.extraction.ollama import LLMExtractionError, OllamaOrderExtractor, llm_response_schema
from tests.conftest import make_email

BODY = "Olá, mandem 1200 parafusos PRF-AGL-40 para dia 21/09/2026."


def ollama_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"model": "qwen3:8b", "message": {"role": "assistant", "content": content}, "done": True})


def make_extractor(handler) -> OllamaOrderExtractor:
    http = httpx.AsyncClient(base_url="http://ollama.test", transport=httpx.MockTransport(handler))
    return OllamaOrderExtractor(base_url="http://ollama.test", model="qwen3:8b", http_client=http)


VALID_CONTENT = json.dumps(
    {
        "customer_name": None,
        "customer_email": "compras@cliente.pt",
        "requested_delivery_date": "2026-09-21",
        "lines": [{"reference": "PRF-AGL-40", "quantity": 1200}],
        "issues": [],
    }
)


async def test_extractor_requests_structured_output_from_qwen(catalog):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.url.path == "/api/chat"
        return ollama_reply(VALID_CONTENT)

    await make_extractor(handler).extract(make_email(body=BODY), catalog)

    payload = seen[0]
    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert payload["format"] == llm_response_schema()
    assert payload["options"]["temperature"] == 0


async def test_prompt_contains_catalog_email_and_rules(catalog):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return ollama_reply(VALID_CONTENT)

    await make_extractor(handler).extract(make_email(body=BODY), catalog)

    prompt = "\n".join(m["content"] for m in seen[0]["messages"])
    for product in catalog:
        assert product.reference in prompt
    assert BODY in prompt
    assert "compras@cliente.pt" in prompt
    assert "Nunca inventes" in prompt


async def test_structured_response_is_parsed_into_extracted_order(catalog):
    order = await make_extractor(lambda r: ollama_reply(VALID_CONTENT)).extract(make_email(body=BODY), catalog)

    assert order.requested_delivery_date == date(2026, 9, 21)
    assert order.lines[0].reference == "PRF-AGL-40"
    assert order.lines[0].quantity == 1200


async def test_response_not_matching_schema_raises(catalog):
    with pytest.raises(LLMExtractionError):
        await make_extractor(lambda r: ollama_reply('{"lines": "muitos"}')).extract(make_email(body=BODY), catalog)


async def test_http_error_is_propagated(catalog):
    with pytest.raises(httpx.HTTPStatusError):
        await make_extractor(lambda r: httpx.Response(500)).extract(make_email(body=BODY), catalog)


def test_llm_schema_requires_every_field_so_model_cannot_omit_them():
    schema = llm_response_schema()

    assert set(schema["required"]) == set(ExtractedOrder.model_fields)
    assert schema["properties"]["requested_delivery_date"]["anyOf"][1] == {"type": "null"}
