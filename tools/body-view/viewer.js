import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/** Actual flybody geometry with authored MuJoCo poses; never a locomotion policy. */
export function createBodyView(container, options = {}) {
  const status = (message) => options.onStatus?.(message);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reducedMotion.matches;
  let disposed = false;
  let state = { mode: 'idle', action: '', leftHz: 0, rightHz: 0 };
  let motion, nodes, model, frameId, resizeObserver, controls, renderer;
  let clipTime = 0, feedbackTime = 0, previousTime = 0;
  const abort = new AbortController();
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.01, 100);
  camera.up.set(0, 0, 1);
  const destination = new THREE.Quaternion();
  const next = new THREE.Quaternion();
  const targetPosition = new THREE.Vector3();
  const warning = document.createElement('p');
  warning.setAttribute('role', 'status');
  warning.style.cssText = 'position:absolute;inset:40% 24px auto;text-align:center;color:#c6c9c5;font:14px/1.6 system-ui';
  warning.hidden = true;
  container.append(warning);

  function fail(message) {
    if (disposed) return;
    warning.textContent = message;
    warning.hidden = false;
    status(message);
  }

  function setState(update = {}) {
    if (disposed) return;
    const requested = ['idle', 'working', 'success', 'failure'].includes(update.mode) ? update.mode : state.mode;
    if (requested !== state.mode) {
      clipTime = 0;
      feedbackTime = 0;
    }
    state = { ...state, ...update, mode: requested };
  }

  function setPaused(value) {
    if (disposed) return;
    paused = Boolean(value);
    if (renderer) renderer.domElement.dataset.paused = String(paused);
  }

  function freeScene(object) {
    object.traverse((child) => {
      child.geometry?.dispose();
      for (const material of Array.isArray(child.material) ? child.material : [child.material]) material?.dispose();
    });
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    abort.abort();
    cancelAnimationFrame(frameId);
    resizeObserver?.disconnect();
    controls?.dispose();
    reducedMotion.removeEventListener('change', onReducedMotion);
    freeScene(scene);
    if (renderer) {
      renderer.domElement.removeEventListener('keydown', onKey);
      renderer.domElement.removeEventListener('webglcontextlost', onContextLost);
      renderer.dispose();
      renderer.domElement.remove();
    }
    warning.remove();
  }

  function onReducedMotion(event) { if (event.matches) setPaused(true); }
  function onContextLost(event) {
    event.preventDefault();
    setPaused(true);
    fail('3D rendering was interrupted. Reload to restore the flybody view. Session data remains available.');
  }
  function onKey(event) {
    if (event.key === '+' || event.key === '=' || event.key === '-') {
      camera.position.sub(controls.target).multiplyScalar(event.key === '-' ? 1.12 : 0.89).add(controls.target);
      controls.update();
      event.preventDefault();
    }
  }

  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.95;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:none;outline-offset:-4px';
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.setAttribute('aria-label', 'Interactive articulated flybody model. Drag to orbit; scroll or use plus and minus to zoom. Procedural session animation, not learned locomotion.');
    renderer.domElement.tabIndex = 0;
    renderer.domElement.dataset.paused = String(paused);
    renderer.domElement.addEventListener('keydown', onKey);
    renderer.domElement.addEventListener('webglcontextlost', onContextLost);
    container.append(renderer.domElement);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 1.8;
    controls.maxDistance = 16;
    controls.maxPolarAngle = Math.PI * 0.88;
    reducedMotion.addEventListener('change', onReducedMotion);
    const fill = new THREE.HemisphereLight(0xe2efff, 0x694124, 1.6);
    fill.up.set(0, 0, 1);
    scene.add(fill);
    for (const [color, intensity, position] of [
      [0xfff0da, 2.8, [4, -3, 6]], [0xb5dcff, 2.1, [-3, 4, 4]], [0xffffff, 1.0, [2, 4, 1]],
    ]) {
      const light = new THREE.DirectionalLight(color, intensity);
      light.position.set(...position);
      scene.add(light);
    }
    resizeObserver = new ResizeObserver(() => {
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height, false);
      if (model) {
        const adjustment = Math.max(1, 0.82 / (width / height)) / Math.max(1, 0.82 / camera.aspect);
        camera.position.sub(controls.target).multiplyScalar(adjustment).add(controls.target);
      }
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    });
    resizeObserver.observe(container);
    status(paused ? 'Loading flybody · reduced motion' : 'Loading flybody');
  } catch {
    fail('3D view unavailable: WebGL could not start. Session data and replay remain available.');
    return { setState, setPaused, dispose };
  }

  async function load() {
    const [geometryResponse, motionResponse] = await Promise.all([
      fetch('/body/flybody.glb', { signal: abort.signal }), fetch('/body/motion.json', { signal: abort.signal }),
    ]);
    if (!geometryResponse.ok || !motionResponse.ok) throw new Error('Flybody assets could not load');
    const [buffer, poses] = await Promise.all([geometryResponse.arrayBuffer(), motionResponse.json()]);
    const gltf = await new GLTFLoader().parseAsync(buffer, '/body/');
    if (disposed) { freeScene(gltf.scene); return; }
    motion = poses;
    model = gltf.scene;
    model.scale.setScalar(14);
    scene.add(model);
    nodes = motion.bodies.map((body) => {
      const node = model.getObjectByName(body.name);
      if (!node) throw new Error('Articulated body node missing');
      return node;
    });
    // Fit the complete articulated motion envelope, including raised wing tips.
    const bounds = new THREE.Box3();
    const sampleBounds = new THREE.Box3();
    function applyFrame(frame) {
      nodes.forEach((node, index) => {
        node.position.fromArray(frame, index * 7);
        node.quaternion.fromArray(frame, index * 7 + 3);
      });
    }
    for (const clip of Object.values(motion.clips)) {
      for (const frame of clip.frames) {
        applyFrame(frame);
        bounds.union(sampleBounds.setFromObject(model));
      }
    }
    applyFrame(motion.clips.idle.frames[0]);
    const center = bounds.getCenter(new THREE.Vector3());
    const radius = bounds.getBoundingSphere(new THREE.Sphere()).radius;
    controls.target.copy(center);
    const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.08 * Math.max(1, 0.82 / camera.aspect);
    camera.position.copy(center).add(new THREE.Vector3(0.85, -1.35, 0.85).normalize().multiplyScalar(distance));
    controls.update();
    const platform = new THREE.Mesh(new THREE.CircleGeometry(radius * 1.3, 80),
      new THREE.MeshStandardMaterial({ color: 0x182023, roughness: 0.94, transparent: true, opacity: 0.42, side: THREE.DoubleSide }));
    platform.position.set(center.x, center.y, bounds.min.z - 0.10);
    scene.add(platform);
    const ring = new THREE.Mesh(new THREE.RingGeometry(radius * 1.10, radius * 1.105, 128),
      new THREE.MeshBasicMaterial({ color: 0x526a65, transparent: true, opacity: 0.25, side: THREE.DoubleSide }));
    ring.position.copy(platform.position);
    ring.position.z += 0.001;
    scene.add(ring);
    renderer.domElement.dataset.ready = 'true';
    status(paused ? 'Flybody ready · motion paused' : 'Flybody ready · procedural motion');
  }

  function animate(timestamp) {
    if (disposed) return;
    frameId = requestAnimationFrame(animate);
    const elapsed = previousTime ? Math.min((timestamp - previousTime) / 1000, 0.06) : 0;
    previousTime = timestamp;
    if (motion && !paused) {
      clipTime += elapsed;
      if (state.mode === 'success' || state.mode === 'failure') {
        feedbackTime += elapsed;
        if (feedbackTime > motion.clips[state.mode].duration) { state.mode = 'idle'; clipTime = 0; }
      }
      const clip = motion.clips[state.mode];
      const sample = (clipTime % clip.duration) / clip.duration * clip.frames.length;
      const first = clip.frames[Math.floor(sample)];
      const second = clip.frames[(Math.floor(sample) + 1) % clip.frames.length];
      const fraction = sample % 1;
      const transition = 1 - Math.exp(-elapsed * 12);
      nodes.forEach((node, index) => {
        const offset = index * 7;
        for (let axis = 0; axis < 3; axis++) targetPosition.setComponent(axis, THREE.MathUtils.lerp(first[offset + axis], second[offset + axis], fraction));
        node.position.lerp(targetPosition, transition);
        destination.fromArray(first, offset + 3);
        next.fromArray(second, offset + 3);
        destination.slerp(next, fraction);
        node.quaternion.slerp(destination, transition);
      });
    }
    controls.update();
    renderer.render(scene, camera);
  }

  load().catch((error) => {
    if (error.name !== 'AbortError') fail('The flybody model could not load. Reload to retry. Session data and replay remain available.');
  });
  frameId = requestAnimationFrame(animate);
  return { setState, setPaused, dispose };
}
