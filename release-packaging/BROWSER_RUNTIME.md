> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# BROWSER_RUNTIME — render browser (chrome-headless-shell)

HyperFrames renders through a pinned **chrome-headless-shell** (Chrome for
Testing family). The tested build on the development machine is
`win64-152.0.7928.2` at `~/.cache/hyperframes/chrome/chrome-headless-shell/`.

## Why it is NOT inside the installer

Google's Chrome for Testing terms grant no binary redistribution right
(audit finding; see PROVENANCE_AUDIT.md). Bundling it would violate those
terms, so the installer does not carry the browser binary.

## How a user still gets zero-action setup

1. **At install time** the installer runs, hidden:
   `runtime\node\node.exe runtime\hyperframes\node_modules\hyperframes\bin\hyperframes.mjs browser ensure`
   — HyperFrames' own official provisioning command — which downloads the
   pinned build from Google's Chrome for Testing endpoints into the
   user-writable cache. No user interaction; internet required (allowed).
2. **Fallback:** if the install-time provisioning fails (e.g. offline), the
   engine calls `runtime_env.ensure_render_browser()` once before the first
   browser render (narova_runner, installed mode only) — same official
   command. Failure to provision surfaces as the existing render-failed
   error path.
3. HyperFrames also honors `HYPERFRAMES_BROWSER_PATH` for manual overrides
   (documented for support cases; not used by default).

Checksums/version pinning of the browser are owned by HyperFrames'
provisioner (it verifies builds itself); the manifest records the
provisioning method rather than a binary hash, since no binary is
distributed.
