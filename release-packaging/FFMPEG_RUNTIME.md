> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# FFMPEG_RUNTIME — bundled FFmpeg / FFprobe

- Build: **gyan.dev `ffmpeg-release-essentials`** win64 (the same family the
  development machine runs). Exact `ffmpeg -version` line + configuration
  string + both binary SHA-256s recorded in runtime-manifest.json; license
  files staged from the zip as `runtime/ffmpeg/license-*.txt`.
- Licensing: this build includes **libx264 → GPL-3.0**. The GPL text ships
  in `runtime/ffmpeg/license-LICENSE`, THIRD_PARTY_NOTICES.txt states
  the GPL obligation and the source-availability offer (ffmpeg.org source
  releases + gyan.dev publish the corresponding sources per build), and the
  exact build is identified in the manifest. This is a documented GPL
  component distribution, not a hidden dependency.
- Path handling: `runtime_env.ffmpeg_executable()/ffprobe_executable()`
  resolve the private binaries in installed mode; `narova_runner`,
  `voice_provider_worker` use them (system PATH fallback only in dev).
  HyperFrames receives them through the engine's environment (PATH entry of
  the private ffmpeg dir is NOT set system-wide; narova's synth/build
  commands inherit the engine env which includes the runtime bin dir via
  the runner command environment — see FILES_CHANGED narova_runner).
- Output contract unchanged: 1920x1080 H.264/AAC/yuv420p/faststart.
