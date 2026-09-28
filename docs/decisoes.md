# Decisões tomadas

Registo das decisões do projeto, pela ordem em que surgiram na conversa com a AI
([`ai-conversations/`](ai-conversations/)). **Origem** indica quem a propôs: o utilizador
(no prompt ou durante a conversa) ou a AI (durante a implementação, com aceitação do utilizador).

## Arquitetura e método

| # | Decisão | Origem | Porquê |
|---|---|---|---|
| 1 | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2.x, SQLite, httpx, pytest, Ollama `qwen3:8b` | Utilizador | Stack definida no prompt inicial. |
| 2 | TDD: teste → RED → mínimo → GREEN → refatorar | Utilizador | Cada componente foi construído assim; a conversa mostra cada ciclo. |
| 3 | Arquitetura simples, sem abstrações genéricas (sem repositório genérico, sem camadas extra) | Utilizador | Um sistema pequeno para uma empresa de 12 pessoas. |
| 4 | `uv` para dependências e Python | AI | Instala o Python 3.12 e as dependências sozinho, o que torna possível "correr com um comando num computador limpo". |

## Extração e validação

| # | Decisão | Origem | Porquê |
|---|---|---|---|
| 5 | Parser determinístico (regex) primeiro; LLM só como fallback | Utilizador | Os emails atuais têm formato regular. O LLM fica para o texto livre futuro. |
| 6 | O LLM só é chamado quando o parser **não consegue interpretar o formato** (sem linhas, sem data, data ambígua, linha não reconhecida) | Utilizador + AI | Uma referência desconhecida ou uma quantidade ≤ 0 num email bem lido vai diretamente para revisão: o LLM não pode "corrigir" dados. Erros técnicos (HTTP, BD, configuração) nunca chamam o LLM. |
| 7 | Tudo o que sai do parser ou do LLM passa pelo `OrderValidator`; o LLM nunca valida | Utilizador | Referências têm de existir no catálogo, quantidades inteiras > 0, data e cliente obrigatórios. |
| 8 | O parser extrai e não filtra: referências desconhecidas passam para o validator | AI | Uma única fonte de verdade para as regras de negócio. |
| 9 | O validator também rejeita referências repetidas e herda as issues do extractor | AI | Uma ambiguidade reportada pelo parser ou pelo LLM tem de impedir o estado `processed`. |
| 10 | Structured output do Ollama com o JSON Schema do Pydantic; sem regex nem parsing de markdown sobre a resposta | Utilizador | A resposta é validada diretamente com `model_validate_json`. |
| 11 | No schema enviado ao LLM, **todos os campos são obrigatórios** (continuam a aceitar `null`) | AI (descoberto no teste real) | Campos com default não iam para `required` e o Ollama deixava o `qwen3:8b` omitir a data. |
| 12 | Regra do prompt para datas: data completa por extenso (ex.: "21 de setembro de 2026") não é ambígua | AI (descoberto no teste real) | O modelo estava demasiado cauteloso e mandava datas explícitas para revisão. |
| 13 | `temperature=0`, `think=false` | AI | Extração deve ser reprodutível. |
| 14 | Resposta do LLM fora do schema → `needs_review`, não `failed` | AI | Com temperatura 0 repetir dá o mesmo resultado; ficaria `failed` para sempre. |

## Estados e robustez

| # | Decisão | Origem | Porquê |
|---|---|---|---|
| 15 | Estados do email: `pending` → `processed` / `needs_review` / `failed` | Utilizador + AI | `failed` é só para erros técnicos. |
| 16 | Encomendas `needs_review` também são guardadas (com as linhas extraídas) e os motivos ficam no email | AI | A pessoa que revê parte do que foi extraído, não do zero. |
| 17 | Idempotência: `source_email_id` UNIQUE e o sync salta emails que já têm encomenda | Utilizador | Um email gera no máximo uma encomenda; o sync pode repetir-se. |
| 18 | Uma sessão/transação por email; um erro num email não afeta os seguintes | Utilizador | Isolamento pedido no prompt. |
| 19 | Emails `failed` são retentados no sync seguinte | AI | Erros técnicos costumam ser transitórios (API ou Ollama em baixo). |
| 20 | Erro a obter catálogo ou emails interrompe o sync (sem LLM) | AI | Sem catálogo não é possível validar nada com segurança. |

## Cliente e anexos

| # | Decisão | Origem | Porquê |
|---|---|---|---|
| 21 | **Cliente = email do remetente** (normalizado: minúsculas, sem nome visível); no caminho do LLM, o remetente sobrepõe-se ao que o modelo devolver | Utilizador | É determinístico e vem sempre no email: a melhor forma de separar encomendas por cliente. Limitação aceite: a mesma empresa com dois endereços aparece como dois clientes (resolve-se depois com uma tabela de apelidos). |
| 22 | Não interpretar a assinatura para obter o nome da empresa | AI | Seria frágil; `customer_name` fica só informativo. |
| 23 | **Emails com anexos → `needs_review`**, por enquanto | Utilizador | Os anexos ainda não são lidos e a encomenda pode estar (também) no anexo. |
| 24 | Com anexos, o corpo continua a ser lido para pré-preencher a revisão, mas o LLM **não** é chamado | AI | O LLM só vê o corpo; o resultado podia estar incompleto e parecer certo. |

## API Ferrapex e configuração

| # | Decisão | Origem | Porquê |
|---|---|---|---|
| 25 | `GET /catalog` (CSV) e `GET /emails` (JSON), com `Authorization: Bearer` | Enunciado | Confirmado com as respostas reais da API. |
| 26 | O `Product` aceita os cabeçalhos do CSV em português (`referencia,descricao,...`) | AI | O CSV real vem em português; o domínio fica em inglês. |
| 27 | Configuração por `.env` (`pydantic-settings`); a chave nunca entra no código nem no git | Utilizador | A chave é pessoal e tem validade. |
| 28 | Mensagens claras para configuração em falta, chave inválida ou expirada (401/403) e API inacessível | AI | Quem corre num computador limpo tem de perceber o que falta. |
| 29 | A aplicação depende de `DATABASE_URL` (qualquer URL SQLAlchemy), sem tipos específicos de SQLite | Utilizador | Poder trocar de base de dados sem mudar código. |

## Interface e execução

| # | Decisão | Origem | Porquê |
|---|---|---|---|
| 30 | Interface web em Jinja2 (encomendas, detalhe, clientes, emails) que usa o mesmo service da API JSON | Utilizador | "Permite ver as encomendas guardadas". Sem dependências de frontend. |
| 31 | Comando único `uv run ferrapex` (sincroniza + abre a página); subcomandos `sync`, `orders`, `serve` | Utilizador (escolheu entre `uv` e Docker) | O enunciado exige correr com um comando a partir de um computador limpo. |
| 32 | Ollama opcional para correr o projeto | AI | Os emails atuais não precisam do LLM; um avaliador não deve ter de descarregar 5 GB. Sem Ollama, emails em texto livre ficam `failed` e são retentados. |
| 33 | Testes sem API nem Ollama reais (fakes, SQLite em memória); testes reais separados com `@pytest.mark.ollama` | Utilizador | Testes rápidos e determinísticos. |
| 34 | Conversas com a AI guardadas em `docs/ai-conversations/`, verificadas para não conterem a chave | Enunciado | "Usa AI para escrever o código e guarda as conversas." |

## Em aberto (próximos passos)

- Ler anexos (`GET /emails/{id}/attachments/{nome}`): CSV/Excel de forma determinística; PDF com extração de texto antes do fallback.
- Tabela de apelidos email → cliente para empresas com vários endereços.
- Teste real com emails em texto livre com descrições em vez de referências.
