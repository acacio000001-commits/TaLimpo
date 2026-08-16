"""Trilha de auditoria — toda consulta a dado pessoal fica registrada.

Isso não é enfeite: é o que demonstra finalidade e base legal exigidas pela
LGPD quando o dossiê for questionado.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from . import db


def _ip(req: Request | None) -> str | None:
    if req is None:
        return None
    encaminhado = req.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return req.client.host if req.client else None


async def registrar(
    *,
    usuario_id: int | None,
    acao: str,
    entidade: str | None = None,
    entidade_id: Any = None,
    alvo_valor: str | None = None,
    detalhes: dict | None = None,
    req: Request | None = None,
) -> None:
    await db.executar(
        """
        INSERT INTO auditoria
            (usuario_id, acao, entidade, entidade_id, alvo_valor, ip, user_agent, detalhes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            usuario_id,
            acao,
            entidade,
            str(entidade_id) if entidade_id is not None else None,
            alvo_valor,
            _ip(req),
            (req.headers.get("user-agent") if req else None),
            json.dumps(detalhes or {}, ensure_ascii=False, default=str),
        ),
    )
