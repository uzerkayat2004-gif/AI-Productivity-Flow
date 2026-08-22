# PRODUCT_FACTS — verify before editing public docs

Concise, checkable facts about AI Productivity Flow (2026-08-22). Public
documentation must match these; if code changes them, update this file first.

- **Canonical product name**: AI Productivity Flow. Feature families: **Voice
  Flow**, **Audio Flow**, **Video Flow** (never rename these). Repo name stays
  `AI-Productivity-Flow`; internal identifiers (`voice_flow` package,
  `~/.voice_flow`, Run-key `VoiceFlow`) are compatibility identifiers, not branding.
- **Platform**: Windows 10/11 x64 only. No macOS/Linux support exists.
- **Status**: Windows Beta. Installer built and locally validated; fresh external
  clean-Windows acceptance pending (`release-packaging/CLEAN_MACHINE_TEST.md`).
- **Speech recognition**: faster-whisper `base.en`, CPU int8, local; bundled with
  the installer. The app as a whole is NOT offline: Edge/cloud voices, AI
  polishing, summaries, and Video Flow planning use the internet.
- **AI policy (BYOK)**: no developer keys shipped. Core dictation needs no key.
  AI polishing + Audio Flow summaries + Video Flow planning need a user-connected
  provider and explicit consent. Never claim "works offline" or "no cloud".
- **Audio Flow voices that work**: Edge (default, free), ElevenLabs, Deepgram,
  OpenAI, Google, Gemini, NVIDIA (cloud ones need the user's key).
  `offline`/SAPI5, `azure`, `fish` exist in the selector catalog but have no
  synthesis implementation — do not advertise them.
- **Video Flow modes**: `summary` and `full` (there is no "lesson" mode).
  Documents: .txt .md .csv .json .html .htm .xml .rtf .docx .pdf ≤ 8 MB.
- **Video Flow pipeline**: planning (connected model) → Creative Director (15
  treatments) → scene authoring → browser-based deterministic rendering
  (bundled HyperFrames modules; portable fallback) → narration (independent
  voice setting, Edge default) + captions → FFmpeg → 1080p H.264 MP4.
- **Removed/never-current (don't document)**: standalone Snippets feature,
  Remotion in the shipped product, Veo, hybrid render router, "evidence engine",
  offline SAPI5 TTS, macOS/Linux.
- **Security facts**: API keys stored locally in SQLite, **not encrypted at
  rest**; OAuth tokens encrypted; loopback-only API on 127.0.0.1:8991; consent
  gates + `validate_no_executable_code` enforced.
- **Installer**: one per-user exe bundling CPython 3.12.10, Node 20.18.1,
  FFmpeg/FFprobe, whisper base.en, HyperFrames 0.7.96 modules, vendored
  Narova + Code2Video (MIT, attributed in release/THIRD_PARTY_NOTICES.txt);
  WebView2/VC++ installed conditionally; render browser provisioned
  automatically during installation (official channels; not redistributed).
