> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# NODE_RUNTIME — private Node.js + HyperFrames without npx

- **Node.js 20.18.1 x64** (official win-x64 zip; `node.exe` SHA-256 in
  runtime-manifest.json). Installed at `runtime/node/node.exe`; never added
  to PATH, never system-installed.
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
