# Voice Flow Next Actions — Style-Aware Post-Dictation Pipeline (Design)

Status: design seams implemented in the 2026-09-01 latency upgrade; the action
router itself ships in the next major update.

## Goal

After dictating, the user says something like *"make this an email"*. The app
must then reformat the polished transcript according to the style the user
selected for that target (e.g. their preferred email style from the Style
feature) instead of the generic per-app cleanup it applied inline.

## Seams already in place (this upgrade)

1. **Style resolution at capture time** — `_capture_session()` in `main.py`
   resolves the target app style via `style_engine.resolve_for_target(hwnd)`
   and freezes it on the session (`resolved_style`, `app_category`,
   `style_id`). The pipeline never re-reads the foreground window, so a
   slow injection target switch cannot corrupt the style used.
2. **Style-aware AI polish** — `_finalize_text()` passes
   `resolved_style.instruction` into `polisher.polish()`; the polisher embeds
   it as the `Style instruction:` line in the LLM prompt. The prompt path is
   therefore already style-parameterized end to end.
3. **Fast + quality lanes** — `polisher._polish_with_api_pool()` now runs an
   interactive fast lane (`gemini-3.5-flash-lite`, ~1s) before the user's
   preferred model. Inline dictation uses the fast lane; the future action
   reformat pass should use the *quality* lane (set
   `voice_flow_polish_speed_mode = "quality"` for that call, or route the
   action prompt directly to the preferred model) because the user is no
   longer waiting synchronously.
4. **Fidelity guard** — `_candidate_preserves_content()` (sliding overlap +
   stemmed matching + ending check) protects any future reformat from
   hallucinated or truncated output.

## Proposed action pipeline (next update)

```
raw transcript -> split_press_enter / apply_spoken_punctuation
             -> ACTION DETECTOR (suffix phrases: "make this an email",
                "send this as a message", "make a note", ...)
             -> if action detected:
                  body = strip action phrase
                  style = style_engine.user_style_for(action.target)  # e.g. email
                  text = polisher.polish(body, style_instruction=style,
                                         speed_mode="quality")
                  deliver via action adapter (clipboard to mail window,
                  mailto:, or API later)
             -> else: existing inline pipeline
```

Design notes:

- The action phrase must be detected BEFORE polishing so the AI does not
  polish the command itself into the body.
- Persist `action` + `target_style_id` on the dictation history row so
  retries re-run the same transformation (mirrors `retry_history`).
- Keep the action adapter interface small: `deliver(text, target) -> bool`
  with `clipboard` as the first adapter (already exists via `injector`).
- The `voice_flow_polish_speed_mode` setting (`balanced` | `fast` |
  `quality`) is read live from storage each polish call, so the GUI can
  expose it without engine changes.
