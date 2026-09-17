<h1 align="center">🌊 AI Productivity Flow</h1>

<p align="center">
  <b>Turn documents into videos, text into audio, and speech into text — directly from your desktop.</b><br>
  <i>A free, lightweight, privacy-focused desktop assistant that operates seamlessly inside every app you use.</i>
</p>

<p align="center">
  <a href="https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases"><img src="https://img.shields.io/badge/Release-v2.1%20Beta-orange.svg" alt="Release: v2.1 Beta"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20(Tested)%20%7C%20macOS%20(Preview)-0078D4.svg" alt="Platform: Windows & macOS">
  <img src="https://img.shields.io/badge/Dictation-100%25%20Local%20Whisper-success.svg" alt="100% Local Whisper Dictation">
  <img src="https://img.shields.io/badge/Cost-100%25%20Free%20%26%20Open%20Source-blue.svg" alt="100% Free & Open Source">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License: Apache 2.0"></a>
</p>

<p align="center">
  <img src="docs/assets/ai-productivity-flow-hero.png" alt="AI Productivity Flow Interface Banner" width="920">
</p>

---

## ⚡ Why AI Productivity Flow?

You shouldn't have to leave the app you're working in just to use AI. Flow operates silently in the background of your desktop:

* 🎬 **Video Flow** — Turn any note, article, or PDF into an animated 1080p explainer video with voiceover and captions in seconds.
* 🎧 **Audio Flow** — Highlight any text on screen to listen in warm, natural human voices with real-time word tracking.
* 🎙️ **Voice Flow** — Speak naturally to type clean, polished text directly into Slack, Word, Gmail, or VS Code.
* 📓 **NotebookLM Sync** — Connect your Google research notebooks directly to your desktop workflow.
* 🔒 **100% Local Dictation** — Speech recognition runs offline on your processor. Your voice never leaves your PC.

---

## 🚀 Quick Install (60 Seconds)

### 🪟 Windows 10 & 11 (Tested & Verified)
Open **PowerShell** (no Administrator required) and paste:
```powershell
irm https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.ps1 | iex
```
*Prefer a classic setup file?* Download **[`AI-Productivity-Flow-Setup-x64.exe`](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases)** from GitHub Releases.

### 🍎 macOS 12+ (Community Preview)
Open **Terminal** and paste:
```bash
curl -fsSL https://raw.githubusercontent.com/uzerkayat2004-gif/AI-Productivity-Flow/main/scripts/install.sh | bash
```

> [!WARNING]
> **macOS Notice**: macOS support is in Community Preview and pending full physical hardware testing. Windows 10/11 x64 is the primary verified platform.

---

## 🌟 The Three Pillars of Flow

### 1. 🎬 Video Flow — Turn Notes & Documents into 1080p Explainer Videos

Transform dense articles, notes, or documentation into visually captivating, animated 1080p MP4 videos with synchronized voiceover.

<p align="center">
  <video src="https://github.com/user-attachments/assets/61afd3f3-d75b-4cff-8010-6a7f0d8657a9" controls width="100%"></video>
</p>

* **Any Content**: Highlight text, paste notes, or drag-and-drop documents (`.pdf`, `.docx`, `.txt`, `.md`, `.csv`, `.json` up to 8 MB).
* **Two Modes**: Choose **Summary Mode** for rapid executive briefings or **Full Mode** for deep educational breakdowns.
* **15 Dynamic Visual Treatments**: Automatically creates title cards, animated flowcharts, timelines, metric counters, 3D WebGL scenes, and recap grids.
* **100% Free & Local**: Bundled deterministic renderer builds finished 1080p MP4 videos locally. Zero paid video API subscriptions required.

---

### 2. 🎧 Audio Flow — Turn Any Text Into Speech & Screen Reader

Turn any web page, research paper, code comment, or document into an instant personal audio track.

<p align="center">
  <video src="https://github.com/user-attachments/assets/d1bc3228-548b-43a0-882d-d81665ee20a3" controls width="100%"></video>
</p>

* **Highlight & Listen**: Select any text on screen (drag >= 6px) to bring up the floating player bar at your cursor.
* **Real-Time Word Tracking**: Words highlight in yellow as they are spoken, making it effortless to follow along.
* **Playback Controls**: Adjust speed (0.75x to 2.0x), scrub the waveform bar, skip forward/back, or download the MP3 with one click.
* **Spoken AI Summaries**: Choose Quick, Standard, or Detailed summaries to hear key takeaways fast.
* **Free Neural Voices**: Ships with ultra-realistic Microsoft Edge Neural voices out of the box with zero API keys required.

---

### 3. 🎙️ Voice Flow — Talk Instead of Typing

Stop typing thousands of words every day. Speak naturally, and Flow transcribes and types for you anywhere your cursor is placed.

* **Simple Triggers**: Hold your **Middle Mouse Button** (scroll wheel) or press `Ctrl + Win` (`Cmd + Ctrl` on Mac) while speaking. Release to paste. Quick-tap toggles continuous dictation.
* **Cleans Hesitations**: Automatically removes stutters, pauses, and filler words ("um", "uh", "like") while keeping your exact meaning.
* **App-Aware Formatting**: Formats formal paragraphs in Outlook/Word, casual messaging in Slack/Teams, and code-friendly identifiers in VS Code.
* **Personal Dictionary**: Add your name, specialized jargon, or shortcuts (e.g. saying or typing `myzoom` expands to your Zoom link).
* **100% Local Speech AI**: Powered by bundled Faster-Whisper (`base.en` CPU int8). Audio is processed locally on your machine.

---

## ⚡ Connected Capabilities

| Feature | What it does |
| :--- | :--- |
| 📓 **NotebookLM Sync** | One-click Google login to bring research notes, study guides, and audio discussions into your desktop flow. |
| 🔑 **Free & BYOK** | 100% free out of the box (local speech + free Edge voices). Optionally connect OpenAI, Claude, Gemini, DeepSeek, or local Ollama keys. |
| 🎨 **Adaptive Themes** | Automatically matches your operating system's Dark or Light theme with an instant toggle on the dashboard. |

---

## ⌨️ Shortcut Cheat Sheet

| Action | Shortcut / Gesture |
| :--- | :--- |
| **Explainer Video & Audio Reader** | **Select / Highlight text** on screen (Floating bar appears) |
| **Talk to Type (Voice Flow)** | **Middle Mouse Button** (Hold & Release) or `Ctrl + Win` (`Cmd + Ctrl` on Mac) |
| **Settings & History Dashboard** | Open **`http://127.0.0.1:8991`** in any browser |

---

## 🔒 Privacy First

* 🛡️ **Offline Dictation**: Voice dictation is processed locally on your CPU/GPU. Your raw microphone audio is never sent to the cloud.
* 🛡️ **No Background Listening**: Microphone only activates while holding down the trigger button.
* 🛡️ **Local Storage**: Transcripts, personal dictionary, and settings are stored locally on your machine in `~/.voice_flow/voice_flow.db`.
* 🛡️ **Zero Tracking**: No telemetry, analytics, or user profiling.

---

## 🛠️ Developer Setup & Manual Build

<details>
<summary><b>Click here to view Developer & Source Setup Guide</b></summary>

### Prerequisites
* Windows 10/11 x64 or macOS 12+
* Python 3.10+ (tested on 3.11, 3.12, 3.13, 3.14)
* FFmpeg (bundled in Windows installer)

### Manual Installation
```bash
git clone https://github.com/uzerkayat2004-gif/AI-Productivity-Flow.git
cd AI-Productivity-Flow

python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS:
source .venv/bin/activate

pip install -e .
```

### Running Locally
* **Windows**: Run `.\run_voice_flow.bat` or launch `VoiceFlowLauncher.vbs`.
* **macOS**: Run `python3 -m voice_flow.main`.

### Running Tests
```bash
# Contract, Video Flow, Audio Flow, and core feature test suites
pytest tests/test_platform_layer.py tests/test_runtime_compatibility.py tests/test_video_flow_engine.py tests/test_insights_deep.py -v
```

### Technical Documentation
* [`docs/CURRENT_PRODUCT_MAP.md`](docs/CURRENT_PRODUCT_MAP.md) — Comprehensive technical architecture map
* [`docs/PRODUCT_FACTS.md`](docs/PRODUCT_FACTS.md) — Verified technical specifications
* [`VIDEO_FLOW_ARCHITECTURE.md`](VIDEO_FLOW_ARCHITECTURE.md) — Video Flow rendering pipeline deep dive

</details>

---

## 📢 Community & Support

* 📦 **Releases**: [GitHub Releases](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases)
* 🐛 **Issues**: [Bug Reports & Requests](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues)
* 💬 **Website**: [Productivity Flow Web Page](https://uzerkayat2004-gif.github.io/AI-Productivity-Flow/)

---

## 📄 License

Open-source under the **Apache License 2.0**. See the [`LICENSE`](LICENSE) file for details.  
Third-party notices are cataloged in [`release/THIRD_PARTY_NOTICES.txt`](release/THIRD_PARTY_NOTICES.txt).
