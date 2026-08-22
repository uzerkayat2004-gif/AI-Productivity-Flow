> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# FILES_CHANGED — every working-tree change for this release

Repo at baseline `195ffa8`; nothing committed/pushed. Categories per mission §53.

## RUNTIME PATH

| File | Change |
|---|---|
| `src/voice_flow/runtime_env.py` | NEW — central resolver (install detection, node/ffmpeg/ffprobe/whisper/browser/narova/code2video paths, preflight, browser provisioning). No behavior in dev mode. |
| `src/voice_flow/video_flow_engine/narova_runner.py` | vendor root/node/ffmpeg resolution via runtime_env; installed-mode env: private `NAROVA_PYTHON`, `NAROVA_HF_MODULES`, private ffmpeg dir prepended to the subprocess PATH; browser ensure before hyperframes build (installed only). |
| `src/voice_flow/video_flow_engine/voice_provider_worker.py` | ffmpeg resolution via runtime_env (system PATH fallback preserved). |
| `src/voice_flow/video_flow_engine/code2video_runner.py` | vendored prompts root via runtime_env (dev fallback unchanged). |
| `src/voice_flow/transcriber.py` | bundled model path for `WhisperModel` in installed mode; name/cache behavior unchanged in dev. |
| `src/voice_flow/watchdog.py` | `get_pythonw_executable` prefers the installed private pythonw (dev fallbacks unchanged). |
| `src/voice_flow/installer.py` | autostart registration (HKCU Run + Startup .lnk) uses the installed pythonw/module command in installed mode; VBS/source-tree path preserved for development. |

## LOGGING PATH

| File | Change |
|---|---|
| `src/voice_flow/main.py` | log file → `~/.voice_flow/logs/voice_flow_debug.log` when installed; source-tree path unchanged in dev. |

## RUNTIME PREFLIGHT

Covered by `runtime_env.preflight_problems()` (called by packaging tests;
surfacing strategy documented in KNOWN_LIMITATIONS).

## PACKAGING / INSTALLER / LEGAL

| File | Change |
|---|---|
| `release/build_windows_release.py` | NEW — orchestrator (refresh → preflight → ISCC → sha256). |
| `release/installer/apf-setup.iss` | NEW — Inno Setup script. |
| `release/THIRD_PARTY_NOTICES.txt` | NEW — legal notices. |
| `release-packaging/*.md` (this set) | NEW — release documentation. |
| `src/voice_flow/release_cleanup_autorun.py` | NEW — uninstaller helper (Run-key cleanup). |
| vendored `third_party/narova/tool/src/hf.js` (build cache + staging copy) | documented patch: bundled-modules direct run before the npx fallback (Windows shim from the earlier mission retained). |

## MODEL PACKAGING

Whisper base.en pinned bundle assembled from the audited local HF cache
(build cache `apf-release-build/downloads/whisper-base.en`, manifest with
revision + SHA-256s).

## PACKAGING TEST

`tests/test_runtime_env_paths.py` — NEW: resolver dev-mode defaults,
installed-mode detection via a fake install root, preflight classification,
manifest validity. Plus explicit vendor-absent skip guards on the 6 tests
that construct Code2VideoRunner/NarovaRunner (they pass wherever the
vendored third_party tree exists). Final standalone suite: 247 passed /
6 skipped / 0 failed.

## OTHER

None. Feature modules (`overlay.py`, `hotkeys.py`, `mouse_hook.py`,
`injector.py`, `style_engine.py`, `creative_director.py`, `scene_author.py`,
GUI JS/CSS/HTML, provider/oauth code, DB, onboarding) are untouched.
