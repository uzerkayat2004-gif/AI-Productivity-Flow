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

1. **In the background after the first launch** the installed Windows app
   runs, hidden and at idle priority, 10 minutes after the engine is ready:
   `runtime\node\node.exe runtime\hyperframes\node_modules\hyperframes\bin\hyperframes.mjs browser ensure`
   — HyperFrames' own official provisioning command — which downloads the
   pinned build from Google's Chrome for Testing endpoints into the
   user-writable cache (`runtime_env.schedule_render_browser_prefetch`).
   No user interaction; internet required (allowed). Up to v1.0.6 the
   installer ran this itself, right before the app's first launch, and the
   download competed with the app for CPU, disk and network.
2. **On demand:** if the browser is still missing (offline, or a render in the
   first 10 minutes), the engine calls `runtime_env.ensure_render_browser()`
   once before the first browser render (narova_runner, installed mode only)
   — same official command, guarded by a lock so it never downloads twice.
   Failure to provision surfaces as the existing render-failed error path.
3. HyperFrames also honors `HYPERFRAMES_BROWSER_PATH` for manual overrides
   (documented for support cases; not used by default).

Checksums/version pinning of the browser are owned by HyperFrames'
provisioner (it verifies builds itself); the manifest records the
provisioning method rather than a binary hash, since no binary is
distributed.
