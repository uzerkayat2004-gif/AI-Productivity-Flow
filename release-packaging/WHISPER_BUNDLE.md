> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# WHISPER_BUNDLE — bundled speech model

- Model: **faster-whisper base.en** (Systran conversion, MIT; base weights
  openai/whisper-base.en, Apache-2.0).
- Pinned revision: `3d3d5dee26484f91867d81cb899cfcf72b96be6c` (copied from
  the audited local HF cache — the exact model the app has been running).
- Files + SHA-256 (also in runtime-manifest.json):
  - `model.bin` 145,216,508 B — `2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef`
  - `config.json` — `f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb`
  - `tokenizer.json` — `929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df`
  - `vocabulary.txt` — `ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf`
- Installed to `runtime/models/whisper/base.en/`.
- Code change (path only, per mission §48): `transcriber.py` passes the
  bundled directory to `WhisperModel(...)` when installed; development
  unchanged (model name → HF cache as before). No decoding/beam/VAD change.
- Verified: model loads under the private Python (CPU, int8) from the
  bundled path.
