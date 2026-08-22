> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# RUNTIME_MANIFEST — what the installer carries

The machine-readable `runtime/runtime-manifest.json` is generated at build
time (assemble_staging.py) and ships inside the installer. It records:

- product + build script
- Python: 3.12.10 + the full `pip freeze` (62 pinned packages)
- Node: 20.18.1 + node.exe SHA-256
- HyperFrames: 0.7.96 (Apache-2.0)
- FFmpeg/FFprobe: binary SHA-256s, exact `ffmpeg -version` line and
  configuration string (GPL build identification)
- Narova/Code2Video: upstream URLs, MIT license, documented local patches
- Whisper model: faster-whisper-base.en @ revision
  `3d3d5dee26484f91867d81cb899cfcf72b96be6c` + model.bin SHA-256
- Render browser: provisioning method (not distributed)
- WebView2 bootstrapper + VC++ redistributable SHA-256s

No secrets, keys, tokens, or user data are included (the staging input is
the repository + official binary downloads only; a secret scan of the
staging tree is part of RELEASE_CHECKLIST).
