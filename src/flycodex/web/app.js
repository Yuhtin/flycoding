'use strict';
const byId = id => document.getElementById(id);
const labels = {running:'Em execução',completed:'Concluído',paused:'Pausado',interrupted:'Interrompido',success:'Sucesso',budget_exhausted:'Limite atingido',execution_failure:'Falha de execução',infrastructure_failure:'Falha de infraestrutura',violation:'Violação da tarefa',aborted_interrupted:'Tentativa interrompida',recovery_error:'Reconciliação necessária',adaptive:'Adaptável',frozen:'Pesos congelados',random:'Aleatória uniforme'};
const reasons = {gate_inactive:'Sem disparos de habilitação.',right_threshold:'Diferença ≥ +2 Hz com habilitação.',left_threshold:'Diferença ≤ −2 Hz com habilitação.',difference_below_threshold:'Diferença abaixo do limiar de 2 Hz.',seeded_uniform_random:'Escolha aleatória uniforme com semente registrada. Sem atividade neural.',synthetic_policy:'Política sintética de teste.'};
const order = ['adaptive-1','frozen-1','random-1','adaptive-2','frozen-2','random-2'];
let current = null;
function text(id, value) { byId(id).textContent = value; }
function turns(state) { return order.flatMap(name => (state.attempts[name]?.turns || []).map(turn => ({name,turn,key:`${name}:${turn.step}`}))); }
function renderSelection() {
  if (!current) return;
  const all = turns(current);
  const selected = byId('history').value;
  const entry = selected === 'live' ? all.at(-1) : all.find(item => item.key === selected);
  if (!entry) return;
  const {name,turn} = entry;
  const choice = turn.choice || {};
  const image = byId('sensory');
  if (turn.input) {
    image.src = '/images/' + encodeURIComponent(turn.input.file);
    image.hidden = false; byId('image-empty').hidden = true;
    text('input-hash',turn.input.rgb_sha256); text('png-hash',turn.input.png_sha256);
  } else { image.hidden = true; byId('image-empty').hidden = false; text('input-hash','—'); text('png-hash','—'); }
  text('input-kind',name.startsWith('random') ? 'Painel de estado registrado. A condição aleatória não usa a rede neural.' : 'Este PNG contém exatamente os pixels recebidos pela rede nesta escolha.');
  document.querySelectorAll('[data-action]').forEach(node => node.classList.toggle('selected',node.dataset.action === choice.action));
  text('prompt',turn.prompt || 'Calculando escolha…');
  text('reason',reasons[choice.reason] || choice.reason || 'Aguardando trace.');
  text('left',choice.left_hz === undefined ? '—' : `${choice.left_hz.toFixed(2)} Hz`);
  text('right',choice.right_hz === undefined ? '—' : `${choice.right_hz.toFixed(2)} Hz`);
  text('gate',choice.gate_spikes ?? '—');
  const feedback = turn.feedback;
  text('feedback',feedback ? ({'-1':'Negativo','0':'Neutro','1':'Positivo'}[feedback.signal] + (feedback.delivered_to_neural ? '' : ' · registrado')) : 'Não entregue');
  const evaluation = turn.evaluation || current.attempts[name].baseline;
  text('score',evaluation ? `${evaluation.passed} / ${evaluation.total}` : '—');
  const tests = byId('tests'); tests.replaceChildren();
  for (const item of evaluation?.tests || []) {
    const li = document.createElement('li'); const label = document.createElement('span'); const result = document.createElement('span');
    label.textContent = item.id; result.textContent = item.passed ? 'passou' : 'falhou'; result.className = item.passed ? 'pass' : 'fail'; li.append(label,result); tests.append(li);
  }
  text('violation',evaluation?.violation || turn.infrastructure_error || turn.codex?.error || '');
  text('trace',JSON.stringify({attempt:name,step:turn.step,choice,feedback,weights_before:turn.weights_before,weights_after_choice:turn.weights_after_choice,weights_after_feedback:turn.weights_after_feedback},null,2));
}
function render(state) {
  current = state;
  text('run-status',labels[state.status] || state.status);
  text('evidence',state.evidence === 'genuine' ? 'Execução real · piloto experimental' : 'SINTÉTICO · fixture de teste');
  text('model',`Modelo ${state.settings?.model || '—'}`);
  text('budget',`Envios reservados ${state.budget?.used ?? 0} / 30`);
  text('active',`Tentativa ${state.active_attempt || '—'}`);
  text('terminal-state',state.busy ? 'Codex em execução' : 'Codex pausado');
  const select = byId('history'); const old = select.value;
  const options = [new Option('Última escolha · acompanhar','live'),...turns(state).map(item => new Option(`${item.name} · instrução ${item.turn.step}`,item.key))];
  select.replaceChildren(...options); select.value = options.some(o => o.value === old) ? old : 'live';
  const tbody = byId('attempts'); tbody.replaceChildren();
  for (const name of order) {
    const attempt = state.attempts[name]; const row = document.createElement('tr');
    const latest = attempt?.turns.filter(t => t.evaluation).at(-1)?.evaluation || attempt?.baseline;
    const values = [name,labels[name.split('-')[0]],labels[attempt?.status] || 'Aguardando',`${attempt?.turns.filter(t => t.send_id).length || 0} / 5`,latest ? `${latest.passed} / ${latest.total}` : '—'];
    for (const value of values) { const cell = document.createElement('td'); cell.textContent = value; row.append(cell); }
    tbody.append(row);
  }
  const terminal = byId('events'); const atEnd = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 40;
  terminal.textContent = state.events?.length ? state.events.map(event => JSON.stringify(event,null,2)).join('\n\n') : 'Aguardando eventos…';
  if (atEnd) terminal.scrollTop = terminal.scrollHeight;
  renderSelection();
}
byId('history').addEventListener('change',renderSelection);
async function refresh() {
  try {
    const response = await fetch('/snapshot.json',{cache:'no-store'});
    if (!response.ok) throw new Error('Aguardando artefatos do piloto');
    render(await response.json()); text('connection','Observando · atualização a cada 1 s');
  } catch (error) { text('connection',error.message || 'Conexão interrompida'); }
  setTimeout(refresh,1000);
}
refresh();
