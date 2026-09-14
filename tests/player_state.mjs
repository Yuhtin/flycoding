import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createPlayerState,
  frameFor,
  reducePlayerState,
  validatePayload,
} from '../src/flycodex/web/player-state.mjs';

const run = {
  version: 1,
  title: 'Recorded Muse run',
  backend: 'opencode',
  model: 'opencode/muse-spark-1.3-contributor-free',
  source_revision: '160ca8b',
  duration_ms: 1000,
  phases: {choice_end_ms: 300, execution_end_ms: 700, feedback_end_ms: 850},
  decision: {at_ms: 240, action: 'fix', text: 'Fix the discount function while preserving the tests.'},
  events: [
    {at_ms: 320, kind: 'message', text: 'I will inspect the function.'},
    {at_ms: 460, kind: 'tool', text: '$ rtk proxy python -B -m unittest -v', tool: 'bash', status: 'completed'},
    {at_ms: 620, kind: 'message', text: 'The tests pass after the edit.'},
  ],
  result: {at_ms: 760, passed: 5, total: 5, before: 1},
  provenance: {neuron_order_sha256: 'abc', recording: 'genuine'},
};
const activity = {
  version: 1,
  neuron_order_sha256: 'abc',
  bins: [
    {at_ms: 0, phase: 'choice', t_start_ms: 0, t_end_ms: 100, indices: [1], counts: [4], total_spikes: 4},
    {at_ms: 100, phase: 'choice', t_start_ms: 100, t_end_ms: 200, indices: [2], counts: [5], total_spikes: 5},
    {at_ms: 700, phase: 'feedback', t_start_ms: 500, t_end_ms: 600, indices: [3], counts: [6], total_spikes: 6},
  ],
};

test('payload validation requires one matching recorded run and activity', () => {
  assert.deepEqual(validatePayload(run, activity, 'abc'), {ok: true});
  assert.equal(validatePayload({...run, backend: 'codex'}, activity).ok, false);
  assert.equal(validatePayload(run, activity, 'wrong').ok, false);
  assert.equal(validatePayload(run, {...activity, neuron_order_sha256: 'wrong'}).ok, false);
  assert.equal(validatePayload(run, {...activity, bins: []}).ok, false);
});

test('decision and output remain hidden until their measured timestamps', () => {
  assert.equal(frameFor({run, activity, elapsedMs: 100}).decision, null);
  assert.equal(frameFor({run, activity, elapsedMs: 239}).decision, null);
  assert.equal(frameFor({run, activity, elapsedMs: 240}).decision.text, run.decision.text);
  assert.deepEqual(frameFor({run, activity, elapsedMs: 600}).events.map(event => event.text), [
    'I will inspect the function.',
    '$ rtk proxy python -B -m unittest -v',
  ]);
  assert.equal(frameFor({run, activity, elapsedMs: 759}).result, null);
  assert.deepEqual(frameFor({run, activity, elapsedMs: 760}).result, run.result);
});

test('measured activity is visible only in choice and feedback windows', () => {
  assert.equal(frameFor({run, activity, elapsedMs: 50}).activeBin.total_spikes, 4);
  assert.equal(frameFor({run, activity, elapsedMs: 350}).activeBin, null);
  assert.equal(frameFor({run, activity, elapsedMs: 750}).activeBin.total_spikes, 6);
  assert.equal(frameFor({run, activity, elapsedMs: 900}).activeBin, null);
});

test('reducer pauses, resumes, completes, and replays without changing payload', () => {
  let state = createPlayerState(run, activity);
  state = reducePlayerState(state, {type: 'PLAY'});
  state = reducePlayerState(state, {type: 'TICK', elapsedMs: 500});
  assert.equal(state.playing, true);
  assert.equal(state.elapsedMs, 500);
  state = reducePlayerState(state, {type: 'PAUSE'});
  state = reducePlayerState(state, {type: 'TICK', elapsedMs: 300});
  assert.equal(state.elapsedMs, 500);
  state = reducePlayerState(state, {type: 'PLAY'});
  state = reducePlayerState(state, {type: 'TICK', elapsedMs: 600});
  assert.equal(state.playing, false);
  assert.equal(state.elapsedMs, 1000);
  state = reducePlayerState(state, {type: 'REPLAY'});
  assert.equal(state.playing, true);
  assert.equal(state.elapsedMs, 0);
  assert.equal(state.run, run);
  assert.equal(state.activity, activity);
});

test('error and retry states never expose stale recorded output', () => {
  let state = createPlayerState(run, activity);
  state = reducePlayerState(state, {type: 'ERROR', message: 'Payload unavailable'});
  assert.equal(state.status, 'error');
  assert.equal(state.run, null);
  assert.equal(state.activity, null);
  state = reducePlayerState(state, {type: 'RETRY'});
  assert.equal(state.status, 'loading');
  assert.equal(state.run, null);
});
