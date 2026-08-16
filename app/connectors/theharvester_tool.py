"""theHarvester — e-mails, subdomínios e hosts ligados a um domínio.

Ferramenta local (CLI). Rodamos só as fontes que não exigem chave de API, para
não travar no free tier nem depender de cadastro.

Uso típico numa apuração: pegar o domínio da empresa investigada e levantar os
e-mails corporativos e os subdomínios esquecidos (homologação, intranet, ftp).
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from .base import Conector, ErroConector, Resultado

FONTES_SEM_CHAVE = "crtsh,duckduckgo,hackertarget,rapiddns,otx,anubis,urlscan,threatminer"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
HOST = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", re.IGNORECASE)


class TheHarvester(Conector):
    chave = "theharvester"
    nome = "theHarvester — e-mails e subdomínios"
    painel = "digital"
    entrada = "dominio"
    descricao = (
        "Levanta e-mails corporativos, subdomínios e hosts de um domínio, "
        "usando apenas fontes públicas que não exigem cadastro."
    )
    local = True
    requer_binario = "theHarvester"

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        dominio = (
            valor.strip().lower()
            .removeprefix("https://").removeprefix("http://")
            .strip("/").split("/")[0]
        )
        if "." not in dominio:
            raise ErroConector("Informe um domínio, ex.: empresa.com.br")

        with tempfile.TemporaryDirectory(prefix="harvester_") as pasta:
            destino = str(Path(pasta) / "saida")
            codigo, saida_txt, erro_txt = await ctx.rodar(
                ["theHarvester", "-d", dominio, "-b", FONTES_SEM_CHAVE,
                 "-l", "100", "-f", destino],
                timeout=110,
            )
            emails, hosts = self._ler_json(Path(pasta))

        if not emails and not hosts:
            emails = sorted(set(EMAIL.findall(saida_txt)))
            hosts = sorted({
                linha.strip() for linha in saida_txt.splitlines()
                if HOST.match(linha.strip()) and dominio in linha
            })

        if not emails and not hosts and codigo != 0:
            raise ErroConector(erro_txt.strip()[:300] or "theHarvester falhou sem mensagem")

        saida = [
            Resultado(
                resumo=f"E-mail: {e}",
                dados={"email": e, "dominio": dominio, "ferramenta": "theHarvester"},
            )
            for e in emails
        ]
        saida += [
            Resultado(
                resumo=f"Host/subdomínio: {h}",
                dados={"host": h, "dominio": dominio, "ferramenta": "theHarvester"},
                fonte_url=f"https://{h}",
            )
            for h in hosts
        ]
        return saida

    @staticmethod
    def _ler_json(pasta: Path) -> tuple[list[str], list[str]]:
        for arquivo in pasta.glob("*.json"):
            try:
                dados = json.loads(arquivo.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(dados, dict):
                return (
                    sorted(set(dados.get("emails") or [])),
                    sorted(set(dados.get("hosts") or [])),
                )
        return [], []
