# PRODUCT_FACTS — verify before editing public docs

Concise, checkable facts about AI Productivity Flow (v1.0.0 Public Release). Public documentation must match these; if code changes them, update this file first.

- **Canonical product name**: AI Productivity Flow.
- **Feature families**: **Video Flow**, **Audio Flow**, **Voice Flow** (maintain this presentation order).
- **Core Promise**: From text to video. From text to audio. From voice to text. Without switching apps.
- **Platforms**:
  - Windows 10/11 x64: Single-file installer (`AI-Productivity-Flow-Setup-x64.exe`) with isolated private runtime.
  - macOS 12+ (Apple Silicon & Intel): Application bundle (`AI Productivity Flow.app` / `AI-Productivity-Flow-macOS.zip`).
- **Status**: v1.0.0 Stable Public Release.
- **Public Version**: 1.0.0 (canonical source: `src/voice_flow/_version.py`).
- **Speech recognition**:
  - Local Faster-Whisper `base.en`, CPU int8, local; bundled with installer.
  - Downloadable streaming models: NVIDIA Nemotron Speech Streaming English 0.6B and Nemotron 3.5 ASR Streaming 0.6B.
  - Cloud STT providers: Deepgram, Groq, OpenAI Whisper, Gemini STT.
- **AI text polishing & rewriting**:
  - Downloadable on-device Liquid LFM 1.3B/3B via llama.cpp.
  - Windows AI Text Rewriter where supported by hardware.
  - Optional cloud LLMs: Gemini, Claude, OpenAI, Groq, Ollama.
- **Audio Flow**:
  - **Read Mode**: Spoken reader that articulates selected text with human cadence.
  - **Summary Mode**: Multi-depth summaries (Short, Balanced, Deep Dive).
  - Voices: Microsoft Edge Neural (default, free), ElevenLabs, Cartesia, OpenAI, Google Cloud TTS.
- **Video Flow**:
  - Source input → AI planning → Creative Director & scene authoring → dynamic layout solver → controlled rendering (Code2Video / Narova / WebGL) + synchronized narration.
  - Direct 1080p MP4 compilation automatically exported to user Downloads.
  - Google NotebookLM research synchronization.
  - Guaranteed offline deterministic fallback layout.
- **Security & Storage**:
  - Provider API keys and settings stored locally in SQLite (`~/.voice_flow/voice_flow.db`).
  - Full backups (`.flowvault`) encrypted with AES-256-GCM.
  - Loopback-only API server on `127.0.0.1:8991` with Origin and Host header verification.
