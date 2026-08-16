"""Tabela FIPE, via BrasilAPI (grátis, sem chave).

Entrada: o código FIPE do modelo (ex.: 001004-9). Numa apuração patrimonial
serve para precificar o veículo declarado; no dia a dia da loja, para conferir
o valor de referência.

Aviso: a BrasilAPI depende do site da FIPE, que cai com frequência e devolve
500 com a mensagem "Fonte de dados FIPE temporariamente indisponível". Nesse
caso o conector não estoura erro — devolve o link para conferência manual, do
mesmo jeito que o Wayback.
"""
from __future__ import annotations

from .base import Conector, ErroConector, Resultado

BASE = "https://brasilapi.com.br/api/fipe"


class Fipe(Conector):
    chave = "fipe"
    nome = "Tabela FIPE — valor do veículo"
    painel = "empresa"
    entrada = "codigo_fipe"
    descricao = (
        "Preço de referência do modelo pelo código FIPE (ex.: 001004-9), com "
        "o histórico de tabelas mensais disponíveis."
    )

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        codigo = valor.strip().upper()
        if len(codigo.replace("-", "")) < 6:
            raise ErroConector("Informe o código FIPE do modelo, ex.: 001004-9")

        url = f"{BASE}/preco/v1/{codigo}"
        try:
            dados = await ctx.get_json(url)
        except Exception:
            return [
                Resultado(
                    resumo=(
                        "A fonte da FIPE está fora do ar no momento. Abra o link e "
                        "consulte manualmente."
                    ),
                    dados={"aviso": "fipe_indisponivel", "codigo_fipe": codigo},
                    fonte_url="https://veiculos.fipe.org.br/",
                )
            ]

        if not dados:
            return []

        registros = dados if isinstance(dados, list) else [dados]
        return [
            Resultado(
                resumo=(
                    f"{r.get('marca', '?')} {r.get('modelo', '?')} "
                    f"{r.get('anoModelo', '')} — {r.get('valor', '?')} "
                    f"(referência {r.get('mesReferencia', '?')})"
                ),
                dados=r,
                fonte_url=url,
            )
            for r in registros
        ]
