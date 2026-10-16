# Changelog

All notable changes to **AI Productivity Flow** are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## 1.0.2 - 2026-10-16

### Voice Flow
- **Local S1-mini polish (VF-1)**: Voice Flow can clean up dictation on the device with the S1-mini model, through llama-cpp or a local llama-server, with a factual safety gate that rejects output that drops or invents content.
- **Faster, steadier speech recognition**: The Nemotron recognizer runs in its own worker process, stays warm between dictations, and re-decodes short recordings with full context for better accuracy.
- **Smarter voice commands**: Task-aware time limits, safer command checks, email layouts that handle "Hey/He <Name>," greetings, and tolerance for common mishearings of "Hey Voice Flow".

### Dictionary rebuilt
- **Words and Replacements, nothing else**: A saved Word (a name or special term such as Kubernetes) is sent to the speech recognizer as a bias term, given to the cloud polisher as a preferred spelling, and afterwards fixes only its own spelling, keeping plural and possessive endings. A Replacement ("Heard as") swaps only the exact misheard phrase the user wrote.
- **No automatic learning**: The dictionary no longer learns from dictation or from polished text. The learning modules were removed.
- **Same result with polishing on or off**: One deterministic pass; links, emails, and code are never changed.
- **Ordinary and built-in words refused**: Words like "meeting" or "hey", and the "Voice Flow" wake phrase, cannot be saved as dictionary words.
- **Recognizer biasing**: Nemotron speech context, faster-whisper hotwords, Deepgram keyterms, and cloud prompts now receive the user's terms.
- **One-time reset**: On first start the old dictionary rows, replacements, and learning data are saved to `dictionary-backup-before-rebuild-<time>.json` in the data folder and cleared. Shortcuts, history, settings, and keys are unchanged.

### Onboarding and app
- **Guides show once**: Each feature guide starts automatically only the first time; Replay onboarding shows them again.
- **Lighter onboarding**: Demo videos load only when their guide opens, and hidden onboarding screens do no layout work.
- **Audio Flow and Video Flow upgrades**: Reworked players, progress rows, and a shared UI dispatcher for the floating bar.

### Standalone Runtime & macOS App Enhancements
- **Hermetic macOS Runtime**: Bundled standalone Python 3.11 (`python-build-standalone`) directly within `Contents/Resources/runtime/python` to ensure execution on clean macOS environments without system or Homebrew Python dependencies.
- **Pure Non-Editable Installation**: Removed editable package installation links from the bundled macOS runtime, relying directly on bundled `Contents/Resources/src` on `PYTHONPATH`.
- **Launcher Hardening**: Updated macOS launcher to execute strictly from the bundled standalone Python runtime with an explicit AppleScript user notification if runtime components are missing.
- **Dual macOS Packaging**: Standardized dual release artifact pipeline producing both Finder-styled `.dmg` disk images and symlink-preserving `.zip` archives with SHA-256 checksums.
- **Opt-in Sentry Crash Reporting**: Integrated privacy-preserving, strictly opt-in error monitoring with automatic credential, path, and audio data scrubbing.

## 1.0.1 - 2026-10-06

### Patch Release: Release Integrity, Installer Rebuild & Packaging Audit
- **Windows Installer Rebuild**: Rebuilt Windows installer (`AI-Productivity-Flow-Setup-x64.exe`) from verified source with Python 3.12, bundled Faster-Whisper models, and fresh SHA-256 verification.
- **macOS Bundle Dependency Packaging**: Updated the macOS packaging pipeline to build with `--bundle-runtime`, bundling all required Python packages into `Contents/Resources/runtime/site-packages`.
- **Strict Release Gate**: Hardened release workflow to verify all required artifacts pass SHA-256 integrity validation and prevent obsolete binary recycling.

## 1.0.0 - 2026-10-06

v1.0.0 — First public release: Video Flow, Audio Flow, Voice Flow. Windows installer and macOS .dmg.

### Core Feature Families
- **Video Flow**: Turn selected text and documents into visual explainers with animated scenes, synchronized audio narration, and local MP4 export.
- **Audio Flow**: Listen to text aloud (Read Mode) or generate structured multi-depth audio briefings (Summary Mode) with integrated playback and MP3 download.
- **Voice Flow**: System-wide voice dictation and instant text injection with bundled Faster-Whisper, downloadable NVIDIA Nemotron streaming ASR, and AI text polishing.

### Professional Installers
- **Windows (`AI-Productivity-Flow-Setup-x64.exe`)**: Modern Inno Setup wizard, official app icon, publisher "Uzer Kayat", Start Menu shortcut, optional Desktop shortcut, and clean uninstaller in Windows Apps & Features.
- **macOS (`AI-Productivity-Flow-macOS.dmg`)**: Branded drag-to-Applications installer with custom artwork matching the website palette, official icon, and universal support. Secondary `.zip` archive provided.

### Privacy & Reliability
- **Opt-in Crash Reporting (Sentry)**: Privacy-preserving crash reporting that is disabled by default, scrubs personal paths and API keys, never captures audio/transcripts, and requires explicit user consent.
