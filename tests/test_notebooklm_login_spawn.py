"""NotebookLM sign-in must survive a windowless parent and report real failures.

The installed app is pythonw.exe. Spawning the pip console-script shim with
CREATE_NO_WINDOW makes that child exit before Chrome opens, and the old
launcher discarded the child's output. These tests cover the spawn used in
production.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from voice_flow.video_flow_engine.notebooklm import login_flow


def _reset_login_state() -> None:
    login_flow._LOGIN_CANCEL.clear()
    login_flow._ACTIVE_LOGIN_PROCESS = None
    login_flow._ACTIVE_LOGIN_PROFILE = None
    with login_flow._STATE_LOCK:
        login_flow._STATE.update(
            running=False,
            mode=None,
            started_at=None,
            finished_at=None,
            success=None,
            error=None,
            note=None,
            durable=None,
            log_path=None,
            exit_code=None,
            window_opened=None,
            cancelled=False,
            browser=None,
        )


def test_cli_argv_uses_console_python_beside_the_shim(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "python"
    scripts = runtime / "Scripts"
    scripts.mkdir(parents=True)
    shim = scripts / "notebooklm.exe"
    python_exe = runtime / "python.exe"
    pythonw = runtime / "pythonw.exe"
    shim.write_text("", encoding="utf-8")
    python_exe.write_text("", encoding="utf-8")
    pythonw.write_text("", encoding="utf-8")

    argv = login_flow._cli_argv([str(shim), "--profile", "video-flow-experiment", "login", "--browser", "chrome"])

    assert argv[:3] == [str(python_exe), "-m", "notebooklm"]
    assert "login" in argv
    assert "--browser" in argv
    assert argv[argv.index("--browser") + 1] == "chrome"
    assert "pythonw" not in Path(argv[0]).name.lower()


def test_login_spawn_hides_the_console_without_create_no_window() -> None:
    kwargs = login_flow._login_spawn_kwargs()
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    assert int(kwargs.get("creationflags", 0)) & no_window == 0
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.PIPE
    assert kwargs["stdin"] == subprocess.DEVNULL


def test_browser_fallback_is_chrome_then_edge_then_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(login_flow.sys, "platform", "win32")
    installed = {"chrome": True, "msedge": True}
    monkeypatch.setattr(login_flow, "_browser_installed", lambda name: installed.get(name, False))
    assert login_flow.resolve_interactive_browser("chrome") == "chrome"
    installed["chrome"] = False
    assert login_flow.resolve_interactive_browser("chrome") == "msedge"
    installed["msedge"] = False
    assert login_flow.resolve_interactive_browser("chrome") == "chromium"
    assert login_flow.resolve_interactive_browser(None) == "chromium"


def test_immediate_exit_surfaces_child_stderr_and_exit_code(tmp_path: Path) -> None:
    script = tmp_path / "fail_login.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.write('partial-stdout\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stderr.write('chrome failed to launch\\n')\n"
        "sys.stderr.flush()\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )
    log_path = tmp_path / "logs" / "notebooklm-login.log"
    code, err = login_flow._run_login_once(
        [sys.executable, str(script), "--profile", "video-flow-experiment", "login", "--browser", "chrome"],
        log_path,
        30,
    )
    text = log_path.read_text(encoding="utf-8")

    assert code == 3
    assert "partial-stdout" in text
    assert "chrome failed to launch" in text
    assert "[exit code 3" in text
    assert "did not open" in err
    assert "chrome failed to launch" in err
    assert "exit 3" in err
    assert "did not finish" not in err.lower()
    assert login_flow._run_login_once.last_detail["window_opened"] is False
    assert login_flow._run_login_once.last_detail["exit_code"] == 3


def test_spawn_from_parent_with_closed_stdio_keeps_the_child_alive(tmp_path: Path) -> None:
    """Simulate pythonw: the parent has no standard handles, and the child must live."""
    result_path = tmp_path / "result.json"
    child = tmp_path / "child_login.py"
    child.write_text(
        "import sys, time\n"
        "print('child-alive', flush=True)\n"
        "sys.stderr.write('child-err\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    src = str(Path(login_flow.__file__).resolve().parents[3])
    parent = tmp_path / "closed_stdio_parent.py"
    parent.write_text(
        textwrap.dedent(
            f"""
            import json, os, sys, time
            sys.path.insert(0, {src!r})
            from voice_flow.video_flow_engine.notebooklm.login_flow import spawn_notebooklm_process
            for fd in (0, 1, 2):
                try:
                    os.close(fd)
                except OSError:
                    pass
            proc = spawn_notebooklm_process([{sys.executable!r}, {str(child)!r}])
            time.sleep(1.0)
            alive = proc.poll() is None
            out = ""
            err = ""
            if proc.stdout is not None:
                import threading
                box = {{}}
                def read_out():
                    box["out"] = proc.stdout.readline()
                def read_err():
                    box["err"] = proc.stderr.readline()
                threads = [threading.Thread(target=read_out), threading.Thread(target=read_err)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(2)
                out = box.get("out") or ""
                err = box.get("err") or ""
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass
            payload = {{"alive": alive, "out": out, "err": err, "code": proc.poll()}}
            with open({str(result_path)!r}, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            """
        ),
        encoding="utf-8",
    )
    completed = subprocess.run([sys.executable, str(parent)], capture_output=True, text=True, timeout=20)
    assert result_path.is_file(), completed.stderr
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["alive"] is True, payload
    assert "child-alive" in payload["out"]
    assert "child-err" in payload["err"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows CI check for the installed login spawn")
def test_windows_login_command_stays_alive_for_browser_timeout(tmp_path: Path) -> None:
    """The login command, spawned like the installed app, must not exit immediately."""
    sleeper = tmp_path / "sleeper.py"
    sleeper.write_text(
        "import sys, time\n"
        "timeout = 8\n"
        "if '--browser-timeout' in sys.argv:\n"
        "    timeout = int(sys.argv[sys.argv.index('--browser-timeout') + 1])\n"
        "print('login-wait-start', flush=True)\n"
        "time.sleep(timeout)\n",
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime" / "python"
    scripts = runtime / "Scripts"
    scripts.mkdir(parents=True)
    # A named shim beside python.exe is what the installed app resolves.
    # The alive check itself uses the production spawn flags on this command.
    command = [
        sys.executable,
        str(sleeper),
        "--profile",
        "video-flow-experiment",
        "login",
        "--browser",
        "chrome",
        "--browser-timeout",
        "8",
    ]
    proc = login_flow.spawn_notebooklm_process(command)
    try:
        time.sleep(3)
        assert proc.poll() is None, f"login command exited early with {proc.poll()}"
    finally:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


def test_double_click_does_not_start_a_second_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOICE_FLOW_LOGIN_DISABLE", raising=False)
    monkeypatch.setattr(login_flow, "resolve_notebooklm_cli", lambda: Path("C:/fake/notebooklm.exe"))
    monkeypatch.setattr(login_flow, "_terminate_stale_login_processes", lambda *args, **kwargs: 0)
    monkeypatch.setattr(login_flow, "_prepare_browser_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(login_flow, "verify_online", lambda **kwargs: {
        "authenticated": True, "status": "ok", "email": "person@example.com",
    })
    started = threading.Event()
    release = threading.Event()
    calls: list[list[str]] = []

    def blocking(command, log_path, timeout):
        calls.append(list(command))
        started.set()
        assert release.wait(5)
        return 0, ""

    monkeypatch.setattr(login_flow, "_run_login_once", blocking)
    wipes: list[str] = []
    monkeypatch.setattr(login_flow, "_clean_account_state_for_switch", lambda profile: wipes.append(profile))
    _reset_login_state()
    try:
        first = login_flow.start_login(profile="video-flow-experiment", mode="cli", browser="chrome")
        assert first["launched"] is True
        assert started.wait(2)
        second = login_flow.start_login(profile="video-flow-experiment", mode="cli", browser="chrome")
        switched = login_flow.start_login(
            profile="video-flow-experiment", mode="cli", browser="chrome", switch_account=True,
        )
        assert second["already_running"] is True
        assert second["launched"] is True
        assert switched["already_running"] is True
        assert wipes == []
        assert len(calls) == 1
    finally:
        release.set()
        for _ in range(50):
            if not login_flow.get_login_state().get("running"):
                break
            time.sleep(0.05)
        _reset_login_state()


def test_keepalive_stays_quiet_without_a_session_and_refreshes_a_master_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voice_flow.video_flow_engine.notebooklm.keepalive import NotebookLMKeepaliveService

    empty = tmp_path / "empty" / "storage_state.json"
    empty.parent.mkdir()
    empty.write_text('{"cookies":[{"name":"SID","value":""}]}', encoding="utf-8")
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda profile=None: empty,
    )
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.get_login_state",
        lambda: {"running": False},
    )
    healed: list[dict] = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: healed.append(kwargs) or {"ok": True},
    )
    quiet = NotebookLMKeepaliveService(profile="video-flow-experiment", refresh_func=None)
    result = quiet.run_once()
    assert result["reason"] == "no_saved_session"
    assert result["ran"] is False
    assert healed == []

    durable = tmp_path / "durable" / "storage_state.json"
    durable.parent.mkdir()
    durable.write_text('{"cookies":[]}', encoding="utf-8")
    (durable.parent / "master_token.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.config.get_storage_state_path",
        lambda profile=None: durable,
    )
    seen: list[str] = []

    def refresh(*, profile: str) -> dict:
        seen.append(profile)
        return {"ok": True}

    service = NotebookLMKeepaliveService(profile="video-flow-experiment", refresh_func=refresh)
    refreshed = service.run_once()
    assert seen == ["video-flow-experiment"]
    assert refreshed.get("reason") != "no_saved_session"
