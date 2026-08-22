# DOCUMENTATION_REALIGNMENT — 2026-08-22 audit & rewrite record

Mission: align the public GitHub presentation with the product that exists in
code. Documentation follows product reality; nothing in the app was changed
except the explicitly listed user-visible branding strings.

## Method

1. **Current Product Mapper** (specialist) mapped the product from `src/` code
   only — ignoring stale docs — producing `docs/CURRENT_PRODUCT_MAP.md`.
2. **Documentation Auditor** (specialist) audited every markdown/metadata file
   and produced a prioritized findings list (below).
3. Rewrites were made from the map, then verified by Architecture, Licensing,
   Branding/Link, and Quality reviewers (specialists), and a final Scope
   Guardian pass.

## Files reviewed (all .md + pyproject + gui manifest/html metadata)

README.md · ROADMAP.md · VIDEO_FLOW_ARCHITECTURE.md · CONTRIBUTING.md ·
SECURITY.md · pyproject.toml · src/voice_flow/gui/manifest.json ·
src/voice_flow/gui/index.html · video-player.html · tests_archived_v5/README.md ·
video_flow_renderer/src/notebook-sketch-poc/README.md · release-packaging/ (17) ·
video-flow-visual-upgrade/ (12) · .gitignore

## Stale claims found → corrected

| Finding | Where | Resolution |
|---|---|---|
| "47 Passed" test badge; 6 references to deleted test files | README, CONTRIBUTING | Removed; live suite documented without a permanent count badge |
| v5 architecture (evidence engine, Hybrid Render Router, Veo, `video_generation/`, Remotion as shipped renderer) | README, ROADMAP, VIDEO_FLOW_ARCHITECTURE | Removed; current pipeline documented (planner → Creative Director → scene authoring → browser renderer → FFmpeg) |
| `file:///C:/Users/...` links | VIDEO_FLOW_ARCHITECTURE, CONTRIBUTING | All removed; repository-relative links only |
| Normal users told to `git clone`/`pip install`/`npm install`/`setup_desktop_app.bat` | README | Replaced by installer download flow; developer setup moved to CONTRIBUTING |
| `github.com/.../Voice-Flow.git`, `cd Voice-Flow` | README, CONTRIBUTING | Current repo URL/name |
| "All AI credentials are encrypted" | README (was false — API keys are plaintext at rest) | Honest statement in README + SECURITY.md; code unchanged |
| "offline Windows SAPI5" TTS advertised | README, ROADMAP | Removed (no implementation; catalog entries route to Edge fallback) |
| Missing OpenAI/Gemini/NVIDIA voices in TTS list | README | Working provider list documented (Edge default + keyed cloud) |
| HyperFrames listed as future work | ROADMAP | Moved to Current (it is the shipped renderer) |
| Snippets advertised as a feature | README (old) | Dropped; snippet-style expansions described under Dictionary (matches code) |
| "Python 3.14 / Node 18+" as user prerequisites | README, CONTRIBUTING | Installer requires nothing; dev docs say 3.10+ (shipped runtime 3.12) |
| Speed range "0.8x–2.0x" | README (old) | Corrected to 0.75–2.0 (or dropped as a stat) |
| Old product name "Flow — Open-Source Multimodal…" / "Wispr Flow-style" / "AI Speech Desktop App" suffix | README title, pyproject, manifest.json, index.html title, installer shortcut descriptions | Canonical "AI Productivity Flow" everywhere user-facing; internal identifiers (voice_flow package, Run key, native window title) intentionally preserved for compatibility |
| Hero artwork claims ("100% private & local", "works offline") | docs/assets/ai-productivity-flow-hero.png | Image used as instructed; README text below it states the accurate privacy posture (local transcription; online AI/TTS when enabled). Discrepancy recorded here rather than altering artwork |
| Self-referential `C:\Users\...` path | tests_archived_v5/README.md | Replaced with repo-relative statement |

## Branding replacements

- Product: **AI Productivity Flow** (was: Flow / VoiceFlow / mixed).
- Features unchanged: Voice Flow, Audio Flow, Video Flow.
- Tagline: *Speak. Listen. Visualize. Without leaving your workflow.*
- Native window title & `FindWindowW` detection string left as-is (behavioral
  dependency — documented decision per mission §31); HTML `<title>`, manifest,
  pyproject description, and shortcut descriptions updated.

## Links corrected

All current-doc links are repository-relative and resolve (README ↔
SECURITY/CONTRIBUTING/VIDEO_FLOW_ARCHITECTURE/LICENSE/release notices/docs map).
Historical reports bannered instead of edited (see below).

## Historical documents intentionally preserved

- `release-packaging/*` — release audits (bannered; CLEAN_MACHINE_TEST /
  RELEASE_CHECKLIST / KNOWN_LIMITATIONS remain the open-items record).
- `video-flow-visual-upgrade/*` — implementation reports of the current engine
  (bannered).
- `tests_archived_v5/README.md`, `video_flow_renderer/src/notebook-sketch-poc/`
  — historical/POC notes, classified.

## Legal notices intentionally preserved (unchanged)

`release/THIRD_PARTY_NOTICES.txt` and all license texts — LGPL/GPL obligations,
MIT/Apache attributions untouched by the marketing alignment.

## Files changed

README.md (rewrite, hero first) · ROADMAP.md (rewrite) ·
VIDEO_FLOW_ARCHITECTURE.md (rewrite) · CONTRIBUTING.md (rewrite) ·
SECURITY.md (rewrite) · pyproject.toml (description only) ·
src/voice_flow/gui/manifest.json (name/description) ·
src/voice_flow/gui/index.html (title + meta) · video-player.html (meta) ·
src/voice_flow/installer.py (4 shortcut description strings — user-visible
metadata only) · .gitignore (.pytest_cache/, hero negation) ·
docs/assets/ai-productivity-flow-hero.png (new) · docs/CURRENT_PRODUCT_MAP.md ·
docs/PRODUCT_FACTS.md · docs/GITHUB_METADATA.md · this file.
Plus packaging-mission changes from the earlier validated mission (committed
separately in the same publication).

## Follow-ups recorded (not fixed in this documentation-only mission)

- The in-app Audio Flow provider list shows "Windows Offline SAPI5 · 1
  connected" (and lists Azure Speech / Fish Audio) although no synthesis
  branch exists for them — selections fall back to Edge. This is a product-UI
  truthfulness issue, not a docs issue; fix belongs in a product change
  (remove the hardcoded offline card + catalog entries in a feature mission).
- The hero artwork says "100% Private & Local / works offline"; per the
  accuracy rule the README states the real posture (local transcription;
  online AI/TTS when enabled) and this discrepancy is recorded rather than
  repeating it in copy.
