# Actual flybody model and procedural animation

The model is derived from the 85 visual OBJ meshes referenced by
[`fruitfly.xml`](https://github.com/TuragaLab/flybody/blob/d015e9bfe441bd90ae431bac24c55cb74bdbce26/flybody/fruitfly/assets/fruitfly.xml)
in TuragaLab/flybody revision `d015e9bfe441bd90ae431bac24c55cb74bdbce26`.
The original Apache-2.0 license is retained as `LICENSE.flybody`. Each of the
87 downloaded source files (XML, meshes, license) has a SHA-256 and byte length
in `sources.lock.json`; `provenance.json` records derived artifact hashes.

The geometry is the actual flybody, including eyes, ocelli, bristles, antennae,
segmented abdomen, six articulated legs, claws, wing veins and membranes.
Collision geoms, sites, lights, cameras, fluid and inertial proxy geoms are not
exported. Original named materials and RGBA values are preserved. GLB materials
use a documented presentation roughness of 0.46 (opaque) and 0.28 (membrane),
zero metalness, and double-sided rendering. Wing membranes retain alpha 0.4.

MuJoCo compiles the source scale and mesh centering/orientation. We export its
compiled `mesh_vert` / `mesh_face` arrays, attaching each mesh with the compiled
`geom_pos` / `geom_quat` under its original body. Exact duplicate vertices are
merged separately inside each named material component, then quadric-error
simplification distributes a 95,000-triangle target proportionally, keeping at
least 80 triangles where available. The hard budget is 120,000 triangles.
Unreferenced vertices are removed and area-weighted normals regenerated.
The final model contains **95,564 triangles**, down from 272,550, with all
85 visual components retained. It is 2,423,588 bytes; animation is 956,222 bytes.

## Motion conventions

**This is procedural MuJoCo forward kinematics, not learned locomotion.**
It does not run a physics rollout, training checkpoint, neural policy, or Codex.
The source XML allocates one keyframe slot but contains no authored `<keyframe>`
poses. Starting with compiled `qpos0`, the exporter authors bounded hinge-angle
waveforms and a partly folded wing pose. Each limited joint is clamped to the
compiled source range before `mj_forward` computes articulated transforms.

`motion.json` has four looping clips (`idle`, `working`, `success`, `failure`),
48 samples each. It includes source joint limits and every sample's `qpos` for
auditing. `bodies` lists original names and parent indices (-1 means world).
Each frame is seven numbers per body: parent-local XYZ translation followed by
XYZW quaternion. Source coordinates are Z-up, in centimeters. The browser keeps
Z-up and scales the model by 14 for presentation; this is not a physical scale
claim. Linear position interpolation and quaternion spherical interpolation
join samples; exponential blending softens mode transitions. Interpolated
transforms are a rendering approximation between validated MuJoCo samples.

Working visibly articulates head, antennae, wings, abdomen and leg joints.
Success nods; failure briefly shakes the head; both settle to idle after their
clip duration. This movement illustrates session state and is not evidence of
learned motor behavior. `action`, `leftHz` and `rightHz` are accepted as session
metadata; the browser does not interpret the rates as a new body-control policy.

## Rebuilding and checking

From the repository root:

```sh
uv run tools/export_flybody.py
uv run tools/export_flybody.py --check
node tools/build_body_view.mjs
uv run pytest -q tests/test_body_assets.py
```

The exporter script pins MuJoCo 3.3.7, NumPy 2.3.3 and fast-simplification
0.1.12 via PEP 723. Sources download only into ignored `build/flybody-source`,
and every file is verified against the committed source lock before use.
`--cache PATH` selects another ignored cache. The explicit `--write-source-lock`
flag bootstraps a deliberately reviewed revision; do not use it for a normal
rebuild. `--check` verifies all 192 samples against freshly compiled MuJoCo and
checks packaged hashes without changing the geometry or motion assets.
Results were byte-for-byte reproduced with these dependencies on macOS arm64;
numerical mesh simplification may differ on other platforms.

The optional Node build runs `npm ci` with committed integrity hashes and pins
Three.js 0.180.0 / esbuild 0.25.10. Its cache defaults to ignored
`build/body-view-deps`; `FLYCODEX_BODY_BUILD_CACHE` overrides that directory.
The checked-in `body-view.js` bundles the viewer, Three.js, GLTFLoader and
OrbitControls. The MIT license is in `LICENSE.three`. Normal Python installation
and browser viewing do not install npm dependencies, MuJoCo or exporter tools.
All browser requests are local; no CDN is used.

## Browser contract

Import `createBodyView` from `/body-view.js`, call it with a container that has
an explicit height and `position: relative`, and optionally pass
`{onStatus(message) { ... }}`. It returns:

- `setState({mode, action, leftHz, rightHz})`: modes are idle, working, success,
  failure. State may be supplied before model loading finishes.
- `setPaused(boolean)`: freezes body animation; orbit and zoom still work.
  Reduced-motion users start paused; an explicit animate control may resume it.
- `dispose()`: cancels requests/animation and releases event listeners,
  observer, controls, geometries, materials and renderer resources.

The module owns its canvas, resize/orbit/zoom behavior and rendering loop.
The canvas has an accessible description and is keyboard focusable; plus and
minus zoom. Load and WebGL failures produce a visible English status and invoke
`onStatus`. The dashboard remains responsible for session truth and pause UI.
`routes.json` lists the exact static allowlist and MIME types; only the module,
GLB and motion JSON are requested at runtime.

Implementation references:
[MuJoCo model/data arrays](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html),
[Three.js GLTFLoader](https://threejs.org/docs/#examples/en/loaders/GLTFLoader),
[glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html).
