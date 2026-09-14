const ACTIONS = new Set(['investigate', 'fix', 'test']);
const PHASES = new Set(['choice', 'execution', 'feedback']);

const finite = value => Number.isFinite(value);

export function validatePayload(run, activity, expectedOrderHash = null) {
  if (!run || run.version !== 1 || run.backend !== 'opencode') return {ok: false, reason: 'Recorded run metadata is unavailable.'};
  if (!run.model || !run.source_revision || !finite(run.duration_ms) || run.duration_ms <= 0) return {ok: false, reason: 'Recorded run timing is unavailable.'};
  const phases = run.phases;
  if (!phases || !finite(phases.choice_end_ms) || !finite(phases.execution_end_ms) || !finite(phases.feedback_end_ms)
    || phases.choice_end_ms <= 0 || phases.choice_end_ms > phases.execution_end_ms || phases.execution_end_ms > phases.feedback_end_ms
    || phases.feedback_end_ms > run.duration_ms) return {ok: false, reason: 'Recorded phase timing is invalid.'};
  if (!run.decision || !ACTIONS.has(run.decision.action) || !finite(run.decision.at_ms) || !run.decision.text) return {ok: false, reason: 'Recorded decision is unavailable.'};
  if (!Array.isArray(run.events) || !run.events.every(event => event && finite(event.at_ms) && ['message', 'tool', 'error'].includes(event.kind) && typeof event.text === 'string')) return {ok: false, reason: 'Recorded conversation is invalid.'};
  if (!run.result || !finite(run.result.at_ms) || !finite(run.result.passed) || !finite(run.result.total)) return {ok: false, reason: 'Recorded result is unavailable.'};
  if (!activity || activity.version !== 1 || activity.neuron_order_sha256 !== run.provenance?.neuron_order_sha256 || (expectedOrderHash && activity.neuron_order_sha256 !== expectedOrderHash) || !Array.isArray(activity.bins) || !activity.bins.length) return {ok: false, reason: 'Recorded neural activity is unavailable.'};
  if (!activity.bins.every((bin, index) => bin && PHASES.has(bin.phase) && finite(bin.at_ms) && (index === 0 || bin.at_ms >= activity.bins[index - 1].at_ms) && finite(bin.t_start_ms) && finite(bin.t_end_ms) && bin.t_end_ms > bin.t_start_ms
    && Array.isArray(bin.indices) && Array.isArray(bin.counts) && bin.indices.length === bin.counts.length)) return {ok: false, reason: 'Recorded neural timing is invalid.'};
  return {ok: true};
}

export function createPlayerState(run = null, activity = null) {
  return {
    status: run && activity ? 'ready' : 'loading',
    playing: false,
    elapsedMs: 0,
    run,
    activity,
    error: null,
  };
}

export function reducePlayerState(state, action) {
  if (!action || typeof action.type !== 'string') return state;
  if (action.type === 'PAYLOAD_READY') return {...createPlayerState(action.run, action.activity), status: 'ready'};
  if (action.type === 'ERROR') return {...createPlayerState(), status: 'error', error: String(action.message || 'Recorded run could not load.')};
  if (action.type === 'RETRY') return {...createPlayerState(), status: 'loading'};
  if (!state.run || !state.activity) return state;
  if (action.type === 'PLAY') {
    const atEnd = state.elapsedMs >= state.run.duration_ms;
    return {...state, status: 'playing', playing: true, elapsedMs: atEnd ? 0 : state.elapsedMs, error: null};
  }
  if (action.type === 'PAUSE') return {...state, status: 'paused', playing: false};
  if (action.type === 'REPLAY') return {...state, status: 'playing', playing: true, elapsedMs: 0, error: null};
  if (action.type === 'TICK' && state.playing) {
    const elapsedMs = Math.min(state.run.duration_ms, state.elapsedMs + Math.max(0, Number(action.elapsedMs) || 0));
    return {...state, elapsedMs, playing: elapsedMs < state.run.duration_ms, status: elapsedMs < state.run.duration_ms ? 'playing' : 'complete'};
  }
  return state;
}

function phaseAt(run, elapsedMs) {
  if (elapsedMs >= run.duration_ms) return 'complete';
  if (elapsedMs < run.phases.choice_end_ms) return 'choice';
  if (elapsedMs < run.phases.execution_end_ms) return 'execution';
  if (elapsedMs < run.phases.feedback_end_ms) return 'feedback';
  return 'complete';
}

export function frameFor({run, activity, elapsedMs = 0}) {
  if (!run || !activity) return {phase: 'loading', decision: null, events: [], result: null, activeBin: null};
  const elapsed = Math.max(0, Math.min(run.duration_ms, Number(elapsedMs) || 0));
  const phase = phaseAt(run, elapsed);
  const decision = elapsed >= run.decision.at_ms ? run.decision : null;
  const events = run.events.filter(event => event.at_ms <= elapsed);
  const result = elapsed >= run.result.at_ms ? run.result : null;
  const phaseBins = phase === 'choice' || phase === 'feedback' ? activity.bins.filter(bin => bin.phase === phase) : [];
  let activeBin = null;
  for (let index = phaseBins.length - 1; index >= 0; index -= 1) {
    const bin = phaseBins[index];
    const end = phaseBins[index + 1]?.at_ms ?? (phase === 'choice' ? run.phases.choice_end_ms : run.phases.feedback_end_ms);
    if (elapsed >= bin.at_ms && elapsed < end) { activeBin = bin; break; }
  }
  return {phase, elapsedMs: elapsed, decision, events, result, activeBin};
}

export function buttonLabel(state) {
  if (state.status === 'loading') return 'Loading…';
  if (state.status === 'error') return 'Try again';
  if (state.playing) return 'Pause';
  if (state.status === 'complete') return 'Play again';
  return 'Play';
}
