# 🔒 Security Policy

Flow takes the security and privacy of user data and credentials seriously.

---

## 🛡️ Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x / 2.x | :white_check_mark: |
| < 1.0   | :x:                |

---

## 🔐 Local-First Security Principles

* **BYOK (Bring Your Own Key):** All API keys entered by the user are stored locally in the user's SQLite database (`~/.voice_flow/voice_flow.db`).
* **Zero Telemetry Leaks:** Flow does not send user transcripts, audio recordings, or API keys to external telemetry servers.
* **Loopback Isolation:** The internal desktop API server binds exclusively to `127.0.0.1` and does not accept remote network connections.

---

## 🚨 Reporting a Vulnerability

If you discover a potential security vulnerability in Flow, please disclose it responsibly:

1. **Do not create a public GitHub issue.**
2. Send a detailed report to the maintainers via GitHub Private Vulnerability Reporting or email the repository owner.
3. Include reproducible steps and details on the affected components.

We will acknowledge receipt within 48 hours and work with you to resolve the issue before public disclosure.
