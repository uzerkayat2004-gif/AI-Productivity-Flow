# Video Flow Architecture

Video Flow turns selected text, pasted content, or documents into narrated,
captioned educational explainer videos. This document describes the architecture
as it exists in the current source tree (`src/voice_flow/video_flow_engine/`).
A factual product-wide map also lives in [docs/CURRENT_PRODUCT_MAP.md](docs/CURRENT_PRODUCT_MAP.md).

## Pipeline

```
Source (selected text · pasted text · document)
        ↓  extraction (.txt .md .csv .json .html .xml .rtf .docx .pdf, ≤ 8 MB)
Educational planning            (code2video_runner.py)
        ↓  outline → storyboard via the user's connected model (consent-gated)
Creative Director               (creative_director.py)
        ↓  15 visual treatments, diversity limits (≤2 consecutive / ≤45% share),
           label caps (≤4 per scene, ≤7 words); deterministic fallback direction
Scene authoring                 (scene_author.py)
        ↓  per-video design system (theme.css), whitelisted SVG paths,
           declarative 3D scene configs
Production bridge               (bridge.py)
        ↓  validated declarative production (renderer: browser | portable)
Rendering                       (narova_runner.py)
        ↓  check → synth → compose → build (--reuse --fps 30 --verify-motion)
           browser-based deterministic renderer (bundled HyperFrames modules)
           with automatic one-shot portable fallback
Narration + captions            (voice_provider_worker.py, narova synth)
        ↓  default Edge neural voice; selectable from the shared voice catalog
           (independent `video_flow_voice_model` setting); SRT/VTT captions
FFmpeg finalization
        ↓
1920×1080 H.264 / AAC / yuv420p / faststart MP4  →  built-in player
```

## Modules

| Module | Responsibility |
|---|---|
| `video_flow_engine/code2video_runner.py` | Educational planning through the connected model; isolated one-shot worker with stdin-only credentials; explicit external-AI consent |
| `video_flow_engine/creative_director.py` | LLM direction (treatments, metaphors, labels) with strict JSON contract, diversity enforcement, `validate_no_executable_code` on all model output |
| `video_flow_engine/scene_author.py` | Deterministic scene emitters for 15 treatments; design tokens; per-video `theme.css`; declarative Three.js configs (schema-conformant) |
| `video_flow_engine/bridge.py` | Storyboard + direction → validated Narova production; legacy portable production retained as fallback |
| `video_flow_engine/narova_runner.py` | Process-managed CLI pipeline (900 s timeout, tree cancellation), browser renderer invocation, FFmpeg output normalization |
| `video_flow_engine/voice_provider_worker.py` | Narration through the app's TTS stack (Edge default; cloud voices via the same provider keys as Audio Flow), registered as the renderer's external voice provider |
| `video_flow_engine/engine.py` | Orchestration, progress states, cancellation, fallback chain (director → deterministic direction; browser → portable renderer) |
| `video_flow_service.py` | Job queue/store, request echo for retries, provider gateway resolution |
| `video_flow_widget.py` / `video_flow_player.py` | Composer UI and standalone always-on-top player |

## Guarantees

- **Security boundary**: model output is constrained JSON/text only; every
  payload passes `validate_no_executable_code` (`video_flow_v3/contracts.py`).
  AI never authors executable code, pixel coordinates, or camera math.
- **Determinism**: visual scenes are compiled from whitelisted primitives; the
  browser renderer verifies motion (`--verify-motion`) so no scene renders static.
- **Isolation**: per-job sandbox under `~/.voice_flow/v3_projects/<job>/`
  (plan, storyboard, direction, renders, logs, captions, final MP4); scrubbed
  subprocess environments; process-tree cancellation.
- **Portability**: the same production format renders through the bundled
  browser renderer or the portable fallback, so generation never hard-fails on a
  missing browser.

## Runtime layout (installed app)

The vendored production tool and renderer modules live under
`runtime/` in the installation (`runtime/narova`, `runtime/code2video`,
`runtime/hyperframes`), resolved centrally by `voice_flow/runtime_env.py`. See
[release-packaging/](release-packaging/) reports for the bundled runtime
inventory and provenance.
