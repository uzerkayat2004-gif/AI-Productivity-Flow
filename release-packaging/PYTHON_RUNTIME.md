> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# PYTHON_RUNTIME — private CPython for the installed app

- **Version:** CPython 3.12.10 x64 (official python.org installer,
  `python-3.12.10-amd64.exe`, silent install into the build tree; includes
  Tcl/Tk for the Flow Bar and pip).
- **Why 3.12:** mission-preferred stable line; every audited dependency has
  cp312 wheels (faster-whisper/CTranslate2, NumPy, SciPy, SoundDevice,
  pynput, PyWebView, pywinauto, comtypes, Tkinter, edge-tts, Pillow,
  pystray). The dev machine's 3.14 is deliberately NOT packaged.
- **Contents:** 62 pinned packages (freeze recorded in
  runtime-manifest.json), `narova_tts` (vendored, pure Python; heavy TTS
  backends remain lazy imports), and the `voice_flow` application package
  itself (installed into site-packages so `pythonw -m voice_flow.watchdog`
  and every worker subprocess resolve without PYTHONPATH or source tree).
- **Verified in staging:** voice_flow imports; runtime_env detects installed
  mode; faster-whisper loads the bundled base.en model (CPU/int8);
  narova_tts synth runs via `NAROVA_PYTHON`.
- The installer carries `python.exe` and `pythonw.exe`; the app never
  consults system Python (`watchdog.get_pythonw_executable` prefers the
  private runtime first).
