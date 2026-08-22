# KNOWN_LIMITATIONS — remaining weaknesses

1. **Treatment coverage vs. concept fit** — the director picks from 15
   treatments, but 3D usage depends on the LLM's choice; two identical topics
   can get different (both valid) plans. A spatial hint in `visual_direction`
   steers it (it chose `particle-field` on one sensor-fusion run and a 2D
   `timeline` plan on another), but there is no hard "spatial concept ⇒ 3D
   scene" rule.

2. **Orbit-3d planets rotate in place** — Narova's declarative schema animates
   object-local rotation/position; a true orbital path around the central body
   would need sinusoidal keyframes the schema doesn't express. Visually still
   reads as a 3D system with a rotating core, but it is not Keplerian motion.

3. **Fallback loses the design system** — when HyperFrames is unavailable the
   portable fallback renders the legacy 4-layout look (still correct MP4,
   motion-audited). The fallback is rare (browser present) but its output is
   visually the old style. The fallback event is visible in progress history
   ("Browser render unavailable — using portable renderer" at 48%).

4. **First HyperFrames build per machine** downloads the pinned HyperFrames
   CLI and Chrome-for-Testing (~once, then cached); a cold render adds that
   latency. The cache can also corrupt (it did once during development);
   recovery is reinstalling the cache.

5. **Render time scales with duration and effects** — ~48–60 s videos take
   roughly 3–6 min wall clock end-to-end (planning LLM calls + TTS + browser
   spans + FFmpeg). Deterministic; practical on the target machine, but not
   instant.

6. **Labels are English-centric** — narration/label cleaning assumes English
   (ASCII-safe glyphs); other languages will render but glyph coverage is
   untested.

7. **No VLM-in-the-loop yet** — visual QA is deterministic (sheets, motion,
   contrast, repetition). A VLM pass exists in the development loop only, not
   in the product pipeline (deliberate: keep generation offline-deterministic).

8. **Lottie unused** — no bundled Lottie assets ship today, so treatments
   don't include Lottie scenes (mission §23 allows this).
