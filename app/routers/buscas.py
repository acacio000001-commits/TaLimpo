"""Execução das buscas: lista de fontes e disparo de consulta.

O front chama /api/buscar uma vez por fonte, em paralelo, e vai preenchendo os
cards conforme cada uma responde — é o que dá a sensação de resultado ao vivo
sem precisar de WebSocket (que não sobrevive ao sleep do free tier).
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import audit, connectors, db
from ..auth import usuario_atual
from ..connectors.base import Contexto, ErroConector

router = APIRouter(prefix="/api", tags=["buscas"])


class EntradaBusca(BaseModel):
    fonte: str = Field(min_length=1, max_length=80)
    valor: str = Field(min_length=1, max_length=300)
    caso_id: int | None = None
    alvo_id: int | None = None


@router.get("/fontes")
async def listar_fontes(usuario: dict = Depends(usuario_atual)):
    """Fontes visíveis para o perfil, já com o estado de disponibilidade."""
    ligadas = {
        r["chave"]: r["ativa"]
        for r in await db.buscar_todos("SELECT chave, ativa FROM fontes")
    }
    admin = "admin" in usuario["paineis"]

    saida = []
    for con in connectors.listar():
        if not admin and con.painel not in usuario["paineis"]:
            continue
        item = con.como_dict()
        item["ativa"] = ligadas.get(con.chave, True)
        saida.append(item)
    return saida


@router.post("/buscar")
async def buscar(dados: EntradaBusca, request: Request, usuario: dict = Depends(usuario_atual)):
    conector = connectors.obter(dados.fonte)
    if conector is None:
        raise HTTPException(404, f"Fonte '{dados.fonte}' não existe")

    if conector.painel not in usuario["paineis"] and "admin" not in usuario["paineis"]:
        raise HTTPException(403, f"Sem acesso ao painel '{conector.painel}'")

    ligada = await db.buscar_um("SELECT ativa FROM fontes WHERE chave = %s", (dados.fonte,))
    if ligada and not ligada["ativa"]:
        raise HTTPException(409, "Fonte desligada pelo administrador")

    ok, motivo = conector.disponivel()
    if not ok:
        raise HTTPException(409, motivo)

    valor = dados.valor.strip()

    # Abre a consulta antes de executar: mesmo se a fonte cair, fica registrado
    # quem procurou o quê e quando.
    linha = await db.buscar_um(
        """
        INSERT INTO consultas (caso_id, alvo_id, fonte_chave, entrada, usuario_id)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
        """,
        (dados.caso_id, dados.alvo_id, dados.fonte, valor, usuario["id"]),
    )
    consulta_id = linha["id"]

    await audit.registrar(
        usuario_id=usuario["id"],
        acao="busca",
        entidade="consulta",
        entidade_id=consulta_id,
        alvo_valor=valor,
        detalhes={"fonte": dados.fonte, "caso_id": dados.caso_id},
        req=request,
    )

    inicio = time.perf_counter()
    ctx = Contexto(request.app.state.http)

    try:
        achados = await conector.executar(valor, ctx)
    except ErroConector as e:
        await _fechar(consulta_id, "erro", inicio, str(e))
        raise HTTPException(422, str(e))
    except Exception as e:  # fonte fora do ar, timeout de rede, etc.
        await _fechar(consulta_id, "erro", inicio, f"{type(e).__name__}: {e}")
        raise HTTPException(502, f"A fonte não respondeu: {type(e).__name__}")

    for achado in achados:
        await db.executar(
            """
            INSERT INTO resultados (consulta_id, resumo, dados, fonte_url)
            VALUES (%s, %s, %s::jsonb, %s)
            """,
            (
                consulta_id,
                achado.resumo[:2000],
                json.dumps(achado.dados, ensure_ascii=False, default=str),
                achado.fonte_url,
            ),
        )

    await _fechar(consulta_id, "ok" if achados else "vazio", inicio, None)

    return {
        "consulta_id": consulta_id,
        "fonte": dados.fonte,
        "fonte_nome": conector.nome,
        "status": "ok" if achados else "vazio",
        "duracao_ms": int((time.perf_counter() - inicio) * 1000),
        "resultados": [
            {"resumo": a.resumo, "dados": a.dados, "fonte_url": a.fonte_url} for a in achados
        ],
    }


@router.get("/consultas")
async def listar_consultas(
    caso_id: int | None = None,
    limite: int = 50,
    usuario: dict = Depends(usuario_atual),
):
    limite = max(1, min(limite, 200))
    if caso_id:
        return await db.buscar_todos(
            "SELECT * FROM vw_consultas_detalhe WHERE caso_id = %s "
            "ORDER BY iniciada_em DESC LIMIT %s",
            (caso_id, limite),
        )
    return await db.buscar_todos(
        "SELECT * FROM vw_consultas_detalhe ORDER BY iniciada_em DESC LIMIT %s",
        (limite,),
    )


@router.get("/consultas/{consulta_id}/resultados")
async def resultados_da_consulta(consulta_id: int, usuario: dict = Depends(usuario_atual)):
    return await db.buscar_todos(
        "SELECT id, resumo, dados, fonte_url, coletado_em FROM resultados "
        "WHERE consulta_id = %s ORDER BY id",
        (consulta_id,),
    )


@router.get("/numeros")
async def numeros(usuario: dict = Depends(usuario_atual)):
    return await db.buscar_um("SELECT * FROM vw_painel_numeros")


async def _fechar(consulta_id: int, status: str, inicio: float, erro: str | None) -> None:
    await db.executar(
        """
        UPDATE consultas
           SET status = %s, concluida_em = now(), duracao_ms = %s, erro = %s
         WHERE id = %s
        """,
        (status, int((time.perf_counter() - inicio) * 1000), erro, consulta_id),
    )
