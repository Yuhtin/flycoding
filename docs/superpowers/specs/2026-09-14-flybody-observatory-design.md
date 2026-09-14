# Flybody observatory and English presentation

User request: make README/dashboard English and make the actual flybody visibly move as if working at Codex. This supersedes the original presentation decision to use a static schematic. Existing measured pilot remains unchanged.

## Experience

A large interactive 3D flybody specimen and the actual Codex terminal share the first screen. A dark restrained lab/workbench scene highlights the anatomically detailed red eyes, six articulated legs, antennae, abdomen and wings. The fly moves gently at rest and actively during work; users can orbit/zoom, pause motion, and replay the saved pilot. English controls, actions, status, accessible labels and README serve an international audience. Reduced-motion and WebGL-unavailable cases remain usable.

## Body boundary

Use TuragaLab/flybody at `d015e9bfe441bd90ae431bac24c55cb74bdbce26`, retaining Apache-2.0 attribution. Export its actual meshes and articulated poses with MuJoCo into a compact GLB and reusable animation data for a local Three.js viewer. No substitute insect illustration and no remote CDN at dashboard runtime. Geometry simplification is allowed and documented. Motion is explicitly a procedural visualization of session state, not a learned locomotion policy or a new neural-control result. It must visibly articulate legs/antennae/wings, rather than merely spin a rigid model. Default viewing requires neither MuJoCo nor a body-training stack. A reproducible optional exporter pins its dependencies, source revision and artifact hashes.

Viewer interface: browser module `body-view.js` exports `createBodyView(container, options)` returning `{setState({mode, action, leftHz, rightHz}), setPaused(boolean), dispose()}`. Modes are `idle`, `working`, `success`, `failure`. The module owns its rendering loop/resize/orbit handling and uses local assets; the dashboard owns session/replay truth. During completion the fly settles into idle after a brief feedback animation. On reduced-motion, default to a static pose with an explicit animate control.

## English and record integrity

Translate README, public results explanations, dashboard and CLI copy. Future selected prompts are English equivalents of the same three actions. Historical snapshots, neural traces, raw events, tests, hashes and nine reservations are immutable. Display English translations of the three recorded prompts and any curated historical agent-message translations with an explicit original/translation indicator; raw original JSON remains available. Unknown transcript text must remain original, never be silently replaced or fabricated.

## Read-only demo and replay

Add `flycodex serve --demo` to serve a bundled sanitized snapshot derived solely from the completed genuine pilot and its original18PNG inputs. No credentials, session IDs, home paths, checkpoints or runtime writer controls are bundled. Include enough true command/agent output to show the recorded fix/test outcome; preserve source text identity for translation. Live mode continues reading an explicitly chosen run directory. A Replay button sequentially presents the recorded turns on a compressed presentation timeline and drives body work/feedback modes; always label this `Condensed replay` and never imply real-time Codex execution. Pause/reset/history selection are deterministic; replay cannot call Codex or alter source records/reservations.

## Delivery and validation

Test serving allowlists, unknown paths, installed asset packaging, replay state transitions, history/evaluation association and motion controls with fixtures. Check actual 3D assets against the pinned source and MuJoCo pose results; visually inspect rendered anatomy and motion in fresh Chrome at desktop/mobile widths. Preserve existing neural and transport tests. Capture an English screenshot and a short MP4 for the user's Twitter post from the labeled real-record replay. Update the existing public repository after verification. Do not make new real Codex calls or post to Twitter.
