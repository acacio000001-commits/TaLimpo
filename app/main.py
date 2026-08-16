"""Ponto de entrada: sobe o banco, sincroniza as fontes e serve os painéis."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config, connectors, db, security
from .auth import router as router_auth
from .routers.admin import router as router_admin
from .routers.buscas import router as router_buscas
from .routers.casos import router as router_casos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("osint")


async def _migrar() -> None:
    caminho = config.DIR_DB / "001_schema.sql"
    await db.executar_script(caminho.read_text(encoding="utf-8"))
    log.info("Esquema aplicado")


async def _sincronizar_fontes() -> None:
    """Espelha o registro de conectores na tabela `fontes`.

    Fonte que sumiu do código fica marcada como indisponível em vez de ser
    apagada — assim o histórico de consultas antigas não perde a referência.
    """
    registro = connectors.carregar()
    for con in registro.values():
        ok, _ = con.disponivel()
        await db.executar(
            """
            INSERT INTO fontes (chave, nome, painel, entrada, descricao,
                                requer_credencial, disponivel, custo, atualizada_em)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (chave) DO UPDATE SET
                nome = EXCLUDED.nome,
                painel = EXCLUDED.painel,
                entrada = EXCLUDED.entrada,
                descricao = EXCLUDED.descricao,
                requer_credencial = EXCLUDED.requer_credencial,
                disponivel = EXCLUDED.disponivel,
                custo = EXCLUDED.custo,
                atualizada_em = now()
            """,
            (
                con.chave, con.nome, con.painel, con.entrada, con.descricao,
                list(con.requer_credencial), ok, con.custo,
            ),
        )

    if registro:
        # 'importacao_manual' não vem de conector nenhum: é alimentada à mão
        # pelo painel de Casos, então fica de fora da varredura.
        await db.executar(
            "UPDATE fontes SET disponivel = false "
            "WHERE chave <> ALL(%s) AND chave <> 'importacao_manual'",
            (list(registro.keys()),),
        )
    log.info("Fontes sincronizadas: %d conector(es)", len(registro))


async def _criar_admin_inicial() -> None:
    if not (config.ADMIN_EMAIL and config.ADMIN_SENHA):
        return
    existe = await db.buscar_um("SELECT 1 FROM usuarios LIMIT 1")
    if existe:
        return

    perfil = await db.buscar_um("SELECT id FROM perfis WHERE chave = 'admin'")
    await db.executar(
        "INSERT INTO usuarios (nome, email, senha_hash, perfil_id) VALUES (%s, %s, %s, %s)",
        (
            config.ADMIN_NOME,
            config.ADMIN_EMAIL,
            security.gerar_hash(config.ADMIN_SENHA),
            perfil["id"],
        ),
    )
    log.warning("Administrador inicial criado: %s — troque a senha no primeiro acesso",
                config.ADMIN_EMAIL)


@asynccontextmanager
async def ciclo(app: FastAPI):
    app.state.erro_boot = None
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=15.0),
        follow_redirects=True,
        headers={"User-Agent": config.USER_AGENT},
    )
    try:
        await db.abrir()
        await _migrar()
        await _sincronizar_fontes()
        await _criar_admin_inicial()
    except Exception as e:
        # Não derruba o processo: o Render reiniciaria em loop e o healthcheck
        # nunca contaria a causa. Melhor subir e explicar em /api/saude.
        app.state.erro_boot = f"{type(e).__name__}: {e}"
        log.exception("Falha ao iniciar o banco")

    yield

    await app.state.http.aclose()
    await db.fechar()


app = FastAPI(
    title="OSINT Detetive",
    version=__version__,
    description="Painéis de investigação sobre fontes públicas, com trilha de auditoria.",
    lifespan=ciclo,
)

if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/api/saude", tags=["infra"])
async def saude():
    if app.state.erro_boot:
        return JSONResponse(
            {"ok": False, "banco": "erro", "detalhe": app.state.erro_boot}, status_code=503
        )
    try:
        await db.buscar_um("SELECT 1 AS ok")
        banco = "ok"
    except Exception as e:
        return JSONResponse(
            {"ok": False, "banco": "erro", "detalhe": str(e)}, status_code=503
        )
    return {
        "ok": True,
        "versao": __version__,
        "banco": banco,
        "conectores": len(connectors.REGISTRO),
    }


app.include_router(router_auth)
app.include_router(router_buscas)
app.include_router(router_casos)
app.include_router(router_admin)


@app.get("/", include_in_schema=False)
async def raiz():
    return FileResponse(config.DIR_WEB / "index.html")


# Estáticos por último para não engolir as rotas /api.
if config.DIR_WEB.exists():
    app.mount("/", StaticFiles(directory=str(config.DIR_WEB), html=True), name="web")
