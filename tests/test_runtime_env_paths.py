"""Packaging/runtime-path tests for the central resolver."""

from __future__ import annotations

import json
from pathlib import Path

from voice_flow import runtime_env


def test_dev_mode_defaults_to_none(tmp_path: Path, monkeypatch) -> None:
    # Point at a directory that definitely has no runtime-manifest.json above it.
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(tmp_path / "not-an-install"))
    assert runtime_env.is_installed() is False
    assert runtime_env.install_root() is None
    assert runtime_env.node_executable() is None
    assert runtime_env.whisper_model_path() is None
    assert runtime_env.pythonw_executable() is None
    assert runtime_env.preflight_problems() == []


def _fake_install(tmp_path: Path) -> Path:
    root = tmp_path / "AI Productivity Flow"
    runtime = root / "runtime"
    (runtime / "python").mkdir(parents=True)
    (runtime / "node").mkdir()
    (runtime / "ffmpeg").mkdir()
    (runtime / "models" / "whisper" / "base.en").mkdir(parents=True)
    (runtime / "runtime-manifest.json").write_text("{}", encoding="utf-8")
    (runtime / "python" / "pythonw.exe").write_bytes(b"x")
    (runtime / "python" / "python.exe").write_bytes(b"x")
    (runtime / "node" / "node.exe").write_bytes(b"x")
    (runtime / "ffmpeg" / "ffmpeg.exe").write_bytes(b"x")
    (runtime / "ffmpeg" / "ffprobe.exe").write_bytes(b"x")
    (runtime / "models" / "whisper" / "base.en" / "model.bin").write_bytes(b"x")
    return root


def test_installed_mode_resolves_private_runtime(tmp_path: Path, monkeypatch) -> None:
    root = _fake_install(tmp_path)
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(root))
    assert runtime_env.is_installed()
    assert runtime_env.install_root() == root
    assert runtime_env.node_executable() == root / "runtime" / "node" / "node.exe"
    assert runtime_env.ffmpeg_executable() == root / "runtime" / "ffmpeg" / "ffmpeg.exe"
    assert runtime_env.ffprobe_executable() == root / "runtime" / "ffmpeg" / "ffprobe.exe"
    assert runtime_env.whisper_model_path() == root / "runtime" / "models" / "whisper" / "base.en"
    assert runtime_env.pythonw_executable() == str(root / "runtime" / "python" / "pythonw.exe")


def test_preflight_classifies_missing_components(tmp_path: Path, monkeypatch) -> None:
    root = _fake_install(tmp_path)
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(root))
    # Hermetic: this developer machine has a real render-browser cache.
    monkeypatch.setattr(runtime_env, "render_browser_cache", lambda: None)
    monkeypatch.setattr(runtime_env, "browser_executable", lambda: None)
    problems = runtime_env.preflight_problems()
    # The fake install intentionally lacks the render browser (user-provisioned).
    assert problems == ["render-browser"]
    (root / "runtime" / "node" / "node.exe").unlink()
    problems = runtime_env.preflight_problems()
    assert "node-runtime" in problems
    assert "render-browser" in problems


def test_manifest_is_valid_json_when_installed(tmp_path: Path, monkeypatch) -> None:
    root = _fake_install(tmp_path)
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(root))
    manifest = json.loads((runtime_env.runtime_root() / "runtime-manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
