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

6. **Windows Startup & Watchdog Auto-Recovery**:
   - **Dual Auto-Start**: Registers in both Windows Registry (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\VoiceFlow`) and Windows Startup Folder (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Voice Flow.lnk`).
   - **Silent Background Execution**: Runs via `VoiceFlowLauncher.vbs` with `pythonw.exe` and `WScript.Shell.Run(..., 0, False)` for zero console/terminal popups on boot.
   - **Watchdog Supervisor**: Background health monitor that auto-recovers and restarts Voice Flow if unexpectedly terminated or crashed, with exponential backoff protection.

---

## 🚀 How to Run & Configure Auto-Startup

### 1. Configure Auto-Startup & Desktop Shortcuts
Run the standalone desktop installer:
```bat
setup_desktop_app.bat
```
Or via Python:
```bash
python -m voice_flow.installer --install
```

### 2. Verify Startup & Watchdog Diagnostics
Run the verification script in PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File scratch/verify_startup.ps1
```
Or check status via CLI:
```bash
python -m voice_flow.watchdog --status
```

### 3. Manual Launch Modes
- **Silent Background (Default)**: Double-click `VoiceFlowLauncher.vbs` or `run_voice_flow.bat`
- **Interactive Console Mode**: `run_voice_flow.bat --console`
- **Watchdog Console Mode**: `run_voice_flow.bat --watchdog-console`
- **Stop Background Service**: `run_voice_flow.bat --stop`

---

## 🛠️ Requirements
- Windows 10 / 11
- Python 3.10+
- Dependencies: `faster-whisper`, `sounddevice`, `pyautogui`, `pyperclip`, `pywebview`, `pynput`, `scipy`

