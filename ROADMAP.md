# 🗺️ Flow Project Roadmap

> A transparent, milestone-driven roadmap for contributors, users, and compute partners.

---

## 🟢 Stage 1: Current Stable Foundation (Completed & Verified)

* [x] **Voice Flow (Core Dictation)**
  * [x] Low-latency global middle-click and `Ctrl+Win` triggers with Push-to-Talk and toggle modes.
  * [x] 64-bit native Win32 message-pump hook (`WH_MOUSE_LL`) with auto-rehook watchdog.
  * [x] Local Faster-Whisper transcription with custom dictionary prompt-biasing and dual-pass VAD.
  * [x] Active window style engine adapting tone and syntax across VS Code, Slack, Excel, and Chrome.
  * [x] Silent Windows Auto-Startup on laptop boot with background supervisor auto-recovery.
* [x] **Audio Flow (Text-to-Speech & Screen Reader)**
  * [x] Screen text highlight detection with real-time yellow highlight tracking.
  * [x] Floating player with waveform scrub bar, speed adjustment, and audio controls.
  * [x] Multi-provider TTS backend (Microsoft Edge Neural, Google, ElevenLabs, Deepgram Aura, SAPI5).
* [x] **Video Flow Brain (Pedagogy & Planning)**
  * [x] Evidence assembly: claims, entities, relationships, confidence, and provenance extraction.
  * [x] Visual director and diversity validator preventing repetitive layouts.
  * [x] Quality checker with automatic targeted scene repair.
  * [x] Remotion 4 compositor for deterministic 1080p video rendering.
  * [x] Standard benchmark suite with 12 domain fixtures and automated quality scoring.

---

## 🟡 Stage 2: Video Flow v2 — Hybrid Rendering (In Progress)

* [x] **Provider-Neutral Video Generation Layer**
  * [x] Canonical `VideoGenerationRequest`, `GeneratedVideoAsset`, and `VideoProviderCapabilities` contracts.
  * [x] `GenerativeVideoProvider` base interface and `FakeGenerativeVideoProvider` mock fixture.
  * [x] `HybridRenderRouter` with **guaranteed zero-cost deterministic fallback**.
  * [x] User-selectable generation policies (`FREE_DETERMINISTIC`, `BALANCED`, `PREMIUM_GENERATIVE`, `LOCAL_ONLY`).
* [ ] **First Generative Video Providers (Optional Integrations)**
  * [ ] Google Veo provider adapter via BYOK / Vertex AI API.
  * [ ] Hugging Face / Fal.ai / Replicate open video model adapters.
  * [ ] Video asset caching and content-addressable storage.
* [ ] **Timeline Asset Stitching**
  * [ ] Seamless blending of generative video clips with Remotion motion typography and audio narration.
  * [ ] Visual transition smoothing between procedural and generative scenes.

---

## 🔵 Stage 3: Ecosystem, Performance & Accessibility (Future Horizons)

* [ ] **Advanced Rendering Backends**
  * [ ] HyperFrames / WebGPU high-throughput procedural vector renderer adapter.
  * [ ] Local quantized diffusion video models (e.g. Wan2.1, HunyuanVideo) for offline premium generation.
* [ ] **Multimodal Accessibility**
  * [ ] Auto-generated closed captions (SRT / VTT) and multi-track narration.
  * [ ] Multilingual translation pipeline for instant visual explanation localization.
  * [ ] Cross-platform companion client (macOS / Linux support).
* [ ] **Community & Compute Infrastructure**
  * [ ] Sponsored inference pools for students and open-source researchers.
  * [ ] Community-contributed educational theme templates and visual motion libraries.
