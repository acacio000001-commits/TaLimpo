"""Portal da Transparência — sanções CEIS/CNEP e vínculo com servidor federal.

Chave gratuita: cadastro no portal e a chave chega por e-mail.
https://api.portaldatransparencia.gov.br/swagger-ui/index.html

Aceita CPF (11 dígitos) ou CNPJ (14 dígitos) na mesma caixa.
"""
from __future__ import annotations

from .. import config
from .base import Conector, ErroConector, Resultado, so_digitos

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"


class TransparenciaSancoes(Conector):
    chave = "transparencia_sancoes"
    nome = "Sanções CEIS/CNEP — Transparência"
    painel = "empresa"
    entrada = "documento"
    descricao = (
        "Empresas e pessoas inidôneas ou suspensas de contratar com o poder "
        "público (CEIS) e punidas pela Lei Anticorrupção (CNEP)."
    )
    requer_credencial = ["PORTAL_TRANSPARENCIA_KEY"]

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        doc = so_digitos(valor)
        if len(doc) not in (11, 14):
            raise ErroConector("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos)")

        cabecalho = {"chave-api-dados": config.PORTAL_TRANSPARENCIA_KEY}
        campo = "cpfSancionado" if len(doc) == 11 else "cnpjSancionado"
        saida: list[Resultado] = []

        for cadastro, rotulo in (("ceis", "CEIS"), ("cnep", "CNEP")):
            url = f"{BASE}/{cadastro}"
            try:
                registros = await ctx.get_json(
                    url, headers=cabecalho, params={campo: doc, "pagina": 1}
                )
            except Exception:
                continue

            for r in registros or []:
                sancionado = (r.get("pessoa") or {}).get("nome") or r.get("nomeInformado") or "?"
                tipo = (r.get("tipoSancao") or {}).get("descricaoResumida") or rotulo
                inicio = r.get("dataInicioSancao") or ""
                fim = r.get("dataFimSancao") or ""
                orgao = (r.get("orgaoSancionador") or {}).get("nome") or ""

                saida.append(
                    Resultado(
                        resumo=(
                            f"[{rotulo}] {sancionado} — {tipo}"
                            + (f" ({inicio} a {fim})" if inicio else "")
                            + (f" — {orgao}" if orgao else "")
                        ),
                        dados={**r, "_cadastro": rotulo},
                        fonte_url=url,
                    )
                )

        return saida
