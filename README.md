# Voice Flow

**Voice Flow** is an open-source voice dictation tool for Windows that remaps the built-in Windows speech recognition to work like Wispr Flow — press a button, speak, text appears.

## Features

- 🎙️ **Wispr Flow Experience**: Floating dark pill overlay with animated waveform, cancel (✕), and finish (✓) buttons.
- ⚡ **Instant Trigger**:
  - **Mouse Scroll Button (Middle Click)**: Press and hold to dictate, release to transcribe and paste.
  - **`Win + Ctrl`**: Global keyboard shortcut toggle.
  - **`Esc`**: Cancel recording.
- 🔒 **Uses Windows Built-in Speech Recognition**: No AI model downloads. Uses the same `System.Speech.Recognition` engine that's already on every Windows PC.
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

2. Install dependencies:
   ```bash
   pip install -e .
   ```

That's it — no model downloads, no API keys, nothing else.

## Usage

```bash
python -m voice_flow.main
```

### Controls

| Action | Control |
|---|---|
| **Start / Hold Dictation** | Press & hold **Mouse Scroll Button** (Middle click) |
| **Finish & Paste** | Release Mouse Scroll Button, or press `✓` on the bar |
| **Keyboard Shortcut** | Press `Win + Ctrl` to toggle recording |
| **Cancel Dictation** | Press `Esc`, or press `✕` on the bar |

## How It Works

1. Press trigger → floating bar appears, microphone starts recording.
2. Speak naturally.
3. Release trigger → audio is sent to Windows' built-in `System.Speech.Recognition` engine (the same one behind Win+H, already installed).
4. Transcribed text is pasted into whatever window/field has focus via clipboard.
5. Bar shows "Done" then fades away.

No internet, no model downloads, no subscription.

## Configuration

Edit `src/voice_flow/config.py` to customize:
- `language`: Speech recognition culture (default: `'en-US'`)
- Bar colors, dimensions, and screen position

## License

MIT License
