"""Verificação HTTP — o site está no ar, para onde redireciona, que servidor usa.

Inspirado no httpfy. Sem chave. Numa apuração serve para confirmar rápido se o
site de um investigado responde, se mudou de endereço (redirecionamento) e onde
está hospedado (cabeçalho Server).
"""
from __future__ import annotations

import re

from .base import Conector, ErroConector, Resultado

TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class HttpCheck(Conector):
    chave = "http_check"
    nome = "HTTP — o site está no ar?"
    painel = "digital"
    entrada = "dominio"
    descricao = (
        "Confere se o site responde: código de status, servidor, cadeia de "
        "redirecionamentos e o título da página."
    )

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        alvo = valor.strip()
        if not alvo:
            raise ErroConector("Informe um domínio ou URL")
        if not alvo.startswith(("http://", "https://")):
            alvo = "https://" + alvo.strip("/")

        try:
            r = await ctx.http.get(alvo)
        except Exception as e:
            raise ErroConector(f"O site não respondeu ({type(e).__name__})")

        tipo = (r.headers.get("content-type") or "").split(";")[0]
        titulo = ""
        if "html" in tipo:
            m = TITULO.search(r.text[:20000])
            if m:
                titulo = re.sub(r"\s+", " ", m.group(1)).strip()[:160]

        resumo = f"{r.status_code} {r.reason_phrase} — {r.url}"
        if titulo:
            resumo += f' — "{titulo}"'

        dados = {
            "url_final": str(r.url),
            "status": r.status_code,
            "servidor": r.headers.get("server", "?"),
            "content_type": tipo,
            "titulo": titulo,
            "redirecionou": str(r.url) != alvo,
            "historico_redirecionamentos": [str(h.url) for h in r.history],
        }
        return [Resultado(resumo=resumo, dados=dados, fonte_url=str(r.url))]
