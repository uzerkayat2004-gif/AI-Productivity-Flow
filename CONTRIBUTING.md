# 🤝 Contributing to AI Productivity Flow

Thank you for your interest in contributing to **AI Productivity Flow**! We welcome contributions from developers, researchers, designers, and educators.

---

## 🛠️ Development Environment Setup

### 1. Prerequisites
* **Python:** 3.10+ (tested on 3.11, 3.12, 3.13)
* **Node.js:** 18+ and npm 9+ (for Video Flow rendering components)
* **Git**
* **OS:** Windows 10 / 11 x64 or macOS 12+ (Apple Silicon & Intel)

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

# Install Python package in editable mode with test dependencies
pip install -e .
pip install pytest pytest-asyncio pytest-timeout cryptography
```

---

## 🧪 Running Tests

Before submitting a Pull Request, ensure all relevant test suites pass:

```bash
# Run Core Platform, Account Security & Download Verification Tests
python -m pytest tests/test_platform_layer.py tests/test_runtime_compatibility.py tests/test_account_auth.py tests/test_audio_video_download_and_player_fixes.py -v

# Run Version Consistency & Update Checker Tests
python -m pytest tests/test_version_consistency.py tests/test_update_checker.py -v

# Run Text Processing & Voice Polishing Regressions
python -m pytest tests/test_text_processing.py tests/test_capture_command_regressions.py tests/test_lfm_engine_local_runtime.py tests/test_voice_style_command_delivery.py -v

# Run NotebookLM Integration Tests
python -m pytest tests/test_notebooklm_account_switch_and_sync.py tests/test_video_flow_subscription_auth.py -v
```

---

## 📌 Versioning Policy

AI Productivity Flow adheres strictly to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/):

* **MAJOR (`X.0.0`)**: Incompatible API changes, breaking storage migrations, or major architectural overhauls.
* **MINOR (`1.X.0`)**: Backwards-compatible new features, new provider integrations, or new platform capabilities.
* **PATCH (`1.0.X`)**: Backwards-compatible bug fixes, performance improvements, and security patches.
* **PRERELEASE (`1.1.0-beta.1`)**: Test builds and release candidates. GitHub prereleases **must** be explicitly flagged with `--prerelease` so that website download links continue serving the latest verified stable release.

### Canonical Version Source
The single source of truth for the product version is:
```python
# src/voice_flow/_version.py
VERSION = "1.0.0"
```
All build scripts, installer definitions, CI workflows, and runtime endpoints derive from or validate against this file. The CI suite runs `tests/test_version_consistency.py` on every commit and PR.

---

## 🏗️ Architecture & Guiding Invariants

### 1. Free-First Architectural Invariant
* **Never make a paid API mandatory.**
* All video scenes must maintain a working deterministic fallback layout.
* Core Voice Flow dictation must remain functional offline using the bundled local Faster-Whisper model.

### 2. Multi-Account Privacy & Isolation
* User data, personal dictionaries, API keys, and NotebookLM sync tokens must remain completely isolated under the active profile in `~/.voice_flow/`.
* Switching accounts must never leak cached state or open database handles across accounts.

### 3. Media Download Predictability
* All exported media must be accessible in the user's standard OS folders (`Downloads`).
* File modification timestamps are synchronized upon completion to ensure immediate prominence at the top of Explorer / Finder under "Today".

---

## 📋 Pull Request Guidelines

1. **Keep Changes Focused:** One feature or bugfix per PR.
2. **Include Tests:** Add unit or regression test cases in `tests/` for any new logic.
3. **Preserve Compatibility:** Do not break existing desktop hotkeys, active styles, or storage contracts.
4. **Update CHANGELOG.md:** Document all user-facing changes and bug fixes under the upcoming version header.

---

## 📢 Community, Issues & Support

* 🐛 **Bug Reports & Feature Requests:** [GitHub Issues](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/issues)
* 💬 **Discussions & Feedback:** [GitHub Discussions](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/discussions)
* 🌐 **Project Website:** [https://ai-productivity-flow.vercel.app/](https://ai-productivity-flow.vercel.app/)
* 👤 **Maintainer:** [@uzerkayat2004-gif](https://github.com/uzerkayat2004-gif) (Uzer Kayat)
