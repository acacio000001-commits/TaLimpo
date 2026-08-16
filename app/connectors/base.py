"""Contrato dos conectores de fonte.

COMO ADICIONAR UMA BASE NOVA
----------------------------
1. Crie um arquivo em app/connectors/, ex.: `meu_orgao.py`
2. Escreva uma classe herdando de `Conector`
3. Pronto. Ela se registra sozinha, entra na tabela `fontes` no próximo boot
   e aparece no painel correspondente. Nenhum outro arquivo precisa mudar.

    from .base import Conector, Resultado

    class MeuOrgao(Conector):
        chave     = "meu_orgao"
        nome      = "Meu Órgão Público"
        painel    = "pessoa"          # pessoa | empresa | digital
        entrada   = "cpf"             # cpf|cnpj|nome|email|telefone|username|dominio|placa|url
        descricao = "O que essa fonte devolve"

        async def executar(self, valor, ctx):
            dados = await ctx.get_json(f"https://api.exemplo.gov.br/{valor}")
            return [Resultado(resumo=dados["nome"], dados=dados)]
"""
from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx

from .. import config

REGISTRO: dict[str, "Conector"] = {}


@dataclass
class Resultado:
    """Uma linha de achado. Vira um registro na tabela `resultados`."""

    resumo: str
    dados: dict[str, Any] = field(default_factory=dict)
    fonte_url: str | None = None


class ErroConector(Exception):
    """Falha esperada da fonte (fora do ar, sem credencial, entrada inválida)."""


class Contexto:
    """Utilidades entregues ao conector: HTTP e execução de ferramenta CLI."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def get_json(self, url: str, **kw) -> Any:
        r = await self.http.get(url, **kw)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def get_texto(self, url: str, **kw) -> str:
        r = await self.http.get(url, **kw)
        r.raise_for_status()
        return r.text

    async def post_json(self, url: str, **kw) -> Any:
        r = await self.http.post(url, **kw)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def tem_binario(nome: str) -> bool:
        return shutil.which(nome) is not None

    @staticmethod
    async def rodar(cmd: list[str], timeout: int = 90) -> tuple[int, str, str]:
        """Executa uma ferramenta de linha de comando com teto de tempo."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            saida, erro = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ErroConector(f"A ferramenta passou de {timeout}s e foi interrompida")
        return (
            proc.returncode or 0,
            saida.decode("utf-8", "replace"),
            erro.decode("utf-8", "replace"),
        )


class Conector:
    # --- metadados (sobrescreva na subclasse) ---
    chave: ClassVar[str] = ""
    nome: ClassVar[str] = ""
    painel: ClassVar[str] = "pessoa"
    entrada: ClassVar[str] = "nome"
    descricao: ClassVar[str] = ""
    requer_credencial: ClassVar[list[str]] = []
    custo: ClassVar[str] = "gratuito"
    requer_binario: ClassVar[str | None] = None
    local: ClassVar[bool] = False  # True = ferramenta CLI, respeita FERRAMENTAS_LOCAIS

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        if cls.chave:
            REGISTRO[cls.chave] = cls()

    # --- disponibilidade ---
    def disponivel(self) -> tuple[bool, str]:
        faltando = [c for c in self.requer_credencial if not getattr(config, c, "")]
        if faltando:
            return False, "Falta configurar: " + ", ".join(faltando)
        if self.local and not config.FERRAMENTAS_LOCAIS:
            return False, "Ferramentas locais desligadas (FERRAMENTAS_LOCAIS=0)"
        if self.requer_binario and not Contexto.tem_binario(self.requer_binario):
            return False, f"Binário '{self.requer_binario}' não encontrado na imagem"
        return True, ""

    # --- execução (implemente na subclasse) ---
    async def executar(self, valor: str, ctx: Contexto) -> list[Resultado]:
        raise NotImplementedError

    # --- serialização para o front ---
    def como_dict(self) -> dict:
        ok, motivo = self.disponivel()
        return {
            "chave": self.chave,
            "nome": self.nome,
            "painel": self.painel,
            "entrada": self.entrada,
            "descricao": self.descricao,
            "requer_credencial": list(self.requer_credencial),
            "custo": self.custo,
            "disponivel": ok,
            "motivo_indisponivel": motivo,
        }


# ------------------------------------------------------------------ helpers

def so_digitos(valor: str) -> str:
    return "".join(c for c in valor if c.isdigit())


def json_seguro(texto: str) -> Any:
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return None
