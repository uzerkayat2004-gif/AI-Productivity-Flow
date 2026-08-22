> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# THIRD_PARTY_LICENSE_AUDIT — notices generated from the audit

The complete, legally-worded notice file ships at the install root
(`THIRD_PARTY_NOTICES.txt`, source: `release/THIRD_PARTY_NOTICES.txt`) and
covers every distributed component: MIT items (narova, code2video, three.js,
Node.js, faster-whisper/ctranslate2/comtypes/sounddevice/Pillow and other
permissive pip packages), Apache-2.0 items (hyperframes, requests-family),
BSD items (pywebview, scipy, numpy, pypdf, pywinauto, httpx, pyperclip,
PyAutoGUI), the **LGPLv3 trio (edge-tts, pynput, pystray)** with license
text + written source offer, the **GPL-3.0 FFmpeg build** with license text
+ build identification + source offer, GSAP's standard-license notice kept
verbatim, Microsoft terms for WebView2/VC++ redistributables, the SIL OFL
font header retained in the noto-sans-arabic package, PSF for Python, and
the dual MIT/Apache-2.0 whisper model attribution.

Components no longer used are excluded (no stale names): the legacy v5
engine, chatterbox/xtts/qwen TTS extras, and piper are not distributed.

License texts staged inside the installer:
- `runtime/ffmpeg/license-gpl-3.0.txt` (from the gyan zip)
- `runtime/license-lgpl-3.0.txt` (LGPLv3 common text)  *(added by the build
  script to the staging runtime root)*
- every pip package's METADATA remains inside its dist-info directory.
