import assert from 'node:assert/strict';
import test from 'node:test';
import {buildCuePlan, createTypingSession, createWorkstationAudio, scheduleSound} from '../src/flycodex/web/workstation-audio.mjs';

const INTERVAL_MS = 60_000 / (70 * 5);

test('typing session reveals one character per bounded clock tick', () => {
  const session = createTypingSession('abc');
  assert.deepEqual(session.snapshot(), {
    text: '', count: 0, complete: false, elapsedMs: 0,
    typing: {left: 0, right: 0, active: false, cadence: 0, key: ''}, contact: false,
  });

  const beforeContact = session.tick(99);
  assert.equal(beforeContact.text, '');
  assert.equal(beforeContact.count, 0);
  assert.equal(beforeContact.contact, false);
  assert.equal(beforeContact.typing.left > 0, true);
  assert.equal(beforeContact.typing.right, 0);
  const firstContact = session.tick(INTERVAL_MS - 99 + 0.1);
  assert.equal(firstContact.text, 'a');
  assert.equal(firstContact.count, 1);
  assert.equal(firstContact.contact, true);
  assert.deepEqual(firstContact.typing, {left: 0, right: 0, active: true, cadence: 1, key: 'a'});

  const nextLift = session.tick(1);
  assert.equal(nextLift.contact, false);
  assert.equal(nextLift.typing.left, 0);
  assert.equal(nextLift.typing.right > 0, true);
  assert.equal(nextLift.typing.active, true);
  assert.equal(nextLift.typing.key, 'a');
  assert.equal(session.tick(44).typing.active, false);
});

test('large frame deltas are capped and never catch up multiple contacts', () => {
  const session = createTypingSession('abcd');
  const first = session.tick(10_000);
  assert.equal(first.elapsedMs <= 100, true);
  assert.equal(first.count, 0);
  const second = session.tick(10_000);
  assert.equal(second.count, 1);
  assert.equal(second.contact, true);
  const third = session.tick(10_000);
  assert.equal(third.count, 1);
  assert.equal(third.contact, false);
});

test('unicode characters are one logical contact and 350 chars fit one minute', () => {
  const unicode = createTypingSession('🙂a');
  unicode.tick(100);
  assert.equal(unicode.tick(100).text, '🙂');
  unicode.tick(100);
  assert.equal(unicode.tick(100).text, '🙂a');

  const session = createTypingSession('x'.repeat(350));
  let state = session.snapshot();
  for (let tick = 0; tick < 600; tick += 1) state = session.tick(100);
  assert.equal(state.count, 350);
  assert.equal(state.complete, true);
});

test('typing alternates front-leg lift and freezes after completion', () => {
  const session = createTypingSession('ab');
  session.tick(100);
  session.tick(INTERVAL_MS - 100 + 0.1);
  const rightLift = session.tick(1);
  assert.equal(rightLift.typing.left, 0);
  assert.equal(rightLift.typing.right > 0, true);
  session.tick(100);
  const complete = session.tick(INTERVAL_MS - 100 + 0.1);
  assert.equal(complete.text, 'ab');
  assert.equal(complete.complete, true);
  assert.equal(complete.contact, true);
  assert.deepEqual(complete.typing, {left: 0, right: 0, active: true, cadence: 1, key: 'b'});
  const after = session.tick(10_000);
  assert.equal(after.elapsedMs, complete.elapsedMs);
  assert.equal(after.contact, false);
  assert.equal(after.complete, true);
  assert.deepEqual(after.typing, {left: 0, right: 0, active: false, cadence: 0, key: 'b'});
});

test('legacy cue projection has no event or message sounds', () => {
  const plan = buildCuePlan({phases: {choice_end_ms: 500}, decision: {at_ms: 500}, events: [{at_ms: 700, kind: 'message'}]});
  assert.equal(plan.every(item => item.type === 'key'), true);
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
    this.Q = {value: 0};
    this.connections = [];
    this.listeners = new Map();
    this.started = [];
    this.stopped = [];
    this.disconnected = false;
  }
  connect(destination) { this.connections.push(destination); return destination; }
  disconnect() { this.disconnected = true; }
  start(time) { this.started.push(time); }
  stop(time) { this.stopped.push(time); }
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
    this.sampleRate = 1_000;
    this.state = 'suspended';
    this.destination = new FakeNode();
    this.sources = [];
    FakeAudioContext.instances.push(this);
  }
  createGain() { return new FakeNode(); }
  createBuffer(channels, length) {
    assert.equal(channels, 1);
    const samples = new Float32Array(length);
    return {getChannelData: () => samples};
  }
  createBufferSource() {
    const source = new FakeNode();
    this.sources.push(source);
    return source;
  }
  createBiquadFilter() { return new FakeNode(); }
  resume() { this.state = 'running'; return Promise.resolve(); }
  close() { this.state = 'closed'; return Promise.resolve(); }
}

test('audio unlocks explicitly and key cancels the previous voice', () => {
  FakeAudioContext.instances.length = 0;
  const audio = createWorkstationAudio({AudioContext: FakeAudioContext});
  assert.equal(audio.hasAudioContext(), false);
  assert.equal(audio.unlock() instanceof FakeAudioContext, true);
  audio.start(null);
  assert.equal(audio.key(), true);
  assert.equal(audio.key(), true);
  const context = FakeAudioContext.instances[0];
  assert.equal(context.sources.length, 2);
  assert.equal(context.sources[0].stopped.includes(undefined), true);
  audio.setMuted(true);
  assert.equal(audio.key(), false);
  assert.equal(context.sources.length, 2);
  audio.setMuted(false);
  audio.stop();
  assert.equal(audio.key(), false);
  audio.dispose();
});

test('key sound is a short filtered noise transient with ended cleanup', () => {
  const context = new FakeAudioContext();
  const node = scheduleSound(context, {type: 'key'}, 2, context.destination);
  assert.deepEqual(node.started, [2]);
  assert.deepEqual(node.stopped, [2.035]);
  assert.equal(node.buffer.getChannelData(0).some(sample => sample !== 0), true);
  const filter = node.connections[0];
  const gain = filter.connections[0];
  node.emit('ended');
  assert.equal(node.disconnected, true);
  assert.equal(filter.disconnected, true);
  assert.equal(gain.disconnected, true);
});

test('missing audio API never blocks the typing caller', () => {
  const silent = createWorkstationAudio({AudioContext: undefined});
  assert.doesNotThrow(() => {
    silent.unlock();
    silent.start(null);
    silent.key();
    silent.stop();
    silent.dispose();
  });
});
