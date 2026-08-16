"""Configuração central lida do ambiente."""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DB = RAIZ / "db"
DIR_WEB = RAIZ / "web"


def _bool(nome: str, padrao: str = "0") -> bool:
    return os.environ.get(nome, padrao).strip().lower() in ("1", "true", "sim", "yes")


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.environ.get(nome, "").strip() or padrao)
    except ValueError:
        return padrao


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

ADMIN_NOME = os.environ.get("ADMIN_NOME", "Administrador").strip()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip()
ADMIN_SENHA = os.environ.get("ADMIN_SENHA", "").strip()

SESSION_TTL_HORAS = _int("SESSION_TTL_HORAS", 12)
COOKIE_SEGURO = _bool("COOKIE_SEGURO", "1")
COOKIE_NOME = "osint_sessao"

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# Credenciais das fontes (todas gratuitas)
DATAJUD_API_KEY = os.environ.get("DATAJUD_API_KEY", "").strip()
PORTAL_TRANSPARENCIA_KEY = os.environ.get("PORTAL_TRANSPARENCIA_KEY", "").strip()

# YouTube Data API v3 — chave grátis no Google Cloud. Vazio = conector desligado.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

# Banco SEPARADO com a base pública de CNPJ + sócios da Receita (>100 GB).
# Vazio = o conector de cruzamento de sócios fica desligado. Ver db/002_socios.sql.
SOCIOS_DATABASE_URL = os.environ.get("SOCIOS_DATABASE_URL", "").strip()

# Ferramentas de linha de comando
FERRAMENTAS_LOCAIS = _bool("FERRAMENTAS_LOCAIS", "1")
MAIGRET_TOP_SITES = _int("MAIGRET_TOP_SITES", 50)
MAIGRET_TIMEOUT = _int("MAIGRET_TIMEOUT", 15)

# Teto de execução de qualquer conector, em segundos.
TIMEOUT_CONECTOR = _int("TIMEOUT_CONECTOR", 120)

USER_AGENT = "osint-detetive/1.0 (+investigacao-particular)"
