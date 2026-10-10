# Changelog

All notable changes to **AI Productivity Flow** are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## 1.0.2 - 2026-10-09

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
