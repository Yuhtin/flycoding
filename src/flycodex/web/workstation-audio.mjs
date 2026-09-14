const DEFAULT_KEY_PERIOD_MS = 420;
const MAX_CUE_AGE_MS = 120;
const MAX_VOICES = 4;

function finite(value) {
  return Number.isFinite(value);
}

function cue(type, atMs, durationMs = 0) {
  return {type, at_ms: Math.max(0, Math.round(atMs)), duration_ms: Math.max(0, Math.round(durationMs))};
}

export function buildCuePlan(run, keyPeriodMs = DEFAULT_KEY_PERIOD_MS) {
  if (!run) return [];
  const choiceEnd = Number(run.phases?.choice_end_ms) || 0;
  const duration = Number(run.duration_ms) || Infinity;
  const cues = [];
  for (let atMs = 240; atMs < choiceEnd; atMs += keyPeriodMs) {
    cues.push(cue('key', atMs, 72));
  }
  const decisionAt = Number(run.decision?.at_ms);
  if (finite(decisionAt) && decisionAt <= duration) cues.push(cue('mouse', decisionAt, 42));
  for (const event of run.events || []) {
    if (!finite(event?.at_ms) || event.at_ms > duration) continue;
    const atMs = Math.max(0, event.at_ms);
    cues.push(cue('mouse', atMs, 38));
    if (event.kind === 'message') {
      cues.push(cue('key', atMs + 34, 68));
      cues.push(cue('key', atMs + 112, 68));
    }
  }
  return cues.sort((left, right) => left.at_ms - right.at_ms || left.type.localeCompare(right.type));
}

export function cuesBetween(plan, fromMs, toMs) {
  if (!Array.isArray(plan) || !finite(toMs)) return [];
  const start = finite(fromMs) ? fromMs : -1;
  return plan.filter(item => item.at_ms > start && item.at_ms <= toMs);
}

export function typingStateAt(plan, elapsedMs, playing) {
  if (!playing || !finite(elapsedMs)) return {active: false, cadence: 0};
  const active = plan.some(item => item.type === 'key' && elapsedMs >= item.at_ms && elapsedMs < item.at_ms + item.duration_ms);
  return {active, cadence: active ? 1 : 0};
}

export function scheduleSound(context, item, time = context.currentTime, destination = context.destination) {
  const duration = item.type === 'mouse' ? .055 : .035;
  const sampleRate = context.sampleRate || 44_100;
  const buffer = context.createBuffer(1, Math.ceil(sampleRate * duration), sampleRate);
  const samples = buffer.getChannelData(0);
  let seed = item.type === 'mouse' ? 0x7f4a7c15 : 0x13579bdf;
  for (let index = 0; index < samples.length; index += 1) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    samples[index] = ((seed / 0xffffffff) * 2 - 1) * (1 - index / samples.length);
  }
  const source = context.createBufferSource();
  const filter = context.createBiquadFilter();
  const gain = context.createGain();
  const end = time + duration;
  source.buffer = buffer;
  filter.type = item.type === 'mouse' ? 'lowpass' : 'highpass';
  filter.frequency.setValueAtTime(item.type === 'mouse' ? 1100 : 2600, time);
  filter.Q.value = item.type === 'mouse' ? .7 : .45;
  gain.gain.setValueAtTime(.0001, time);
  gain.gain.exponentialRampToValueAtTime(item.type === 'mouse' ? .045 : .022, time + .002);
  gain.gain.exponentialRampToValueAtTime(.0001, end);
  source.connect(filter).connect(gain).connect(destination);
  source.start(time);
  source.stop(end);
  return source;
}

export function createWorkstationAudio({AudioContext: Context = globalThis.AudioContext || globalThis.webkitAudioContext} = {}) {
  let context = null;
  let output = null;
  let muted = false;
  let stopped = true;
  let plan = [];
  let cursorMs = -1;
  let wasPlaying = false;
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

  function start(run) {
    plan = buildCuePlan(run);
    cursorMs = -1;
    wasPlaying = false;
    stopped = false;
    const current = ensureContext();
    try {
      const resumed = current?.state === 'suspended' ? current.resume?.() : null;
      resumed?.catch?.(() => {});
    } catch {}
  }

  function setMuted(value) {
    muted = Boolean(value);
    if (output) output.gain.value = muted ? 0 : 1;
    if (muted) {
      wasPlaying = false;
      silence();
    }
    return muted;
  }

  function advance(elapsedMs, playing) {
    if (!finite(elapsedMs)) return;
    if (!playing || muted || stopped || !context || !output) {
      cursorMs = elapsedMs;
      wasPlaying = false;
      silence();
      return;
    }
    if (!wasPlaying) {
      cursorMs = elapsedMs;
      wasPlaying = true;
      return;
    }
    if (elapsedMs < cursorMs) cursorMs = -1;
    const elapsedCues = cuesBetween(plan, Math.max(cursorMs, elapsedMs - MAX_CUE_AGE_MS), elapsedMs).slice(-MAX_VOICES);
    cursorMs = elapsedMs;
    wasPlaying = true;
    for (const item of elapsedCues) {
      try {
        while (activeNodes.size >= MAX_VOICES) {
          const oldest = activeNodes.values().next().value;
          activeNodes.delete(oldest);
          oldest.stop();
        }
        const node = scheduleSound(context, item, context.currentTime, output);
        activeNodes.add(node);
        node.addEventListener?.('ended', () => activeNodes.delete(node));
      } catch {}
    }
  }

  function stop() {
    stopped = true;
    cursorMs = -1;
    wasPlaying = false;
    plan = [];
    silence();
  }

  function suspend() {
    wasPlaying = false;
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
    start,
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
