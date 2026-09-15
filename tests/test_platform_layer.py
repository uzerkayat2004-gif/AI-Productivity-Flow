"""Platform abstraction layer contract tests.

These run on **every** OS. That is the point: the same assertions execute on the
Windows runner and the macOS runner, so a backend that silently stops honouring
the contract fails CI on the platform it broke.

Three things are verified:

1. Importing ``voice_flow.platform`` (and both backends) is safe anywhere and
   has no OS side effects.
2. The active backend structurally satisfies ``PlatformBackend``.
3. Every contract method degrades instead of raising — including when called on
   the *wrong* OS, which is what makes the macOS backend testable from Windows.
"""

from __future__ import annotations

import sys

import pytest

from voice_flow.platform import (
    IS_MACOS,
    IS_WINDOWS,
    NullBackend,
    get_backend,
    reset_backend,
    set_backend,
)
from voice_flow.platform.base import (
    PermissionReport,
    PermissionState,
    PlatformBackend,
)

# Methods every backend must expose, with arguments safe to call anywhere.
CONTRACT_CALLS = {
    "copy_to_clipboard": ("probe",),
    "read_clipboard": (),
    "send_paste": (),
    "send_copy": (),
    "send_enter": (),
    "active_window_title": (),
    "active_app_name": (),
    "is_own_window_focused": (),
    "get_selected_text": (),
    "beep": (),
    "get_launch_at_login": (),
    "permission_report": (),
    "open_permission_settings": ("nonexistent-key",),
    "system_tts_voices": (),
}


def _all_backends():
    """Instantiate every backend, regardless of host OS."""
    from voice_flow.platform.macos import MacOSBackend
    from voice_flow.platform.windows import WindowsBackend

    return [WindowsBackend(), MacOSBackend(), NullBackend("test")]


# ---------------------------------------------------------------------------
# import safety
# ---------------------------------------------------------------------------


def test_stdlib_platform_is_not_shadowed():
    """``voice_flow.platform`` must not break ``import platform``."""
    import platform as stdlib_platform

    assert hasattr(stdlib_platform, "system")
    assert isinstance(stdlib_platform.system(), str)
    assert "voice_flow" not in getattr(stdlib_platform, "__file__", "")


def test_both_backends_import_on_any_os():
    """Cross-platform import is what lets Windows CI check the macOS code."""
    from voice_flow.platform.macos import MacOSBackend
    from voice_flow.platform.windows import WindowsBackend

    assert MacOSBackend is not None
    assert WindowsBackend is not None


def test_macos_native_imports_and_is_inert_off_platform():
    from voice_flow.platform import macos_native

    assert isinstance(macos_native.available(), bool)
    if not IS_MACOS:
        assert macos_native.available() is False
        assert macos_native.send_key_combo(macos_native.KEY_V) is False
        assert macos_native.frontmost_window_owner() == {}
        assert macos_native.focused_selected_text() == ""


def test_wincompat_stubs_are_inert_off_platform():
    from voice_flow.platform.wincompat import IS_WINDOWS as W
    from voice_flow.platform.wincompat import Win32Unavailable, windll, wintypes

    assert hasattr(wintypes, "DWORD")
    if not W:
        # Calling a stubbed Win32 symbol must fail loudly, not silently pass.
        with pytest.raises(Win32Unavailable):
            windll.user32.GetForegroundWindow()


# ---------------------------------------------------------------------------
# backend selection
# ---------------------------------------------------------------------------


def test_get_backend_matches_host_os():
    backend = get_backend()
    if IS_WINDOWS:
        assert backend.name == "windows"
    elif IS_MACOS:
        assert backend.name == "macos"
    else:
        assert backend.name == "null"


def test_get_backend_is_cached_singleton():
    assert get_backend() is get_backend()


def test_set_and_reset_backend_roundtrip():
    original = get_backend()
    sentinel = NullBackend("sentinel")
    try:
        set_backend(sentinel)
        assert get_backend() is sentinel
    finally:
        reset_backend()
    rebuilt = get_backend()
    assert rebuilt is not sentinel
    assert rebuilt.name == original.name


# ---------------------------------------------------------------------------
# contract conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend", _all_backends(), ids=lambda b: b.name)
def test_backend_satisfies_protocol(backend):
    assert isinstance(backend, PlatformBackend)
    assert isinstance(backend.name, str) and backend.name


@pytest.mark.parametrize("backend", _all_backends(), ids=lambda b: b.name)
def test_contract_methods_never_raise(backend):
    """A backend on the wrong OS must degrade, never explode."""
    for method_name, args in CONTRACT_CALLS.items():
        method = getattr(backend, method_name, None)
        assert callable(method), f"{backend.name} is missing {method_name}"
        if backend.name != sys.platform and backend.name not in ("null",):
            # Off-platform: must be inert.
            try:
                method(*args)
            except Exception as exc:  # pragma: no cover - failure path
                pytest.fail(f"{backend.name}.{method_name} raised off-platform: {exc!r}")


@pytest.mark.parametrize("backend", _all_backends(), ids=lambda b: b.name)
def test_return_types_match_contract(backend):
    assert isinstance(backend.read_clipboard(), str)
    assert isinstance(backend.active_window_title(), str)
    assert isinstance(backend.active_app_name(), str)
    assert isinstance(backend.get_selected_text(), str)
    assert isinstance(backend.is_own_window_focused(), bool)
    assert isinstance(backend.get_launch_at_login(), bool)
    assert isinstance(backend.system_tts_voices(), list)
    assert isinstance(backend.open_permission_settings("bogus"), bool)


@pytest.mark.parametrize("backend", _all_backends(), ids=lambda b: b.name)
def test_permission_report_shape(backend):
    report = backend.permission_report()
    assert isinstance(report, PermissionReport)
    assert isinstance(report.platform, str)

    payload = report.to_dict()
    assert set(payload) == {"platform", "allRequiredGranted", "permissions"}
    assert isinstance(payload["allRequiredGranted"], bool)

    for state, entry in zip(report.states, payload["permissions"]):
        assert isinstance(state, PermissionState)
        assert state.key and isinstance(state.key, str)
        assert state.label and isinstance(state.label, str)
        assert isinstance(state.granted, bool)
        assert isinstance(state.required, bool)
        assert set(entry) == {
            "key",
            "label",
            "granted",
            "required",
            "description",
            "settingsUrl",
            "indeterminate",
        }


def test_open_permission_settings_rejects_unknown_key():
    for backend in _all_backends():
        assert backend.open_permission_settings("definitely-not-a-permission") is False


# ---------------------------------------------------------------------------
# macOS specifics (assertions hold from any OS)
# ---------------------------------------------------------------------------


def test_macos_declares_the_three_required_permissions():
    """Microphone, Accessibility and Input Monitoring are all mandatory."""
    from voice_flow.platform.macos import MacOSBackend

    report = MacOSBackend().permission_report()
    keys = {s.key for s in report.states}
    assert keys == {"microphone", "accessibility", "input_monitoring"}
    assert all(s.required for s in report.states)
    assert all(s.settings_url.startswith("x-apple") for s in report.states)


def test_macos_permission_settings_urls_are_distinct():
    from voice_flow.platform.macos import MacOSBackend

    urls = [s.settings_url for s in MacOSBackend().permission_report().states]
    assert len(set(urls)) == len(urls)


def test_null_backend_reports_no_permissions():
    report = NullBackend("test").permission_report()
    assert report.states == ()
    assert report.all_required_granted is True
    assert report.missing_required == ()


# ---------------------------------------------------------------------------
# host-specific live checks
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows only")
def test_windows_clipboard_roundtrip_preserves_user_clipboard():
    backend = get_backend()
    saved = backend.read_clipboard()
    try:
        probe = "voice-flow-contract-probe"
        assert backend.copy_to_clipboard(probe) is True
        assert backend.read_clipboard() == probe
    finally:
        backend.copy_to_clipboard(saved)


# ---------------------------------------------------------------------------
# API Server Permissions Integration Tests
# ---------------------------------------------------------------------------


def test_api_server_permissions_endpoint_structure():
    from voice_flow.platform import get_backend
    backend = get_backend()
    report = backend.permission_report()
    payload = {"success": True, **report.to_dict()}
    assert payload["success"] is True
    assert "platform" in payload
    assert "allRequiredGranted" in payload
    assert isinstance(payload["permissions"], list)


def test_build_macos_app_script_runs():
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "scripts" / "build_macos_app.py"
    assert script.is_file()

    res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert res.returncode == 0, f"build_macos_app.py failed: {res.stderr}"

    dist_dir = Path(__file__).resolve().parent.parent / "dist"
    app_bundle = dist_dir / "Voice Flow.app"
    zip_bundle = dist_dir / "VoiceFlow-macOS-unsigned.zip"

    assert app_bundle.is_dir()
    assert (app_bundle / "Contents" / "Info.plist").is_file()
    assert (app_bundle / "Contents" / "MacOS" / "voice-flow-launcher").is_file()
    assert zip_bundle.is_file()
    assert zip_bundle.stat().st_size > 1000
    assert (app_bundle / "Contents" / "Resources" / "AppIcon.icns").is_file()


def test_native_settings_cross_platform():
    from voice_flow.native_settings import get_launch_at_login, set_launch_at_login

    res_get = get_launch_at_login()
    assert hasattr(res_get, "applied")
    assert isinstance(res_get.applied, bool)

    res_set_invalid = set_launch_at_login("not-a-bool")  # type: ignore
    assert res_set_invalid.applied is False
    assert "boolean" in (res_set_invalid.error or "")


def test_injector_cross_platform_safe_imports():
    from voice_flow import injector

    assert hasattr(injector, "inject_text")
    assert hasattr(injector, "ClipboardInjector")
    assert hasattr(injector, "_safe_copy_to_clipboard")
    assert hasattr(injector, "_safe_paste_from_clipboard")
    assert hasattr(injector, "get_active_window_title")
    assert hasattr(injector, "get_window_class_name")
    assert hasattr(injector, "focus_target_window")
    assert hasattr(injector, "is_same_window_hierarchy")


def test_api_server_permissions_http_endpoints():
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from voice_flow.gui.api_server import VoiceFlowApiHandler

    server = ThreadingHTTPServer(("127.0.0.1", 0), VoiceFlowApiHandler)
    server.daemon_threads = True
    server.block_on_close = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/platform/permissions",
            headers={"Connection": "close"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.load(resp)
        assert data["success"] is True
        assert "platform" in data
        assert "allRequiredGranted" in data
        assert isinstance(data["permissions"], list)

        post_data = json.dumps({"key": "invalid-perm"}).encode("utf-8")
        post_req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/platform/permissions/open",
            data=post_data,
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(post_req, timeout=3) as resp:
            post_res = json.load(resp)
        assert post_res == {"success": False}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_macos_backend_methods_off_platform_resilience():
    from voice_flow.platform.macos import MacOSBackend

    mac_backend = MacOSBackend()
    assert mac_backend.beep("start") in (True, False)
    assert mac_backend.beep("stop") in (True, False)
    assert mac_backend.beep("error") in (True, False)
    assert mac_backend.beep("unknown_kind") in (True, False)
    assert isinstance(mac_backend.system_tts_voices(), list)
    assert mac_backend.system_tts_to_file("text", "nonexistent/out.wav") is False
    assert mac_backend.request_permission("microphone") in (True, False)
    assert mac_backend.request_permission("accessibility") in (True, False)
    assert mac_backend.request_permission("input_monitoring") in (True, False)
    assert mac_backend.request_permission("unknown_key") is False
    assert isinstance(mac_backend.get_launch_at_login(), bool)
    assert mac_backend.set_launch_at_login(False) in (True, False)


def test_wincompat_monkeypatches_ctypes():
    import ctypes
    from voice_flow.platform import wincompat

    assert hasattr(ctypes, "windll")
    assert hasattr(ctypes, "wintypes")


