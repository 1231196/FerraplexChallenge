# Ferrapex — encomendas por email

Vai buscar os emails da caixa de encomendas da Ferrapex à API, extrai cada encomenda
(cliente, linhas com referência e quantidade, data pretendida), guarda-a em SQLite e
mostra-a numa página web e na linha de comandos.

## Correr

Pré-requisito: [uv](https://docs.astral.sh/uv/). Trata do Python 3.12 e das dependências.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # só se ainda não tiveres uv
```

Na pasta do projeto, cria o `.env` com a tua chave:

```bash
cp .env.example .env        # depois edita FERRAPEX_API_KEY=<a tua chave>
```

E corre:

```bash
uv run ferrapex
```

Isto instala tudo, cria a base de dados em `data/ferrapex.db`, importa os emails da API
e abre a página web em http://127.0.0.1:8000.

### Outros comandos

| Comando | O que faz |
|---|---|
| `uv run ferrapex` | sincroniza e abre a página web |
| `uv run ferrapex sync` | só sincroniza (pode repetir-se: cada email gera no máximo uma encomenda) |
| `uv run ferrapex orders` | lista as encomendas na linha de comandos |
| `uv run ferrapex serve` | só arranca a página web |
| `uv run ferrapex --no-browser` / `--port 8080` | opções |

Na página web: lista de encomendas com botão **Sincronizar emails**, detalhe de cada encomenda
(linhas, motivos de revisão, email original) e lista de emails com o estado de processamento.
A API JSON (`POST /sync`, `GET /orders`, `GET /orders/{id}`) está documentada em `/docs`.

## Como funciona

```text
API Ferrapex → DeterministicOrderParser → OrderValidator ─ válido ─────────────→ processed
                        │ não consegue interpretar o formato
                        ▼
               OllamaOrderExtractor (qwen3:8b) → OrderValidator ─ válido → processed
                                                                └ issues → needs_review
```

- **Parser determinístico primeiro.** Os emails atuais têm um formato regular
  (`Para entrega a AAAA-MM-DD` + linhas `REFERENCIA | QUANTIDADE`) e são lidos com regex.
- **LLM só como fallback.** Serve para os futuros emails em texto livre, com descrições em vez
  de referências. Só é chamado quando o parser não consegue interpretar o email. Nunca é
  chamado por erros técnicos (HTTP, base de dados, configuração) nem para "corrigir" referências
  ou quantidades de um email bem lido. Usa structured output com JSON Schema.
- **Tudo é validado.** O resultado do parser e o do LLM passam sempre pelo `OrderValidator`:
  referências existentes no catálogo, quantidades inteiras positivas, data de entrega e cliente
  presentes. O LLM nunca é usado como validador.
- **Na dúvida, revisão humana.** Uma encomenda com qualquer problema fica `needs_review`, com
  os motivos guardados e visíveis na página.
- **Idempotente e isolado.** `source_email_id` é único. Um erro técnico num email marca-o como
  `failed`, não impede os restantes, e o email volta a ser tentado no próximo sync.

### Ollama (opcional)

Os emails atuais não precisam do LLM. Para ativar o fallback para texto livre:

```bash
ollama pull qwen3:8b
```

Sem Ollama, um email que o parser não entenda fica `failed` e é retentado no sync seguinte.
Os restantes emails não são afetados.

## Configuração (`.env`)

| Variável | Default |
|---|---|
| `FERRAPEX_API_BASE_URL` | `https://challenge.tailormatics.ai/api/challenge` |
| `FERRAPEX_API_KEY` | — (obrigatória, pessoal e com validade) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `qwen3:8b` |
| `DATABASE_URL` | `sqlite:///./data/ferrapex.db` (qualquer URL SQLAlchemy) |

## Testes

```bash
uv run pytest             # unitários + integração (API e Ollama simulados, SQLite em memória)
uv run pytest -m ollama   # contra um Ollama real com qwen3:8b
```

## Estrutura

```text
app/
├── cli.py                  comando `ferrapex`
├── main.py                 FastAPI (API JSON)
├── web/                    páginas Jinja2
├── api/ferrapex_client.py  cliente HTTP da API Ferrapex
├── domain/                 modelos Pydantic (Email, Product, ExtractedOrder)
├── extraction/             parser determinístico, extractor Ollama, política de fallback
├── validation/             OrderValidator
├── services/               OrderImportService (pipeline de sincronização)
└── persistence/            SQLAlchemy: modelos e repositórios
tests/fixtures/             emails e catálogo de exemplo reais da API
docs/ai-conversations/      conversas com a AI usadas para construir o projeto
```
