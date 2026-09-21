# 🤝 Contributing to AI Productivity Flow

Thank you for your interest in contributing to **AI Productivity Flow**! We welcome contributions from developers, researchers, designers, and educators.

---

## 🛠️ Development Environment Setup

### 1. Prerequisites
* **Python:** 3.10+ (tested on 3.11, 3.12, 3.13, 3.14)
* **Node.js:** 18+ and npm 9+ (for Video Flow Remotion renderer)
* **Git**
* **OS:** Windows 10 / 11 x64 (primary production tier) or macOS 12+ (community preview)

### 2. Initial Setup
```bash
# Clone the repository
git clone https://github.com/uzerkayat2004-gif/AI-Productivity-Flow.git
cd AI-Productivity-Flow

# Create virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Install Python package in editable mode
pip install -e .

# Install Remotion renderer dependencies
cd video_flow_renderer
npm install
cd ..
```

---

## 🧪 Running Tests

Before submitting a Pull Request, ensure all relevant test suites pass:

```bash
# Run Core Platform, Account Security & Download Verification Tests
python -m pytest tests/test_platform_layer.py tests/test_runtime_compatibility.py tests/test_account_auth.py tests/test_audio_video_download_and_player_fixes.py -v

# Run Text Processing & Voice Polishing Regressions
python -m pytest tests/test_text_processing.py tests/test_capture_command_regressions.py tests/test_lfm_engine_local_runtime.py tests/test_voice_style_command_delivery.py -v

# Run NotebookLM Integration Tests
python -m pytest tests/test_notebooklm_account_switch_and_sync.py tests/test_video_flow_subscription_auth.py -v

# Typecheck the Remotion Renderer
cd video_flow_renderer && npm run typecheck && cd ..
```

---

## 🏗️ Architecture & Guiding Invariants

### 1. Free-First Architectural Invariant
* **Never make a paid API mandatory.**
* All video scenes must maintain a working deterministic fallback (`procedural_2d`, `procedural_3d`, or `remotion`).
* Core Voice Flow dictation must remain 100% functional offline using the bundled local Whisper model.

### 2. Multi-Account Privacy & Isolation
* User data, personal dictionaries, API keys, and NotebookLM sync tokens must remain completely isolated under their active user profile in `~/.voice_flow/`.
* Switching accounts must never leak cached state or open database handles.

### 3. Media Download Predictability
* All exported media must be accessible in the user's standard Windows folders (`Downloads`, `Videos`, `Music`).
* File modification timestamps are synchronized upon completion to ensure immediate prominence at the top of Explorer under "Today".

---

## 📋 Pull Request Guidelines

1. **Keep Changes Focused:** One feature or bugfix per PR.
2. **Include Tests:** Add unit or regression test cases in `tests/` for any new logic.
3. **Preserve Compatibility:** Do not break existing desktop hotkeys, active styles, or storage contracts.
4. **Documentation:** Update `README.md` or relevant architecture docs if user-facing behavior changes.

---

## 📢 Community, Issues & Support

* 🐛 **Bug Reports & Feature Requests:** [GitHub Issues](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues)
* 💬 **Discussions & Feedback:** [GitHub Discussions](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/discussions)
* 🌐 **Project Website:** [https://ai-productivity-flow.vercel.app/](https://ai-productivity-flow.vercel.app/)
* 👤 **Maintainer:** [@uzerkayat2004-gif](https://github.com/uzerkayat2004-gif) (Uzer Kayat)
