# CURRENT_PRODUCT_MAP — AI Productivity Flow (mapped from code, 2026-08-22)

> Factual source-of-truth map produced by inspecting `src/`, `tests/`, `release/`,
> `release-packaging/`, and `pyproject.toml` BEFORE rewriting public documentation.
> Existing marketing docs were ignored as inputs. Maintained alongside
> `docs/PRODUCT_FACTS.md`.

## Voice Flow — speech → polished text
- Triggers: middle-mouse push-to-talk/tap-toggle (`WH_MOUSE_LL`), Ctrl+Win hold, Esc cancel; self-healing hook watchdogs (`hotkeys.py`, `mouse_hook.py`).
- Recording: sounddevice → 16 kHz mono; mic selectable; 20-min watchdog.
- Transcription: faster-whisper `base.en`, CPU int8, beam 1; dual-pass (VAD then non-VAD); bundled model path in installed builds (`transcriber.py`, `config.py`).
- Dictionary & corrections: `initial_prompt` biasing + literal post-processing; `trigger -> expansion` snippet-style rules; protected spans; auto-learning opt-in (`dictionary.py`).
- Polishing: optional multi-provider LLM polish (gemini/groq/openai/together/deepseek, user keys, failover + rate-limit cooldown) with strict safety checks; deterministic cleanup fallback always available (`polisher.py`).
- Insertion: clipboard paste into the captured target window (Ctrl+V, Shift+Insert fallback), clipboard restore (`injector.py`).
- History + Insights: words/WPM/time-saved/streaks/archetypes; audio archive 14 days.

## Audio Flow — selected text → speech
- Activation: left-drag selection → circular widget at cursor; also via GUI endpoints.
- Modes: Full Audio; Summary (Quick/Standard/Detailed via LLM with explicit consent).
- TTS providers that WORK today (`tts_engine._synthesize`): **Edge TTS (default, free)**, ElevenLabs, Deepgram, OpenAI, Google, Gemini, NVIDIA (cloud ones need the user's API key; failures fall back to Edge).
- Note: `offline`/SAPI5, `azure`, `fish` appear in the selector catalog but have no synthesis branch — they route to the Edge fallback (documented as not-working; do not advertise).
- Playback: pause/resume/stop, speed 0.75–2.0×.

## Video Flow — text/documents → narrated explainer video
- Inputs: selected text, pasted text, documents (.txt .md .csv .json .html .htm .xml .rtf .docx .pdf ≤ 8 MB).
- Modes: `summary` and `full` (no "lesson" mode exists).
- Planning: vendored educational planner prompts via the user's connected model (Groq default gateway; gemini/openai/together/openrouter/nvidia/deepseek via provider connections); explicit external-AI consent required.
- Creative Director: 15 treatments, diversity limits (≤2 consecutive, ≤45% share), label caps (≤4/scene, ≤7 words).
- Scene authoring: per-video design system (theme.css), whitelisted SVG, declarative 3D configs.
- Rendering: browser-based deterministic renderer (HyperFrames, bundled) with automatic portable fallback; `--verify-motion`; FFmpeg normalization to 1920×1080 H.264/AAC/yuv420p/faststart.
- Narration: independent Video Flow voice setting (default Edge `en-US-AvaNeural`), same catalog as Audio Flow; captions SRT/VTT; progress; cancellation; history; standalone player.
- Output: `<job>/video.mp4` 1080p MP4 in the existing player.

## Platform shell
- Dashboard (pywebview, loopback 127.0.0.1:8991), always-on-top non-activating Flow Bar, global hooks, selection capture with console guard, 6-slide onboarding (once), settings, light/dark theme, Windows autostart (HKCU Run + Startup .lnk), watchdog supervisor, data under `~/.voice_flow`.

## Installer / release state
- One per-user Inno Setup exe: private CPython 3.12.10 (62 pinned packages), Node 20.18.1, FFmpeg/FFprobe, faster-whisper base.en (pinned rev), HyperFrames 0.7.96 modules, vendored Narova + Code2Video (MIT, attributed), WebView2 bootstrapper + VC++ redist (conditional, silent).
- Render browser provisioned automatically during installation via the renderer's official command (not redistributed; license).
- Status: installer built and locally validated; **fresh external clean-Windows acceptance pending** (`release-packaging/CLEAN_MACHINE_TEST.md`).

## Verified-absent legacy (do not document as current)
Standalone Snippets UI (merged into Dictionary rules) · Remotion in the shipped product · Veo · hybrid render router / `video_generation/` · "lesson" video mode · working offline SAPI5 TTS · macOS/Linux support.
`video_flow_renderer/` is a dev-side legacy asset (single fallback bundle reference only); the canvas V3 preview player mounts only if program data exists (always 404 now) — playback is the standard `<video>` element.
