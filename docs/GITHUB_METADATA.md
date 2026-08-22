# GITHUB_METADATA — proposed repository metadata

Apply AFTER the documentation realignment is committed and pushed. Prepared per
the 2026-08-22 mission; GitHub was NOT edited until publication was authorized.

## Description (canonical, fits GitHub limit)

Windows desktop AI productivity app for voice dictation, selected-text audio, and visual explainer videos — system-wide, BYOK, and workflow-first.

Shorter fallback if length-limited:

Windows AI productivity app for voice dictation, selected-text audio and visual explainer videos.

## Homepage

Leave blank — no official website exists.

## Topics (GitHub caps topics; prefer this order)

windows · desktop-app · ai-productivity · voice-dictation · speech-to-text ·
faster-whisper · text-to-speech · tts · visual-explainer · video-generation ·
byok · multimodal · productivity · accessibility · python

## Recommended release identity

- Tag: `v0.9.0-beta`
- Title: `AI Productivity Flow v0.9.0 Beta — Windows`
- Pre-release: yes
- Repository tagline (About): the description above; mention **Windows Beta** in
  README/release notes (done).

## Apply command (run only when authorized)

```bash
gh repo edit uzerkayat2004-gif/AI-Productivity-Flow \
  --description "Windows desktop AI productivity app for voice dictation, selected-text audio, and visual explainer videos — system-wide, BYOK, and workflow-first." \
  --remove-website \
  --add-topic windows --add-topic desktop-app --add-topic ai-productivity \
  --add-topic voice-dictation --add-topic speech-to-text --add-topic faster-whisper \
  --add-topic text-to-speech --add-topic tts --add-topic visual-explainer \
  --add-topic video-generation --add-topic byok --add-topic multimodal \
  --add-topic productivity --add-topic accessibility --add-topic python
```
