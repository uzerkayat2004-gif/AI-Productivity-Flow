"""v1.0.14: Video Flow runs on macOS. No "coming to Mac soon" gate anywhere,
and the packaged Mac app resolves its own Node, ffmpeg, Narova and HyperFrames."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "voice_flow"


def _shipped_text_files():
    for base in (SRC, ROOT / "scripts", ROOT / "docs"):
        for path in base.rglob("*"):
            if path.suffix in {".py", ".js", ".html", ".css", ".json", ".md"} and "__pycache__" not in path.parts and "node_modules" not in path.parts:
                yield path
    yield ROOT / "README.md"


def test_no_coming_soon_text_anywhere():
    hits = []
    for path in _shipped_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"coming to Mac soon|Video Flow is coming", text, re.IGNORECASE):
            if path.name == "walkthrough.py":
                continue  # the walkthrough checks the text is absent
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_gate_module_and_hooks_are_gone():
    assert not (SRC / "video_flow_platform.py").exists()
    for rel in ("gui/api_server.py", "main.py", "video_flow_widget.py", "gui/app.js", "gui/video-flow.js"):
        text = (SRC / rel).read_text(encoding="utf-8")
        assert "video_flow_supported" not in text and "vfVideoFlowGatedOnMac" not in text and "vfApplyMacVideoFlowGate" not in text, rel
    assert not (SRC / "gui" / "assets" / "onboarding" / "scene_2_mac_mixed.mp3").exists()


def _fake_mac_bundle(tmp_path: Path) -> Path:
    res = tmp_path / "AI Productivity Flow.app" / "Contents" / "Resources"
    runtime = res / "runtime"
    (runtime / "node" / "bin").mkdir(parents=True)
    (runtime / "node" / "bin" / "node").write_text("x")
    (runtime / "ffmpeg").mkdir()
    (runtime / "ffmpeg" / "ffmpeg").write_text("x")
    (runtime / "ffmpeg" / "ffprobe").write_text("x")
    (runtime / "narova" / "tool" / "bin").mkdir(parents=True)
    (runtime / "narova" / "tool" / "bin" / "narova.js").write_text("x")
    (runtime / "build-manifest.json").write_text("{}")
    return res


def test_mac_bundle_resolves_video_toolchain(tmp_path, monkeypatch):
    from voice_flow import runtime_env as RE

    res = _fake_mac_bundle(tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(RE, "_mac_resources_dir", lambda: res)
    monkeypatch.setattr(RE, "runtime_root", lambda: None)
    rt = res / "runtime"
    assert RE.app_runtime_root() == rt
    assert RE.is_packaged_app() is True
    assert RE.node_executable() == rt / "node" / "bin" / "node"
    assert RE.ffmpeg_executable() == rt / "ffmpeg" / "ffmpeg"
    assert RE.ffprobe_executable() == rt / "ffmpeg" / "ffprobe"
    assert RE.ffmpeg_dir() == rt / "ffmpeg"
    assert RE.narova_tool_root() == rt / "narova"


def test_narova_environment_uses_the_mac_bundle(tmp_path, monkeypatch):
    from voice_flow import runtime_env as RE
    from voice_flow.video_flow_engine import narova_runner as NR

    res = _fake_mac_bundle(tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(RE, "_mac_resources_dir", lambda: res)
    monkeypatch.setattr(RE, "runtime_root", lambda: None)
    monkeypatch.setattr(RE, "native_worker_python", lambda: "/bundle/python3")
    env = NR._safe_environment()
    rt = res / "runtime"
    assert env["NAROVA_HF_MODULES"] == str(rt / "hyperframes")
    assert env["NAROVA_PYTHON"] == "/bundle/python3"
    first = env["PATH"].split(":")[:2]
    assert str(rt / "ffmpeg") in first and str(rt / "node" / "bin") in first


def test_render_browser_cache_finds_the_mac_binary(tmp_path, monkeypatch):
    from voice_flow import runtime_env as RE

    exe = tmp_path / ".cache" / "puppeteer" / "chrome-headless-shell" / "mac_arm-1" / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell"
    exe.parent.mkdir(parents=True)
    exe.write_text("x")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert RE.render_browser_cache() == exe


def test_mac_runtime_fingerprint_records_the_bundled_toolchain():
    from voice_flow import bundled_runtime as BR

    mac = BR.mac_runtime()
    assert mac["node"] == BR.MAC_NODE and mac["ffmpeg"] == BR.MAC_FFMPEG and mac["hyperframes"] == BR.MAC_HYPERFRAMES
    build = (ROOT / "scripts" / "build_macos_app.py").read_text(encoding="utf-8")
    assert f'VF_NODE_VERSION = "{BR.MAC_NODE}"' in build
    assert f'VF_FFMPEG_VERSION = "{BR.MAC_FFMPEG}"' in build
    assert f'VF_HYPERFRAMES_VERSION = "{BR.MAC_HYPERFRAMES}"' in build
    assert "bundle_video_flow_toolchain(runtime_dir" in build


def test_ffprobe_is_resolved_from_the_bundle(monkeypatch, tmp_path):
    from voice_flow import runtime_env as RE
    from voice_flow.video_flow_engine.notebooklm import provenance

    media = tmp_path / "v.mp4"
    media.write_bytes(b"x" * 10)
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd

        class R:
            returncode = 0
            stdout = "{}"
            stderr = ""
        return R()

    monkeypatch.setattr(RE, "ffprobe_executable", lambda: Path("/bundle/ffprobe"))
    monkeypatch.setattr(provenance.subprocess, "run", fake_run)
    provenance.probe_media_file(media)
    assert seen["cmd"][0] == "/bundle/ffprobe"
