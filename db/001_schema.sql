-- =====================================================================
-- OSINT Detetive — esquema Postgres (Neon)
-- Idempotente: roda a cada boot da API sem quebrar nada.
-- =====================================================================

-- ---------------------------------------------------------------- ACESSO
CREATE TABLE IF NOT EXISTS perfis (
    id          serial PRIMARY KEY,
    chave       text UNIQUE NOT NULL,
    nome        text NOT NULL,
    descricao   text,
    criado_em   timestamptz NOT NULL DEFAULT now()
);

-- Painéis liberados por perfil: pessoa | empresa | digital | casos | admin
CREATE TABLE IF NOT EXISTS perfil_paineis (
    perfil_id   int NOT NULL REFERENCES perfis(id) ON DELETE CASCADE,
    painel      text NOT NULL,
    PRIMARY KEY (perfil_id, painel)
);

CREATE TABLE IF NOT EXISTS usuarios (
    id           serial PRIMARY KEY,
    nome         text NOT NULL,
    email        text NOT NULL,
    senha_hash   text NOT NULL,
    perfil_id    int  NOT NULL REFERENCES perfis(id),
    ativo        boolean NOT NULL DEFAULT true,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    ultimo_login timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_uniq ON usuarios (lower(email));

CREATE TABLE IF NOT EXISTS sessoes (
    id          uuid PRIMARY KEY,
    usuario_id  int NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token_hash  text UNIQUE NOT NULL,
    ip          text,
    user_agent  text,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    expira_em   timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessoes_usuario_idx ON sessoes (usuario_id);
CREATE INDEX IF NOT EXISTS sessoes_expira_idx  ON sessoes (expira_em);

-- ------------------------------------------------------- FONTES (PLUGINS)
-- Sincronizada a partir do registro de conectores em app/connectors/.
-- Para adicionar uma base nova basta soltar um arquivo .py lá: a linha
-- aparece aqui sozinha no próximo boot.
CREATE TABLE IF NOT EXISTS fontes (
    chave             text PRIMARY KEY,
    nome              text NOT NULL,
    painel            text NOT NULL,
    entrada           text NOT NULL,
    descricao         text,
    requer_credencial text[] NOT NULL DEFAULT '{}',
    disponivel        boolean NOT NULL DEFAULT true,
    ativa             boolean NOT NULL DEFAULT true,
    custo             text NOT NULL DEFAULT 'gratuito',
    atualizada_em     timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------- CASOS E ALVOS
CREATE TABLE IF NOT EXISTS clientes (
    id          serial PRIMARY KEY,
    nome        text NOT NULL,
    documento   text,
    contato     text,
    observacao  text,
    criado_por  int REFERENCES usuarios(id),
    criado_em   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS casos (
    id            serial PRIMARY KEY,
    codigo        text UNIQUE NOT NULL,
    titulo        text NOT NULL,
    cliente_id    int REFERENCES clientes(id) ON DELETE SET NULL,
    status        text NOT NULL DEFAULT 'aberto',   -- aberto | suspenso | encerrado
    base_legal    text NOT NULL DEFAULT 'execucao_contrato',
    finalidade    text,
    descricao     text,
    responsavel_id int REFERENCES usuarios(id),
    criado_em     timestamptz NOT NULL DEFAULT now(),
    encerrado_em  timestamptz
);
CREATE INDEX IF NOT EXISTS casos_status_idx ON casos (status);

-- tipo: cpf | cnpj | nome | email | telefone | username | dominio | placa | url
CREATE TABLE IF NOT EXISTS alvos (
    id         serial PRIMARY KEY,
    caso_id    int NOT NULL REFERENCES casos(id) ON DELETE CASCADE,
    tipo       text NOT NULL,
    valor      text NOT NULL,
    rotulo     text,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (caso_id, tipo, valor)
);
CREATE INDEX IF NOT EXISTS alvos_caso_idx  ON alvos (caso_id);
CREATE INDEX IF NOT EXISTS alvos_valor_idx ON alvos (valor);

-- --------------------------------------------------- CONSULTAS E RESULTADOS
CREATE TABLE IF NOT EXISTS consultas (
    id            bigserial PRIMARY KEY,
    caso_id       int REFERENCES casos(id) ON DELETE CASCADE,
    alvo_id       int REFERENCES alvos(id) ON DELETE SET NULL,
    fonte_chave   text NOT NULL,
    entrada       text NOT NULL,
    status        text NOT NULL DEFAULT 'pendente',  -- pendente|ok|vazio|erro
    usuario_id    int REFERENCES usuarios(id),
    iniciada_em   timestamptz NOT NULL DEFAULT now(),
    concluida_em  timestamptz,
    duracao_ms    int,
    erro          text
);
CREATE INDEX IF NOT EXISTS consultas_caso_idx  ON consultas (caso_id, iniciada_em DESC);
CREATE INDEX IF NOT EXISTS consultas_fonte_idx ON consultas (fonte_chave);

CREATE TABLE IF NOT EXISTS resultados (
    id           bigserial PRIMARY KEY,
    consulta_id  bigint NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
    resumo       text,
    dados        jsonb NOT NULL DEFAULT '{}'::jsonb,
    fonte_url    text,
    coletado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resultados_consulta_idx ON resultados (consulta_id);
CREATE INDEX IF NOT EXISTS resultados_dados_idx    ON resultados USING gin (dados);

-- ----------------------------------------------------------- ANEXOS
-- Conteúdo em bytea porque o disco do Render é efêmero.
CREATE TABLE IF NOT EXISTS anexos (
    id          bigserial PRIMARY KEY,
    caso_id     int NOT NULL REFERENCES casos(id) ON DELETE CASCADE,
    nome        text NOT NULL,
    mime        text,
    tamanho     int,
    sha256      text,
    exif        jsonb NOT NULL DEFAULT '{}'::jsonb,
    conteudo    bytea,
    enviado_por int REFERENCES usuarios(id),
    enviado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS anexos_caso_idx ON anexos (caso_id);

-- --------------------------------------------------------- TIMELINE
CREATE TABLE IF NOT EXISTS eventos_caso (
    id         bigserial PRIMARY KEY,
    caso_id    int NOT NULL REFERENCES casos(id) ON DELETE CASCADE,
    tipo       text NOT NULL DEFAULT 'nota',
    texto      text NOT NULL,
    usuario_id int REFERENCES usuarios(id),
    criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS eventos_caso_idx ON eventos_caso (caso_id, criado_em DESC);

-- ------------------------------------------------------- AUDITORIA (LGPD)
CREATE TABLE IF NOT EXISTS auditoria (
    id           bigserial PRIMARY KEY,
    usuario_id   int REFERENCES usuarios(id) ON DELETE SET NULL,
    acao         text NOT NULL,
    entidade     text,
    entidade_id  text,
    alvo_valor   text,
    ip           text,
    user_agent   text,
    detalhes     jsonb NOT NULL DEFAULT '{}'::jsonb,
    criado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS auditoria_criado_idx  ON auditoria (criado_em DESC);
CREATE INDEX IF NOT EXISTS auditoria_usuario_idx ON auditoria (usuario_id, criado_em DESC);

-- ----------------------------------------------------------- VISÕES
CREATE OR REPLACE VIEW vw_consultas_detalhe AS
SELECT c.id,
       c.iniciada_em,
       c.status,
       c.duracao_ms,
       c.entrada,
       c.fonte_chave,
       f.nome   AS fonte_nome,
       f.painel AS fonte_painel,
       ca.codigo AS caso_codigo,
       ca.titulo AS caso_titulo,
       u.nome    AS usuario_nome,
       (SELECT count(*) FROM resultados r WHERE r.consulta_id = c.id) AS qtd_resultados
FROM consultas c
LEFT JOIN fontes   f  ON f.chave = c.fonte_chave
LEFT JOIN casos    ca ON ca.id = c.caso_id
LEFT JOIN usuarios u  ON u.id = c.usuario_id;

CREATE OR REPLACE VIEW vw_painel_numeros AS
SELECT (SELECT count(*) FROM casos WHERE status = 'aberto')                              AS casos_abertos,
       (SELECT count(*) FROM alvos)                                                      AS alvos,
       (SELECT count(*) FROM consultas WHERE iniciada_em > now() - interval '30 days')   AS consultas_30d,
       (SELECT count(*) FROM fontes WHERE ativa AND disponivel)                          AS fontes_ativas;

-- --------------------------------------------------------- PERFIS PADRÃO
INSERT INTO perfis (chave, nome, descricao) VALUES
    ('admin',      'Administrador', 'Acesso total, gestão de usuários, fontes e auditoria'),
    ('investigador','Investigador', 'Todos os painéis de busca e gestão dos próprios casos'),
    ('consulta',   'Consulta',      'Somente leitura de casos e dossiês, sem disparar buscas')
ON CONFLICT (chave) DO NOTHING;

-- Fonte especial: não é um conector, é o retorno colado à mão de um serviço
-- que só tem painel web (bureau contratado, agência de campo, ofício).
INSERT INTO fontes (chave, nome, painel, entrada, descricao, custo)
VALUES ('importacao_manual', 'Importação manual', 'casos', 'texto',
        'Retorno de consulta contratada ou diligência externa, colado à mão e '
        'registrado no caso com origem, autor e data.', 'contratado')
ON CONFLICT (chave) DO NOTHING;

INSERT INTO perfil_paineis (perfil_id, painel)
SELECT p.id, x.painel
FROM perfis p
JOIN (VALUES
    ('admin','pessoa'), ('admin','empresa'), ('admin','digital'), ('admin','casos'), ('admin','admin'),
    ('investigador','pessoa'), ('investigador','empresa'), ('investigador','digital'), ('investigador','casos'),
    ('consulta','casos')
) AS x(perfil, painel) ON x.perfil = p.chave
ON CONFLICT DO NOTHING;
