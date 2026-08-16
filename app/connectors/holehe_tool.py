"""holehe — descobre em quais serviços um e-mail tem cadastro.

Ferramenta local (CLI). Não faz login em lugar nenhum: usa a resposta pública
do fluxo de "esqueci minha senha" de cada site.
"""
from __future__ import annotations

import re

from .base import Conector, ErroConector, Resultado

LINHA_POSITIVA = re.compile(r"^\s*\[\+\]\s+(\S+)", re.MULTILINE)


class Holehe(Conector):
    chave = "holehe"
    nome = "holehe — contas por e-mail"
    painel = "digital"
    entrada = "email"
    descricao = (
        "Varre ~120 serviços (redes, e-commerce, apps) e lista onde aquele "
        "e-mail tem cadastro ativo."
    )
    local = True
    requer_binario = "holehe"

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        email = valor.strip().lower()
        if "@" not in email:
            raise ErroConector("Informe um e-mail válido")

        codigo, saida_txt, erro_txt = await ctx.rodar(
            ["holehe", "--only-used", "--no-color", "--no-clear", email],
            timeout=110,
        )
        if codigo != 0 and not saida_txt.strip():
            raise ErroConector(erro_txt.strip()[:300] or "holehe falhou sem mensagem")

        sites = sorted({m.group(1).strip() for m in LINHA_POSITIVA.finditer(saida_txt)})
        if not sites:
            return []

        return [
            Resultado(
                resumo=f"Cadastro encontrado em {site}",
                dados={"servico": site, "email": email, "ferramenta": "holehe"},
                fonte_url=f"https://{site}" if "." in site else None,
            )
            for site in sites
        ]
