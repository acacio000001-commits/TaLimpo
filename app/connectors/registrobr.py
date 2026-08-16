"""Registro.br — situação de um domínio .br, via BrasilAPI (grátis, sem chave).

Numa apuração serve para: confirmar que o site do investigado está ativo,
descobrir a data de expiração (domínio prestes a cair costuma indicar empresa
parando) e ver os servidores de nome, que entregam onde o site está hospedado.
"""
from __future__ import annotations

from .base import Conector, ErroConector, Resultado

ESTADOS = {
    "REGISTERED": "registrado",
    "AVAILABLE": "disponível (não registrado)",
    "EXPIRED": "expirado",
    "SUSPENDED": "suspenso",
    "WAITING_TRANSFER": "aguardando transferência",
}


class RegistroBr(Conector):
    chave = "registrobr"
    nome = "Registro.br — domínio .br"
    painel = "digital"
    entrada = "dominio"
    descricao = (
        "Situação do domínio, data de expiração e servidores de nome — mostra "
        "se o site está ativo e onde está hospedado."
    )

    async def executar(self, valor: str, ctx) -> list[Resultado]:
        dominio = (
            valor.strip().lower()
            .removeprefix("https://").removeprefix("http://")
            .strip("/").split("/")[0]
        )
        if "." not in dominio:
            raise ErroConector("Informe um domínio, ex.: empresa.com.br")

        url = f"https://brasilapi.com.br/api/registrobr/v1/{dominio}"
        dados = await ctx.get_json(url)
        if not dados:
            return []

        situacao = ESTADOS.get(dados.get("status", ""), dados.get("status", "?"))
        expira = (dados.get("expires-at") or "")[:10]
        hosts = dados.get("hosts") or []

        saida = [
            Resultado(
                resumo=(
                    f"{dados.get('fqdn', dominio)} — {situacao}"
                    + (f", expira em {expira}" if expira else "")
                ),
                dados=dados,
                fonte_url=url,
            )
        ]
        if hosts:
            saida.append(
                Resultado(
                    resumo="Servidores de nome: " + ", ".join(hosts),
                    dados={"hosts": hosts, "dominio": dominio},
                    fonte_url=url,
                )
            )
        return saida
