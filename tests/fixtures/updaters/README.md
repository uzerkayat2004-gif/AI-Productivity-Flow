Verbatim copies of shipped updater code, used by tests/test_small_updates_v108.py
to check what an *already installed* app (whose code can no longer change)
decides for a new release.

- v1_0_6_app_updater.py.txt   = `git show v1.0.6:src/voice_flow/app_updater.py`
  (byte-identical to v1.0.7's, so it stands for both)
- v1_0_6_bundled_runtime.py.txt = `git show v1.0.6:src/voice_flow/bundled_runtime.py`
- v1_0_7_bundled_runtime.py.txt = `git show v1.0.7:src/voice_flow/bundled_runtime.py`

They are `.txt` so pytest and linters never import them directly.
