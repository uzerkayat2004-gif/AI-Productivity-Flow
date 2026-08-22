# FILES_CHANGED — every file touched for this upgrade
> 🗄️ Historical implementation report (2026-08-22 visual upgrade mission). For current architecture see [VIDEO_FLOW_ARCHITECTURE.md](../VIDEO_FLOW_ARCHITECTURE.md).

Root: `C:\Users\Asus\.gemini\antigravity\scratch\voice-flow` (the running
install). Recovery point: `video-flow-visual-upgrade/engine-pre-upgrade-backup/`
contains the pre-upgrade copies of the engine package.

## VIDEO FLOW ENGINE (`src/voice_flow/video_flow_engine/`)

| File | Change | Why |
|---|---|---|
| `creative_director.py` | NEW (14.4 KB) | storyboard → treatments/metaphors/labels direction payload; diversity + label caps; `validate_no_executable_code` on all model output |
| `scene_author.py` | NEW (23.3 KB) | 15 treatment emitters, per-video design tokens, `theme.css` generation, whitelisted SVG paths, declarative Three.js presets. Post-audit fixes: `points`→`particles`, scalar `spread`→`[x,y,z]`, `box`→`cube` (Narova schema); transparent `vfd-clear` stage + `three.background` so the z-index-0 WebGL canvas is visible; two `style="font-size":NNpx` quote typos; strict `#[0-9A-Fa-f]{6}` theme-color regex |
| `bridge.py` | MODIFIED | added `build_directed_production` (hyperframes renderer, `_files.theme.css`) beside the untouched legacy `build_narova_production` |
| `engine.py` | MODIFIED | `_build_production` (director → authored production, deterministic fallback), one-shot portable-renderer fallback on browser-render failure, `creative-direction.json` persistence |
| `narova_runner.py` | MODIFIED | write `_files` (theme.css) into the Narova project, default build timeout 300 s → 900 s for browser renders of ~60 s videos |
| `code2video_runner.py` | MODIFIED (pre-mission session, same engine scope) | planning gateway provider support (planning was fixed before this mission began; included for completeness) |

## Video Flow service layer

| File | Change | Why |
|---|---|---|
| `src/voice_flow/video_flow_service.py` | MODIFIED | pass-through wiring of engine options (e.g. `visual_direction`) into the engine call; no behavior change elsewhere |

## NAROVA / HYPERFRAMES (`third_party/narova/`)

| File | Change | Why |
|---|---|---|
| `tool/src/hf.js` | MODIFIED | Windows integration patch: `npx` is a batch shim, spawn through `cmd.exe /d /s /c npx …` — direct spawn fails with `spawn EFTYPE` and every HyperFrames render dies at frame capture. No other Narova file touched. |

## VIDEO FLOW TESTS (`tests/`)

| File | Change | Why |
|---|---|---|
| `test_creative_director.py` | NEW (12 tests) | director contracts, diversity, label caps, fallbacks, security, directed production shape, and a regression test pinning Three.js object types to Narova's schema |
| `test_video_flow_long_render_policy.py` | MODIFIED | timeout bound updated 300 s → 900 s to match the browser-render budget (test intent kept: bounded timeout supporting one-minute videos) |

## VIDEO FLOW DOCUMENTATION / QA (this directory)

`visual_qa.py`, `driving_test.py`, `particle_probe.py`, the 12 required
`.md` docs, A/B/C/D/E artifacts (mp4s, contact sheets, probe frame),
`hf-feasibility/` + `directed-validation/` + `particle-probe/` scratch
projects, `engine-pre-upgrade-backup/`.

## OTHER

**None.** No non-Video-Flow application file was modified for this upgrade
(see `NON_VIDEO_FLOW_VERIFICATION.md` for the audit method).
