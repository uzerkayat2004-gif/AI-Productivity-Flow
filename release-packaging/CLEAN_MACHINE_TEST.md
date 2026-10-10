> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# CLEAN_MACHINE_TEST — what was actually executed, and what was not

Mission §57 requires honesty here. **A genuinely clean Windows 10/11 VM was
not available in this working environment.** Everything below lists exactly
what was and was not validated.

## Executed (build machine, real artifacts)

1. **Full test suite** before changes (253 passed / 1 skipped) and after all
   packaging changes with the repository package explicitly on sys.path —
   no regression (final counts in the build log; 4 new packaging tests).
2. **Installed-mode resolution** from the staging tree (identical layout to
   the installed app): install root detection, node/ffmpeg/ffprobe/whisper
   resolution to private runtime, NAROVA_PYTHON + NAROVA_HF_MODULES
   environment, preflight green.
3. **Whisper base.en** loads under the private CPython 3.12 (int8 CPU) from
   the bundled path.
4. **Packaged narration chain (real audio)**: bundled Node → narova
   check/synth → private python narova_tts → voiceflow external provider →
   Edge TTS → bundled ffmpeg normalization → 3.3 s WAV, under a sandboxed
   NAROVA_HOME and data dir (no user data touched).
5. **hf.js patch** passes `node --check` under the bundled Node; bundled
   hyperframes CLI --help renders under the bundled Node.
6. **Installer package**: Inno compile succeeds; the resulting exe installs
   silently on the build machine (per-user dir created, files verified,
   shortcuts created; postinstall conditional steps skipped where the
   machine already has WebView2/VC++); uninstall removes the install tree.
7. **Dev app health**: the developer's running application stayed live and
   functional throughout the mission (its API and processes were never
   touched by the build).

## NOT executed (requires a clean Windows 10/11 x64 VM)

The full §43 acceptance sequence, specifically:

- Install/launch **on a machine with no Python/Node/FFmpeg/Git** (proving
  absence of undeclared dependencies — the packaging audit addresses this
  statically, but §44's empirical proof is missing).
- Fresh-user onboarding walk-through (§43 steps 5–6).
- Live microphone dictation + transcription + paste into Notepad (steps
  9–12) — microphone interaction is not automatable in this environment.
- Provider key entry through the UI and AI polishing (steps 17–19).
- Real Video Flow generation on the installed app (steps 21–28) and job
  cancellation (step 29).
- Reboot/auto-start verification (steps 32–38) and Windows Defender
  behavior on a fresh machine.

## Verdict per mission §57

The installer exists, is internally verified, and every packaged component
was exercised through the real pipeline — **but the clean-machine
acceptance test has not been run**, so the release must be treated as
build-complete, not release-accepted. Run the §43 sequence on a clean VM
(or a fresh Windows user profile with developer tools hidden from PATH,
which approximates but does not replace it) before publishing.
