"""In-app updater: asset choice, checksums, download progress, and install command."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.test_api_server import _get, test_server
from voice_flow.app_updater import (
    APP_UPDATE_NAMES,
    MAC_DISK_IMAGE_NAME,
    MANUAL_FINDER_INSTRUCTIONS,
    WINDOWS_INSTALLER_FLAGS,
    WINDOWS_INSTALLER_NAME,
    UpdateError,
    UpdateManager,
    apply_staged_package,
    assert_public_release_url,
    build_windows_installer_command,
    download_file,
    extract_app_zip,
    format_bytes,
    mac_attach_argv,
    mac_quarantine_argv,
    mac_relaunch_argv,
    parse_sha256_text,
    restore_package,
    run_pending_update,
    runtime_fingerprint_from_manifest,
    runtimes_match,
    select_update_plan,
    verify_sha256,
)
from voice_flow.bundled_runtime import RUNTIME_FIELDS, mac_runtime, windows_runtime

ROOT = Path(__file__).resolve().parents[1]


def _asset(name: str, size: int) -> dict:
    return {
        "name": name,
        "browser_download_url": (
            "https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/download/v9.9.9/"
            + name
        ),
        "size": size,
    }


def _release_assets(platform: str, *, app_size: int = 8_000_000, full_size: int = 560_000_000) -> list[dict]:
    if platform == "win":
        full_name = WINDOWS_INSTALLER_NAME
        extra: list[dict] = []
    else:
        full_name = MAC_DISK_IMAGE_NAME
        extra = [_asset("AI-Productivity-Flow-macOS.zip", full_size), _asset("AI-Productivity-Flow-macOS.zip.sha256", 80)]
    app_name = APP_UPDATE_NAMES[platform]
    return [
        _asset(full_name, full_size),
        _asset(full_name + ".sha256", 90),
        _asset(app_name, app_size),
        _asset(app_name + ".sha256", 90),
        _asset(app_name + ".manifest.json", 400),
        *extra,
    ]


def test_asset_selection_uses_the_small_package_when_the_runtime_matches():
    for platform, runtime in (("win", windows_runtime()), ("mac", mac_runtime())):
        plan = select_update_plan(
            _release_assets(platform),
            platform=platform,
            installed_runtime=runtime,
            remote_runtime=dict(runtime),
            can_apply_app=True,
        )
        assert plan["kind"] == "app"
        assert plan["asset_name"] == APP_UPDATE_NAMES[platform]
        assert plan["size_bytes"] == 8_000_000
        assert plan["size_label"] == format_bytes(8_000_000)
        assert plan["runtime_changed"] is False
        assert "/releases/download/" in plan["download_url"]
        assert plan["download_url"].endswith(APP_UPDATE_NAMES[platform])
        assert plan["sha256_url"].endswith(APP_UPDATE_NAMES[platform] + ".sha256")


def test_asset_selection_uses_the_full_installer_when_the_runtime_changed():
    windows = select_update_plan(
        _release_assets("win"),
        platform="win",
        installed_runtime=windows_runtime(),
        remote_runtime={**windows_runtime(), "python": "9.9.9"},
        can_apply_app=True,
    )
    assert windows["kind"] == "full"
    assert windows["asset_name"] == WINDOWS_INSTALLER_NAME
    assert windows["size_bytes"] == 560_000_000
    assert windows["install_label"] == "Restart to install"
    assert "runtime" in windows["reason"].lower()

    mac = select_update_plan(
        _release_assets("mac"),
        platform="mac",
        installed_runtime=mac_runtime(),
        remote_runtime={**mac_runtime(), "local_ai_engine": "llama.cpp newer"},
        can_apply_app=True,
    )
    assert mac["kind"] == "full"
    assert mac["asset_name"] == MAC_DISK_IMAGE_NAME
    assert mac["size_bytes"] == 560_000_000


def test_missing_manifest_or_unwritable_install_falls_back_to_the_full_file():
    assets = _release_assets("mac")
    missing = select_update_plan(
        assets, platform="mac", installed_runtime=mac_runtime(), remote_runtime=None, can_apply_app=True,
    )
    assert missing["kind"] == "full"
    assert missing["asset_name"] == MAC_DISK_IMAGE_NAME

    blocked = select_update_plan(
        assets,
        platform="mac",
        installed_runtime=mac_runtime(),
        remote_runtime=mac_runtime(),
        can_apply_app=False,
    )
    assert blocked["kind"] == "full"
    assert blocked["asset_name"] == MAC_DISK_IMAGE_NAME


def test_mac_full_update_uses_the_zip_only_when_the_dmg_is_absent():
    assets = [item for item in _release_assets("mac") if not item["name"].startswith(MAC_DISK_IMAGE_NAME)]
    plan = select_update_plan(
        assets, platform="mac", installed_runtime=mac_runtime(), remote_runtime=None, can_apply_app=True,
    )
    assert plan["asset_name"] == "AI-Productivity-Flow-macOS.zip"


def test_checksum_mismatch_deletes_the_file(tmp_path):
    payload = tmp_path / "update.bin"
    payload.write_bytes(b"not-the-real-update")
    with pytest.raises(UpdateError, match="checksum"):
        verify_sha256(payload, "ab" * 32 + "  update.bin\n")
    assert not payload.exists()


def test_checksum_text_accepts_the_formats_the_release_writes():
    digest = "a" * 64
    assert parse_sha256_text(f"{digest}  AI-Productivity-Flow-Setup-x64.exe\n") == digest
    assert parse_sha256_text(digest) == digest
    assert parse_sha256_text(f"SHA256 (file) = {digest.upper()}") == digest
    with pytest.raises(UpdateError):
        parse_sha256_text("no digest here")


def test_windows_installer_command_is_silent_and_relaunches_via_the_script(tmp_path):
    installer = tmp_path / WINDOWS_INSTALLER_NAME
    command = build_windows_installer_command(installer)
    assert command[0] == str(installer)
    assert command[1:] == list(WINDOWS_INSTALLER_FLAGS)
    assert command[1:] == ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]

    iss = (ROOT / "release" / "installer" / "apf-setup.iss").read_text(encoding="utf-8")
    assert "function IsSilentSetup" in iss
    assert "Result := WizardSilent" in iss
    assert "Check: IsSilentSetup" in iss
    assert "PrivilegesRequired=lowest" in iss
    assert "nowait postinstall skipifsilent" in iss
    files = iss.split("[Files]", 1)[1].split("[", 1)[0]
    uninstall = iss.split("[UninstallDelete]", 1)[1].split("[", 1)[0]
    assert ".voice_flow" not in files
    assert ".voice_flow" not in uninstall


def test_direct_fallback_refuses_the_repository_page():
    asset = _asset(WINDOWS_INSTALLER_NAME, 10)["browser_download_url"]
    assert_public_release_url(asset)
    with pytest.raises(UpdateError):
        assert_public_release_url("https://github.com/uzerkayat2004-gif/AI-Productivity-Flow")
    with pytest.raises(UpdateError):
        assert_public_release_url("https://github.com/uzerkayat2004-gif/AI-Productivity-Flow/releases/latest")


def test_swap_refuses_the_user_data_folder(tmp_path):
    data = tmp_path / ".voice_flow" / "voice_flow"
    data.mkdir(parents=True)
    (data / "main.py").write_text("cookies")
    staging = tmp_path / "staging" / "voice_flow"
    staging.mkdir(parents=True)
    (staging / "main.py").write_text("new")
    with pytest.raises(UpdateError, match="user data"):
        apply_staged_package(staging, data, tmp_path / "voice_flow.bak")
    assert (data / "main.py").read_text() == "cookies"


def test_failed_launch_restores_the_previous_package(tmp_path):
    target = tmp_path / "voice_flow"
    target.mkdir()
    (target / "main.py").write_text("old")
    staging = tmp_path / "staged" / "voice_flow"
    staging.mkdir(parents=True)
    (staging / "main.py").write_text("new")
    backup = tmp_path / "voice_flow.bak"
    launched: list[list[str]] = []

    class Dead:
        def poll(self):
            return 1

        def terminate(self):
            return None

    outcome = run_pending_update(
        {
            "kind": "app",
            "staging": str(staging),
            "target": str(target),
            "backup": str(backup),
            "success_marker": str(tmp_path / "update-ok"),
            "relaunch": ["relaunch-app"],
            "wait_pid": 0,
            "pending_path": str(tmp_path / "pending.json"),
        },
        wait_for_exit=lambda pid: None,
        launch=lambda command: launched.append(command) or Dead(),
        wait_for_marker=lambda path: False,
    )
    assert outcome == "rolled-back"
    assert (target / "main.py").read_text() == "old"
    assert not backup.exists()
    assert launched == [["relaunch-app"], ["relaunch-app"]]


def test_successful_launch_keeps_the_new_package(tmp_path):
    target = tmp_path / "voice_flow"
    target.mkdir()
    (target / "main.py").write_text("old")
    staging = tmp_path / "staged" / "voice_flow"
    staging.mkdir(parents=True)
    (staging / "main.py").write_text("new")
    outcome = run_pending_update(
        {
            "kind": "app",
            "staging": str(staging),
            "target": str(target),
            "backup": str(tmp_path / "voice_flow.bak"),
            "success_marker": str(tmp_path / "update-ok"),
            "relaunch": ["relaunch-app"],
            "wait_pid": 0,
            "pending_path": str(tmp_path / "pending.json"),
        },
        wait_for_exit=lambda pid: None,
        launch=lambda command: None,
        wait_for_marker=lambda path: True,
    )
    assert outcome == "ok"
    assert (target / "main.py").read_text() == "new"
    assert not (tmp_path / "voice_flow.bak").exists()


def test_helper_runs_the_silent_installer_command(tmp_path):
    installer = tmp_path / WINDOWS_INSTALLER_NAME
    installer.write_bytes(b"MZ")
    command = build_windows_installer_command(installer)
    seen: list[list[str]] = []
    outcome = run_pending_update(
        {"kind": "installer", "command": command, "wait_pid": 0},
        wait_for_exit=lambda pid: None,
        launch=lambda argv: seen.append(argv),
        wait_for_marker=lambda path: False,
    )
    assert outcome == "ok"
    assert seen == [command]


def test_mac_replace_commands_mount_copy_and_clear_quarantine(tmp_path):
    image = tmp_path / "AI-Productivity-Flow-macOS.dmg"
    bundle = tmp_path / "AI Productivity Flow.app"
    mount = tmp_path / "mount"
    assert mac_attach_argv(image, mount)[:4] == ["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly"]
    assert str(image) in mac_attach_argv(image, mount)
    assert mac_quarantine_argv(bundle) == ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(bundle)]
    assert mac_relaunch_argv(bundle) == ["/usr/bin/open", str(bundle)]
    assert "Finder" in MANUAL_FINDER_INSTRUCTIONS


class _FileServer(BaseHTTPRequestHandler):
    body = b""
    ignore_range = False
    redirects = False
    delay = 0.0

    def do_GET(self):  # noqa: N802
        if self.delay:
            import time
            time.sleep(self.delay)
        if self.redirects and self.path.startswith("/start"):
            self.send_response(302)
            self.send_header("Location", "/file")
            self.end_headers()
            return
        data = type(self).body
        start = 0
        status = 200
        requested = self.headers.get("Range")
        if requested and not type(self).ignore_range:
            start = int(requested.split("=", 1)[1].split("-", 1)[0] or "0")
            status = 206
        chunk = data[start:]
        self.send_response(status)
        self.send_header("Content-Length", str(len(chunk)))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        self.end_headers()
        try:
            self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt, *args):
        return


def _serve(body: bytes, *, ignore_range: bool = False, redirects: bool = False, delay: float = 0.0):
    handler = type(
        "Handler",
        (_FileServer,),
        {"body": body, "ignore_range": ignore_range, "redirects": redirects, "delay": delay},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_download_reports_progress_follows_redirects_and_resumes(tmp_path):
    body = b"0123456789abcdef" * 8000
    server = _serve(body, redirects=True)
    port = server.server_address[1]
    try:
        progress: list[tuple[int, int | None]] = []
        dest = tmp_path / "update.bin"
        download_file(
            f"http://127.0.0.1:{port}/start",
            dest,
            progress=lambda done, total: progress.append((done, total)),
        )
        assert dest.read_bytes() == body
        assert progress[-1][0] == len(body)
        assert progress[-1][1] == len(body)
        assert any(0 < done < len(body) for done, _total in progress)

        resumed = tmp_path / "resumed.bin"
        partial = resumed.with_name(resumed.name + ".partial")
        partial.write_bytes(body[:1000])
        resume_progress: list[int] = []
        download_file(
            f"http://127.0.0.1:{port}/file",
            resumed,
            progress=lambda done, total: resume_progress.append(done),
        )
        assert resumed.read_bytes() == body
        assert resume_progress[0] == 1000
    finally:
        server.shutdown()
        server.server_close()


def test_download_restarts_when_the_server_ignores_range(tmp_path):
    body = b"full-body-contents"
    server = _serve(body, ignore_range=True)
    port = server.server_address[1]
    try:
        dest = tmp_path / "update.bin"
        partial = dest.with_name(dest.name + ".partial")
        partial.write_bytes(b"stale-partial")
        download_file(f"http://127.0.0.1:{port}/file", dest)
        assert dest.read_bytes() == body
    finally:
        server.shutdown()
        server.server_close()


def test_download_reports_no_internet_and_timeouts(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise urllib.error.URLError(OSError("Network is unreachable"))

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    with pytest.raises(UpdateError, match="No internet connection"):
        download_file("http://127.0.0.1/file", tmp_path / "update.bin", timeout=0.2)

    monkeypatch.undo()
    server = _serve(b"slow", delay=2.0)
    port = server.server_address[1]
    try:
        with pytest.raises(UpdateError, match="timed out"):
            download_file(f"http://127.0.0.1:{port}/file", tmp_path / "slow.bin", timeout=0.2)
    finally:
        server.shutdown()
        server.server_close()


def test_download_progress_api_reports_percent_and_megabytes(test_server, monkeypatch):
    manager = UpdateManager()
    manager.state = "downloading"
    manager.downloaded = 5 * 1024 * 1024
    manager.total = 10 * 1024 * 1024
    manager.plan = {
        "kind": "app",
        "install_label": "Restart to update",
        "size_label": "8.0 MB",
        "asset_name": APP_UPDATE_NAMES["win"],
        "fallback_url": "",
    }
    monkeypatch.setattr("voice_flow.app_updater._manager", manager)
    code, _headers, body = _get(test_server["base_url"] + "/api/updates/progress")
    assert code == 200
    assert body["success"] is True
    assert body["state"] == "downloading"
    assert body["progress"] == 50.0
    assert body["downloaded_bytes"] == 5 * 1024 * 1024
    assert body["total_bytes"] == 10 * 1024 * 1024
    assert body["downloaded_mb"] == 5.0
    assert body["total_mb"] == 10.0
    assert body["label"] == "50% · 5.0 MB of 10.0 MB"
    assert body["can_cancel"] is True
    assert body["install_label"] == "Restart to update"


def test_app_update_package_contains_the_app_and_runtime_manifest(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_app_update", ROOT / "release" / "build_app_update.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    built = module.build_app_update("win", tmp_path)
    archive_path = built["zip"]
    checksum = built["sha256"].read_text(encoding="utf-8")
    verify_sha256(archive_path, checksum)
    assert archive_path.stat().st_size < 120 * 1024 * 1024
    staged, manifest = extract_app_zip(archive_path, tmp_path / "extracted")
    assert (staged / "gui" / "index.html").is_file()
    assert (staged / "gui" / "app.js").is_file()
    assert list((staged / "gui" / "assets" / "onboarding").glob("*"))
    names = []
    import zipfile
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    assert "manifest.json" in names
    assert not any(name.endswith("python.exe") or "ffmpeg" in name for name in names)
    assert runtimes_match(windows_runtime(), runtime_fingerprint_from_manifest(manifest))
    standalone = json.loads(built["manifest"].read_text(encoding="utf-8"))
    assert built["manifest"].name == "AI-Productivity-Flow-app-update-win.manifest.json"
    assert built["sha256"].name == "AI-Productivity-Flow-app-update-win.zip.sha256"
    assert standalone["runtime"] == manifest["runtime"]
    assert set(standalone["runtime"]) == set(RUNTIME_FIELDS)


def test_runtime_pins_match_the_packaging_scripts():
    from voice_flow.bundled_runtime import (
        MAC_LLAMA_CPP,
        MAC_NEMO_SPEECH,
        MAC_PYTHON,
        NAROVA_VERSION,
        WINDOWS_FFMPEG,
        WINDOWS_HYPERFRAMES,
        WINDOWS_LOCAL_AI,
        WINDOWS_NODE,
        WINDOWS_PYTHON,
        WINDOWS_WHISPER,
    )

    staging = (ROOT / "release" / "assemble_windows_staging.py").read_text(encoding="utf-8")
    mac = (ROOT / "scripts" / "build_macos_app.py").read_text(encoding="utf-8")
    assert f'PYTHON_VERSION = "{WINDOWS_PYTHON}"' in staging
    assert f'NODE_VERSION = "{WINDOWS_NODE}"' in staging
    assert f'HYPERFRAMES_VERSION = "{WINDOWS_HYPERFRAMES}"' in staging
    assert f'FFMPEG_VERSION = "{WINDOWS_FFMPEG}"' in staging
    assert f'WHISPER_REVISION = "{WINDOWS_WHISPER}"' in staging
    assert f'LLAMA_CPP_PACKAGE = "{WINDOWS_LOCAL_AI}"' in staging
    assert f'python_version": "{MAC_PYTHON}"' in mac
    assert f'LLAMA_CPP_BUILD = "{MAC_LLAMA_CPP}"' in mac
    assert f'NEMO_SPEECH_VERSION = "{MAC_NEMO_SPEECH}"' in mac
    listed = json.loads((ROOT / "third_party" / "narova" / "package.json").read_text(encoding="utf-8"))
    assert listed["version"] == NAROVA_VERSION


def test_about_page_offers_update_now_instead_of_the_github_download():
    script = (ROOT / "src" / "voice_flow" / "gui" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")
    assert "Update now" in script
    assert "Download update" not in script
    assert "/api/updates/download" in script
    assert "/api/updates/progress" in script
    assert "/api/updates/fallback" in script
    assert "Version 1.0" in html
    assert "build 1.0.7" in html
    assert "Version 1.0.7" not in html
    assert "Crash reports help fix bugs (you can turn this off in Privacy)" in html


def test_restore_package_puts_the_backup_back(tmp_path):
    target = tmp_path / "voice_flow"
    target.mkdir()
    (target / "main.py").write_text("broken")
    backup = tmp_path / "voice_flow.bak"
    backup.mkdir()
    (backup / "main.py").write_text("old")
    restore_package(target, backup)
    assert (target / "main.py").read_text() == "old"
    assert not backup.exists()
