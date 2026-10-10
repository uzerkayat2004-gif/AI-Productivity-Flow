# CURRENT_PRODUCT_MAP — AI Productivity Flow (Mapped from v1.0.0 Source)

> Factual source-of-truth map produced by inspecting `src/`, `tests/`, `release/`,
> and `pyproject.toml`. Maintained alongside `docs/PRODUCT_FACTS.md`.

## 1. Video Flow — text/documents → narrated explainer video
- **Inputs**: Selected text, pasted text, documents (`.txt`, `.md`, `.csv`, `.json`, `.html`, `.htm`, `.xml`, `.rtf`, `.docx`, `.pdf` ≤ 8 MB), Google NotebookLM notebooks.
- **Modes**: `summary` and `full`.
- **Planning**: AI-driven concept extraction and pedagogical structuring via user's connected model (Groq, Gemini, OpenAI, Claude, Together, Ollama) or local fallback.
- **Creative Director**: Pacing calculations, scene diversity rules, layout solver (`layout_solver_v21.py`), dynamic card hierarchy.
- **Scene Authoring**: Structured scene programs (`statement`, `process`, `comparison`, `metric`, `diagram`).
- **Rendering Pipeline**: Narova / Code2Video / Canvas-WebGL composition; FFmpeg normalization to 1920×1080 H.264/AAC MP4.
- **Narration**: Independent Video Flow voice setting (Edge TTS default, ElevenLabs, Cartesia, OpenAI TTS) with synchronized per-scene duration mapping.
- **Output**: 1080p MP4 saved to user's system `Downloads` folder, with in-app playback and history tracking.

## 2. Audio Flow — selected text → spoken reader & summaries
- **Activation**: Left-drag selection → circular widget at cursor; also via GUI endpoints and shortcut commands.
- **Modes**:
  - **Read Mode**: Spoken reader articulating selected text with human cadence and natural flow.
  - **Summary Mode**: Multi-depth summaries: **Short**, **Balanced**, **Deep Dive** via connected LLM.
- **TTS Providers**: Microsoft Edge Neural (default, free), ElevenLabs, Cartesia, OpenAI, Google Cloud TTS.
- **Playback**: Mini floating bar and in-app audio player with waveform scrubbing, speed adjustment (0.75x–2.0x), and one-click MP3 download.

## 3. Voice Flow — speech → polished text
- **Triggers**: `Ctrl + Win` hold/tap (Windows default), `Cmd + Option` (macOS), middle-mouse button, Alt + Space; self-healing hook watchdogs.
- **Recording**: `sounddevice` → 16 kHz mono; selectable microphone; silence gate & adaptive VAD.
- **Transcription**:
  - Bundled local Faster-Whisper `base.en`, CPU int8.
  - Downloadable streaming models: NVIDIA Nemotron Speech Streaming English 0.6B and Nemotron 3.5 ASR Streaming 0.6B.
  - Optional cloud STT: Deepgram, Groq, OpenAI Whisper, Gemini STT.
- **Dictionary & Snippets**: Custom pronunciation corrections, acronym biasing, and snippet trigger expansions (`trigger -> expansion`) with cross-process SQLite sync.
- **AI Text Polish**:
  - Downloadable on-device Liquid LFM 1.3B/3B via llama.cpp.
  - Windows AI Text Rewriter where supported by hardware.
  - Optional cloud LLMs (Gemini, Claude, OpenAI, Groq, Ollama).
  - Deterministic cleanup fallback always available.
- **Insertion**: System-wide clipboard injection into active target window (Ctrl+V on Windows, Cmd+V on macOS).

## 4. Platform Shell & Multi-Account
- **UI Architecture**: pywebview desktop wrapper, local API server on `127.0.0.1:8991`, non-activating floating pill bar, light/dark theme, system tray integration.
- **Multi-Account & Security**: Isolated user SQLite database under `~/.voice_flow/`, 1-click switch account modal, separate credentials vault.
- **NotebookLM Sync**: Google OAuth integration syncing research notebooks and sources.
- **Update System**: Safe, non-intrusive update checker querying GitHub Releases for stable updates.

## 5. Distribution & Packaging
- **Windows**: Single-file Inno Setup installer (`AI-Productivity-Flow-Setup-x64.exe`) bundling private Python, Node, FFmpeg, Whisper model, and runtimes.
- **macOS**: Application bundle (`AI Productivity Flow.app` / `AI-Productivity-Flow-macOS.zip`).
- **Terminal Installers**: `scripts/install.ps1` (PowerShell) and `scripts/install.sh` (Bash).
