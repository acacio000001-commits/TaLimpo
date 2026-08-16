/* Investiga — front dos painéis.
 * Sem framework de propósito: o Render free tem 512 MB e o backend Python já
 * ocupa boa parte. Se um dia virar Next.js, a API não muda.
 */
'use strict';

// Mesma origem por padrão. Para hospedar o front separado (Cloudflare Pages),
// rode no console: localStorage.setItem('api_base', 'https://SEU-APP.onrender.com')
const API = localStorage.getItem('api_base') || '';

const estado = {
  usuario: null,
  fontes: [],
  rota: 'modulos',
  caso: null,
  casos: [],
};

const MODULOS = [
  { rota: 'pessoa',  painel: 'pessoa',  icone: '👤', titulo: 'Pessoa Física',
    texto: 'Nome em diários oficiais, processos judiciais pelo número CNJ e sanções públicas.' },
  { rota: 'empresa', painel: 'empresa', icone: '🏢', titulo: 'Empresa / CNPJ',
    texto: 'Quadro societário completo, situação cadastral, endereço e sanções CEIS/CNEP.' },
  { rota: 'digital', painel: 'digital', icone: '🌐', titulo: 'Rastro Digital',
    texto: 'E-mail, apelido e telefone: contas cadastradas, perfis em redes e páginas apagadas.' },
  { rota: 'casos',   painel: 'casos',   icone: '📁', titulo: 'Casos e Dossiê',
    texto: 'Amarra tudo a um caso: alvos, linha do tempo, anexos com EXIF e dossiê para impressão.' },
  { rota: 'admin',   painel: 'admin',   icone: '⚙',  titulo: 'Administração',
    texto: 'Equipe, perfis de acesso, liga/desliga fontes e trilha de auditoria.' },
];

const ROTULO_ENTRADA = {
  cpf: 'CPF', cnpj: 'CNPJ', documento: 'CPF ou CNPJ', nome: 'Nome completo',
  email: 'E-mail', telefone: 'Telefone com DDD', username: 'Usuário / apelido',
  dominio: 'Domínio', url: 'URL ou domínio', cep: 'CEP', processo: 'Número CNJ do processo',
};

// ------------------------------------------------------------------- infra
async function api(caminho, opcoes = {}) {
  const r = await fetch(API + caminho, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(opcoes.headers || {}) },
    ...opcoes,
  });
  if (r.status === 401) { estado.usuario = null; mostrarLogin(); throw new Error('Sessão expirada'); }
  const texto = await r.text();
  const corpo = texto ? JSON.parse(texto) : null;
  if (!r.ok) throw new Error(corpo?.detail || `Erro ${r.status}`);
  return corpo;
}

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const dataHora = (v) => v ? new Date(v).toLocaleString('pt-BR') : '—';
const el = (id) => document.getElementById(id);

// ------------------------------------------------------------------ acesso
function mostrarLogin() {
  el('tela-login').classList.remove('oculto');
  el('app').classList.add('oculto');
}

async function entrar(ev) {
  ev.preventDefault();
  const botao = el('botao-entrar');
  botao.disabled = true;
  el('erro-login').textContent = '';
  try {
    const r = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: el('login-email').value, senha: el('login-senha').value }),
    });
    // Guardado só como plano B: se o navegador bloquear o cookie de terceiro
    // (front em domínio diferente da API), o Bearer mantém a sessão.
    if (r.token) localStorage.setItem('token', r.token);
    await iniciar();
  } catch (e) {
    el('erro-login').textContent = e.message;
  } finally {
    botao.disabled = false;
  }
}

async function sair() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
  localStorage.removeItem('token');
  estado.usuario = null;
  mostrarLogin();
}

// -------------------------------------------------------------------- shell
function montarNavegacao() {
  const paineis = estado.usuario.paineis;
  document.querySelectorAll('.nav-item').forEach((b) => {
    const p = b.dataset.painel;
    b.classList.toggle('oculto', !!p && !paineis.includes(p));
    b.classList.toggle('ativo', b.dataset.rota === estado.rota);
    b.onclick = () => ir(b.dataset.rota);
  });
  el('rodape-nome').textContent = estado.usuario.nome;
  el('rodape-perfil').textContent = estado.usuario.perfil_nome || estado.usuario.perfil;
}

function ir(rota) {
  estado.rota = rota;
  montarNavegacao();
  const telas = {
    modulos: telaModulos, pessoa: telaBusca, empresa: telaBusca,
    digital: telaBusca, casos: telaCasos, admin: telaAdmin,
  };
  (telas[rota] || telaModulos)(rota);
}

function cabecalho(titulo, subtitulo, acoes = '') {
  return `<div class="cabecalho-pagina">
    <div><h2>${esc(titulo)}</h2><p>${esc(subtitulo)}</p></div>
    <div class="acoes">${acoes}</div>
  </div>`;
}

// ------------------------------------------------------------------ módulos
async function telaModulos() {
  const c = el('conteudo');
  c.innerHTML = cabecalho('Módulos', 'Escolha por onde começar a apuração.') +
    '<div class="grade-numeros" id="numeros"></div><div class="grade" id="grade-modulos"></div>';

  el('grade-modulos').innerHTML = MODULOS
    .filter((m) => estado.usuario.paineis.includes(m.painel))
    .map((m) => `<div class="cartao modulo" data-rota="${m.rota}">
        <div class="icone">${m.icone}</div>
        <h3>${esc(m.titulo)}</h3>
        <p>${esc(m.texto)}</p>
      </div>`).join('');

  document.querySelectorAll('.modulo').forEach((d) => { d.onclick = () => ir(d.dataset.rota); });

  try {
    const n = await api('/api/numeros');
    el('numeros').innerHTML = [
      ['Casos abertos', n.casos_abertos], ['Alvos monitorados', n.alvos],
      ['Consultas em 30 dias', n.consultas_30d], ['Fontes ativas', n.fontes_ativas],
    ].map(([r, v]) => `<div class="cartao"><div class="numero">${v ?? 0}</div>
        <div class="numero-rotulo">${r}</div></div>`).join('');
  } catch (_) { el('numeros').innerHTML = ''; }
}

// ------------------------------------------------------------------ buscas
async function telaBusca(painel) {
  if (!estado.fontes.length) estado.fontes = await api('/api/fontes');
  const fontes = estado.fontes.filter((f) => f.painel === painel);

  const titulos = { pessoa: 'Pessoa Física', empresa: 'Empresa / CNPJ', digital: 'Rastro Digital' };
  const entradas = [...new Set(fontes.map((f) => f.entrada))];

  if (!estado.casos.length) { try { estado.casos = await api('/api/casos?status=aberto'); } catch (_) {} }

  el('conteudo').innerHTML =
    cabecalho(titulos[painel] || painel,
      'Cada fonte responde no seu tempo — os cards preenchem conforme chegam.') +
    `<div class="cartao" style="margin-bottom:20px">
      <div class="linha">
        <div class="campo">
          <label for="busca-tipo">Tipo de dado</label>
          <select id="busca-tipo">
            ${entradas.map((e) => `<option value="${e}">${esc(ROTULO_ENTRADA[e] || e)}</option>`).join('')}
          </select>
        </div>
        <div class="campo">
          <label for="busca-valor">Valor</label>
          <input type="text" id="busca-valor" placeholder="Digite e pressione Enter">
        </div>
        <div class="campo" style="max-width:260px">
          <label for="busca-caso">Vincular ao caso (recomendado)</label>
          <select id="busca-caso">
            <option value="">— sem caso —</option>
            ${estado.casos.map((c) => `<option value="${c.id}">${esc(c.codigo)} · ${esc(c.titulo)}</option>`).join('')}
          </select>
        </div>
        <button class="botao" id="botao-buscar">Buscar</button>
      </div>
      <div class="erro-texto" id="erro-busca"></div>
    </div>
    <div class="aviso-caixa">
      Consulta sem caso vinculado não entra em nenhum dossiê e fica registrada
      na auditoria sem finalidade declarada. Vincule sempre que possível.
    </div>
    <div class="grade" id="resultados"></div>`;

  const disparar = () => executarBusca(painel);
  el('botao-buscar').onclick = disparar;
  el('busca-valor').onkeydown = (e) => { if (e.key === 'Enter') disparar(); };
  el('busca-tipo').onchange = () => { el('resultados').innerHTML = ''; };
  el('busca-valor').focus();
}

async function executarBusca(painel) {
  const tipo = el('busca-tipo').value;
  const valor = el('busca-valor').value.trim();
  const casoId = el('busca-caso').value ? Number(el('busca-caso').value) : null;
  el('erro-busca').textContent = '';

  if (!valor) { el('erro-busca').textContent = 'Informe um valor para buscar.'; return; }

  const alvo = estado.fontes.filter((f) => f.painel === painel && f.entrada === tipo);
  if (!alvo.length) { el('erro-busca').textContent = 'Nenhuma fonte para esse tipo de dado.'; return; }

  const caixa = el('resultados');
  caixa.innerHTML = alvo.map((f) => cartaoFonte(f)).join('');

  // Dispara todas em paralelo; cada card se atualiza sozinho ao responder.
  alvo.forEach(async (f) => {
    const div = document.querySelector(`[data-fonte="${f.chave}"]`);
    if (!f.disponivel || !f.ativa) {
      pintarFonte(div, 'erro', `<div class="achado">${esc(f.motivo_indisponivel || 'Fonte desligada')}</div>`);
      return;
    }
    try {
      const r = await api('/api/buscar', {
        method: 'POST',
        body: JSON.stringify({ fonte: f.chave, valor, caso_id: casoId }),
      });
      if (!r.resultados.length) {
        pintarFonte(div, 'vazio', '<div class="achado">Nada encontrado.</div>', `${r.duracao_ms} ms`);
        return;
      }
      pintarFonte(div, 'ok', r.resultados.map(achadoHtml).join(''),
        `${r.resultados.length} achado(s) · ${r.duracao_ms} ms`);
    } catch (e) {
      pintarFonte(div, 'erro', `<div class="achado">${esc(e.message)}</div>`);
    }
  });
}

function cartaoFonte(f) {
  return `<div class="cartao cartao-fonte rodando" data-fonte="${f.chave}">
    <div class="cabecalho-fonte">
      <strong>${esc(f.nome)}</strong>
      <span class="etiqueta" data-estado><span class="girando"></span></span>
    </div>
    <p style="color:var(--texto-fraco);font-size:12px;margin:0 0 10px">${esc(f.descricao)}</p>
    <div data-corpo></div>
  </div>`;
}

function pintarFonte(div, estadoNovo, html, rotulo) {
  if (!div) return;
  div.className = `cartao cartao-fonte ${estadoNovo}`;
  const classe = { ok: 'ok', vazio: '', erro: 'erro' }[estadoNovo] || '';
  const texto = rotulo || { ok: 'ok', vazio: 'vazio', erro: 'erro' }[estadoNovo];
  div.querySelector('[data-estado]').outerHTML = `<span class="etiqueta ${classe}">${esc(texto)}</span>`;
  div.querySelector('[data-corpo]').innerHTML = html;
}

function achadoHtml(a) {
  const link = a.fonte_url
    ? ` <a href="${esc(a.fonte_url)}" target="_blank" rel="noopener">abrir fonte ↗</a>` : '';
  return `<div class="achado">
    <div>${esc(a.resumo)}${link}</div>
    <details><summary>dados brutos</summary>
      <div class="bruto">${esc(JSON.stringify(a.dados, null, 2))}</div>
    </details>
  </div>`;
}

// ------------------------------------------------------------------- casos
async function telaCasos() {
  if (estado.caso) return telaCasoDetalhe(estado.caso);

  estado.casos = await api('/api/casos');
  const clientes = await api('/api/clientes').catch(() => []);

  el('conteudo').innerHTML =
    cabecalho('Casos', 'Todo achado precisa estar amarrado a um caso com finalidade declarada.',
      '<button class="botao" id="botao-novo-caso">Novo caso</button>') +
    `<div class="cartao oculto" id="form-caso" style="margin-bottom:20px">
      <div class="linha">
        <div class="campo"><label>Código</label><input type="text" id="caso-codigo" placeholder="2026-001"></div>
        <div class="campo"><label>Título</label><input type="text" id="caso-titulo" placeholder="Localização de devedor"></div>
        <div class="campo"><label>Cliente</label>
          <select id="caso-cliente"><option value="">—</option>
            ${clientes.map((c) => `<option value="${c.id}">${esc(c.nome)}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="linha" style="margin-top:14px">
        <div class="campo"><label>Base legal (LGPD)</label>
          <select id="caso-base">
            <option value="execucao_contrato">Execução de contrato</option>
            <option value="legitimo_interesse">Legítimo interesse</option>
            <option value="exercicio_direitos">Exercício regular de direitos em processo</option>
            <option value="consentimento">Consentimento do titular</option>
          </select>
        </div>
        <div class="campo"><label>Finalidade</label>
          <input type="text" id="caso-finalidade" placeholder="Para que essa apuração existe">
        </div>
        <button class="botao" id="botao-salvar-caso">Salvar</button>
      </div>
      <div class="erro-texto" id="erro-caso"></div>
    </div>
    <div class="cartao"><table>
      <thead><tr><th>Código</th><th>Título</th><th>Cliente</th><th>Status</th>
        <th>Alvos</th><th>Consultas</th><th>Aberto em</th></tr></thead>
      <tbody id="lista-casos"></tbody>
    </table></div>`;

  el('lista-casos').innerHTML = estado.casos.length ? estado.casos.map((c) => `
    <tr style="cursor:pointer" data-caso="${c.id}">
      <td><strong>${esc(c.codigo)}</strong></td><td>${esc(c.titulo)}</td>
      <td>${esc(c.cliente_nome || '—')}</td>
      <td><span class="etiqueta ${c.status === 'aberto' ? 'ok' : ''}">${esc(c.status)}</span></td>
      <td>${c.qtd_alvos}</td><td>${c.qtd_consultas}</td><td>${dataHora(c.criado_em)}</td>
    </tr>`).join('')
    : '<tr><td colspan="7" class="vazio-texto">Nenhum caso ainda.</td></tr>';

  document.querySelectorAll('[data-caso]').forEach((tr) => {
    tr.onclick = () => { estado.caso = Number(tr.dataset.caso); telaCasoDetalhe(estado.caso); };
  });

  el('botao-novo-caso').onclick = () => el('form-caso').classList.toggle('oculto');
  el('botao-salvar-caso').onclick = async () => {
    el('erro-caso').textContent = '';
    try {
      await api('/api/casos', { method: 'POST', body: JSON.stringify({
        codigo: el('caso-codigo').value.trim(),
        titulo: el('caso-titulo').value.trim(),
        cliente_id: el('caso-cliente').value ? Number(el('caso-cliente').value) : null,
        base_legal: el('caso-base').value,
        finalidade: el('caso-finalidade').value.trim(),
      })});
      telaCasos();
    } catch (e) { el('erro-caso').textContent = e.message; }
  };
}

async function telaCasoDetalhe(casoId) {
  const caso = await api(`/api/casos/${casoId}`);
  const consultas = await api(`/api/consultas?caso_id=${casoId}`);

  el('conteudo').innerHTML =
    cabecalho(`${caso.codigo} — ${caso.titulo}`,
      `Cliente: ${caso.cliente_nome || '—'} · Base legal: ${caso.base_legal} · ${caso.finalidade || 'sem finalidade declarada'}`,
      `<button class="botao secundario" id="botao-voltar">Voltar</button>
       <button class="botao" id="botao-dossie">Gerar dossiê</button>`) +
    `<div class="grade" style="grid-template-columns:1fr 1fr">
      <div class="cartao">
        <h3 style="margin-top:0">Alvos</h3>
        <div class="linha" style="margin-bottom:12px">
          <div class="campo" style="max-width:150px"><select id="alvo-tipo">
            ${['cpf','cnpj','nome','email','telefone','username','url','placa']
              .map((t) => `<option value="${t}">${esc(ROTULO_ENTRADA[t] || t)}</option>`).join('')}
          </select></div>
          <div class="campo"><input type="text" id="alvo-valor" placeholder="Valor do alvo"></div>
          <button class="botao pequeno" id="botao-alvo">Incluir</button>
        </div>
        <table><tbody id="lista-alvos"></tbody></table>
      </div>

      <div class="cartao">
        <h3 style="margin-top:0">Linha do tempo</h3>
        <div class="linha" style="margin-bottom:12px">
          <div class="campo"><input type="text" id="nota-texto" placeholder="Registrar diligência ou observação"></div>
          <button class="botao pequeno" id="botao-nota">Anotar</button>
        </div>
        <div id="lista-eventos"></div>
      </div>

      <div class="cartao">
        <h3 style="margin-top:0">Anexos</h3>
        <p style="color:var(--texto-fraco);font-size:12px">
          Foto enviada tem o EXIF lido na hora — GPS, data original e aparelho.
        </p>
        <div class="linha">
          <div class="campo"><input type="file" id="anexo-arquivo"></div>
          <button class="botao pequeno" id="botao-anexo">Enviar</button>
        </div>
        <table><tbody id="lista-anexos"></tbody></table>
      </div>

      <div class="cartao">
        <h3 style="margin-top:0">Extrair documentos de um texto</h3>
        <p style="color:var(--texto-fraco);font-size:12px">
          Cole o retorno de um bureau, o texto de um PDF ou uma transcrição.
          CPF e CNPJ são conferidos pelo dígito verificador antes de entrar.
        </p>
        <div class="campo"><textarea id="ext-texto" rows="5"
          placeholder="Cole o texto aqui"></textarea></div>
        <label style="display:flex;gap:8px;align-items:center;margin-bottom:12px">
          <input type="checkbox" id="ext-criar" style="width:auto"> incluir os achados como alvos do caso
        </label>
        <button class="botao pequeno" id="botao-extrair">Extrair</button>
        <div id="ext-saida"></div>
        <div class="erro-texto" id="erro-extrair"></div>
      </div>

      <div class="cartao">
        <h3 style="margin-top:0">Importar consulta contratada</h3>
        <p style="color:var(--texto-fraco);font-size:12px">
          Para fornecedor que só tem painel web (Informbank, agência de campo,
          ofício respondido). Entra no dossiê marcado como origem manual.
        </p>
        <div class="campo"><input type="text" id="imp-origem"
          placeholder="Origem — ex.: Informbank (consulta contratada)"></div>
        <div class="campo"><input type="text" id="imp-entrada"
          placeholder="O que foi consultado — ex.: CPF 000.000.000-00"></div>
        <div class="campo"><input type="text" id="imp-resumo"
          placeholder="Resumo do achado em uma linha"></div>
        <div class="campo"><textarea id="imp-conteudo" rows="4"
          placeholder="Cole aqui o retorno completo (opcional)"></textarea></div>
        <button class="botao pequeno" id="botao-importar">Registrar no caso</button>
        <div class="erro-texto" id="erro-importar"></div>
      </div>

      <div class="cartao">
        <h3 style="margin-top:0">Consultas do caso</h3>
        <table><tbody id="lista-consultas"></tbody></table>
      </div>
    </div>`;

  el('lista-alvos').innerHTML = caso.alvos.length ? caso.alvos.map((a) => `
    <tr><td><span class="etiqueta">${esc(a.tipo)}</span></td>
      <td><strong>${esc(a.valor)}</strong></td>
      <td style="text-align:right"><button class="botao secundario pequeno" data-apagar="${a.id}">×</button></td>
    </tr>`).join('') : '<tr><td class="vazio-texto">Nenhum alvo.</td></tr>';

  el('lista-eventos').innerHTML = caso.eventos.length ? caso.eventos.map((e) => `
    <div class="achado"><div>${esc(e.texto)}</div>
      <div style="color:var(--texto-fraco);font-size:11px">
        ${esc(e.usuario_nome || '—')} · ${dataHora(e.criado_em)}</div>
    </div>`).join('') : '<div class="vazio-texto">Sem registros.</div>';

  el('lista-anexos').innerHTML = caso.anexos.length ? caso.anexos.map((a) => {
    const gps = a.exif?.GPSLatitude
      ? `<a href="https://www.google.com/maps?q=${a.exif.GPSLatitude},${a.exif.GPSLongitude}" target="_blank" rel="noopener">GPS ↗</a>`
      : '';
    const data = a.exif?.DateTimeOriginal ? `· foto de ${esc(a.exif.DateTimeOriginal)}` : '';
    return `<tr><td><a href="${API}/api/anexos/${a.id}" target="_blank" rel="noopener">${esc(a.nome)}</a>
        <div style="color:var(--texto-fraco);font-size:11px">
          ${(a.tamanho / 1024).toFixed(0)} KB ${data} ${gps}<br>sha256 ${esc((a.sha256 || '').slice(0, 16))}…
        </div></td></tr>`;
  }).join('') : '<tr><td class="vazio-texto">Sem anexos.</td></tr>';

  el('lista-consultas').innerHTML = consultas.length ? consultas.map((q) => `
    <tr><td><strong>${esc(q.fonte_nome || q.fonte_chave)}</strong>
        <div style="color:var(--texto-fraco);font-size:11px">
          ${esc(q.entrada)} · ${esc(q.usuario_nome || '—')} · ${dataHora(q.iniciada_em)}</div></td>
      <td style="text-align:right"><span class="etiqueta ${q.status === 'ok' ? 'ok' : q.status === 'erro' ? 'erro' : ''}">
        ${q.qtd_resultados} achado(s)</span></td>
    </tr>`).join('') : '<tr><td class="vazio-texto">Nenhuma consulta.</td></tr>';

  el('botao-voltar').onclick = () => { estado.caso = null; telaCasos(); };
  el('botao-dossie').onclick = () => gerarDossie(casoId);

  el('botao-alvo').onclick = async () => {
    const valor = el('alvo-valor').value.trim();
    if (!valor) return;
    await api(`/api/casos/${casoId}/alvos`, { method: 'POST',
      body: JSON.stringify({ tipo: el('alvo-tipo').value, valor }) });
    telaCasoDetalhe(casoId);
  };

  document.querySelectorAll('[data-apagar]').forEach((b) => {
    b.onclick = async () => {
      await api(`/api/casos/${casoId}/alvos/${b.dataset.apagar}`, { method: 'DELETE' });
      telaCasoDetalhe(casoId);
    };
  });

  el('botao-nota').onclick = async () => {
    const texto = el('nota-texto').value.trim();
    if (!texto) return;
    await api(`/api/casos/${casoId}/eventos`, { method: 'POST', body: JSON.stringify({ texto }) });
    telaCasoDetalhe(casoId);
  };

  el('botao-extrair').onclick = async () => {
    el('erro-extrair').textContent = '';
    el('ext-saida').innerHTML = '';
    const criar = el('ext-criar').checked;
    try {
      const r = await api(`/api/casos/${casoId}/extrair`, { method: 'POST', body: JSON.stringify({
        texto: el('ext-texto').value, criar_alvos: criar,
      })});

      const bloco = (titulo, itens, classe) => itens.length
        ? `<div class="achado"><strong>${titulo}</strong>${itens.map((a) =>
            `<div><span class="etiqueta ${classe}">${esc(a.tipo)}</span>
             ${esc(a.original)}${a.nota ? ` <small style="color:var(--texto-fraco)">— ${esc(a.nota)}</small>` : ''}</div>`
          ).join('')}</div>` : '';

      el('ext-saida').innerHTML =
        bloco(`${r.total} documento(s) encontrado(s)`, r.achados, 'ok') +
        bloco(`${r.suspeitos.length} descartado(s) por dígito inválido`, r.suspeitos, 'erro') +
        (r.alvos_criados ? `<div class="achado">${r.alvos_criados} alvo(s) incluído(s) no caso.</div>` : '');

      if (criar && r.alvos_criados) setTimeout(() => telaCasoDetalhe(casoId), 1200);
    } catch (e) { el('erro-extrair').textContent = e.message; }
  };

  el('botao-importar').onclick = async () => {
    el('erro-importar').textContent = '';
    try {
      await api(`/api/casos/${casoId}/importar`, { method: 'POST', body: JSON.stringify({
        origem: el('imp-origem').value.trim(),
        entrada: el('imp-entrada').value.trim(),
        resumo: el('imp-resumo').value.trim(),
        conteudo: el('imp-conteudo').value,
      })});
      telaCasoDetalhe(casoId);
    } catch (e) { el('erro-importar').textContent = e.message; }
  };

  el('botao-anexo').onclick = async () => {
    const arquivo = el('anexo-arquivo').files[0];
    if (!arquivo) return;
    const fd = new FormData();
    fd.append('arquivo', arquivo);
    const r = await fetch(`${API}/api/casos/${casoId}/anexos`, {
      method: 'POST', body: fd, credentials: 'include',
    });
    if (!r.ok) { alert('Falha ao enviar o anexo'); return; }
    telaCasoDetalhe(casoId);
  };
}

async function gerarDossie(casoId) {
  const d = await api(`/api/casos/${casoId}/dossie`);
  const janela = window.open('', '_blank');
  const linhas = d.consultas.map((q) => `
    <h3>${esc(q.fonte_nome || q.fonte_chave)} — entrada: ${esc(q.entrada)}</h3>
    <p><small>Coletado por ${esc(q.usuario_nome || '—')} em ${dataHora(q.iniciada_em)} ·
      status ${esc(q.status)}</small></p>
    <ul>${(q.resultados || []).map((r) => `<li>${esc(r.resumo)}
      ${r.fonte_url ? `<br><small>${esc(r.fonte_url)}</small>` : ''}</li>`).join('')}</ul>`).join('');

  janela.document.write(`<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
    <title>Dossiê ${esc(d.codigo)}</title>
    <style>body{font-family:Georgia,serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6}
      h1{border-bottom:2px solid #333;padding-bottom:8px}
      h3{margin-top:26px;background:#f4f4f4;padding:6px 10px}
      small{color:#666} li{margin-bottom:6px} .rodape{margin-top:40px;border-top:1px solid #ccc;
      padding-top:12px;font-size:12px;color:#666}</style></head><body>
    <h1>Dossiê — ${esc(d.codigo)}</h1>
    <p><strong>${esc(d.titulo)}</strong></p>
    <p>Cliente: ${esc(d.cliente_nome || '—')}<br>
       Responsável: ${esc(d.responsavel_nome || '—')}<br>
       Base legal (LGPD): ${esc(d.base_legal)}<br>
       Finalidade: ${esc(d.finalidade || '—')}<br>
       Aberto em: ${dataHora(d.criado_em)}</p>
    <h2>Alvos</h2>
    <ul>${d.alvos.map((a) => `<li>${esc(a.tipo)}: <strong>${esc(a.valor)}</strong></li>`).join('') || '<li>—</li>'}</ul>
    <h2>Apurações</h2>
    ${linhas || '<p>Nenhuma consulta registrada.</p>'}
    <h2>Diligências</h2>
    <ul>${d.eventos.map((e) => `<li>${dataHora(e.criado_em)} — ${esc(e.texto)}
      <small>(${esc(e.usuario_nome || '—')})</small></li>`).join('') || '<li>—</li>'}</ul>
    <div class="rodape">
      Documento gerado em ${new Date().toLocaleString('pt-BR')} pelo sistema Investiga.
      Todo dado aqui foi coletado de fonte pública indicada em cada item, com registro
      de autor, data e hora na trilha de auditoria.
    </div>
    <script>window.print()<\/script></body></html>`);
  janela.document.close();
}

// -------------------------------------------------------------------- admin
async function telaAdmin() {
  const [usuarios, fontes, perfis, auditoria] = await Promise.all([
    api('/api/admin/usuarios'), api('/api/admin/fontes'),
    api('/api/admin/perfis'), api('/api/admin/auditoria?limite=60'),
  ]);

  el('conteudo').innerHTML =
    cabecalho('Administração', 'Equipe, fontes e trilha de auditoria.') +
    `<div class="cartao" style="margin-bottom:20px">
      <h3 style="margin-top:0">Equipe</h3>
      <div class="linha" style="margin-bottom:14px">
        <div class="campo"><input type="text" id="novo-nome" placeholder="Nome"></div>
        <div class="campo"><input type="email" id="novo-email" placeholder="E-mail"></div>
        <div class="campo"><input type="password" id="nova-senha" placeholder="Senha (mín. 8)"></div>
        <div class="campo" style="max-width:180px"><select id="novo-perfil">
          ${perfis.map((p) => `<option value="${p.chave}">${esc(p.nome)}</option>`).join('')}
        </select></div>
        <button class="botao" id="botao-novo-usuario">Incluir</button>
      </div>
      <div class="erro-texto" id="erro-usuario"></div>
      <table><thead><tr><th>Nome</th><th>E-mail</th><th>Perfil</th>
        <th>Último acesso</th><th></th></tr></thead>
        <tbody>${usuarios.map((u) => `<tr>
          <td>${esc(u.nome)}</td><td>${esc(u.email)}</td><td>${esc(u.perfil_nome)}</td>
          <td>${dataHora(u.ultimo_login)}</td>
          <td style="text-align:right"><button class="botao secundario pequeno" data-usuario="${u.id}">
            ${u.ativo ? 'Desativar' : 'Ativar'}</button></td></tr>`).join('')}
        </tbody></table>
    </div>

    <div class="cartao" style="margin-bottom:20px">
      <h3 style="margin-top:0">Fontes</h3>
      <table><thead><tr><th>Fonte</th><th>Painel</th><th>Entrada</th>
        <th>Estado</th><th></th></tr></thead>
        <tbody>${fontes.map((f) => `<tr>
          <td><strong>${esc(f.nome)}</strong>
            <div style="color:var(--texto-fraco);font-size:11px">${esc(f.descricao || '')}</div></td>
          <td>${esc(f.painel)}</td><td>${esc(f.entrada)}</td>
          <td>${f.disponivel
            ? '<span class="etiqueta ok">disponível</span>'
            : `<span class="etiqueta aviso">falta credencial</span>`}</td>
          <td style="text-align:right"><button class="botao secundario pequeno"
            data-fonte-chave="${esc(f.chave)}" data-ativa="${f.ativa}">
            ${f.ativa ? 'Desligar' : 'Ligar'}</button></td></tr>`).join('')}
        </tbody></table>
    </div>

    <div class="cartao">
      <h3 style="margin-top:0">Auditoria — últimos 60 registros</h3>
      <table><thead><tr><th>Quando</th><th>Quem</th><th>Ação</th><th>Alvo</th><th>IP</th></tr></thead>
        <tbody>${auditoria.map((a) => `<tr>
          <td>${dataHora(a.criado_em)}</td><td>${esc(a.usuario_nome || '—')}</td>
          <td><span class="etiqueta">${esc(a.acao)}</span></td>
          <td>${esc(a.alvo_valor || '—')}</td><td>${esc(a.ip || '—')}</td></tr>`).join('')}
        </tbody></table>
    </div>`;

  el('botao-novo-usuario').onclick = async () => {
    el('erro-usuario').textContent = '';
    try {
      await api('/api/admin/usuarios', { method: 'POST', body: JSON.stringify({
        nome: el('novo-nome').value.trim(), email: el('novo-email').value.trim(),
        senha: el('nova-senha').value, perfil: el('novo-perfil').value,
      })});
      telaAdmin();
    } catch (e) { el('erro-usuario').textContent = e.message; }
  };

  document.querySelectorAll('[data-usuario]').forEach((b) => {
    b.onclick = async () => {
      await api(`/api/admin/usuarios/${b.dataset.usuario}/ativo`, { method: 'PATCH' });
      telaAdmin();
    };
  });

  document.querySelectorAll('[data-fonte-chave]').forEach((b) => {
    b.onclick = async () => {
      await api(`/api/admin/fontes/${b.dataset.fonteChave}`, {
        method: 'PATCH', body: JSON.stringify({ ativa: b.dataset.ativa !== 'true' }),
      });
      estado.fontes = [];
      telaAdmin();
    };
  });
}

// ------------------------------------------------------------------- início
async function iniciar() {
  try {
    estado.usuario = await api('/api/auth/eu');
  } catch (_) {
    mostrarLogin();
    return;
  }
  el('tela-login').classList.add('oculto');
  el('app').classList.remove('oculto');
  estado.fontes = [];
  ir('modulos');
}

el('form-login').onsubmit = entrar;
el('botao-sair').onclick = sair;
el('botao-tema').onclick = () => {
  const atual = document.documentElement.dataset.tema === 'claro' ? 'escuro' : 'claro';
  document.documentElement.dataset.tema = atual;
  localStorage.setItem('tema', atual);
};

document.documentElement.dataset.tema = localStorage.getItem('tema') || 'escuro';

// Se o cookie não sobreviver (front em outro domínio), reusa o Bearer salvo.
const salvo = localStorage.getItem('token');
if (salvo) {
  const originalFetch = window.fetch;
  window.fetch = (url, opcoes = {}) => originalFetch(url, {
    ...opcoes,
    headers: { ...(opcoes.headers || {}), Authorization: `Bearer ${salvo}` },
  });
}

iniciar();
