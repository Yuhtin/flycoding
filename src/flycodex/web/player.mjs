import {createBodyView} from '/body-view.js';
import {createBrainView} from '/brain-view.js';
import {buttonLabel, createPlayerState, frameFor, reducePlayerState, validatePayload} from './player-state.mjs';

const byId = id => document.getElementById(id);
const bodyStage = byId('body-stage');
const brainStage = byId('brain-stage');
const playButton = byId('play-toggle');
const playerStatus = byId('player-status');
const conversation = byId('conversation');
const prefersReducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

let state = createPlayerState();
let bodyReady = false;
let brainReady = false;
let brainOrderHash = null;
let frameHandle = null;
let previousTimestamp = 0;
let renderedEvents = 0;
let activeBinKey = null;
let userAtConversationEnd = true;
let body;
let brain;

function setText(id, value) {
  const node = byId(id);
  if (node && node.textContent !== String(value)) node.textContent = String(value);
}

function statusReady(message) {
  return /ready|unavailable|could not load|could not start|interrupted/.test(String(message).toLowerCase());
}

function syncPlayAvailability() {
  const available = Boolean(state.run && state.activity && bodyReady && brainReady);
  playButton.disabled = state.status === 'loading' || state.status === 'error' || !available;
  playButton.textContent = buttonLabel(state);
}

function setStatus(message) {
  setText('player-status', message);
}

function phaseLabel(phase) {
  return ({loading: 'Loading', choice: 'Measuring the choice', execution: 'OpenCode is responding', feedback: 'Measuring feedback', complete: 'Complete'}[phase] || 'Ready');
}

function updateBody(phase) {
  const mode = phase === 'choice' || phase === 'execution' ? 'working' : phase === 'feedback' ? 'success' : 'idle';
  body?.setState({mode, action: state.run?.decision?.action || ''});
  body?.setPaused(!state.playing || prefersReducedMotion.matches);
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
  const label = document.createElement('span');
  label.className = 'entry-label';
  label.textContent = 'OpenCode';
  entry.append(label);
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

function updateReadout(frame) {
  const timelineActive = state.playing || state.status === 'paused';
  const timelineLabel = timelineActive ? phaseLabel(frame.phase) : state.status === 'complete' ? 'Complete' : state.status === 'error' ? 'Unavailable' : 'Ready';
  setText('timeline-label', timelineLabel);
  updateBody(frame.phase);
  const nextBinKey = timelineActive && frame.activeBin ? `${frame.activeBin.phase}:${frame.activeBin.at_ms}` : null;
  if (nextBinKey !== activeBinKey) {
    if (frame.activeBin) brain?.setActivity(frame.activeBin);
    else brain?.clearActivity();
    activeBinKey = nextBinKey;
  }
  const decisionVisible = Boolean(frame.decision);
  setText('decision-word', decisionVisible ? frame.decision.action[0].toUpperCase() + frame.decision.action.slice(1) : 'Press Play');
  setText('decision-text', decisionVisible ? frame.decision.text : 'The measured circuit has not chosen yet.');
  byId('decision-text').hidden = !decisionVisible;
  renderConversation(frame.events);
  const resultLine = byId('result-line');
  resultLine.hidden = !frame.result;
  if (frame.result) {
    resultLine.textContent = `${frame.result.passed}/${frame.result.total} external tests passed`;
  }
  if (state.status === 'loading') setStatus('Loading the recorded run…');
  else if (state.status === 'error') setStatus(state.error);
  else if (state.status === 'paused') setStatus(`Paused · ${phaseLabel(frame.phase).toLowerCase()}`);
  else if (state.status === 'complete') setStatus('Complete · play again');
  else if (state.playing) setStatus(phaseLabel(frame.phase));
  else if (!bodyReady || !brainReady) setStatus('Preparing the recorded views…');
  else setStatus('Ready · one recorded run');
}

function render() {
  updateReadout(frameFor(state));
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
  if (!state.run || !state.activity) return;
  if (state.playing) state = reducePlayerState(state, {type: 'PAUSE'});
  else state = state.status === 'complete' ? reducePlayerState(state, {type: 'REPLAY'}) : reducePlayerState(state, {type: 'PLAY'});
  render();
  if (state.playing) startClock(); else stopClock();
}

async function loadPayload() {
  stopClock();
  state = reducePlayerState(state, {type: 'RETRY'});
  clearConversation();
  updateReadout(frameFor(state));
  syncPlayAvailability();
  try {
    const [runResponse, activityResponse] = await Promise.all([fetch('/watch/run.json', {cache: 'no-store'}), fetch('/watch/activity.json', {cache: 'no-store'})]);
    if (!runResponse.ok || !activityResponse.ok) throw new Error('Recorded run data is unavailable.');
    const [run, activity] = await Promise.all([runResponse.json(), activityResponse.json()]);
    const valid = validatePayload(run, activity, brainOrderHash);
    if (!valid.ok) throw new Error(valid.reason);
    state = reducePlayerState(state, {type: 'PAYLOAD_READY', run, activity});
    setText('run-model', 'Muse Spark');
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

playButton.addEventListener('click', onPlay);
byId('retry-button').addEventListener('click', () => { byId('error-panel').hidden = true; loadPayload(); });
conversation.addEventListener('scroll', () => {
  userAtConversationEnd = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 24;
});
prefersReducedMotion.addEventListener('change', () => updateBody(frameFor(state).phase));

body = createBodyView(bodyStage, {onStatus(message) {
  bodyReady ||= statusReady(message);
  if (message) bodyStage.setAttribute('aria-label', `Recorded flybody presentation. ${message}`);
  syncPlayAvailability();
}});
brain = createBrainView(brainStage, {onStatus(message) {
  brainReady ||= statusReady(message);
  syncPlayAvailability();
}, onReady(info) {
  brainReady = true;
  brainOrderHash = info.manifest.neuron_order_sha256 || info.manifest.order_sha256 || null;
  if (state.run && state.activity && !validatePayload(state.run, state.activity, brainOrderHash).ok) {
    state = reducePlayerState(state, {type: 'ERROR', message: 'Recorded neural activity does not match the loaded anatomy.'});
    setText('error-message', state.error);
    byId('error-panel').hidden = false;
  }
  syncPlayAvailability();
}});
body.setPaused(true);
setStatus('Loading the recorded run…');
loadPayload();

window.addEventListener('pagehide', () => {
  stopClock();
  body?.dispose();
  brain?.dispose();
});
