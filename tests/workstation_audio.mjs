import assert from 'node:assert/strict';
import test from 'node:test';
import {buildCuePlan, cuesBetween, createWorkstationAudio, scheduleSound, typingStateAt} from '../src/flycodex/web/workstation-audio.mjs';

const run = {
  duration_ms: 2_000,
  phases: {choice_end_ms: 800},
  decision: {at_ms: 800},
  events: [
    {at_ms: 1_000, kind: 'message', text: 'Muse update'},
    {at_ms: 1_400, kind: 'tool', text: 'test output'},
  ],
};

test('cue plan places deterministic key bursts and mouse boundaries', () => {
  const plan = buildCuePlan(run, 200);
  assert.deepEqual(plan.filter(cue => cue.type === 'key').map(cue => cue.at_ms), [240, 440, 640, 1034, 1112]);
  assert.deepEqual(plan.filter(cue => cue.type === 'mouse').map(cue => cue.at_ms), [800, 1000, 1400]);
  assert.deepEqual(cuesBetween(plan, 799, 800).map(cue => cue.type), ['mouse']);
  assert.equal(typingStateAt(plan, 270, true).active, true);
  assert.equal(typingStateAt(plan, 270, false).active, false);
});

test('typing lift alternates sides and is zero outside each pre-contact window', () => {
  const plan = buildCuePlan(run, 200);
  const firstLift = typingStateAt(plan, 150, true);
  assert.equal(firstLift.left > 0, true);
  assert.equal(firstLift.right, 0);
  const secondLift = typingStateAt(plan, 350, true);
  assert.equal(secondLift.left, 0);
  assert.equal(secondLift.right > 0, true);
  assert.deepEqual(typingStateAt(plan, 240, true), {active: true, cadence: 1, left: 0, right: 0});
  assert.deepEqual(typingStateAt(plan, 20, true), {active: false, cadence: 0, left: 0, right: 0});
  assert.deepEqual(typingStateAt(plan, 150, false), {active: false, cadence: 0, left: 0, right: 0});
});

class FakeParam {
  setValueAtTime() {}
  exponentialRampToValueAtTime() {}
}

class FakeNode {
  constructor() {
    this.gain = new FakeParam();
    this.frequency = new FakeParam();
    this.Q = {value: 0};
    this.started = [];
    this.stopped = [];
    this.connections = [];
    this.listeners = new Map();
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
    this.oscillators = [];
    FakeAudioContext.instances.push(this);
  }
  createGain() { return new FakeNode(); }
  createBuffer(channels, length) {
    assert.equal(channels, 1);
    const samples = new Float32Array(length);
    return {getChannelData: () => samples};
  }
  createBufferSource() {
    const node = new FakeNode();
    this.oscillators.push(node);
    return node;
  }
  createBiquadFilter() { return new FakeNode(); }
  resume() { this.state = 'running'; return Promise.resolve(); }
  close() { this.state = 'closed'; return Promise.resolve(); }
}

test('audio unlocks from start, pauses without catch-up, and mutes active nodes', () => {
  FakeAudioContext.instances.length = 0;
  const audio = createWorkstationAudio({AudioContext: FakeAudioContext});
  assert.equal(audio.hasAudioContext(), false);
  audio.advance(500, true);
  audio.start(run);
  assert.equal(audio.hasAudioContext(), true);
  audio.advance(0, true);
  audio.advance(300, true);
  const context = FakeAudioContext.instances[0];
  assert.equal(context.oscillators.length, 1);
  audio.advance(700, false);
  assert.equal(context.oscillators[0].stopped.includes(undefined), true);
  audio.resume();
  audio.advance(1_100, true);
  assert.equal(context.oscillators.length, 1);
  audio.setMuted(true);
  assert.equal(audio.isMuted(), true);
  audio.advance(1_500, true);
  assert.equal(context.oscillators.length, 1);
  audio.dispose();
});

test('long render gaps only schedule recent cues', () => {
  FakeAudioContext.instances.length = 0;
  const audio = createWorkstationAudio({AudioContext: FakeAudioContext});
  audio.start(run);
  audio.advance(0, true);
  audio.advance(1_000, true);
  const context = FakeAudioContext.instances[0];
  assert.equal(context.oscillators.length, 1, 'the cue at 1000ms is recent');
  audio.advance(1_500, true);
  assert.equal(context.oscillators.length, 2, 'the cue at 1400ms is recent');
  audio.dispose();
});

test('scheduleSound is safe for an offline-style context and missing audio API', () => {
  const context = new FakeAudioContext();
  const node = scheduleSound(context, {type: 'mouse'}, 2, context.destination);
  assert.deepEqual(node.started, [2]);
  assert.deepEqual(node.stopped, [2.055]);
  assert.equal(node.buffer.getChannelData(0).some(sample => sample !== 0), true);
  const filter = node.connections[0];
  const gain = filter.connections[0];
  node.emit('ended');
  assert.equal(node.disconnected, true);
  assert.equal(filter.disconnected, true);
  assert.equal(gain.disconnected, true);
  const silent = createWorkstationAudio({AudioContext: undefined});
  assert.doesNotThrow(() => { silent.start(run); silent.advance(100, true); silent.stop(); silent.dispose(); });
});
