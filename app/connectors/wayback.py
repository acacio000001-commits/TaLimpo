"""Wayback Machine — histórico de uma URL/domínio (grátis, sem chave).

Serve para provar que uma página, anúncio ou perfil existiu e como estava numa
data específica, mesmo depois de apagado.

O endpoint CDX (lista completa de capturas) vive instável e estoura timeout com
frequência. Por isso a consulta começa pelo /wayback/available, que é leve e
confiável, e só depois tenta enriquecer com o CDX — se ele falhar, o achado
principal já está garantido.
"""
from __future__ import annotations

from .base import Conector, ErroConector, Resultado


def _legivel(ts: str) -> str:
    if len(ts) >= 12:
        return f"{ts[6:8]}/{ts[4:6]}/{ts[0:4]} {ts[8:10]}:{ts[10:12]}"
    return ts or "?"


class Wayback(Conector):
    chave = "wayback"
    nome = "Wayback Machine — página apagada"
    painel = "digital"
    entrada = "url"
    descricao = (
        "Capturas arquivadas de um site, perfil ou anúncio. Prova de conteúdo "
        "que já foi removido do ar."
    )

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        alvo = valor.strip().removeprefix("https://").removeprefix("http://").strip("/")
        if not alvo:
            raise ErroConector("Informe uma URL ou domínio")

        saida: list[Resultado] = []

        # 1) captura mais próxima — leve, mas o Archive vive instável
        disp = None
        for _ in range(2):
            try:
                disp = await ctx.get_json(
                    "https://archive.org/wayback/available",
                    params={"url": alvo},
                    timeout=20,
                )
                break
            except Exception:
                continue

        proxima = ((disp or {}).get("archived_snapshots") or {}).get("closest") or {}
        if proxima.get("available"):
            saida.append(
                Resultado(
                    resumo=f"Última captura: {_legivel(proxima.get('timestamp', ''))}",
                    dados=proxima,
                    fonte_url=proxima.get("url"),
                )
            )

        # 2) histórico completo — melhor esforço, pode cair sem prejuízo
        try:
            linhas = await ctx.get_json(
                "https://web.archive.org/cdx/search/cdx",
                params={
                    "url": alvo,
                    "output": "json",
                    "limit": "40",
                    "collapse": "timestamp:6",
                    "filter": "statuscode:200",
                    "fl": "timestamp,original,mimetype,statuscode,digest",
                },
                timeout=20,
            )
        except Exception:
            linhas = None

        if linhas and len(linhas) > 1:
            cabecalho, *registros = linhas
            for reg in registros:
                item = dict(zip(cabecalho, reg))
                ts = item.get("timestamp", "")
                saida.append(
                    Resultado(
                        resumo=f"Captura de {_legivel(ts)} — {item.get('original', alvo)}",
                        dados=item,
                        fonte_url=f"https://web.archive.org/web/{ts}/{item.get('original', alvo)}",
                    )
                )
        else:
            # O Archive fora do ar não pode zerar a diligência: devolve o link
            # direto para conferência manual, registrado no caso como qualquer
            # outro achado.
            saida.append(
                Resultado(
                    resumo=(
                        "Histórico completo indisponível agora (API do Internet Archive "
                        "instável). Abra o link e confira manualmente."
                    ),
                    dados={"aviso": "archive_indisponivel", "alvo": alvo},
                    fonte_url=f"https://web.archive.org/web/*/{alvo}",
                )
            )

        return saida
