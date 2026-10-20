# PRODUCT_FACTS — verify before editing public docs

Concise, checkable facts about AI Productivity Flow (Version 1.0). Public documentation must match these; if code changes them, update this file first.

- **Canonical product name**: AI Productivity Flow.
- **Feature families**: **Video Flow**, **Audio Flow**, **Voice Flow** (maintain this presentation order).
- **Core Promise**: From text to video. From text to audio. From voice to text. Without switching apps.
- **Platforms**:
  - Windows 10/11 x64: Single-file installer (`AI-Productivity-Flow-Setup-x64.exe`) with isolated private runtime.
  - macOS 14 Sonoma or later (Apple Silicon only, M1 or newer; not Intel Macs. The release bundle's Python runtime and launcher are arm64): Application bundle (`AI Productivity Flow.app` / `AI-Productivity-Flow-macOS.zip`).
- **Status**: Version 1.0.
- **Public version**: 1.0 (`DISPLAY_VERSION` in `src/voice_flow/_version.py`). This is the only version shown in the app, installer, splash, and release title.
- **Internal build**: 1.0.14 (`VERSION` in the same file). Update checks, Sentry releases, git tags, and the installer `AppVersion` use this build number. It changes every release; the public version stays 1.0 for this launch.
- **Download sizes** (v1.0.2 artifacts, the last published build): Windows installer about 546 MB, installed footprint about 1.5 GB, Mac DMG about 271 MB, Mac zip about 287 MB.
- **Crash reports**: on by default. Opt out under Settings → System → About & Updates → Privacy. Reports exclude audio, transcripts, and personal data.
- **Speech recognition**:
  - Local Faster-Whisper `base.en`, CPU int8, local; bundled with installer.
  - Downloadable streaming models: NVIDIA Nemotron Speech Streaming English 0.6B and Nemotron 3.5 ASR Streaming 0.6B.
  - Cloud STT providers: Deepgram, Groq, OpenAI Whisper, Gemini STT.
- **AI text polishing & rewriting**:
  - Downloadable on-device S1-mini by Superwhisper and Liquid LFM 2.5 350M via llama.cpp (cleanup only; voice commands need a cloud polish model).
  - Windows AI Text Rewriter where supported by hardware.
  - Optional cloud LLMs: Gemini, Claude, OpenAI, Groq, Nebius Token Factory, Ollama.
- **Audio Flow**:
  - **Trigger**: select text, then click the Listen button next to it or the floating bar. Mac also has a hotkey, Control+Option+L (read the selection; press again to stop). Mac needs Accessibility to read the selection.
  - **Read Mode**: Spoken reader that articulates selected text with human cadence.
  - **Summary Mode**: Multi-depth summaries (Short, Balanced, Deep Dive).
  - Voices: Microsoft Edge Neural (default, free, online: text is sent to Microsoft), ElevenLabs, Cartesia, OpenAI, Google Cloud TTS.
- **Video Flow** (Windows and macOS):
  - Source input → AI planning → Creative Director & scene authoring → dynamic layout solver → controlled rendering (Code2Video / Narova / WebGL) + synchronized narration.
  - Direct 1080p MP4 compilation automatically exported to user Downloads.
  - Google NotebookLM research synchronization.
  - Guaranteed offline deterministic fallback layout.
- **Security & Storage**:
  - Provider API keys and settings stored locally in SQLite (`~/.voice_flow/voice_flow.db`).
  - Full backups (`.flowvault`) encrypted with AES-256-GCM.
  - Loopback-only API server on `127.0.0.1:8991` with Origin and Host header verification.
