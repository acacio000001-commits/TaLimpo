"""Gerador de Google Dorks — monta as buscas avançadas prontas.

Não consome API nem chave: devolve os links já formados para você abrir. É a
ferramenta que mais rende em apuração de pessoa, porque alcança conteúdo que
API nenhuma indexa (grupo de Facebook, PDF de prefeitura, ata de condomínio,
classificado antigo).
"""
from __future__ import annotations

from urllib.parse import quote_plus

from .base import Conector, ErroConector, Resultado

# (rótulo, modelo do dork). {t} é substituído pelo termo entre aspas.
DORKS = [
    ("Menções exatas", '"{t}"'),
    ("Documentos oficiais (.gov.br)", '"{t}" site:gov.br'),
    ("PDF e planilhas", '"{t}" (filetype:pdf OR filetype:xlsx OR filetype:docx)'),
    ("Processos e jurisprudência", '"{t}" (site:jusbrasil.com.br OR site:escavador.com OR site:jus.br)'),
    ("Diários oficiais", '"{t}" ("diário oficial" OR "diario oficial")'),
    ("Redes sociais", '"{t}" (site:instagram.com OR site:facebook.com OR site:linkedin.com OR site:x.com)'),
    ("Classificados e veículos", '"{t}" (site:olx.com.br OR site:webmotors.com.br OR site:mercadolivre.com.br)'),
    ("Empresas e sociedade", '"{t}" (site:econodata.com.br OR site:cnpj.biz OR site:casadosdados.com.br)'),
    ("Currículos e contatos", '"{t}" (curriculo OR currículo OR "e-mail" OR contato)'),
    ("Notícias", '"{t}" (site:g1.globo.com OR site:uol.com.br OR site:folha.uol.com.br)'),
]

BUSCADORES = {
    "Google": "https://www.google.com/search?q={q}",
    "Bing": "https://www.bing.com/search?q={q}",
    "DuckDuckGo": "https://duckduckgo.com/?q={q}",
}


class GoogleDorks(Conector):
    chave = "google_dorks"
    nome = "Google Dorks — buscas avançadas"
    painel = "pessoa"
    entrada = "nome"
    descricao = (
        "Monta 10 buscas avançadas prontas para o termo (nome, CPF, telefone, "
        "apelido) em Google, Bing e DuckDuckGo. Abra e leia — é trabalho manual."
    )

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        termo = valor.strip()
        if len(termo) < 3:
            raise ErroConector("Informe pelo menos 3 caracteres")

        saida: list[Resultado] = []
        for rotulo, modelo in DORKS:
            consulta = modelo.format(t=termo)
            codificada = quote_plus(consulta)
            links = {n: u.format(q=codificada) for n, u in BUSCADORES.items()}

            saida.append(
                Resultado(
                    resumo=f"{rotulo}: {consulta}",
                    dados={"dork": consulta, "termo": termo, "links": links},
                    fonte_url=links["Google"],
                )
            )
        return saida
