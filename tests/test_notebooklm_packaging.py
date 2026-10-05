"""Packaging and runtime discovery checks for NotebookLM's private tools."""

from __future__ import annotations

from pathlib import Path

from release.build_windows_release import (
    NOTEBOOKLM_PACKAGE,
    ensure_notebooklm_runtime,
    notebooklm_runtime_executables,
)
from voice_flow.video_flow_engine.notebooklm import config


class _EmptySettings:
    def get_setting(self, key):
        return None


def test_private_runtime_scripts_precede_personal_experiment(monkeypatch, tmp_path):
    runtime_scripts = tmp_path / "runtime" / "python" / "Scripts"
    runtime_scripts.mkdir(parents=True)
    cli = runtime_scripts / "notebooklm.exe"
    mcp = runtime_scripts / "notebooklm-mcp.exe"
    cli.touch()
    mcp.touch()
    active_python = tmp_path / "active" / "python.exe"
    active_python.parent.mkdir(parents=True)
    active_python.touch()

    monkeypatch.delenv("NOTEBOOKLM_CLI", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_MCP", raising=False)
    monkeypatch.setattr(config.sys, "executable", str(active_python))
    monkeypatch.setattr("voice_flow.runtime_env.runtime_root", lambda: tmp_path / "runtime")
    monkeypatch.setattr("voice_flow.storage.StorageEngine", lambda: _EmptySettings())
    monkeypatch.setattr(config, "ISOLATED_CLI_PATH", tmp_path / "personal" / "notebooklm.exe")
    monkeypatch.setattr(config, "ISOLATED_MCP_PATH", tmp_path / "personal" / "notebooklm-mcp.exe")

    assert config.resolve_notebooklm_cli() == cli
    assert config.resolve_notebooklm_mcp() == mcp


def test_explicit_cli_and_mcp_paths_still_win(monkeypatch, tmp_path):
    explicit_cli = tmp_path / "explicit-cli.exe"
    explicit_mcp = tmp_path / "explicit-mcp.exe"
    explicit_cli.touch()
    explicit_mcp.touch()

    assert config.resolve_notebooklm_cli(explicit_cli) == explicit_cli.resolve()
    assert config.resolve_notebooklm_mcp(explicit_mcp) == explicit_mcp.resolve()


def test_active_python_environment_is_used_when_no_private_runtime(monkeypatch, tmp_path):
    active = tmp_path / "active" / "Scripts"
    active.mkdir(parents=True)
    cli = active / "notebooklm.exe"
    mcp = active / "notebooklm-mcp.exe"
    cli.touch()
    mcp.touch()
    python = active.parent / "python.exe"
    python.touch()

    monkeypatch.delenv("NOTEBOOKLM_CLI", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_MCP", raising=False)
    monkeypatch.setattr(config.sys, "executable", str(python))
    monkeypatch.setattr("voice_flow.runtime_env.runtime_root", lambda: None)
    monkeypatch.setattr("voice_flow.storage.StorageEngine", lambda: _EmptySettings())
    monkeypatch.setattr(config, "ISOLATED_CLI_PATH", tmp_path / "personal" / "notebooklm.exe")
    monkeypatch.setattr(config, "ISOLATED_MCP_PATH", tmp_path / "personal" / "notebooklm-mcp.exe")

    assert config.resolve_notebooklm_cli() == cli
    assert config.resolve_notebooklm_mcp() == mcp


def test_release_preflight_targets_both_notebooklm_console_scripts(tmp_path):
    expected = [
        tmp_path / "python" / "Scripts" / "notebooklm.exe",
        tmp_path / "python" / "Scripts" / "notebooklm-mcp.exe",
    ]
    assert notebooklm_runtime_executables(tmp_path) == expected


def test_release_provisioning_uses_uv_for_the_private_runtime(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    runtime = staging / "runtime"
    python = runtime / "python" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    commands: list[list[str]] = []

    monkeypatch.setattr("release.build_windows_release.shutil.which", lambda name: "C:/tools/uv.exe")

    def fake_run(command, **kwargs):
        commands.append(command)
        for script in notebooklm_runtime_executables(runtime):
            script.parent.mkdir(parents=True, exist_ok=True)
            script.touch()
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("release.build_windows_release.subprocess.run", fake_run)

    assert ensure_notebooklm_runtime(staging) is True
    assert commands == [["C:/tools/uv.exe", "pip", "install", "--python", str(python), NOTEBOOKLM_PACKAGE]]


def test_release_provisioning_uses_private_python_pip_when_uv_is_absent(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    runtime = staging / "runtime"
    python = runtime / "python" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    commands: list[list[str]] = []

    monkeypatch.setattr("release.build_windows_release.shutil.which", lambda name: None)

    def fake_run(command, **kwargs):
        commands.append(command)
        for script in notebooklm_runtime_executables(runtime):
            script.parent.mkdir(parents=True, exist_ok=True)
            script.touch()
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("release.build_windows_release.subprocess.run", fake_run)

    assert ensure_notebooklm_runtime(staging) is True
    assert commands == [[str(python), "-m", "pip", "install", NOTEBOOKLM_PACKAGE]]


def test_release_provisioning_skips_when_both_scripts_are_staged(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    runtime = staging / "runtime"
    for script in notebooklm_runtime_executables(runtime):
        script.parent.mkdir(parents=True, exist_ok=True)
        script.touch()
    monkeypatch.setattr(
        "release.build_windows_release.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not install")),
    )

    assert ensure_notebooklm_runtime(staging) is False
