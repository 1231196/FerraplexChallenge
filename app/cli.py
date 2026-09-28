"""Ponto de entrada `ferrapex`.

    ferrapex           sincroniza e abre a página web (http://127.0.0.1:8000)
    ferrapex sync      só sincroniza
    ferrapex orders    lista as encomendas guardadas
    ferrapex serve     só arranca a página web
"""

import argparse
import asyncio
import sys
import threading
import webbrowser

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.dependencies import get_session_factory, import_service
from app.persistence.repositories import OrderRepository

HOST = "127.0.0.1"


class ConfigError(Exception):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ferrapex", description="Importação de encomendas Ferrapex.")
    parser.add_argument("command", nargs="?", default="start", choices=["start", "sync", "orders", "serve"])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="não abrir o browser automaticamente")
    args = parser.parse_args(argv)

    try:
        _check_config()
        if args.command == "orders":
            _print_orders()
            return 0
        if args.command in ("start", "sync"):
            ok = _sync()
            if args.command == "sync":
                return 0 if ok else 1
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    url = f"http://{HOST}:{args.port}"
    print(f"\nPágina web em {url}  (Ctrl+C para terminar)")
    if not args.no_browser:
        open_browser(url)
    run_server(HOST, args.port)
    return 0


def _check_config() -> None:
    try:
        get_settings()
    except ValidationError as exc:
        missing = ", ".join(str(e["loc"][0]).upper() for e in exc.errors())
        raise ConfigError(
            f"Configuração em falta: {missing}.\n"
            "Copia o ficheiro de exemplo e preenche a tua chave:\n"
            "    cp .env.example .env\n"
            "    # editar .env -> FERRAPEX_API_KEY=<a tua chave>"
        ) from exc


def _sync() -> bool:
    print("A sincronizar emails da API Ferrapex…")
    try:
        result = asyncio.run(_run_sync())
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        hint = " — chave inválida ou expirada (FERRAPEX_API_KEY no .env)" if code in (401, 403) else ""
        print(f"A API respondeu {code}{hint}.", file=sys.stderr)
        return False
    except httpx.RequestError as exc:
        print(f"Não foi possível contactar a API: {exc!r}", file=sys.stderr)
        return False

    print(
        f"  recebidos: {result.fetched} | processadas: {result.processed} | "
        f"para revisão: {result.needs_review} | falhadas: {result.failed} | já importadas: {result.skipped}"
    )
    return True


async def _run_sync():
    async with import_service(get_session_factory()) as service:
        return await service.sync()


def _print_orders() -> None:
    with get_session_factory()() as session:
        orders = OrderRepository(session).get_all()
        if not orders:
            print("Ainda não há encomendas. Corre `uv run ferrapex sync`.")
            return
        for o in orders:
            lines = ", ".join(f"{l.product_reference} x {l.quantity}" for l in o.lines)
            print(
                f"#{o.id:<3} {o.source_email_id:<8} {o.status:<13} {o.requested_delivery_date or '—'!s:<11} "
                f"{o.customer_name or o.customer_email}\n      {lines or '(sem linhas)'}"
            )


def open_browser(url: str) -> None:
    # Pequeno atraso para o servidor já estar a aceitar ligações.
    threading.Timer(1.0, webbrowser.open, args=[url]).start()


def run_server(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port)


if __name__ == "__main__":
    sys.exit(main())
