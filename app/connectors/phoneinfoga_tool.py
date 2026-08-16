"""phoneinfoga — reconhecimento de número de telefone.

Ferramenta local (CLI). Devolve país, operadora, tipo de linha e as buscas
sugeridas em mecanismos públicos.
"""
from __future__ import annotations

import re

from .base import Conector, ErroConector, Resultado, so_digitos

CAMPO = re.compile(r"^\s*([A-Za-z][A-Za-z /]+):\s*(.+?)\s*$", re.MULTILINE)


class PhoneInfoga(Conector):
    chave = "phoneinfoga"
    nome = "phoneinfoga — telefone"
    painel = "digital"
    entrada = "telefone"
    descricao = (
        "Valida o número, identifica país, operadora, tipo de linha e monta as "
        "buscas públicas (Google, redes, classificados) para aquele número."
    )
    local = True
    requer_binario = "phoneinfoga"

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        numero = so_digitos(valor)
        if len(numero) < 10:
            raise ErroConector("Informe o número com DDD (mínimo 10 dígitos)")
        if not numero.startswith("55"):
            numero = "55" + numero
        e164 = "+" + numero

        codigo, saida_txt, erro_txt = await ctx.rodar(
            ["phoneinfoga", "scan", "-n", e164], timeout=90
        )
        if codigo != 0 and not saida_txt.strip():
            raise ErroConector(erro_txt.strip()[:300] or "phoneinfoga falhou sem mensagem")

        campos = {
            m.group(1).strip(): m.group(2).strip()
            for m in CAMPO.finditer(saida_txt)
            if m.group(2).strip()
        }

        operadora = campos.get("Carrier") or campos.get("Operadora") or ""
        local = campos.get("Location") or campos.get("Country") or ""
        tipo = campos.get("Line type") or campos.get("Type") or ""

        resumo = " — ".join(p for p in [e164, local, operadora, tipo] if p)
        return [
            Resultado(
                resumo=resumo,
                dados={
                    "numero": e164,
                    "campos": campos,
                    "saida_bruta": saida_txt[:8000],
                    "ferramenta": "phoneinfoga",
                },
                fonte_url=f"https://www.google.com/search?q=%22{e164}%22",
            )
        ]
