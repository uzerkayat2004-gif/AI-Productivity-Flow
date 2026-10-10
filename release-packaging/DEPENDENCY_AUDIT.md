> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# DEPENDENCY_AUDIT — runtime closure actually required

Method: static AST import scan of `src/voice_flow` (including lazy imports),
subprocess/`shutil.which` sweep, vendored-tool inspection (narova setup.sh,
pipeline.js, hf.js), and inspection of the live `~/.narova` venv.

## Python packages (all bundled into the private runtime)

Directly imported by the app: PIL/Pillow, comtypes, cryptography,
edge_tts, faster_whisper, numpy, psutil, pyautogui, pynput, pypdf,
pyperclip, pystray, pywinauto, scipy, sounddevice, webview (pywebview),
win32api/win32con/win32process (pywin32), httpx.

**pyproject.toml gaps found by the audit (missing before):** Pillow,
cryptography, psutil, pywin32, httpx, pystray. The release pins all of them
in `apf-release-build/requirements-release.txt` (62 frozen packages total,
recorded in runtime-manifest.json).

## Native binaries

| Binary | Production consumer | Resolution |
|---|---|---|
| node.exe | narova_runner (narova.js CLI; HyperFrames CLI) | `runtime/node/node.exe` via runtime_env; PATH in dev |
| ffmpeg.exe | narova synth/build, video normalization, voice worker WAV conversion | `runtime/ffmpeg/ffmpeg.exe` |
| ffprobe.exe | hyperframes render | `runtime/ffmpeg/ffprobe.exe` |
| chrome-headless-shell | hyperframes render | per-user cache via official provisioning (NOT bundled — see BROWSER_RUNTIME.md) |
| WebView2 | pywebview app UI | system Evergreen; bootstrapper run at install if missing |
| VC++ runtime | ctranslate2/numpy/scipy/etc. native wheels | vc_redist.x64 run at install if missing |

## Runtime-managed state (user-writable, seeded or provisioned)

- `~/.voice_flow/` — db, settings, v3_projects, logs (unchanged contract).
- `~/.narova/providers/voiceflow.json` — written by the app per job
  (registered external TTS provider; command points at the private python).
- `~/.cache/hyperframes/chrome/chrome-headless-shell/` — render browser,
  provisioned by `hyperframes browser ensure` at install (first-render
  fallback).
- `~/.narova/venv/` — **not needed in installed mode**: `NAROVA_PYTHON`
  points at the private python, which hosts `narova_tts` in site-packages;
  narova.js honors NAROVA_PYTHON first (pipeline.js findVenvPython), so the
  bash/setup.sh venv path is never taken on a packaged install.

## Optional / dev-only (not bundled, absence is fine)

`antigravity` / `agy` / `agentapi` discovery in video_flow_providers.py
(optional local providers — detected when present, silently absent
otherwise). piper-tts and onnxruntime (only for the unused piper TTS
backend; backends import lazily).
