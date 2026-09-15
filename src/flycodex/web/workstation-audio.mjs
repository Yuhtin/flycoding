const DEFAULT_KEY_PERIOD_MS = 60_000 / (70 * 5);
const MAX_FRAME_ADVANCE_MS = 100;
const KEY_LIFT_MS = DEFAULT_KEY_PERIOD_MS;
const KEY_ACTIVE_MS = 45;

function finite(value) {
  return Number.isFinite(value);
}

function typingSnapshot(text, count, complete, elapsedMs, typing, contact) {
  return {text, count, complete, elapsedMs, typing, contact};
}

export function createTypingSession(sourceText, {wpm = 70} = {}) {
  const source = Array.from(String(sourceText ?? ''));
  const wordsPerMinute = finite(Number(wpm)) && Number(wpm) > 0 ? Number(wpm) : 70;
  const intervalMs = 60_000 / (wordsPerMinute * 5);
  const liftMs = Math.min(KEY_LIFT_MS, intervalMs);
  let text = '';
  let count = 0;
  let elapsedMs = 0;
  let nextContactMs = intervalMs;
  let lastContactMs = -Infinity;
  let lastKey = '';

  function snapshot(contact = false) {
    const complete = count >= source.length;
    if (complete) return typingSnapshot(text, count, true, elapsedMs, {left: 0, right: 0, active: contact, cadence: contact ? 1 : 0, key: lastKey}, contact);
    if (contact) return typingSnapshot(text, count, false, elapsedMs, {left: 0, right: 0, active: true, cadence: 1, key: lastKey}, true);
    const liftStart = Math.max(0, nextContactMs - liftMs);
    const inLift = elapsedMs >= liftStart && elapsedMs < nextContactMs;
    const lift = inLift ? Math.sin(Math.PI * (elapsedMs - liftStart) / liftMs) : 0;
    const left = count % 2 === 0 ? lift : 0;
    const right = count % 2 === 1 ? lift : 0;
    const active = contact || (finite(lastContactMs) && elapsedMs - lastContactMs < KEY_ACTIVE_MS);
    return typingSnapshot(text, count, false, elapsedMs, {left, right, active, cadence: active ? 1 : 0, key: lastKey}, contact);
  }

  return {
    snapshot: () => snapshot(),
    tick(deltaMs) {
      if (count >= source.length) return snapshot();
      const delta = finite(Number(deltaMs)) ? Math.max(0, Math.min(MAX_FRAME_ADVANCE_MS, Number(deltaMs))) : 0;
      elapsedMs += delta;
      let contact = false;
      if (elapsedMs + 1e-9 >= nextContactMs) {
        lastKey = source[count];
        text += lastKey;
        count += 1;
        lastContactMs = elapsedMs;
        nextContactMs += intervalMs;
        contact = true;
      }
      return snapshot(contact);
    },
  };
}

function cue(type, atMs, durationMs = 0) {
  return {type, at_ms: Math.max(0, Math.round(atMs)), duration_ms: Math.max(0, Math.round(durationMs))};
}

export function buildCuePlan(run, keyPeriodMs = DEFAULT_KEY_PERIOD_MS) {
  if (!run) return [];
  const choiceEnd = Number(run.phases?.choice_end_ms) || 0;
  const cues = [];
  for (let atMs = 240; atMs < choiceEnd; atMs += keyPeriodMs) {
    cues.push(cue('key', atMs, 72));
  }
  return cues.sort((left, right) => left.at_ms - right.at_ms || left.type.localeCompare(right.type));
}

export function cuesBetween(plan, fromMs, toMs) {
  if (!Array.isArray(plan) || !finite(toMs)) return [];
  const start = finite(fromMs) ? fromMs : -1;
  return plan.filter(item => item.at_ms > start && item.at_ms <= toMs);
}

export function typingStateAt(plan, elapsedMs, playing) {
  if (!playing || !finite(elapsedMs)) return {active: false, cadence: 0, left: 0, right: 0};
  const keyCues = plan.filter(item => item.type === 'key');
  let left = 0;
  let right = 0;
  for (const [keyIndex, item] of keyCues.entries()) {
    const liftStart = item.at_ms - 180;
    if (elapsedMs < liftStart || elapsedMs >= item.at_ms) continue;
    const lift = Math.sin(Math.PI * (elapsedMs - liftStart) / 180);
    if (keyIndex % 2 === 0) left = Math.max(left, lift);
    else right = Math.max(right, lift);
  }
  const active = keyCues.some(item => elapsedMs >= item.at_ms && elapsedMs < item.at_ms + item.duration_ms);
  return {active, cadence: active ? 1 : 0, left, right};
}

export function scheduleSound(context, _item, time = context.currentTime, destination = context.destination) {
  const duration = .035;
  const sampleRate = context.sampleRate || 44_100;
  const buffer = context.createBuffer(1, Math.ceil(sampleRate * duration), sampleRate);
  const samples = buffer.getChannelData(0);
  let seed = 0x13579bdf;
  for (let index = 0; index < samples.length; index += 1) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    samples[index] = ((seed / 0xffffffff) * 2 - 1) * (1 - index / samples.length);
  }
  const source = context.createBufferSource();
  const filter = context.createBiquadFilter();
  const gain = context.createGain();
  const end = time + duration;
  source.buffer = buffer;
  filter.type = 'highpass';
  filter.frequency.setValueAtTime(2600, time);
  filter.Q.value = .45;
  gain.gain.value = 0;
  gain.gain.setValueAtTime(.0001, time);
  gain.gain.exponentialRampToValueAtTime(.09, time + .002);
  gain.gain.exponentialRampToValueAtTime(.0001, end);
  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    try { source.disconnect(); } catch {}
    try { filter.disconnect(); } catch {}
    try { gain.disconnect(); } catch {}
  };
  source.connect(filter).connect(gain).connect(destination);
  source.addEventListener?.('ended', cleanup);
  source.start(time);
  source.stop(end);
  return source;
}

export function createWorkstationAudio({AudioContext: Context = globalThis.AudioContext || globalThis.webkitAudioContext} = {}) {
  let context = null;
  let output = null;
  let muted = false;
  let stopped = true;
  const activeNodes = new Set();

  function silence() {
    for (const node of activeNodes) {
      try { node.stop(); } catch {}
    }
    activeNodes.clear();
  }

  function ensureContext() {
    if (context || typeof Context !== 'function') return context;
    try {
      context = new Context();
      output = context.createGain();
      output.gain.value = muted ? 0 : 1;
      output.connect(context.destination);
    } catch {
      context = null;
      output = null;
    }
    return context;
  }

  function unlock() {
    stopped = false;
    const current = ensureContext();
    try {
      const resumed = current?.state === 'suspended' ? current.resume?.() : null;
      resumed?.catch?.(() => {});
    } catch {}
    return current;
  }

  function start(_run = null) {
    silence();
    unlock();
  }

  function key() {
    silence();
    if (muted || stopped || !context || !output) return false;
    try {
      const node = scheduleSound(context, {type: 'key'}, context.currentTime, output);
      activeNodes.add(node);
      node.addEventListener?.('ended', () => activeNodes.delete(node));
      return true;
    } catch {
      return false;
    }
  }

  function setMuted(value) {
    muted = Boolean(value);
    if (output) output.gain.value = muted ? 0 : 1;
    if (muted) silence();
    return muted;
  }

  function advance(elapsedMs, playing) {
    if (!playing || muted || stopped) silence();
  }

  function stop() {
    stopped = true;
    silence();
  }

  function suspend() {
    silence();
    try {
      const suspended = context?.suspend?.();
      suspended?.catch?.(() => {});
    } catch {}
  }

  function resume() {
    try {
      const resumed = context?.resume?.();
      resumed?.catch?.(() => {});
    } catch {}
  }

  function dispose() {
    stop();
    try {
      const closed = context?.close?.();
      closed?.catch?.(() => {});
    } catch {}
    context = null;
    output = null;
  }

  return {
    unlock,
    start,
    key,
    advance,
    setMuted,
    stop,
    suspend,
    resume,
    dispose,
    isMuted: () => muted,
    hasAudioContext: () => Boolean(context),
  };
}
