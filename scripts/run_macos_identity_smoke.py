"""Bounded CI smoke via LaunchServices, with cleanup scoped to this bundle/run."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


_INVENTORY = """
ObjC.import('AppKit');
function run(argv) {
    var apps = $.NSWorkspace.sharedWorkspace.runningApplications;
    var pids = [];
    for (var i = 0; i < apps.count; i++) {
        var app = apps.objectAtIndex(i);
        if (app.executableURL && ObjC.unwrap(app.executableURL.path).indexOf(argv[0] + '/') === 0)
            pids.push(Number(app.processIdentifier));
    }
    return JSON.stringify(pids);
}
"""


def _bundle_pids(app_path: Path) -> set[int]:
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", _INVENTORY, str(app_path)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    return set(json.loads(result.stdout))


def main(argv: list[str]) -> int:
    if len(argv) != 3 or sys.platform != "darwin":
        print("usage (macOS): python scripts/run_macos_identity_smoke.py APP_PATH OUT_DIR", file=sys.stderr)
        return 2
    app_path = Path(argv[1]).resolve()
    out = Path(argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not app_path.is_dir() or app_path.suffix != ".app":
        print("Missing built .app bundle", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[1]
    before = _bundle_pids(app_path)
    # A clean runner is required so an existing instance cannot satisfy this run.
    if before:
        print("Bundle already running before CI smoke; refusing to reuse it", file=sys.stderr)
        return 1
    launcher = None
    try:
        launcher = subprocess.Popen([
            "open", "-n", "-W", "--stdout", str(out / "app-stdout.txt"),
            "--stderr", str(out / "app-stderr.txt"), str(app_path),
        ])
        started = time.monotonic()
        for seconds in (30, 60):
            time.sleep(max(0, started + seconds - time.monotonic()))
            with (out / f"identity-{seconds}s.json").open("w", encoding="utf-8") as evidence, (out / f"capture-{seconds}s-stderr.txt").open("w", encoding="utf-8") as capture_errors:
                subprocess.run([
                    "osascript", "-l", "JavaScript",
                    str(root / "scripts/capture_macos_app_identity.js"), str(app_path),
                ], stdout=evidence, stderr=capture_errors, check=False, timeout=20)
            subprocess.run(["screencapture", "-x", str(out / f"screen-{seconds}s.png")], check=True, timeout=10)
            with (out / "alive.txt").open("a", encoding="utf-8") as alive:
                bundle_running = bool(_bundle_pids(app_path))
                engine_running = launcher.poll() is None
                alive.write(f"{seconds}s: {'running' if engine_running and bundle_running else 'EXITED'}\n")
        try:
            report = json.loads((out / "identity-60s.json").read_text(encoding="utf-8"))
        except ValueError:
            report = {"applications": []}
        with (out / "windows.txt").open("w", encoding="utf-8") as windows:
            for app in report["applications"]:
                windows.write(f"{app['localizedName']}: {', '.join(app['windows'])}\n")
        shutil.copyfile(out / "identity-60s.json", out / "processes.txt")
        log = Path.home() / ".voice_flow/gui_launcher.log"
        if log.is_file():
            shutil.copyfile(log, out / "gui_launcher.log")
        return subprocess.run([
            sys.executable, str(root / "scripts/check_mac_smoke_artifacts.py"), str(out),
        ], check=False, timeout=20).returncode
    except Exception as exc:
        try:
            (out / "smoke-error.txt").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        except OSError:
            pass
        raise
    finally:
        cleanup_errors = []
        try:
            log = Path.home() / ".voice_flow/gui_launcher.log"
            if log.is_file():
                shutil.copyfile(log, out / "gui_launcher.log")
        except Exception as exc:
            cleanup_errors.append(f"launcher log: {exc}")
        try:
            # Re-query executable paths; never terminate unrelated runner apps.
            owned = _bundle_pids(app_path) - before
            for pid in owned:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    cleanup_errors.append(f"terminate PID {pid}: {exc}")
            if owned:
                time.sleep(2)
                for pid in (_bundle_pids(app_path) - before) & owned:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except OSError as exc:
                        cleanup_errors.append(f"kill PID {pid}: {exc}")
        except Exception as exc:
            cleanup_errors.append(f"bundle cleanup: {exc}")
        # Always try our own wrapper, even when inventory or diagnostics failed.
        if launcher is not None:
            try:
                if launcher.poll() is None:
                    launcher.terminate()
                    try:
                        launcher.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        launcher.kill()
                        launcher.wait(timeout=5)
            except Exception as exc:
                cleanup_errors.append(f"open wrapper cleanup: {exc}")
        if cleanup_errors:
            message = "\n".join(cleanup_errors) + "\n"
            print(message, file=sys.stderr)
            try:
                (out / "cleanup-errors.txt").write_text(message, encoding="utf-8")
            except OSError:
                pass



if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
