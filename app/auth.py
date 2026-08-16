"""Login por sessão, perfis e controle de acesso por painel."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from . import audit, config, db, security

router = APIRouter(prefix="/api/auth", tags=["acesso"])


# ------------------------------------------------------------------ modelos
class EntradaLogin(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    senha: str = Field(min_length=1, max_length=200)


# ------------------------------------------------------------- dependências
async def usuario_opcional(request: Request) -> dict | None:
    token = request.cookies.get(config.COOKIE_NOME)
    if not token:
        cabecalho = request.headers.get("authorization", "")
        if cabecalho.lower().startswith("bearer "):
            token = cabecalho[7:].strip()
    if not token:
        return None

    linha = await db.buscar_um(
        """
        SELECT u.id, u.nome, u.email, u.ativo,
               p.chave AS perfil, p.nome AS perfil_nome,
               s.id AS sessao_id, s.expira_em
        FROM sessoes s
        JOIN usuarios u ON u.id = s.usuario_id
        JOIN perfis   p ON p.id = u.perfil_id
        WHERE s.token_hash = %s AND s.expira_em > now()
        """,
        (security.hash_token(token),),
    )
    if not linha or not linha["ativo"]:
        return None

    linha["paineis"] = [
        r["painel"]
        for r in await db.buscar_todos(
            """
            SELECT pp.painel FROM perfil_paineis pp
            JOIN perfis p ON p.id = pp.perfil_id
            WHERE p.chave = %s
            """,
            (linha["perfil"],),
        )
    ]
    return linha


async def usuario_atual(usuario: dict | None = Depends(usuario_opcional)) -> dict:
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada ou inexistente")
    return usuario


def exige_painel(painel: str):
    """Dependência que trava a rota a quem tem o painel liberado no perfil."""

    async def _checar(usuario: dict = Depends(usuario_atual)) -> dict:
        if painel not in usuario["paineis"] and "admin" not in usuario["paineis"]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Seu perfil não tem acesso ao painel '{painel}'",
            )
        return usuario

    return _checar


exige_admin = exige_painel("admin")


# ------------------------------------------------------------------- rotas
@router.post("/login")
async def login(dados: EntradaLogin, request: Request, response: Response):
    usuario = await db.buscar_um(
        """
        SELECT u.id, u.nome, u.email, u.senha_hash, u.ativo, p.chave AS perfil
        FROM usuarios u JOIN perfis p ON p.id = u.perfil_id
        WHERE lower(u.email) = lower(%s)
        """,
        (dados.email.strip(),),
    )

    if not usuario or not security.conferir_senha(dados.senha, usuario["senha_hash"]):
        await audit.registrar(
            usuario_id=usuario["id"] if usuario else None,
            acao="login_negado",
            entidade="usuario",
            alvo_valor=dados.email.strip(),
            req=request,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")

    if not usuario["ativo"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuário desativado")

    token = security.novo_token()
    expira = datetime.now(timezone.utc) + timedelta(hours=config.SESSION_TTL_HORAS)

    await db.executar(
        """
        INSERT INTO sessoes (id, usuario_id, token_hash, ip, user_agent, expira_em)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            uuid.uuid4(),
            usuario["id"],
            security.hash_token(token),
            (request.client.host if request.client else None),
            request.headers.get("user-agent"),
            expira,
        ),
    )
    await db.executar("UPDATE usuarios SET ultimo_login = now() WHERE id = %s", (usuario["id"],))
    await db.executar("DELETE FROM sessoes WHERE expira_em < now()")

    response.set_cookie(
        key=config.COOKIE_NOME,
        value=token,
        httponly=True,
        secure=config.COOKIE_SEGURO,
        samesite="none" if config.COOKIE_SEGURO else "lax",
        max_age=config.SESSION_TTL_HORAS * 3600,
        path="/",
    )

    await audit.registrar(
        usuario_id=usuario["id"], acao="login", entidade="usuario",
        entidade_id=usuario["id"], req=request,
    )

    paineis = [
        r["painel"]
        for r in await db.buscar_todos(
            "SELECT pp.painel FROM perfil_paineis pp JOIN perfis p ON p.id = pp.perfil_id "
            "WHERE p.chave = %s",
            (usuario["perfil"],),
        )
    ]
    return {
        "token": token,
        "usuario": {
            "id": usuario["id"],
            "nome": usuario["nome"],
            "email": usuario["email"],
            "perfil": usuario["perfil"],
            "paineis": paineis,
        },
    }


@router.post("/logout")
async def logout(request: Request, response: Response, usuario: dict = Depends(usuario_atual)):
    await db.executar("DELETE FROM sessoes WHERE id = %s", (usuario["sessao_id"],))
    response.delete_cookie(config.COOKIE_NOME, path="/")
    await audit.registrar(usuario_id=usuario["id"], acao="logout", req=request)
    return {"ok": True}


@router.get("/eu")
async def eu(usuario: dict = Depends(usuario_atual)):
    return {
        "id": usuario["id"],
        "nome": usuario["nome"],
        "email": usuario["email"],
        "perfil": usuario["perfil"],
        "perfil_nome": usuario["perfil_nome"],
        "paineis": usuario["paineis"],
    }
