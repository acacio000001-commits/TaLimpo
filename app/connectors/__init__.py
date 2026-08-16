"""Descoberta automática de conectores.

Todo módulo .py desta pasta (que não comece com "_") é importado no boot.
As classes que herdam de Conector se registram sozinhas em base.REGISTRO.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import REGISTRO, Conector, Contexto, ErroConector, Resultado  # noqa: F401


def carregar() -> dict[str, Conector]:
    pasta = Path(__file__).parent
    for mod in pkgutil.iter_modules([str(pasta)]):
        if mod.name.startswith("_") or mod.name == "base":
            continue
        importlib.import_module(f"{__name__}.{mod.name}")
    return REGISTRO


def obter(chave: str) -> Conector | None:
    return REGISTRO.get(chave)


def listar() -> list[Conector]:
    return sorted(REGISTRO.values(), key=lambda c: (c.painel, c.nome))
