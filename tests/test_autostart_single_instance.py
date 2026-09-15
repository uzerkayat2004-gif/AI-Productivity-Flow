"""Regression tests: single boot autostart mechanism + boot-safe single-instance guard.

Covers the "two app instances at Windows startup" bug:
1. The launcher mutex must actually detect ERROR_ALREADY_EXISTS
   (ctypes.windll never synced the ctypes error variable, so the guard was a no-op).
2. A second launcher must POLL for the first launcher's window (boot race:
   the engine spawns a second launcher before the first window exists) and
   exit with 'focused' instead of spawning its own suite.
3. installer must register exactly ONE boot mechanism (HKCU Run key) and
   remove legacy Startup-folder .lnk duplicates on install/upgrade.
"""

from __future__ import annotations

import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from voice_flow import installer
from voice_flow import release_cleanup_autorun
from voice_flow.gui import desktop_launcher

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Windows mutex / autostart behavior",
)


def _unique_mutex_name() -> str:
    return f"Local\\VoiceFlowTestMutex_{uuid.uuid4().hex}"


# =========================================================================
# 1. Launcher mutex (single-instance foundation)
# =========================================================================


def test_acquire_launcher_mutex_detects_already_held_mutex(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: ctypes.windll-based code returned get_last_error()==0, so an
    already-held mutex was never detected and the duplicate guard never ran."""
    name = _unique_mutex_name()
    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_NAME", name)
    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_HANDLE", None)

    kernel32 = desktop_launcher._get_kernel32()
    external_handle = kernel32.CreateMutexW(None, False, name)  # "first launcher"
    assert external_handle
    try:
        assert desktop_launcher._acquire_launcher_mutex() is False
    finally:
        kernel32.CloseHandle(external_handle)


def test_acquire_launcher_mutex_succeeds_then_blocks_second_acquire(monkeypatch: pytest.MonkeyPatch) -> None:
    name = _unique_mutex_name()
    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_NAME", name)
    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_HANDLE", None)

    kernel32 = desktop_launcher._get_kernel32()
    assert desktop_launcher._acquire_launcher_mutex() is True
    try:
        # Second launcher in the same boot window must see the mutex as held.
        assert desktop_launcher._acquire_launcher_mutex() is False
    finally:
        if desktop_launcher._LAUNCHER_MUTEX_HANDLE:
            kernel32.CloseHandle(desktop_launcher._LAUNCHER_MUTEX_HANDLE)


def test_launcher_mutex_held_tracks_other_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    name = _unique_mutex_name()
    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_NAME", name)
    monkeypatch.setattr(desktop_launcher, "_LAUNCHER_MUTEX_HANDLE", None)

    kernel32 = desktop_launcher._get_kernel32()
    external_handle = kernel32.CreateMutexW(None, False, name)
    assert external_handle
    try:
        assert desktop_launcher._launcher_mutex_held() is True
    finally:
        kernel32.CloseHandle(external_handle)

    # Once the holder releases (process exit), the mutex must read free.
    assert desktop_launcher._launcher_mutex_held() is False


# =========================================================================
# 2. Boot-safe duplicate guard polling
# =========================================================================


def test_wait_focuses_window_once_it_appears_after_polls() -> None:
    """The guard must poll (not decide on a single early check) and report
    'focused' when the first launcher's window finally exists."""
    sleeps: list[float] = []
    focus_calls = {"n": 0}

    def fake_focus() -> bool:
        focus_calls["n"] += 1
        return focus_calls["n"] >= 3  # window appears on the 3rd poll

    outcome = desktop_launcher._wait_for_existing_window(
        total_seconds=60.0,
        poll_interval=0.25,
        sleep=sleeps.append,
        clock=lambda: len(sleeps) * 0.25,
        focus=fake_focus,
        mutex_held=lambda: True,
    )

    assert outcome == "focused"
    assert focus_calls["n"] == 3
    assert len(sleeps) == 2  # actually polled with retries


def test_wait_reports_released_when_first_launcher_dies_without_window() -> None:
    sleeps: list[float] = []
    held = iter([True, True, False])

    outcome = desktop_launcher._wait_for_existing_window(
        total_seconds=60.0,
        poll_interval=0.25,
        sleep=sleeps.append,
        clock=lambda: len(sleeps) * 0.25,
        focus=lambda: False,
        mutex_held=lambda: next(held),
    )

    assert outcome == "released"
    assert len(sleeps) == 2


def test_wait_times_out_while_mutex_still_held_and_no_window() -> None:
    """Bounded wait: falls back to a fresh launch instead of hanging forever."""
    sleeps: list[float] = []
    clock = {"t": 0.0}

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    outcome = desktop_launcher._wait_for_existing_window(
        total_seconds=1.0,
        poll_interval=0.25,
        sleep=fake_sleep,
        clock=lambda: clock["t"],
        focus=lambda: False,
        mutex_held=lambda: True,
    )

    assert outcome == "timeout"
    assert len(sleeps) == 4  # 1.0s / 0.25s, then stops


# =========================================================================
# 3. Launcher entry flow: second launcher exits instead of spawning a suite
# =========================================================================


def test_duplicate_launcher_exits_focused_without_spawning_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Boot race: window check misses (too early), mutex held -> after polling,
    the second launcher must exit(0) and must NOT call launch_desktop_gui."""
    monkeypatch.setattr(desktop_launcher, "_launcher_log", lambda _msg: None)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: False)
    monkeypatch.setattr(desktop_launcher, "_acquire_launcher_mutex", lambda: False)
    monkeypatch.setattr(desktop_launcher, "_wait_for_existing_window", lambda: "focused")

    launch = MagicMock()
    monkeypatch.setattr(desktop_launcher, "launch_desktop_gui", launch)

    with pytest.raises(SystemExit) as excinfo:
        desktop_launcher._run_desktop_launcher()

    assert excinfo.value.code == 0
    launch.assert_not_called()


@pytest.mark.parametrize("outcome", ["released", "timeout"])
def test_launcher_starts_fresh_when_mutex_released_or_wait_times_out(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    monkeypatch.setattr(desktop_launcher, "_launcher_log", lambda _msg: None)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: False)
    monkeypatch.setattr(desktop_launcher, "_acquire_launcher_mutex", lambda: False)
    monkeypatch.setattr(desktop_launcher, "_wait_for_existing_window", lambda: outcome)

    launch = MagicMock()
    monkeypatch.setattr(desktop_launcher, "launch_desktop_gui", launch)

    desktop_launcher._run_desktop_launcher()  # must not raise SystemExit

    launch.assert_called_once()


def test_launcher_focuses_existing_window_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_launcher, "_launcher_log", lambda _msg: None)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: True)

    launch = MagicMock()
    monkeypatch.setattr(desktop_launcher, "launch_desktop_gui", launch)

    with pytest.raises(SystemExit):
        desktop_launcher._run_desktop_launcher()

    launch.assert_not_called()


# =========================================================================
# 4. Installer: exactly ONE boot mechanism
# =========================================================================


def test_install_all_registers_exactly_one_boot_mechanism(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vbs = tmp_path / "VoiceFlowLauncher.vbs"
    vbs.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(installer, "get_vbs_launcher_path", lambda: vbs)

    calls = {"reg": 0, "register_startup": 0, "unregister_startup": 0, "shortcuts": 0}
    monkeypatch.setattr(installer, "register_registry_autorun", lambda: calls.__setitem__("reg", calls["reg"] + 1) or True)
    monkeypatch.setattr(
        installer,
        "register_startup_folder",
        lambda: calls.__setitem__("register_startup", calls["register_startup"] + 1) or True,
    )
    monkeypatch.setattr(
        installer,
        "unregister_startup_folder",
        lambda: calls.__setitem__("unregister_startup", calls["unregister_startup"] + 1) or True,
    )
    monkeypatch.setattr(installer, "register_desktop_shortcuts", lambda: calls.__setitem__("shortcuts", 1) or True)

    assert installer.install_all() is True

    assert calls["reg"] == 1
    assert calls["unregister_startup"] == 1
    # Regression: the legacy 'dual-layer' install created a second boot
    # mechanism (Startup .lnk) which opened two instances at logon.
    assert calls["register_startup"] == 0


def test_ensure_single_autostart_mechanism_registers_run_key_and_removes_lnk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(installer, "register_registry_autorun", lambda: calls.append("reg") or True)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: calls.append("unreg_lnk") or True)

    assert installer.ensure_single_autostart_mechanism() is True
    assert calls == ["reg", "unreg_lnk"]


def test_ensure_single_autostart_mechanism_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "register_registry_autorun", lambda: False)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: True)
    assert installer.ensure_single_autostart_mechanism() is False


def test_set_autostart_true_never_registers_startup_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "register_registry_autorun", lambda: True)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: True)

    def _must_not_register() -> bool:
        raise AssertionError("register_startup_folder must never create a second boot mechanism")

    monkeypatch.setattr(installer, "register_startup_folder", _must_not_register)
    assert installer.set_autostart(True) is True


# =========================================================================
# 5. Launcher first-launch autostart normalization
# =========================================================================


def test_first_launch_normalizes_autostart_to_single_mechanism(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no stored preference exists, the launcher must call
    set_autostart(True) unconditionally so a legacy Startup-folder-only
    install gets normalized to the Run key (removing the duplicate)."""

    class FakeStorage:
        def __init__(self) -> None:
            self.saved: list[tuple[str, object]] = []

        def get_setting(self, _key, default=None):
            return default

        def save_setting(self, key, value):
            self.saved.append((key, value))

    fake_storage = FakeStorage()
    monkeypatch.setattr("voice_flow.storage.storage", fake_storage)

    autostart_calls: list[bool] = []
    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda enable=True: autostart_calls.append(enable))
    monkeypatch.setattr(desktop_launcher, "ensure_backend_running", lambda: None)
    monkeypatch.setattr(desktop_launcher, "is_api_server_ready", lambda timeout=0.2: True)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", lambda: False)
    monkeypatch.setattr(desktop_launcher, "_poke_overlay_show", lambda: None)

    mock_webview = MagicMock()
    mock_webview.create_window.return_value = MagicMock()
    monkeypatch.setattr(desktop_launcher, "webview", mock_webview)

    desktop_launcher.launch_desktop_gui()

    assert autostart_calls == [True]
    assert ("autostart_enabled", True) in fake_storage.saved


# =========================================================================
# 6. Uninstall/upgrade cleanup helper
# =========================================================================


def test_release_cleanup_removes_all_legacy_autostart_entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    deleted: list[str] = []

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_delete_value(key, name):
        if name == "Voice Flow":  # never registered on this machine
            raise FileNotFoundError(name)
        deleted.append(name)

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_SET_VALUE=0x20000,
        OpenKey=lambda *a, **k: FakeKey(),
        DeleteValue=fake_delete_value,
    )
    monkeypatch.setattr(release_cleanup_autorun, "winreg", fake_winreg)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    startup_dir = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True)
    (startup_dir / "AI Productivity Flow.lnk").write_bytes(b"lnk")
    (startup_dir / "VoiceFlow.lnk").write_bytes(b"lnk")
    (startup_dir / "unrelated.lnk").write_bytes(b"lnk")

    release_cleanup_autorun.main()

    assert sorted(deleted) == ["AI Productivity Flow", "VoiceFlow"]
    assert not (startup_dir / "AI Productivity Flow.lnk").exists()
    assert not (startup_dir / "VoiceFlow.lnk").exists()
    assert (startup_dir / "unrelated.lnk").exists()  # untouched


def test_release_cleanup_tolerates_missing_registry_and_startup_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_open_key(*args, **kwargs):
        raise FileNotFoundError()

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(), KEY_SET_VALUE=0x20000, OpenKey=fake_open_key, DeleteValue=lambda *a: None
    )
    monkeypatch.setattr(release_cleanup_autorun, "winreg", fake_winreg)
    monkeypatch.setenv("APPDATA", str(tmp_path))  # Startup dir does not exist

    release_cleanup_autorun.main()  # must not raise
