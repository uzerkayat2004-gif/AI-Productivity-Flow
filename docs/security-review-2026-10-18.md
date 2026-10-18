# Security and bug review: 2026-10-18

Scope: the whole repo at main `00e6699` (v1.0.6), reviewed overnight before the public launch.
Branch: `fix/overnight-security-review` (6 commits). Not covered here: the NotebookLM login code and the splash/launcher code (those are in PR #43).

## Fixed in this branch

| # | Severity | Issue | Where | Fix commit |
|---|---|---|---|---|
| 1 | High | Stored XSS in the Audio Flow player history. Selected text (from a web page or PDF) was put into the page with innerHTML and inline onclick strings. The page is served from 127.0.0.1:8991, so script injected there could call the local API. | `gui/audio-summary-player.html`, `gui/audio-summary-player.classic.html`, embedded copy in `audio_summary_player.py` | c4f767c (test `tests/test_audio_player_history_xss.py`) |
| 2 | High (functional) | Video Flow render setup fails with exit 1 on Windows. The bundled Node is 20.18.1, but hyperframes 0.7.96 needs Node 22 or newer. Renders are likely affected too. Bumped to Node 22.23.3 and added SHA-256 pins for the build-time Python, Node and ffmpeg downloads. | `release/assemble_windows_staging.py`, `bundled_runtime.py` | 763f6d4 (test `tests/test_windows_runtime_pins.py`) |
| 3 | Medium | Any website could trigger local GET API actions (for example a paid-key summary at `/api/audio-summary/test`). Cross-site GETs are now refused (OAuth callbacks exempt), and `Access-Control-Allow-Origin: *` was removed from `/api/video-flow/v3/audio`. | API server | d58d730 (test `tests/test_api_cross_site_get.py`) |
| 4 | Medium | On macOS, `~/.voice_flow` (API keys plus the token encryption key) and `~/.notebooklm` (Google cookies) were readable by other users (0755). They are now 0700. No change on Windows. | `paths.py`, `main.py`, `storage.py` | d98eba9 (test `tests/test_private_data_dir_permissions.py`) |
| 5 | Low | The Windows browser fallback ran `cmd /c start "" <url>`, and `&` in a URL could run extra commands. It now uses rundll32 and accepts only http(s) URLs. | `video_flow_oauth.py` | 780f887 (test `tests/test_launch_system_browser_safety.py`) |
| 6 | Low (UX) | Upgrades kept the "(Default)" Start menu folder. Added `UsePreviousGroup=no`. | `release/installer/apf-setup.iss` | 4424f3b |

## Reviewed and OK
- The local server binds 127.0.0.1 only, with a Host-header check (DNS rebinding) and a POST Origin allow-list.
- No shell=True, pickle, yaml.load, eval or exec on untrusted input. Static and video serving are confined to their folders.
- Updater: HTTPS only, GitHub release assets only, SHA-256 checked before install, no downgrade, zip `..` paths blocked.
- Every model download has a pinned SHA-256. Sentry scrubs keys and personal data.
- The main UI (`app.js`, `video-flow.js`) escapes model and document text.
- Full git history: no private keys or tokens. The only key-like value is the public Sentry DSN, which is meant to be public.

## Open, not fixed
- Low: the model downloader turns off TLS verification on SSL errors (`downloadable_models.py:574-580`). The hash pins limit the damage.
- Low: the updater URL check allows assets from any GitHub repo (`app_updater.py:83`).
- Low: an old partial update download can be resumed onto a newer file. The checksum then fails once, and a retry works.
- Mac quit after SIGTERM takes about 31 s (menu quit takes about 6 s). Suspect: the SIGTERM handler in `child_processes.py:321-351`. Unverified.
- Mac onboarding demo videos show a Windows taskbar. They need re-recording on a Mac.
- Onboarding text is small at 1024x681. Mac WKWebView autoplay is unconfirmed.
- Not done: pip-audit, npm audit, a full innerHTML sweep.

## Needs Uzair's decision
1. Test the Node 22 bump on a real Windows build, including one Video Flow render. It makes the next Windows update a full installer.
2. Code signing: updates are checked only against a checksum stored in the same GitHub release.
3. API keys are stored in plain text, with the token encryption key in the same database. Moving them to Windows DPAPI or the macOS Keychain is his call.
4. CircleCI: no key was committed. Remove any deploy key in GitHub Settings > Deploy keys and delete the CircleCI project.

## Tests (Linux sandbox)
See the bottom of this file for the before and after runs of the full suite.
- Before (main 00e6699): 4258 passed, 115 failed, 22 errors, 55 skipped.
- After (this branch): 4286 passed, 115 failed, 22 errors, 55 skipped. The failing set is identical, so there are no new failures. The 28 extra passes are the new tests. The existing failures are sandbox and environment issues (Windows-only paths, missing benchmark folders, outdated test fakes).
