"""Mac bundle and Windows staging checks for vendored Code2Video."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bundle_code2video import api_config_is_placeholder, copy_code2video
from voice_flow import runtime_env


def test_copy_drops_bytecode_and_replaces_real_secrets(tmp_path: Path):
    source = tmp_path / "src"
    cache = source / "prompts" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "stage1.cpython-312.pyc").write_bytes(b"bytecode")
    (source / "prompts" / "stage1.py").write_text("def get_prompt1_outline():\n    return ''\n", encoding="utf-8")
    (source / "src").mkdir()
    (source / "src" / "gpt_request.py").write_text("import openai\n", encoding="utf-8")
    (source / "src" / "api_config.json").write_text(
        json.dumps({"claude": {"api_key": "sk-real-secret-value"}}),
        encoding="utf-8",
    )
    (source / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")

    destination = tmp_path / "bundle" / "third_party" / "code2video"
    copy_code2video(source, destination)

    assert (destination / "prompts" / "stage1.py").is_file()
    assert (destination / "src" / "gpt_request.py").is_file()
    assert not (destination / "prompts" / "__pycache__").exists()
    assert not (destination / ".env").exists()
    config = destination / "src" / "api_config.json"
    assert api_config_is_placeholder(config)
    assert "sk-real-secret-value" not in config.read_text(encoding="utf-8")


def test_real_vendor_copy_keeps_placeholder_config(tmp_path: Path):
    source = Path(__file__).resolve().parents[1] / "third_party" / "code2video"
    destination = tmp_path / "Resources" / "third_party" / "code2video"
    copy_code2video(source, destination)

    assert (destination / "prompts" / "stage1.py").is_file()
    assert (destination / "src" / "gpt_request.py").is_file()
    assert not any(destination.rglob("__pycache__"))
    assert not any(destination.rglob("*.pyc"))
    config = destination / "src" / "api_config.json"
    assert config.is_file()
    assert api_config_is_placeholder(config)


def test_macos_bundle_resolves_code2video_from_build_manifest(tmp_path: Path, monkeypatch):
    resources = tmp_path / "AI Productivity Flow.app" / "Contents" / "Resources"
    (resources / "runtime").mkdir(parents=True)
    (resources / "runtime" / "build-manifest.json").write_text("{}", encoding="utf-8")
    prompts = resources / "third_party" / "code2video" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "stage1.py").write_text("# prompt\n", encoding="utf-8")
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(resources))

    assert runtime_env.is_installed() is False
    assert runtime_env.code2video_root() == resources / "third_party" / "code2video"


def test_windows_runtime_code2video_still_wins(tmp_path: Path, monkeypatch):
    root = tmp_path / "AI Productivity Flow"
    runtime_vendor = root / "runtime" / "code2video" / "prompts"
    runtime_vendor.mkdir(parents=True)
    (runtime_vendor / "stage1.py").write_text("# windows\n", encoding="utf-8")
    (root / "runtime" / "runtime-manifest.json").write_text("{}", encoding="utf-8")
    mac_vendor = root / "third_party" / "code2video" / "prompts"
    mac_vendor.mkdir(parents=True)
    (mac_vendor / "stage1.py").write_text("# mac\n", encoding="utf-8")
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(root))

    assert runtime_env.is_installed() is True
    assert runtime_env.code2video_root() == root / "runtime" / "code2video"


def test_openai_dependency_is_declared():
    root = Path(__file__).resolve().parents[1]
    for relative in ("requirements.txt", "pyproject.toml"):
        text = (root / relative).read_text(encoding="utf-8")
        assert "openai>=1.40.0,<3" in text
    installer = (root / "release" / "installer" / "apf-setup.iss").read_text(encoding="utf-8")
    assert r"runtime\code2video" in installer
    windows_build = (root / "release" / "build_windows_release.py").read_text(encoding="utf-8")
    assert "refresh_code2video_vendor" in windows_build
    assert "import openai" in windows_build
