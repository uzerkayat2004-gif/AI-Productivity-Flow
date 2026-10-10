> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# WEBVIEW2 — desktop UI runtime guarantee

The main desktop UI is PyWebView, which on Windows hosts the UI in the
**Microsoft Edge WebView2** runtime (Evergreen). Windows 11 and updated
Windows 10 machines already carry it, but a clean machine must not be
assumed.

## Approach (official Microsoft distribution)

The installer bundles the official **WebView2 Evergreen Bootstrapper**
(`MicrosoftEdgeWebview2Setup.exe`, checksum in runtime-manifest.json) and,
in its post-install step, runs it silently (`/silent /install`) **only when
no WebView2 runtime is detected** (registry probes of the EdgeUpdate
Clients key under HKLM/HKCU, per Microsoft's documented detection).
This is Microsoft's supported "distribute the Bootstrapper with your app"
pattern. The user downloads one installer and takes no extra action.

No fixed-version runtime is copied (Evergreen keeps it updated by Microsoft,
matching current product behavior on the dev machine).
