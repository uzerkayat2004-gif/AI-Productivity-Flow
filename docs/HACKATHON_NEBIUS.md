# Nebius x NVIDIA hackathon notes

This file explains what changed in AI Productivity Flow during the hackathon window and how the app uses Nebius Token Factory and NVIDIA Nemotron. It only describes what is in the code.

## What changed since Aug 26, 2026

Source: `git log --since=2026-08-26` on this repository. On Aug 26 the newest commit was `01017d8` (Aug 22, "docs: realign AI Productivity Flow public identity and documentation"). There were no commits between Aug 22 and Sep 9.

From Sep 9 to Oct 19 (before this branch) there were 322 commits, 276 of them not merges. `src/voice_flow` changed in 269 files, and the number of test files went from 52 to 333. The main pieces of work:

- **Releases.** The app went from a Windows beta to Version 1.0. The v1.0.0 baseline landed on Oct 5, v1.0.2 on Oct 16, and internal builds 1.0.3 to 1.0.13 followed between Oct 16 and Oct 19 (installer, first launch, splash fixes, in-app updates, then silent auto-updates).
- **macOS.** A platform layer and a native Apple Silicon app bundle (Sep 15 onwards), with bundled Python, llama-server and NeMo-Speech, a real Quit, menu bar items, and many paste and Audio Flow fixes for macOS 14. Video Flow is still Windows only and is marked "coming to Mac soon".
- **Voice Flow.** Local NVIDIA Nemotron speech recognition (Nemotron Speech Streaming English 0.6B and Nemotron 3.5 ASR Streaming 0.6B, run in their own worker and kept warm), S1-mini by Superwhisper as an offline polish model with a factual safety gate, a rebuilt dictionary (Words and Replacements), safer voice commands, and speed work on dictation and polish.
- **Audio Flow.** Read and Summary modes, NotebookLM audio, a hardened player (including a stored XSS fix in the summary player history), and Mac support for selection, hotkey and playback.
- **Video Flow.** NotebookLM durable sign-in and recovery, a retry when NotebookLM refuses a video and a local fallback after that, Cinematic limited to Google AI Ultra accounts, and since Oct 19 a missing AI planning key never fails a video.
- **Onboarding and Settings.** Guided tours for all three flows, simpler Settings, and opt-out crash reports that never include user text.
- **Security.** Cross-site GETs to the local API are refused, the data folder is private on macOS, only web URLs are opened from the app, and loopback calls skip proxies.
- **Model work.** VF-1 training and evaluation work happened in this repo between Oct 12 and Oct 15, then moved to a separate private repository on Oct 16.

Before this branch, Nemotron *language* models could already be picked through the NVIDIA NIM and OpenRouter catalog entries. There was no Nebius provider and no per-job model routing.

### Added on the `feat/nebius-nemotron` branch

- A **Nebius Token Factory** provider (OpenAI-compatible, `https://api.tokenfactory.nebius.com/v1/`, Bearer key from a saved connection or `NEBIUS_API_KEY`), listed with the other providers, with a **Test** button that calls `/v1/models`.
- **Nemotron model routing** with a fast tier and a reasoning tier, runtime checks against `/v1/models`, graceful fallback, and a per-tier override on the provider page.
- **Optional Tavily web research** for Video Flow planning.
- Unit tests for all three (`tests/test_nebius_provider.py`, `tests/test_tavily_research.py`), with every HTTP call mocked.

Nothing on this branch is merged into `main` or released.

## How Token Factory and Nemotron are used

### Provider

- Code: `src/voice_flow/nebius_provider.py`, plus the `nebius` entries in `video_flow_providers.py` (provider list, seeded models, Test), `video_flow_service.py` (planning endpoint and gateway), `voice_polish_bridge.py`, `audio_summary.py`, `polisher.py` and `provider_registry.py`.
- Requests are standard Chat Completions calls to `https://api.tokenfactory.nebius.com/v1/chat/completions`, the same shape the app already sends to OpenAI and Groq.
- Key order: an active saved connection first, then `NEBIUS_API_KEY`. With neither, no Nebius request is made.

### Routing

| Tier | Default | Fallback | Jobs |
| --- | --- | --- | --- |
| Fast | `nvidia/Nemotron-3_5-Lightning` | `nvidia/nemotron-3-super-120b-a12b` | Voice Flow polishing and voice commands (`voice_polish_bridge.py`), Audio Flow summaries and explanations (`audio_summary.py`) |
| Reasoning | `nvidia/Nemotron-3-Ultra-550b-a55b` | `nvidia/nemotron-3-super-120b-a12b` | Video Flow planning; the same gateway serves creative direction and scene authoring (`video_flow_service.ProviderModelGateway`) |

Why: dictation cleanup must come back in a few seconds, so it goes to Lightning (30B total, 3B active). A video plan is a long, structured job, so it goes to Ultra.

How a model is chosen for a request:

1. The model picked in the app, if it is a concrete id. `nemotron-fast` and `nemotron-reasoning` mean "let the tier decide".
2. The tier override saved on the Nebius provider page.
3. The tier defaults above.
4. If none of those is in the account's `/v1/models` list: another served Nemotron model that suits the tier, then any served model.

The model list is cached for 10 minutes per key. Video Flow waits for it (8 second limit). Voice polishing never waits: it uses the cached list and refreshes it in the background, so a cold cache cannot slow a dictation. If the list cannot be loaded, the configured id is sent unchanged.

Nemotron can return its reasoning in a `<think>` block. The app removes that block before using the answer.

### Full voice pipeline

The app already ships local NVIDIA Nemotron speech recognition (`src/voice_flow/nemotron_engine.py`, models listed in `downloadable_models.py`): Nemotron Speech Streaming English 0.6B or Nemotron 3.5 ASR Streaming 0.6B as Q8_0 GGUF files, run through the NeMo-Speech native library. They are one-click downloads; fresh installs are offered the download, and Whisper base.en stays as the bundled fallback.

With that model downloaded and a Nebius key added, a dictation runs:

voice → Nemotron speech recognition on the device → Nemotron fast tier on Nebius (cleanup or voice command) → text typed into the focused app.

The audio never leaves the computer. Only the transcript is sent to Nebius.

### Optional Tavily research

- Code: `src/voice_flow/tavily_research.py`, hooked into `video_flow_engine/engine.py` and `video_flow_engine/code2video_runner.py`.
- Runs only when a Tavily key is saved (or `TAVILY_API_KEY` is set), the user ticks **Research with web sources**, and external AI planning is allowed for that video.
- One `POST https://api.tavily.com/search` call (basic depth, 5 results). Sources that look like code are dropped by the same check used on model output.
- The top sources (title, URL, short snippet) are added to the outline prompt. Titles and URLs are kept in the plan (`storyboard/storyboard.json` → `research_sources`) and in `plan/research_sources.json`.
- No key, box off, or any Tavily error: the video is planned exactly as before.

## Not done yet / limits

- Not tested against the live Nebius or Tavily APIs from this branch; tests mock every HTTP call. The model ids match the models.dev listing for Nebius on Oct 19, 2026, and the app checks them at runtime.
- No special "reasoning off" request flag is sent to Nemotron, because the exact Token Factory parameter was not verified. If the fast tier is slow in practice, that is the first thing to try.
- If a request to a served model fails, the app does not retry it on the fallback model; the existing failover and offline fallback take over.
- Saved keys show their models in the pickers after **Test** passes, like every other provider.

## Feedback for Nebius (draft)

TODO: write about 150 words of honest feedback after using Token Factory live. Points to cover: how setup and key creation felt, whether the `/v1/models` list matched the docs and models.dev, latency of Nemotron 3.5 Lightning for short dictation cleanup, quality of Nemotron 3 Ultra for long JSON video plans, rate limits or errors hit, pricing clarity, and one thing that would make Token Factory easier for a small desktop app.
