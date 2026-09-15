"""Voice Flow Background Watchdog and Auto-Recovery Supervisor.

Runs silently in the background (zero console window popup) to supervise Voice Flow.
Monitors the Voice Flow main engine process and REST API health, and automatically
restarts the application if it ever crashes or terminates unexpectedly.
"""

from __future__ import annotations

import argparse
import atexit
import collections
import ctypes
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

# Ensure stdout/stderr exist in pythonw.exe environment
if sys.stdout is None:
    class DummyWriter:
        encoding = "utf-8"
        errors = "replace"
        def write(self, x): pass
        def flush(self): pass
        def isatty(self): return False
    sys.stdout = DummyWriter()
    sys.stderr = DummyWriter()

# Hide console window on Windows immediately
if sys.platform == "win32":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd and "--show-console" not in sys.argv:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass

from voice_flow.paths import data_dir
from voice_flow.runtime_guard import runtime_is_engine_ready, prepare_runtime_port

# Configure Logging
log_file = data_dir() / "watchdog.log"
try:
    data_dir().mkdir(parents=True, exist_ok=True)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Watchdog] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("voice_flow.watchdog")

# A watchdog_shutdown.flag older than this is treated as the debris of a
# crashed/stalled restart sequencer rather than an active shutdown request:
# delete it and resume supervision instead of leaving the app down forever.
WATCHDOG_STALE_FLAG_SECONDS = 120.0


def get_src_dir() -> Path:
    """Find the src directory for Voice Flow across environments."""
    # 1. Check environment variable overrides (highest precedence)
    for env_var in ("AI_PRODUCTIVITY_FLOW_ROOT", "VOICE_FLOW_ROOT", "VOICE_FLOW_SRC"):
        val = os.environ.get(env_var, "").strip()
        if val:
            cand = Path(val).expanduser().resolve()
            if cand.name == "src" and (cand / "voice_flow").is_dir():
                return cand
            if (cand / "src" / "voice_flow").is_dir():
                return cand / "src"
            if (cand / "voice_flow").is_dir():
                return cand

    # 2. Direct package parent if running from source tree
    pkg_dir = Path(__file__).resolve().parent
    if pkg_dir.name == "voice_flow":
        candidate = pkg_dir.parent
        if (candidate / "voice_flow").is_dir():
            return candidate

    # 3. Current working directory / parent search
    cwd = Path.cwd()
    if (cwd / "src" / "voice_flow").is_dir():
        return cwd / "src"
    if (cwd / "voice_flow").is_dir():
        return cwd

    # 4. Known project workspace paths (.zcode, D:\Projects\voice-flow, and scratch workspaces)
    known_candidates = [
        Path(r"C:\Users\Asus\.zcode\workspace\default\AI-Productivity-Flow\src"),
        Path(r"D:\Projects\voice-flow\src"),
        Path(r"C:\Users\Asus\.gemini\antigravity\scratch\AI-Productivity-Flow\src"),
    ]
    for cand in known_candidates:
        if cand.is_dir() and (cand / "voice_flow").is_dir():
            return cand

    # 5. Check scratch directory dynamically
    scratch_dir = Path(r"C:\Users\Asus\.gemini\antigravity\scratch")
    if scratch_dir.is_dir():
        try:
            for sub in scratch_dir.iterdir():
                if sub.is_dir():
                    cand = sub / "src"
                    if cand.is_dir() and (cand / "voice_flow").is_dir():
                        return cand
        except Exception:
            pass

    return pkg_dir.parent


def _is_gui_binary(path: Path | str) -> bool:
    try:
        p = Path(path)
        if not p.is_file():
            return False
        import struct
        with open(p, "rb") as f:
            f.seek(0x3C)
            pe_offset = struct.unpack("<I", f.read(4))[0]
            f.seek(pe_offset + 0x5C)
            subsystem = struct.unpack("<H", f.read(2))[0]
            return subsystem == 2
    except Exception:
        return False


def get_pythonw_executable() -> str:
    """Find the best silent pythonw.exe binary available on the system."""
    project_root = get_src_dir().parent

    # 1. Check virtualenv pyvenv.cfg for the base CPython installation
    # Virtualenvs created by uv use a console trampoline for .venv\Scripts\pythonw.exe.
    # The genuine GUI pythonw.exe lives in the base Python home directory defined in pyvenv.cfg.
    venv_cfg = project_root / ".venv" / "pyvenv.cfg"
    if venv_cfg.is_file():
        try:
            for line in venv_cfg.read_text(encoding="utf-8").splitlines():
                if line.startswith("home") and "=" in line:
                    home_dir = Path(line.split("=", 1)[1].strip())
                    home_pyw = home_dir / "pythonw.exe"
                    if home_pyw.is_file() and _is_gui_binary(home_pyw):
                        return str(home_pyw)
        except Exception:
            pass

    # 2. Check runtime_env if installed package
    try:
        from voice_flow import runtime_env

        installed_pyw = runtime_env.pythonw_executable()
        if installed_pyw and Path(installed_pyw).is_file():
            return installed_pyw
    except Exception:
        pass

    # 3. Sibling pythonw.exe next to current sys.executable
    if sys.executable:
        current_dir_pyw = Path(sys.executable).parent / "pythonw.exe"
        if current_dir_pyw.is_file() and _is_gui_binary(current_dir_pyw):
            return str(current_dir_pyw)

    # 4. Check scratch subdirectories for .venv with pyvenv.cfg
    scratch_dir = Path(r"C:\Users\Asus\.gemini\antigravity\scratch")
    if scratch_dir.is_dir():
        try:
            for sub in scratch_dir.iterdir():
                cfg = sub / ".venv" / "pyvenv.cfg"
                if cfg.is_file():
                    for line in cfg.read_text(encoding="utf-8").splitlines():
                        if line.startswith("home") and "=" in line:
                            home_dir = Path(line.split("=", 1)[1].strip())
                            home_pyw = home_dir / "pythonw.exe"
                            if home_pyw.is_file() and _is_gui_binary(home_pyw):
                                return str(home_pyw)
        except Exception:
            pass

    # 5. Virtual environment relative to source tree root
    venv_pyw = project_root / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pyw.is_file() and _is_gui_binary(venv_pyw):
        return str(venv_pyw)

    # 6. sys.prefix virtualenv / conda Scripts
    prefix_pyw = Path(sys.prefix) / "Scripts" / "pythonw.exe"
    if prefix_pyw.is_file() and _is_gui_binary(prefix_pyw):
        return str(prefix_pyw)

    # 7. Standard Windows Python installations
    python_system_paths = [
        Path(r"C:\Python314\pythonw.exe"),
        Path(r"C:\Python313\pythonw.exe"),
        Path(r"C:\Python312\pythonw.exe"),
        Path(r"C:\Python311\pythonw.exe"),
        Path(r"C:\Python310\pythonw.exe"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        python_system_paths.extend([
            Path(local_app_data) / "Programs" / "Python" / "Python314" / "pythonw.exe",
            Path(local_app_data) / "Programs" / "Python" / "Python313" / "pythonw.exe",
            Path(local_app_data) / "Programs" / "Python" / "Python312" / "pythonw.exe",
            Path(local_app_data) / "Programs" / "Python" / "Python311" / "pythonw.exe",
        ])

    for cand in python_system_paths:
        if cand.is_file() and _is_gui_binary(cand):
            return str(cand)

    # 8. Check PATH via shutil.which
    which_pyw = shutil.which("pythonw.exe") or shutil.which("pythonw")
    if which_pyw and _is_gui_binary(which_pyw):
        return which_pyw

    # 9. Fallback to venv_pyw if it exists
    if venv_pyw.is_file():
        return str(venv_pyw)

    # 10. Fallback to sibling pythonw.exe
    if sys.executable:
        current_dir_pyw = Path(sys.executable).parent / "pythonw.exe"
        if current_dir_pyw.is_file():
            return str(current_dir_pyw)

    # 11. Generic fallback
    if sys.platform != "win32":
        return sys.executable or "python3"
    return "pythonw.exe"


def get_pythonw_env(extra_env: dict | None = None) -> dict:
    """Prepare environment dictionary with venv context and PYTHONPATH."""
    src_dir = str(get_src_dir())
    project_root = get_src_dir().parent
    venv_dir = project_root / ".venv"

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    venv_site = venv_dir / "Lib" / "site-packages"
    if venv_site.is_dir():
        site_str = str(venv_site)
        if "PYTHONPATH" in env and env["PYTHONPATH"]:
            if site_str not in env["PYTHONPATH"]:
                env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{site_str}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{site_str}"
    elif "PYTHONPATH" in env and env["PYTHONPATH"]:
        env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_dir

    if venv_dir.is_dir():
        env["VIRTUAL_ENV"] = str(venv_dir)
        launcher_cand = venv_dir / "Scripts" / "pythonw.exe"
        if not launcher_cand.is_file():
            launcher_cand = venv_dir / "Scripts" / "python.exe"
        env["__PYVENV_LAUNCHER__"] = str(launcher_cand)
        venv_scripts = str(venv_dir / "Scripts")
        if "PATH" in env:
            env["PATH"] = f"{venv_scripts}{os.pathsep}{env['PATH']}"
        else:
            env["PATH"] = venv_scripts

    return env


def get_silent_windows_spawn_kwargs() -> dict:
    """Return creationflags and startupinfo that guarantee zero console window popup on Windows."""
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        startupinfo.lpDesktop = r"WinSta0\Default"
        kwargs["startupinfo"] = startupinfo
    return kwargs


class WatchdogSupervisor:
    """Supervises Voice Flow process lifecycle with auto-recovery and crash backoff."""

    def __init__(
        self,
        poll_interval: float = 3.0,
        max_rapid_crashes: int = 5,
        crash_window_seconds: float = 60.0,
        startup_grace_seconds: float = 60.0,
    ) -> None:
        self.poll_interval = poll_interval
        self.max_rapid_crashes = max_rapid_crashes
        self.crash_window_seconds = crash_window_seconds
        # faster-whisper cold imports can take ~10s; probing REST health before
        # the engine finishes booting caused a permanent probe-kill crash-loop.
        self.startup_grace_seconds = startup_grace_seconds
        self.recent_crashes: collections.deque[float] = collections.deque()
        self.child_process: subprocess.Popen | None = None
        self.child_pid: int | None = None
        self.running = False
        self._grace_until = 0.0
        self._lock_file = data_dir() / "watchdog.lock"
        self._shutdown_flag = data_dir() / "watchdog_shutdown.flag"
        atexit.register(self.release_lock)

    def acquire_lock(self) -> bool:
        """Ensure only one watchdog instance runs globally."""
        self._lock_file = data_dir() / "watchdog.lock"
        self._shutdown_flag = data_dir() / "watchdog_shutdown.flag"
        try:
            self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        if self._lock_file.exists():
            try:
                content = self._lock_file.read_text(encoding="utf-8").strip()
                if content:
                    old_pid = int(content)
                    if old_pid == os.getpid():
                        return True
                    if self._is_pid_alive(old_pid):
                        log.info("Another Watchdog supervisor is already running (PID %d). Exiting duplicate.", old_pid)
                        try:
                            self._ensure_gui_open()
                        except Exception as e:
                            log.debug("Error ensuring GUI open on duplicate launch: %s", e)
                        return False
                    else:
                        log.info("Removing stale watchdog lock file from defunct PID %d.", old_pid)
                        try:
                            self._lock_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                else:
                    try:
                        self._lock_file.unlink(missing_ok=True)
                    except Exception:
                        pass
            except Exception as e:
                log.debug("Error checking existing lock file: %s", e)
                try:
                    self._lock_file.unlink(missing_ok=True)
                except Exception:
                    pass

        try:
            self._lock_file.write_text(str(os.getpid()), encoding="utf-8")
            return True
        except Exception as e:
            log.warning("Could not write watchdog lock file: %s", e)
            return True

    _acquire_lock = acquire_lock

    def _ensure_gui_open(self) -> None:
        """Launch Desktop GUI window when shortcut is clicked while backend is active."""
        try:
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    hwnd = (
                        user32.FindWindowW(None, "AI Productivity Flow")
                        or user32.FindWindowW(None, "Voice Flow")
                    )
                    if hwnd and user32.IsWindow(hwnd):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                        user32.SetForegroundWindow(hwnd)
                        return
                except Exception:
                    pass

            pyw = get_pythonw_executable()
            src_dir = str(get_src_dir())
            env = get_pythonw_env()
            spawn_kwargs = get_silent_windows_spawn_kwargs()

            subprocess.Popen(
                [pyw, "-m", "voice_flow.gui.desktop_launcher"],
                cwd=src_dir,
                env=env,
                **spawn_kwargs,
            )
        except Exception as e:
            log.warning("Could not launch Desktop GUI from watchdog: %s", e)

    def release_lock(self) -> None:
        try:
            self._lock_file = data_dir() / "watchdog.lock"
            if self._lock_file.exists():
                content = self._lock_file.read_text(encoding="utf-8").strip()
                if content == str(os.getpid()):
                    self._lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    _release_lock = release_lock

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True

        try:
            import psutil
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    proc_name = proc.name().lower()
                    if "python" not in proc_name and "voice_flow" not in proc_name:
                        return False
                    try:
                        cmdline = " ".join(proc.cmdline()).lower()
                        if "voice_flow" in cmdline or "python" in proc_name:
                            return True
                        return False
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        return "python" in proc_name or "voice_flow" in proc_name
            return False
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
                if h_process:
                    exit_code = ctypes.c_ulong()
                    kernel32.GetExitCodeProcess(h_process, ctypes.byref(exit_code))
                    kernel32.CloseHandle(h_process)
                    STILL_ACTIVE = 259
                    return exit_code.value == STILL_ACTIVE
                return False
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def is_shutdown_requested(self) -> bool:
        self._shutdown_flag = data_dir() / "watchdog_shutdown.flag"
        return self._shutdown_flag.exists()

    def shutdown_flag_age(self) -> float:
        """Age of the shutdown flag in seconds (inf when absent/unreadable)."""
        try:
            flag = data_dir() / "watchdog_shutdown.flag"
            if not flag.exists():
                return float("inf")
            return max(0.0, time.time() - flag.stat().st_mtime)
        except Exception:
            return float("inf")

    def should_stop_for_shutdown(self) -> bool:
        """True only when an ACTIVE (non-stale) shutdown flag exists.

        Stale-flag recovery: a flag older than WATCHDOG_STALE_FLAG_SECONDS is
        debris from a restart sequencer that died before finishing (or a
        machine that slept mid-restart). Treat it as stale, delete it, and
        resume supervision so the app self-heals instead of staying down.
        """
        if not self.is_shutdown_requested():
            return False
        age = self.shutdown_flag_age()
        if age > WATCHDOG_STALE_FLAG_SECONDS:
            log.warning(
                "Shutdown flag is stale (%.0fs old > %.0fs); treating as abandoned restart, resuming supervision.",
                age,
                WATCHDOG_STALE_FLAG_SECONDS,
            )
            self.clear_shutdown_flag()
            return False
        return True

    def clear_shutdown_flag(self) -> None:
        try:
            self._shutdown_flag = data_dir() / "watchdog_shutdown.flag"
            if self._shutdown_flag.exists():
                self._shutdown_flag.unlink(missing_ok=True)
        except Exception:
            pass

    def request_shutdown(self) -> None:
        try:
            self._shutdown_flag = data_dir() / "watchdog_shutdown.flag"
            self._shutdown_flag.parent.mkdir(parents=True, exist_ok=True)
            self._shutdown_flag.write_text(f"shutdown requested at {time.time()}", encoding="utf-8")
        except Exception:
            pass

    def spawn_voice_flow(self) -> bool:
        """Launch Voice Flow silently using pythonw.exe."""
        pythonw = get_pythonw_executable()
        src_dir = str(get_src_dir())

        # Port reclamation: ensure port 8991 is not held by a dead or incompatible process
        try:
            port_result = prepare_runtime_port(port=8991, require_engine=True)
            if port_result.status == "reclaimed":
                log.info("Reclaimed port 8991 from stale listener(s): %s", port_result.terminated_pids)
            elif port_result.status == "occupied":
                log.warning("Port 8991 is currently occupied by a foreign process; attempting spawn anyway.")
        except Exception as e:
            log.debug("Port preparation check before spawn: %s", e)

        log.info("Spawning Voice Flow engine silently: %s -m voice_flow.main (cwd=%s)", pythonw, src_dir)
        try:
            env = get_pythonw_env()
            spawn_kwargs = get_silent_windows_spawn_kwargs()

            self.child_process = subprocess.Popen(
                [pythonw, "-m", "voice_flow.main"],
                cwd=src_dir,
                env=env,
                **spawn_kwargs,
            )
            self.child_pid = self.child_process.pid
            log.info("Voice Flow started with PID %d", self.child_process.pid)
            # Grant a startup grace window before health probing resumes so a
            # slow cold import is never mistaken for a dead engine, and clear
            # any strikes recorded against the previous (replaced) process.
            self._grace_until = time.time() + self.startup_grace_seconds
            return True
        except Exception as e:
            log.error("Failed to spawn Voice Flow: %s", e, exc_info=True)
            return False

    _spawn_voice_flow = spawn_voice_flow

    def record_crash(self) -> float:
        """Record a crash timestamp and calculate required throttle backoff."""
        now = time.time()
        self.recent_crashes.append(now)

        # Purge crashes outside window
        while self.recent_crashes and (now - self.recent_crashes[0] > self.crash_window_seconds):
            self.recent_crashes.popleft()

        crash_count = len(self.recent_crashes)
        if crash_count > self.max_rapid_crashes:
            backoff = min(30.0, 2.0 ** (crash_count - self.max_rapid_crashes))
            log.warning(
                "Excessive crash rate detected (%d crashes in %.0fs). Backing off for %.1fs before restarting...",
                crash_count,
                self.crash_window_seconds,
                backoff,
            )
            return backoff
        return 0.5

    def check_health(self) -> bool:
        """Check if Voice Flow process and/or REST API is healthy."""
        if self.child_process is not None:
            ret = self.child_process.poll()
            if ret is not None:
                log.warning("Supervised Voice Flow process (PID %s) terminated with code %s.", self.child_pid or self.child_process.pid, ret)
                self.child_process = None
                return False
            return True

        # During the startup grace window a fresh spawn must never be probe-
        # killed for a not-yet-responding REST port (cold imports take ~10s).
        if time.time() < self._grace_until:
            return True

        # A standalone desktop launcher can serve the API contract but cannot
        # capture audio. Adopt only a runtime with a registered engine.
        if runtime_is_engine_ready(port=8991, timeout=0.5):
            return True

        return False

    def run(self) -> None:
        """Main supervision loop."""
        if not self.acquire_lock():
            return

        self.clear_shutdown_flag()
        self.running = True
        log.info("Voice Flow Watchdog supervisor active (polling every %.1fs)", self.poll_interval)

        try:
            # Initial check: if Voice Flow is not already active, launch it immediately
            if not self.check_health():
                log.info("Voice Flow is not running. Starting initial instance...")
                self.spawn_voice_flow()

            while self.running:
                time.sleep(self.poll_interval)

                if self.should_stop_for_shutdown():
                    log.info("Shutdown requested. Watchdog stopping cleanly.")
                    # --stop must also stop the engine, or it keeps port 8991
                    # busy and every future spawn fails on the engine mutex.
                    child = getattr(self, "child_process", None)
                    if child is not None and child.poll() is None:
                        try:
                            child.terminate()
                            child.wait(timeout=10)
                        except Exception:
                            pass
                    break

                if not self.check_health():
                    if self.should_stop_for_shutdown():
                        break

                    backoff = self.record_crash()
                    if backoff > 0:
                        time.sleep(backoff)

                    if self.should_stop_for_shutdown():
                        break

                    log.info("[AUTO-RECOVERY] Restarting Voice Flow after unexpected termination...")
                    self.spawn_voice_flow()

        except KeyboardInterrupt:
            log.info("Watchdog interrupted by user.")
        except Exception as exc:
            log.error("Watchdog supervisor loop exception: %s", exc, exc_info=True)
        finally:
            self.running = False
            self.release_lock()
            log.info("Watchdog supervisor terminated.")

    def stop(self) -> None:
        """Signal watchdog to stop supervision and exit."""
        self.request_shutdown()
        self.running = False
        if self.child_process and self.child_process.poll() is None:
            try:
                self.child_process.terminate()
                self.child_process.wait(timeout=3.0)
            except Exception:
                try:
                    self.child_process.kill()
                except Exception:
                    pass
        self.release_lock()


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Flow Watchdog & Auto-Recovery Supervisor")
    parser.add_argument("--status", action="store_true", help="Check watchdog and Voice Flow health status")
    parser.add_argument("--stop", action="store_true", help="Stop watchdog and running Voice Flow instance")
    parser.add_argument("--show-console", action="store_true", help="Do not hide console window")
    args = parser.parse_args()

    supervisor = WatchdogSupervisor()

    if args.status:
        is_running = runtime_is_engine_ready(port=8991, timeout=0.5)
        lock_file = data_dir() / "watchdog.lock"
        watchdog_pid = lock_file.read_text(encoding="utf-8").strip() if lock_file.exists() else "Not running"
        print(f"Voice Flow Backend (Port 8991): {'HEALTHY / RUNNING' if is_running else 'STOPPED'}")
        print(f"Watchdog Status: PID {watchdog_pid}")
        return

    if args.stop:
        supervisor.stop()
        print("[OK] Shutdown signal sent to Voice Flow Watchdog.")
        return

    supervisor.run()


if __name__ == "__main__":
    main()
