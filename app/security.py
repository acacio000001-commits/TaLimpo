"""Hash de senha e tokens de sessão — só biblioteca padrão, nada pesado."""
from __future__ import annotations

import hashlib
import hmac
import secrets

ITERACOES = 240_000
ALGO = "pbkdf2_sha256"


def gerar_hash(senha: str) -> str:
    sal = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), ITERACOES)
    return f"{ALGO}${ITERACOES}${sal}${dk.hex()}"


def conferir_senha(senha: str, armazenado: str) -> bool:
    try:
        algo, iteracoes, sal, esperado = armazenado.split("$", 3)
        if algo != ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), int(iteracoes))
        return hmac.compare_digest(dk.hex(), esperado)
    except (ValueError, TypeError):
        return False


def novo_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()
