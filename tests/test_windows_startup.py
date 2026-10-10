"""Offline regressions for the current-user Windows logon task."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import types

import pytest

from voice_flow import installer, windows_startup
from voice_flow import native_settings


@pytest.fixture(autouse=True)
def _block_live_startup_mutations(monkeypatch: pytest.MonkeyPatch):
    """A missed mock must fail before touching Task Scheduler or HKCU."""
    def blocked(*_args, **_kwargs):
        raise AssertionError("test attempted an unmocked startup mutation")

    monkeypatch.setattr(installer, "register_registry_autorun", blocked)
    monkeypatch.setattr(installer, "unregister_registry_autorun", blocked)
    monkeypatch.setattr(installer, "unregister_startup_folder", blocked)


def _action() -> windows_startup.StartupAction:
    return windows_startup.StartupAction(
        executable=r'C:\Program Files\Voice Flow\pythonw.exe',
        arguments=r'-m voice_flow.watchdog --label "quoted value"',
        working_directory=r'C:\Users\A User\Voice Flow Data',
    )


def _status(*, exists=False, enabled=False, matches=False, available=True):
    return windows_startup.TaskStatus(
        available=available,
        exists=exists,
        enabled=enabled,
        matches=matches,
        task_name="AI Productivity Flow-S-1-5-21-1001",
        sid="S-1-5-21-1001",
    )


def test_register_task_uses_sid_logon_and_bounded_reliability_settings() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def runner(script: str, env: dict[str, str]) -> dict[str, object]:
        calls.append((script, env))
        if "RegisterTaskDefinition" in script:
            return {"success": True, "available": True, "sid": "S-1-5-21-1001"}
        return {
            "available": True,
            "exists": True,
            "enabled": True,
            "matches": True,
            "taskName": "AI Productivity Flow-S-1-5-21-1001",
            "sid": "S-1-5-21-1001",
        }

    result = windows_startup.register_task(_action(), runner=runner)

    assert result.success is True
    register_script = calls[0][0]
    inspect_script = calls[1][0]
    assert "$definition.Principal.LogonType = 3" in register_script
    assert "$definition.Principal.RunLevel = 0" in register_script
    assert "$trigger.Delay = 'PT10S'" in register_script
    assert "$settings.DisallowStartIfOnBatteries = $false" in register_script
    assert "$settings.StopIfGoingOnBatteries = $false" in register_script
    assert "$settings.RunOnlyIfNetworkAvailable = $false" in register_script
    assert "$settings.StartWhenAvailable = $true" in register_script
    assert "$settings.ExecutionTimeLimit = 'PT0S'" in register_script
    assert "$settings.RestartInterval = 'PT1M'" in register_script
    assert "$settings.RestartCount = 3" in register_script
    assert "$settings.Priority = 6" in register_script
    assert "$settings.MultipleInstances = 2" in register_script
    assert "GetCurrent().User.Value" in register_script
    assert "Resolve-IdentitySid $definition.Principal.UserId" in inspect_script
    assert "Resolve-IdentitySid $trigger.UserId" in inspect_script
    assert "NTAccount" in inspect_script
    assert ".Translate([System.Security.Principal.SecurityIdentifier])" in inspect_script
    assert "$principalSid -eq $sid" in inspect_script
    assert "$triggerSid -eq $sid" in inspect_script
    assert "RestartCount -eq 3" in inspect_script
    assert "Priority -eq 6" in inspect_script
    config = json.loads(calls[0][1]["VOICE_FLOW_STARTUP_CONFIG"])
    assert config == {
        "executable": _action().executable,
        "arguments": _action().arguments,
        "workingDirectory": _action().working_directory,
    }


def test_inspect_task_rejects_malformed_output_and_runner_errors() -> None:
    def malformed(_script: str, _env: dict[str, str]):
        raise RuntimeError("Windows Task Scheduler returned malformed status")

    status = windows_startup.inspect_task(_action(), runner=malformed)
    assert status.available is False
    assert "malformed" in (status.error or "")

    def timeout(_script: str, _env: dict[str, str]):
        raise subprocess.TimeoutExpired("powershell.exe", 10)

    status = windows_startup.inspect_task(_action(), runner=timeout)
    assert status.available is False
    assert "timed out" in (status.error or "").lower()


def test_powershell_runner_is_bounded_hidden_and_rejects_malformed_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    powershell = tmp_path / "powershell.exe"
    powershell.write_bytes(b"")
    observed: dict[str, object] = {}

    def fake_run(args, **kwargs):
        observed["args"] = args
        observed.update(kwargs)
        return types.SimpleNamespace(returncode=0, stdout="not-json", stderr="")

    monkeypatch.setattr(windows_startup.sys, "platform", "win32")
    monkeypatch.setattr(windows_startup, "powershell_executable", lambda: powershell)
    monkeypatch.setattr(windows_startup.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="malformed"):
        windows_startup._run_powershell("fixed script", {})

    assert observed["shell"] is False
    assert observed["timeout"] == windows_startup.POWERSHELL_TIMEOUT_SECONDS
    assert observed["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    assert "-ExecutionPolicy" not in observed["args"]
    assert observed["args"][-2:] == ["-Command", "fixed script"]


def test_scheduler_success_leaves_only_verified_task(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(windows_startup, "inspect_task", lambda _a: _status())
    monkeypatch.setattr(
        windows_startup,
        "register_task",
        lambda _a: windows_startup.TaskResult(True, status=_status(exists=True, enabled=True, matches=True)),
    )
    monkeypatch.setattr(installer, "unregister_registry_autorun", lambda: calls.append("run-off") or True)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: calls.append("lnk-off") or True)

    assert installer.set_autostart(True) is True
    assert calls == ["run-off", "lnk-off"]


def test_failed_task_registration_uses_one_run_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    inspections = iter((_status(), _status()))
    calls: list[str] = []
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(windows_startup, "inspect_task", lambda _a: next(inspections))
    monkeypatch.setattr(
        windows_startup,
        "register_task",
        lambda _a: windows_startup.TaskResult(False, available=True, error="denied"),
    )
    monkeypatch.setattr(installer, "register_registry_autorun", lambda: calls.append("run-on") or True)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: calls.append("lnk-off") or True)

    assert installer.set_autostart(True) is True
    assert calls == ["run-on", "lnk-off"]


def test_ambiguous_registration_failure_does_not_add_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    inspections = iter((_status(), _status(available=False)))
    fallback = []
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(windows_startup, "inspect_task", lambda _a: next(inspections))
    monkeypatch.setattr(
        windows_startup,
        "register_task",
        lambda _a: windows_startup.TaskResult(False, available=False, error="timed out"),
    )
    monkeypatch.setattr(installer, "register_registry_autorun", lambda: fallback.append(1) or True)

    assert installer.set_autostart(True) is False
    assert fallback == []


def test_query_timeout_never_creates_possible_duplicate_run_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback: list[str] = []
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(
        windows_startup,
        "inspect_task",
        lambda _a: _status(available=False),
    )
    monkeypatch.setattr(installer, "is_registry_autorun_enabled", lambda: False)
    monkeypatch.setattr(installer, "register_registry_autorun", lambda: fallback.append("created") or True)

    assert installer.set_autostart(True) is False
    assert fallback == []


def test_cleanup_failure_rolls_task_back_when_legacy_path_remains(monkeypatch: pytest.MonkeyPatch) -> None:
    removed: list[str] = []
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(windows_startup, "inspect_task", lambda _a: _status())
    monkeypatch.setattr(windows_startup, "register_task", lambda _a: windows_startup.TaskResult(True))
    monkeypatch.setattr(installer, "unregister_registry_autorun", lambda: False)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: True)
    monkeypatch.setattr(installer, "has_own_registry_autorun", lambda: True)
    monkeypatch.setattr(installer, "is_startup_folder_enabled", lambda: False)
    monkeypatch.setattr(
        windows_startup,
        "unregister_task",
        lambda: removed.append("task") or windows_startup.TaskResult(True),
    )

    assert installer.set_autostart(True) is False
    assert removed == ["task"]


def test_repeat_enable_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(
        windows_startup,
        "inspect_task",
        lambda _a: _status(exists=True, enabled=True, matches=True),
    )
    monkeypatch.setattr(installer, "unregister_registry_autorun", lambda: True)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: True)

    assert installer.set_autostart(True) is True
    # The autouse mutation guard proves register_task was not called.


def test_reconcile_respects_disabled_task_but_repairs_enabled_stale_task(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"status": _status(exists=True, enabled=False, matches=True)}
    registrations: list[str] = []
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(windows_startup, "inspect_task", lambda _a: state["status"])
    monkeypatch.setattr(installer, "unregister_registry_autorun", lambda: True)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: True)
    monkeypatch.setattr(
        windows_startup,
        "register_task",
        lambda _a: registrations.append("register") or windows_startup.TaskResult(True),
    )

    assert installer.reconcile_autostart(True) is False
    assert registrations == []

    state["status"] = _status(exists=True, enabled=True, matches=False)
    assert installer.reconcile_autostart(True) is True
    assert registrations == ["register"]


def test_status_prefers_task_and_accepts_fallback_only_when_task_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"status": _status(exists=True, enabled=False, matches=True)}
    monkeypatch.setattr(installer, "get_startup_action", _action)
    monkeypatch.setattr(windows_startup, "inspect_task", lambda _a: state["status"])
    monkeypatch.setattr(installer, "is_registry_autorun_enabled", lambda: True)
    monkeypatch.setattr(installer, "is_startup_folder_enabled", lambda: False)

    assert installer.is_autostart_enabled() is False
    state["status"] = _status(exists=True, enabled=True, matches=False)
    assert installer.is_autostart_enabled() is False
    state["status"] = _status()
    assert installer.is_autostart_enabled() is True


def test_disable_and_uninstall_remove_only_owned_startup_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        windows_startup,
        "unregister_task",
        lambda: calls.append("task") or windows_startup.TaskResult(True),
    )
    monkeypatch.setattr(installer, "unregister_registry_autorun", lambda: calls.append("run") or True)
    monkeypatch.setattr(installer, "unregister_startup_folder", lambda: calls.append("lnk") or True)

    assert installer.set_autostart(False) is True
    assert calls == ["task", "run", "lnk"]
    calls.clear()
    assert installer.uninstall_all() is True
    assert calls == ["task", "run", "lnk"]


def test_development_and_installed_actions_are_absolute_and_quoted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "project with spaces"
    root.mkdir()
    vbs = root / "VoiceFlowLauncher.vbs"
    vbs.write_text("' launcher", encoding="utf-8")
    wscript = tmp_path / "Windows" / "System32" / "wscript.exe"
    wscript.parent.mkdir(parents=True)
    wscript.write_bytes(b"")
    monkeypatch.setattr(installer, "_installed_watchdog_command", lambda: None)
    monkeypatch.setattr(installer, "get_project_root", lambda: root)
    monkeypatch.setattr(installer, "get_vbs_launcher_path", lambda: vbs)
    monkeypatch.setattr(installer, "_windows_system_executable", lambda _name: wscript)

    action = installer.get_startup_action()
    assert action is not None
    assert Path(action.executable).is_absolute()
    assert action.arguments == f'"{vbs.resolve()}"'
    assert action.working_directory == str(root.resolve())

    pythonw = tmp_path / "installed" / "pythonw.exe"
    pythonw.parent.mkdir()
    pythonw.write_bytes(b"")
    data = tmp_path / "data dir"
    monkeypatch.setattr(
        installer,
        "_installed_watchdog_command",
        lambda: (str(pythonw), "-m voice_flow.watchdog", str(data)),
    )
    installed = installer.get_startup_action()
    assert installed == windows_startup.StartupAction(
        str(pythonw), "-m voice_flow.watchdog", str(data.resolve())
    )


def test_native_settings_keeps_injected_registry_seam() -> None:
    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Registry:
        HKEY_CURRENT_USER = object()
        KEY_READ = 1
        KEY_WRITE = 2
        KEY_SET_VALUE = 2
        REG_SZ = 1

        def __init__(self):
            self.values: dict[str, str] = {}

        def OpenKey(self, *_args):
            return Key()

        def SetValueEx(self, _key, name, _reserved, _kind, value):
            self.values[name] = value

        def QueryValueEx(self, _key, name):
            if name not in self.values:
                raise FileNotFoundError(name)
            return self.values[name], self.REG_SZ

        def DeleteValue(self, _key, name):
            if name not in self.values:
                raise FileNotFoundError(name)
            del self.values[name]

    registry = Registry()
    command = r'"C:\Program Files\Voice Flow\pythonw.exe" -m voice_flow.watchdog'

    assert native_settings.set_launch_at_login(True, command, registry).applied is True
    assert native_settings.get_launch_at_login(registry).applied is True
    assert registry.values[native_settings.RUN_VALUE] == command
    assert native_settings.set_launch_at_login(False, registry=registry).applied is True
    assert native_settings.get_launch_at_login(registry).applied is False
