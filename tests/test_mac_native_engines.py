"""macOS native engines: bundled llama-server (S1-mini), NeMo-Speech (Nemotron), minimum macOS.

Pure-Python checks that run on every host: they build synthetic Mach-O files
instead of needing a Mac.
"""
from __future__ import annotations

import io
import os
import plistlib
import struct
import sys
from pathlib import Path

import pytest

from scripts import build_macos_app as builder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from voice_flow import runtime_env  # noqa: E402


# --------------------------------------------------------------------------
# synthetic Mach-O helpers
# --------------------------------------------------------------------------

def _lc_dylib(cmd: int, name: str) -> bytes:
    raw = name.encode() + b"\0"
    size = 24 + len(raw)
    size += (-size) % 8
    body = struct.pack("<IIIIII", cmd, size, 24, 0, 0, 0) + raw
    return body + b"\0" * (size - len(body))


def _lc_rpath(path: str) -> bytes:
    raw = path.encode() + b"\0"
    size = 12 + len(raw)
    size += (-size) % 8
    body = struct.pack("<III", builder._LC_RPATH, size, 12) + raw
    return body + b"\0" * (size - len(body))


def _lc_build_version(major: int, minor: int) -> bytes:
    return struct.pack("<IIIIII", builder._LC_BUILD_VERSION, 24, 1, (major << 16) | (minor << 8), 0, 0)


def _lc_version_min(major: int, minor: int) -> bytes:
    return struct.pack("<IIII", builder._LC_VERSION_MIN_MACOSX, 16, (major << 16) | (minor << 8), 0)


def macho(minos=(14, 0), deps=(), rpaths=("@loader_path",), legacy=False) -> bytes:
    cmds = [_lc_version_min(*minos) if legacy else _lc_build_version(*minos)]
    cmds += [_lc_dylib(builder._LC_LOAD_DYLIB, d) for d in deps]
    cmds += [_lc_rpath(r) for r in rpaths]
    blob = b"".join(cmds)
    header = struct.pack("<IIIIIIII", 0xFEEDFACF, 0x0100000C, 0, 6, len(cmds), len(blob), 0, 0)
    return header + blob


def fat(*slices: bytes) -> bytes:
    offset = 4096
    arches = b""
    body = b""
    for i, sl in enumerate(slices):
        arches += struct.pack(">IIIII", 0x0100000C + i, 0, offset + len(body), len(sl), 12)
        body += sl + b"\0" * ((-len(sl)) % 4096)
    head = struct.pack(">II", 0xCAFEBABE, len(slices)) + arches
    return head + b"\0" * (offset - len(head)) + body


# --------------------------------------------------------------------------
# Mach-O parsing and the minimum-macOS audit (problem 3)
# --------------------------------------------------------------------------

def test_macho_info_reads_minos_dylibs_and_rpaths(tmp_path):
    path = tmp_path / "llama-server"
    path.write_bytes(macho((13, 3), deps=["@rpath/libllama.0.dylib", "/usr/lib/libSystem.B.dylib"]))
    info = builder.macho_info(path)
    assert info["minos"] == (13, 3, 0)
    assert "@rpath/libllama.0.dylib" in info["dylibs"]
    assert info["rpaths"] == ["@loader_path"]


def test_macho_info_legacy_version_min_and_fat_takes_highest(tmp_path):
    path = tmp_path / "_cdflib.so"
    path.write_bytes(fat(macho((12, 0), legacy=True), macho((14, 0))))
    assert builder.macho_info(path)["minos"] == (14, 0, 0)


def test_macho_info_ignores_non_macho_and_java_class(tmp_path):
    text = tmp_path / "README"
    text.write_text("hello")
    java = tmp_path / "A.class"
    java.write_bytes(b"\xca\xfe\xba\xbe\x00\x00\x00\x37" + b"\0" * 64)
    assert builder.macho_info(text) == {}
    assert builder.macho_info(java) == {}


def test_info_plist_declares_the_audited_minimum(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "CONTENTS_DIR", tmp_path)
    builder.create_info_plist()
    data = plistlib.loads((tmp_path / "Info.plist").read_bytes())
    assert data["LSMinimumSystemVersion"] == builder.MACOS_MINIMUM == "14.0"


def test_minimum_audit_fails_when_a_binary_needs_newer_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "RESOURCES_DIR", tmp_path / "Contents" / "Resources")
    lib = tmp_path / "Contents" / "Resources" / "runtime" / "scipy" / "_x.so"
    lib.parent.mkdir(parents=True)
    lib.write_bytes(macho((14, 0)))
    (lib.parent / "_y.so").write_bytes(macho((15, 0)))
    with pytest.raises(RuntimeError, match="newer than the declared 14.0"):
        builder.verify_bundle_minimum_macos(tmp_path, "14.0")


def test_minimum_audit_passes_and_records_highest(tmp_path, monkeypatch):
    resources = tmp_path / "Contents" / "Resources"
    monkeypatch.setattr(builder, "RESOURCES_DIR", resources)
    runtime = resources / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "build-manifest.json").write_text("{}", encoding="utf-8")
    (runtime / "a.so").write_bytes(macho((14, 0)))
    (runtime / "b.dylib").write_bytes(macho((11, 0)))
    os.symlink("a.so", runtime / "link.so")
    assert builder.verify_bundle_minimum_macos(tmp_path, "14.0") == "14.0.0"
    import json
    manifest = json.loads((runtime / "build-manifest.json").read_text())
    assert manifest["minimum_macos"] == "14.0"
    assert manifest["highest_binary_minos"] == "14.0.0"


def test_readme_states_the_same_minimum():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "macOS 14 Sonoma or later" in readme
    assert "macOS 12+" not in readme


# --------------------------------------------------------------------------
# Bundling helpers (problems 1 and 2)
# --------------------------------------------------------------------------

def test_engine_downloads_are_pinned_with_sha256():
    for url, sha in (
        (builder.LLAMA_CPP_MACOS_ARM64_URL, builder.LLAMA_CPP_MACOS_ARM64_SHA256),
        (builder.NEMO_SPEECH_MACOS_ARM64_URL, builder.NEMO_SPEECH_MACOS_ARM64_SHA256),
    ):
        assert url.startswith("https://github.com/")
        assert "arm64" in url or "aarch64" in url
        assert len(sha) == 64 and int(sha, 16) >= 0
    assert builder.LLAMA_CPP_BUILD in builder.LLAMA_CPP_MACOS_ARM64_URL
    # macOS ships NeMo-Speech v0.2.0 (C ABI v1, like the v0.1.0 Windows download):
    # v0.1.0 was ~20x slower than real time on Apple Silicon.
    assert builder.NEMO_SPEECH_VERSION == "0.2.0"
    assert f"/v{builder.NEMO_SPEECH_VERSION}/" in builder.NEMO_SPEECH_MACOS_ARM64_URL


def test_download_rejects_checksum_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "REPO_ROOT", tmp_path)

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *a, **k: Resp(b"tampered"))
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        builder._download_verified("https://example.invalid/x.tar.gz", "0" * 64, "x.tar.gz")
    assert not (tmp_path / ".cache" / "engines" / "x.tar.gz").exists()


def test_rpath_closure_copies_only_needed_libs_and_keeps_symlinks(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "llama-server").write_bytes(macho(deps=["@rpath/libllama.0.dylib", "/usr/lib/libc++.1.dylib"]))
    (src / "libllama.0.7.0.dylib").write_bytes(macho(deps=["@rpath/libggml.0.dylib"]))
    os.symlink("libllama.0.7.0.dylib", src / "libllama.0.dylib")
    (src / "libggml.0.27.0.dylib").write_bytes(macho())
    os.symlink("libggml.0.27.0.dylib", src / "libggml.0.dylib")
    (src / "llama-cli").write_bytes(macho())  # not needed by llama-server
    dest = tmp_path / "dest"
    copied = builder._copy_with_rpath_closure(src, ["llama-server"], dest)
    names = sorted(p.name for p in copied)
    assert names == ["libggml.0.27.0.dylib", "libllama.0.7.0.dylib", "llama-server"]
    assert (dest / "libllama.0.dylib").is_symlink()
    assert os.readlink(dest / "libggml.0.dylib") == "libggml.0.27.0.dylib"
    assert not (dest / "llama-cli").exists()


def test_rpath_closure_fails_loudly_on_missing_dependency(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "llama-server").write_bytes(macho(deps=["@rpath/libmissing.dylib"]))
    with pytest.raises(RuntimeError, match="libmissing.dylib"):
        builder._copy_with_rpath_closure(src, ["llama-server"], tmp_path / "dest")


def test_native_engines_skipped_for_intel_target(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(builder, "RESOURCES_DIR", tmp_path)
    called = []
    monkeypatch.setattr(builder, "bundle_llama_server", lambda *a: called.append("llama"))
    monkeypatch.setattr(builder, "bundle_nemo_speech", lambda *a: called.append("nemo"))
    monkeypatch.setattr(builder, "bundle_video_flow_toolchain", lambda *a: called.append("video") or {})
    builder.bundle_native_engines("x86_64")
    assert called == []
    builder.bundle_native_engines("aarch64")
    assert called == ["llama", "nemo", "video"]


# --------------------------------------------------------------------------
# Runtime lookup inside the .app
# --------------------------------------------------------------------------

@pytest.fixture
def mac_bundle(tmp_path, monkeypatch):
    resources = tmp_path / "AI Productivity Flow.app" / "Contents" / "Resources"
    runtime = resources / "runtime"
    (runtime / "llama").mkdir(parents=True)
    (runtime / "nemo" / "lib").mkdir(parents=True)
    (runtime / "python" / "bin").mkdir(parents=True)
    (runtime / "build-manifest.json").write_text("{}", encoding="utf-8")
    (runtime / "llama" / "llama-server").write_bytes(b"x")
    (runtime / "nemo" / "lib" / "libnemo_speech_asr_c.dylib").write_bytes(b"x")
    (runtime / "python" / "bin" / "python3").write_bytes(b"x")
    monkeypatch.setattr(runtime_env, "_mac_resources_dir", lambda: resources)
    monkeypatch.setattr(runtime_env.sys, "platform", "darwin")
    monkeypatch.delenv("LLAMA_SERVER_PATH", raising=False)
    return runtime


def test_runtime_env_finds_bundled_engines_on_mac(mac_bundle):
    assert runtime_env.mac_bundle_runtime_dir() == mac_bundle
    assert runtime_env.mac_bundled_llama_server() == mac_bundle / "llama" / "llama-server"
    assert runtime_env.mac_bundled_nemo_speech_dylib() == mac_bundle / "nemo" / "lib" / "libnemo_speech_asr_c.dylib"
    # The native speech worker runs on the real bundled python3, not the launcher.
    assert runtime_env.native_worker_python() == str(mac_bundle / "python" / "bin" / "python3")


def test_runtime_env_mac_helpers_inert_off_mac(mac_bundle, monkeypatch):
    monkeypatch.setattr(runtime_env.sys, "platform", "win32")
    assert runtime_env.mac_bundle_runtime_dir() is None
    assert runtime_env.mac_bundled_llama_server() is None
    assert runtime_env.mac_bundled_nemo_speech_dylib() is None
    assert runtime_env.native_worker_python() == runtime_env.python_executable()


def test_runtime_env_requires_build_manifest(mac_bundle):
    (mac_bundle / "build-manifest.json").unlink()
    assert runtime_env.mac_bundle_runtime_dir() is None


def test_vf1_engine_uses_bundled_llama_server_on_mac(mac_bundle, monkeypatch):
    from voice_flow import vf1_engine

    monkeypatch.setattr(vf1_engine.sys, "platform", "darwin")
    engine = vf1_engine.VF1Engine()
    assert engine._find_llama_server_binary() == mac_bundle / "llama" / "llama-server"


def test_vf1_engine_explicit_override_still_wins_on_mac(mac_bundle, monkeypatch, tmp_path):
    from voice_flow import vf1_engine

    custom = tmp_path / "my-llama-server"
    custom.write_bytes(b"x")
    monkeypatch.setenv("LLAMA_SERVER_PATH", str(custom))
    monkeypatch.setattr(vf1_engine.sys, "platform", "darwin")
    assert vf1_engine.VF1Engine()._find_llama_server_binary() == custom


def test_s1_runtime_available_with_bundled_server(mac_bundle, monkeypatch):
    import importlib.util

    from voice_flow import s1_engine, vf1_engine

    monkeypatch.setattr(vf1_engine.sys, "platform", "darwin")
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name == "llama_cpp" else real_find_spec(name, *a))
    assert s1_engine.is_s1_runtime_available() is True


def test_nemotron_finds_bundled_dylib_on_mac(mac_bundle, monkeypatch):
    from voice_flow import nemotron_engine

    monkeypatch.setattr(nemotron_engine.sys, "platform", "darwin")
    found = nemotron_engine._find_nemo_speech_dll()
    assert found == mac_bundle / "nemo" / "lib" / "libnemo_speech_asr_c.dylib"
    assert nemotron_engine._ensure_nemo_speech_binaries() == found


def test_nemotron_worker_spawned_with_native_worker_python():
    source = (ROOT / "src/voice_flow/nemotron_engine.py").read_text(encoding="utf-8")
    assert "NativeASRClient(str(dll_path), runtime_env.native_worker_python())" in source


def _spawned_cmd(monkeypatch, tmp_path, platform_name):
    from voice_flow import vf1_engine

    monkeypatch.setattr(vf1_engine.sys, "platform", platform_name)
    manager = vf1_engine.LlamaServerManager(run_dir=tmp_path / "run")
    seen = []

    def fake_spawn(cmd):
        seen.append(cmd)
        raise RuntimeError("stop after capturing the command")

    monkeypatch.setattr(manager, "_spawn", fake_spawn)
    assert manager.ensure_running(binary=tmp_path / "llama-server", model_path=tmp_path / "s1.gguf",
                                  ready_timeout=0.5) is False
    return seen[0]


def test_llama_server_skips_metal_device_on_mac(monkeypatch, tmp_path):
    cmd = _spawned_cmd(monkeypatch, tmp_path, "darwin")
    assert cmd[cmd.index("-dev") + 1] == "none"
    assert cmd[cmd.index("-ngl") + 1] == "0"


def test_llama_server_command_unchanged_off_mac(monkeypatch, tmp_path):
    cmd = _spawned_cmd(monkeypatch, tmp_path, "win32")
    assert "-dev" not in cmd


def test_llama_server_ready_timeout_longer_on_mac(monkeypatch):
    from voice_flow import vf1_engine

    engine = vf1_engine.VF1Engine()
    monkeypatch.setattr(vf1_engine.sys, "platform", "darwin")
    assert engine._server_ready_timeout() == 60.0
    monkeypatch.setattr(vf1_engine.sys, "platform", "win32")
    assert engine._server_ready_timeout() == float(engine.config.server_ready_timeout_seconds)


def _capture_popen(monkeypatch, platform_name):
    from voice_flow import vf1_engine

    monkeypatch.setattr(vf1_engine.sys, "platform", platform_name)
    monkeypatch.setattr(vf1_engine.os, "name", "posix")
    seen = {}

    class FakeProc:
        pid = 987654

        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        seen["cmd"], seen["env"] = cmd, kwargs.get("env") or {}
        return FakeProc()

    monkeypatch.setattr(vf1_engine.subprocess, "Popen", fake_popen)
    marked = []
    monkeypatch.setattr(vf1_engine.child_processes, "track", lambda proc, name="": proc)
    monkeypatch.setattr(vf1_engine.child_processes, "mark_hard_kill", lambda proc: marked.append(proc))
    manager = vf1_engine.LlamaServerManager(run_dir=Path("/nonexistent-run"))
    manager._spawn(["llama-server", "-m", "s1.gguf"])
    return seen, marked


def test_mac_llama_server_creates_no_metal_device_and_is_hard_killed(monkeypatch):
    seen, marked = _capture_popen(monkeypatch, "darwin")
    assert seen["env"].get("GGML_METAL_DEVICES") == "0"
    script = seen["cmd"][2]
    assert 'kill -KILL "$child"' in script and 'kill -TERM "$child"' not in script
    assert len(marked) == 1


def test_linux_llama_server_spawn_unchanged(monkeypatch):
    seen, marked = _capture_popen(monkeypatch, "linux")
    assert "GGML_METAL_DEVICES" not in seen["env"]
    assert 'kill -TERM "$child"' in seen["cmd"][2]
    assert marked == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_hard_kill_tree_never_delivers_sigterm(tmp_path):
    import subprocess
    import time
    from voice_flow import child_processes

    marker = tmp_path / "got-term"
    proc = subprocess.Popen(
        ["/bin/sh", "-c", f"trap 'echo term > {marker}; exit 0' TERM; while :; do sleep 0.05; done"],
        start_new_session=True,
    )
    try:
        time.sleep(0.3)
        child_processes.track(proc, "hard")
        child_processes.mark_hard_kill(proc)
        child_processes.kill_tree(proc, timeout=3)
        assert proc.poll() is not None
        assert proc.returncode == -9
        assert not marker.exists()
    finally:
        child_processes.untrack(proc)
        if proc.poll() is None:
            proc.kill()
