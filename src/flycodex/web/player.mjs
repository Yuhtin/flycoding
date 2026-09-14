import {createWorkstationView} from '/workstation-view.js';
import {buttonLabel, createPlayerState, frameFor, reducePlayerState, validatePayload, viewReadiness} from './player-state.mjs';
import {formatMetric, hudForBin, hudLabel, latestRevealedBin, rasterIndices, RASTER_CELLS, temporalRaster} from './workstation-state.mjs';

const byId = id => document.getElementById(id);
const bodyStage = byId('body-stage');
const screen = byId('computer-screen');
const raster = byId('brain-stage');
const playButton = byId('play-toggle');
const conversation = byId('conversation');
const prefersReducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

let state = createPlayerState();
let viewReady = false;
let frameHandle = null;
let previousTimestamp = 0;
let renderedEvents = 0;
let lastRevealKey = null;
let lastMeasuredHud = null;
let rasterIndexSubset = [];
let userAtConversationEnd = true;
let workstation;
let rasterContext;

const RASTER_BACKGROUND = '#0b1718';

function setText(id, value) {
  const node = byId(id);
  if (node && node.textContent !== String(value)) node.textContent = String(value);
}

function setStatus(message) {
  setText('player-status', message);
}

function syncPlayAvailability() {
  const available = Boolean(state.run && state.activity && viewReady);
  playButton.disabled = state.status === 'loading' || state.status === 'error' || !available;
  playButton.textContent = buttonLabel(state);
}

function showViewError(message) {
  state = reducePlayerState(state, {type: 'ERROR', message});
  setText('error-message', message);
  setText('retry-button', 'Reload page');
  byId('error-panel').hidden = false;
  render();
}

function phaseLabel(phase) {
  return ({loading: 'Loading', choice: 'Measuring neural choice', execution: 'OpenCode is responding', feedback: 'Measuring feedback', complete: 'Complete'}[phase] || 'Ready');
}

function clearRaster() {
  if (!rasterContext) return;
  rasterContext.fillStyle = RASTER_BACKGROUND;
  rasterContext.fillRect(0, 0, raster.width, raster.height);
}

function createRaster() {
  raster.width = 280;
  raster.height = 72;
  rasterContext = raster.getContext('2d', {alpha: false});
  if (rasterContext) {
    rasterContext.imageSmoothingEnabled = false;
    clearRaster();
  }
}

function renderRaster(columns) {
  const context = rasterContext;
  if (!context) return;
  clearRaster();
  if (!columns.length) return;
  const columnWidth = raster.width / Math.max(70, columns.length);
  const rowHeight = raster.height / RASTER_CELLS;
  const maximum = Math.max(1, ...columns.flatMap(column => column.values));
  for (const [columnIndex, column] of columns.entries()) {
    for (const [rowIndex, value] of column.values.entries()) {
      if (!value) continue;
      context.fillStyle = `rgba(114, 228, 229, ${(.18 + .82 * value / maximum).toFixed(3)})`;
      context.fillRect(columnIndex * columnWidth, rowIndex * rowHeight, Math.max(1, columnWidth), Math.max(1, rowHeight));
    }
  }
}

function updateHud(frame) {
  const timelineActive = state.playing || state.status === 'paused' || state.status === 'complete';
  const latestBin = timelineActive ? latestRevealedBin(state.activity, frame.elapsedMs) : null;
  const revealKey = latestBin?.at_ms ?? null;
  if (timelineActive && revealKey !== lastRevealKey) {
    lastRevealKey = revealKey;
    lastMeasuredHud = hudForBin(latestBin, rasterIndexSubset);
    renderRaster(temporalRaster(state.activity, rasterIndexSubset, frame.elapsedMs));
  }
  const label = hudLabel({status: state.status, playing: state.playing, phase: frame.phase, hasBin: Boolean(frame.activeBin)});
  setText('hud-state', label);
  if (lastMeasuredHud) {
    setText('hud-active', formatMetric(lastMeasuredHud.activeNeuronCount));
    setText('hud-rate', formatMetric(lastMeasuredHud.spikesPerSecond));
  } else {
    setText('hud-active', '—');
    setText('hud-rate', '—');
  }
}

function clearConversation() {
  conversation.replaceChildren();
  const empty = document.createElement('p');
  empty.className = 'conversation-empty';
  empty.textContent = 'Output appears after the fly chooses.';
  conversation.append(empty);
  renderedEvents = 0;
}

function appendMessage(event) {
  const entry = document.createElement('article');
  entry.className = 'conversation-entry';
  entry.dataset.kind = 'message';
  const text = document.createElement('p');
  text.textContent = event.text;
  entry.append(text);
  conversation.append(entry);
}

function appendTerminalDetails(events) {
  const details = document.createElement('details');
  details.className = 'terminal-details';
  details.dataset.kind = 'tool';
  const summary = document.createElement('summary');
  summary.textContent = `Terminal details · ${events.length} recorded events`;
  details.append(summary);
  for (const event of events) {
    const entry = document.createElement('article');
    entry.className = 'conversation-entry';
    entry.dataset.kind = event.kind;
    const label = document.createElement('span');
    label.className = 'entry-label';
    label.textContent = event.kind === 'error' ? 'Error' : `Tool${event.tool ? ` · ${event.tool}` : ''}`;
    const output = document.createElement('pre');
    output.textContent = event.text;
    entry.append(label, output);
    details.append(entry);
  }
  conversation.append(details);
}

function renderConversation(events) {
  if (events.length === renderedEvents) return;
  const wasOpen = conversation.querySelector('.terminal-details')?.open || false;
  const shouldFollow = userAtConversationEnd;
  conversation.replaceChildren();
  for (const event of events.filter(item => item.kind === 'message')) appendMessage(event);
  const terminalEvents = events.filter(item => item.kind !== 'message');
  if (terminalEvents.length) {
    appendTerminalDetails(terminalEvents);
    conversation.querySelector('.terminal-details').open = wasOpen;
  }
  if (!events.length) {
    const empty = document.createElement('p');
    empty.className = 'conversation-empty';
    empty.textContent = 'Output appears after the fly chooses.';
    conversation.append(empty);
  }
  renderedEvents = events.length;
  if (shouldFollow) conversation.scrollTop = conversation.scrollHeight;
}

function updateScreen(frame) {
  const timelineActive = state.playing || state.status === 'paused';
  setText('decision-text', frame.decision?.text || 'The measured circuit has not chosen yet.');
  byId('decision-text').hidden = !frame.decision;
  renderConversation(frame.events);
  const resultLine = byId('result-line');
  resultLine.hidden = !frame.result;
  if (frame.result) resultLine.textContent = `${frame.result.passed}/${frame.result.total} external tests passed`;
  if (state.status === 'loading') setStatus('Loading the recorded run…');
  else if (state.status === 'error') setStatus(state.error);
  else if (state.status === 'paused') setStatus(`Paused · ${phaseLabel(frame.phase).toLowerCase()}`);
  else if (state.status === 'complete') setStatus('Complete · play again');
  else if (state.playing) setStatus(phaseLabel(frame.phase));
  else if (!viewReady) setStatus('Preparing the workstation…');
  else setStatus('Ready · one recorded run');
  workstation?.setState({mode: frame.phase === 'choice' || frame.phase === 'execution' ? 'working' : frame.phase === 'feedback' ? 'success' : 'idle', action: state.run?.decision?.action || ''});
  workstation?.setPaused(!state.playing || prefersReducedMotion.matches);
  updateHud(frame);
}

function render() {
  const frame = frameFor(state);
  updateScreen(frame);
  syncPlayAvailability();
}

function stopClock() {
  if (frameHandle !== null) cancelAnimationFrame(frameHandle);
  frameHandle = null;
  previousTimestamp = 0;
}

function clock(timestamp) {
  frameHandle = null;
  if (!state.playing) return;
  const elapsedMs = previousTimestamp ? Math.max(0, timestamp - previousTimestamp) : 0;
  previousTimestamp = timestamp;
  state = reducePlayerState(state, {type: 'TICK', elapsedMs});
  render();
  if (state.playing) frameHandle = requestAnimationFrame(clock);
  else stopClock();
}

function startClock() {
  stopClock();
  previousTimestamp = 0;
  frameHandle = requestAnimationFrame(clock);
}

function onPlay() {
  if (!state.run || !state.activity || !viewReady) return;
  const replaying = state.status === 'complete';
  if (state.playing) state = reducePlayerState(state, {type: 'PAUSE'});
  else state = replaying ? reducePlayerState(state, {type: 'REPLAY'}) : reducePlayerState(state, {type: 'PLAY'});
  if (replaying) {
    lastMeasuredHud = null;
    lastRevealKey = null;
    clearRaster();
  }
  render();
  if (state.playing) startClock(); else stopClock();
}

async function loadPayload() {
  stopClock();
  state = reducePlayerState(state, {type: 'RETRY'});
  lastMeasuredHud = null;
  lastRevealKey = null;
  rasterIndexSubset = [];
  clearRaster();
  clearConversation();
  render();
  try {
    const [runResponse, activityResponse, manifestResponse] = await Promise.all([fetch('/watch/run.json', {cache: 'no-store'}), fetch('/watch/activity.json', {cache: 'no-store'}), fetch('/brain/manifest.json', {cache: 'no-store'})]);
    if (!runResponse.ok || !activityResponse.ok || !manifestResponse.ok) throw new Error('Recorded run or anatomy data is unavailable.');
    const [run, activity, manifest] = await Promise.all([runResponse.json(), activityResponse.json(), manifestResponse.json()]);
    if (!manifest || !Number.isInteger(manifest.total_neurons) || manifest.total_neurons <= 0 || !manifest.neuron_order_sha256) throw new Error('Loaded anatomy manifest is invalid.');
    const valid = validatePayload(run, activity, manifest.neuron_order_sha256);
    if (!valid.ok) throw new Error(valid.reason);
    state = reducePlayerState(state, {type: 'PAYLOAD_READY', run, activity});
    rasterIndexSubset = rasterIndices(activity, RASTER_CELLS);
    setText('hud-neurons', formatMetric(manifest.total_neurons));
    setText('recording-model', run.model);
    setText('provenance-copy', `Measured neural activity and the OpenCode response come from one preserved run. Source ${run.source_revision}. Play does not start a coding backend.`);
    render();
  } catch (error) {
    state = reducePlayerState(state, {type: 'ERROR', message: error?.message || 'Recorded run could not load.'});
    setText('error-message', state.error);
    byId('error-panel').hidden = false;
    render();
  }
}

createRaster();
playButton.addEventListener('click', onPlay);
byId('retry-button').addEventListener('click', () => {
  if (byId('retry-button').textContent === 'Reload page') { location.reload(); return; }
  byId('error-panel').hidden = true;
  loadPayload();
});
conversation.addEventListener('scroll', () => {
  userAtConversationEnd = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 24;
});
prefersReducedMotion.addEventListener('change', () => workstation?.setPaused(!state.playing || prefersReducedMotion.matches));

workstation = createWorkstationView(bodyStage, {
  screenElement: screen,
  onStatus(message) {
    const readiness = viewReadiness(message);
    if (readiness === 'ready') {
      viewReady = true;
      screen.classList.add('is-mounted');
      render();
      return;
    }
    if (readiness === 'error') {
      viewReady = false;
      showViewError('Workstation view unavailable. Reload to retry.');
      return;
    }
    syncPlayAvailability();
  },
  onReady() {
    viewReady = true;
    screen.classList.add('is-mounted');
    render();
  },
});
setStatus('Loading the recorded run…');
loadPayload();

window.addEventListener('pagehide', () => {
  stopClock();
  workstation?.dispose();
});
