# 🗺️ AI Productivity Flow — Project Roadmap

> A transparent, milestone-driven roadmap for contributors, users, and compute partners.

---

## 🟢 Stage 1: Core Multimodal Foundation (Completed & Verified)

* [x] **Voice Flow (Zero-Friction Dictation)**
  * [x] Low-latency global middle-click and `Ctrl+Win` (`Cmd+Ctrl` on Mac) triggers with Push-to-Talk and toggle modes.
  * [x] 64-bit native Win32 message-pump hook (`WH_MOUSE_LL`) with auto-rehook watchdog.
  * [x] Local Faster-Whisper transcription with custom dictionary prompt-biasing and dual-pass VAD.
  * [x] Active window style engine adapting tone and syntax across VS Code, Slack, Outlook, Excel, and Chrome.
  * [x] Silent Windows Auto-Startup on laptop boot with background supervisor auto-recovery.
* [x] **Audio Flow (Text-to-Speech & Screen Reader)**
  * [x] Screen text highlight detection with real-time word tracking.
  * [x] Floating player with waveform scrub bar, speed adjustment (0.75x–2.0x), and audio controls.
  * [x] Multi-provider TTS backend (Free Microsoft Edge Neural, Google Cloud, ElevenLabs, Deepgram Aura, SAPI5).
  * [x] Automatic and one-click downloading to user Downloads & Music folders with exact title preservation.
* [x] **Video Flow v2.1 (Pedagogy & Hybrid Rendering)**
  * [x] 15 dynamic visual treatments: animated flowcharts, timelines, metric counters, 3D WebGL scenes, and recap grids.
  * [x] Evidence assembly: claims, entities, relationships, confidence, and provenance extraction.
  * [x] Guaranteed zero-cost deterministic Remotion & procedural rendering fallback.
  * [x] Dual-mode operation: Summary Mode (rapid briefing) & Full Mode (deep educational breakdown).
  * [x] Automatic and one-click downloading to user Downloads & Videos folders.

---

## 🟢 Stage 2: Intelligence, Accounts & Connectivity (Completed & Verified)

* [x] **NotebookLM Research Sync & Knowledge Base**
  * [x] Native Google OAuth integration with durable token refresh and error state recovery.
  * [x] Direct synchronization of Google Notebooks, Audio Overviews, study guides, and research sources.
* [x] **Multi-Account Security & Isolation**
  * [x] General → System → Account Settings navigation order.
  * [x] Interactive Switch Account modal with zero data leakage.
  * [x] Isolated SQLite databases and secure encrypted credential vaults per account profile.
* [x] **Robust Download Engine**
  * [x] Multi-directory dual-drive saving across `D:\` and `C:\` (`Downloads`, `Videos`, `Music`).
  * [x] Timestamp synchronization (`mtime` set to `NOW`) guaranteeing top placement under "Today" in Windows Explorer.
  * [x] Sanitized filenames preserving exact media titles without trailing punctuation.

---

## 🟡 Stage 3: Ecosystem, Distribution & Accessibility (Active & Next Up)

* [ ] **Cross-Platform Parity**
  * [x] macOS Community Preview with one-liner installer (`curl ... | bash`) and Universal App bundle (.zip).
  * [ ] Full physical hardware QA and notarization on Apple Silicon (M1/M2/M3/M4) and Intel macOS.
  * [ ] Linux desktop companion packaging (Flatpak / AppImage).
* [ ] **Advanced Generative Model Adapters**
  * [x] OpenAI Codex & Whisper streaming integration with transient socket resilience.
  * [ ] Native Google Veo and Vertex AI video generation adapters.
  * [ ] Local quantized diffusion video models (e.g., Wan2.1, HunyuanVideo) for offline premium visual generation.
* [ ] **Multimodal Accessibility**
  * [ ] Auto-generated closed captions (SRT / VTT) and multi-track narration.
  * [ ] Multilingual translation pipeline for instant visual explanation localization.
  * [ ] Community-contributed educational theme templates and visual motion libraries.
