"""MODELO — bureau contratado (Informbank, Serasa, Boa Vista, Assertiva...).

Este arquivo começa com "_", então o carregador AUTOMATICAMENTE O IGNORA.
Para ligar um bureau de verdade:

  1. copie para um nome sem underline, ex.: `informbank.py`
  2. ajuste chave/nome/entrada e o endpoint conforme a documentação do bureau
  3. acrescente a variável da chave de API em app/config.py e no .env
  4. reinicie — a fonte aparece sozinha no painel

Diferente das fontes públicas, aqui o dado é obtido sob CONTRATO. Registre a
finalidade no caso: é isso que sustenta a base legal do art. 7º da LGPD.
"""
from __future__ import annotations

from .. import config
from .base import Conector, ErroConector, Resultado, so_digitos


class BureauExemplo(Conector):
    chave = "bureau_exemplo"
    nome = "Bureau contratado (modelo)"
    painel = "pessoa"
    entrada = "documento"          # cpf ou cnpj
    descricao = "Consulta cadastral contratada. Substitua pelo bureau real."
    custo = "contratado"
    requer_credencial = ["BUREAU_API_KEY"]   # crie essa variável em config.py

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        doc = so_digitos(valor)
        if len(doc) not in (11, 14):
            raise ErroConector("Informe um CPF (11) ou CNPJ (14 dígitos)")

        dados = await ctx.get_json(
            "https://api.SEU-BUREAU.com.br/v1/cadastral",
            params={"documento": doc},
            headers={"Authorization": f"Bearer {getattr(config, 'BUREAU_API_KEY', '')}"},
        )
        if not dados:
            return []

        return [
            Resultado(
                resumo=dados.get("nome") or doc,
                dados=dados,
                fonte_url="https://api.SEU-BUREAU.com.br/v1/cadastral",
            )
        ]
