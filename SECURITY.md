# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.x (Windows Beta releases) | ✅ |
| older pre-release builds | ❌ |

## How AI credentials are handled

- AI provider **API keys** are entered by the user in the app's provider
  settings and are **stored locally in the user's SQLite database under
  `~/.voice_flow`**. They are stored locally, but **not encrypted at rest** —
  any process running as your user can read them. Treat the database file as
  sensitive.
- **OAuth tokens** (where a provider uses OAuth) are encrypted at rest with a
  locally generated key.
- Credential use is consent-gated: summaries and Video Flow planning only run
  when you explicitly enable them (off by default); AI polishing runs once you
  connect a provider key and can be disabled in Settings. Planning
  workers receive keys over stdin with a scrubbed environment — keys are never
  placed in command lines or logs.

## Network behavior

- The app serves its dashboard and local API on **loopback only**
  (127.0.0.1:8991); it is not reachable from other machines.
- Local speech recognition (Voice Flow) does not send audio anywhere.
- Internet is used for: AI providers you connect, Audio/Video Flow voices
  (default Edge neural voices are an online service), Audio Flow summaries,
  Video Flow planning, and one-time setup of the remaining render components (downloaded through their official channels).

## Data

- Dictation history, settings, API keys, generated videos, and logs live under
  `~/.voice_flow` in your user profile. Dictation audio archives expire after
  14 days. Uninstalling the app preserves this folder unless you delete it.

## Video Flow sandboxing

- Every video job runs in a per-job sandbox (`~/.voice_flow/v3_projects/<id>/`).
- All AI-authored content passes `validate_no_executable_code` — the model can
  never emit scripts, and rendered scenes are compiled from whitelisted
  primitives.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security → Report a
vulnerability) rather than a public issue. Include steps to reproduce and the
app version. Reports are acknowledged promptly.
