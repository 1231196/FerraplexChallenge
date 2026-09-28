# Ferrapex — encomendas por email

Vai buscar os emails da caixa de encomendas da Ferrapex à API, extrai cada encomenda
(cliente, linhas com referência e quantidade, data pretendida), guarda-a em SQLite e
mostra-a numa página web e na linha de comandos.

## Resumo para a avaliação

**(a) Tecnologia e porquê.** Escolhi as tecnologias com um critério principal: ser simples e
funcional. Python 3.12 com FastAPI, Pydantic, SQLAlchemy 2.x e SQLite; páginas em Jinja2 sem
frameworks de frontend; `uv` para instalar tudo com um comando; Ollama com `qwen3:8b`, local e
opcional, só para o texto livre. A alternativa que pus de lado foi o **Docker**
(`docker compose up` com a app e o Ollama). Perdeu por ser mais pesado para quem avalia: exige
o Docker instalado e descarregar o modelo (~5 GB), quando os emails atuais nem precisam do LLM.
Com `uv run ferrapex` basta o `uv`, que trata do próprio Python.

**(b) Como correr, do zero.** Ver [Correr](#correr): instalar o `uv`, `cp .env.example .env`
com a chave e `uv run ferrapex`.

**(c) O que a AI escreveu, o que corrigi à mão e em que ainda não confio.** Usei o Claude Code
para tudo: código, testes, templates e documentação. Fi-lo de propósito, porque este não é um
sistema crítico: corre localmente e não tem autenticação, utilizadores nem nada do género. À
mão só configurei o `.env` com a chave da API. Os textos (README, decisões e prompts) foram
escritos por mim e melhorados pelo Claude Code. As conversas estão em
[`docs/ai-conversations/`](docs/ai-conversations/) e as decisões em
[`docs/decisoes.md`](docs/decisoes.md).

**(d) Uma decisão em que não segui a sugestão da AI.** A AI sugeriu usar o LLM para fazer a
avaliação das encomendas. Preferi manter o funcionamento determinístico: primeiro o regex; o
LLM só como segunda via, quando o regex não consegue ler o email; e, quando o LLM é usado, o
resultado volta a passar por verificações determinísticas (regex e regras de negócio) antes de
ser aceite. A avaliação com exemplos confirmou esta escolha: só com o prompt, o `qwen3:8b`
inventou quantidades e datas, apesar das instruções, e as verificações determinísticas
apanharam esses casos (15/21 → 22/22).

Usei o `qwen3:8b` para ter um LLM local como segunda via. Com um modelo maior (Gemini, GPT ou
Claude), penso que os resultados seriam excelentes, sobretudo no texto livre e no mapeamento de
descrições para referências. Trocar de modelo só mexe no extractor
(`app/extraction/ollama.py`); o resto do pipeline, incluindo as verificações determinísticas,
mantém-se igual.

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
| `uv run ferrapex orders --customer <email>` | só as encomendas de um cliente |
| `uv run ferrapex serve` | só arranca a página web |
| `uv run ferrapex --no-browser` / `--port 8080` | opções |

A página web tem:

- a lista de encomendas, com o botão **Sincronizar emails**;
- o detalhe de cada encomenda: linhas, motivos de revisão e email original;
- os clientes e as respetivas encomendas;
- os emails, com o estado de processamento.

A API JSON (`POST /sync`, `GET /orders?customer_email=`, `GET /orders/{id}`) está
documentada em `/docs`.

## Como funciona

```text
API Ferrapex → DeterministicOrderParser (regex) → OrderValidator ─ válido ──→ processed
                        │ não consegue interpretar o formato        └ issues → needs_review
                        ▼
               OllamaOrderExtractor (qwen3:8b)
                        ▼
               OrderValidator + verificação de evidência no texto (regex)
                        ├ válido ─→ processed
                        └ issues → needs_review
```

- **Parser determinístico primeiro.** Os emails atuais têm um formato regular
  (`Para entrega a AAAA-MM-DD` + linhas `REFERENCIA | QUANTIDADE`) e são lidos com regex.
- **LLM só como fallback.** Serve para os futuros emails em texto livre, com descrições em vez
  de referências. Só é chamado quando o parser não consegue interpretar o email. Nunca é
  chamado por erros técnicos (HTTP, base de dados, configuração) nem para "corrigir" referências
  ou quantidades de um email bem lido. Usa structured output com JSON Schema.
- **O LLM tem de mostrar evidência.** Nos testes, o `qwen3:8b` inventou quantidades e datas e
  mapeou produtos inexistentes, apesar do prompt. O resultado do LLM passa por verificações
  determinísticas: a quantidade e a data têm de estar escritas no email, e nenhuma referência
  escrita pode faltar. Uma referência inferida de uma descrição fica como sugestão para
  revisão humana.
- **Tudo é validado.** O resultado do parser e o do LLM passam sempre pelo `OrderValidator`:
  referências existentes no catálogo, quantidades inteiras positivas, data de entrega e cliente
  presentes. O LLM nunca é usado como validador.
- **Cliente = email do remetente.** É determinístico e vem sempre no email: o endereço é
  normalizado (minúsculas, sem o nome visível) e, no caminho do LLM, o remetente sobrepõe-se
  ao que o modelo devolver. O nome (`customer_name`) é só informativo.
- **Anexos vão para revisão.** Por enquanto os anexos não são lidos. Um email com anexos fica
  `needs_review`: o corpo é lido na mesma para pré-preencher a encomenda, mas o LLM não é
  chamado, porque não vê o anexo e o resultado podia ficar incompleto.
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

### Avaliação com exemplos

```bash
uv run python scripts/evaluate_examples.py
```

Corre 22 emails de exemplo pelo pipeline real, com o `qwen3:8b`: formato atual, gralhas,
anexos, texto livre, descrições, inglês, ambiguidades e omissões. O relatório fica em
[`docs/avaliacao-exemplos.md`](docs/avaliacao-exemplos.md).

## Estrutura

```text
app/
├── cli.py                  comando `ferrapex`
├── main.py                 FastAPI (API JSON)
├── web/                    páginas Jinja2
├── api/ferrapex_client.py  cliente HTTP da API Ferrapex
├── domain/                 modelos Pydantic (Email, Product, ExtractedOrder)
├── extraction/             parser determinístico, extractor Ollama, política de fallback
├── validation/             OrderValidator e verificação de evidência (grounding)
├── services/               OrderImportService (pipeline de sincronização)
└── persistence/            SQLAlchemy: modelos e repositórios
tests/fixtures/             emails e catálogo de exemplo reais da API
scripts/                    avaliação com exemplos contra o LLM real
docs/avaliacao-exemplos.md  resultado da avaliação
docs/decisoes.md            registo das decisões tomadas
docs/ai-conversations/      conversas com a AI usadas para construir o projeto
```
