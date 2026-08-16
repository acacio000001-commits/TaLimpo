"""Diários Oficiais municipais — Querido Diário / Open Knowledge Brasil.

Fonte pública, sem chave. Excelente para nome de pessoa: nomeações, licitações,
contratos, concursos e processos administrativos citam nome completo.

Atenção ao host: `queridodiario.ok.org.br/api` devolve o SITE (HTML).
A API de verdade fica em `api.queridodiario.ok.org.br`.
"""
from __future__ import annotations

from .base import Conector, ErroConector, Resultado

BASE = "https://api.queridodiario.ok.org.br"


class QueridoDiario(Conector):
    chave = "querido_diario"
    nome = "Diários Oficiais (Querido Diário)"
    painel = "pessoa"
    entrada = "nome"
    descricao = (
        "Busca o nome no texto dos diários oficiais municipais: nomeações, "
        "contratos, licitações e atos administrativos."
    )

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        termo = valor.strip()
        if len(termo) < 3:
            raise ErroConector("Informe pelo menos 3 caracteres")

        dados = await ctx.get_json(
            f"{BASE}/gazettes",
            params={
                "querystring": f'"{termo}"',
                "size": 20,
                "sort_by": "descending_date",
                "excerpt_size": 300,
                "number_of_excerpts": 1,
                "pre_tags": "",
                "post_tags": "",
            },
        )
        if not dados:
            return []

        saida: list[Resultado] = []
        for item in dados.get("gazettes") or []:
            municipio = item.get("territory_name") or item.get("territory_id") or "?"
            uf = item.get("state_code") or ""
            data = item.get("date") or "?"
            trechos = item.get("excerpts") or []
            trecho = (trechos[0][:300] if trechos else "").replace("\n", " ").strip()

            saida.append(
                Resultado(
                    resumo=(
                        f"{data} — {municipio}"
                        + (f"/{uf}" if uf else "")
                        + (f": {trecho}" if trecho else "")
                    ),
                    dados=item,
                    fonte_url=item.get("txt_url") or item.get("url"),
                )
            )
        return saida
