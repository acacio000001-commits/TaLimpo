"""Painel de Casos: clientes, casos, alvos, timeline, anexos e dossiê."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from .. import audit, db, extrator, security
from ..auth import exige_painel

router = APIRouter(prefix="/api", tags=["casos"])
exige_casos = exige_painel("casos")

TAMANHO_MAX_ANEXO = 8 * 1024 * 1024  # 8 MB — free tier do Neon é 0,5 GB


# ------------------------------------------------------------------ modelos
class EntradaCliente(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    documento: str | None = None
    contato: str | None = None
    observacao: str | None = None


class EntradaCaso(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    titulo: str = Field(min_length=2, max_length=200)
    cliente_id: int | None = None
    base_legal: str = "execucao_contrato"
    finalidade: str | None = None
    descricao: str | None = None


class EntradaAlvo(BaseModel):
    tipo: str = Field(min_length=2, max_length=20)
    valor: str = Field(min_length=1, max_length=300)
    rotulo: str | None = None


class EntradaNota(BaseModel):
    texto: str = Field(min_length=1, max_length=5000)
    tipo: str = "nota"


class EntradaExtracao(BaseModel):
    texto: str = Field(min_length=3, max_length=200_000)
    criar_alvos: bool = False


class EntradaImportacao(BaseModel):
    origem: str = Field(min_length=2, max_length=160)
    entrada: str = Field(min_length=1, max_length=300)
    resumo: str = Field(min_length=2, max_length=2000)
    conteudo: str = Field(default="", max_length=200_000)


class EntradaStatus(BaseModel):
    status: str = Field(pattern="^(aberto|suspenso|encerrado)$")


# ----------------------------------------------------------------- clientes
@router.get("/clientes")
async def listar_clientes(usuario: dict = Depends(exige_casos)):
    return await db.buscar_todos("SELECT * FROM clientes ORDER BY nome")


@router.post("/clientes")
async def criar_cliente(dados: EntradaCliente, request: Request, usuario: dict = Depends(exige_casos)):
    linha = await db.buscar_um(
        """
        INSERT INTO clientes (nome, documento, contato, observacao, criado_por)
        VALUES (%s, %s, %s, %s, %s) RETURNING *
        """,
        (dados.nome, dados.documento, dados.contato, dados.observacao, usuario["id"]),
    )
    await audit.registrar(
        usuario_id=usuario["id"], acao="cliente_criado", entidade="cliente",
        entidade_id=linha["id"], req=request,
    )
    return linha


# -------------------------------------------------------------------- casos
@router.get("/casos")
async def listar_casos(status: str | None = None, usuario: dict = Depends(exige_casos)):
    sql = """
        SELECT c.*, cl.nome AS cliente_nome, u.nome AS responsavel_nome,
               (SELECT count(*) FROM alvos a WHERE a.caso_id = c.id)     AS qtd_alvos,
               (SELECT count(*) FROM consultas q WHERE q.caso_id = c.id) AS qtd_consultas
        FROM casos c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        LEFT JOIN usuarios u  ON u.id = c.responsavel_id
    """
    if status:
        return await db.buscar_todos(sql + " WHERE c.status = %s ORDER BY c.criado_em DESC", (status,))
    return await db.buscar_todos(sql + " ORDER BY c.criado_em DESC")


@router.post("/casos")
async def criar_caso(dados: EntradaCaso, request: Request, usuario: dict = Depends(exige_casos)):
    existe = await db.buscar_um("SELECT 1 FROM casos WHERE codigo = %s", (dados.codigo,))
    if existe:
        raise HTTPException(409, f"Já existe um caso com o código '{dados.codigo}'")

    linha = await db.buscar_um(
        """
        INSERT INTO casos (codigo, titulo, cliente_id, base_legal, finalidade,
                           descricao, responsavel_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *
        """,
        (
            dados.codigo, dados.titulo, dados.cliente_id, dados.base_legal,
            dados.finalidade, dados.descricao, usuario["id"],
        ),
    )
    await audit.registrar(
        usuario_id=usuario["id"], acao="caso_criado", entidade="caso",
        entidade_id=linha["id"], detalhes={"codigo": dados.codigo}, req=request,
    )
    return linha


@router.get("/casos/{caso_id}")
async def ver_caso(caso_id: int, usuario: dict = Depends(exige_casos)):
    caso = await db.buscar_um(
        """
        SELECT c.*, cl.nome AS cliente_nome, u.nome AS responsavel_nome
        FROM casos c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        LEFT JOIN usuarios u  ON u.id = c.responsavel_id
        WHERE c.id = %s
        """,
        (caso_id,),
    )
    if not caso:
        raise HTTPException(404, "Caso não encontrado")

    caso["alvos"] = await db.buscar_todos(
        "SELECT * FROM alvos WHERE caso_id = %s ORDER BY criado_em", (caso_id,)
    )
    caso["eventos"] = await db.buscar_todos(
        """
        SELECT e.*, u.nome AS usuario_nome FROM eventos_caso e
        LEFT JOIN usuarios u ON u.id = e.usuario_id
        WHERE e.caso_id = %s ORDER BY e.criado_em DESC
        """,
        (caso_id,),
    )
    caso["anexos"] = await db.buscar_todos(
        "SELECT id, nome, mime, tamanho, sha256, exif, enviado_em FROM anexos "
        "WHERE caso_id = %s ORDER BY enviado_em DESC",
        (caso_id,),
    )
    return caso


@router.patch("/casos/{caso_id}/status")
async def mudar_status(
    caso_id: int, dados: EntradaStatus, request: Request, usuario: dict = Depends(exige_casos)
):
    linha = await db.buscar_um(
        """
        UPDATE casos SET status = %s,
               encerrado_em = CASE WHEN %s = 'encerrado' THEN now() ELSE NULL END
        WHERE id = %s RETURNING *
        """,
        (dados.status, dados.status, caso_id),
    )
    if not linha:
        raise HTTPException(404, "Caso não encontrado")
    await audit.registrar(
        usuario_id=usuario["id"], acao="caso_status", entidade="caso",
        entidade_id=caso_id, detalhes={"status": dados.status}, req=request,
    )
    return linha


# -------------------------------------------------------------------- alvos
@router.post("/casos/{caso_id}/alvos")
async def criar_alvo(
    caso_id: int, dados: EntradaAlvo, request: Request, usuario: dict = Depends(exige_casos)
):
    linha = await db.buscar_um(
        """
        INSERT INTO alvos (caso_id, tipo, valor, rotulo) VALUES (%s, %s, %s, %s)
        ON CONFLICT (caso_id, tipo, valor) DO UPDATE SET rotulo = EXCLUDED.rotulo
        RETURNING *
        """,
        (caso_id, dados.tipo.strip().lower(), dados.valor.strip(), dados.rotulo),
    )
    await audit.registrar(
        usuario_id=usuario["id"], acao="alvo_criado", entidade="alvo",
        entidade_id=linha["id"], alvo_valor=dados.valor.strip(),
        detalhes={"caso_id": caso_id, "tipo": dados.tipo}, req=request,
    )
    return linha


@router.delete("/casos/{caso_id}/alvos/{alvo_id}")
async def apagar_alvo(
    caso_id: int, alvo_id: int, request: Request, usuario: dict = Depends(exige_casos)
):
    await db.executar("DELETE FROM alvos WHERE id = %s AND caso_id = %s", (alvo_id, caso_id))
    await audit.registrar(
        usuario_id=usuario["id"], acao="alvo_removido", entidade="alvo",
        entidade_id=alvo_id, req=request,
    )
    return {"ok": True}


# ----------------------------------------------------------------- timeline
@router.post("/casos/{caso_id}/eventos")
async def criar_evento(
    caso_id: int, dados: EntradaNota, request: Request, usuario: dict = Depends(exige_casos)
):
    linha = await db.buscar_um(
        "INSERT INTO eventos_caso (caso_id, tipo, texto, usuario_id) "
        "VALUES (%s, %s, %s, %s) RETURNING *",
        (caso_id, dados.tipo, dados.texto, usuario["id"]),
    )
    return linha


# ---------------------------------------------------- extração de documentos
@router.post("/casos/{caso_id}/extrair")
async def extrair_documentos(
    caso_id: int,
    dados: EntradaExtracao,
    request: Request,
    usuario: dict = Depends(exige_casos),
):
    """Lê um texto solto e devolve os documentos brasileiros encontrados.

    CPF e CNPJ passam por validação de dígito verificador — o que reprova vem
    separado em `suspeitos`, porque o padrão de regex sozinho casa qualquer
    sequência de 11 ou 14 dígitos e encheria o caso de protocolo e código de
    barras achando que é documento.
    """
    resultado = extrator.extrair(dados.texto)
    criados = 0

    if dados.criar_alvos:
        for achado in resultado.achados:
            if achado.tipo not in extrator.VIRAM_ALVO:
                continue
            await db.executar(
                """
                INSERT INTO alvos (caso_id, tipo, valor, rotulo)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (caso_id, tipo, valor) DO NOTHING
                """,
                (caso_id, achado.tipo, achado.valor, "extraído de texto"),
            )
            criados += 1

    await audit.registrar(
        usuario_id=usuario["id"],
        acao="extracao_documentos",
        entidade="caso",
        entidade_id=caso_id,
        detalhes={
            "encontrados": len(resultado.achados),
            "suspeitos": len(resultado.suspeitos),
            "alvos_criados": criados,
        },
        req=request,
    )

    return {**resultado.como_dict(), "alvos_criados": criados}


# -------------------------------------------------------- importação manual
@router.post("/casos/{caso_id}/importar")
async def importar_consulta(
    caso_id: int,
    dados: EntradaImportacao,
    request: Request,
    usuario: dict = Depends(exige_casos),
):
    """Registra no caso o retorno de um serviço que só tem painel web.

    É o caminho para bureau contratado sem API (Informbank) e para diligência
    externa (agência de campo, ofício respondido). O achado entra no dossiê
    igual aos automáticos, mas com a origem declarada como manual — quem ler
    o relatório sabe distinguir o que a máquina coletou do que foi colado.
    """
    consulta = await db.buscar_um(
        """
        INSERT INTO consultas (caso_id, fonte_chave, entrada, status,
                               usuario_id, concluida_em, duracao_ms)
        VALUES (%s, 'importacao_manual', %s, 'ok', %s, now(), 0)
        RETURNING id
        """,
        (caso_id, dados.entrada.strip(), usuario["id"]),
    )

    await db.executar(
        """
        INSERT INTO resultados (consulta_id, resumo, dados)
        VALUES (%s, %s, %s::jsonb)
        """,
        (
            consulta["id"],
            f"[{dados.origem.strip()}] {dados.resumo.strip()}"[:2000],
            json.dumps(
                {
                    "origem": dados.origem.strip(),
                    "conteudo": dados.conteudo.strip(),
                    "importado_por": usuario["nome"],
                    "_manual": True,
                },
                ensure_ascii=False,
            ),
        ),
    )

    await db.executar(
        "INSERT INTO eventos_caso (caso_id, tipo, texto, usuario_id) VALUES (%s, %s, %s, %s)",
        (
            caso_id,
            "importacao",
            f"Importação manual de {dados.origem.strip()}: {dados.resumo.strip()[:200]}",
            usuario["id"],
        ),
    )

    await audit.registrar(
        usuario_id=usuario["id"],
        acao="importacao_manual",
        entidade="consulta",
        entidade_id=consulta["id"],
        alvo_valor=dados.entrada.strip(),
        detalhes={"caso_id": caso_id, "origem": dados.origem.strip()},
        req=request,
    )
    return {"consulta_id": consulta["id"], "ok": True}


# ------------------------------------------------------------------ anexos
@router.post("/casos/{caso_id}/anexos")
async def enviar_anexo(
    caso_id: int,
    request: Request,
    arquivo: UploadFile = File(...),
    observacao: str = Form(""),
    usuario: dict = Depends(exige_casos),
):
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_ANEXO:
        raise HTTPException(413, "Arquivo acima de 8 MB")

    exif = _ler_exif(conteudo, arquivo.filename or "anexo")

    linha = await db.buscar_um(
        """
        INSERT INTO anexos (caso_id, nome, mime, tamanho, sha256, exif, conteudo, enviado_por)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, nome, mime, tamanho, sha256, exif, enviado_em
        """,
        (
            caso_id,
            arquivo.filename or "anexo",
            arquivo.content_type,
            len(conteudo),
            security.sha256_bytes(conteudo),
            json.dumps(exif, ensure_ascii=False, default=str),
            conteudo,
            usuario["id"],
        ),
    )
    await audit.registrar(
        usuario_id=usuario["id"], acao="anexo_enviado", entidade="anexo",
        entidade_id=linha["id"], detalhes={"caso_id": caso_id, "observacao": observacao},
        req=request,
    )
    return linha


@router.get("/anexos/{anexo_id}")
async def baixar_anexo(anexo_id: int, usuario: dict = Depends(exige_casos)):
    from fastapi.responses import Response as RespostaBruta

    linha = await db.buscar_um(
        "SELECT nome, mime, conteudo FROM anexos WHERE id = %s", (anexo_id,)
    )
    if not linha:
        raise HTTPException(404, "Anexo não encontrado")
    return RespostaBruta(
        content=bytes(linha["conteudo"]),
        media_type=linha["mime"] or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{linha["nome"]}"'},
    )


def _ler_exif(conteudo: bytes, nome: str) -> dict:
    """EXIF via exiftool. GPS e data original são o que mais rende no caso."""
    import shutil

    if not shutil.which("exiftool"):
        return {"_aviso": "exiftool não instalado nesta imagem"}

    sufixo = Path(nome).suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=sufixo, delete=False) as tmp:
        tmp.write(conteudo)
        caminho = tmp.name
    try:
        saida = subprocess.run(
            ["exiftool", "-json", "-n", "-charset", "utf8", caminho],
            capture_output=True, text=True, timeout=25,
        )
        dados = json.loads(saida.stdout or "[]")
        if not dados:
            return {}
        bruto = dados[0]
        bruto.pop("SourceFile", None)
        return bruto
    except Exception as e:
        return {"_erro": f"{type(e).__name__}: {e}"}
    finally:
        Path(caminho).unlink(missing_ok=True)


# ------------------------------------------------------------------ dossiê
@router.get("/casos/{caso_id}/dossie")
async def dossie(caso_id: int, request: Request, usuario: dict = Depends(exige_casos)):
    """Pacote completo do caso — é isso que o front imprime em PDF."""
    caso = await ver_caso(caso_id, usuario)

    caso["consultas"] = await db.buscar_todos(
        """
        SELECT q.id, q.fonte_chave, f.nome AS fonte_nome, f.painel,
               q.entrada, q.status, q.iniciada_em, q.duracao_ms,
               u.nome AS usuario_nome,
               COALESCE(
                   json_agg(
                       json_build_object(
                           'resumo', r.resumo,
                           'fonte_url', r.fonte_url,
                           'coletado_em', r.coletado_em,
                           'dados', r.dados
                       ) ORDER BY r.id
                   ) FILTER (WHERE r.id IS NOT NULL),
                   '[]'::json
               ) AS resultados
        FROM consultas q
        LEFT JOIN fontes     f ON f.chave = q.fonte_chave
        LEFT JOIN usuarios   u ON u.id = q.usuario_id
        LEFT JOIN resultados r ON r.consulta_id = q.id
        WHERE q.caso_id = %s
        GROUP BY q.id, f.nome, f.painel, u.nome
        ORDER BY q.iniciada_em
        """,
        (caso_id,),
    )

    await audit.registrar(
        usuario_id=usuario["id"], acao="dossie_gerado", entidade="caso",
        entidade_id=caso_id, req=request,
    )
    return caso
