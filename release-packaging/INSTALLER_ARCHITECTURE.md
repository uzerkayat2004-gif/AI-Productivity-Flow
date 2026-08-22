> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# INSTALLER_ARCHITECTURE — one-file per-user Windows installer

## Technology decision

**Inno Setup 6.5.1** (`ISCC.exe`): mature, scriptable, excellent per-user
(lowest-privilege) support, single self-contained Setup exe output, built-in
conditional post-install steps and uninstall registration. NSIS/WiX were
considered; WiX adds MSI machinery without benefit for a per-user app, NSIS
hand-rolls more logic. Inno is the smallest reliable path to exactly one exe.

## Layout installed on the user machine

```
%LOCALAPPDATA%\Programs\AI Productivity Flow\
    runtime\
        python\           CPython 3.12.10 + 62 packages + voice_flow + narova_tts
        node\             node.exe (20.18.1)
        hyperframes\      node_modules (hyperframes 0.7.96 + deps, win64 natives)
        ffmpeg\           ffmpeg.exe / ffprobe.exe + GPL license text
        narova\           vendored Narova tool (MIT) incl. tool\node_modules
        code2video\       vendored prompts (MIT)
        models\whisper\base.en\
        webview2\         MicrosoftEdgeWebview2Setup.exe (conditional run)
        vcredist\         vc_redist.x64.exe (conditional run)
        runtime-manifest.json
        license-lgpl-3.0.txt
    THIRD_PARTY_NOTICES.txt
    LICENSE
```

Install: per-user (`PrivilegesRequired=lowest`), no admin, no PATH mutation.
Shortcuts (Start Menu; Desktop optional task) target
`runtime\python\pythonw.exe -m voice_flow.watchdog` with the app icon.

## Post-install steps (all silent)

1. `vc_redist.x64.exe /install /quiet /norestart` — only when the VC++ 14
   x64 runtime registry key is absent.
2. `MicrosoftEdgeWebview2Setup.exe /silent /install` — only when no WebView2
   Evergreen runtime is registered (HKLM/HKCU EdgeUpdate probes).
3. `node.exe …\hyperframes.mjs browser ensure` — provisions the pinned
   chrome-headless-shell into the user cache (official Google endpoints;
   the binary is not redistributed). Non-fatal; the app retries before the
   first render if needed.
4. Optional user-checkbox launch of the app (skipped in silent installs).

## Uninstall

Removes the install directory, Start Menu/Desktop shortcuts, and the app's
`HKCU\…\Run\VoiceFlow` autostart value (via `voice_flow.release_cleanup_autorun`).
User data under `~/.voice_flow` is intentionally preserved (recoverable).

## Repair / reinstall

Reinstalling the same version over an existing install replaces the
application/runtime files and leaves `~/.voice_flow` untouched (Inno default
behavior with per-user dirs; no data reset code paths exist in the
installer).

## Build reproducibility

`release/build_windows_release.py` → refresh app package into staging →
preflight (14 required components + hf.js `node --check`) → ISCC with
injected staging/dist paths → SHA-256. Sizes: staging ≈ 1.5 GB, installer
≈ 444 MB (LZMA2/max, solid). Largest components: python runtime (~700 MB
with ctranslate2/onnx/scipy), hyperframes node_modules (~180 MB incl.
onnxruntime-node/sharp natives), narova+node_modules (~120 MB), whisper
model (~145 MB), node (~80 MB), ffmpeg (~170 MB unpacked).
