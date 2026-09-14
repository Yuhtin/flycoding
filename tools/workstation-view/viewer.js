import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { CSS3DObject, CSS3DRenderer } from 'three/addons/renderers/CSS3DRenderer.js';

/**
 * A fixed, immersive desk scene around the unchanged recorded flybody.
 * The monitor transcript is a real CSS3D object placed on the modeled screen.
 */
export function createWorkstationView(container, options = {}) {
  const status = (message) => options.onStatus?.(message);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reducedMotion.matches;
  let disposed = false;
  let state = { mode: 'idle', action: '' };
  let motion = null;
  let nodes = null;
  let model = null;
  let frameId = null;
  let resizeObserver = null;
  let previousTime = 0;
  let clipTime = 0;
  let feedbackTime = 0;
  let renderer = null;
  let cssRenderer = null;
  let screenObject = null;
  let monitorParts = null;
  let keyboardGroup = null;
  let desktopModelPosition = null;
  let desktopCameraTarget = null;
  let narrowViewport = false;
  let typingLegs = null;
  const abort = new AbortController();

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(29, 1, 0.1, 100);
  camera.up.set(0, 0, 1);
  camera.position.set(7.0, -11.0, 6.8);
  const cameraTarget = new THREE.Vector3(0.2, 0.35, 2.35);

  const colors = {
    desk: 0x17191d,
    deskEdge: 0x282a31,
    black: 0x080b10,
    screenFrame: 0x121820,
    keyboard: 0x222a34,
    key: 0x59616a,
    cyan: 0x53d7e3,
    magenta: 0xff4ca4,
    window: 0x0b1625,
  };

  function material(color, options = {}) {
    return new THREE.MeshStandardMaterial({color, roughness: 0.72, metalness: 0.16, ...options});
  }

  function box(name, size, position, color, options = {}) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material(color, options));
    mesh.name = name;
    mesh.position.set(...position);
    scene.add(mesh);
    return mesh;
  }

  function addDesk() {
    box('desk-top', [12, 6.4, 0.42], [0, 0, 0], colors.desk, {roughness: 0.88});
    box('desk-front-edge', [12, 0.12, 0.52], [0, -3.16, -0.02], colors.deskEdge, {roughness: 0.84});
    for (const x of [-5.1, 5.1]) box('desk-leg', [0.42, 0.42, 3.4], [x, 0, -1.9], colors.black, {roughness: 0.92});
    const mat = material(colors.window, {roughness: 0.48, metalness: 0.08, emissive: 0x07101c, emissiveIntensity: 0.6});
    const windowPanel = new THREE.Mesh(new THREE.BoxGeometry(18, 0.12, 8.5), mat);
    windowPanel.position.set(0, 3.9, 4.65);
    scene.add(windowPanel);
    for (const x of [-6.0, -1.2, 3.8]) box('window-mullion', [0.06, 0.16, 8.5], [x, 3.78, 4.65], colors.cyan, {emissive: colors.cyan, emissiveIntensity: 1.8});
    box('window-sill', [18.0, 0.22, 0.12], [0, 3.76, 1.1], colors.magenta, {emissive: colors.magenta, emissiveIntensity: 1.1});
    for (const [x, width, height, lights] of [[-7.0, 2.0, 4.6, 3], [-4.4, 2.5, 3.4, 4], [-1.4, 1.8, 5.8, 3], [1.1, 2.2, 3.7, 4], [4.0, 2.8, 5.2, 5], [7.2, 1.9, 3.2, 3]]) {
      box('city-building', [width, 0.35, height], [x, 3.55, 1.1 + height / 2], colors.black, {roughness: 0.94, emissive: 0x03070e, emissiveIntensity: 0.7});
      for (let index = 0; index < lights; index += 1) {
        const lightZ = 1.5 + (index % 3) * 0.72;
        const lightX = x - width * 0.28 + (Math.floor(index / 3) % 2) * width * 0.52;
        box('city-light', [0.12, 0.05, 0.18], [lightX, 3.34, lightZ], index % 2 ? colors.cyan : colors.magenta, {emissive: index % 2 ? colors.cyan : colors.magenta, emissiveIntensity: 2.0});
      }
    }
  }

  function addMonitor() {
    const monitorX = 0.15;
    const monitorY = 1.0;
    const monitorZ = 2.95;
    const screenWidth = 5.35;
    const screenHeight = 3.56;
    const frameDepth = 0.34;
    const shell = box('monitor-shell', [screenWidth, frameDepth, screenHeight], [monitorX, monitorY, monitorZ], colors.screenFrame, {roughness: 0.42, metalness: 0.45});
    const bezel = box('monitor-bezel', [screenWidth - 0.24, 0.06, screenHeight - 0.24], [monitorX, monitorY - 0.2, monitorZ], colors.black, {roughness: 0.28, metalness: 0.25});
    const stand = box('monitor-stand', [0.35, 0.38, 1.35], [monitorX, monitorY + 0.02, 1.08], colors.screenFrame, {roughness: 0.5, metalness: 0.48});
    const foot = box('monitor-foot', [2.05, 1.18, 0.16], [monitorX, monitorY - 0.05, 0.39], colors.screenFrame, {roughness: 0.45, metalness: 0.42});
    const led = box('monitor-led', [0.32, 0.04, 0.025], [monitorX, monitorY - 0.23, 1.34], colors.cyan, {emissive: colors.cyan, emissiveIntensity: 2.2});
    monitorParts = {shell, bezel, stand, foot, led, monitorX, monitorY, monitorZ, frameDepth};

    const element = options.screenElement;
    if (!element) return;
    element.style.width = '960px';
    element.style.height = '640px';
    element.style.pointerEvents = 'auto';
    screenObject = new CSS3DObject(element);
    screenObject.position.set(monitorX, monitorY - frameDepth / 2 - 0.025, monitorZ);
    screenObject.rotation.x = Math.PI / 2;
    screenObject.scale.setScalar((screenWidth - 0.24) / 960);
    scene.add(screenObject);
  }

  function addKeyboard() {
    const keyboard = new THREE.Group();
    keyboardGroup = keyboard;
    keyboard.position.set(0.15, -1.34, 0.3);
    keyboard.rotation.z = -0.035;
    keyboard.add(new THREE.Mesh(new THREE.BoxGeometry(3.9, 1.55, 0.16), material(colors.keyboard, {roughness: 0.55, metalness: 0.25})));
    const keyMaterial = material(colors.key, {roughness: 0.66, metalness: 0.12});
    for (let row = 0; row < 4; row += 1) {
      const columns = row === 3 ? 9 : 12;
      const width = row === 3 ? 0.28 : 0.22;
      for (let column = 0; column < columns; column += 1) {
        const key = new THREE.Mesh(new THREE.BoxGeometry(width, 0.23, 0.055), keyMaterial);
        key.position.set((column - (columns - 1) / 2) * 0.29, (row - 1.5) * 0.3, 0.12);
        keyboard.add(key);
      }
    }
    scene.add(keyboard);
    box('mouse', [0.58, 0.9, 0.17], [4.05, -1.18, 0.4], colors.keyboard, {roughness: 0.5, metalness: 0.25});
  }

  function applyViewportLayout() {
    if (monitorParts) {
      const {shell, bezel, stand, foot, led, monitorX, monitorY, monitorZ, frameDepth} = monitorParts;
      const x = narrowViewport ? 0 : monitorX;
      const raised = narrowViewport ? 1.5 : 1.3;
      shell.position.set(x, monitorY, monitorZ + raised);
      bezel.position.set(x, monitorY - 0.2, monitorZ + raised);
      stand.position.set(x, monitorY + 0.02, raised ? 1.78 : 1.08);
      stand.scale.z = raised ? 2.2 : 1;
      foot.position.set(x, monitorY - 0.05, 0.39);
      led.position.set(x, monitorY - 0.23, monitorZ + raised - 1.61);
      if (screenObject) screenObject.position.set(x, monitorY - frameDepth / 2 - 0.025, monitorZ + raised);
    }
    if (keyboardGroup) keyboardGroup.position.set(narrowViewport ? 0 : 0.15, narrowViewport ? -1.3 : -1.34, 0.3);
    if (model && desktopModelPosition) model.position.set(narrowViewport ? 0.15 : desktopModelPosition.x, narrowViewport ? -2.5 : desktopModelPosition.y, desktopModelPosition.z);
  }

  function applyCameraFraming() {
    if (narrowViewport) cameraTarget.set(0, 0, 3);
    else if (desktopCameraTarget) cameraTarget.copy(desktopCameraTarget);
    const basePosition = narrowViewport ? new THREE.Vector3(0, -23.0, 8.0) : new THREE.Vector3(7.0, -11.0, 6.8);
    const distanceScale = narrowViewport ? 1 : 1.22 * Math.max(1, 0.9 / camera.aspect);
    camera.position.copy(basePosition).sub(cameraTarget).multiplyScalar(distanceScale).add(cameraTarget);
    camera.updateProjectionMatrix();
  }

  function freeScene(object) {
    object.traverse((child) => {
      child.geometry?.dispose();
      for (const entry of Array.isArray(child.material) ? child.material : [child.material]) entry?.dispose();
    });
  }

  function requestRender() {
    if (!disposed && frameId === null) frameId = requestAnimationFrame(animate);
  }

  function fail(message) {
    if (disposed) return;
    status(message);
  }

  function setState(update = {}) {
    if (disposed) return;
    const mode = ['idle', 'working', 'success', 'failure'].includes(update.mode) ? update.mode : state.mode;
    if (mode !== state.mode) { clipTime = 0; feedbackTime = 0; }
    state = {...state, ...update, mode};
    requestRender();
  }

  function setPaused(value) {
    if (disposed) return;
    const requested = Boolean(value);
    if (requested === paused) return;
    paused = requested;
    previousTime = 0;
    if (renderer) renderer.domElement.dataset.paused = String(paused);
    requestRender();
  }

  function onReducedMotion(event) { if (event.matches) setPaused(true); }

  function dispose() {
    if (disposed) return;
    disposed = true;
    abort.abort();
    if (frameId !== null) cancelAnimationFrame(frameId);
    resizeObserver?.disconnect();
    reducedMotion.removeEventListener('change', onReducedMotion);
    freeScene(scene);
    if (renderer) { renderer.dispose(); renderer.domElement.remove(); }
    if (cssRenderer) cssRenderer.domElement.remove();
    screenObject?.removeFromParent();
  }

  function applyFrame(frame) {
    nodes?.forEach((node, index) => {
      const offset = index * 7;
      node.position.fromArray(frame, offset);
      node.quaternion.fromArray(frame, offset + 3);
    });
  }

  function applyTypingMotion(_seconds, typing = {}) {
    if (!typingLegs) return;
    for (const [side, chain] of typingLegs.entries()) {
      const requestedLift = side === 0 ? typing.left : typing.right;
      const lift = Number.isFinite(requestedLift) ? Math.max(0, Math.min(1, requestedLift)) : 0;
      const strength = 0.8 + 0.6 * lift;
      // The baseline keeps both claws on the key plane between cues. Audio
      // supplies a smooth 180 ms pre-cue lift in [0, 1], with zero at contact.
      const angles = [0.018 * strength, -0.108 * strength, 0.158 * strength, -0.117 * strength, 0.063 * strength, -0.027 * strength];
      chain.forEach((node, index) => {
        if (!node) return;
        const rotation = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), angles[index]);
        node.quaternion.multiply(rotation);
      });
    }
  }

  function animate(timestamp) {
    frameId = null;
    if (disposed) return;
    const elapsed = previousTime ? Math.min((timestamp - previousTime) / 1000, 0.06) : 0;
    previousTime = timestamp;
    if (motion && model && !paused) {
      clipTime += elapsed;
      if (state.mode === 'success' || state.mode === 'failure') {
        feedbackTime += elapsed;
        if (feedbackTime > motion.clips[state.mode].duration) { state.mode = 'idle'; clipTime = 0; }
      }
      const clip = motion.clips[state.mode] || motion.clips.idle;
      const sample = (clipTime % clip.duration) / clip.duration * clip.frames.length;
      const first = clip.frames[Math.floor(sample)];
      const second = clip.frames[(Math.floor(sample) + 1) % clip.frames.length];
      const fraction = sample % 1;
      nodes.forEach((node, index) => {
        const offset = index * 7;
        for (let axis = 0; axis < 3; axis += 1) node.position.setComponent(axis, THREE.MathUtils.lerp(first[offset + axis], second[offset + axis], fraction));
        const quaternion = new THREE.Quaternion().fromArray(first, offset + 3);
        const nextQuaternion = new THREE.Quaternion().fromArray(second, offset + 3);
        quaternion.slerp(nextQuaternion, fraction);
        node.quaternion.copy(quaternion);
      });
      applyTypingMotion(Number.isFinite(state.elapsedMs) ? state.elapsedMs / 1000 : clipTime, state.mode === 'working' ? state.typing : undefined);
    }
    camera.lookAt(cameraTarget);
    renderer?.render(scene, camera);
    cssRenderer?.render(scene, camera);
    if (!paused && motion) requestRender();
    else previousTime = 0;
  }

  try {
    renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'low-power'});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 0.75));
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.9;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.cssText = 'position:absolute;inset:0;display:block;width:100%;height:100%;touch-action:none;outline:none;image-rendering:pixelated';
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.setAttribute('aria-label', 'Immersive recorded fly workstation with physical keyboard, monitor, and flybody.');
    renderer.domElement.dataset.paused = String(paused);
    container.append(renderer.domElement);
    cssRenderer = new CSS3DRenderer();
    cssRenderer.setSize(1, 1);
    cssRenderer.domElement.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:hidden';
    container.append(cssRenderer.domElement);
    addDesk();
    addMonitor();
    addKeyboard();
    const ambient = new THREE.HemisphereLight(0x9fc7e8, 0x130e19, 1.65);
    ambient.position.set(0, 0, 8);
    scene.add(ambient);
    for (const [color, intensity, position] of [[0x9cdfff, 4.1, [-5, -4, 8]], [0xff4cb0, 3.2, [5, 3, 5]], [0xfff1ce, 2.4, [2, -4, 6]]]) {
      const light = new THREE.DirectionalLight(color, intensity);
      light.position.set(...position);
      scene.add(light);
    }
    resizeObserver = new ResizeObserver(() => {
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height, false);
      cssRenderer.setSize(width, height);
      camera.aspect = width / height;
      narrowViewport = camera.aspect < 0.8;
      applyViewportLayout();
      applyCameraFraming();
      requestRender();
    });
    resizeObserver.observe(container);
    reducedMotion.addEventListener('change', onReducedMotion);
    status(paused ? 'Loading flybody · reduced motion' : 'Loading flybody');
  } catch {
    fail('Workstation view unavailable: WebGL could not start. Recorded replay remains available.');
    return {setState, setPaused, dispose};
  }

  async function load() {
    const [geometryResponse, motionResponse] = await Promise.all([
      fetch('/body/flybody.glb', {signal: abort.signal}),
      fetch('/body/motion.json', {signal: abort.signal}),
    ]);
    if (!geometryResponse.ok || !motionResponse.ok) throw new Error('Flybody assets could not load');
    const [buffer, poses] = await Promise.all([geometryResponse.arrayBuffer(), motionResponse.json()]);
    const gltf = await new GLTFLoader().parseAsync(buffer, '/body/');
    if (disposed) { freeScene(gltf.scene); return; }
    motion = poses;
    const ground = motion.ground;
    if (!ground || !Number.isFinite(ground.source_z) || !Number.isFinite(ground.clearance)) throw new Error('Ground contact metadata is missing');
    model = gltf.scene;
    model.scale.setScalar(15);
    model.position.set(0.15, -2.7, 0.0);
    model.rotation.z = Math.PI / 2;
    scene.add(model);
    nodes = motion.bodies.map((body) => {
      const node = model.getObjectByName(body.name);
      if (!node) throw new Error('Articulated body node missing');
      return node;
    });
    typingLegs = [
      ['coxa_T1_left', 'femur_T1_left', 'tibia_T1_left', 'tarsus_T1_left', 'tarsus2_T1_left', 'tarsus3_T1_left'].map((name) => model.getObjectByName(name)),
      ['coxa_T1_right', 'femur_T1_right', 'tibia_T1_right', 'tarsus_T1_right', 'tarsus2_T1_right', 'tarsus3_T1_right'].map((name) => model.getObjectByName(name)),
    ];
    applyFrame(motion.clips.idle.frames[0]);
    applyTypingMotion(0, state.typing);
    const bounds = new THREE.Box3().setFromObject(model);
    const floorZ = model.scale.z * (ground.source_z - ground.clearance) + model.position.z;
    model.position.z += 0.23 - floorZ;
    desktopModelPosition = model.position.clone();
    applyViewportLayout();
    const center = bounds.getCenter(new THREE.Vector3());
    desktopCameraTarget = new THREE.Vector3(0.25, 0.35, Math.max(2.45, center.z + 1.0));
    applyCameraFraming();
    renderer.domElement.dataset.ready = 'true';
    status(paused ? 'Flybody ready · motion paused' : 'Flybody ready · procedural motion');
    options.onReady?.({model, scene, camera});
    requestRender();
  }

  load().catch((error) => {
    if (error.name !== 'AbortError') fail('The flybody model could not load. Reload to retry. Recorded replay remains available.');
  });
  requestRender();
  return {setState, setPaused, dispose};
}
