# Archived v5-era tests (2026-08-22)

These 17 test files target modules that no longer exist in the merged app:
the old v5 motion-island engine (`video_flow.py`, `video_flow_models.py`,
`video_flow_motion.py`, `video_flow_themes.py`, `video_generation/`),
deleted `video_flow_v3` generation internals (`source/`, old contracts
symbols), old `video_flow_engine` internals (`diversity`, `director`),
the pre-merge overlay API (`dock_from_pointer`), the old player API
(`launch_video_player`), and a removed `tests.benchmarks` helper.

The replacement engine lives in `src/voice_flow/video_flow_engine/`
(Code2Video -> Narova) and is covered by `tests/test_video_flow_engine.py`,
`test_video_flow_bridge*.py`, `test_code2video_runner.py`,
`test_narova_runner.py`, and `test_video_flow_process_manager.py`.

Reference copies of the v5 modules remain in the pristine GitHub clone:
`C:\Users\Asus\.zcode\workspace\default\AI-Productivity-Flow`.
