"""DataJud / CNJ — API pública de processos judiciais.

Chave gratuita e pública, publicada na documentação do CNJ:
https://datajud-wiki.cnj.jus.br/api-publica/acesso

Atenção: a API pública devolve os METADADOS do processo (classe, assuntos,
movimentos, órgão julgador). Ela NÃO devolve nome nem CPF das partes — o CNJ
remove isso. Por isso a entrada aqui é o número CNJ do processo.
"""
from __future__ import annotations

from .. import config
from .base import Conector, ErroConector, Resultado, so_digitos

# Tribunais mais usados. Para varrer outro, acrescente o alias aqui.
TRIBUNAIS = [
    "api_publica_tjrj", "api_publica_tjsp", "api_publica_tjmg",
    "api_publica_tjrs", "api_publica_tjpr", "api_publica_tjba",
    "api_publica_trf2", "api_publica_trf1", "api_publica_trf3",
    "api_publica_tst",  "api_publica_stj",
]


class DataJud(Conector):
    chave = "datajud_cnj"
    nome = "Processos — DataJud/CNJ"
    painel = "pessoa"
    entrada = "processo"
    descricao = (
        "Metadados oficiais do processo pelo número CNJ: classe, assuntos, "
        "órgão julgador, data de ajuizamento e a lista completa de movimentos."
    )
    requer_credencial = ["DATAJUD_API_KEY"]

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        numero = so_digitos(valor)
        if len(numero) != 20:
            raise ErroConector(
                "O número CNJ tem 20 dígitos "
                "(formato NNNNNNN-DD.AAAA.J.TR.OOOO)"
            )

        cabecalho = {
            "Authorization": f"APIKey {config.DATAJUD_API_KEY}",
            "Content-Type": "application/json",
        }
        corpo = {"query": {"match": {"numeroProcesso": numero}}, "size": 5}

        for tribunal in TRIBUNAIS:
            url = f"https://api-publica.datajud.cnj.jus.br/{tribunal}/_search"
            try:
                dados = await ctx.post_json(url, headers=cabecalho, json=corpo)
            except Exception:
                continue

            acertos = ((dados or {}).get("hits") or {}).get("hits") or []
            if not acertos:
                continue

            saida: list[Resultado] = []
            for acerto in acertos:
                p = acerto.get("_source") or {}
                classe = (p.get("classe") or {}).get("nome") or "?"
                orgao = (p.get("orgaoJulgador") or {}).get("nome") or "?"
                ajuizamento = (p.get("dataAjuizamento") or "")[:10]
                assuntos = ", ".join(
                    a.get("nome", "") for a in (p.get("assuntos") or [])
                )[:160]

                saida.append(
                    Resultado(
                        resumo=(
                            f"{classe} — {orgao}"
                            + (f" — ajuizado em {ajuizamento}" if ajuizamento else "")
                            + (f" — {assuntos}" if assuntos else "")
                        ),
                        dados={**p, "_tribunal": tribunal.replace("api_publica_", "").upper()},
                        fonte_url=url,
                    )
                )
            return saida

        return []
