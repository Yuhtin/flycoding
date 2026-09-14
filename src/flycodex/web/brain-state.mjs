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

export function feedbackLabel(feedback) {
  if (!feedback || !Number.isInteger(feedback.signal)) return '—';
  return ({'-1': 'Negative', '0': 'Neutral', '1': 'Positive'})[String(feedback.signal)] || 'Recorded';
}

export function emptyReadout() {
  return {choice: null, feedback: null, input: null, latestBin: null, identity: 'No window'};
}

export function measuredActivity(indices = [], counts = [], pointByRetained = new Int32Array(), selectedIndex = null) {
  const drawableIndices = [], drawableCounts = [];
  let unplacedCount = 0, unplacedSpikes = 0, selectedSpikes = 0;
  for (let position = 0; position < indices.length; position += 1) {
    const retained = indices[position], count = counts[position] || 0;
    if (retained === selectedIndex) selectedSpikes = count;
    const point = pointByRetained[retained] ?? -1;
    if (point < 0) { unplacedCount += 1; unplacedSpikes += count; }
    else { drawableIndices.push(retained); drawableCounts.push(count); }
  }
  return {drawableIndices, drawableCounts, unplacedCount, unplacedSpikes, selectedSpikes};
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

export function codingActivityAllowed(activity, current, attemptName, turnNumber, orderHash = null) {
  if (!activity?.available || activity.status !== 'running' || !current || current.status !== 'running' || current.busy) return false;
  if (orderHash != null && activity.neuron_order_sha256 !== orderHash) return false;
  if (current.active_attempt !== attemptName || activity.attempt !== attemptName || Number(activity.turn) !== Number(turnNumber)) return false;
  const attempt = current.attempts?.[attemptName];
  if (!attempt || attempt.status !== 'running') return false;
  const phase = activity.phase === 'choice' ? 'choice_start' : activity.phase === 'feedback' ? 'feedback_start' : null;
  if (!phase || attempt.phase !== phase) return false;
  const turn = (attempt.turns || []).find(item => Number(item.step) === Number(turnNumber));
  if (!turn) return false;
  const expectedRun = current.run || current.settings?.run;
  if (expectedRun != null && activity.run !== expectedRun) return false;
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
    identity: reset ? {...previous.identity, jobId: null, windowId: null, run: null, attempt: null, turn: null, phase: null} : previous.identity,
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
