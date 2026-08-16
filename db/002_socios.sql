-- =====================================================================
-- BASE DE SÓCIOS — opcional, roda num Postgres SEPARADO
-- =====================================================================
--
-- Este arquivo NÃO é aplicado automaticamente. Ele existe para preparar o
-- banco extra que alimenta o conector `socios_cruzamento`.
--
-- POR QUE UM BANCO À PARTE
-- A base pública de CNPJ + sócios da Receita Federal passa de 100 GB depois de
-- descompactada. O plano gratuito do Neon oferece 0,5 GB por projeto — não
-- cabe, e não adianta insistir. Ou você sobe um Postgres num VPS (Contabo ou
-- Hetzner, a partir de ~US$5/mês, com disco de 200 GB) ou deixa esta fonte
-- desligada. Todo o resto do sistema continua gratuito de qualquer forma.
--
-- PASSO A PASSO
--
-- 1. Suba um Postgres no VPS (docker run postgres:16 já serve).
--
-- 2. Carregue a base usando um dos ETLs públicos:
--
--    https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ
--      → baixa, descompacta e insere direto no Postgres. É o mais direto.
--
--    https://github.com/turicas/socios-brasil
--      → converte os arquivos de largura fixa para CSV limpo. Use se preferir
--        controlar a carga você mesmo.
--
--    A carga completa leva de 6 a 12 horas na primeira vez. A Receita publica
--    atualização mensal.
--
-- 3. Rode ESTE arquivo nesse banco, para criar a view que o conector espera.
--
-- 4. No Render, cadastre a variável:
--      SOCIOS_DATABASE_URL=postgresql://usuario:senha@ip-do-vps:5432/cnpj
--    A fonte aparece sozinha como disponível no próximo boot.
--
-- ---------------------------------------------------------------------
-- OBSERVAÇÃO SOBRE O CPF DOS SÓCIOS
-- A Receita publica o CPF do sócio mascarado, no formato ***123456**. Só os
-- 6 dígitos do meio são revelados. Por isso a busca por CPF casa pelo miolo —
-- o que significa que pode haver homônimo numérico. SEMPRE confirme o nome do
-- sócio antes de usar o achado no relatório.
-- ---------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Ajuste os nomes das colunas conforme o ETL que você usou. O que está abaixo
-- corresponde ao schema do repositório aphonsoar.
CREATE OR REPLACE VIEW vw_socios_busca AS
SELECT
    s.nome_socio_razao_social          AS nome_socio,
    s.cpf_cnpj_socio                   AS doc_socio,
    e.cnpj_basico                      AS cnpj,
    e.razao_social                     AS razao_social,
    q.descricao                        AS qualificacao,
    s.data_entrada_sociedade           AS data_entrada
FROM socios s
JOIN empresa e            ON e.cnpj_basico = s.cnpj_basico
LEFT JOIN quals q         ON q.codigo::text = s.qualificacao_socio::text;

-- Sem estes índices a busca por nome demora minutos.
CREATE INDEX IF NOT EXISTS socios_doc_idx
    ON socios (cpf_cnpj_socio);

CREATE INDEX IF NOT EXISTS socios_nome_trgm_idx
    ON socios USING gin (upper(nome_socio_razao_social) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS socios_cnpj_basico_idx
    ON socios (cnpj_basico);

CREATE INDEX IF NOT EXISTS empresa_cnpj_basico_idx
    ON empresa (cnpj_basico);
