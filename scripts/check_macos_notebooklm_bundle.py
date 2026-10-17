#!/usr/bin/env python3
"""Assert the macOS .app can import NotebookLM and keep a login process alive.

The published v1.0.4 bundle reported ``cli_path: null`` while
``bin/notebooklm-mcp`` was present, so sign-in never started. This check runs
against the built ``.app`` and fails the macOS release job when that regresses.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _stop(process: subprocess.Popen) -> None:
    try:
        import psutil
        owned = psutil.Process(process.pid)
        for child in owned.children(recursive=True):
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=5)
    except Exception:
        pass


def main() -> None:
    if len(sys.argv) != 2:
        _fail(f"usage: {Path(sys.argv[0]).name} 'AI Productivity Flow.app'")
    app = Path(sys.argv[1]).resolve()
    python = app / "Contents" / "Resources" / "runtime" / "python" / "bin" / "python3"
    cli = python.parent / "notebooklm"
    if not python.is_file():
        _fail(f"bundled python3 is missing: {python}")
    if not cli.is_file():
        _fail(f"bundled notebooklm CLI is missing: {cli}")

    probe = subprocess.run(
        [str(python), "-c", "import notebooklm, pathlib; print(pathlib.Path(notebooklm.__file__).resolve())"],
        capture_output=True,
        text=True,
        check=False,
    )
    module = (probe.stdout or "").strip()
    runtime = python.parent.parent
    if probe.returncode != 0 or not module or runtime not in Path(module).parents:
        _fail(
            "bundled python3 could not import notebooklm from the app runtime.\n"
            f"stdout={probe.stdout}\nstderr={probe.stderr}"
        )
    print(f"notebooklm module: {module}")

    from voice_flow.video_flow_engine.notebooklm.login_flow import spawn_notebooklm_process

    home = Path(tempfile.mkdtemp(prefix="apf-nlm-bundle-"))
    command = [
        str(python), "-m", "notebooklm",
        "--profile", "video-flow-experiment",
        "login",
        "--browser", "chrome",
        "--browser-timeout", "8",
    ]
    process = spawn_notebooklm_process(command, env={
        "HOME": str(home),
        "NOTEBOOKLM_HOME": str(home / ".notebooklm"),
    })
    try:
        time.sleep(3)
        if process.poll() is not None:
            out = ""
            err = ""
            if process.stdout is not None:
                out = process.stdout.read()
            if process.stderr is not None:
                err = process.stderr.read()
            _fail(
                "bundled `python3 -m notebooklm login` exited before the browser wait "
                f"(code {process.returncode}).\nstdout={out}\nstderr={err}"
            )
        print("notebooklm login still running after 3s")
    finally:
        _stop(process)


if __name__ == "__main__":
    main()
