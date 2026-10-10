> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# KNOWN_LIMITATIONS

1. **Clean-machine acceptance not yet run** (see CLEAN_MACHINE_TEST.md) —
   the single most important open item before publishing.
2. **Render browser needs internet once**: chrome-headless-shell is
   provisioned at install (or first render) from Google's official
   endpoints because its license does not allow redistribution. An offline
   install defers this to the first online moment; video generation that
   needs the browser waits for it. Voice Flow/Audio Flow are unaffected.
3. **GSAP desktop bundling**: GSAP ships inside vendored Narova under its
   standard license, whose wording targets web interfaces; the notice is
   retained verbatim. Consider contacting Webflow/GreenSock for written
   comfort in a future release (low practical risk; GSAP only executes
   inside rendered HTML).
4. **FFmpeg GPL**: the bundled build includes libx264 → GPL-3.0. Compliance
   is documented (license text, exact build id, source offer). If the
   project wants a non-GPL binary, an LGPL build without x264 breaks the
   H.264 encoding contract — keep GPL + documentation.
5. **Narova upstream is darwin/linux-declared**: Windows support rests on
   our documented hf.js patches. Upgrading narova requires re-validating
   those patches (recorded in runtime-manifest.json).
6. **Installer size**: ~444 MB / ~1.5 GB installed. Accepted by the mission
   (reliability > size). The private python is the largest component.
7. **Antivirus/SmartScreen**: unsigned installer and unsigned python/node
   binaries may trigger warnings on first run. Code-signing hooks are
   deliberately absent until a certificate exists (mission §35) — no
   bypass, no fake signing.
8. **Editable-install hazard on dev machines**: the developer machine has
   `voice-flow` pip-installed editable pointing at the dev tree; repo tests
   now pin `pythonpath = ["src"]` so they test the repository package.
9. **Per-user install only**: no all-users/machine-wide mode. Per mission
   §22 this is the chosen behavior.
