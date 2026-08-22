> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# RELEASE_CHECKLIST — before publishing to GitHub Releases

Build is complete; acceptance is not. Work top-to-bottom:

1. [ ] **Clean Windows 10/11 x64 VM**: snapshot fresh state (no Python,
       Node, FFmpeg, Git, dev caches).
2. [ ] Copy `dist/AI-Productivity-Flow-Setup-x64.exe`; verify the
       `.sha256` matches.
3. [ ] Install with the normal UI (double-click), then launch from the
       Start Menu shortcut.
4. [ ] Walk the existing onboarding (steps 5–6 of §43) — must appear and
       behave exactly as the dev build.
5. [ ] Dictate with Voice Flow; confirm bundled Whisper transcription and
       paste into Notepad (§43 steps 9–12).
6. [ ] Confirm Audio Flow reads selected text (Edge TTS).
7. [ ] Add a real user provider key through the existing provider UI;
       confirm AI polishing works.
8. [ ] Generate a Video Flow video end-to-end (planning, narration,
       browser render, captions, MP4 in the player); cancel one job and
       confirm cancellation.
9. [ ] Confirm Task Manager shows NO system Python/Node/FFmpeg usage —
       all binaries resolve under
       `%LOCALAPPDATA%\Programs\AI Productivity Flow\runtime\`.
10. [ ] Reboot; confirm autostart works, no console windows, no missing-
        runtime errors, Defender still enabled and silent.
11. [ ] Uninstall; confirm the app tree, shortcuts, and Run key are gone
        and `~/.voice_flow` user data remains. Reinstall over it; confirm
        data survived.
12. [ ] Optional: sign the installer + launcher with a real Authenticode
        certificate (`ISCC /S` signtool settings); otherwise expect
        SmartScreen warnings and say so in the release notes.
13. [ ] Tag the release, attach the exe + sha256 + release notes that link
        THIRD_PARTY_NOTICES (LGPL/GPL obligations) and state the
        internet-needed-once behavior for the render browser.

Local pre-publish sanity (already done in this build): staging preflight
14/14 components, hf.js node --check, packaged synth chain, license texts
present, secret scan of staging (repo + official downloads only).
