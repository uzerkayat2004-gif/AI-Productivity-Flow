# Changelog

All notable changes to **AI Productivity Flow** are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## 1.0.0 - 2026-10-05

### First Stable Public Release

AI Productivity Flow is a free and open-source desktop AI system for Windows and macOS. It is designed to work inside your existing workflow without requiring you to switch between separate browser tabs or workspaces.

#### Core Feature Families

- **Video Flow**
  - Transform text selections, articles, or complex documents into visual explainers with animated scene compositions and synchronized audio narration.
  - Multi-engine rendering architecture: Creative Director pipeline with dynamic layout solver, visual themes, and local deterministic fallback.
  - Native Google NotebookLM integration for audio/visual summaries and document analysis.
  - Direct local MP4 rendering with automatic export to the user's Downloads directory.
  - Provider support for Google Gemini, OpenAI, Claude, Groq, Ollama, and local fallbacks.

- **Audio Flow**
  - **Read Mode**: Spoken reader that explains and articulates selected text clearly using high-fidelity text-to-speech.
  - **Summary Mode**: Multi-depth spoken summaries (Short, Balanced, Deep Dive) for quick briefs or comprehensive document breakdowns.
  - Integrated audio player with playback speed control (0.75x–2.0x), waveform visualization, and one-click MP3 download.
  - TTS provider options: Edge TTS (free, high quality), Cartesia, ElevenLabs, Google TTS, OpenAI TTS, and local system speech.

- **Voice Flow**
  - System-wide voice dictation and text injection that types directly into whatever application is currently focused.
  - **Local-first transcription**: Bundled Faster-Whisper (CPU/GPU) with zero internet requirement.
  - **Downloadable streaming models**: NVIDIA Nemotron Speech Streaming English 0.6B and Nemotron 3.5 ASR Streaming 0.6B with low-latency streaming transcription.
  - **Optional cloud STT**: Deepgram, Groq Whisper, OpenAI Whisper, and Gemini STT.
  - **AI Text Polish**: On-device Liquid LFM 1.3B/3B, Windows AI Text Rewriter, or optional cloud LLMs for conversational cleanup, tone transformation, and snippet expansion.
  - Custom user dictionary and snippet expansion with cross-process synchronization.

#### Platform Support

- **Windows 10 / 11 (64-bit)**:
  - Per-user installer (`AI-Productivity-Flow-Setup-x64.exe`) with isolated private runtime.
  - Global hotkeys (`Ctrl + Win` default, single Ctrl, double-tap Ctrl, Alt+Space, middle mouse button).
  - Background system tray watchdog with fast window restore.
- **macOS 12+ (Apple Silicon & Intel)**:
  - Desktop application bundle (`AI Productivity Flow.app`) packaged as `AI-Productivity-Flow-macOS.zip`.
  - Platform abstraction layer supporting macOS pasteboard, AppleScript injection, and system shortcuts (`Cmd + Option`).
  - Single-line terminal installer (`scripts/install.sh`) for rapid setup.

#### Security & Privacy Architecture

- **Local-first by design**: Audio recorded by local models never leaves the device.
- **Explicit Cloud Routing (BYOK)**: User API keys and cloud requests are sent only to the specific providers chosen by the user.
- **Local SQLite Storage**: App data, history, and provider configurations live locally in `~/.voice_flow/`.
- **Encrypted Exports**: Complete data vault export/import (`.flowvault`) encrypted with AES-256-GCM.
- **Hermetic Desktop API**: The internal GUI server binds strictly to loopback (`127.0.0.1:8991`) with Origin, Host, and port verification.

#### Open Source & Updates

- Licensed under **Apache-2.0**.
- Safe, non-intrusive update checker querying GitHub Releases for new stable releases without automated background installation.
