import {createBodyView} from '/body-view.js';
import {createBrainView} from '/brain-view.js';
import {applyActivityPage, codingActivityAllowed, createBrainState, emptyReadout, feedbackLabel, measurementAge} from '/brain-state.mjs';
import {coalesceItemEvents, createReplay, evaluationForTurn, order, readableEvent, recordedWorkspace, translatePrompt, turns} from '/presentation.mjs';

const byId = id => document.getElementById(id);
const setText = (id, value) => { const node = byId(id); if (node && node.textContent !== String(value)) node.textContent = String(value); };
const labels = {running:'Running',completed:'Completed',paused:'Paused',interrupted:'Interrupted',success:'Success',budget_exhausted:'Budget exhausted',execution_failure:'Execution failed',infrastructure_failure:'Infrastructure failure',violation:'Task violation',adaptive:'Adaptive',frozen:'Frozen weights',random:'Uniform random'};
const reasons = {gate_inactive:'No gating spikes: investigate.',right_threshold:'Right − left ≥ +2 Hz, with gating spikes.',left_threshold:'Right − left ≤ −2 Hz, with gating spikes.',difference_below_threshold:'The difference is below the 2 Hz threshold.',seeded_uniform_random:'Seeded uniform random choice. This condition does not use the neural circuit.'};
const prompts = {investigate:'Analyze the failure and explain the likely cause without editing.',fix:'Fix the discount function while preserving the tests.',test:'Run the tests and report the result.'};
let mode = 'lab';
let lab = {availability:false,status:'idle',job_id:null,choice:null,error:null,oldest_seq:0,latest_seq:0,neuron_order_sha256:null};
let labCursor = 0, labJobSeen = null, brainState = createBrainState(null), brainReady = false;
let current = null, replay = createReplay([]), archiveSnapshotText = '', translations = [];
let codingWindow = null, codingCursor = 0, codingActivity = null;
let connected = false, liveFeedback = 'idle', feedbackTimer, lastArchiveTurn = '';
const recordedFeedback = new Set();
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let motionPaused = motionPreference.matches, motionChosen = false;

function clearLiveFeedback() { clearTimeout(feedbackTimer); liveFeedback = 'idle'; }
function setBodyMode(value, entry = null) {
  const choice = entry?.turn?.choice || lab.choice || {};
  const modeValue = value === 'working' || value === 'replay' ? 'working' : value === 'success' ? 'success' : value === 'failure' ? 'failure' : 'idle';
  body.setState({mode:modeValue, action:choice.action, leftHz:choice.left_hz, rightHz:choice.right_hz});
  const text = value === 'replay' ? 'Replaying work' : value === 'working' ? 'Working' : value === 'success' ? 'Positive feedback' : value === 'failure' ? 'Negative feedback' : 'Idle';
  setText('body-mode', text);
  updateMotion();
}

const body = createBodyView(byId('body-stage'), {framingScale:1.15, onStatus(message) { setText('body-status', message); }});
const brain = createBrainView(byId('brain-stage'), {
  onStatus(message) { setText('brain-status', message); },
  onReady(info) {
    brainReady = true;
    brainState = createBrainState(info.manifest.neuron_order_sha256 || info.manifest.order_sha256);
    setText('brain-counts', `${info.manifest.positioned_neurons.toLocaleString('en-US')} positioned · ${info.manifest.missing_neurons.toLocaleString('en-US')} unplaced`);
    setText('brain-identity', `Order ${String(info.manifest.neuron_order_sha256 || '').slice(0, 10)}…`);
    setText('observe-submit', 'Observe');
    updateLabControls();
    const readout = info.manifest.readout_indices?.[0];
    if (readout) brain.select(readout.index);
  },
  onSelection(neuron) {
    setText('selected-neuron', neuron.type ? `${neuron.type}${neuron.class ? ` · ${neuron.class}` : ''}` : 'Selected neuron');
    setText('selected-neuron-meta', `${neuron.superclass || 'retained source neuron'} · retained order`);
    setText('selected-index', neuron.index ?? '—');
    setText('selected-spikes', '—');
  },
  onActivitySummary(summary) {
    setText('selected-spikes', summary.selectedIndex == null || !summary.hasActivity ? '—' : summary.selectedSpikes);
    setText('unplaced-measured', summary.unplacedCount ? `${summary.unplacedCount} unplaced · ${summary.unplacedSpikes} spikes` : 'No unplaced activity');
  },
});

function updateMotion() {
  const frozenForArchive = mode === 'archive' && replay.frame().active && !replay.frame().playing;
  body.setPaused(motionPaused || frozenForArchive);
  setText('motion-toggle', motionPaused ? 'Animate fly' : 'Pause motion');
  byId('motion-toggle').setAttribute('aria-pressed', String(motionPaused));
}
motionPreference.addEventListener('change', event => { if (!motionChosen) { motionPaused = event.matches; updateMotion(); } });
byId('motion-toggle').addEventListener('click', () => { motionChosen = true; motionPaused = !motionPaused; updateMotion(); });

function updateLabControls() {
  const enabled = mode === 'lab' && brainReady && lab.availability && !['loading','running'].includes(lab.status);
  byId('observe-submit').disabled = !enabled;
  byId('observe-cancel').disabled = mode !== 'lab' || !['loading','running'].includes(lab.status);
  byId('observe-kind').disabled = mode !== 'lab' || ['loading','running'].includes(lab.status);
  byId('observe-passed').disabled = mode !== 'lab' || ['loading','running'].includes(lab.status);
}

function updatePhaseStrip(phase = 'sensory') {
  const phases = ['sensory', 'cns', 'gate', 'instruction', 'execution'];
  document.querySelectorAll('#phase-strip span').forEach((node, index) => node.classList.toggle('active', phases[index] === phase));
}

function phaseForState(state, attempt = null) {
  if (state?.busy) return 'execution';
  if (attempt?.phase === 'choice_start' || attempt?.phase === 'feedback_start') return 'cns';
  if (attempt?.phase === 'reserve_start') return 'gate';
  if (attempt?.phase === 'send_start') return 'instruction';
  if (attempt?.phase && attempt.phase !== 'complete') return 'execution';
  return state?.status === 'completed' || state?.choice ? 'instruction' : 'sensory';
}

function setMode(next) {
  if (!['lab','coding','archive'].includes(next)) return;
  mode = next;
  document.querySelectorAll('[data-mode]').forEach(button => button.classList.toggle('selected', button.dataset.mode === next));
  byId('lab-controls').hidden = next !== 'lab';
  byId('archive-panel').hidden = next !== 'archive';
  setText('footer-mode', next === 'lab' ? 'Measured local lab · no coding calls' : next === 'coding' ? 'Live coding observer · actual backend events' : 'Read-only archive · historical full-brain activity unavailable');
  if (next !== 'lab') { brain.clearActivity(); setText('brain-mode', next === 'archive' ? 'Historic activity unavailable' : 'Waiting for measured coding window'); }
  if (next === 'coding') clearLiveReadout();
  if (next !== 'coding') codingActivity = null;
  updateLabControls();
  if (next === 'archive') loadArchive();
  updatePhaseStrip(next === 'archive' ? 'sensory' : next === 'lab' ? 'sensory' : 'cns');
  render();
}
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => setMode(button.dataset.mode)));
document.querySelectorAll('[data-brain-filter]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-brain-filter]').forEach(item => item.classList.toggle('selected', item === button));
  brain.setFilter(button.dataset.brainFilter);
}));
byId('original-language').addEventListener('change', render);

function formatRecorded(value) {
  if (!Number.isFinite(value)) return '—';
  return new Date(value).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
}
function clearLiveReadout() {
  const blank = emptyReadout();
  setText('active', blank.identity); setText('prompt', 'Waiting for a live coding run.'); setText('prompt-language', 'No instruction selected');
  setText('reason', 'Waiting for measured neural output.'); setText('left', '—'); setText('right', '—'); setText('gate', '—'); setText('feedback', '—');
  setText('simulation-time', '—'); setText('recorded-time', '—'); setText('measurement-age', 'Age unavailable'); setText('input-hash', '—'); setText('live-score', '—'); setText('live-cap', '—'); setText('live-evaluation-state', 'No coding run');
  setText('trace', 'No trace available.'); setText('input-label', 'Awaiting input'); setText('unplaced-measured', 'No unplaced activity'); setText('selected-spikes', '—'); setText('brain-mode', mode === 'coding' ? 'Waiting for measured coding window' : 'Measured bins idle');
  const image = byId('sensory'); image.hidden = true; image.removeAttribute('src'); delete image.dataset.job; byId('image-empty').hidden = false;
  document.querySelectorAll('[data-action]').forEach(node => node.classList.remove('selected'));
  setText('terminal-state', 'Waiting'); setText('terminal-backend', 'Backend —'); setText('terminal-scope', 'No coding backend connected');
  setText('translation-note', 'No coding events'); setText('model', 'Model not recorded'); setText('events', 'No coding run snapshot exists yet.'); setText('raw-events', 'No events.');
}
function updateMeasuredReadout(choice, latestBin, input, identityLabel, feedback = null) {
  const actual = choice || {};
  const actualFeedback = feedback || actual.feedback;
  const action = actual.action;
  setText('active', identityLabel || 'No window');
  setText('prompt', action ? prompts[action] || action : 'Waiting for the first measured choice.');
  setText('prompt-language', action ? 'English instruction derived from actual choice' : 'No instruction selected');
  document.querySelectorAll('[data-action]').forEach(node => node.classList.toggle('selected', node.dataset.action === action));
  setText('reason', reasons[actual.reason] || actual.reason || 'Waiting for measured neural output.');
  setText('left', actual.left_hz === undefined ? '—' : `${Number(actual.left_hz).toFixed(2)} Hz`);
  setText('right', actual.right_hz === undefined ? '—' : `${Number(actual.right_hz).toFixed(2)} Hz`);
  setText('gate', actual.gate_spikes ?? '—');
  setText('feedback', feedbackLabel(actualFeedback));
  setText('simulation-time', latestBin ? `${latestBin.start_ms}–${latestBin.end_ms} ms` : '—');
  setText('recorded-time', formatRecorded(latestBin?.recorded_at_ms));
  setText('measurement-age', measurementAge(latestBin?.recorded_at_ms));
  setText('input-hash', input?.rgb_sha256 || '—');
  const image = byId('sensory');
  image.hidden = !input;
  byId('image-empty').hidden = Boolean(input);
  if (input?.file) image.src = (mode === 'archive' ? '/archive/images/' : '/images/') + encodeURIComponent(input.file);
  setText('input-label', input ? 'Exact measured PNG' : 'Awaiting input');
  if (latestBin) setText('brain-mode', `Measured ${latestBin.start_ms}–${latestBin.end_ms} ms · ${latestBin.total_spikes} spikes`);
  else if (mode === 'lab') setText('brain-mode', 'Measured bins idle');
  setText('trace', JSON.stringify({choice:actual, latest_bin:latestBin || null, identity:identityLabel || null}, null, 2));
}

async function jsonFetch(path, options = {}) {
  const response = await fetch(path, {cache:'no-store', ...options});
  let value = null;
  try { value = await response.json(); } catch { /* the caller uses status for unavailable endpoints */ }
  return {response, value};
}

async function observe(event) {
  event.preventDefault();
  brain.clearActivity(); brainState = createBrainState(brainState.orderHash); clearLiveReadout();
  const passed = Number(byId('observe-passed').value);
  const value = {kind:byId('observe-kind').value, passed:Number.isInteger(passed) ? passed : 0};
  const result = await jsonFetch('/lab/observe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(value)});
  if (!result.response.ok) { setText('run-status', result.value?.error || 'Observation unavailable'); return; }
  labJobSeen = null;
  labCursor = 0;
  setText('run-status', 'Loading neural policy');
  render();
}
byId('observe-form').addEventListener('submit', observe);
byId('observe-cancel').addEventListener('click', async () => {
  const result = await jsonFetch('/lab/cancel', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
  if (!result.response.ok) setText('run-status', result.value?.error || 'Nothing to cancel');
});

async function refreshLab() {
  const stateResult = await jsonFetch('/lab/state');
  if (stateResult.response.status === 404) {
    lab.availability = false;
    if (!connected) setMode('archive');
    setText('connection', 'Read-only server · archive available');
    updateLabControls();
    return;
  }
  if (!stateResult.value) return;
  lab = stateResult.value;
  connected = stateResult.response.ok;
  setText('connection', lab.availability ? 'Lab connected · local only' : 'Lab unavailable · archive remains read-only');
  if (labJobSeen && lab.job_id && lab.job_id !== labJobSeen) {
    brainState = createBrainState(lab.neuron_order_sha256 || brainState.orderHash);
    brainState.cursor = labCursor;
  }
  if (lab.job_id) labJobSeen = lab.job_id;
  labCursor = Number.isInteger(labCursor) ? labCursor : 0;
  updatePhaseStrip(lab.status === 'loading' || lab.status === 'running' ? 'cns' : lab.choice ? 'gate' : 'sensory');
  const pageResult = await jsonFetch(`/lab/events?after=${labCursor}`);
  if (pageResult.value?.events) {
    brainState = applyActivityPage(brainState, pageResult.value);
    labCursor = brainState.cursor;
    const bin = brainState.lastBin;
    if (bin && brainState.overlayAllowed && ['loading','running'].includes(lab.status)) brain.setActivity(bin);
    if (!brainState.overlayAllowed) setText('brain-mode', brainState.overlayError);
    if (['completed','cancelled','error','idle'].includes(lab.status)) brain.clearActivity();
  }
  if (lab.status === 'completed') setText('run-status', 'Measured choice complete');
  else if (lab.status === 'running') setText('run-status', 'Measuring CNS · live bins');
  else if (lab.status === 'loading') setText('run-status', 'Loading neural policy');
  else if (lab.status === 'cancelled') setText('run-status', 'Observation cancelled');
  else if (lab.status === 'error') setText('run-status', lab.error || 'Observation error');
  else setText('run-status', lab.availability ? 'Ready for observation' : 'Prepared data unavailable');
  setText('evidence', lab.availability ? 'Actual local neural computation' : lab.error || 'Prepared data unavailable');
  updateMeasuredReadout(lab.choice, brainState.lastBin, lab.choice?.input_sha256 ? {rgb_sha256:lab.choice.input_sha256} : null, lab.job_id ? `Lab job ${lab.job_id.slice(0, 10)}…` : 'No window');
  if (lab.job_id) {
    const image = byId('sensory');
    image.hidden = false; byId('image-empty').hidden = true;
    if (image.dataset.job !== lab.job_id) { image.dataset.job = lab.job_id; image.hidden = false; image.src = `/lab/input.png?job_id=${encodeURIComponent(lab.job_id)}`; byId('image-empty').hidden = true; }
  }
  setText('terminal-state', 'No coding calls');
  setText('terminal-backend', 'Lab only');
  setText('terminal-scope', 'No coding backend connected');
  setText('translation-note', 'The lab emits measured neural bins only');
  setText('events', 'This observation has no coding calls.');
  setText('live-score', '—'); setText('live-cap', '—'); setText('live-evaluation-state', 'Lab observation · no external tests');
  setBodyMode(lab.status === 'running' || lab.status === 'loading' ? 'working' : 'idle');
  updateLabControls();
}

function executionText(event, original = false, workspace = '') {
  if (event?.backend === 'opencode' || event?.source === 'opencode.run.jsonl') {
    const raw = event.raw || {};
    const part = raw.part || {};
    const state = part.state || raw.state || {};
    const redact = value => {
      const text = typeof value === 'string' ? value : JSON.stringify(value);
      return text ? (workspace ? text.replaceAll(workspace, '<workspace>') : text) : '';
    };
    if (event.kind === 'tool' || raw.type === 'tool_use' || part.tool || state.input || state.output) {
      const lines = [`[OpenCode · tool]`, `Tool: ${redact(part.tool || raw.tool || 'unknown')}`];
      if (state.status || part.status) lines.push(`Status: ${redact(state.status || part.status)}`);
      if (state.input ?? part.input) lines.push(`Input: ${redact(state.input ?? part.input)}`);
      if (state.output ?? part.output) lines.push(`Output: ${redact(state.output ?? part.output)}`);
      return lines.join('\n');
    }
    const text = raw.part?.text || raw.part?.content || raw.message?.content || raw.error?.message || event.kind || 'event';
    return `[OpenCode · ${event.kind || 'event'}]\n${redact(text)}`;
  }
  return readableEvent(event, workspace, original ? [] : translations);
}
function renderTerminal(turn, state, busy) {
  const backend = turn?.backend || state?.settings?.backend || (turn?.execution ? 'codex' : '—');
  const model = state?.settings?.model || 'Model not recorded';
  const events = turn?.events || [];
  const workspace = turn ? recordedWorkspace(state.attempts?.[turn._attemptName], turn._attemptName) : '';
  const original = byId('original-language').checked;
  setText('terminal-backend', `${backend} · ${model}`);
  setText('terminal-state', busy ? `${backend} working` : events.length ? 'Recorded events' : 'Waiting');
  setText('terminal-scope', backend === 'opencode' ? 'Actual normalized OpenCode events' : 'Actual normalized execution events');
  setText('translation-note', original ? 'Original-language events' : 'English translations labeled in transcript');
  setText('model', model);
  const readable = events.map(event => executionText(event, original, workspace)).filter(Boolean).join('\n\n') || (busy ? 'Waiting for actual process events…' : 'No execution events recorded.');
  setText('events', readable);
}

async function refreshCoding() {
  const result = await jsonFetch('/snapshot.json');
  if (!result.response.ok || !result.value?.attempts) {
    connected = false; setText('connection', 'Waiting for a coding run'); setText('run-status', 'Waiting for live coding files'); setText('evidence', 'Start the CLI run separately; no automatic runner');
    setText('terminal-state', 'Waiting'); setText('terminal-backend', 'Backend —'); setText('events', 'No coding run snapshot exists yet. Select Live coding before starting the CLI run.');
    brain.clearActivity(); clearLiveReadout(); updatePhaseStrip('sensory'); setBodyMode('idle'); return;
  }
  connected = true; current = result.value;
  const entries = turns(current);
  const latest = entries.at(-1);
  if (!latest) { setText('run-status', 'Waiting for first coding turn'); clearLiveReadout(); updatePhaseStrip('sensory'); return; }
  latest.turn._attemptName = latest.name;
  const turn = latest.turn;
  const busy = Boolean(current.busy);
  const liveInput = current.attempts?.[latest.name]?.phase === 'feedback_start' ? turn.feedback_input || turn.input : turn.input;
  updatePhaseStrip(phaseForState(current, current.attempts?.[latest.name]));
  setText('run-status', busy ? 'Coding backend executing' : labels[current.status] || current.status || 'Coding run available');
  setText('evidence', current.evidence === 'genuine' ? 'Actual recorded coding run' : 'Synthetic fixture · no live submission');
  updateMeasuredReadout(turn.choice, null, liveInput, `${latest.name} · turn ${turn.step}`, turn.feedback);
  renderTerminal(turn, current, busy);
  const activityResult = await jsonFetch('/activity.json');
  if (activityResult.value?.available) {
    const document = activityResult.value;
    const expectedOrder = brainState.orderHash;
    const matchesTurn = codingActivityAllowed(document, current, latest.name, turn.step, expectedOrder);
    if (!matchesTurn) {
      codingActivity = null; brain.clearActivity();
      setText('brain-mode', expectedOrder && document.neuron_order_sha256 !== expectedOrder ? 'Activity order does not match anatomy' : 'Measured activity owner is unavailable');
      setText('measurement-age', 'Age unavailable');
    } else {
      if (codingWindow !== document.window_id) { codingWindow = document.window_id; codingCursor = 0; brainState = createBrainState(expectedOrder); }
      const page = {reset:false, latest_seq:document.window?.events?.at(-1)?.seq || 0, events:(document.window?.events || []).map(event => ({...event, neuron_order_sha256:document.neuron_order_sha256, run:document.run, attempt:document.attempt, turn:document.turn, phase:document.phase, window_id:document.window_id}))};
      brainState = applyActivityPage(brainState, page);
      codingCursor = brainState.cursor;
      const latestBin = brainState.lastBin;
      if (latestBin && brainState.overlayAllowed) brain.setActivity(latestBin);
      updateMeasuredReadout(turn.choice, latestBin, document.phase === 'feedback' ? turn.feedback_input || liveInput : liveInput, `${document.attempt} · turn ${document.turn} · ${document.phase}`, turn.feedback);
    }
  } else {
    brain.clearActivity(); setText('brain-mode', activityResult.value?.reason === 'missing' ? 'No measured activity file yet' : 'Measured activity unavailable');
  }
  const evaluation = turn.evaluation || (turn.evaluation === null ? null : null);
  const budgetUsed = current.budget?.used ?? current.reservations?.used ?? '—';
  const budgetLimit = current.budget?.limit ?? current.limits?.total ?? current.settings?.max_calls ?? '—';
  setText('live-score', evaluation ? `${evaluation.passed} / ${evaluation.total}` : '—');
  setText('live-cap', `${budgetUsed} / ${budgetLimit}`);
  setText('live-evaluation-state', evaluation ? 'Actual external evaluation' : busy ? 'Awaiting external evaluation' : 'No evaluation recorded');
  setBodyMode(busy ? 'working' : 'idle', latest);
}

function renderTable(frame) {
  const entries = turns(current); const shown = new Set(entries.slice(0, frame.completed).map(entry => entry.key)); const tbody = byId('attempts'); tbody.replaceChildren();
  for (const name of order) {
    const attempt = current?.attempts?.[name]; const completedTurns = frame.active ? (attempt?.turns || []).filter(t => shown.has(`${name}:${t.step}`)) : attempt?.turns || [];
    const latest = completedTurns.filter(t => t.evaluation).at(-1)?.evaluation || attempt?.baseline; const state = !frame.active || completedTurns.length === attempt?.turns?.length ? labels[attempt?.status] || 'Waiting' : completedTurns.length ? 'Replay in progress' : 'Not replayed';
    const row = document.createElement('tr');
    for (const value of [name, labels[name.split('-')[0]], state, `${completedTurns.filter(t => t.send_id || t.reserved).length} / 5`, latest ? `${latest.passed} / ${latest.total}` : '—']) { const cell = document.createElement('td'); cell.textContent = value; row.append(cell); }
    tbody.append(row);
  }
}
function archiveEntry(frame) { const entries = turns(current || {}); const selection = byId('history').value; return frame.active ? frame.entry : selection === 'live' ? entries.at(-1) : entries.find(item => item.key === selection); }
function renderArchive() {
  if (!current) return;
  updatePhaseStrip('sensory');
  const frame = replay.frame(); const entry = archiveEntry(frame); const demo = current.presentation?.mode === 'demo';
  const successCount = Object.values(current.attempts || {}).filter(item => item.status === 'success').length;
  setText('run-status', frame.active ? frame.phase === 'complete' ? 'Replay complete' : frame.playing ? 'Condensed replay' : 'Replay paused' : `${labels[current.status] || current.status}${current.status === 'completed' ? ` · ${successCount} / 6 successful` : ''}`);
  setText('evidence', current.evidence === 'genuine' ? 'Genuine archive · read-only' : 'Synthetic fixture · archived');
  setText('replay-play', frame.playing ? 'Pause replay' : frame.active && frame.phase !== 'complete' ? 'Resume replay' : 'Play replay');
  setText('replay-label', frame.active ? `Condensed replay · ${Math.floor(frame.elapsed / 1000)} / ${Math.round(frame.duration / 1000)} s` : `Recorded session · ${Math.round(frame.duration / 1000)} s replay`);
  byId('replay-progress').value = frame.active ? frame.progress : 0; renderTable(frame);
  brain.clearActivity(); setText('brain-mode', 'Historic activity unavailable');
  if (!entry) {
    clearLiveReadout();
    setText('run-status', 'Archive has no selected coding turn');
    setText('evidence', 'Read-only archive · no measured live bins');
    setText('terminal-state', 'Archive readout'); setText('terminal-backend', `Historical Codex · ${current.settings?.model || 'model not recorded'}`);
    setText('terminal-scope', 'Read-only recorded archive'); setText('translation-note', 'Archive events only'); setText('events', 'No selected coding turn in this archive.');
    setText('model', current.settings?.model || 'Model not recorded'); setText('brain-mode', 'Historic activity unavailable'); updatePhaseStrip('sensory'); setBodyMode('idle'); return;
  }
  const {name,turn} = entry; const choice = turn.choice || {}; const working = frame.active && frame.phase === 'working'; const live = !frame.active && byId('history').value === 'live';
  let bodyState = working ? 'replay' : 'idle'; if (!frame.active && live && current.busy) bodyState = 'working'; else if (!frame.active && live) bodyState = liveFeedback;
  setBodyMode(bodyState, entry); updateMeasuredReadout(choice, null, turn.input, `${name} · turn ${turn.step}`, turn.feedback);
  const prompt = translatePrompt(turn.prompt || prompts[choice.action] || 'Recorded instruction'); const original = byId('original-language').checked; setText('prompt', original ? turn.prompt || prompt.text : prompt.text); setText('prompt-language', prompt.translated ? original ? 'Original recorded instruction · Portuguese' : 'English translation · original preserved' : 'Original recorded instruction');
  setText('feedback', turn.feedback ? ({'-1':'Negative','0':'Neutral','1':'Positive'}[turn.feedback.signal] || 'Recorded') : working ? 'Pending replay' : 'Not delivered');
  const evaluation = evaluationForTurn(current.attempts[name], turn, !working); setText('score', evaluation ? `${evaluation.passed} / ${evaluation.total}` : '—'); setText('evaluation-state', working ? 'Before this turn' : 'Recorded result');
  const tests = byId('tests'); tests.replaceChildren(); for (const item of evaluation?.tests || []) { const li = document.createElement('li'); const result = document.createElement('span'); result.className = item.passed ? 'pass' : 'fail'; result.textContent = item.passed ? '✓' : '×'; const label = document.createElement('span'); label.textContent = String(item.id || '').replaceAll('_',' '); li.append(result, label); tests.append(li); }
  setText('violation', working ? '' : evaluation?.violation || turn.infrastructure_error || turn.codex?.error || turn.execution?.error || '');
  const events = frame.active ? frame.events : coalesceItemEvents(turn.events || []); const workspace = recordedWorkspace(current.attempts[name], name); setText('terminal-scope', `${name} · turn ${turn.step} · ${frame.active ? 'condensed replay' : 'recorded archive'}`); setText('terminal-state', frame.active ? frame.playing ? 'Replaying' : 'Paused' : 'Recorded'); setText('terminal-backend', `Codex · ${current.settings?.model || 'model not recorded'}`); setText('translation-note', original ? 'Original-language archive events' : 'Archive events · English translations labeled'); setText('model', current.settings?.model || 'Model not recorded'); setText('events', events.map(event => executionText(event, original, workspace)).filter(Boolean).join('\n\n') || 'No events recorded for this turn.'); setText('raw-events', events.map(event => JSON.stringify(event, null, 2)).join('\n\n') || 'No events.');
  const image = byId('sensory'); if (turn.input) { image.hidden = false; byId('image-empty').hidden = true; image.src = (demo ? '/archive/images/' : '/images/') + encodeURIComponent(turn.input.file); } else { image.hidden = true; byId('image-empty').hidden = false; }
}

async function loadArchive() {
  const result = await jsonFetch('/archive/snapshot.json');
  if (!result.response.ok || !result.value?.attempts) return;
  current = result.value; archiveSnapshotText = JSON.stringify(current); replay = createReplay(turns(current)); const options = [new Option('Latest turn · follow','live'), ...turns(current).map(entry => new Option(`${entry.name} · turn ${entry.turn.step}`, entry.key))]; byId('history').replaceChildren(...options); byId('history').value = 'live'; replay.select('live'); byId('replay-play').disabled = !turns(current).length; byId('replay-reset').disabled = !turns(current).length; renderArchive();
}
byId('replay-play').addEventListener('click', () => { replay.frame().playing ? replay.pause() : replay.play(); renderArchive(); });
byId('replay-reset').addEventListener('click', () => { replay.reset(); renderArchive(); });
byId('history').addEventListener('change', () => { replay.select(byId('history').value); clearLiveFeedback(); renderArchive(); });

async function refreshArchiveLive() {
  if (mode !== 'archive') return;
  const result = await jsonFetch('/snapshot.json'); if (!result.response.ok || !result.value?.attempts) return;
  const raw = JSON.stringify(result.value); const following = !replay.frame().active && byId('history').value === 'live'; const entries = turns(result.value); const latest = entries.at(-1); const oldLatest = turns(current || {}).at(-1);
  if (raw !== archiveSnapshotText) {
    for (const entry of entries) { if (entry.turn.feedback?.signal == null) continue; const key = `${entry.key}:${entry.turn.send_id || ''}`; if (!recordedFeedback.has(key)) { recordedFeedback.add(key); if (following && entry === latest) { clearLiveFeedback(); liveFeedback = entry.turn.feedback.signal < 0 ? 'failure' : entry.turn.feedback.signal > 0 ? 'success' : 'idle'; feedbackTimer = setTimeout(() => { clearLiveFeedback(); renderArchive(); }, 2500); } } }
    current = result.value; archiveSnapshotText = raw;
    if (!oldLatest || latest?.key !== oldLatest.key) { replay = createReplay(entries); const oldSelection = byId('history').value; const options = [new Option('Latest turn · follow','live'), ...entries.map(entry => new Option(`${entry.name} · turn ${entry.turn.step}`, entry.key))]; byId('history').replaceChildren(...options); byId('history').value = options.some(option => option.value === oldSelection) ? oldSelection : 'live'; replay.select(byId('history').value); byId('replay-play').disabled = !entries.length; byId('replay-reset').disabled = !entries.length; }
  }
  connected = true; setText('connection', current.presentation?.mode === 'demo' ? 'Read-only · bundled archive' : 'Connected · refreshes every 1 s'); renderArchive();
}

function render() { if (mode === 'archive') renderArchive(); }
let last = performance.now(); setInterval(() => { const now = performance.now(); const delta = now - last; last = now; if (mode === 'archive' && replay.frame().playing) { replay.advance(delta); renderArchive(); } }, 100);
async function poll() {
  try { if (mode === 'lab') await refreshLab(); else if (mode === 'coding') await refreshCoding(); else await refreshArchiveLive(); }
  catch (error) { connected = false; setText('connection', 'Disconnected · measured overlays cleared'); brain.clearActivity(); if (mode === 'lab') setText('run-status', error.message || 'Lab connection unavailable'); }
  setTimeout(poll, mode === 'lab' && ['loading','running'].includes(lab.status) ? 120 : 700);
}
fetch('/translations.json').then(response => response.ok ? response.json() : []).then(data => { translations = data; if (mode === 'archive') renderArchive(); }).catch(() => {});
window.addEventListener('pagehide', () => { body.dispose(); brain.dispose(); }, {once:true});
updateMotion(); updateLabControls(); poll();
