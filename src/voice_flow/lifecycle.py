"""Voice Flow Suite Lifecycle and Application Restart Manager.

Provides clean, graceful hard-reset and restart capabilities for Voice Flow on Windows:
1. Resets floating overlay bar position and flushes audio buffers.
2. Gracefully signals watchdog supervisor to stop auto-recovery during restart.
3. Terminates backend (voice_flow.main), supervisor (voice_flow.watchdog), and
   pywebview GUI (voice_flow.gui.desktop_launcher) processes without lingering zombies.
4. Releases and reclaims runtime port 8991 and clears lock files.
5. Relaunches the entire Voice Flow suite fresh using the stable launcher.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence

from voice_flow.paths import data_dir


def _get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _get_src_dir() -> Path:
    from voice_flow.watchdog import get_src_dir
    return get_src_dir()


RESTART_LOCK_FILENAME = "restart_sequence.lock"
RESTART_LOCK_STALE_SECONDS = 90.0
WATCHDOG_FLAG_FILENAME = "watchdog_shutdown.flag"


def _debug_log(msg: str, log_name: str = "restart_debug.log") -> None:
    """Best-effort append to a debug log inside the data directory."""
    try:
        log_path = data_dir() / log_name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _pid_is_alive(pid: int | None) -> bool:
    """Best-effort liveness check that never raises."""
    if not pid or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        import psutil
        return bool(psutil.pid_exists(pid))
    except Exception:
        return False


def _restart_lock_path() -> Path:
    return data_dir() / RESTART_LOCK_FILENAME


def try_acquire_restart_lock() -> bool:
    """Guard against concurrent restart sequences double-spawning the suite.

    A second restart request while a sequence is running must be refused,
    otherwise the second sequence's terminate sweep kills the suite the first
    sequence just relaunched (observed as: window opens, closes ~9s later).
    The lock auto-expires after RESTART_LOCK_STALE_SECONDS or when the owning
    PID is dead, so a crashed sequence can never wedge future restarts.
    """
    lock = _restart_lock_path()
    now = time.time()
    if lock.exists():
        owner_pid = 0
        age = RESTART_LOCK_STALE_SECONDS + 1.0
        try:
            parts = lock.read_text(encoding="utf-8").split()
            if len(parts) >= 2:
                owner_pid = int(parts[0])
                age = max(0.0, now - float(parts[1]))
        except Exception:
            owner_pid, age = 0, RESTART_LOCK_STALE_SECONDS + 1.0

        if age < RESTART_LOCK_STALE_SECONDS and _pid_is_alive(owner_pid):
            _debug_log(f"restart_suite refused: sequence already in progress (owner pid={owner_pid}, age={age:.1f}s)")
            return False
        # Stale or dead owner: take over.
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create so two simultaneous requests cannot both win.
        with open(lock, "x", encoding="utf-8") as f:
            f.write(f"{os.getpid()} {now}")
        return True
    except FileExistsError:
        return False
    except Exception:
        # If we cannot even write the lock, proceed rather than block restarts.
        return True


def release_restart_lock() -> None:
    try:
        _restart_lock_path().unlink(missing_ok=True)
    except Exception:
        pass


def _ancestor_pids(max_levels: int = 16) -> list[int]:
    """Return this process's ancestor chain, closest parent first.

    The restart sequencer runs as a child of the API server, which itself
    lives inside the suite process tree. When terminate_suite_processes kills
    suite processes it can take down its own ancestors (or itself via a tree
    kill); the whole ancestor chain must therefore be excluded from the sweep
    and terminated explicitly only AFTER the relaunch has been secured.
    """
    chain: list[int] = []
    try:
        import psutil
        pid = os.getpid()
        for _ in range(max_levels):
            try:
                parent = psutil.Process(pid).parent()
            except Exception:
                break
            if parent is None:
                break
            if parent.pid in chain or parent.pid == os.getpid():
                break
            chain.append(parent.pid)
            pid = parent.pid
    except Exception:
        pass
    return chain


def _terminate_ancestors(ancestors: Sequence[int]) -> None:
    """Best-effort terminate of the (old) suite ancestors after relaunch.

    Only suite-looking processes are terminated so that a foreign ancestor
    (shell, explorer) is never touched. Called after relaunch succeeded, so
    even in the worst case the new suite is already spawning.
    """
    import psutil

    suite_markers = (
        "voice_flow.watchdog",
        "voice_flow.main",
        "voice_flow.gui.desktop_launcher",
        "voice_flow.lifecycle",
        "voiceflowlauncher.vbs",
    )
    for pid in ancestors:
        if not pid or pid == os.getpid():
            continue
        try:
            proc = psutil.Process(pid)
            try:
                cmd = " ".join(str(x) for x in proc.cmdline()).lower()
                name = proc.name().lower()
            except Exception:
                info = proc.info if isinstance(proc.info, dict) else {}
                cmd = " ".join(str(x) for x in info.get("cmdline") or []).lower()
                name = str(info.get("name") or "").lower()
            if not any(marker in cmd for marker in suite_markers):
                _debug_log(f"Skipping non-suite ancestor pid={pid} ({name})")
                continue
            if "python" not in name and "wscript" not in name and "cscript" not in name:
                continue
            proc.terminate()
            _debug_log(f"Terminated suite ancestor pid={pid} after relaunch")
        except Exception as e:
            _debug_log(f"Could not terminate ancestor pid={pid}: {e}")


def _get_python_exe() -> str:
    """Return windowless pythonw.exe to ensure zero console window popup."""
    try:
        from voice_flow.watchdog import get_pythonw_executable
        return get_pythonw_executable()
    except Exception:
        pass

    if sys.executable:
        exe = sys.executable
        if not exe.lower().endswith("pythonw.exe"):
            cand = exe[:-4] + "w.exe"
            if os.path.isfile(cand):
                return cand
        elif os.path.isfile(exe):
            return exe

    return "pythonw.exe"


def terminate_suite_processes(
    exclude_pids: Sequence[int] | None = None,
    timeout: float = 2.5,
) -> list[int]:
    """Find and terminate all running Voice Flow suite processes on the system."""
    import psutil

    current_pid = os.getpid()
    exclude_set = set(exclude_pids or [])
    exclude_set.add(current_pid)

    # Exclude the entire ancestor chain: the sequencer is a child of the API
    # server inside the suite tree, and terminating an ancestor mid-sweep has
    # been observed to kill the sequencer itself (restart then stalls after
    # 'Wrote watchdog_shutdown.flag' with the app fully down). Ancestors are
    # terminated explicitly in _terminate_ancestors AFTER the relaunch.
    ancestors = _ancestor_pids()
    exclude_set.update(ancestors)

    def is_lifecycle_worker(proc: psutil.Process) -> bool:
        try:
            pid = getattr(proc, "pid", None)
            if pid is not None and (pid == current_pid or pid in exclude_set):
                return True
            cmd = ""
            if hasattr(proc, "info") and isinstance(proc.info, dict):
                cmd_list = proc.info.get("cmdline") or []
                if isinstance(cmd_list, list):
                    cmd = " ".join(str(x) for x in cmd_list)
            if not cmd and callable(getattr(proc, "cmdline", None)):
                res = proc.cmdline()
                if isinstance(res, list):
                    cmd = " ".join(str(x) for x in res)
            cmd_norm = cmd.lower().replace("\\", ".").replace("/", ".")
            if "voice_flow.lifecycle" in cmd_norm:
                return True
        except Exception:
            pass
        return False

    term_log_path = data_dir() / "terminate_debug.log"
    def _tlog(msg: str) -> None:
        try:
            with open(term_log_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
        except Exception:
            pass

    _tlog(f"terminate_suite_processes started (current_pid={current_pid}, ancestors_excluded={ancestors})")

    # Close any open application windows cleanly first
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            for title in ("AI Productivity Flow", "Voice Flow", "Voice Flow - AI Speech Desktop App"):
                hwnd = user32.FindWindowW(None, title)
                if hwnd and user32.IsWindow(hwnd):
                    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        except Exception:
            pass

    suite_markers = (
        "voice_flow.watchdog",
        "voice_flow.main",
        "voice_flow.gui.desktop_launcher",
        "voiceflowlauncher.vbs",
    )

    targets: list[psutil.Process] = []

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = proc.info.get("pid")
            if not pid or pid in exclude_set or pid == current_pid:
                continue

            if is_lifecycle_worker(proc):
                continue

            cmdline_list = proc.info.get("cmdline") or []
            cmdline_str = " ".join(cmdline_list).lower()
            cmdline_normalized = cmdline_str.replace("\\", ".").replace("/", ".")
            name_str = (proc.info.get("name") or "").lower()

            if "pytest" in cmdline_str or "pytest" in name_str:
                continue

            if any(marker in cmdline_str or marker in cmdline_normalized for marker in suite_markers):
                # Ensure we only terminate python/wscript processes
                if "python" in name_str or "wscript" in name_str or "cscript" in name_str:
                    targets.append(proc)
                    _tlog(f"Matched marker target: pid={pid}, name={name_str}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Also collect and terminate any processes listening on port 8991
    try:
        from voice_flow.runtime_guard import listener_pids
        for lpid in listener_pids("127.0.0.1", 8991):
            if lpid not in exclude_set and lpid != current_pid:
                try:
                    lp = psutil.Process(lpid)
                    if not is_lifecycle_worker(lp):
                        targets.append(lp)
                        _tlog(f"Matched listener 8991 target: pid={lpid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except Exception:
        pass

    # Collect all child processes recursively (WebView2 renderers, workers)
    all_targets_dict: dict[int, psutil.Process] = {}
    for proc in targets:
        all_targets_dict[proc.pid] = proc
        try:
            for child in proc.children(recursive=True):
                if not is_lifecycle_worker(child):
                    all_targets_dict[child.pid] = child
                    _tlog(f"Matched child target: pid={child.pid} of parent={proc.pid}")
                else:
                    _tlog(f"Skipping lifecycle worker child: pid={child.pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    all_targets = list(all_targets_dict.values())
    terminated_pids: list[int] = []

    _tlog(f"All targets to terminate: {[p.pid for p in all_targets]}")

    # Send terminate first. Each termination is isolated: one failing or
    # misbehaving target must never abort the sweep (the sequencer MUST
    # always reach relaunch_suite below).
    for proc in all_targets:
        try:
            _tlog(f"Terminating pid={proc.pid}...")
            proc.terminate()
            terminated_pids.append(proc.pid)
            _tlog(f"Terminated pid={proc.pid} OK")
        except Exception as e:
            _tlog(f"Could not terminate pid={getattr(proc, 'pid', '?')}: {e}")

    _tlog("Waiting for targets to exit...")
    # Wait for processes to exit
    if all_targets:
        try:
            _, alive = psutil.wait_procs(all_targets, timeout=timeout)
        except Exception as e:
            _tlog(f"wait_procs failed (continuing): {e}")
            alive = []
        _tlog(f"Alive after timeout: {[p.pid for p in alive]}")
        for proc in alive:
            try:
                proc.kill()
                _tlog(f"Killed pid={proc.pid}")
            except Exception:
                pass

    _tlog(f"terminate_suite_processes finished successfully. Result: {sorted(set(terminated_pids))}")
    return sorted(set(terminated_pids))


def clean_runtime_artifacts() -> None:
    """Clear lock files and flags before relaunching."""
    d = data_dir()
    for fname in ("watchdog.lock", "watchdog_shutdown.flag"):
        try:
            (d / fname).unlink(missing_ok=True)
        except Exception:
            pass


def _clear_shutdown_flag_safety_net(reason: str) -> None:
    """Safety net: once a relaunch has been spawned, the shutdown flag must go.

    A stalled/crashed restart sequencer must never leave watchdog_shutdown.flag
    behind blocking watchdog recovery with the app fully down. The fresh suite's
    watchdog also clears the flag on boot; this makes the invariant immediate.
    """
    try:
        flag = data_dir() / WATCHDOG_FLAG_FILENAME
        if flag.exists():
            flag.unlink(missing_ok=True)
            _debug_log(f"Safety net removed watchdog_shutdown.flag ({reason})")
    except Exception:
        pass


def relaunch_suite() -> bool:
    """Relaunch the entire AI Productivity Flow suite (launcher -> watchdog -> main -> overlay -> window)."""
    from voice_flow.installer import get_vbs_launcher_path
    from voice_flow.watchdog import get_pythonw_env, get_silent_windows_spawn_kwargs

    vbs_path = get_vbs_launcher_path()
    wscript_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")

    src_dir = str(_get_src_dir())
    env = get_pythonw_env()
    spawn_kwargs = get_silent_windows_spawn_kwargs()
    if sys.platform == "win32":
        flags = spawn_kwargs.get("creationflags", 0)
        spawn_kwargs["creationflags"] = (
            flags
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )

    # Prefer VBS launcher if it exists, as it natively hides console on Windows
    if vbs_path.is_file() and os.path.isfile(wscript_path):
        try:
            subprocess.Popen(
                [wscript_path, str(vbs_path)],
                cwd=src_dir,
                env=env,
                close_fds=True,
                **spawn_kwargs,
            )
            _clear_shutdown_flag_safety_net("after vbs relaunch")
            return True
        except Exception as exc:
            _debug_log(f"VBS relaunch failed, falling back to pythonw: {exc}")

    # 3. Direct silent pythonw fallback
    python_exe = _get_python_exe()
    try:
        subprocess.Popen(
            [python_exe, "-m", "voice_flow.gui.desktop_launcher"],
            cwd=src_dir,
            env=env,
            close_fds=True,
            **spawn_kwargs,
        )
        _clear_shutdown_flag_safety_net("after pythonw relaunch")
        return True
    except Exception as exc:
        _debug_log(f"pythonw relaunch failed: {exc}")
        return False


def execute_restart_sequence(delay_seconds: float = 0.8) -> None:
    """Execute the full sequence: pause, signal shutdown, terminate, clean, reclaim port, and relaunch.

    Crash-proof contract:
    - Every step is individually fault-isolated and its outcome logged.
    - relaunch_suite() is attempted in a ``finally`` block no matter what
      happened earlier (a failed terminate/clean/prepare step can never leave
      the app fully down).
    - watchdog_shutdown.flag is removed in ``finally`` AND by the relaunch
      safety net, so a stalled sequence can never keep blocking watchdog
      recovery.
    - The suite ancestor chain is excluded from the terminate sweep (it killed
      the sequencer itself in the past) and terminated only after the relaunch
      is secured.
    """
    _log = _debug_log

    _log(f"Started execute_restart_sequence (pid={os.getpid()})")

    # We ARE the restart sequence: take over the restart lock unconditionally
    # (our spawner may still nominally own it).
    try:
        lock = _restart_lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass
        with open(lock, "x", encoding="utf-8") as f:
            f.write(f"{os.getpid()} {time.time()}")
    except Exception as e:
        _log(f"Could not write restart lock (continuing): {e}")

    relaunch_attempted = False
    relaunch_result: bool | None = None
    ancestors: list[int] = []

    try:
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        ancestors = _ancestor_pids()
        _log(f"Ancestor chain excluded from terminate sweep: {ancestors}")

        # Step 1: signal the watchdog to not respawn processes during termination
        try:
            shutdown_flag = data_dir() / WATCHDOG_FLAG_FILENAME
            shutdown_flag.parent.mkdir(parents=True, exist_ok=True)
            shutdown_flag.write_text(f"restart at {time.time()}", encoding="utf-8")
            _log("step=write_shutdown_flag outcome=ok")
        except Exception as e:
            _log(f"step=write_shutdown_flag outcome=error error={e}")

        # Step 2: terminate suite processes (our whole ancestor chain excluded)
        try:
            termed = terminate_suite_processes(exclude_pids=list(ancestors))
            _log(f"step=terminate_suite_processes outcome=ok terminated={termed}")
        except Exception as e:
            _log(f"step=terminate_suite_processes outcome=error error={e}")

        # Step 3: clean locks and flags
        try:
            clean_runtime_artifacts()
            _log("step=clean_runtime_artifacts outcome=ok")
        except Exception as e:
            _log(f"step=clean_runtime_artifacts outcome=error error={e}")

        # Step 4: reclaim port 8991 (non-fatal by design; the relaunched
        # suite's watchdog re-runs port reclamation at spawn time anyway)
        try:
            from voice_flow.runtime_guard import prepare_runtime_port
            prepare_runtime_port(port=8991)
            _log("step=prepare_runtime_port outcome=ok")
        except Exception as e:
            _log(f"step=prepare_runtime_port outcome=error error={e}")

        # Small settle pause
        time.sleep(0.5)
    except Exception as e:
        # Anything unexpected above must never prevent the relaunch below.
        _log(f"Unexpected error before relaunch (continuing to relaunch): {e}")
    finally:
        # Step 5: relaunch the suite fresh — guaranteed exactly one attempt.
        if not relaunch_attempted:
            relaunch_attempted = True
            try:
                relaunch_result = relaunch_suite()
                _log(f"step=relaunch_suite outcome=ok result={relaunch_result}")
                if not relaunch_result:
                    # One retry: a transient spawn failure must not leave the app down.
                    time.sleep(1.0)
                    relaunch_result = relaunch_suite()
                    _log(f"step=relaunch_suite_retry outcome=ok result={relaunch_result}")
            except Exception as e:
                _log(f"step=relaunch_suite outcome=error error={e}")
                try:
                    relaunch_result = relaunch_suite()
                    _log(f"step=relaunch_suite_retry outcome=ok result={relaunch_result}")
                except Exception as e2:
                    _log(f"step=relaunch_suite_retry outcome=error error={e2}")

        # Step 6: guarantee the shutdown flag is gone, no matter what.
        try:
            (data_dir() / WATCHDOG_FLAG_FILENAME).unlink(missing_ok=True)
            _log("step=remove_shutdown_flag outcome=ok")
        except Exception as e:
            _log(f"step=remove_shutdown_flag outcome=error error={e}")

        # Step 7: only now terminate the old suite ancestors (relaunch already
        # secured). Only suite-looking processes are touched.
        try:
            _terminate_ancestors(ancestors)
        except Exception as e:
            _log(f"step=terminate_ancestors outcome=error error={e}")

        # Step 8: release the restart lock so future restarts are allowed.
        release_restart_lock()
        _log(f"Finished execute_restart_sequence (relaunch_result={relaunch_result})")


def restart_suite(runtime_controller: object | None = None) -> bool:
    """Trigger an asynchronous, detached deep restart of the entire Voice Flow suite."""
    # 1. Reset floating overlay position if active
    if runtime_controller is not None:
        try:
            overlay = getattr(runtime_controller, "overlay", None)
            if overlay and hasattr(overlay, "reset_position"):
                overlay.reset_position()
        except Exception:
            pass

        try:
            audio = getattr(runtime_controller, "audio", None)
            if audio and hasattr(audio, "stop"):
                audio.stop()
        except Exception:
            pass

    # 2. Refuse a second restart while one is already in flight: a concurrent
    # sequence would terminate the suite the first sequence just relaunched
    # (observed as: window opens, then closes ~9s later).
    if not try_acquire_restart_lock():
        return False

    # 3. Spawn a detached background restart worker
    from voice_flow.watchdog import get_pythonw_executable, get_pythonw_env, get_silent_windows_spawn_kwargs

    python_exe = get_pythonw_executable()
    src_dir = str(_get_src_dir())
    env = get_pythonw_env()
    spawn_kwargs = get_silent_windows_spawn_kwargs()
    if sys.platform == "win32":
        flags = spawn_kwargs.get("creationflags", 0)
        # CREATE_BREAKAWAY_FROM_JOB detaches the sequencer from any job object
        # the suite was started under, so a job-wide kill cascade cannot take
        # the sequencer down mid-sequence. DETACHED_PROCESS + a new process
        # group shield it from console events as well.
        spawn_kwargs["creationflags"] = (
            flags
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
        )

    try:
        try:
            subprocess.Popen(
                [python_exe, "-m", "voice_flow.lifecycle", "--execute-restart"],
                cwd=src_dir,
                env=env,
                close_fds=True,
                **spawn_kwargs,
            )
            return True
        except Exception:
            # Breakaway is refused by jobs that forbid it; retry without it.
            if sys.platform == "win32":
                spawn_kwargs["creationflags"] = (
                    spawn_kwargs["creationflags"]
                    & ~getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
                )
            subprocess.Popen(
                [python_exe, "-m", "voice_flow.lifecycle", "--execute-restart"],
                cwd=src_dir,
                env=env,
                close_fds=True,
                **spawn_kwargs,
            )
            return True
    except Exception as exc:
        print(f"[ERROR] Could not spawn restart worker: {exc}")
        release_restart_lock()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Flow Suite Lifecycle Manager")
    parser.add_argument("--execute-restart", action="store_true", help="Execute deep restart sequence")
    parser.add_argument("--relaunch", action="store_true", help="Relaunch suite directly")
    args = parser.parse_args()

    if args.execute_restart:
        execute_restart_sequence(delay_seconds=0.8)
    elif args.relaunch:
        relaunch_suite()


if __name__ == "__main__":
    main()
