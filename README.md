# 🌊 Flow — Open-Source Multimodal Information Transformation

> **Zero-friction information transformation across Speech, Audio, and Video directly from your desktop workflow.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows_10_%2F_11-blue.svg)]()
[![Tests](https://img.shields.io/badge/Tests-47%20Passed%20(100%25)-success.svg)]()

---

## 💡 What is Flow?

**Flow** is a native desktop productivity platform engineered around a simple, powerful philosophy:

> **You should never need to open the main application to receive value.**

Whether you are writing code in VS Code, researching papers in Chrome, analyzing data in Excel, or chatting in Slack, Flow sits silently in the background. With a single gesture (middle mouse click, hotkey, or text highlight), Flow transforms information instantly:

```text
User selects text anywhere (Browser / IDE / Document)
                        ↓
                 Invoke Flow
         _______________|_______________
        |               |               |
   Voice Flow      Audio Flow      Video Flow
 (Speech → Text) (Text → Audio)  (Text → Video)
        ↓               ↓               ↓
  Direct Paste    Spoken Audio   Visual Explainer
```

---

## 🌟 The Three Pillars of Flow

### 1. 🎙️ Voice Flow (Speech → Text & Intelligent Dictation)
* **Zero-Latency Triggers:** Middle Mouse Button (scroll wheel click) or `Ctrl + Win` / `Win + Ctrl` hotkey.
* **Push-to-Talk & Toggle Tap:** Hold (>0.30s) to speak and release to paste, or quick-tap (<0.30s) to toggle continuous dictation.
* **Active Window Style Engine:** Automatically senses the foreground application window and adapts formatting (e.g., Markdown/snake_case in VS Code, professional tone in Slack/Email, natural phrasing in browsers).
* **Local Faster-Whisper Engine:** Local offline transcription with dictionary prompt-biasing and dual-pass VAD fallback.
* **Intelligent Auto-Refinement:** AI-powered grammar and disfluency cleanup with strict code-symbol and keyword preservation.
* **Active Window Text Injection:** Direct Win32 clipboard injection with automatic modifier key state clearing and terminal (`Shift+Insert`) support.

### 2. 🎧 Audio Flow (Selected Text → Spoken Speech & Screen Reader)
* **Screen Highlight Reading:** Highlight text anywhere to immediately hear it read aloud with synchronized yellow tracking.
* **Interactive Floating Player:** Waveform scrub bar, speed adjustment (0.8x–2.0x), play/pause, and quick stop.
* **Multi-Provider TTS:** Free Microsoft Edge Neural voices, Google Cloud TTS, Gemini AI Audio, Azure Speech, ElevenLabs, Deepgram Aura, and offline Windows SAPI5.

### 3. 🎬 Video Flow (Selected Text → Source-Grounded Visual Explanation)
* **Source-Grounded Explanation:** Converts dense text, code, or documents into structured, animated 16:9 explainer videos.
* **Video Flow Brain:** Analyzes evidence claims, extracts key entities, designs pedagogical scene structures, and generates synchronized narration scripts.
* **Hybrid Rendering Engine:** Combines deterministic 2D motion graphics, 3D WebGL scenes, Remotion animations, and generative video clips with guaranteed zero-cost fallbacks.

---

## 🚦 Project Status

| Subsystem | Component | Status | Description |
| :--- | :--- | :---: | :--- |
| **Voice Flow** | Core Speech-to-Text | ✅ Implemented | 64-bit Win32 hook, Faster-Whisper, local prompt-biasing |
| **Voice Flow** | Active Window Style Engine | ✅ Implemented | Title/class detection, category presets (Formal/Casual/Code) |
| **Voice Flow** | Auto-Startup & Watchdog | ✅ Implemented | Silent Windows startup, process health supervisor |
| **Audio Flow** | Text-to-Speech Engine | ✅ Implemented | Edge Neural, Google, ElevenLabs, Deepgram, SAPI5 |
| **Audio Flow** | Highlight Tracker Widget | ✅ Implemented | Synchronized text highlight & floating audio controls |
| **Video Flow** | Video Flow Brain | ✅ Implemented | Evidence grounding, scene planning, diversity validation |
| **Video Flow** | Deterministic 2D/3D Renderer | ✅ Implemented | React/Remotion motion scenes, Canvas/SVG animations |
| **Video Flow** | Hybrid Render Router | ✅ Implemented | Provider-neutral generative video routing & fallback contracts |
| **Video Flow** | Benchmark Suite | ✅ Implemented | 12 domain benchmark fixtures, multi-metric scoring harness |
| **Video Flow** | Generative Video Provider | 🚧 In Progress | Integration seams ready; testing with mock provider |
| **Platform** | Insights Telemetry | ✅ Implemented | 28-day activity heatmap, speedometer gauge, app breakdown |
| **Platform** | Custom Dictionary & Snippets | ✅ Implemented | Trigger expansion (`myemail -> me@company.com`), tag filtering |
| **Platform** | Multi-Key Connection Hub | ✅ Implemented | BYOK multi-provider manager with load balancing |

---

## 🏗️ Architectural Philosophy: Hybrid Rendering

Video Flow is architected as a **hybrid rendering pipeline**. It avoids black-box text-to-video APIs in favor of structured comprehension:

```text
Selected Content / Source Text
              ↓
   Evidence & Source Grounding (Claims, Entities, Spans)
              ↓
       Video Flow Brain (Pedagogical Scene Planning)
              ↓
  Scene Programs & Visual Direction (Motion, Layout, Timing)
              ↓
      Hybrid Render Router
   ↙           ↓            ↘
Procedural   WebGL/3D   Generative Video (Veo / Future)
 Remotion                 [Optional Enhancement]
    ↓          ↓             ↓
   ───────────────────────────
              ↓
    Narration & Audio Sync
              ↓
      Automated QA & Repair
              ↓
     Final Explainer Video
```

### 🆓 Free-First Guarantee
Flow is built so that **no user is ever blocked by a paywall**.
- When generative video APIs are unavailable or unconfigured, the **Hybrid Render Router** automatically falls back to deterministic procedural Remotion and 2D/3D Canvas rendering.
- You never need a paid API key or cloud billing to generate high-quality explanation videos.

---

## 📦 Installation & Setup

### Prerequisites
* **Operating System:** Windows 10 or 11 (64-bit)
* **Python:** Version 3.10+ (tested on Python 3.14)
* **Node.js:** Version 18+ (for Remotion video renderer)

### Quick Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/uzerkayat2004-gif/Voice-Flow.git
   cd Voice-Flow
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -e .
   ```

3. **Install Video Flow Renderer dependencies:**
   ```bash
   cd video_flow_renderer
   npm install
   cd ..
   ```

4. **One-Click Desktop & Auto-Startup Installation:**
   ```bat
   setup_desktop_app.bat
   ```
   *Registers Flow in Windows Startup and creates Desktop shortcuts for silent background startup on boot.*

---

## 🚀 Running Flow

* **Silent Background Mode (Recommended):**
  Double-click `VoiceFlowLauncher.vbs` or run:
  ```bat
  run_voice_flow.bat
  ```
* **Interactive Console Mode:**
  ```bat
  run_voice_flow.bat --console
  ```
* **Check Background Watchdog Status:**
  ```bash
  python -m voice_flow.watchdog --status
  ```
* **Open Web Dashboard:**
  Navigate to `http://127.0.0.1:8991` in your browser.

---

## 🧪 Testing & Verification

Run the comprehensive automated test suite (all tests execute offline with zero paid API calls):

```bash
# Run all core tests
python -m pytest tests/test_insights_deep.py tests/test_history_features.py tests/test_dictionary_safety.py tests/test_style_system.py tests/test_provider_management.py tests/test_watchdog_and_startup.py tests/test_hybrid_render_routing.py tests/test_video_flow_benchmarks.py -s

# Run Video Flow engine tests
python -m pytest tests/test_video_flow.py tests/test_video_flow_models.py tests/test_video_flow_motion.py tests/test_video_flow_providers.py tests/test_video_flow_themes.py -s

# Run Video Flow Renderer TypeScript Typecheck
cd video_flow_renderer && npm run typecheck
```

---

## 🔒 Privacy & Local-First Design

* **Local Speech-to-Text:** Whisper runs locally on your CPU/GPU. No audio leaves your machine unless you configure an external speech provider.
* **BYOK (Bring Your Own Key):** All AI credentials are encrypted and stored locally in `~/.voice_flow/voice_flow.db`. Keys are never transmitted to third-party telemetry servers.
* **Consent-Gated Processing:** Source text is only sent to external LLMs if you explicitly select that model and authorize the request.

---

## 🤝 Sponsors & Compute Partners

Flow is designed so its core functionality remains 100% free and useful without paid inference. We are actively interested in compute, API-credit, infrastructure, and research partnerships to accelerate open multimodal AI accessibility:

* 🎥 **Video Inference Partnerships:** Integrating next-generation generative video models into our hybrid router.
* ⚡ **GPU & Cloud Compute:** Distributed rendering clusters and open-weights model hosting.
* 🧠 **LLM & Speech Inference:** API credit support for open-source research and educational explanation generation.
* 🎓 **Accessibility & Education:** Partnering with academic institutions to make research papers and dense educational material accessible in multimodal formats.

*If your organization is interested in supporting open-source multimodal accessibility, please open an issue or contact the maintainers.*

---

## 📄 License

This project is licensed under the **Apache License 2.0**. See the [`LICENSE`](LICENSE) file for details.

### Third-Party Licenses
Third-party libraries used in Flow remain subject to their respective licenses:
* Remotion (`video_flow_renderer`) is distributed under the Remotion Company License.
* Faster-Whisper, SoundDevice, PyWebView, React, and other dependencies remain under their respective MIT / Apache / BSD licenses.
