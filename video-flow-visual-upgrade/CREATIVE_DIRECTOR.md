# CREATIVE_DIRECTOR — architecture and contracts
> 🗄️ Historical implementation report (2026-08-22 visual upgrade mission). For current architecture see [VIDEO_FLOW_ARCHITECTURE.md](../VIDEO_FLOW_ARCHITECTURE.md).

`src/voice_flow/video_flow_engine/creative_director.py` (new)

## Position

```
Code2Video storyboard  (WHAT to teach — unchanged)
        ↓
creative_director.direct(storyboard, gateway, theme, visual_direction)
        ↓  direction payload (constrained JSON)
scene_author.author_scene(entry, design, …)  (HOW to show it)
        ↓
bridge.build_directed_production → Narova/HyperFrames
```

## Direction payload

```json
{
  "brief": {
    "visual_theme": "...", "audience": "...",
    "accent_shift": 0, "motion": "crisp|flowing",
    "background": "gradient|grid|flat",
    "scene_variety_goal": "...", "avoid": ["repeated card grids", "large paragraphs"]
  },
  "scenes": [
    {"id": "...", "treatment": "wave-demo", "metaphor": "sunlight splitting into waves",
     "labels": ["Short blue waves scatter", "…"], "visual_notes": "…"}
  ]
}
```

The LLM chooses **treatments, metaphors, labels** — nothing executable. The
prompt offers the 15 treatments with one-line selection guidance keyed to
concept type (process → `process-flow`, spatial depth → `particle-field`,
recap → `recap-mosaic`, …) plus the storyboard section titles and the user's
`visual_direction`. Response parsing is defensive (JSON extraction, per-scene
validation, drop bad entries); anything unrecoverable raises `DirectorError`
and the engine falls back to a deterministic assignment (round-robin over
concept-appropriate treatments, hero-title first, recap-mosaic last).

## Treatment registry (15)

hero-title · labeled-diagram · process-flow · comparison-split · timeline ·
counter-stats · wave-demo · particle-field (3D) · orbit-3d · cutaway-3d ·
before-after · scale-comparison · layer-reveal · chart-growth · recap-mosaic

## Text discipline (mission §16)

- On-screen labels: ≤ 7 words (`MAX_LABEL_WORDS`), ≤ 4 labels per scene
  (`MAX_LABELS`).
- Explanatory detail stays in narration + captions; screens show labels,
  names, numbers, short phrases.

## Diversity rules (mission §15)

- No treatment more than `MAX_CONSECUTIVE = 2` scenes in a row.
- No treatment above `MAX_SHARE = 0.45` of scenes.
- Enforced after parsing (swap/rotate violators); QA re-checks the final
  sequence (`visual_qa.structure_repetition`).

## Security

- Model output re-validated with `contracts.validate_no_executable_code`.
- Labels escaped; only whitelisted treatment names accepted; path data
  whitelist in scene_author; declarative Three.js configs only.
- Gateway consent path unchanged (`allow_external_ai`, isolated worker).

## Tests

`tests/test_creative_director.py` — 11 tests: payload contract, treatment
validation, diversity enforcement, label caps, deterministic fallback,
`DirectorError` paths, no-executable-code guarantees.
