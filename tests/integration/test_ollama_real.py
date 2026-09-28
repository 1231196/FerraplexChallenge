"""Teste contra um Ollama real. Não corre por omissão: `pytest -m ollama`."""

import os

import pytest

from app.extraction.ollama import OllamaOrderExtractor
from app.validation.order_validator import OrderValidator
from tests.conftest import make_email

pytestmark = pytest.mark.ollama


async def test_qwen_extracts_natural_language_order(catalog):
    extractor = OllamaOrderExtractor(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
    )
    body = (
        "Boa tarde,\n\nPrecisamos de 1200 unidades do parafuso aglomerado PRF-AGL-40 "
        "e de 24 silicones SIL-ACE-280. Entrega no dia 21 de setembro de 2026, por favor.\n\nCumprimentos"
    )
    try:
        order = await extractor.extract(make_email(body=body), catalog)
    finally:
        await extractor.aclose()

    assert {(l.reference, l.quantity) for l in order.lines} == {("PRF-AGL-40", 1200), ("SIL-ACE-280", 24)}
    assert str(order.requested_delivery_date) == "2026-09-21"
    assert OrderValidator().validate(order, catalog) == []


async def test_qwen_does_not_guess_on_ambiguous_order(catalog):
    extractor = OllamaOrderExtractor(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
    )
    body = "Olá, mandem uns quantos parafusos PRF-AGL-40 e 10 martelos de borracha lá para o fim do mês."
    try:
        order = await extractor.extract(make_email(body=body), catalog)
    finally:
        await extractor.aclose()

    # O que interessa é o resultado final: nunca pode passar como válido.
    assert OrderValidator().validate(order, catalog) != []
