"""DDD -> estado e lista de cidades, via BrasilAPI (grátis, sem chave)."""
from __future__ import annotations

from .base import Conector, ErroConector, Resultado, so_digitos


class BrasilApiDdd(Conector):
    chave = "brasilapi_ddd"
    nome = "DDD — região do telefone"
    painel = "digital"
    entrada = "telefone"
    descricao = "A partir do DDD, devolve o estado e todas as cidades da área."

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        numero = so_digitos(valor)
        if numero.startswith("55") and len(numero) > 11:
            numero = numero[2:]
        ddd = numero[:2]
        if len(ddd) != 2:
            raise ErroConector("Informe ao menos o DDD com 2 dígitos")

        dados = await ctx.get_json(f"https://brasilapi.com.br/api/ddd/v1/{ddd}")
        if not dados:
            return []

        cidades = dados.get("cities") or []
        return [
            Resultado(
                resumo=f"DDD {ddd} — {dados.get('state', '?')} ({len(cidades)} cidades)",
                dados={"ddd": ddd, **dados},
                fonte_url=f"https://brasilapi.com.br/api/ddd/v1/{ddd}",
            )
        ]
