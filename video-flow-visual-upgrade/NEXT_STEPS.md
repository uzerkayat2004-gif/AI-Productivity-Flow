# NEXT_STEPS — future improvements only (not part of this upgrade)

1. **Concept→treatment heuristics** — a small semantic classifier that biases
   3D treatments for inherently spatial concepts (orbits, cutaways, fields)
   even without a user hint, complementing the LLM's choice.
2. **Scene-level retry with repair** — on a failed span, re-author just that
   scene (different treatment) instead of only re-rendering it; bounded to one
   repair pass.
3. **Asset library** — bundle a small set of openly licensed SVG/glTF assets
   (arrows, vehicles, molecules) so treatments can reference real objects
   instead of primitives, plus Lottie where an asset exists.
4. **VLM review pass (opt-in)** — offline screenshot critique appended to the
   job's QA record for users who want it; never blocks delivery.
5. **Orbital keyframes** — upstream Narova schema work to express parametric
   paths (`orbitRadius`, `angularSpeed`) so `orbit-3d` gets true revolutions.
6. **Per-scene render caching across jobs** — hash authored scenes and reuse
   rendered spans between regenerations of the same topic (extend `--reuse`
   across job sandboxes).
7. **Progress granularity** — surface span-level render progress (k of n
   scenes) in the existing progress rail message.
