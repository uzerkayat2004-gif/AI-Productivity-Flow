"""Spawn NotebookLM login the way the installed app does, from this pythonw process.

Writes a status JSON file. Does not type into Google or finish sign-in.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    status_path = Path(sys.argv[1])
    write(status_path, {"stage": "starting", "executable": sys.executable})
    try:
        from voice_flow.video_flow_engine.notebooklm.login_flow import (
            _cli_argv,
            resolve_interactive_browser,
            spawn_notebooklm_process,
        )

        runtime = Path(sys.executable).resolve().parent
        cli = runtime / "Scripts" / "notebooklm.exe"
        browser = resolve_interactive_browser("chrome")
        command = [
            str(cli),
            "--profile",
            "e2e-release-test",
            "login",
            "--browser",
            browser,
            "--browser-timeout",
            "25",
        ]
        argv = _cli_argv(list(command))
        started = time.time()
        process = spawn_notebooklm_process(command)
        while True:
            code = process.poll()
            write(
                status_path,
                {
                    "stage": "spawned",
                    "pid": process.pid,
                    "browser": browser,
                    "command": command,
                    "argv": argv,
                    "parent": sys.executable,
                    "elapsed": round(time.time() - started, 3),
                    "exit_code": code,
                    "alive": code is None,
                },
            )
            if code is not None:
                return 0
            time.sleep(0.4)
    except Exception:
        write(status_path, {"stage": "error", "error": traceback.format_exc(), "alive": False})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
