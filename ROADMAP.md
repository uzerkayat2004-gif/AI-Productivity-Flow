# 🗺️ AI Productivity Flow — Project Roadmap

> A transparent, milestone-driven roadmap for contributors, users, and compute partners.

---

## 🟢 Stage 1: Core Multimodal Foundation (Completed — v1.0.0 Stable)

* [x] **Video Flow (Text-to-Video Visual Explainers)**
  * [x] AI-driven planning, concept breakdown, and Creative Director scene authoring.
  * [x] Multi-engine rendering architecture with dynamic layout solver and visual themes.
  * [x] Guaranteed zero-cost local deterministic layout and synthesis fallback.
  * [x] Native Google NotebookLM integration for audio/visual research synthesis.
  * [x] Direct MP4 compilation with automatic download to system Downloads folder.
* [x] **Audio Flow (Spoken Reader & Multi-Depth Audio Summaries)**
  * [x] **Read Mode**: Natural conversational spoken reader articulating selected text with high fidelity.
  * [x] **Summary Mode**: Multi-depth audio summaries (Short, Balanced, Deep Dive).
  * [x] Integrated floating and window player with waveform scrub bar, playback rate control (0.75x–2.0x), and MP3 download.
  * [x] Comprehensive voice provider ecosystem (Free Microsoft Edge Neural, ElevenLabs, Cartesia, Google Cloud, OpenAI TTS).
* [x] **Voice Flow (System-Wide Voice Dictation & Text Injection)**
  * [x] Low-latency global triggers (`Ctrl+Win` on Windows, `Cmd+Option` on macOS, Middle Click, Alt+Space).
  * [x] Local-first Faster-Whisper transcription running 100% on-device with zero cloud dependencies.
  * [x] Downloadable NVIDIA Nemotron Speech Streaming English 0.6B and Nemotron 3.5 ASR Streaming 0.6B models.
  * [x] Downloadable Liquid LFM 1.3B/3B on-device text rewriting and Windows AI Text Rewriter integration.
  * [x] Optional cloud STT (Deepgram, Groq, OpenAI Whisper, Gemini STT) and cloud LLM polishers.
  * [x] User dictionary and snippet expansion with cross-process persistence.

---

## 🟢 Stage 2: Security, Accounts & Distribution (Completed — v1.0.0 Stable)

* [x] **Multi-Account Security & Isolation**
  * [x] Isolated SQLite storage (`voice_flow.db`) and separate profile workspaces under `~/.voice_flow/`.
  * [x] Instant account switching with zero data leakage or lock contention.
  * [x] AES-256-GCM encrypted `.flowvault` archives for full account backup and migration.
* [x] **Cross-Platform Packaging & Release Baseline**
  * [x] Windows 10/11 x64 single-file installer (`AI-Productivity-Flow-Setup-x64.exe`) with isolated private runtime.
  * [x] macOS 12+ application bundle (`AI Productivity Flow.app` / `AI-Productivity-Flow-macOS.zip`).
  * [x] Safe, non-intrusive update checker querying GitHub Releases for stable updates.
  * [x] Canonical product versioning pinned strictly to `1.0.0` with CI consistency enforcement.

---

## 🟡 Stage 3: Ecosystem Expansion & Enhancements (Next Milestones)

* [ ] **Packaging & Signing Expansion**
  * [ ] Apple Developer ID code signing and automated notarization pipeline for macOS Gatekeeper.
  * [ ] Windows EV code signing certificate integration.
  * [ ] Linux desktop companion packaging (Flatpak / AppImage).
* [ ] **Visual Layouts & Narration**
  * [ ] Additional animated flowchart, code execution, and data-visualization scene types.
  * [ ] Auto-generated closed captions (SRT / VTT) and multi-track narration.
  * [ ] Multilingual translation pipeline for instant visual explanation localization.
* [ ] **Local Model Performance**
  * [ ] Quantized local diffusion video adapters where GPU compute is available.
  * [ ] Extended voice cloning and local Piper TTS integration.
