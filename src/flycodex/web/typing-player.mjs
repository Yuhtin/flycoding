import {createWorkstationView} from '/workstation-view.js';
import {createTypingSession, createWorkstationAudio} from './workstation-audio.mjs';

const byId = id => document.getElementById(id);
const play = byId('play-toggle');
const input = byId('prompt-input');
const screen = byId('computer-screen');
const audioButton = byId('audio-toggle');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const audio = createWorkstationAudio();
const raster = byId('brain-stage');
const context = raster.getContext('2d', {alpha: false});
let view;
let ready = false;
let connectionReady = false;
let status = 'ready';
let session = createTypingSession(input.value);
let snapshot = session.snapshot();
let frameId = null;
let previousTime = null;
let pollTimer = null;
let releaseTimer = null;
let requestId = null;
let backend = {enabled: false};
let disposed = false;

function message(text) {
  const conversation = byId('conversation');
  if (conversation.textContent === text) return;
  const follow = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 24;
  const paragraph = document.createElement('p');
  paragraph.className = 'conversation-entry typing-output';
  paragraph.textContent = text;
  conversation.replaceChildren(paragraph);
  if (follow) conversation.scrollTop = conversation.scrollHeight;
}
function history() {
  if (!context) return;
  context.fillStyle = '#0b1718';
  context.fillRect(0, 0, raster.width, raster.height);
  context.fillStyle = '#72e4e5';
  for (let i = 0; i < Math.min(snapshot.count, 70); i++) {
    context.fillRect(i * 4, 22, 2, 28);
  }
}
function render() {
  const typing = status === 'typing';
  byId('typed-text').textContent = snapshot.text;
  byId('decision-text').scrollTop = byId('decision-text').scrollHeight;
  byId('hud-active').textContent = snapshot.count;
  byId('hud-rate').textContent = snapshot.count;
  const label = ({ready: 'Ready · press Play', typing: 'Typing · 70 WPM', paused: 'Paused', sending: 'Sending to OpenCode…', running: 'OpenCode is responding', complete: 'Complete · play again', error: 'OpenCode error · try again'})[status];
  byId('player-status').textContent = label;
  byId('hud-state').textContent = label;
  play.textContent = typing ? 'Pause' : status === 'running' ? 'Cancel' : status === 'complete' || status === 'error' ? 'Play again' : 'Play';
  play.disabled = !ready || !connectionReady || status === 'sending' || !input.value.trim();
  input.disabled = ['typing', 'paused', 'sending', 'running'].includes(status);
  byId('restart-button').disabled = status === 'running' || status === 'sending';
  view?.setState({mode: 'working', elapsedMs: snapshot.elapsedMs, typing: snapshot.typing});
  view?.setPaused(!typing || reducedMotion.matches);
  history();
}
function stopClock() {
  if (frameId !== null) cancelAnimationFrame(frameId);
  frameId = null;
  previousTime = null;
}
function tick(timestamp) {
  frameId = null;
  if (status !== 'typing' || disposed) return;
  const delta = previousTime === null ? 0 : timestamp - previousTime;
  previousTime = timestamp;
  snapshot = session.tick(delta);
  if (snapshot.contact) audio.key();
  render();
  if (snapshot.complete) {
    stopClock();
    releaseTimer = setTimeout(() => {
      snapshot = session.snapshot();
      render();
    }, 45);
    void submit();
  } else frameId = requestAnimationFrame(tick);
}
function reset() {
  stopClock();
  clearTimeout(releaseTimer);
  audio.stop();
  session = createTypingSession(input.value);
  snapshot = session.snapshot();
  requestId = null;
  status = 'ready';
  message('The fly will type your prompt, one key at a time.');
  render();
}
function pause() {
  stopClock();
  audio.suspend();
  status = 'paused';
  render();
}
async function jsonRequest(url, body) {
  const response = await fetch(url, body === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `OpenCode request failed (${response.status})`);
  return value;
}
function showBackend(value) {
  backend = value;
  if (value.text) message(value.text);
  if (value.error && value.status !== 'cancelled') {
    message(`${value.text || ''}${value.text ? '\n\n' : ''}${value.error}`);
    status = 'error';
  } else if (['completed', 'cancelled'].includes(value.status)) {
    status = 'complete';
    if (!value.text) message(value.status === 'cancelled' ? 'OpenCode was stopped.' : 'OpenCode finished without a text response.');
  } else status = 'running';
  render();
}
async function poll() {
  if (disposed || status !== 'running') return;
  const pollingRequest = requestId;
  try {
    const value = await jsonRequest('/typing/state');
    if (disposed || status !== 'running' || requestId !== pollingRequest) return;
    if (requestId && value.request_id && value.request_id !== requestId) throw new Error('A different OpenCode session is active.');
    showBackend(value);
    if (status === 'running') pollTimer = setTimeout(poll, 350);
  } catch (error) {
    status = 'error';
    message(error.message);
    render();
  }
}
async function submit() {
  if (!backend.enabled) {
    status = 'complete';
    message('Prompt typed. OpenCode is not connected.');
    render();
    return;
  }
  status = 'sending';
  message('Waiting for OpenCode…');
  render();
  requestId = crypto.randomUUID();
  try {
    const value = await jsonRequest('/typing/submit', {prompt: snapshot.text, request_id: requestId});
    showBackend(value);
    if (status === 'running') void poll();
  } catch (error) {
    status = 'error';
    message(error.message);
    render();
  }
}
play.addEventListener('click', async () => {
  if (status === 'typing') return pause();
  if (status === 'running') {
    try { showBackend(await jsonRequest('/typing/cancel', {})); }
    catch (error) { message(error.message); }
    return;
  }
  if (!ready || status === 'sending') return;
  if (status !== 'paused') reset();
  status = 'typing';
  audio.start(null);
  byId('details').open = false;
  message('The fly is typing your prompt…');
  render();
  frameId = requestAnimationFrame(tick);
});
input.addEventListener('input', reset);
byId('restart-button').addEventListener('click', reset);
byId('retry-button').addEventListener('click', () => location.reload());
audioButton.addEventListener('click', () => {
  const muted = audio.setMuted(!audio.isMuted());
  audioButton.textContent = muted ? 'Sound off' : 'Sound on';
  audioButton.setAttribute('aria-pressed', String(!muted));
  audioButton.setAttribute('aria-label', muted ? 'Unmute sound effects' : 'Mute sound effects');
});
document.addEventListener('visibilitychange', () => { if (document.hidden && status === 'typing') pause(); });
reducedMotion.addEventListener('change', render);
view = createWorkstationView(byId('body-stage'), {
  screenElement: screen,
  onReady() { ready = true; screen.classList.add('is-mounted'); render(); },
  onStatus(text) {
    if (/unavailable|failed/i.test(text)) {
      byId('error-panel').hidden = false;
      byId('error-message').textContent = text;
    }
  },
});
jsonRequest('/typing/state').then(value => {
  backend = value;
  connectionReady = true;
  render();
  document.querySelector('.screen-model').textContent = value.enabled ? 'OpenCode · live' : 'Typing simulation';
  if (value.enabled && ['running', 'starting'].includes(value.status)) {
    requestId = value.request_id;
    if (value.prompt) { input.value = value.prompt; snapshot = {...snapshot, text: value.prompt, count: Array.from(value.prompt).length, complete: true}; }
    showBackend(value);
    void poll();
  }
}).catch(() => { connectionReady = true; message('Typing is available. OpenCode is not connected.'); render(); });
window.addEventListener('pagehide', () => {
  disposed = true;
  stopClock();
  clearTimeout(pollTimer);
  clearTimeout(releaseTimer);
  audio.dispose();
  view?.dispose();
});
reset();
