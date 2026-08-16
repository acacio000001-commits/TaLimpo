"""CEP com coordenadas, via BrasilAPI (grátis, sem chave)."""
from __future__ import annotations

from .base import Conector, ErroConector, Resultado, so_digitos


class BrasilApiCep(Conector):
    chave = "brasilapi_cep"
    nome = "CEP — endereço e coordenadas"
    painel = "empresa"
    entrada = "cep"
    descricao = "Logradouro, bairro, cidade, UF e latitude/longitude quando disponível."

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        cep = so_digitos(valor)
        if len(cep) != 8:
            raise ErroConector("CEP precisa ter 8 dígitos")

        dados = await ctx.get_json(f"https://brasilapi.com.br/api/cep/v2/{cep}")
        if not dados:
            return []

        partes = [
            dados.get("street"),
            dados.get("neighborhood"),
            dados.get("city"),
            dados.get("state"),
        ]
        resumo = ", ".join(p for p in partes if p) or cep
        return [
            Resultado(
                resumo=resumo,
                dados=dados,
                fonte_url=f"https://brasilapi.com.br/api/cep/v2/{cep}",
            )
        ]
