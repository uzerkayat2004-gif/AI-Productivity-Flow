# NAROVA_FULL_FIDELITY_AUDIT — what our old integration was missing

Internal report required by mission §8, based on inspecting the vendored
Narova source (`third_party/narova/tool/src/*`), its showcase/examples, and the
HyperFrames render path it drives.

## Our previous use of Narova

- Bridge emitted only `scene.visual` portable trees with **4 deterministic
  layouts** (focus/comparison/transformation/flow) — every section became
  title + cards.
- Renderer pinned to **`no-browser`**: the portable composer rasterizes those
  trees without a browser, so no CSS design system, no SVG path animation, no
  GSAP cues, no Three.js.
- No per-video design system: one hardcoded palette, no theme.css, no motion
  language, no typographic scale.
- No creative decision layer: the storyboard's *educational* intent went
  straight to layout; nothing chose *how* a concept should be shown.

## Full showcase-style use

Narova's own high-quality reels are authored as:

- **Custom scene HTML** (`scene.body`) with Narova's motion attributes
  (`reveal`, `cue`, `data-draw`, `data-count`, `data-mark`, `data-delay`)
  driven by GSAP timing and narration cues — not portable card trees.
- **Per-reel `theme.css`** — palette, typography scale, backgrounds
  (gradients/grid), easing language — so scenes vary while the reel stays
  coherent.
- **Inline SVG illustration** with hand-shaped path data that draws on cue
  (spectrum waves, arrows, charts).
- **HyperFrames renderer** (`--renderer hyperframes`): the reel is composed to
  an HTML project (spans per scene, gsap + three vendored assets) and rendered
  by a real browser at fixed fps with streaming encode; audio/captions are
  muxed the same way as the browserless path.
- **Declarative Three.js** scenes (module scenes with vendored three.core.js)
  for spatial subjects.
- **Creative brief first**: showcase reels pick a visual idea per scene
  deliberately; scene structure follows the concept.

## Gap list → what we implemented

| Missing | Implemented as |
|---|---|
| Treatment choice per scene | `creative_director.direct()` — LLM picks from 15 treatments with metaphor + labels |
| Design system | `scene_author.resolve_design()` + per-video `theme.css` (`_files`) |
| Animated SVG | whitelisted path emitters with `data-draw` cues |
| Motion/GSAP cues | `reveal`/`cue`/`data-delay` attributes on authored HTML |
| Three.js | declarative configs for `particle-field`, `orbit-3d`, `cutaway-3d` |
| HyperFrames renderer | `renderer: "hyperframes"` + Windows npx spawn fix in `hf.js` |
| Diversity enforcement | MAX_CONSECUTIVE=2, MAX_SHARE=0.45, structural QA |

## Feasibility evidence

1. First HyperFrames build through the vendored CLI: 2 scenes, 6.9 s video —
   confirmed browser rendering works after the npx/Chromium repairs.
2. Hand-authored showcase-style reel on the sky-blue topic (`hf-feasibility`,
   `directed-validation` projects) — 16.8 s, saved as `narova-full-fidelity.mp4`
   (variant B): animated SVG spectrum waves, drawn underlines, sequenced chips.
3. Same capabilities then driven automatically by the pipeline (variant C).
