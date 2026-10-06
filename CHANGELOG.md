# Changelog

All notable changes to **AI Productivity Flow** are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## 1.0.1 - 2026-10-06

### Patch Release: Release Integrity, Installer Rebuild & Packaging Audit

This release resolves critical packaging and workflow issues identified in the release-artifact integrity audit:

#### Packaging & Artifact Fixes
- **Windows Installer Rebuild**: Fixed an issue where the initial Windows installer asset on GitHub retained an obsolete v0.9.0-beta payload due to build staging caching. The Windows installer (`AI-Productivity-Flow-Setup-x64.exe`) has been rebuilt from scratch from verified source with Python 3.12, bundled Faster-Whisper models, and fresh SHA-256 verification.
- **macOS Bundle Dependency Packaging**: Updated the macOS packaging pipeline to build with `--bundle-runtime`, bundling all required Python packages into `Contents/Resources/runtime/site-packages` and adding architecture validation to support clean macOS machines.
- **macOS Terminal Installer**: Harmonized target bundle directory in `scripts/install.sh` to correctly match `AI Productivity Flow.app`.

#### Release Workflow & Gate Hardening
- **Strict Release Gate**: Hardened `.github/workflows/release.yml` to prevent publishing incomplete or outdated releases. The workflow now verifies that all 4 required release artifacts (`Setup-x64.exe`, `Setup-x64.exe.sha256`, `macOS.zip`, `macOS.zip.sha256`) exist, pass SHA-256 integrity validation, and specifically blocks recycling the old v0.9.0-beta binary hash (`aad99333...`).
- **macOS Smoke Validation**: Added automated archive validation ensuring `Contents/Resources/runtime/site-packages` is non-empty before uploading release artifacts.

#### Core Feature Refinements
- **Voice Flow Commands & Dictionary**: Integrated automatic dictionary pipeline learning, Nemotron speech tokenizer repair, and enhanced command parsing.

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
