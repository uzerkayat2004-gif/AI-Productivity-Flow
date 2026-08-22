# Roadmap

Status: **Windows Beta** — ready to use and actively improving.

## Current / Shipped

- **Voice Flow** — system-wide dictation (middle-mouse / Ctrl+Win), local
  faster-whisper `base.en` transcription (bundled with the installer), dual-pass
  VAD transcription, personal dictionary & corrections, optional BYOK AI
  polishing with deterministic fallback, direct insertion, history & insights.
- **Audio Flow** — selected-text reading with free Edge neural voices by default,
  BYOK premium voices (ElevenLabs, OpenAI, Gemini, Google, Deepgram, NVIDIA),
  Full Audio and spoken summaries (quick / standard / detailed).
- **Video Flow** — text/document → educational explainer video: consent-gated
  planning on a connected model, Creative Director with 15 visual treatments and
  diversity limits, per-video design system, browser-based deterministic
  rendering with portable fallback, selectable narration voice, captions,
  1080p MP4 output, history & player.
- **Platform** — always-on-top Flow Bar, self-healing global hooks, onboarding,
  provider management, light/dark theme, Windows autostart + watchdog, per-user
  data under `~/.voice_flow`.
- **Distribution** — single per-user Windows installer bundling the private
  Python/Node/FFmpeg runtimes, the speech model, and the deterministic renderer.

## Release Hardening

- External clean-machine Windows acceptance test (fresh Windows 10/11 VM, no
  developer tools) — the main open item before wider promotion.
- Tester feedback loop: install/first-run experience, dictation quality across
  microphones, video generation reliability across GPUs/drivers.
- Code signing for the installer (SmartScreen friendliness) once a certificate
  is available.
- Release reliability: repeatable one-command release builds, checksummed
  artifacts, upgrade-over-install behavior.

## Near-Term

- Voice quality options and model choices for local transcription.
- Richer Video Flow treatment library and narration voice controls.
- Audio Flow reading queue / background reading improvements.
- Accessibility and multi-language voice coverage.

## Future

- Additional platforms beyond Windows (exploration only; nothing promised).
- Optional local AI polishing for fully-offline advanced cleanup.
- Shareable video style presets.
