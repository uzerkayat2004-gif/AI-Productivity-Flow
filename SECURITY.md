# 🔒 Security Policy

AI Productivity Flow takes the security and privacy of user data, audio streams, and credentials seriously.

---

## 🛡️ Supported Versions

| Version | Supported |
|:---|:---|
| 1.0.x | :white_check_mark: |
| < 1.0 | :x: |

---

## 🔐 Local-First Security Principles

* **Local-First by Default**: Audio recorded with local Faster-Whisper or downloadable on-device models is transcribed strictly on your machine.
* **Explicit Cloud Provider Routing (BYOK)**: When you configure and select a cloud speech-to-text, text-to-speech, or LLM provider, only the text or audio required for that individual request is transmitted directly to that provider.
* **Local Credential Storage**: Provider API keys and connection parameters are stored locally on your device in the SQLite database (`~/.voice_flow/voice_flow.db`).
* **Encrypted Account Vaults**: Full account export and migration archives (`.flowvault`) are encrypted with **AES-256-GCM** using a user-specified password.
* **Loopback Desktop API**: The internal GUI HTTP and WebSocket server binds exclusively to `127.0.0.1:8991` and verifies `Host` and `Origin` headers to protect against cross-site request attacks.

## 📡 Crash Reporting & Telemetry (Sentry)

AI Productivity Flow optionally integrates Sentry for anonymous, opt-in crash diagnostics:
- **Zero Default Network Transmission**: Crash reporting is disabled by default (`anonymous_crash_reports: false`). No SDK initialization or network requests happen unless the user explicitly opts in.
- **Data Scrubbing Rules**:
  - **Local Username Anonymization**: All file paths containing `/Users/<username>/...` or `C:\Users\<username>\...` have the username replaced with `[REDACTED]`.
  - **Secret Redaction**: Environment variables and request headers containing API keys or tokens (`OPENAI_*`, `ANTHROPIC_*`, `GROQ_*`, `GEMINI_*`, `DEEPGRAM_*`, `SENTRY_*`, `AWS_*`, etc.) are stripped.
  - **Zero Audio & Transcript Data**: Keywords associated with audio, transcripts, recordings, and dictation are redacted, and request bodies/query parameters are dropped.
- **Designated Sentry Ingest Domain**: Telemetry reports (when opted-in) are sent directly and exclusively to the EU Sentry ingest endpoint `*.ingest.de.sentry.io`.

---

## 🚨 Reporting a Vulnerability

If you discover a potential security vulnerability in AI Productivity Flow, please disclose it responsibly:

1. **Do not create a public GitHub issue.**
2. Submit a private report via [GitHub Security Advisories](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/security/advisories/new) or contact the maintainer directly.
3. Include reproducible steps and details on the affected components.

We will acknowledge receipt within 48 hours and work with you to resolve the issue before public disclosure.
