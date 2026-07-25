# 🎙️ Voice Flow — AI Speech Desktop Application

**Voice Flow** is a high-performance, real-time AI speech-to-text dictation application for Windows, featuring a native desktop interface, floating Wispr Flow-style overlay bar, 100% hardware audio routing, 2026 voice model API integrations, and direct Microsoft Excel spreadsheet cell navigation.

---

## 🌟 Key Features

1. **Floating Wispr Flow Bar Marker (`[ ─── ]`)**:
   - Always-on-top system-wide overlay bar with 10-second startup initialization sequence (`Starting... 10s` -> `Ready to do this and all`).
   - Click-to-activate dictation mode (`🎙️ Dictating... Click to stop`).

2. **100% Hardware Microphone Device Selection**:
   - Hardware audio routing using `sounddevice.InputStream(device=...)` bypassing Windows Microsoft Sound Mapper. Supports `Headphones`, `LK`, `Headset (Max Pro)`.

3. **2026 Voice Model & API Keys Hub (10 Providers, 5 Left / 5 Right)**:
   - ✨ **Google Gemini**: `gemini-3.1-flash-live`, `gemini-3.1-flash-tts`, `gemini-3.5-live-translate`, `gemini-2.5-flash-tts`, `gemini-2.0-flash`
   - ⚡ **Groq Audio**: `whisper-large-v3-turbo`, `whisper-large-v3`, `distil-whisper-large-v3-en`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`
   - 🎙️ **ElevenLabs Voice**: `eleven_v3`, `eleven_flash_v2_5`, `eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_english_v2`
   - 🎧 **Deepgram Speech**: `nova-3`, `flux`, `aura-2`, `aura-asteria-en`, `nova-2-general`
   - 🤖 **OpenAI Voice**: `gpt-realtime-2`, `gpt-realtime-whisper`, `gpt-realtime-translate`, `whisper-1`, `tts-1-hd`
   - 🗣️ **AssemblyAI**: `universal-2`, `universal-1`, `conformer-2`, `slam-1`, `conformer-1`
   - 🤗 **Hugging Face Voice**: `fixie-ai/ultravox-v0_5`, `openai/whisper-large-v3-turbo`, `kyutai/moshiko-pytorch`, `suno/bark`, `coqui/XTTS-v2`
   - ☁️ **Cloudflare Workers Voice AI**: `@cf/deepgram/nova-3`, `@cf/myshell/melotts`, `@cf/openai/whisper-large-v3-turbo`
   - 🤝 **Together Voice AI**: `cartesia/sonic-multilingual`, `hexgrad/kokoro-v0_19`, `togethercomputer/whisper-large-v3`
   - 🚀 **Replicate Voice**: `victor-upx/kokoro-tts`, `coqui/xtts-v2`, `replicate/whisp-v3`

4. **Microsoft Excel & Spreadsheet Integration**:
   - Automatic active window detection for Excel, CSVs, and spreadsheets.
   - Spoken table commands (`"next cell"`, `"tab"`, `"next row"`, `"new line"`) are instantly converted into tabbed/newline clipboard data for effortless multi-cell entry.

5. **Persistent SQLite Storage**:
   - Dictation history, custom dictionary terms, and verified API keys are stored in `~/.voice_flow/voice_flow.db` and preserved across sessions.

6. **Windows Startup Auto-Launch**:
   - Registers in Windows Registry `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` so the floating bar appears automatically when you start your laptop.

---

## 🚀 How to Run

### Method 1: Double-Click Batch File
Double click `run_voice_flow.bat` in the project root.

### Method 2: Command Line
```bash
python -m voice_flow.gui.desktop_launcher
```

---

## 🛠️ Requirements
- Windows 10 / 11
- Python 3.10+
- Dependencies: `sounddevice`, `pyautogui`, `pyperclip`, `pywebview`, `pynput`
