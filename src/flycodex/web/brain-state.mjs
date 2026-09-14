export function createBrainState(orderHash = null) {
  return {
    orderHash,
    cursor: 0,
    events: [],
    identity: {orderHash, jobId: null, windowId: null, run: null, attempt: null, turn: null, phase: null},
    lastBin: null,
    lastRecordedAtMs: null,
    overlayAllowed: true,
    overlayError: '',
  };
}

function eventIdentity(event) {
  return {
    orderHash: event.neuron_order_sha256 ?? null,
    jobId: event.job_id ?? null,
    windowId: event.window_id ?? null,
    run: event.run ?? null,
    attempt: event.attempt ?? null,
    turn: event.turn ?? null,
    phase: event.phase ?? null,
  };
}

export function overlayIdentity(event, expected) {
  if (!event || !expected) return false;
  const actual = eventIdentity(event);
  for (const key of ['orderHash', 'jobId', 'windowId', 'run', 'attempt', 'turn', 'phase']) {
    if (expected[key] != null && actual[key] != null && expected[key] !== actual[key]) return false;
  }
  if (expected.orderHash != null && actual.orderHash !== expected.orderHash) return false;
  if (expected.jobId != null && actual.jobId !== expected.jobId) return false;
  return true;
}

export function applyActivityPage(previous, page = {}) {
  const reset = Boolean(page.reset);
  const events = Array.isArray(page.events) ? page.events : [];
  const next = {
    ...previous,
    events: reset ? [] : previous.events.slice(),
    lastBin: reset ? null : previous.lastBin,
    lastRecordedAtMs: reset ? null : previous.lastRecordedAtMs,
    overlayAllowed: reset ? true : previous.overlayAllowed,
    overlayError: reset ? '' : previous.overlayError,
  };
  for (const event of events) {
    if (!reset && Number.isInteger(event.seq) && event.seq <= next.cursor && next.events.some(previousEvent => previousEvent.seq === event.seq)) continue;
    const identity = eventIdentity(event);
    if (identity.orderHash && next.orderHash && identity.orderHash !== next.orderHash) {
      next.overlayAllowed = false;
      next.overlayError = 'Activity identity does not match the anatomy order.';
    }
    if (next.identity.jobId && identity.jobId && next.identity.jobId !== identity.jobId) {
      next.overlayAllowed = false;
      next.overlayError = 'Activity identity changed while the page was live.';
    }
    next.identity = {
      ...next.identity,
      ...Object.fromEntries(Object.entries(identity).filter(([, value]) => value != null)),
    };
    next.events.push(event);
    if (event.type === 'bin') {
      next.lastBin = event;
      next.lastRecordedAtMs = event.recorded_at_ms ?? null;
    }
  }
  if (next.events.length > 512) next.events = next.events.slice(-512);
  const latest = Number.isInteger(page.latest_seq) ? page.latest_seq : next.cursor;
  next.cursor = Math.max(next.cursor, latest);
  return next;
}

export function measurementAge(recordedAtMs, nowMs = Date.now()) {
  if (!Number.isFinite(recordedAtMs)) return 'Age unavailable';
  const elapsed = nowMs - recordedAtMs;
  if (elapsed < 0) return 'Recorded time unavailable';
  return `${(elapsed / 1000).toFixed(1)} s ago`;
}
