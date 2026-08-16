"""Cruzamento de sócios — todas as empresas ligadas a uma pessoa.

É o recurso mais forte para apuração patrimonial e o único aqui que NÃO cabe no
plano gratuito: exige a base pública completa de CNPJ + sócios da Receita
Federal carregada num Postgres próprio (a base passa de 100 GB; o Neon free tem
0,5 GB).

Fica desligado sozinho enquanto SOCIOS_DATABASE_URL não existir — aparece no
painel como indisponível, sem quebrar nada.

Como ligar: instruções em db/002_socios.sql e na seção correspondente do README.

O dado é 100% público e de distribuição livre pela própria Receita Federal.
"""
from __future__ import annotations

from .. import config
from .base import Conector, ErroConector, Resultado, so_digitos

LIMITE = 100


class SociosCruzamento(Conector):
    chave = "socios_cruzamento"
    nome = "Sócios — todas as empresas da pessoa"
    painel = "pessoa"
    entrada = "documento"
    descricao = (
        "Dado um CPF ou nome, lista TODAS as empresas em que a pessoa figura "
        "como sócia ou administradora. Exige a base da Receita carregada."
    )
    requer_credencial = ["SOCIOS_DATABASE_URL"]
    custo = "infraestrutura própria"

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        termo = valor.strip()
        if len(termo) < 4:
            raise ErroConector("Informe um CPF ou um nome com pelo menos 4 letras")

        # Importado aqui de propósito: quem não usa esta fonte não paga o custo
        # de abrir uma segunda conexão de banco.
        import psycopg
        from psycopg.rows import dict_row

        doc = so_digitos(termo)

        # A Receita publica o CPF do sócio mascarado (***123456**), então o
        # casamento é feito pelos 6 dígitos do meio, que são os revelados.
        if len(doc) == 11:
            miolo = doc[3:9]
            onde = "s.doc_socio LIKE %s"
            params: tuple = (f"%{miolo}%", LIMITE)
        else:
            onde = "unaccent(upper(s.nome_socio)) LIKE unaccent(upper(%s))"
            params = (f"%{termo}%", LIMITE)

        sql = f"""
            SELECT s.nome_socio, s.doc_socio, s.cnpj, s.razao_social,
                   s.qualificacao, s.data_entrada
            FROM vw_socios_busca s
            WHERE {onde}
            ORDER BY s.data_entrada DESC NULLS LAST
            LIMIT %s
        """

        try:
            async with await psycopg.AsyncConnection.connect(
                config.SOCIOS_DATABASE_URL, row_factory=dict_row, connect_timeout=15
            ) as con:
                cur = await con.execute(sql, params)
                linhas = await cur.fetchall()
        except Exception as e:
            raise ErroConector(
                f"Não consegui consultar a base de sócios ({type(e).__name__}). "
                "Confira SOCIOS_DATABASE_URL e se a view vw_socios_busca existe."
            )

        return [
            Resultado(
                resumo=(
                    f"{linha['nome_socio']} — {linha['razao_social']} "
                    f"(CNPJ {linha['cnpj']}, {linha['qualificacao'] or 'sócio'}"
                    + (f", desde {linha['data_entrada']}" if linha["data_entrada"] else "")
                    + ")"
                ),
                dados=dict(linha),
                fonte_url=f"https://brasilapi.com.br/api/cnpj/v1/{so_digitos(linha['cnpj'] or '')}",
            )
            for linha in linhas
        ]
