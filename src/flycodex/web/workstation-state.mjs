const PHASE_LABELS = {
  choice: 'Measuring neural choice',
  execution: 'Waiting for OpenCode',
  feedback: 'Measuring feedback',
  complete: 'Complete',
};

export const RASTER_CELLS = 96;

const positive = value => Number.isFinite(value) && value > 0;

export function activeNeuronCount(bin) {
  if (!bin || !Array.isArray(bin.counts)) return 0;
  return bin.counts.filter(positive).length;
}

export function spikesPerSecond(bin) {
  if (!bin || !Number.isFinite(bin.total_spikes) || !Number.isFinite(bin.t_start_ms) || !Number.isFinite(bin.t_end_ms)) return null;
  const seconds = (bin.t_end_ms - bin.t_start_ms) / 1000;
  return seconds > 0 ? bin.total_spikes / seconds : null;
}

export function rasterIndices(activity, limit = RASTER_CELLS) {
  const indices = new Set();
  for (const bin of activity?.bins || []) {
    for (const [index, count] of (bin.indices || []).map((index, position) => [index, bin.counts?.[position]])) {
      if (Number.isInteger(index) && positive(count)) indices.add(index);
    }
  }
  return [...indices].sort((left, right) => left - right).slice(0, Math.max(0, limit));
}

export function rasterForBin(bin, indices) {
  const values = new Map();
  for (const [index, count] of (bin?.indices || []).map((index, position) => [index, bin.counts?.[position]])) {
    if (Number.isInteger(index) && positive(count)) values.set(index, count);
  }
  return (indices || []).map(index => values.get(index) || 0);
}

export function temporalRaster(activity, indices, elapsedMs) {
  return (activity?.bins || [])
    .filter(bin => Number.isFinite(bin.at_ms) && bin.at_ms <= elapsedMs)
    .map(bin => ({at_ms: bin.at_ms, values: rasterForBin(bin, indices)}));
}

export function hudForBin(bin, indices) {
  if (!bin) return {activeNeuronCount: null, spikesPerSecond: null, raster: null};
  return {
    activeNeuronCount: activeNeuronCount(bin),
    spikesPerSecond: spikesPerSecond(bin),
    raster: rasterForBin(bin, indices),
  };
}

export function hudLabel({status = 'ready', playing = false, phase = 'loading', hasBin = false} = {}) {
  if (status === 'loading') return 'Loading recorded activity';
  if (status === 'error') return 'Activity unavailable';
  if (status === 'paused') return `Paused · ${PHASE_LABELS[phase] || 'recorded run'}`;
  if (status === 'complete') return 'Complete · measured run';
  if (!playing) return 'Ready · press Play';
  if (phase === 'execution') return 'Waiting · OpenCode is responding';
  return hasBin ? 'Measured activity' : `Waiting · ${PHASE_LABELS[phase] || 'recorded activity'}`;
}

export function formatMetric(value, suffix = '') {
  if (!Number.isFinite(value)) return '—';
  return `${Math.round(value).toLocaleString('en-US')}${suffix}`;
}
