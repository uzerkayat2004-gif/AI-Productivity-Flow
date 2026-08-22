# AB_BENCHMARK — same topic, three systems (mission §39/§40)
> 🗄️ Historical implementation report (2026-08-22 visual upgrade mission). For current architecture see [VIDEO_FLOW_ARCHITECTURE.md](../VIDEO_FLOW_ARCHITECTURE.md).

Topic for A/B/C: **"Why is the sky blue?"**

- **A — Current system**: Code2Video → 4-layout bridge → no-browser renderer
  (`baseline-current.mp4`, backend job `vf-29df3b55d24d4613ad988617f1234f51`).
- **B — Full Narova**: same educational storyboard, showcase-style authoring,
  HyperFrames (`narova-full-fidelity.mp4`, hand-driven via the vendored CLI).
- **C — Upgraded Video Flow**: Code2Video → Creative Director → full Narova →
  HyperFrames, through the real backend
  (job `vf-3690331573224dc9bf1e511dff5b9832`, 47.1 s — doubles as the mission
  §45 45–60 s real-pipeline test).
- **D — Required autonomous-driving test** (mission §46): "We're moving toward
  end-to-end neural networks for autonomous driving" through the real backend
  (job `vf-34c30b3077aa4dd6be63b5e27ea56ef6`).
- **E — Sensor-fusion 3D check**: spatial topic steered toward a three.js
  particle scene. Run 1 (backend, 220 s): director chose `particle-field`,
  config passed `narova check`, HyperFrames rendered — but the particles were
  invisible because Narova layers the 3D canvas behind the scene body and our
  opaque stage background covered it. After the visibility fix
  (`vfd-clear` stage + `three.background`), a probe render through the same
  authoring + Narova build path shows the 900-particle field (deterministic
  pixel count on the extracted frame), and a second full backend run (301 s,
  63.9 s video, treatments incl. `timeline`) confirms the pipeline end-to-end.
  Live runs have now exercised 8 of the 15 treatments.

## Deterministic metrics (visual_qa.py)

| Metric | A | B | C | D |
|---|---:|---:|---:|---:|
| Duration | 48.4 s | 16.8 s | 47.1 s | 55.8 s |
| Resolution | 1080p | 720p* | 1080p | 1080p |
| frame_contrast_avg | 1872 | 2256 | 2601 | 3659 |
| frame_to_frame_change | 277.7 | 557.6 | 527.2 | 722.6 |
| Motion vs baseline | 1.0x | 2.0x | 1.9x | 2.6x |
| Treatments | 4 fixed layouts | 3 hand-authored | 4 distinct, max run 1 | 5 distinct, max run 1 |
| monotony_flag | false | false | false | false |

*B was rendered at the showcase default 720p before final normalization;
C/D go through the app's 1080p FFmpeg normalize.

## Scored table (mission §40; 1–5, from metrics + VLM sheet review)

| Metric | A | B | C | D |
|---|:-:|:-:|:-:|:-:|
| Educational clarity | 3 | 3 | 4 | 4 |
| Visual storytelling | 2 | 4 | 4 | 4 |
| Scene variety | 1 | 4 | 4 | 5 |
| Motion quality | 2 | 4 | 4 | 4 |
| Text dependence | 2 (text-led cards) | 4 | 4 | 4 |
| 3D/spatial quality | 1 | 1 (none) | 3 (declarative 3D available) | 3 |
| Professional appearance | 2 | 4 | 4 | 4 |
| Visual coherence | 3 | 5 (hand-tuned) | 4 (design system) | 4 |
| Render reliability | 5 | 5 | 5 (fallback proven live) | 5 |
| Generation time | ~3 min | 17 s render | ≈ 4 min | 499 s |

Notes:
- B remains the ceiling for a single hand-authored reel (a human tuned it);
  C/D reach most of that quality **automatically** from any selected text,
  which is the mission's target.
- A's VLM sheet review: "highly consistent template… content varies, layout
  does not; text-heavy". C: "rhythmic structural shifts… balanced
  text/animation". D adds counters and a wave/data pairing on the driving
  narrative with the highest contrast (3659) and motion (722) of all runs.

## D — required driving test detail

Treatments: hero-title → process-flow → counter-stats → wave-demo →
recap-mosaic (max consecutive 1). Narration ≈ 58 s across 5 scenes, 21 caption
cues, Piper voice, 1080p output, playable in the existing player. The first
attempt of this test also proved the fallback: an invalid three.js type was
rejected by `narova check`, the engine switched to the portable renderer
mid-job and still delivered a motion-audited 57.9 s video — then the emitter
was fixed and the rerun went full HyperFrames.
