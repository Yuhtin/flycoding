import {createBodyView} from '/body-view.js';
import {coalesceItemEvents, createReplay, evaluationForTurn, order, readableEvent, recordedWorkspace, translatePrompt, turns} from '/presentation.mjs';

const byId = id => document.getElementById(id);
const text = (id, value) => { const node = byId(id); if (node.textContent !== String(value)) node.textContent = value; };
const labels = {running:'Running',completed:'Completed',paused:'Paused',interrupted:'Interrupted',success:'Success',budget_exhausted:'Budget exhausted',execution_failure:'Execution failed',infrastructure_failure:'Infrastructure failure',violation:'Task violation',aborted_interrupted:'Attempt interrupted',recovery_error:'Recovery required',adaptive:'Adaptive',frozen:'Frozen weights',random:'Uniform random'};
const reasons = {gate_inactive:'No gating spikes: investigate.',right_threshold:'Right − left ≥ +2 Hz, with gating spikes.',left_threshold:'Right − left ≤ −2 Hz, with gating spikes.',difference_below_threshold:'The difference is below the 2 Hz threshold.',seeded_uniform_random:'Seeded uniform random choice. This condition does not use the neural circuit.',synthetic_policy:'Synthetic test policy.'};
let current = null, replay = createReplay([]), translations = [], connected = false, snapshotText = '';
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let motionPaused = motionPreference.matches, motionChosen = false;
let bodySignature = '', liveFeedback = 'idle', feedbackTimer;
const recordedFeedback = new Set();
function clearLiveFeedback() {
  clearTimeout(feedbackTimer);
  liveFeedback = 'idle';
}
const body = createBodyView(byId('body-stage'), {framingScale:1.15, onStatus(message) { text('body-status', message); }});
function updateMotion() {
  const frame = replay.frame();
  body.setPaused(motionPaused || (frame.active && !frame.playing));
  text('motion-toggle', motionPaused ? 'Animate fly' : 'Pause motion');
  byId('motion-toggle').setAttribute('aria-pressed', String(motionPaused));
}
updateMotion();
motionPreference.addEventListener('change', event => { if (!motionChosen) { motionPaused = event.matches; updateMotion(); } });
byId('motion-toggle').addEventListener('click', () => { motionChosen = true; motionPaused = !motionPaused; updateMotion(); });
byId('history').addEventListener('change', () => { replay.select(byId('history').value); clearLiveFeedback(); render(); });
byId('replay-play').addEventListener('click', () => { clearLiveFeedback(); replay.frame().playing ? replay.pause() : replay.play(); render(); });
byId('replay-reset').addEventListener('click', () => { clearLiveFeedback(); replay.reset(); render(); });
byId('original-language').addEventListener('change', render);
byId('image-kind').addEventListener('change', render);

function setBody(mode, entry) {
  const choice = entry?.turn.choice || {};
  const signature = `${mode}:${entry?.key}:${connected}`;
  if (signature !== bodySignature) {
    body.setState({mode, action:choice.action, leftHz:choice.left_hz, rightHz:choice.right_hz});
    bodySignature = signature;
  }
  text('body-mode', mode === 'working' ? (replay.frame().active ? 'Replaying work' : 'Working') : mode === 'success' ? 'Positive feedback' : mode === 'failure' ? 'Negative feedback' : 'Idle');
  updateMotion();
}
function renderTable(frame) {
  const entries = turns(current);
  const shown = new Set(entries.slice(0, frame.completed).map(entry => entry.key));
  const tbody = byId('attempts'); tbody.replaceChildren();
  for (const name of order) {
    const attempt = current.attempts?.[name];
    const completedTurns = frame.active ? (attempt?.turns || []).filter(t => shown.has(`${name}:${t.step}`)) : attempt?.turns || [];
    const latest = completedTurns.filter(t => t.evaluation).at(-1)?.evaluation || attempt?.baseline;
    const allShown = !frame.active || (attempt?.turns?.length > 0 && completedTurns.length === attempt.turns.length);
    const state = allShown ? labels[attempt?.status] || 'Waiting' : completedTurns.length ? 'Replay in progress' : 'Not replayed';
    const row = document.createElement('tr');
    for (const value of [name,labels[name.split('-')[0]],state,`${completedTurns.filter(t => t.send_id || t.reserved).length} / 5`,latest ? `${latest.passed} / ${latest.total}` : '—']) {
      const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
    }
    tbody.append(row);
  }
}
function render() {
  const frame = replay.frame();
  text('replay-play', frame.playing ? 'Pause replay' : frame.active && frame.phase !== 'complete' ? 'Resume replay' : 'Play replay');
  text('replay-label', frame.active ? `Condensed replay · ${Math.floor(frame.elapsed / 1000)} / ${Math.round(frame.duration / 1000)} s` : `Recorded session · ${Math.round(frame.duration / 1000)} s replay`);
  byId('replay-progress').value = frame.active ? frame.progress : 0;
  if (!current) { setBody('idle'); return; }
  const all = turns(current);
  const selection = byId('history').value;
  const entry = frame.active ? frame.entry : selection === 'live' ? all.at(-1) : all.find(item => item.key === selection);
  const demo = current.presentation?.mode === 'demo';
  const successCount = Object.values(current.attempts || {}).filter(a => a.status === 'success').length;
  text('run-status', frame.active ? (frame.phase === 'complete' ? 'Replay complete' : frame.playing ? 'Condensed replay' : 'Replay paused') : !connected ? 'Disconnected · saved record' : `${labels[current.status] || current.status}${current.status === 'completed' ? ` · ${successCount} / 6 successful` : ''}`);
  text('evidence',current.evidence === 'genuine' ? (demo ? 'Genuine pilot · bundled demo' : 'Genuine experimental pilot') : 'SYNTHETIC · test fixture');
  text('model',current.settings?.model || 'Model not recorded');
  text('budget',`Recorded reservations ${current.budget?.used ?? 0} / ${current.budget?.limit ?? 30}`);
  byId('demo-provenance').hidden = !demo;
  text('raw-summary', demo ? 'Original-language events · sanitized JSON' : 'Original-language events · raw JSON');
  text('raw-note', demo ? 'Curated genuine events. Workspace paths are relative; private metadata is omitted. English translations are presentation only.' : 'Original events from the selected run. English translations are presentation only.');
  text('comparison-note',frame.active ? 'Condensed replay progress · evaluations appear only after their recorded turn.' : 'Recorded outcomes · up to 5 instructions per attempt, 10 per condition.');
  renderTable(frame);
  if (!entry) { setBody('idle'); return; }
  const {name,turn} = entry;
  if (frame.active) byId('history').value = entry.key;
  const working = frame.active && frame.phase === 'working';
  const live = !frame.active && selection === 'live' && !demo;
  let mode = 'idle';
  if (frame.active) mode = frame.phase === 'working' ? 'working' : frame.phase === 'feedback' ? (turn.feedback?.signal < 0 ? 'failure' : turn.feedback?.signal > 0 ? 'success' : 'idle') : 'idle';
  else if (connected && live) mode = current.busy && current.status === 'running' ? 'working' : liveFeedback;
  setBody(mode, entry);
  text('active',`${name} · turn ${turn.step}`);
  const choice = turn.choice || {};
  const original = byId('original-language').checked;
  const prompt = translatePrompt(turn.prompt || 'Computing the next choice…');
  text('prompt',original ? turn.prompt || prompt.text : prompt.text);
  text('prompt-language',prompt.translated ? original ? 'Original recorded instruction · Portuguese' : 'English translation · original preserved' : 'Original recorded instruction');
  document.querySelectorAll('[data-action]').forEach(node => node.classList.toggle('selected',node.dataset.action === choice.action));
  text('reason',reasons[choice.reason] || choice.reason || 'Waiting for trace.');
  text('left',choice.left_hz === undefined ? '—' : `${choice.left_hz.toFixed(2)} Hz`);
  text('right',choice.right_hz === undefined ? '—' : `${choice.right_hz.toFixed(2)} Hz`);
  text('gate',choice.gate_spikes ?? '—');
  const feedback = working ? null : turn.feedback;
  text('feedback',feedback ? ({'-1':'Negative','0':'Neutral','1':'Positive'}[feedback.signal] + (feedback.delivered_to_neural ? '' : ' · recorded')) : working ? 'Pending replay' : 'Not delivered');
  const evaluation = evaluationForTurn(current.attempts[name], turn, !working);
  text('score',evaluation ? `${evaluation.passed} / ${evaluation.total}` : '—');
  text('evaluation-state', working ? 'Before this turn' : 'Recorded result');
  const tests = byId('tests'); tests.replaceChildren();
  for (const item of evaluation?.tests || []) {
    const li = document.createElement('li'), result = document.createElement('span'), label = document.createElement('span');
    result.textContent = item.passed ? '✓' : '×'; result.className = item.passed ? 'pass' : 'fail';
    label.textContent = item.id.replaceAll('_',' '); li.setAttribute('aria-label',`${item.id}: ${item.passed ? 'passed' : 'failed'}`); li.append(result,label); tests.append(li);
  }
  text('violation',working ? '' : evaluation?.violation || turn.infrastructure_error || turn.codex?.error || '');
  const imageKind = byId('image-kind').value;
  const input = imageKind === 'feedback_input' && working ? null : turn[imageKind];
  const image = byId('sensory');
  image.hidden = !input; byId('image-empty').hidden = Boolean(input);
  if (input) { const src = '/images/' + encodeURIComponent(input.file); if (image.getAttribute('src') !== src) image.src = src; }
  text('input-hash', input?.rgb_sha256 || '—'); text('png-hash', input?.png_sha256 || '—');
  text('image-empty',working && imageKind === 'feedback_input' ? 'Feedback appears after this replayed turn.' : 'No input image available.');
  text('input-kind',name.startsWith('random') ? 'Recorded state panel. The random condition does not use the neural circuit.' : 'The exact PNG pixels received by the circuit for this recorded input.');
  text('trace',JSON.stringify({attempt:name,step:turn.step,choice,feedback,weights_before:turn.weights_before,weights_after_choice:turn.weights_after_choice,...(!working && {weights_after_feedback:turn.weights_after_feedback})},null,2));
  const events = frame.active ? frame.events : coalesceItemEvents(turn.events || []);
  const workspace = recordedWorkspace(current.attempts[name], name);
  text('terminal-scope',`${name} · turn ${turn.step} · ${frame.active ? 'condensed replay' : live ? 'latest record' : 'recorded history'}`);
  text('terminal-state',!connected && live ? 'Disconnected' : frame.active ? frame.playing ? 'Replaying' : 'Paused' : live && current.busy && current.status === 'running' ? 'Codex working' : 'Recorded');
  text('translation-note',original ? 'Original-language events' : 'English translations labeled in transcript');
  const terminal = byId('events'), atEnd = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 40;
  const readable = events.map(event => readableEvent(event,workspace,original ? [] : translations)).filter(Boolean).join('\n\n') || 'No events recorded for this turn.';
  const changed = terminal.textContent !== readable;
  text('events',readable);
  text('raw-events',events.map(event => JSON.stringify(event,null,2)).join('\n\n') || 'No events.');
  if (changed && (atEnd || frame.active)) terminal.scrollTop = terminal.scrollHeight;
}

async function refresh() {
  try {
    const response = await fetch('/snapshot.json',{cache:'no-store',signal:AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error('No pilot snapshot available');
    const raw = await response.text(), state = JSON.parse(raw);
    if (!state.attempts || typeof state.attempts !== 'object') throw new Error('Invalid pilot snapshot');
    const followingLive = connected && !replay.frame().active && byId('history').value === 'live' && state.presentation?.mode !== 'demo';
    connected = true;
    // Observe availability independently of busy: evaluation is persisted after turn_settled.
    // Initial/reconnected snapshots and signals seen during history/replay are consumed silently.
    const entries = turns(state), latest = entries.at(-1);
    if (raw !== snapshotText && (state.busy || latest?.key !== turns(current || {}).at(-1)?.key)) clearLiveFeedback();
    for (const entry of entries) {
      if (entry.turn.feedback?.signal == null) continue;
      const key = `${entry.key}:${entry.turn.send_id || ''}`;
      const fresh = !recordedFeedback.has(key);
      recordedFeedback.add(key);
      if (fresh && followingLive && entry === latest) {
        clearLiveFeedback();
        const signal = entry.turn.feedback.signal;
        liveFeedback = signal < 0 ? 'failure' : signal > 0 ? 'success' : 'idle';
        feedbackTimer = setTimeout(() => { clearLiveFeedback(); render(); },2500);
      }
    }
    if (raw !== snapshotText) {
      current = state; snapshotText = raw;
      const oldSelection = byId('history').value;
      replay = createReplay(turns(state));
      const options = [new Option('Latest turn · follow','live'),...turns(state).map(entry => new Option(`${entry.name} · turn ${entry.turn.step}`,entry.key))];
      byId('history').replaceChildren(...options);
      byId('history').value = options.some(option => option.value === oldSelection) ? oldSelection : 'live';
      replay.select(byId('history').value);
      byId('replay-play').disabled = !turns(state).length;
      byId('replay-reset').disabled = !turns(state).length;
    }
    text('connection',state.presentation?.mode === 'demo' ? 'Read-only · bundled demo' : 'Connected · refreshes every 1 s');
    render();
  } catch (error) {
    connected = false; clearLiveFeedback();
    text('connection',current ? 'Disconnected · showing saved record' : error.message || 'Connection unavailable');
    render();
  }
  setTimeout(refresh,1000);
}
let last = performance.now();
setInterval(() => { const now = performance.now(), delta = now - last; last = now; if (replay.frame().playing) { replay.advance(delta); render(); } },100);
fetch('/translations.json').then(response => response.ok ? response.json() : []).then(data => { translations = data; render(); }).catch(() => {});
window.addEventListener('pagehide', () => body.dispose(), {once:true});
refresh();
