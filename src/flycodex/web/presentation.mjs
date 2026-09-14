export function evaluationForTurn(attempt, turn, includeCurrent = true) {
  const turnIndex = attempt.turns.indexOf(turn) - (includeCurrent ? 0 : 1);
  for (let index = turnIndex; index >= 0; index -= 1) {
    if (attempt.turns[index].evaluation) return attempt.turns[index].evaluation;
  }
  return attempt.baseline;
}
export function coalesceItemEvents(events) {
  const projected = [];
  const itemIndexes = new Map();
  for (const event of events) {
    const item = event.item || {};
    const coalesced = item.id && (item.type === 'command_execution' || item.type === 'file_change');
    if (!coalesced || !itemIndexes.has(item.id)) {
      if (coalesced) itemIndexes.set(item.id, projected.length);
      projected.push(event);
    } else {
      projected[itemIndexes.get(item.id)] = event;
    }
  }
  return projected;
}
export function relativeToWorkspace(value, workspace) {
  if (!workspace || typeof value !== 'string') return value;
  const root = workspace.replace(/\/+$/, '');
  if (value === root) return '.';
  return value.split(root + '/').join('');
}
export function recordedWorkspace(attempt, name) {
  if (attempt.workspace) return attempt.workspace;
  const marker = `/attempts/${name}/workspace`;
  for (const turn of attempt.turns || []) {
    for (const event of turn.events || []) {
      for (const change of event.item?.changes || []) {
        const path = change.path || '';
        const end = path.indexOf(marker) + marker.length;
        if (end >= marker.length && (path.length === end || path[end] === '/')) return path.slice(0, end);
      }
    }
  }
  return '';
}
export function readableEvent(event, workspace = "", translations = []) {
  const item = event.item || {};
  if (item.type === 'agent_message' || item.type === 'reasoning') {
    const projected = translate(item.text || '', translations);
    return (projected.translated ? '[English translation]\n' : '') + projected.text;
  }
  if (item.type === 'command_execution') {
    const output = item.aggregated_output || '';
    const result = item.exit_code == null ? '' : `\n[exit ${item.exit_code}]`;
    return `$ ${relativeToWorkspace(item.command || '', workspace)}\n${relativeToWorkspace(output, workspace)}${result}`;
  }
  if (item.type === 'file_change') return (item.changes || []).map(change => `[file ${change.kind || 'changed'}] ${relativeToWorkspace(change.path || '', workspace)}`).join('\n');
  if (event.type === 'thread.started') return '[session started]';
  if (event.type === 'turn.started') return '[turn started]';
  if (event.type === 'turn.completed') return '[turn completed]';
  if (event.type === 'turn.failed' || event.type === 'error') return `[failure] ${event.message || event.error?.message || 'See raw event.'}`;
  if (event.type === 'diagnostic') return `[${event.stream || 'diagnostic'}] ${event.message || ''}`;
  return `[${event.type || 'event'}] ${item.type || ''}`;
}

export function translate(original, translations = []) {
  const found = translations.find(entry => entry.original === original);
  return {text: found ? found.english : original, translated: Boolean(found)};
}
const historicalPrompts = [
  {original:'Analise a falha e explique a provável causa, sem editar.', english:'Analyze the failure and explain the likely cause without editing.'},
  {original:'Corrija a função de desconto, preservando os testes.', english:'Fix the discount function while preserving the tests.'},
  {original:'Execute os testes e relate o resultado.', english:'Run the tests and report the result.'},
];
export const translatePrompt = original => translate(original, historicalPrompts);
export const order = ['adaptive-1','frozen-1','random-1','adaptive-2','frozen-2','random-2'];
export const turns = state => order.flatMap(name => (state.attempts?.[name]?.turns || []).map(turn => ({name,turn,key:`${name}:${turn.step}`})));

// Presentation time only: no timers, writes, runner or mutations of source records.
export function createReplay(entries) {
  const turnMs = 6000;
  const feedbackAt = 4200;
  const duration = entries.length * turnMs;
  let elapsed = 0, playing = false, active = false, selection = 'live';
  return {
    play() { if (!duration) return; if (!active || elapsed >= duration) elapsed = 0; active = true; playing = true; },
    pause() { playing = false; },
    reset() { elapsed = 0; playing = false; active = Boolean(duration); },
    select(value) { playing = false; active = false; selection = value; },
    advance(ms) { if (playing) elapsed = Math.min(duration, elapsed + Math.max(0, ms)); if (elapsed >= duration) playing = false; },
    frame() {
      const index = Math.min(Math.floor(elapsed / turnMs), Math.max(0, entries.length - 1));
      const within = elapsed - index * turnMs;
      const phase = elapsed >= duration ? 'complete' : within >= feedbackAt ? 'feedback' : 'working';
      const events = coalesceItemEvents(entries[index]?.turn.events || []);
      const visible = phase === 'working' ? events.slice(0, Math.min(events.length - 1, Math.max(1, Math.floor(within / feedbackAt * events.length)))) : events;
      return {active, playing, selection, elapsed, duration, index, entry: entries[index], phase,
        completed: Math.min(entries.length, index + (phase === 'working' ? 0 : 1)), events: visible,
        progress: duration ? elapsed / duration : 0};
    },
  };
}
