"""maigret — procura um apelido/usuário em centenas de sites.

Ferramenta local (CLI). No free tier do Render (512 MB / 0.1 CPU) a varredura
completa não cabe, então o número de sites e o timeout são limitados por
MAIGRET_TOP_SITES e MAIGRET_TIMEOUT.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from .. import config
from .base import Conector, ErroConector, Resultado

LINHA_POSITIVA = re.compile(r"^\s*\[\+\]\s+([^:]+):\s*(\S+)", re.MULTILINE)


class Maigret(Conector):
    chave = "maigret"
    nome = "maigret — usuário em redes"
    painel = "digital"
    entrada = "username"
    descricao = (
        "Procura o apelido em centenas de redes e fóruns e devolve os perfis "
        "encontrados com o link direto."
    )
    local = True
    requer_binario = "maigret"

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        usuario = valor.strip().lstrip("@")
        if len(usuario) < 3:
            raise ErroConector("Informe um usuário com pelo menos 3 caracteres")

        with tempfile.TemporaryDirectory(prefix="maigret_") as pasta:
            codigo, saida_txt, erro_txt = await ctx.rodar(
                [
                    "maigret", usuario,
                    "--json", "simple",
                    "--folderoutput", pasta,
                    "--timeout", str(config.MAIGRET_TIMEOUT),
                    "--top-sites", str(config.MAIGRET_TOP_SITES),
                    "--no-progressbar",
                    "--no-color",
                ],
                timeout=config.TIMEOUT_CONECTOR,
            )

            achados = self._ler_json(Path(pasta))

        if not achados:
            achados = [
                {"site": m.group(1).strip(), "url": m.group(2).strip()}
                for m in LINHA_POSITIVA.finditer(saida_txt)
            ]

        if not achados and codigo != 0:
            raise ErroConector(erro_txt.strip()[:300] or "maigret falhou sem mensagem")

        return [
            Resultado(
                resumo=f"Perfil em {a['site']}",
                dados={**a, "usuario": usuario, "ferramenta": "maigret"},
                fonte_url=a.get("url"),
            )
            for a in achados
        ]

    @staticmethod
    def _ler_json(pasta: Path) -> list[dict]:
        """O maigret grava report_<usuario>_simple.json na pasta de saída."""
        achados: list[dict] = []
        for arquivo in pasta.glob("*.json"):
            try:
                conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(conteudo, dict):
                continue
            for site, info in conteudo.items():
                if not isinstance(info, dict):
                    continue
                status = info.get("status") or {}
                encontrado = (
                    status.get("status") == "Claimed"
                    if isinstance(status, dict)
                    else str(status) == "Claimed"
                )
                if encontrado:
                    achados.append(
                        {
                            "site": site,
                            "url": info.get("url_user") or info.get("url_main"),
                            "ids": (status.get("ids") if isinstance(status, dict) else None) or {},
                        }
                    )
        return achados
