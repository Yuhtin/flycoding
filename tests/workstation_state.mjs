import assert from 'node:assert/strict';
import test from 'node:test';
import {
  RASTER_CELLS,
  activeNeuronCount,
  formatMetric,
  hudForBin,
  hudLabel,
  rasterForHistory,
  rasterIndices,
  spikesPerSecond,
} from '../src/flycodex/web/workstation-state.mjs';

const activity = {
  bins: [
    {at_ms: 0, phase: 'choice', t_start_ms: 0, t_end_ms: 100, indices: [20, 4, 99], counts: [0, 3, 2], total_spikes: 5},
    {at_ms: 700, phase: 'feedback', t_start_ms: 500, t_end_ms: 700, indices: [4, 7], counts: [5, 1], total_spikes: 6},
  ],
};

test('HUD metrics derive measured positive counts and simulation rate', () => {
  const bin = activity.bins[0];
  assert.equal(activeNeuronCount(bin), 2);
  assert.equal(spikesPerSecond(bin), 50);
  assert.deepEqual(hudForBin(bin, [4, 20, 99]), {
    activeNeuronCount: 2,
    spikesPerSecond: 50,
    raster: [3, 0, 2],
  });
});

test('raster subset is deterministic and never exceeds measured cells', () => {
  const indices = rasterIndices(activity, RASTER_CELLS);
  assert.deepEqual(indices, [4, 7, 99]);
  assert.deepEqual(rasterIndices({...activity, bins: [...activity.bins].reverse()}, RASTER_CELLS), indices);
  assert.deepEqual(hudForBin(activity.bins[1], indices).raster, [5, 1, 0]);
  assert.deepEqual(rasterForHistory(activity, indices, 50), [3, 0, 2]);
  assert.deepEqual(rasterForHistory(activity, indices, 700), [8, 1, 2]);
});

test('HUD labels distinguish ready, paused, execution waiting, and measured activity', () => {
  assert.equal(hudLabel({playing: false, status: 'ready'}), 'Ready · press Play');
  assert.equal(hudLabel({playing: false, status: 'paused', phase: 'choice'}), 'Paused · Measuring neural choice');
  assert.equal(hudLabel({playing: true, phase: 'execution'}), 'Waiting · OpenCode is responding');
  assert.equal(hudLabel({playing: true, phase: 'feedback', hasBin: true}), 'Measured activity');
  assert.equal(formatMetric(139662), '139,662');
  assert.equal(formatMetric(50, ' spikes/s'), '50 spikes/s');
});
