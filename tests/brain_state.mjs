import test from 'node:test';
import assert from 'node:assert/strict';
import {applyActivityPage, createBrainState, measurementAge, overlayIdentity} from '../src/flycodex/web/brain-state.mjs';

test('activity pages retain the newest measured bin and server timestamp', () => {
  const initial = createBrainState('order-a');
  const next = applyActivityPage(initial, {
    reset: false,
    latest_seq: 2,
    events: [
      {seq: 1, type: 'started', job_id: 'job-1', neuron_order_sha256: 'order-a'},
      {seq: 2, type: 'bin', job_id: 'job-1', neuron_order_sha256: 'order-a',
       start_ms: 40, end_ms: 50, indices: [4, 9], counts: [2, 1], total_spikes: 3,
       recorded_at_ms: 1700000000000},
    ],
  });
  assert.equal(next.cursor, 2);
  assert.deepEqual(next.lastBin.indices, [4, 9]);
  assert.equal(next.lastBin.end_ms, 50);
  assert.equal(next.lastRecordedAtMs, 1700000000000);
  assert.equal(next.identity.jobId, 'job-1');
});

test('reset and mixed identity refuse stale overlays while retaining the new page', () => {
  const running = applyActivityPage(createBrainState('order-a'), {
    reset: false, latest_seq: 1,
    events: [{seq: 1, type: 'bin', job_id: 'old', neuron_order_sha256: 'order-a',
      start_ms: 0, end_ms: 10, indices: [2], counts: [1], total_spikes: 1}],
  });
  const reset = applyActivityPage(running, {
    reset: true, latest_seq: 4,
    events: [{seq: 4, type: 'bin', job_id: 'new', neuron_order_sha256: 'order-b',
      start_ms: 0, end_ms: 10, indices: [7], counts: [4], total_spikes: 4}],
  });
  assert.equal(reset.cursor, 4);
  assert.deepEqual(reset.lastBin.indices, [7]);
  assert.equal(reset.overlayAllowed, false);
  assert.match(reset.overlayError, /identity/i);
});

test('measurement age uses recorded time and reports unavailable when absent', () => {
  assert.equal(measurementAge(1700000000000, 1700000001250), '1.3 s ago');
  assert.equal(measurementAge(undefined, 1700000001250), 'Age unavailable');
  assert.equal(measurementAge(1700000005000, 1700000001250), 'Recorded time unavailable');
});

test('overlay identity includes the run window and retained-order hash', () => {
  assert.equal(overlayIdentity({neuron_order_sha256: 'h', job_id: 'j'}, {jobId: 'j', windowId: null, orderHash: 'h'}), true);
  assert.equal(overlayIdentity({neuron_order_sha256: 'h', job_id: 'j'}, {jobId: 'other', windowId: null, orderHash: 'h'}), false);
});

test('repeated full activity pages do not duplicate events or grow without bound', () => {
  const page = {reset:false, latest_seq:2, events:[
    {seq:1, type:'start', neuron_order_sha256:'h', window_id:'w'},
    {seq:2, type:'bin', neuron_order_sha256:'h', window_id:'w', start_ms:0, end_ms:10, indices:[1], counts:[2], total_spikes:2},
  ]};
  let state = createBrainState('h');
  state = applyActivityPage(state, page);
  state = applyActivityPage(state, page);
  assert.equal(state.events.length, 2);
  assert.equal(state.lastBin.total_spikes, 2);
});

test('activity identity must match the selected coding turn before overlaying', () => {
  const expected = {orderHash:'h', jobId:null, windowId:'w', run:'run-1', attempt:'adaptive-1', turn:2, phase:'choice'};
  assert.equal(overlayIdentity({neuron_order_sha256:'h', window_id:'w', run:'run-1', attempt:'adaptive-1', turn:2, phase:'choice'}, expected), true);
  assert.equal(overlayIdentity({neuron_order_sha256:'h', window_id:'w', run:'run-1', attempt:'adaptive-1', turn:1, phase:'choice'}, expected), false);
});
