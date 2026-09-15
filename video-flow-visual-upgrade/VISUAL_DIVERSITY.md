# VISUAL_DIVERSITY — scene selection and repetition prevention

## Where diversity is decided

1. **Director prompt** — treatments are presented with concept-type guidance
   so the LLM's first choice is usually the concept-appropriate one
   (process → `process-flow`, depth/field → `particle-field`, closing →
   `recap-mosaic`).
2. **Post-parse enforcement** (`creative_director.py`):
   - `MAX_CONSECUTIVE = 2` — same treatment may not run 3+ scenes in a row;
   - `MAX_SHARE = 0.45` — no treatment may occupy >45% of scenes;
   - violators are rotated into the next concept-appropriate treatment;
   - first scene is forced to an opener style when the LLM picks poorly,
     last scene to a recap style.
3. **Structural QA** (`visual_qa.structure_repetition`) — reads
   `creative-direction.json` next to the produced video, reports the
   treatment sequence and `max_consecutive`; a sequence like
   `comparison, comparison, comparison, cards, cards` would be flagged for
   re-direction.

## Randomness policy

No randomness for variety's own sake (mission §15). Treatment choice is a
function of concept type + position; enforcement only repairs genuinely
repetitive plans.

## Measured results

| Video | Treatments | max_consecutive |
|---|---|---|
| A baseline | 4 fixed layouts, every scene cards/split | 4+ (structural) |
| C upgraded (sky blue) | hero-title → process-flow → wave-demo → recap-mosaic | 1 |
| Driving test | see AB_BENCHMARK.md | — |

## Text dominance

Diversity includes *texture*: counters, waves, 3D fields and diagrams carry
information visually instead of prose. Label caps (≤7 words, ≤4 per scene)
apply regardless of treatment; paragraphs are never emitted.
