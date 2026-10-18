"""v1.0.8: in-app updates download the small app zip, and Node 22 for Video
Flow is an app-managed download instead of a bundled runtime change.

The v1.0.6 (and identical v1.0.7) updater is loaded from a verbatim copy of
its shipped source, because installed apps keep that code until they update.
"""

from __future__ import annotations

import hashlib
import http.server
import importlib.util
import io
import json
import subprocess
import sys
import threading
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "updaters"
APP_ZIP_SIZE = 50 * 1024 * 1024
FULL_SIZE = 526_900_000


def _module_from_source(name: str, source: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = f"<{name}>"
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _old_updater(monkeypatch, bundled_fixture: str) -> types.ModuleType:
    """The shipped updater, wired to the shipped bundled_runtime pins."""
    pins = _module_from_source("old_bundled_runtime", (FIXTURES / bundled_fixture).read_text(encoding="utf-8"))
    saved = sys.modules.get("voice_flow.bundled_runtime")
    sys.modules["voice_flow.bundled_runtime"] = pins
    try:
        updater = _module_from_source(
            "old_app_updater", (FIXTURES / "v1_0_6_app_updater.py.txt").read_text(encoding="utf-8")
        )
    finally:
        if saved is None:
            sys.modules.pop("voice_flow.bundled_runtime", None)
        else:
            sys.modules["voice_flow.bundled_runtime"] = saved
    updater._pins = pins
    return updater


def _release_assets(platform: str) -> list[dict]:
    if platform == "win":
        full = "AI-Productivity-Flow-Setup-x64.exe"
        app = "AI-Productivity-Flow-app-update-win.zip"
    else:
        full = "AI-Productivity-Flow-macOS.dmg"
        app = "AI-Productivity-Flow-app-update-mac.zip"
    base = "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/v1.0.8/"
    names = [(full, FULL_SIZE), (full + ".sha256", 90), (app, APP_ZIP_SIZE), (app + ".sha256", 90),
             (app.replace(".zip", ".manifest.json"), 4000)]
    return [{"name": n, "browser_download_url": base + n, "size": s} for n, s in names]


def _build_app_update():
    spec = importlib.util.spec_from_file_location("apf_build_app_update", ROOT / "release" / "build_app_update.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v108_manifest(platform: str) -> dict:
    """The real app-update manifest this tree would publish for 1.0.8."""
    return _build_app_update().build_manifest(platform)


def _installed_fingerprint(old, platform: str, tmp_path: Path) -> dict:
    """What the old app reads from its own install manifest."""
    runtime = old._pins.runtime_for_platform(platform)
    if platform == "win":
        manifest = {"product": "AI Productivity Flow", "version": "old", "runtime": runtime,
                    "node": {"version": runtime["node"]}}
    else:
        manifest = {"bundled_runtime": True, "runtime": runtime}
    path = tmp_path / f"{platform}-install-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    old._installed_manifest_candidates = lambda: [path]
    return old.installed_runtime_fingerprint(platform)


def _old_plan(old, platform: str, tmp_path: Path) -> dict:
    installed = _installed_fingerprint(old, platform, tmp_path)
    manifest = _v108_manifest(platform)
    result = old.describe_update(
        _release_assets(platform),
        platform=platform,
        installed_runtime=installed,
        fetch_manifest_fn=lambda _url: manifest,
        can_apply_app=True,
    )
    return result["update_plan"]


def test_fixtures_are_the_shipped_sources():
    """When the tags are present, the fixtures match them byte for byte."""
    pairs = [("v1.0.6", "app_updater.py", "v1_0_6_app_updater.py.txt"),
             ("v1.0.7", "app_updater.py", "v1_0_6_app_updater.py.txt"),
             ("v1.0.6", "bundled_runtime.py", "v1_0_6_bundled_runtime.py.txt"),
             ("v1.0.7", "bundled_runtime.py", "v1_0_7_bundled_runtime.py.txt")]
    checked = 0
    for tag, name, fixture in pairs:
        try:
            shipped = subprocess.run(["git", "show", f"{tag}:src/voice_flow/{name}"], cwd=ROOT,
                                     capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            continue
        assert shipped == (FIXTURES / fixture).read_bytes(), f"{fixture} drifted from {tag}"
        checked += 1
    if not checked:
        pytest.skip("release tags not fetched in this checkout")


def test_v106_windows_install_gets_the_small_zip_for_v108(monkeypatch, tmp_path):
    old = _old_updater(monkeypatch, "v1_0_6_bundled_runtime.py.txt")
    assert old._pins.WINDOWS_NODE == "20.18.1"
    plan = _old_plan(old, "win", tmp_path)
    assert plan["kind"] == "app", plan["reason"]
    assert plan["asset_name"] == "AI-Productivity-Flow-app-update-win.zip"
    assert plan["size_bytes"] == APP_ZIP_SIZE
    # The second check inside the shipped install step also passes.
    manifest = _v108_manifest("win")
    assert old.runtimes_match(_installed_fingerprint(old, "win", tmp_path),
                              old.runtime_fingerprint_from_manifest(manifest))


def test_v106_mac_install_gets_the_small_zip_for_v108(monkeypatch, tmp_path):
    old = _old_updater(monkeypatch, "v1_0_6_bundled_runtime.py.txt")
    plan = _old_plan(old, "mac", tmp_path)
    assert plan["kind"] == "app", plan["reason"]
    assert plan["asset_name"] == "AI-Productivity-Flow-app-update-mac.zip"
    assert _v108_manifest("mac")["runtime"]["node"] == "not-bundled"


def test_v107_windows_install_needs_the_full_installer_once(monkeypatch, tmp_path):
    """v1.0.7 bundles Node 22 and its updater compares every field, node
    included. One manifest cannot equal both 20.18.1 (v1.0.6, most users) and
    22.23.3 (v1.0.7), so v1.0.7 Windows users take the full installer once."""
    old = _old_updater(monkeypatch, "v1_0_7_bundled_runtime.py.txt")
    plan = _old_plan(old, "win", tmp_path)
    assert plan["kind"] == "full"
    assert plan["size_bytes"] == FULL_SIZE


def test_v107_mac_install_gets_the_small_zip(monkeypatch, tmp_path):
    old = _old_updater(monkeypatch, "v1_0_7_bundled_runtime.py.txt")
    assert _old_plan(old, "mac", tmp_path)["kind"] == "app"


def test_v108_manifest_keeps_every_field_for_old_updaters_and_lists_node22():
    from voice_flow import bundled_runtime

    manifest = _v108_manifest("win")
    from voice_flow._version import VERSION
    assert manifest["version"] == VERSION
    assert set(manifest["runtime"]) == set(bundled_runtime.RUNTIME_FIELDS)
    assert manifest["runtime"]["node"] == "20.18.1"
    node = manifest["app_managed"]["node"]
    assert node["version"] == "22.23.3"
    assert node["sha256"] == "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71"


# --- the 1.0.8+ updater ------------------------------------------------------

def _new_plan(installed: dict, remote: dict, platform: str = "win") -> dict:
    from voice_flow import app_updater

    return app_updater.select_update_plan(
        app_updater.simplify_assets(_release_assets(platform)),
        platform=platform,
        installed_runtime=installed,
        remote_runtime=remote,
        can_apply_app=True,
    )


def test_new_updater_treats_node_as_app_managed():
    from voice_flow import bundled_runtime

    installed = bundled_runtime.windows_runtime()
    remote = dict(installed, node="24.0.0")
    plan = _new_plan(installed, remote)
    assert plan["kind"] == "app"
    assert plan["runtime_changes"] == {"core": [], "app_managed": ["node"]}


@pytest.mark.parametrize("field,value", [
    ("python", "3.13.1"),
    ("whisper", "0" * 40),
    ("local_ai_engine", "llama-cpp-python==0.4.0"),
])
def test_new_updater_still_requires_the_full_installer_for_core_changes(field, value):
    from voice_flow import bundled_runtime

    installed = bundled_runtime.windows_runtime()
    plan = _new_plan(installed, dict(installed, **{field: value}))
    assert plan["kind"] == "full"
    assert plan["runtime_changes"]["core"] == [field]
    assert "runtime change" in plan["reason"]


def test_new_updater_v108_to_v108_mac_and_win_are_small():
    from voice_flow import app_updater, bundled_runtime

    for platform in ("win", "mac"):
        installed = bundled_runtime.runtime_for_platform(platform)
        remote = app_updater.runtime_fingerprint_from_manifest(_v108_manifest(platform))
        assert _new_plan(installed, remote, platform)["kind"] == "app"


# --- Node 22 as an app-managed download --------------------------------------

def _node_zip(top: str = "node-v22.23.3-win-x64", *, with_exe: bool = True, evil: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if with_exe:
            archive.writestr(f"{top}/node.exe", b"MZ fake node")
        archive.writestr(f"{top}/LICENSE", b"MIT")
        if evil:
            archive.writestr("../escape.txt", b"nope")
    return buffer.getvalue()


class _Server:
    def __init__(self, body: bytes, status: int = 200):
        payload = body
        code = status
        self.hits = 0
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.hits += 1
                self.send_response(code)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_a):
                return None

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/node.zip"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def node_component(monkeypatch, tmp_path):
    from voice_flow import node_component as module

    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path / "data"))
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    module._set_status(state="unknown", error="", downloaded_bytes=0, total_bytes=None)
    return module


def test_node22_download_verifies_hash_and_installs(node_component, monkeypatch):
    body = _node_zip()
    # Stand in for the real pin, which only the real nodejs.org zip matches.
    monkeypatch.setattr(node_component, "MANAGED_NODE_SHA256", hashlib.sha256(body).hexdigest())
    server = _Server(body)
    seen = []
    try:
        exe = node_component.ensure_managed_node(
            lambda done, total: seen.append((done, total)),
            url=server.url, expected_sha256=hashlib.sha256(body).hexdigest(), force=True,
        )
    finally:
        server.close()
    assert exe is not None and exe.name == "node.exe" and exe.is_file()
    assert exe.parent == node_component.managed_node_dir()
    # The marker records the verified hash; it must equal the pin to count.
    marker = json.loads((exe.parent / "component.json").read_text(encoding="utf-8"))
    assert marker["version"] == "22.23.3"
    assert seen and seen[-1][0] == len(body)
    assert node_component.managed_node_executable() == exe
    # Second call reuses it without the network.
    assert node_component.ensure_managed_node(url="http://127.0.0.1:9/unused", force=True) == exe
    assert not list((node_component.components_root() / "node").glob(".download-*"))


def test_node22_hash_mismatch_is_rejected_with_a_clear_message(node_component):
    server = _Server(_node_zip())
    try:
        with pytest.raises(node_component.NodeComponentError, match="security check"):
            node_component.ensure_managed_node(url=server.url, expected_sha256="0" * 64, force=True)
    finally:
        server.close()
    assert node_component.managed_node_executable() is None
    assert node_component.component_status()["error"]
    assert not list((node_component.components_root() / "node").glob(".download-*"))


def test_node22_network_failure_is_a_clear_message(node_component):
    server = _Server(b"gone", status=404)
    try:
        with pytest.raises(node_component.NodeComponentError, match="internet connection"):
            node_component.ensure_managed_node(url=server.url, force=True)
    finally:
        server.close()
    assert node_component.prefetch_managed_node() is True  # not needed on this OS: never raises


def test_node22_rejects_unsafe_or_incomplete_archives(node_component):
    for body, pattern in ((_node_zip(evil=True), "unsafe"), (_node_zip(with_exe=False), "node.exe")):
        server = _Server(body)
        try:
            with pytest.raises(node_component.NodeComponentError, match=pattern):
                node_component.ensure_managed_node(url=server.url,
                                                   expected_sha256=hashlib.sha256(body).hexdigest(), force=True)
        finally:
            server.close()
        assert node_component.managed_node_executable() is None


def _fake_windows_install(monkeypatch, tmp_path, node_version: str):
    from voice_flow import node_component, runtime_env

    runtime = tmp_path / "install" / "runtime"
    (runtime / "node").mkdir(parents=True)
    (runtime / "node" / "node.exe").write_bytes(b"MZ")
    (runtime / "runtime-manifest.json").write_text(json.dumps({"node": {"version": node_version}}), encoding="utf-8")
    monkeypatch.setattr(node_component, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(runtime_env, "runtime_root", lambda: runtime)
    monkeypatch.setattr(runtime_env, "is_installed", lambda: True)
    monkeypatch.setattr(runtime_env, "node_executable", lambda: runtime / "node" / "node.exe")
    return runtime


def test_bundled_node20_needs_the_managed_node(node_component, monkeypatch, tmp_path):
    runtime = _fake_windows_install(monkeypatch, tmp_path, "20.18.1")
    assert node_component.needs_managed_node() is True
    assert node_component.video_node_executable() == runtime / "node" / "node.exe"  # not downloaded yet
    assert node_component.component_status()["state"] == "missing"


def test_bundled_node22_needs_nothing(node_component, monkeypatch, tmp_path):
    _fake_windows_install(monkeypatch, tmp_path, "22.23.3")
    assert node_component.needs_managed_node() is False
    assert node_component.ensure_managed_node() is None
    assert node_component.component_status()["state"] == "not_needed"


def test_mac_and_dev_never_download(node_component, monkeypatch):
    monkeypatch.setattr(node_component, "sys", types.SimpleNamespace(platform="darwin"))
    assert node_component.needs_managed_node() is False
    assert node_component.ensure_managed_node() is None


def test_render_downloads_node22_first_and_uses_it(node_component, monkeypatch, tmp_path):
    from voice_flow.video_flow_engine import narova_runner as nr

    _fake_windows_install(monkeypatch, tmp_path, "20.18.1")
    managed = tmp_path / "data" / "components" / "node" / "22.23.3" / "node.exe"
    calls = []

    def fake_ensure(progress=None, **_kw):
        calls.append(1)
        progress(5 * 1048576, 34 * 1048576)
        return managed

    monkeypatch.setattr(node_component, "ensure_managed_node", fake_ensure)
    runner = nr.NarovaRunner(vendor_root=tmp_path)
    events = []
    runner._ensure_video_node(events.append)
    assert calls == [1] and runner.node_path == str(managed)
    assert any("Node.js 22" in e["message"] and "5 of 34 MB" in e["message"] for e in events)


def test_render_node_failure_falls_back_cleanly(node_component, monkeypatch, tmp_path):
    from voice_flow.video_flow_engine import narova_runner as nr
    from voice_flow.video_flow_engine.engine import _FALLBACK_RENDER_CODES
    from voice_flow.video_flow_engine.sandbox import EngineError

    _fake_windows_install(monkeypatch, tmp_path, "20.18.1")

    def boom(*_a, **_kw):
        raise node_component.NodeComponentError("Couldn't download Node.js for Video Flow. Check your internet connection and try again.")

    monkeypatch.setattr(node_component, "ensure_managed_node", boom)
    runner = nr.NarovaRunner(vendor_root=tmp_path)
    with pytest.raises(EngineError) as raised:
        runner._ensure_video_node(lambda _e: None)
    # render_failed -> the engine falls back to the portable renderer, no crash.
    assert raised.value.code in _FALLBACK_RENDER_CODES
    assert "internet connection" in str(raised.value)


def test_render_browser_prefetch_fetches_node_before_the_browser(node_component, monkeypatch, tmp_path):
    from voice_flow import runtime_env

    _fake_windows_install(monkeypatch, tmp_path, "20.18.1")
    monkeypatch.setattr(runtime_env, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(runtime_env, "render_browser_cache", lambda: None)
    monkeypatch.setattr(runtime_env, "browser_executable", lambda: None)
    monkeypatch.setattr(runtime_env, "_RENDER_BROWSER_PREFETCH_SCHEDULED", False)
    monkeypatch.delenv("VOICE_FLOW_RENDER_BROWSER_PREFETCH", raising=False)
    order = []
    monkeypatch.setattr(node_component, "prefetch_managed_node", lambda: order.append("node") or True)
    monkeypatch.setattr(runtime_env, "ensure_render_browser", lambda **kw: order.append(("browser", kw)))
    timers = []

    class FakeTimer:
        def __init__(self, delay, fn):
            timers.append(fn)
            self.daemon = False
            self.name = ""

        def start(self):
            return None

    monkeypatch.setattr(runtime_env.threading, "Timer", FakeTimer)
    assert runtime_env.schedule_render_browser_prefetch() is True
    timers[0]()
    assert order == ["node", ("browser", {"background": True})]


def test_ensure_render_browser_uses_node22_for_hyperframes(node_component, monkeypatch, tmp_path):
    from voice_flow import runtime_env

    runtime = _fake_windows_install(monkeypatch, tmp_path, "20.18.1")
    cli = runtime / "hyperframes" / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")
    managed = tmp_path / "node22.exe"
    monkeypatch.setattr(runtime_env, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(runtime_env, "render_browser_cache", lambda: None)
    monkeypatch.setattr(runtime_env, "browser_executable", lambda: None)
    monkeypatch.setattr(node_component, "ensure_managed_node", lambda **kw: managed)
    monkeypatch.setattr(node_component, "managed_node_executable", lambda: managed)
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: ran.append(argv))
    runtime_env.ensure_render_browser(background=True)
    assert ran and ran[0][0] == str(managed)
