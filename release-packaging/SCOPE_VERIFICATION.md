> 🗄️ Release-packaging audit report (2026-08-22 mission). Current installer reference: [../release/](../release/). Open items live in CLEAN_MACHINE_TEST.md and RELEASE_CHECKLIST.md.
# SCOPE_VERIFICATION — product behavior unchanged

Method: full diff review of the working tree vs baseline `195ffa8`
(`git diff --stat` + file-by-file classification in FILES_CHANGED.md),
plus before/after test-suite comparison and a live check that the running
development app continued operating throughout the mission.

## Mission §54 checklist

| Question | Answer |
|---|---|
| Voice Flow functionality changed? | NO — transcriber change is the permitted model-path resolution only |
| Audio Flow functionality changed? | NO |
| Video Flow behavior changed? | NO — path resolution/env only; prompts, treatments, rendering, quality untouched |
| Generated video quality changed? | NO |
| Onboarding redesigned? | NO — not touched |
| Flow Bar design changed? | NO |
| App navigation changed? | NO |
| Global shortcuts changed? | NO |
| Mouse hooks changed? | NO |
| Clipboard injection changed? | NO |
| User settings semantics changed? | NO (one NEW independent setting key from the voice feature, pre-existing) |
| Provider UX changed? | NO |
| Local LLM added? | NO |
| Developer API keys bundled? | NO (verified: staging built from repo + official downloads only) |
| Requires system Python? | NO — private 3.12 runtime; watchdog prefers it |
| Requires system Node? | NO — bundled; npx eliminated at runtime |
| Requires system FFmpeg? | NO — bundled + subprocess PATH scoping |
| Requires Git? | NO |
| Requires npm/npx from the user? | NO — hyperframes node_modules bundled |
| Requires a Whisper download after install? | NO — base.en bundled |
| Works from one normal-user installer? | YES (built; install test executed on build machine; clean-VM caveat in CLEAN_MACHINE_TEST.md) |
| Tested on clean Windows? | PARTIAL — honestly stated in CLEAN_MACHINE_TEST.md |

## Files outside packaging scope modified

None. `overlay.py`, `hotkeys.py`, `mouse_hook.py`, `injector.py`,
`style_engine.py`, GUI assets, `creative_director.py`, `scene_author.py`,
provider/oauth/db code: untouched.

## Test suite

Baseline (before any change): 253 passed / 1 skipped — NOTE: run against the
machine's editable install (the repo previously had no `pythonpath` config),
which masked that 6 tests need the vendored third_party tree.
Final (repository package pinned via pytest `pythonpath = ["src"]`):
**247 passed / 6 skipped, 0 failures** standalone — the 6 skips are
vendor-dependent tests (Code2Video prompts / Narova tool) that now skip
explicitly when third_party is absent and pass wherever the vendor exists
(the development install with third_party runs them green). 4 new packaging
tests added. No previously passing test fails.
