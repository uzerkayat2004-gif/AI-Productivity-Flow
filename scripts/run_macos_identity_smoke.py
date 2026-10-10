"""Bounded CI smoke via LaunchServices, with cleanup scoped to this bundle/run."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import platform
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


_PROC_PIDPATH = None


def _process_path(pid: int) -> str:
    """Resolve actual kernel executable path even when comm was renamed."""
    global _PROC_PIDPATH
    if _PROC_PIDPATH is None:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        function = library.proc_pidpath
        function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        function.restype = ctypes.c_int
        _PROC_PIDPATH = function
    function = _PROC_PIDPATH
    buffer = ctypes.create_string_buffer(4096)
    if function(pid, buffer, len(buffer)) <= 0:
        raise OSError(ctypes.get_errno(), "proc_pidpath unavailable for PID")
    return os.fsdecode(buffer.value)


def _owned_processes(app_path: Path, errors: list | None = None) -> list[dict]:
    """Resolve argv-free OS PID/PPID entries independently of registration/name."""
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,comm="], capture_output=True,
        text=True, check=True, timeout=3,
    )
    owned = []
    deadline = time.monotonic() + 3
    for line in result.stdout.splitlines()[:4096]:
        if time.monotonic() > deadline:
            if errors is not None:
                errors.append("proc_pidpath inventory reached 3-second bound")
            break
        fields = line.strip().split(None, 2)
        if len(fields) != 3:
            continue
        pid, ppid, comm = fields
        try:
            executable = _process_path(int(pid))
        except (OSError, ValueError) as exc:
            if errors is not None and len(errors) < 32:
                errors.append({"pid": pid, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if executable.startswith(str(app_path) + "/"):
            owned.append({"pid": int(pid), "ppid": int(ppid), "executablePath": executable, "comm": comm})
    return owned


def _record_state(app_path: Path, out: Path, launcher, seconds: int, started: float) -> None:
    state = {"sampleSeconds": seconds, "elapsedSeconds": time.monotonic() - started,
             "wrapperPid": launcher.pid, "wrapperReturncode": launcher.poll(),
             "statusInterpretation": "Wrapper/native registration are independent signals; kernel PID path errors or absent registration do not prove engine exit. Legacy alive.txt requires wrapper pending and nonempty native PID set."}
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", _INVENTORY, str(app_path)],
            capture_output=True, text=True, check=True, timeout=3,
        )
        state["nativeBundlePids"] = sorted(json.loads(result.stdout))
    except Exception as exc:
        state["nativeInventoryError"] = f"{type(exc).__name__}: {exc}"
    try:
        path_errors = []
        state["ownedProcesses"] = _owned_processes(app_path, path_errors)
        state["processInventoryComplete"] = not bool(path_errors)
        if path_errors:
            state["processPathErrors"] = path_errors
    except Exception as exc:
        state["processInventoryError"] = f"{type(exc).__name__}: {exc}"
    try:
        (out / f"launcher-status-{seconds}s.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Could not save launcher status: {exc}", file=sys.stderr)


def _redact_excerpt(lines: list[str]) -> str:
    try:
        from scripts.report_macos_launch_failure import _SENSITIVE, _URL_QUERY
    except ModuleNotFoundError:
        from report_macos_launch_failure import _SENSITIVE, _URL_QUERY
    output = []
    for line in lines[:120]:
        # Search before truncating, so a credential past the limit still drops its line.
        if _SENSITIVE.search(line):
            output.append("[credential-bearing line redacted]")
        else:
            output.append(_URL_QUERY.sub(r"\1?[query redacted]", line)[:1500])
    return ("\n".join(output) + "\n")[:65536]


def _crash_excerpt(report: Path) -> str:
    """Extract headers and crashed stack before redaction; never upload full report."""
    with report.open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024).decode("utf-8", errors="replace")
    if report.suffix == ".ips":
        decoder = json.JSONDecoder()
        documents = []
        remainder = raw.lstrip()
        for _ in range(2):
            if not remainder:
                break
            try:
                document, end = decoder.raw_decode(remainder)
            except ValueError:
                break
            documents.append(document)
            remainder = remainder[end:].lstrip()
        lines = []
        header = documents[0] if documents and isinstance(documents[0], dict) else {}
        body = documents[-1] if documents and isinstance(documents[-1], dict) else {}
        for label, record, fields in (
            ("header", header, ("app_name", "timestamp", "app_version", "bundleID", "os_version", "bug_type")),
            ("process", body, ("procName", "procPath", "pid", "parentProc", "parentPid", "osVersion", "exception", "termination", "faultingThread")),
        ):
            for field in fields:
                if field in record:
                    lines.append(f"{label}.{field}: {json.dumps(record[field], ensure_ascii=False)}")
        threads = body.get("threads", [])
        faulting = body.get("faultingThread")
        crashed = None
        if isinstance(threads, list):
            if type(faulting) is int and 0 <= faulting < len(threads):
                crashed = threads[faulting]
            else:
                crashed = next((thread for thread in threads if isinstance(thread, dict) and thread.get("triggered") is True), None)
        if isinstance(crashed, dict):
            lines.append(f"crashedThread.name: {crashed.get('name', '')}")
            frames = crashed.get("frames", [])
            if isinstance(frames, list):
                images = body.get("usedImages", [])
                for index, frame in enumerate(frames[:30]):
                    lines.append(f"frame {index}: {json.dumps(frame, ensure_ascii=False)}")
                    image_index = frame.get("imageIndex") if isinstance(frame, dict) else None
                    if type(image_index) is int and isinstance(images, list) and 0 <= image_index < len(images):
                        image = images[image_index]
                        if isinstance(image, dict):
                            lines.append(f"frame {index} image: {image.get('path', image.get('name', ''))}")
        if crashed is None:
            lines.append("[crashed-thread stack unavailable in bounded structured input]")
        if not lines or (len(documents) == 1 and remainder):
            lines.append("[structured IPS parse incomplete or report exceeds 8 MiB; header only may be available]")
        return _redact_excerpt(lines)
    # Traditional reports put the exception/termination details in the header.
    lines = raw.splitlines()
    excerpt = lines[:45]
    for index, line in enumerate(lines):
        if line.startswith("Thread ") and "Crashed:" in line:
            excerpt.append(line)
            for frame in lines[index + 1:index + 31]:
                if not frame.strip() or frame.startswith("Thread "):
                    break
                excerpt.append(frame)
            break
    return _redact_excerpt(excerpt)


def _collect_diagnostics(app_path: Path, out: Path, launched_at: float) -> None:
    """Bounded, best-effort collection; errors cannot replace the smoke result."""
    try:
        from scripts.report_macos_launch_failure import log_tail
    except ModuleNotFoundError:
        from report_macos_launch_failure import log_tail
    errors = []
    resources = app_path / "Contents/Resources"
    environment = {"os": platform.system(), "architecture": platform.machine(),
                   "macosVersion": platform.mac_ver()[0], "ciPythonVersion": platform.python_version(),
                   "runnerImageOS": os.environ.get("ImageOS", ""), "runnerImageVersion": os.environ.get("ImageVersion", "")}
    try:
        result = subprocess.run(["sw_vers"], capture_output=True, text=True, check=True, timeout=3)
        environment["swVers"] = result.stdout.strip()
    except Exception as exc:
        environment["swVersError"] = f"{type(exc).__name__}: {exc}"
    try:
        manifest = resources / "runtime/build-manifest.json"
        if manifest.is_file():
            # The manifest contains build/runtime versions, never app configuration.
            environment["runtimeBuildManifest"] = json.loads(manifest.read_text(encoding="utf-8"))
        (out / "environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
    except (OSError, ValueError) as exc:
        errors.append(f"environment metadata: {exc}")
    sources = {
        "engine-debug.log": Path.home() / ".voice_flow/logs/voice_flow_debug.log",
        "bundled-engine-debug.log": resources / "voice_flow_debug.log",
        "bundled-crash_log.txt": resources / "crash_log.txt",
        "gui_launcher.log": Path.home() / ".voice_flow/gui_launcher.log",
        "gui_crash.log": Path.home() / ".voice_flow/gui_crash.log",
    }
    for name, source in sources.items():
        try:
            # Existing reporter redacts credential lines/query strings and bounds
            # output to 64 KiB input / 120 tail lines. No raw app log is copied.
            (out / name).write_text(log_tail(source) + "\n", encoding="utf-8")
        except OSError as exc:
            errors.append(f"{name}: {exc}")
    try:
        # Read packaged metadata without launching another bundled Python process.
        metadata_paths = list((resources / "runtime/site-packages").glob("pynput-*.dist-info/METADATA"))
        metadata_paths += list((resources / "runtime/python/lib/python3.11/site-packages").glob("pynput-*.dist-info/METADATA"))
        versions = []
        for metadata in metadata_paths[:4]:
            with metadata.open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream.read(65536).splitlines():
                    if line.startswith("Version: "):
                        versions.append(line.removeprefix("Version: "))
                        break
        (out / "packaged-pynput-version.txt").write_text("\n".join(versions) + ("\n" if versions else "metadata not found\n"), encoding="utf-8")
    except OSError as exc:
        errors.append(f"pynput metadata: {exc}")
    copied = 0
    for directory in (Path.home() / "Library/Logs/DiagnosticReports", Path("/Library/Logs/DiagnosticReports")):
        try:
            reports = sorted(directory.glob("*"), key=lambda path: path.name)
            for report in reports:
                name = report.name.lower()
                if copied >= 8:
                    break
                if report.suffix not in (".ips", ".crash") or not any(marker in name for marker in ("python", "ai productivity flow", "ai-productivity-flow")):
                    continue
                if report.stat().st_mtime < launched_at or not report.is_file():
                    continue
                crash_dir = out / "crash"
                crash_dir.mkdir(exist_ok=True)
                (crash_dir / f"{copied}-{report.name}.redacted.txt").write_text(_crash_excerpt(report), encoding="utf-8")
                copied += 1
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"crash reports in {directory}: {exc}")
    if errors:
        try:
            (out / "diagnostic-errors.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")
        except OSError:
            pass


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
    try:
        from scripts.probe_macos_embedded_runtime import capture_embedded_runtime
    except ModuleNotFoundError:
        from probe_macos_embedded_runtime import capture_embedded_runtime
    before = _bundle_pids(app_path)
    # A clean runner is required so an existing instance cannot satisfy this run.
    if before:
        print("Bundle already running before CI smoke; refusing to reuse it", file=sys.stderr)
        return 1
    capture_embedded_runtime(app_path, out)
    launcher = None
    launched_at = time.time()
    try:
        launcher = subprocess.Popen([
            "open", "-n", "-W", "--stdout", str(out / "app-stdout.txt"),
            "--stderr", str(out / "app-stderr.txt"), str(app_path),
        ])
        started = time.monotonic()
        for seconds in (1, 5, 15, 30, 60):
            time.sleep(max(0, started + seconds - time.monotonic()))
            _record_state(app_path, out, launcher, seconds, started)
            if seconds not in (30, 60):
                continue
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
        _collect_diagnostics(app_path, out, launched_at)
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
            _collect_diagnostics(app_path, out, launched_at)
        except Exception as exc:
            cleanup_errors.append(f"diagnostic collection: {exc}")
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
