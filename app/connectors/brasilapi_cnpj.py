"""CNPJ na base pública da Receita Federal.

Três provedores gratuitos em cadeia. O BrasilAPI limita taxa e devolve 429 com
facilidade, então na primeira falha cai para o minhareceita.org (mesmo formato
de campos) e, por último, para o cnpj.ws (formato próprio).
"""
from __future__ import annotations

from .base import Conector, ErroConector, Resultado, so_digitos


class CnpjReceita(Conector):
    chave = "brasilapi_cnpj"
    nome = "CNPJ — Receita Federal"
    painel = "empresa"
    entrada = "cnpj"
    descricao = (
        "Razão social, nome fantasia, situação cadastral, CNAE, capital social, "
        "endereço e o quadro societário completo (QSA)."
    )

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        cnpj = so_digitos(valor)
        if len(cnpj) != 14:
            raise ErroConector("CNPJ precisa ter 14 dígitos")

        tentativas = [
            (f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", self._formato_receita),
            (f"https://minhareceita.org/{cnpj}", self._formato_receita),
            (f"https://publica.cnpj.ws/cnpj/{cnpj}", self._formato_cnpjws),
        ]

        ultimo_erro: Exception | None = None
        for url, converter in tentativas:
            try:
                dados = await ctx.get_json(url)
            except Exception as e:
                ultimo_erro = e
                continue
            if dados:
                return converter(dados, url, cnpj)

        if ultimo_erro:
            raise ErroConector(
                "Os três provedores de CNPJ falharam (o último respondeu "
                f"{type(ultimo_erro).__name__}). Tente de novo em alguns segundos."
            )
        return []

    # -- formato compartilhado por BrasilAPI e minhareceita.org --------------
    @staticmethod
    def _formato_receita(dados: dict, url: str, cnpj: str) -> list[Resultado]:
        situacao = dados.get("descricao_situacao_cadastral") or "?"
        saida = [
            Resultado(
                resumo=f"{dados.get('razao_social', '?')} — {situacao}",
                dados=dados,
                fonte_url=url,
            )
        ]
        # Cada sócio vira um achado próprio: é o que abre a próxima linha de
        # investigação (cruzar o sócio com outras empresas).
        for socio in dados.get("qsa") or []:
            saida.append(
                Resultado(
                    resumo=(
                        f"Sócio: {socio.get('nome_socio') or '?'} "
                        f"({socio.get('qualificacao_socio') or ''})"
                    ),
                    dados={**socio, "_cnpj_origem": cnpj,
                           "_empresa": dados.get("razao_social")},
                    fonte_url=url,
                )
            )
        return saida

    # -- formato do cnpj.ws --------------------------------------------------
    @staticmethod
    def _formato_cnpjws(dados: dict, url: str, cnpj: str) -> list[Resultado]:
        estab = dados.get("estabelecimento") or {}
        situacao = estab.get("situacao_cadastral") or "?"
        saida = [
            Resultado(
                resumo=f"{dados.get('razao_social', '?')} — {situacao}",
                dados=dados,
                fonte_url=url,
            )
        ]
        for socio in dados.get("socios") or []:
            qualificacao = (socio.get("qualificacao_socio") or {}).get("descricao", "")
            saida.append(
                Resultado(
                    resumo=f"Sócio: {socio.get('nome') or '?'} ({qualificacao})",
                    dados={**socio, "_cnpj_origem": cnpj,
                           "_empresa": dados.get("razao_social")},
                    fonte_url=url,
                )
            )
        return saida
