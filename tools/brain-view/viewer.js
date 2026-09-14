import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const FILTERS = {
  all: () => true,
  brain: entry => !String(entry.superclass || '').startsWith('vnc_'),
  optic: entry => /^(ol_|visual)/.test(String(entry.superclass || '')),
  vnc: entry => String(entry.superclass || '').startsWith('vnc_'),
};

export function createBrainView(container, options = {}) {
  let disposed = false;
  let renderer;
  let controls;
  let resizeObserver;
  let points;
  let metadata = [];
  let manifest;
  let positions;
  let retainedIndices;
  let pointByRetained;
  let colors;
  let baseColors;
  let visibleMask;
  let overlayPoints;
  let overlayKey = '';
  let selectedPoint = -1;
  let fitCenter = null;
  let fitRadius = 1;
  const fitDirection = new THREE.Vector3(0.65, -1.0, 0.75).normalize();
  let currentFilter = 'all';
  let activity = new Map();
  const abort = new AbortController();
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100000);
  const status = message => options.onStatus?.(message);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const warning = document.createElement('p');
  warning.className = 'brain-warning';
  warning.setAttribute('role', 'status');
  warning.hidden = true;
  container.append(warning);

  const fail = message => {
    if (disposed) return;
    warning.textContent = message;
    warning.hidden = false;
    status(message);
  };

  function colorFor(entry, isReadout) {
    if (isReadout) return new THREE.Color(0xd3e9a9);
    const superclass = String(entry?.superclass || '');
    if (superclass.startsWith('vnc_')) return new THREE.Color(0x8ba7ac);
    if (/^(ol_|visual)/.test(superclass)) return new THREE.Color(0x9a8eb8);
    return new THREE.Color(0x9fae9f);
  }

  function render() {
    if (!disposed && renderer) renderer.render(scene, camera);
  }

  function applyColors() {
    if (!colors || !baseColors || !visibleMask) return;
    const max = Math.max(1, ...activity.values());
    for (let point = 0; point < visibleMask.length; point += 1) {
      const retained = retainedIndices[point];
      const entry = metadata[retained] || {};
      const base = baseColors[point];
      const measured = activity.get(retained) || 0;
      const readout = manifest.readout_indices.some(item => item.index === retained);
      const color = measured > 0 ? new THREE.Color(0xffcc72).lerp(new THREE.Color(0xfff2b0), Math.min(1, measured / max)) : base.clone();
      if (readout && measured <= 0) color.copy(new THREE.Color(0xd3e9a9));
      if (!visibleMask[point]) color.multiplyScalar(0.10);
      color.toArray(colors, point * 3);
    }
    points.geometry.attributes.color.needsUpdate = true;
  }

  function applyFilter(filter) {
    currentFilter = FILTERS[filter] ? filter : 'all';
    visibleMask = retainedIndices.map(index => FILTERS[currentFilter](metadata[index] || {}));
    applyColors();
    status(`${currentFilter} anatomy · ${visibleMask.filter(Boolean).length.toLocaleString('en-US')} positioned neurons`);
    render();
  }

  function selectPoint(pointIndex) {
    if (pointIndex < 0 || pointIndex >= retainedIndices.length) return;
    selectedPoint = pointIndex;
    const retained = retainedIndices[pointIndex];
    options.onSelection?.({index: retained, ...(metadata[retained] || {})});
    render();
  }

  function onPointer(event) {
    if (!points || !renderer) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    const raycaster = new THREE.Raycaster();
    raycaster.params.Points.threshold = Math.max(1, camera.position.distanceTo(controls.target) * 0.006);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObject(points)[0];
    if (hit) selectPoint(hit.index);
  }

  function onKey(event) {
    if (!points) return;
    if (event.key === '+' || event.key === '=') {
      camera.position.sub(controls.target).multiplyScalar(0.88).add(controls.target); controls.update(); event.preventDefault();
    } else if (event.key === '-') {
      camera.position.sub(controls.target).multiplyScalar(1.14).add(controls.target); controls.update(); event.preventDefault();
    }
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    abort.abort();
    resizeObserver?.disconnect();
    controls?.removeEventListener('change', render);
    controls?.dispose();
    renderer?.domElement.removeEventListener('pointerup', onPointer);
    renderer?.domElement.removeEventListener('keydown', onKey);
    renderer?.dispose();
    renderer?.domElement.remove();
    points?.geometry.dispose();
    points?.material.dispose();
    overlayPoints?.geometry.dispose();
    overlayPoints?.material.dispose();
    warning.remove();
  }

  try {
    renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'low-power'});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:none;outline-offset:-4px';
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.setAttribute('aria-label', 'Interactive retained CNS neuron anatomy. Drag to orbit; scroll to zoom; plus and minus zoom with keyboard.');
    renderer.domElement.tabIndex = 0;
    renderer.domElement.addEventListener('pointerup', onPointer);
    renderer.domElement.addEventListener('keydown', onKey);
    container.append(renderer.domElement);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = !reducedMotion.matches;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 1;
    controls.maxDistance = 1e9;
    controls.addEventListener('change', render);
    resizeObserver = new ResizeObserver(() => {
      const width = Math.max(1, container.clientWidth), height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      if (fitCenter) {
        const distance = fitRadius / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.35 * Math.max(1, 1 / camera.aspect);
        camera.position.copy(fitCenter).add(fitDirection.clone().multiplyScalar(distance));
        controls.target.copy(fitCenter);
        controls.update();
      }
      render();
    });
    resizeObserver.observe(container);
  } catch {
    fail('3D brain view unavailable: WebGL could not start. Measured readouts remain available.');
    return {setActivity() {}, clearActivity() {}, setFilter() {}, dispose};
  }

  async function load() {
    status('Loading source CNS anatomy…');
    const [manifestResponse, positionResponse, indexResponse, neuronResponse] = await Promise.all([
      fetch('/brain/manifest.json', {signal: abort.signal}),
      fetch('/brain/positions.bin', {signal: abort.signal}),
      fetch('/brain/indices.bin', {signal: abort.signal}),
      fetch('/brain/neurons.json', {signal: abort.signal}),
    ]);
    if (![manifestResponse, positionResponse, indexResponse, neuronResponse].every(response => response.ok)) throw new Error('Anatomy assets could not load');
    [manifest, positions, retainedIndices, metadata] = await Promise.all([
      manifestResponse.json(), positionResponse.arrayBuffer().then(buffer => new Float32Array(buffer)),
      indexResponse.arrayBuffer().then(buffer => new Uint32Array(buffer)), neuronResponse.json(),
    ]);
    pointByRetained = new Int32Array(manifest.total_neurons).fill(-1);
    retainedIndices.forEach((retained, point) => { pointByRetained[retained] = point; });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    colors = new Float32Array(positions.length);
    baseColors = [];
    for (let point = 0; point < retainedIndices.length; point += 1) {
      const color = colorFor(metadata[retainedIndices[point]], manifest.readout_indices.some(item => item.index === retainedIndices[point]));
      baseColors.push(color);
      color.toArray(colors, point * 3);
    }
    visibleMask = retainedIndices.map(() => true);
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    points = new THREE.Points(geometry, new THREE.PointsMaterial({size: 1.8, vertexColors: true, transparent: true, opacity: 0.88, sizeAttenuation: true}));
    scene.add(points);
    const bounds = new THREE.Box3().setFromBufferAttribute(geometry.getAttribute('position'));
    const center = bounds.getCenter(new THREE.Vector3());
    const radius = Math.max(1, bounds.getBoundingSphere(new THREE.Sphere()).radius);
    fitCenter = center.clone(); fitRadius = radius;
    controls.target.copy(center);
    const fitDistance = radius / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.35 * Math.max(1, 1 / camera.aspect);
    camera.position.copy(center).add(fitDirection.clone().multiplyScalar(fitDistance));
    camera.near = Math.max(0.01, radius / 1000); camera.far = radius * 20; camera.updateProjectionMatrix(); controls.update();
    renderer.domElement.dataset.ready = 'true';
    status(`Source CNS ready · ${manifest.positioned_neurons.toLocaleString('en-US')} positioned · ${manifest.missing_neurons.toLocaleString('en-US')} unplaced`);
    options.onReady?.({manifest, metadata, pointByRetained});
    render();
  }

  load().catch(error => { if (error.name !== 'AbortError') fail('Source CNS anatomy could not load. Measured readouts remain available.'); });

  return {
    setFilter(filter) { if (points) applyFilter(filter); },
    setActivity(next = {}) {
      const indices = next.indices || [], counts = next.counts || [];
      const key = `${indices.join(',')}|${counts.join(',')}`;
      if (key === overlayKey) return;
      overlayKey = key;
      activity = new Map();
      const overlayPositions = [], overlayColors = [];
      const max = Math.max(1, ...counts);
      for (let index = 0; index < indices.length; index += 1) {
        const retained = indices[index], point = pointByRetained?.[retained] ?? -1;
        if (point < 0) continue;
        activity.set(retained, counts[index] || 0);
        overlayPositions.push(positions[point * 3], positions[point * 3 + 1], positions[point * 3 + 2]);
        const brightness = 0.65 + 0.35 * Math.min(1, (counts[index] || 0) / max);
        overlayColors.push(1, brightness, 0.25);
      }
      if (overlayPoints) { scene.remove(overlayPoints); overlayPoints.geometry.dispose(); overlayPoints.material.dispose(); overlayPoints = null; }
      if (overlayPositions.length) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(overlayPositions, 3));
        geometry.setAttribute('color', new THREE.Float32BufferAttribute(overlayColors, 3));
        overlayPoints = new THREE.Points(geometry, new THREE.PointsMaterial({size:120, vertexColors:true, transparent:true, opacity:0.95, sizeAttenuation:true, depthWrite:false}));
        scene.add(overlayPoints);
      }
      applyColors(); render();
    },
    clearActivity() {
      if (!activity.size && !overlayPoints) return;
      activity = new Map(); overlayKey = '';
      if (overlayPoints) { scene.remove(overlayPoints); overlayPoints.geometry.dispose(); overlayPoints.material.dispose(); overlayPoints = null; }
      applyColors(); render();
    },
    select(index) { const point = pointByRetained?.[index] ?? -1; if (point >= 0) selectPoint(point); },
    dispose,
  };
}
