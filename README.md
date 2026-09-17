# 🌊 AI Productivity Flow — Open-Source Multimodal Desktop Transformation

> **Zero-friction information transformation across Speech, Audio, and Video directly from your desktop workflow.**

<p align="center">
  <a href="https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/actions/workflows/ci.yml"><img src="https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/actions/workflows/ci.yml/badge.svg" alt="CI & Multi-Platform Build"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%20(Tested)%20%7C%20macOS%20(Preview)-0078D4.svg" alt="Platform: Windows & macOS">
  <img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Status-Beta%20v2.1-orange.svg" alt="Status: Beta">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License: Apache 2.0"></a>
</p>

---

## ⚡ Quick Download & Install (One-Liner Terminal Commands)

Install AI Productivity Flow in seconds. The automated installer configures an isolated environment, verifies dependencies, provisions speech models and rendering engines, registers desktop shortcuts, and activates resilient background auto-start.

### 🪟 Windows 10 / 11 (Primary & Fully Tested)
Run this command in **PowerShell** (no Administrator privileges required):

```powershell
irm https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.ps1 | iex
```

*Prefer a standalone installer?* Download the pre-built **`AI-Productivity-Flow-Setup-x64.exe`** directly from our **[GitHub Releases](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases)**.

---

### 🍎 macOS 12+ Apple Silicon & Intel (Community Preview)
Run this command in **Terminal**:

```bash
curl -fsSL https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.sh | bash
```

> [!WARNING]
> **⚠️ Note for macOS Users (Experimental / Untested Disclaimer):**
> macOS support is currently in **Community Preview / Experimental** mode and **has not yet undergone full physical hardware validation** across all Apple hardware and macOS versions. You may encounter system permission prompts (Accessibility, Microphone, Input Monitoring), audio input latency, or minor hotkey quirks.
> 
> **Windows 10/11 x64 is the primary, production-verified platform.** If you encounter any bugs, crashes, or quirks on macOS, please help us improve by reporting them on [GitHub Issues](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues).

---

## 💡 What is AI Productivity Flow?

**AI Productivity Flow** is a native desktop productivity platform engineered around a core principle:

> **You should never need to open the main application window to receive value.**

Whether you are writing code in VS Code, researching papers in Chrome, analyzing spreadsheets in Excel, or communicating in Slack, Flow operates silently beside your workflow. With a single gesture (middle mouse button, hotkey, or text selection), Flow transforms information instantly:

```text
User selects text anywhere (Browser / IDE / Document / Chat)
                            ↓
                     Invoke Flow
          __________________|__________________
         |                  |                  |
    🎙 Voice Flow      🎧 Audio Flow      🎬 Video Flow
   (Speech → Text)    (Text → Audio)     (Text → Video)
         ↓                  ↓                  ↓
  Direct Paste in App  Spoken Audio Bar  Visual Explainer (MP4)
```

---

## 🌟 The Core Upgrades & Feature Pillars

### 1. 🎙️ Voice Flow — Speech → Polished Text & Intelligent Dictation
* **Zero-Latency Triggers:** Middle Mouse Button (scroll-wheel click) or `Ctrl + Win` (Windows) / `Cmd + Ctrl` (macOS).
* **Push-to-Talk & Tap-to-Toggle:** Hold (>0.30s) to speak and release to paste, or quick-tap (<0.30s) to toggle continuous dictation.
* **Local Faster-Whisper Transcription:** Fast offline transcription powered by bundled `base.en` (CPU int8). Dictation audio never leaves your machine.
* **Active Window Style Engine:** Automatically senses the active foreground window and formats text contextually:
  * *VS Code / IDE:* Formats as code-friendly identifiers (`snake_case`, `camelCase`) and Markdown.
  * *Slack / Teams / Chat:* Natural, concise phrasing.
  * *Email / Outlook:* Professional, polished prose.
* **Intelligent AI Auto-Refinement:** Cleans disfluencies, pauses, and grammar while strictly preserving code symbols, keywords, and domain acronyms.
* **Custom Personal Dictionary & Snippets:** Add custom acronyms, technical terms, and trigger expansions (e.g., `myemail` → `me@company.com`). Longer triggers take priority; code spans are protected.
* **Telemetry & Insights:** 28-day activity heatmap, speedometer WPM gauge, estimated time saved, and per-app breakdowns.

---

### 2. 🎧 Audio Flow — Selected Text → Natural Spoken Audio & Screen Reader
* **Screen Highlight Reading:** Highlight text anywhere on screen to hear it read aloud immediately with synchronized yellow word tracking.
* **Compact Floating Player Bar:** Includes a real-time waveform scrub bar, skip forward/back controls, playback speed adjustment (0.8x to 2.0x), and one-click MP3 download.
* **Spoken AI Summaries:** Summarize lengthy text into spoken audio at three selectable depths: **Quick**, **Standard**, or **Detailed**.
* **Multi-Provider TTS Engine:**
  * **Free Microsoft Edge Neural Voices:** High-fidelity, natural voices out of the box with zero API key or setup required.
  * **Google Cloud TTS & Gemini AI Audio:** Includes latest preview voices (`gemini-3.1-flash-tts-preview:Orus`, `Puck`, etc.).
  * **ElevenLabs & Deepgram Aura:** Studio-grade ultra-realistic voices.
  * **OpenAI & NVIDIA:** High-performance neural voice endpoints.

---

### 3. 🎬 Video Flow — Text or Documents → Source-Grounded Visual Explainers
* **Dense Content to 1080p Video:** Highlight text, paste notes, or drag-and-drop documents (`.txt`, `.md`, `.pdf`, `.docx`, `.html`, `.csv`, `.json`). Video Flow plans an educational breakdown, designs a multi-scene visual sequence, narrates it, and renders a finished 1080p MP4 with synchronized captions.
* **Educational Scene Planning:** Analyzes key concepts, evidence claims, and entities using your connected AI model.
* **Creative Director (15 Dynamic Visual Treatments):** Avoids monotonous slides by varying scenes with:
  * Title cards and concept highlights
  * Animated process flowcharts and timelines
  * Data metrics and animated counters
  * 3D WebGL scenes and spatial visualizations
  * Waveform demos and recap grids
* **Hybrid & Deterministic Rendering:** Browser-based rendering powered by bundled HyperFrames, Narova, and WebGL modules.
* **Free-First Fallback Guarantee:** When external generative video APIs are not configured, Video Flow automatically falls back to deterministic procedural rendering. **You are never paywalled.**
* **Built-in Player & Export:** Watch in the lightweight on-screen player with speed controls, scrubber, captions toggle, and local MP4 file saving.

---

### 4. 📓 NotebookLM Durable Session Integration
* **Native NotebookLM Integration:** Deep pipeline support for Google NotebookLM session workflows.
* **Durable Session Management:** Automatic cookie refresh, account switching, and resilient session recovery.
* **Chrome 127+ App-Bound Encryption Support:** Seamlessly handles modern Chrome cookie encryption schemes and provides accurate diagnostics for expired or invalid sessions.

---

### 5. 🤖 Multi-Model / BYOK Connection Hub
* **Bring Your Own Key (BYOK):** AI Productivity Flow ships without proprietary developer keys. You retain full control over your cloud inference.
* **Multi-Provider Support:**
  * **OpenAI:** GPT-4o, GPT-4o-mini, o1, o3-mini
  * **Anthropic:** Claude 3.5 Sonnet, Claude 3.5 Haiku
  * **Google Gemini:** Gemini 2.0 Flash, Gemini 1.5 Pro, Gemini 1.5 Flash
  * **NVIDIA NIM:** Nemotron, Llama 3.1
  * **Groq, Mistral, DeepSeek, Local Ollama:** Full support for custom OpenAI-compatible endpoints.
* **Resilient Failover & Load Balancing:** Automatic round-robin distribution and failover pools ensure your dictation and planning never stall on API rate limits.
* **Consent Gates:** Source text is only sent to external LLMs when explicitly initiated and authorized by the user.

---

### 6. 🎨 Dynamic UI Themes & Cross-Platform Adaptation
* **Adaptive Dark & Light Themes:** The web dashboard, floating flow bar, and media players automatically detect and adapt to your OS color scheme, with instant manual overrides.
* **Platform-Native Ergonomics:**
  * *Windows:* Win32 low-level hooks, system tray integration, silent background watchdog supervisor, and zero-console startup.
  * *macOS:* Native menu bar item, Cocoa accessibility clipboard bridge, and adapted keyboard hints (`Cmd` vs `Win`).

---

## 🚦 Project Status & Component Matrix

| Subsystem | Component | Status | Description |
| :--- | :--- | :---: | :--- |
| **Voice Flow** | Local Speech-to-Text | ✅ Verified | Bundled Faster-Whisper `base.en`, CPU int8, zero cloud leaks |
| **Voice Flow** | Active Window Style Engine | ✅ Verified | Automatic application sensing (VS Code, Slack, Email, Browser) |
| **Voice Flow** | Auto-Startup & Watchdog | ✅ Verified | Dual-layer autostart (Registry + Startup Folder), silent watchdog supervisor |
| **Audio Flow** | Highlight Screen Reader | ✅ Verified | Cursor-tracking floating player bar with synchronized yellow tracking |
| **Audio Flow** | Multi-Provider TTS | ✅ Verified | Free Edge Neural, Google, Gemini Audio, ElevenLabs, Deepgram, NVIDIA |
| **Video Flow** | Pedagogical Scene Brain | ✅ Verified | Evidence grounding, concept extraction, 15 visual treatments |
| **Video Flow** | Deterministic Renderer | ✅ Verified | HyperFrames / Narova / WebGL browser-based 1080p MP4 rendering |
| **Video Flow** | Free-First Fallback Router | ✅ Verified | Guaranteed zero-cost rendering without external paid video APIs |
| **NotebookLM** | Durable Sessions Pipeline | ✅ Verified | Chrome 127+ App-Bound encryption support, cookie refresh, error diagnostics |
| **Platform** | Multi-Key BYOK Manager | ✅ Verified | OpenAI, Anthropic, Gemini, NVIDIA, Groq, Mistral, DeepSeek, Ollama |
| **Platform** | Insights & Telemetry | ✅ Verified | 28-day activity heatmap, speedometer WPM gauge, application breakdown |
| **Platform** | macOS Support | 🚧 Preview | Native app bundle, accessibility integration (physical QA in progress) |

---

## 📦 Manual Setup & Developer Guide

### Prerequisites
* **Operating System:** Windows 10/11 x64 (Primary) or macOS 12+ (Community Preview)
* **Python:** 3.10+ (tested on 3.11, 3.12, 3.13, 3.14)
* **Node.js:** 18+ (optional, for Remotion rendering components)

### Manual Installation from Source

1. **Clone the repository:**
   ```bash
   git clone https://github.com/uzerkayat2004-gif/AI-Productivity-Flow.git
   cd AI-Productivity-Flow
   ```

2. **Set up Python virtual environment & install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # macOS:
   source .venv/bin/activate

   pip install -e .
   ```

3. **Install Video Flow Renderer dependencies (optional for local video):**
   ```bash
   cd video_flow_renderer
   npm install
   cd ..
   ```

4. **Register Desktop App & Auto-Start:**
   * **Windows:** Run `setup_desktop_app.bat` to register startup entries and create Start Menu shortcuts.
   * **macOS:** Build the standalone app bundle with `python scripts/build_macos_app.py`.

---

## 🚀 Running AI Productivity Flow

### On Windows
* **Silent Background Mode (Recommended):**
  Double-click `VoiceFlowLauncher.vbs` or run:
  ```bat
  .\run_voice_flow.bat
  ```
* **Interactive Console Mode:**
  ```bat
  .\run_voice_flow.bat --console
  ```
* **Check Background Watchdog Status:**
  ```bash
  python -m voice_flow.watchdog --status
  ```

### On macOS
* **Using the Pre-built `.app` Bundle:**
  1. Download `VoiceFlow-macOS-unsigned.zip` from GitHub Releases or run `python scripts/build_macos_app.py`.
  2. Move `Voice Flow.app` to `/Applications`.
  3. Clear the macOS Gatekeeper quarantine attribute:
     ```bash
     xattr -cr "/Applications/Voice Flow.app"
     ```
  4. Launch `Voice Flow.app` and grant **Microphone**, **Accessibility**, and **Input Monitoring** permissions when prompted.
* **Running from Terminal:**
  ```bash
  python3 -m voice_flow.main
  ```

### Web Dashboard (All Platforms)
Open **`http://127.0.0.1:8991`** in any browser to configure providers, manage custom dictionary entries, view telemetry insights, and adjust audio/video preferences.

---

## 🧪 Testing & Verification

Run the comprehensive offline test suite across platforms (all tests execute offline with zero paid API calls):

```bash
# Platform Abstraction & Cross-Platform Contract Tests (Windows & macOS)
pytest tests/test_platform_layer.py tests/test_runtime_compatibility.py -v

# Video Flow Engine, NotebookLM & Media Player Tests
pytest tests/test_video_flow_engine.py tests/test_video_flow_providers.py tests/test_video_flow_contracts.py tests/test_video_flow_notebooklm.py tests/test_audio_video_download_and_player_fixes.py -v

# Core Feature & Subsystem Tests (Insights, History, Dictionary Safety, Style Presets)
pytest tests/test_insights_deep.py tests/test_history_features.py tests/test_dictionary_safety.py tests/test_style_system.py -v
```

---

## 🔒 Privacy & Local-First Architecture

* **Local Speech Recognition:** Dictation is transcribed locally on your CPU/GPU using the bundled Whisper model. Audio is never sent to external servers.
* **Local Database:** Transcripts, dictionary words, and history are stored locally in SQLite at `~/.voice_flow/voice_flow.db`.
* **Zero Telemetry Tracking:** We do not track your usage, collect telemetry, or store your text.
* **Consent-Gated External AI:** Source text is only transmitted to external LLM providers when you explicitly trigger cloud features (AI Polish, Spoken Summaries, or Video Planning).

---

## 📢 Information Channel & Community

* **GitHub Releases:** [Releases & Changelogs](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases)
* **Issue Tracker:** [Bug Reports & Feature Requests](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues)
* **Product Documentation:** Detailed technical documentation lives under [`docs/`](docs/):
  * [`docs/CURRENT_PRODUCT_MAP.md`](docs/CURRENT_PRODUCT_MAP.md) — Comprehensive technical architecture map
  * [`docs/PRODUCT_FACTS.md`](docs/PRODUCT_FACTS.md) — Verified product specifications and supported subsystems
  * [`VIDEO_FLOW_ARCHITECTURE.md`](VIDEO_FLOW_ARCHITECTURE.md) — Deep-dive into the Video Flow rendering pipeline

---

## 📄 License

This project is licensed under the **Apache License 2.0**. See the [`LICENSE`](LICENSE) file for details.

### Third-Party Notices
Third-party libraries used in AI Productivity Flow remain subject to their respective open-source licenses:
* Faster-Whisper, SoundDevice, PyWebView, React, and Three.js remain under MIT / Apache / BSD licenses.
* Attributions are cataloged in [`release/THIRD_PARTY_NOTICES.txt`](release/THIRD_PARTY_NOTICES.txt).
