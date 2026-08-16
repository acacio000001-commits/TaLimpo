"""Pool de conexões Postgres (Neon) e atalhos de consulta."""
from __future__ import annotations

from typing import Any, Iterable

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from . import config

_pool: AsyncConnectionPool | None = None


async def abrir() -> AsyncConnectionPool:
    """Cria o pool. O Neon dorme, então o pool nasce pequeno e com timeout folgado."""
    global _pool
    if _pool is None:
        if not config.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL nao configurada. Copie .env.example para .env "
                "e cole a connection string do Neon."
            )
        _pool = AsyncConnectionPool(
            conninfo=config.DATABASE_URL,
            min_size=0,
            max_size=4,
            timeout=30,
            max_idle=120,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=False,
        )
        await _pool.open(wait=True, timeout=45)
    return _pool


async def fechar() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Pool ainda nao aberto")
    return _pool


async def buscar_todos(sql: str, params: Iterable[Any] | None = None) -> list[dict]:
    async with pool().connection() as con:
        cur = await con.execute(sql, params)
        return await cur.fetchall()


async def buscar_um(sql: str, params: Iterable[Any] | None = None) -> dict | None:
    async with pool().connection() as con:
        cur = await con.execute(sql, params)
        return await cur.fetchone()


async def executar(sql: str, params: Iterable[Any] | None = None) -> None:
    async with pool().connection() as con:
        await con.execute(sql, params)


async def executar_script(sql: str) -> None:
    """Roda um arquivo .sql inteiro numa transação só."""
    async with pool().connection() as con:
        await con.set_autocommit(False)
        try:
            await con.execute(sql)
            await con.commit()
        except Exception:
            await con.rollback()
            raise
        finally:
            await con.set_autocommit(True)
