# HYPERFRAMES_INTEGRATION — how full rendering works
> 🗄️ Historical implementation report (2026-08-22 visual upgrade mission). For current architecture see [VIDEO_FLOW_ARCHITECTURE.md](../VIDEO_FLOW_ARCHITECTURE.md).

## Path

`NarovaRunner.render()` (video_flow_engine/narova_runner.py) runs the vendored
CLI in the job's `narova/` sandbox:

```
node third_party/narova/tool/bin/narova.js synth   --project <dir> --renderer hyperframes
node .../narova.js compose --project <dir> --renderer hyperframes
node .../narova.js build   --project <dir> --renderer hyperframes --reuse --fps 30 --quality standard --verify-motion
```

- `synth` — Piper narration per scene (`out/audio/*.wav` + `full.wav`,
  sentence takes), SRT/VTT cues with word timing.
- `compose` — writes the HyperFrames HTML project: `out/hf-<job>/index.html`
  plus one self-contained span per scene under `spans/scene-*`
  (index.html, style.css, vendored `gsap.min.js` / `three.core.js`,
  narration.wav).
- `build` — invokes HyperFrames (`hf.js` → `npx --yes hyperframes@<PIN>`,
  pinned for reproducibility) which renders each span in Chrome for Testing at
  30 fps with streaming encode, reusing cached spans via `--reuse`, then
  assembles spans + full audio into `out/video.mp4`. `--verify-motion` fails
  spans that render static.
- The engine then FFmpeg-normalizes to the existing contract: 1920x1080
  H.264 CRF 20, AAC 192k, yuv420p, +faststart → `<job>/video.mp4`, and copies
  `captions.srt/vtt` into `<job>/captions/`.

## Scene content contract

Authored scenes are declarative only (mission invariant, enforced by
`validate_no_executable_code` on every payload):

- HTML with Narova motion attributes: `class="reveal"`, `class="cue"
  data-cue="0" data-delay="…"`, `data-draw` (stroke draw-on), `data-count`
  (animated counters), `data-mark`.
- Inline SVG with path data restricted to a whitelist regex
  (`^[MmLlHhVvCcSsQqTtAaZz0-9 ,.\-+eE]*$`).
- Three.js via declarative config consumed by Narova's module-scene runtime —
  never emitted JS.

## Windows integration patch (third_party/narova/tool/src/hf.js)

`npx` on Windows is a batch shim: spawning it directly fails with
`spawn EFTYPE` during capture calibration and frame capture. The patch spawns
`cmd.exe /d /s /c npx …` on Windows (verbatim args off), keeping the direct
spawn elsewhere, with the existing retry for transient registry DNS errors.
Without this, every HyperFrames render dies at "Starting frame capture".

A second environment fault (not a repo change): the cached Chrome for Testing
binary was corrupt and produced `EFTYPE`-style launch failures; reinstalling
the cache restored rendering. First proof build: 6.9 s / 2 scenes.

## Failure handling

- Browser/HyperFrames unavailable → engine logs, reports 48%
  "Browser render unavailable — using portable renderer", and rebuilds via the
  legacy `no-browser` production (old 4-layout output, still correct MP4).
- A failed span build surfaces as `render_failed` with logs in
  `logs/narova.log`; `--reuse` makes retries cheap (only failed spans re-render).
- All subprocesses run under `ProcessManager` (tree cancel on job cancel,
  timeouts raised for long browser builds).
