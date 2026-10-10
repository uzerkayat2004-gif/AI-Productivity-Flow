# Upstream Provenance: Code2Video

- **Upstream Repository**: [https://github.com/showlab/Code2Video](https://github.com/showlab/Code2Video)
- **Pinned Commit SHA**: `7729a8b71582b3982bef70f5860a9a98354e9a70`
- **License**: MIT License (see `LICENSE`)

## Purpose
AI Productivity Flow vendors a minimal subset of Code2Video for planning prompts and provider compatibility. It uses Code2Video's stage-1 and stage-2 structured prompt templates and request helpers, rather than the upstream Manim animation rendering pipeline.

## Vendored Files
- `LICENSE` — MIT License text
- `UPSTREAM.md` — Provenance documentation and pinned commit reference
- `prompts/stage1.py` — Stage 1 storyboard/planning prompt template
- `prompts/stage2.py` — Stage 2 scene detail prompt template
- `src/gpt_request.py` — Provider request utility helper
- `src/api_config.json` — Upstream API configuration template (placeholders only)
