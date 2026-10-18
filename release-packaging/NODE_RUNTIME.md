> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# NODE_RUNTIME — private Node.js + HyperFrames without npx

- **Node.js 20.18.1 x64** bundled (official win-x64 zip; `node.exe` SHA-256 in
  runtime-manifest.json). Installed at `runtime/node/node.exe`; never added
  to PATH, never system-installed.
- **Node.js 22.23.3 x64 (app-managed, since 1.0.8)**: HyperFrames 0.7.96 needs
  Node >= 22. The app downloads the pinned official win-x64 zip (SHA-256
  `2b0ff57b…ed71`) into `%USERPROFILE%\.voice_flow\components\node\22.23.3`
  in the background at idle priority, or before the first full-fidelity render
  (`src/voice_flow/node_component.py`). The bundled Node stays 20.18.1 so the
  runtime fingerprint of v1.0.6 installs still matches and in-app updates use
  the ~50 MB app zip. Do not bump the bundled Node: from 1.0.8 the updater
  treats `node` as app-managed, but 1.0.6/1.0.7 updaters do not.
- **HyperFrames 0.7.96 (Apache-2.0)** — the pinned version narova's hf.js
  expects — is pre-installed into `runtime/hyperframes/node_modules` at
  BUILD time via npm on the build machine (exactly the packages the npx
  resolution would produce, including win64 natives for onnxruntime-node
  and sharp).
- **No npx / npm registry at runtime:** the vendored `hf.js` now checks for
  the bundled install first (`NAROVA_HF_MODULES`, set by the engine's safe
  environment, or the installed runtime layout) and runs
  `node …/hyperframes/bin/hyperframes.mjs` directly. The npx path remains as
  the development fallback. Patch is documented in runtime-manifest.json.
- Verified: patched hf.js passes `node --check` under the bundled Node; the
  bundled CLI's help renders under the bundled Node.
