"""Gravatar — perfil público vinculado a um e-mail (grátis, sem chave).

Muita gente esquece que tem Gravatar. Quando existe, costuma trazer nome real,
cidade, site pessoal e as redes que a pessoa cadastrou.
"""
from __future__ import annotations

import hashlib

from .base import Conector, ErroConector, Resultado


class Gravatar(Conector):
    chave = "gravatar"
    nome = "Gravatar — perfil por e-mail"
    painel = "digital"
    entrada = "email"
    descricao = "Nome, foto, cidade, site e contas vinculadas ao e-mail no Gravatar."

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        email = valor.strip().lower()
        if "@" not in email:
            raise ErroConector("Informe um e-mail válido")

        digest = hashlib.md5(email.encode()).hexdigest()
        url = f"https://www.gravatar.com/{digest}.json"

        try:
            dados = await ctx.get_json(url, headers={"Accept": "application/json"})
        except Exception:
            dados = None
        if not dados:
            return []

        perfis = dados.get("entry") or []
        saida: list[Resultado] = []
        for p in perfis:
            nome = (
                p.get("displayName")
                or (p.get("name") or {}).get("formatted")
                or email
            )
            local = p.get("currentLocation") or ""
            saida.append(
                Resultado(
                    resumo=f"{nome}" + (f" — {local}" if local else ""),
                    dados=p,
                    fonte_url=p.get("profileUrl") or url,
                )
            )
        return saida
