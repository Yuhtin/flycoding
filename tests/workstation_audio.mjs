import assert from 'node:assert/strict';
import test from 'node:test';
import {createTypingSession, createWorkstationAudio, scheduleSound} from '../src/flycodex/web/workstation-audio.mjs';

const INTERVAL_MS = 60_000 / (100 * 5);

test('typing session runs at 100 WPM with one contact per bounded tick', () => {
  const session = createTypingSession('abc');
  assert.deepEqual(session.snapshot(), {
    text: '', count: 0, complete: false, elapsedMs: 0,
    typing: {left: 0, right: 0, active: false, cadence: 0, key: ''}, contact: false,
  });
  const lift = session.tick(99);
  assert.equal(lift.text, '');
  assert.equal(lift.typing.left > 0, true);
  const first = session.tick(INTERVAL_MS - 99 + .1);
  assert.equal(first.text, 'a');
  assert.equal(first.count, 1);
  assert.equal(first.contact, true);
  assert.deepEqual(first.typing, {left: 0, right: 0, active: true, cadence: 1, key: 'a'});
  const right = session.tick(1);
  assert.equal(right.typing.left, 0);
  assert.equal(right.typing.right > 0, true);
  assert.equal(right.typing.key, 'a');
  assert.equal(session.tick(44).typing.active, false);
});

test('large deltas are capped and 500 characters occupy one logical minute', () => {
  const session = createTypingSession('abcd');
  assert.equal(session.tick(10_000).elapsedMs <= 100, true);
  assert.equal(session.tick(10_000).count, 1);
  assert.equal(session.tick(10_000).count, 2);

  const minute = createTypingSession('x'.repeat(500));
  let state = minute.snapshot();
  for (let tick = 0; tick < 600; tick += 1) state = minute.tick(100);
  assert.equal(state.count, 500);
  assert.equal(state.complete, true);
});

test('Unicode code points each produce one character contact', () => {
  const session = createTypingSession('🙂a');
  session.tick(100);
  assert.equal(session.tick(100).text, '🙂');
  session.tick(100);
  assert.equal(session.tick(100).text, '🙂a');
});

class FakeParam {
  constructor() { this.value = 0; }
  setValueAtTime() {}
  exponentialRampToValueAtTime() {}
}

class FakeNode {
  constructor() {
    this.gain = new FakeParam();
    this.frequency = new FakeParam();
    this.playbackRate = new FakeParam();
    this.Q = {value: 0};
    this.connections = [];
    this.listeners = new Map();
    this.started = [];
    this.stopped = [];
    this.disconnected = false;
  }
  connect(destination) { this.connections.push(destination); return destination; }
  disconnect() { this.disconnected = true; }
  start(...args) { this.started.push(args); }
  stop(...args) { this.stopped.push(args); }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }
  emit(type) { for (const listener of this.listeners.get(type) || []) listener(); }
}

class FakeAudioContext {
  static instances = [];
  constructor() {
    this.currentTime = 0;
    this.state = 'suspended';
    this.destination = new FakeNode();
    this.sources = [];
    FakeAudioContext.instances.push(this);
  }
  createGain() { return new FakeNode(); }
  createBiquadFilter() { return new FakeNode(); }
  createBufferSource() { const node = new FakeNode(); this.sources.push(node); return node; }
  decodeAudioData() { return Promise.resolve({duration: 1.6}); }
  resume() { this.state = 'running'; return Promise.resolve(); }
  suspend() { this.state = 'suspended'; return Promise.resolve(); }
  close() { this.state = 'closed'; return Promise.resolve(); }
}

function fakeFetch() {
  return Promise.resolve({ok: true, arrayBuffer: () => Promise.resolve(new ArrayBuffer(16))});
}

test('prepare decodes keyboard sprite and key selects varied nonrepeating slots', async () => {
  FakeAudioContext.instances.length = 0;
  const audio = createWorkstationAudio({AudioContext: FakeAudioContext, fetch: fakeFetch});
  audio.start(null);
  assert.equal(await audio.prepare(), true);
  assert.equal(audio.isPrepared(), true);
  audio.key('a');
  audio.key('a');
  const [first, second] = FakeAudioContext.instances[0].sources;
  assert.equal(first.started[0][1] !== second.started[0][1], true);
  assert.equal(first.started[0][2], .09);
  assert.equal(first.playbackRate.value >= .94 && first.playbackRate.value <= 1.06, true);
  assert.equal(second.playbackRate.value >= .94 && second.playbackRate.value <= 1.06, true);
  assert.equal(first.stopped.length >= 2, true);
  for (let index = 0; index < 14; index++) audio.key('a');
  const sources = FakeAudioContext.instances[0].sources;
  assert.equal(new Set(sources.map(source => source.started[0][1])).size, 16);
  assert(new Set(sources.map(source => source.playbackRate.value)).size > 8);
  audio.dispose();
});

test('one key voice cancels prior voice, mute is silent, and failures are safe', async () => {
  const buffer = {duration: 1.6};
  const audio = createWorkstationAudio({AudioContext: FakeAudioContext, decodedBuffer: buffer});
  audio.start(null);
  assert.equal(audio.key('x'), true);
  assert.equal(audio.key('y'), true);
  const context = FakeAudioContext.instances.at(-1);
  assert.equal(context.sources.length, 2);
  assert.equal(context.sources[0].stopped.length >= 2, true);
  audio.setMuted(true);
  assert.equal(audio.key('z'), false);
  audio.setMuted(false);
  audio.stop();
  assert.equal(audio.key('z'), false);
  audio.dispose();

  const failed = createWorkstationAudio({AudioContext: FakeAudioContext, fetch: () => Promise.reject(new Error('missing'))});
  failed.start(null);
  assert.equal(await failed.prepare(), false);
  assert.equal(failed.key('x'), false);
  failed.dispose();
});

test('scheduleSound uses the real sprite slot and bounded playback', () => {
  const context = new FakeAudioContext();
  const node = scheduleSound(context, {duration: 1.6}, {slot: 5, playbackRate: 1.05, gain: .6, time: 2, destination: context.destination});
  assert.deepEqual(node.started[0], [2, .5, .09]);
  assert.equal(node.playbackRate.value, 1.05);
  assert.equal(node.stopped[0][0] > 2.08 && node.stopped[0][0] < 2.1, true);
  const filter = node.connections[0];
  const output = filter.connections[0];
  node.emit('ended');
  assert.equal(node.disconnected, true);
  assert.equal(filter.disconnected, true);
  assert.equal(output.disconnected, true);
});

test('disposing during sample loading prevents late audio activation', async () => {
  let finishFetch;
  const audio = createWorkstationAudio({AudioContext: FakeAudioContext,
    fetch: () => new Promise(resolve => { finishFetch = resolve; })});
  audio.start();
  const preparing = audio.prepare();
  audio.dispose();
  finishFetch(await fakeFetch());
  assert.equal(await preparing, false);
  assert.equal(await audio.prepare(), false);
  assert.equal(audio.isPrepared(), false);
  assert.equal(audio.key('a'), false);
});
