"""YouTube — metadados públicos de um vídeo (título, canal, data, visualizações).

Inspirado no youtube-metadata. Usa a YouTube Data API v3, que exige uma chave
gratuita do Google Cloud (console.cloud.google.com → ative "YouTube Data API v3"
→ crie uma chave de API). Sem a chave, o conector aparece indisponível.

Numa apuração serve para datar um vídeo, identificar o canal por trás e medir
alcance (visualizações) de um conteúdo ligado ao investigado.
"""
from __future__ import annotations

import re

from .. import config
from .base import Conector, ErroConector, Resultado

VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")


class YouTube(Conector):
    chave = "youtube"
    nome = "YouTube — metadados de vídeo"
    painel = "digital"
    entrada = "url"
    descricao = (
        "Título, canal, data de publicação, descrição e número de visualizações "
        "de um vídeo do YouTube, a partir do link."
    )
    requer_credencial = ["YOUTUBE_API_KEY"]

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        alvo = valor.strip()
        m = VIDEO_ID.search(alvo)
        vid = m.group(1) if m else (alvo if re.fullmatch(r"[A-Za-z0-9_-]{11}", alvo) else None)
        if not vid:
            raise ErroConector("Informe o link ou o ID de um vídeo do YouTube")

        dados = await ctx.get_json(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": vid, "key": config.YOUTUBE_API_KEY},
        )
        itens = (dados or {}).get("items") or []
        if not itens:
            return []

        v = itens[0]
        s = v.get("snippet", {}) or {}
        st = v.get("statistics", {}) or {}
        pub = (s.get("publishedAt") or "")[:10]

        resumo = f"{s.get('title', '?')} — canal {s.get('channelTitle', '?')}"
        if pub:
            resumo += f", publicado {pub}"
        if st.get("viewCount"):
            resumo += f", {st['viewCount']} visualizações"

        return [
            Resultado(
                resumo=resumo,
                dados={
                    "title": s.get("title"),
                    "channelTitle": s.get("channelTitle"),
                    "publishedAt": s.get("publishedAt"),
                    "description": (s.get("description") or "")[:1000],
                    "viewCount": st.get("viewCount"),
                    "likeCount": st.get("likeCount"),
                    "commentCount": st.get("commentCount"),
                    "video_id": vid,
                },
                fonte_url=f"https://www.youtube.com/watch?v={vid}",
            )
        ]
