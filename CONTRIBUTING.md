# Contributing to AI Productivity Flow

Thanks for contributing! This guide is for **developers** working from source.
Normal users should install the Windows installer from
[GitHub Releases](https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases) —
no developer tooling needed.

## Development setup

```bash
git clone https://github.com/uzerkayat2004-gif/AI-Productivity-Flow.git
cd AI-Productivity-Flow
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e .
```

- **Python**: 3.10+ supported for development; the shipped Windows runtime is
  CPython 3.12 (what the installer bundles and CI-equivalent runs target).
- **Windows only**: global hooks (mouse/keyboard), clipboard injection, and the
  Flow Bar use Win32 APIs; the product currently targets Windows 10/11 x64.
- **Video Flow from source**: generation additionally uses the vendored
  production tool under `third_party/` (not tracked in this repository — see
  `release/THIRD_PARTY_NOTICES.txt` for the components the installer ships) and
  FFmpeg on PATH. The bundled installer provides all of this automatically.

## Running tests

```bash
python -m pytest tests/ -q
```

The suite covers the dictation pipeline, dictionary/corrections, providers and
consent, Video Flow engine contracts (planner, creative director, scene
authoring, bridge, runner), packaging/runtime-path resolution, and the API
surface. Vendor-dependent integration tests skip automatically when the vendored
tool is absent.

## Repository layout

```
src/voice_flow/            application package (voice_flow)
  video_flow_engine/       Video Flow generation engine
  gui/                     dashboard UI (HTML/JS) + loopback API server
tests/                     active test suite
tests_archived_v5/         retired tests from the pre-Narova engine (historical)
release/                   Windows installer build (Inno Setup script, notices)
release-packaging/         release/packaging audit reports
docs/                      product facts, maps, metadata proposals
video_flow_renderer/       legacy dev-side renderer assets (not shipped)
```

## Where to extend

- **Video Flow visuals**: add or tune treatments in
  `video_flow_engine/creative_director.py` (registry + prompts) and
  `scene_author.py` (deterministic emitters). Keep model output
  script-free — `validate_no_executable_code` is enforced everywhere.
- **Providers**: follow the existing consent + isolation patterns
  (`provider_validation.py`, isolated one-shot workers, stdin-only credentials).
- **UI**: the dashboard lives in `src/voice_flow/gui/` and talks to the
  loopback-only API on 127.0.0.1:8991.

## Ground rules

- Don't change product behavior without tests; don't weaken the security
  boundaries (`validate_no_executable_code`, consent gates, scrubbed envs).
- Keep public documentation aligned with code — see
  [docs/PRODUCT_FACTS.md](docs/PRODUCT_FACTS.md) before editing claims.
- Commits: conventional-style summaries (`feat:`, `fix:`, `docs:`).

## Security

See [SECURITY.md](SECURITY.md) before handling credentials or provider APIs.
