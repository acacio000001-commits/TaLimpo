# Investiga — painéis de apuração sobre fontes públicas

Sistema web com painéis separados (Pessoa, Empresa, Rastro Digital, Casos,
Administração), banco 100% SQL, controle de acesso por perfil e trilha de
auditoria. Roda inteiro em plano gratuito permanente.

```
Neon (Postgres)  ←  Render (Docker: FastAPI + ferramentas OSINT)  →  painéis
```

---

## 1. Banco no Neon (grátis, sem cartão)

1. Crie conta em <https://neon.com> → **New Project** → região `AWS us-east-2`
2. Copie a **Connection string** (`postgresql://...?sslmode=require`)

Não precisa rodar migração à mão: o `db/001_schema.sql` é aplicado sozinho a
cada boot da API e é idempotente.

## 2. API no Render (grátis)

1. Suba esta pasta num repositório no GitHub
2. <https://render.com> → **New** → **Blueprint** → aponte para o repositório
   (ele lê o `render.yaml`)
3. Preencha as variáveis: `DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_SENHA`
4. Aguarde o build (~5 min na primeira vez, por causa do maigret)

Acesse a URL do serviço e entre com o e-mail e a senha de administrador. O
primeiro usuário é criado sozinho **apenas se a tabela de usuários estiver
vazia** — troque a senha logo depois.

### O que esperar do plano gratuito

| Limite | Efeito prático |
|---|---|
| Dorme após 15 min sem acesso | A primeira busca do dia demora ~1 min. As seguintes são normais. |
| 512 MB RAM / 0.1 CPU | `maigret` limitado a 50 sites (`MAIGRET_TOP_SITES`). Aumente só se migrar de plano. |
| Disco efêmero | Nada é salvo em arquivo. Anexos vão como `bytea` no Postgres. |
| 750 h/mês por workspace | Um serviço só cabe folgado. |
| Neon 0,5 GB por projeto | Milhares de consultas. Anexos são o que pesa — limite de 8 MB por arquivo. |

## 3. Rodar local (opcional)

```bash
cp .env.example .env          # preencha DATABASE_URL
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Sem Docker as ferramentas CLI não existem — rode com `FERRAMENTAS_LOCAIS=0`
que os conectores locais aparecem como indisponíveis em vez de dar erro.

---

## Fontes já ligadas

| Fonte | Painel | Entrada | Credencial |
|---|---|---|---|
| CNPJ — Receita Federal (BrasilAPI) | empresa | CNPJ | não |
| CEP — endereço e coordenadas | empresa | CEP | não |
| Tabela FIPE — valor do veículo | empresa | código FIPE | não |
| Registro.br — domínio .br | digital | domínio | não |
| Sócios — empresas da pessoa | pessoa | CPF ou nome | banco próprio |
| Sanções CEIS/CNEP — Transparência | empresa | CPF ou CNPJ | chave grátis |
| Diários Oficiais (Querido Diário) | pessoa | nome | não |
| Google Dorks — buscas avançadas | pessoa | qualquer termo | não |
| Processos — DataJud/CNJ | pessoa | número CNJ | chave pública |
| DDD — região do telefone | digital | telefone | não |
| Gravatar — perfil por e-mail | digital | e-mail | não |
| Wayback Machine | digital | URL | não |
| holehe — contas por e-mail | digital | e-mail | ferramenta local |
| maigret — usuário em redes | digital | usuário | ferramenta local |
| phoneinfoga — telefone | digital | telefone | ferramenta local |
| theHarvester — e-mails e subdomínios | digital | domínio | ferramenta local |

O conector de CNPJ tenta três provedores em cadeia (BrasilAPI → minhareceita.org
→ cnpj.ws), porque o BrasilAPI limita taxa e devolve 429 com frequência. O
Wayback e o FIPE degradam em vez de falhar: se a fonte estiver fora do ar, eles
devolvem o link para conferência manual. A fonte da FIPE, em particular, cai com
frequência — a instabilidade é do site da FIPE, não do nosso lado.

---

## Extrator de documentos

Dentro da tela do caso existe um campo onde você cola texto solto — retorno de
bureau, transcrição de PDF, print convertido — e o sistema devolve todos os
CPF, CNPJ, e-mails, telefones, CEP, placas e URLs encontrados, com a opção de
transformar tudo em alvos do caso de uma vez.

Os padrões vêm do projeto público
[osint-brazuca-regex](https://github.com/osintbrazuca/osint-brazuca-regex), mas
com uma camada a mais: **CPF e CNPJ passam por validação de dígito
verificador**. O regex sozinho casa qualquer sequência de 11 ou 14 dígitos, o
que na prática transformaria todo telefone, protocolo e código de barras do
texto em "documento". O que reprova na validação aparece numa lista separada de
descartados, para você conferir se foi engano do extrator.

### Chaves gratuitas

- **DataJud/CNJ** — chave pública publicada em
  <https://datajud-wiki.cnj.jus.br/api-publica/acesso>
- **Portal da Transparência** — cadastro gratuito, chave chega por e-mail:
  <https://api.portaldatransparencia.gov.br/swagger-ui/index.html>

---

## Adicionar uma fonte nova

É o ponto central do projeto: **um arquivo, nada mais**.

Crie `app/connectors/minha_fonte.py`:

```python
from .base import Conector, Resultado

class MinhaFonte(Conector):
    chave     = "minha_fonte"
    nome      = "Nome que aparece no painel"
    painel    = "pessoa"        # pessoa | empresa | digital
    entrada   = "cpf"           # cpf|cnpj|documento|nome|email|telefone|username|url|cep|processo
    descricao = "O que essa fonte devolve"

    async def executar(self, valor, ctx):
        dados = await ctx.get_json(f"https://api.exemplo.gov.br/{valor}")
        return [Resultado(resumo=dados["nome"], dados=dados,
                          fonte_url="https://api.exemplo.gov.br")]
```

Reinicie. A fonte se registra sozinha, entra na tabela `fontes`, aparece no
painel certo e já fica sujeita ao liga/desliga do administrador e à auditoria.

Para **bureau contratado** (Informbank, Serasa, Boa Vista, Assertiva), copie
`app/connectors/_modelo_bureau.py` para um nome sem underline e ajuste o
endpoint. Arquivos que começam com `_` são ignorados pelo carregador.

## Fornecedor sem API

Nem todo fornecedor tem integração: bureau que só oferece painel web, agência
de investigação de campo, ofício respondido em papel. Para esses existe a
**importação manual**, dentro da tela do caso: você informa a origem, o que foi
consultado e o resumo, e opcionalmente cola o retorno completo.

O achado entra no dossiê junto dos automáticos, mas marcado com
`origem manual` e o nome de quem importou — quem lê o relatório distingue o que
o sistema coletou do que foi transcrito. A ação também vai para a auditoria
como `importacao_manual`.

---

## Cruzamento de sócios (opcional, único item pago)

É o recurso mais forte para apuração patrimonial: dado um CPF ou nome, listar
**todas as empresas** em que a pessoa figura como sócia. Nenhuma API gratuita
faz isso — a Receita publica a base inteira, mas não oferece consulta reversa.

O impedimento é tamanho: a base descompactada passa de **100 GB** e o Neon
gratuito oferece 0,5 GB. Não cabe, e não há truque. Para ligar é preciso um
Postgres próprio num VPS (Contabo ou Hetzner, a partir de ~US$5/mês com disco
de 200 GB).

O conector já está escrito e desligado sozinho: enquanto `SOCIOS_DATABASE_URL`
estiver vazia, ele aparece no painel como indisponível e nada quebra. O passo a
passo da carga está em [`db/002_socios.sql`](db/002_socios.sql), usando os ETLs
públicos [aphonsoar](https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ)
ou [turicas/socios-brasil](https://github.com/turicas/socios-brasil).

Uma ressalva que vale para o relatório: a Receita publica o CPF do sócio
**mascarado** (`***123456**`), revelando só os 6 dígitos do meio. A busca casa
por esse miolo, então pode haver coincidência numérica entre pessoas
diferentes. Confirme sempre o nome antes de usar o achado.

## Perfis de acesso

| Perfil | Painéis |
|---|---|
| `admin` | todos + administração |
| `investigador` | pessoa, empresa, digital, casos |
| `consulta` | somente casos (leitura) |

Ajuste em `perfil_paineis` (SQL) ou pelo painel de Administração.

---

## Aviso legal

Toda fonte aqui é **pública ou contratada**, e cada achado guarda a URL de
origem, o autor e o horário da coleta — é isso que sustenta o dossiê se ele
for questionado.

Atividade de detetive particular no Brasil é regulada pela **Lei 13.432/2017**
(exige contrato com o cliente e veda atuação em investigação criminal sem
requisição). O tratamento dos dados segue a **LGPD (Lei 13.709/2018)**: por
isso todo caso exige base legal e finalidade declaradas, e toda consulta fica
registrada na tabela `auditoria`.

Não conecte este sistema a bases de dados vazadas ou revendidas sem contrato.
Além de ilícito, o achado perde valor probatório justamente por não ter origem
demonstrável.
