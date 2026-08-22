# PERFORMANCE — resource measurements (ordinary Windows desktop)

## End-to-end generation (through the real backend, 127.0.0.1:8991)

| Run | Video | Path | Wall clock | Output |
|---|---|---|---|---|
| C "sky blue" | 47.1 s, 1080p | full pipeline (planning → director → HF → FFmpeg) | ≈ 4 min | 3.10 MB |
| D driving #1 | 57.9 s, 1080p | portable fallback (Skia) after config rejection | ≈ 4 min (incl. failed attempt) | 2.4 MB |
| D driving #2 | 55.8 s, 1080p | full pipeline, HyperFrames | 499 s | 3.70 MB |
| E sensor fusion #1 | 57.9 s, 1080p | full pipeline, HyperFrames; director chose `particle-field` (canvas-hidden pre-fix) | 220 s | 3.10 MB |
| E probe (post-fix) | 4.6 s, 1080p | same authoring path, fixture direction, `particle-field` with visible 3D particles | ≈ 60 s render | 1.06 MB |
| E sensor fusion #2 | 63.9 s, 1080p | full pipeline, HyperFrames (treatments incl. timeline) | 301 s | 4.23 MB |

Render time scales with duration and effects; planning (2 LLM calls) and TTS
are bounded by provider latency; browser spans dominate for ~1-minute videos.

## Peak process counts (driving #2, sampled every 10 s via tasklist)

- Chrome (renderer + compositor workers): **14**
- Node (Narova CLI / HyperFrames): **6**
- Python (app, workers, Piper venv): **9**
- FFmpeg (final normalize): **2**

All processes exit after the job; ProcessManager tracks and tree-cancels the
pipeline on cancellation. No orphaned browser processes observed after
completion.

## Output stability

- Every output: H.264, 1920x1080, yuv420p, AAC, +faststart → existing player
  accepts all (`playable: true` from the history API; Range-served file route).
- Narova's own motion audit passed on the fallback run ("no 2s frozen or 0.5s
  black segments"); HyperFrames `--verify-motion` gates span renders.
- Temp disk: per-job sandbox under `~/.voice_flow/v3_projects/<id>/`; span
  cache (`--reuse`) keeps re-renders incremental.

## Reliability events during the mission

1. `spawn EFTYPE` at frame capture → hf.js cmd.exe shim (fixed).
2. Corrupt Chrome-for-Testing cache → reinstall (environment, not repo).
3. First driving run hit an invalid `points` three.js type → portable
   fallback engaged automatically, video still delivered; emitter fixed and
   regression-tested (`test_three_configs_match_narova_schema`).
4. First sensor-fusion run revealed the 3D canvas renders BEHIND the scene
   body (Narova z-index 0) — opaque stage backgrounds hide it. Fixed with a
   transparent `vfd-clear` stage + `three.background` hex; visibility proven
   by a probe render through the same authoring + Narova build path (900
   particles visible; deterministic pixel count on the extracted frame).
