import httpx
from pydantic import ValidationError

from app.domain.email import Email
from app.domain.order import ExtractedOrder
from app.domain.product import Product
from app.extraction.deterministic_parser import parse_sender

SYSTEM_PROMPT = """\
És um assistente que extrai encomendas de emails de clientes da Ferrapex.
Responde APENAS com um objeto que respeite o JSON Schema fornecido.

Regras obrigatórias:
1. Usa apenas referências que existam no CATÁLOGO, escritas exatamente como lá aparecem.
2. Nunca inventes referências. Se um produto não corresponder de forma inequívoca a uma
   referência do catálogo, não o incluas em `lines` e adiciona uma issue do tipo "unmatched_product".
3. Nunca inventes quantidades. Usa apenas quantidades escritas explicitamente no email, como
   número inteiro. Se a quantidade for vaga ou ausente, não incluas a linha e adiciona uma
   issue do tipo "ambiguous_quantity".
4. Identifica TODAS as linhas de encomenda presentes no email.
5. Extrai a data de entrega pedida e converte-a para YYYY-MM-DD. Uma data completa escrita
   por extenso ou noutro formato (ex.: "21 de setembro de 2026", "21/09/2026") NÃO é ambígua:
   converte-a e não adiciones issue. Usa null e adiciona uma issue do tipo
   "ambiguous_delivery_date" apenas se não houver data, se faltar o dia/mês/ano, se for vaga
   (ex.: "fim do mês", "próxima semana") ou se houver várias datas de entrega possíveis.
6. Usa o endereço do remetente como `customer_email`.
7. Sempre que houver qualquer dúvida ou ambiguidade, adiciona uma issue com `type` e `message`
   explicativa. Prefere sempre revisão humana a adivinhar.
"""


def llm_response_schema() -> dict:
    """JSON Schema do ExtractedOrder com todos os campos obrigatórios.

    Os campos com default (ex.: requested_delivery_date) não aparecem em `required`
    no schema gerado pelo Pydantic, e o Ollama deixa então o modelo omiti-los.
    Aqui passam a obrigatórios (continuam a aceitar null).
    """
    schema = ExtractedOrder.model_json_schema()
    schema["required"] = list(schema["properties"])
    for prop in schema["properties"].values():
        prop.pop("default", None)
    return schema


class LLMExtractionError(Exception):
    """A resposta do LLM não respeitou o schema esperado."""


class OllamaOrderExtractor:
    def __init__(
        self,
        base_url: str,
        model: str = "qwen3:8b",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._model = model

    async def extract(self, email: Email, catalog: list[Product]) -> ExtractedOrder:
        payload = {
            "model": self._model,
            "stream": False,
            "think": False,
            "format": llm_response_schema(),
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._user_prompt(email, catalog)},
            ],
        }
        response = await self._http.post("/api/chat", json=payload)
        response.raise_for_status()

        content = response.json()["message"]["content"]
        try:
            return ExtractedOrder.model_validate_json(content)
        except ValidationError as exc:
            raise LLMExtractionError(f"Resposta do LLM fora do schema: {exc}") from exc

    @staticmethod
    def _user_prompt(email: Email, catalog: list[Product]) -> str:
        _, sender_address = parse_sender(email.sender)
        catalog_lines = "\n".join(f"{p.reference} | {p.description} | {p.unit}" for p in catalog)
        return (
            f"CATÁLOGO (referência | descrição | unidade):\n{catalog_lines}\n\n"
            f"REMETENTE: {sender_address}\n"
            f"DATA DE RECEÇÃO: {email.received_at.date().isoformat()}\n"
            f"ASSUNTO: {email.subject}\n\n"
            f"CORPO DO EMAIL:\n{email.body}"
        )

    async def aclose(self) -> None:
        await self._http.aclose()
