"""Extrator de documentos brasileiros a partir de texto solto.

Cola-se o retorno de um bureau, a transcrição de um PDF ou um print, e daqui
saem os CPF, CNPJ, telefones, e-mails, CEP e placas encontrados — prontos para
virar alvos do caso.

Os padrões vêm do projeto osint-brazuca-regex (público, contexto Brasil):
https://github.com/osintbrazuca/osint-brazuca-regex

IMPORTANTE — por que não usamos o regex puro:
o padrão de CPF casa QUALQUER sequência de 11 dígitos, e o de CNPJ qualquer
sequência de 14. Num texto real isso vira ruído: número de protocolo, código de
barras, chave de nota fiscal e telefone com DDI entram como "CPF". Por isso
todo CPF e CNPJ passa pela validação de dígito verificador antes de ser aceito,
e o que não valida é devolvido em separado, marcado como suspeito.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ------------------------------------------------------------------ padrões
PADROES: dict[str, re.Pattern] = {
    "cpf": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "cnpj": re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    "cep": re.compile(r"\b\d{5}-?\d{3}\b"),
    "placa": re.compile(r"\b[A-Z]{3}-?\d[0-9A-Z]\d{2}\b"),
    "email": re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "telefone": re.compile(
        r"(?:\+?55\s?)?\(?\b(?:1[1-9]|2[12478]|3[1234578]|4[1-9]|"
        r"5[1345]|6[1-9]|7[134579]|8[1-9]|9[1-9])\)?\s?9?\d{4}[-.\s]?\d{4}\b"
    ),
    "url": re.compile(r"\bhttps?://[^\s<>\"')]+"),
}

# Tipos que viram alvo do caso automaticamente.
VIRAM_ALVO = {"cpf", "cnpj", "email", "telefone", "placa"}


@dataclass
class Achado:
    tipo: str
    valor: str            # normalizado (só dígitos, quando for documento)
    original: str         # como apareceu no texto
    valido: bool = True   # False = casou o padrão mas reprovou na validação
    nota: str = ""


@dataclass
class Extracao:
    achados: list[Achado] = field(default_factory=list)
    suspeitos: list[Achado] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            "achados": [vars(a) for a in self.achados],
            "suspeitos": [vars(a) for a in self.suspeitos],
            "total": len(self.achados),
        }


# ------------------------------------------------------------- validadores
def _digitos(v: str) -> str:
    return "".join(c for c in v if c.isdigit())


def cpf_valido(valor: str) -> bool:
    cpf = _digitos(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        if resto == 10:
            resto = 0
        if resto != int(cpf[tamanho]):
            return False
    return True


def cnpj_valido(valor: str) -> bool:
    cnpj = _digitos(valor)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, posicao in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(cnpj[i]) * pesos[i] for i in range(posicao))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(cnpj[posicao]):
            return False
    return True


# ---------------------------------------------------------------- extração
def extrair(texto: str) -> Extracao:
    resultado = Extracao()
    vistos: set[tuple[str, str]] = set()

    for tipo, padrao in PADROES.items():
        for achado in padrao.finditer(texto):
            bruto = achado.group(0).strip()
            valor = _digitos(bruto) if tipo in ("cpf", "cnpj", "cep", "telefone") else bruto

            if tipo == "placa":
                valor = bruto.replace("-", "").upper()
            if tipo == "email":
                valor = bruto.lower()

            chave = (tipo, valor)
            if chave in vistos:
                continue
            vistos.add(chave)

            item = Achado(tipo=tipo, valor=valor, original=bruto)

            if tipo == "cpf" and not cpf_valido(valor):
                item.valido = False
                item.nota = "Dígito verificador não confere — provavelmente não é um CPF"
                resultado.suspeitos.append(item)
                continue
            if tipo == "cnpj" and not cnpj_valido(valor):
                item.valido = False
                item.nota = "Dígito verificador não confere — provavelmente não é um CNPJ"
                resultado.suspeitos.append(item)
                continue
            if tipo == "telefone":
                if len(valor) not in (10, 11, 12, 13):
                    continue
                item.nota = "Sem validação possível — confira o número"

            resultado.achados.append(item)

    # CPF que também casou como CNPJ (ou vice-versa) é ruído previsível:
    # o padrão de CNPJ é mais largo e engole sequências de 11 dígitos.
    cpfs = {a.valor for a in resultado.achados if a.tipo == "cpf"}
    resultado.achados = [
        a for a in resultado.achados
        if not (a.tipo == "cnpj" and a.valor[:11] in cpfs)
    ]

    ordem = {"cpf": 0, "cnpj": 1, "email": 2, "telefone": 3, "placa": 4, "cep": 5, "url": 6}
    resultado.achados.sort(key=lambda a: (ordem.get(a.tipo, 9), a.valor))
    return resultado
