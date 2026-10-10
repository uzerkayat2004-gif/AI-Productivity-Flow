> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# PROVENANCE_AUDIT — Outcome B: third-party code is shipped, with attribution

## Verdict (mission §17 gate)

**Outcome B.** The application executes and redistributes third-party code:
- `Narova` (MIT, © 2026 Ammar Hasan) — the JS production tool (`narova.js`,
  `py/narova_tts`, vendored three.js/gsap) runs the video pipeline;
- `Code2Video` (MIT, © 2025 Anno Yanzhe Chen) — its prompt files are loaded
  at runtime by the planner adapter.

Both are permissively licensed; the release ships them **with full MIT
attribution** in THIRD_PARTY_NOTICES.txt, names them in the notices (not
disguised as first-party code), and documents the two local patches to
narova (`tool/src/hf.js`: Windows npx shim + bundled-modules direct run) in
runtime-manifest.json. Nothing was renamed to hide origin.

## Complete shipped-component license table

| Component | Version/pin | License | Notes |
|---|---|---|---|
| narova | vendored snapshot | MIT | shipped; patches documented |
| code2video | vendored snapshot | MIT | prompts shipped |
| three.js (narova vendor) | r185 | MIT | shipped via narova |
| gsap (narova vendor) | 3.14.2 | GreenSock standard license | notice kept verbatim; desktop-bundling not explicitly addressed by Webflow — flagged in KNOWN_LIMITATIONS |
| hyperframes | 0.7.96 | Apache-2.0 | node_modules shipped (replaces npx) |
| Node.js | 20.18.1 | MIT (+ bundled deps) | official zip |
| FFmpeg/FFprobe | gyan release-essentials | GPL-3.0 (libx264) | GPL text + source offer; build identified in manifest |
| Python | 3.12.10 | PSF | official installer |
| 62 pip packages | pinned (manifest) | MIT/BSD/Apache | incl. LGPLv3 trio below |
| edge-tts | 7.2.8 | LGPLv3 | notices + source offer |
| pynput | 1.8.2 | LGPLv3 | notices + source offer |
| pystray | 0.19.5 | LGPLv3 | notices + source offer |
| faster-whisper base.en | rev 3d3d5dee | MIT (Systran) / Apache-2.0 (openai weights) | model bundled |
| WebView2 bootstrapper | Evergreen | Microsoft terms | official distribution pattern |
| VC++ redistributable | 14.x | Microsoft terms | official installer |
| chrome-headless-shell | 152.0.7928.2 | Google CfT terms | **NOT redistributed** — provisioned per user via official endpoints |

## LGPLv3 compliance (edge-tts, pynput, pystray)

Shipped unmodified; LGPL-3.0 text included in the runtime directory;
THIRD_PARTY_NOTICES.txt carries a written source-offer statement pointing to
each canonical repository at the exact pinned version (three-year
availability commitment stated). The product does not statically link or
modify these libraries.

## GPL compliance (FFmpeg)

GPL-3.0 text shipped in `runtime/ffmpeg/`; the exact build version and
configuration are recorded in runtime-manifest.json; notices state the
source-availability offer (ffmpeg.org source releases; gyan.dev publishes
corresponding sources per build).

## Explicitly NOT bundled

Developer credentials/API keys, developer `~/.voice_flow` data, Chrome for
Testing binaries, npm/pip caches, piper voices (unused backend), the
`~/.narova` development venv.
