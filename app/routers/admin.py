"""Painel administrativo: equipe, perfis, fontes e auditoria."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import audit, db, security
from ..auth import exige_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class EntradaUsuario(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=200)
    senha: str = Field(min_length=8, max_length=200)
    perfil: str = "investigador"


class TrocaSenha(BaseModel):
    senha: str = Field(min_length=8, max_length=200)


class EstadoFonte(BaseModel):
    ativa: bool


# ------------------------------------------------------------------ equipe
@router.get("/usuarios")
async def listar_usuarios(usuario: dict = Depends(exige_admin)):
    return await db.buscar_todos(
        """
        SELECT u.id, u.nome, u.email, u.ativo, u.criado_em, u.ultimo_login,
               p.chave AS perfil, p.nome AS perfil_nome
        FROM usuarios u JOIN perfis p ON p.id = u.perfil_id
        ORDER BY u.nome
        """
    )


@router.post("/usuarios")
async def criar_usuario(dados: EntradaUsuario, request: Request, usuario: dict = Depends(exige_admin)):
    perfil = await db.buscar_um("SELECT id FROM perfis WHERE chave = %s", (dados.perfil,))
    if not perfil:
        raise HTTPException(400, f"Perfil '{dados.perfil}' não existe")

    existe = await db.buscar_um(
        "SELECT 1 FROM usuarios WHERE lower(email) = lower(%s)", (dados.email,)
    )
    if existe:
        raise HTTPException(409, "Já existe usuário com esse e-mail")

    linha = await db.buscar_um(
        """
        INSERT INTO usuarios (nome, email, senha_hash, perfil_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id, nome, email, ativo, criado_em
        """,
        (dados.nome, dados.email.strip(), security.gerar_hash(dados.senha), perfil["id"]),
    )
    await audit.registrar(
        usuario_id=usuario["id"], acao="usuario_criado", entidade="usuario",
        entidade_id=linha["id"], detalhes={"perfil": dados.perfil}, req=request,
    )
    return linha


@router.patch("/usuarios/{usuario_id}/ativo")
async def alternar_ativo(usuario_id: int, request: Request, usuario: dict = Depends(exige_admin)):
    if usuario_id == usuario["id"]:
        raise HTTPException(400, "Você não pode desativar a si mesmo")

    linha = await db.buscar_um(
        "UPDATE usuarios SET ativo = NOT ativo WHERE id = %s RETURNING id, nome, ativo",
        (usuario_id,),
    )
    if not linha:
        raise HTTPException(404, "Usuário não encontrado")
    if not linha["ativo"]:
        await db.executar("DELETE FROM sessoes WHERE usuario_id = %s", (usuario_id,))

    await audit.registrar(
        usuario_id=usuario["id"], acao="usuario_ativo_alterado", entidade="usuario",
        entidade_id=usuario_id, detalhes={"ativo": linha["ativo"]}, req=request,
    )
    return linha


@router.patch("/usuarios/{usuario_id}/senha")
async def trocar_senha(
    usuario_id: int, dados: TrocaSenha, request: Request, usuario: dict = Depends(exige_admin)
):
    linha = await db.buscar_um(
        "UPDATE usuarios SET senha_hash = %s WHERE id = %s RETURNING id, nome",
        (security.gerar_hash(dados.senha), usuario_id),
    )
    if not linha:
        raise HTTPException(404, "Usuário não encontrado")
    await db.executar("DELETE FROM sessoes WHERE usuario_id = %s", (usuario_id,))
    await audit.registrar(
        usuario_id=usuario["id"], acao="senha_alterada", entidade="usuario",
        entidade_id=usuario_id, req=request,
    )
    return linha


@router.get("/perfis")
async def listar_perfis(usuario: dict = Depends(exige_admin)):
    return await db.buscar_todos(
        """
        SELECT p.id, p.chave, p.nome, p.descricao,
               COALESCE(array_agg(pp.painel) FILTER (WHERE pp.painel IS NOT NULL), '{}') AS paineis
        FROM perfis p
        LEFT JOIN perfil_paineis pp ON pp.perfil_id = p.id
        GROUP BY p.id ORDER BY p.id
        """
    )


# ------------------------------------------------------------------ fontes
@router.get("/fontes")
async def listar_fontes(usuario: dict = Depends(exige_admin)):
    return await db.buscar_todos("SELECT * FROM fontes ORDER BY painel, nome")


@router.patch("/fontes/{chave}")
async def alternar_fonte(
    chave: str, dados: EstadoFonte, request: Request, usuario: dict = Depends(exige_admin)
):
    linha = await db.buscar_um(
        "UPDATE fontes SET ativa = %s, atualizada_em = now() WHERE chave = %s RETURNING *",
        (dados.ativa, chave),
    )
    if not linha:
        raise HTTPException(404, "Fonte não encontrada")
    await audit.registrar(
        usuario_id=usuario["id"], acao="fonte_alterada", entidade="fonte",
        entidade_id=chave, detalhes={"ativa": dados.ativa}, req=request,
    )
    return linha


# --------------------------------------------------------------- auditoria
@router.get("/auditoria")
async def listar_auditoria(
    limite: int = 100,
    usuario_id: int | None = None,
    acao: str | None = None,
    usuario: dict = Depends(exige_admin),
):
    limite = max(1, min(limite, 500))
    condicoes, params = [], []
    if usuario_id:
        condicoes.append("a.usuario_id = %s")
        params.append(usuario_id)
    if acao:
        condicoes.append("a.acao = %s")
        params.append(acao)
    onde = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    params.append(limite)

    return await db.buscar_todos(
        f"""
        SELECT a.*, u.nome AS usuario_nome
        FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id
        {onde}
        ORDER BY a.criado_em DESC LIMIT %s
        """,
        params,
    )
