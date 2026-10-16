"""The macOS .app ships faster-whisper base.en so dictation never downloads."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

from voice_flow import runtime_env

REPO = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fake_mac_bundle(tmp_path: Path, with_model: bool = True) -> Path:
    resources = tmp_path / "AI Productivity Flow.app" / "Contents" / "Resources"
    runtime = resources / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "build-manifest.json").write_text("{}", encoding="utf-8")
    if with_model:
        model = runtime / "models" / "whisper" / "base.en"
        model.mkdir(parents=True)
        (model / "model.bin").write_bytes(b"x")
    return resources


def test_mac_bundle_whisper_model_resolves_on_darwin(tmp_path, monkeypatch):
    resources = _fake_mac_bundle(tmp_path)
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(resources))
    monkeypatch.setattr(sys, "platform", "darwin")
    path = runtime_env.whisper_model_path()
    assert path == (resources / "runtime" / "models" / "whisper" / "base.en").resolve()
    # The Mac bundle is still not a Windows install.
    assert runtime_env.install_root() is None


def test_mac_bundle_without_model_returns_none(tmp_path, monkeypatch):
    resources = _fake_mac_bundle(tmp_path, with_model=False)
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(resources))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert runtime_env.whisper_model_path() is None


def test_mac_bundle_layout_ignored_off_darwin(tmp_path, monkeypatch):
    resources = _fake_mac_bundle(tmp_path)
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(resources))
    monkeypatch.setattr(sys, "platform", "win32")
    assert runtime_env.whisper_model_path() is None


def test_transcriber_uses_bundled_mac_model_offline(tmp_path, monkeypatch):
    resources = _fake_mac_bundle(tmp_path)
    monkeypatch.setenv("AI_PRODUCTIVITY_FLOW_ROOT", str(resources))
    monkeypatch.setattr(sys, "platform", "darwin")
    from voice_flow import transcriber

    ref, local_only = transcriber.resolve_local_whisper_model("base.en")
    assert Path(ref) == (resources / "runtime" / "models" / "whisper" / "base.en").resolve()
    assert local_only is True


def test_build_script_pins_same_whisper_as_windows():
    mac = _load_module("build_macos_app_pin", REPO / "scripts" / "build_macos_app.py")
    win = _load_module("assemble_windows_staging_pin", REPO / "release" / "assemble_windows_staging.py")
    assert mac.WHISPER_REVISION == win.WHISPER_REVISION
    assert mac.WHISPER_FILES == win.WHISPER_FILES


def test_stage_whisper_model_verifies_and_copies(tmp_path, monkeypatch):
    mac = _load_module("build_macos_app_stage", REPO / "scripts" / "build_macos_app.py")
    payloads = {name: f"payload-{name}".encode() for name in mac.WHISPER_FILES}
    monkeypatch.setattr(
        mac, "WHISPER_FILES", {n: hashlib.sha256(b).hexdigest() for n, b in payloads.items()}
    )
    calls = []

    def fetch(url, dest):
        name = url.rsplit("/", 1)[-1]
        calls.append(name)
        dest.write_bytes(payloads[name])

    runtime = tmp_path / "runtime"
    info = mac.stage_whisper_model(runtime, cache_dir=tmp_path / "cache", fetch=fetch)
    target = runtime / "models" / "whisper" / "base.en"
    for name, data in payloads.items():
        assert (target / name).read_bytes() == data
    assert info["revision"] == mac.WHISPER_REVISION
    assert sorted(calls) == sorted(payloads)
    # Second run uses the verified cache: no downloads.
    calls.clear()
    mac.stage_whisper_model(tmp_path / "runtime2", cache_dir=tmp_path / "cache", fetch=fetch)
    assert calls == []


def test_stage_whisper_model_rejects_bad_checksum(tmp_path):
    mac = _load_module("build_macos_app_bad", REPO / "scripts" / "build_macos_app.py")

    def fetch(url, dest):
        dest.write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="CHECKSUM MISMATCH"):
        mac.stage_whisper_model(tmp_path / "runtime", cache_dir=tmp_path / "cache", fetch=fetch)
