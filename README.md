# Voice Flow

**Voice Flow** is an open-source, local AI voice dictation tool for Windows. It provides a seamless, Wispr Flow-style dictation experience using offline speech recognition with OpenAI's Whisper model.

## Features

- 🎙️ **Wispr Flow Experience**: Floating dark pill overlay with animated waveform, cancel (✕), and finish (✓) buttons.
- ⚡ **Instant Trigger**:
  - **Mouse Scroll Button (Middle Click)**: Press and hold to dictate, release to transcribe and paste.
  - **`Win + Ctrl`**: Global keyboard shortcut toggle.
- 🔒 **100% Offline & Private**: Powered by `faster-whisper` running locally on your computer.
- 🎯 **Works Everywhere**: Direct text injection into any input field, text editor, browser, or IDE via clipboard paste.
- 🚫 **No Focus Stealing**: Floating bar uses Windows `WS_EX_NOACTIVATE` window styling so keyboard focus stays in your active application.

## Prerequisites

- Windows 10 / 11
- Python >= 3.10
- Microphone

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/your-username/voice-flow.git
   cd voice-flow
   ```

2. Install dependencies using `uv` (or standard `pip`):
   ```bash
   uv sync
   # or with pip:
   pip install -e .
   ```

## Usage

Run Voice Flow:

```bash
uv run voice-flow
# or:
python -m voice_flow.main
```

Upon first launch, `faster-whisper` will automatically download the Whisper `base` model (~140 MB). Subsequents runs use the cached model fully offline.

### Controls

| Action | Control |
|---|---|
| **Start / Hold Dictation** | Press & hold **Mouse Scroll Button** (Middle click) |
| **Finish & Paste** | Release Mouse Scroll Button, or press `✓` on the bar |
| **Keyboard Shortcut** | Press `Win + Ctrl` |
| **Cancel Dictation** | Press `Esc`, or press `✕` on the bar |

## Configuration

Edit `src/voice_flow/config.py` to customize:
- `model_size`: `'tiny'`, `'base'`, `'small'`, or `'medium'`
- `language`: `'en'` (or auto-detect)
- Bar colors, dimensions, and screen position

## License

MIT License
