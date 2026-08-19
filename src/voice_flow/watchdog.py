"""Voice Flow Background Watchdog and Auto-Recovery Supervisor.

Runs silently in the background (zero console window popup) to supervise Voice Flow.
Monitors the Voice Flow main engine process and REST API health, and automatically
restarts the application if it ever crashes or terminates unexpectedly.
"""

from __future__ import annotations

import argparse
import collections
import ctypes
import json
import logging
import os
from pathlib import Path
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
from voice_flow.runtime_guard import runtime_is_compatible

# Configure Logging
log_file = data_dir() / "watchdog.log"
data_dir().mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Watchdog] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("voice_flow.watchdog")


def get_pythonw_executable() -> str:
    """Find the best silent pythonw.exe binary available on the system."""
    project_root = Path(__file__).resolve().parent.parent.parent
    venv_pyw = project_root / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pyw.exists():
        return str(venv_pyw)

    current_dir_pyw = Path(sys.executable).parent / "pythonw.exe"
    if current_dir_pyw.exists():
        return str(current_dir_pyw)

    c_python314 = Path(r"C:\Python314\pythonw.exe")
    if c_python314.exists():
        return str(c_python314)

    return "pythonw.exe"


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
        self.startup_grace_seconds = startup_grace_seconds
        self.recent_crashes: collections.deque[float] = collections.deque()
        self.child_process: subprocess.Popen | None = None
        self.running = False
        self._unhealthy_strikes = 0
        self._child_started_at: float | None = None
        self._lock_file = data_dir() / "watchdog.lock"
        self._shutdown_flag = data_dir() / "watchdog_shutdown.flag"

    def acquire_lock(self) -> bool:
        """Ensure only one watchdog instance runs globally."""
        if self._lock_file.exists():
            try:
                content = self._lock_file.read_text(encoding="utf-8").strip()
                if content:
                    old_pid = int(content)
                    if old_pid != os.getpid() and self._is_pid_alive(old_pid):
                        log.info("Another Watchdog is already running (PID %d). Opening Desktop GUI and exiting.", old_pid)
                        self._ensure_gui_open()
                        return False
            except Exception:
                pass

        try:
            self._lock_file.write_text(str(os.getpid()), encoding="utf-8")
            return True
        except Exception as e:
            log.warning("Could not write watchdog lock file: %s", e)
            return True

    def _ensure_gui_open(self) -> None:
        """Launch Desktop GUI window when shortcut is clicked while backend is active."""
        try:
            pyw = get_pythonw_executable()
            src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            subprocess.Popen(
                [pyw, "-m", "voice_flow.gui.desktop_launcher"],
                cwd=src_dir,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0,
            )
        except Exception as e:
            log.warning("Could not launch Desktop GUI from watchdog: %s", e)

    def release_lock(self) -> None:
        try:
            if self._lock_file.exists():
                content = self._lock_file.read_text(encoding="utf-8").strip()
                if content == str(os.getpid()):
                    self._lock_file.unlink()
        except Exception:
            pass

    def _is_pid_alive(self, pid: int) -> bool:
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
        return self._shutdown_flag.exists()

    def clear_shutdown_flag(self) -> None:
        try:
            if self._shutdown_flag.exists():
                self._shutdown_flag.unlink()
        except Exception:
            pass

    def request_shutdown(self) -> None:
        try:
            self._shutdown_flag.write_text(f"shutdown requested at {time.time()}", encoding="utf-8")
        except Exception:
            pass

    def spawn_voice_flow(self) -> bool:
        """Launch Voice Flow silently using pythonw.exe."""
        pythonw = get_pythonw_executable()
        src_dir = str(Path(__file__).resolve().parent.parent)

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        log.info("Spawning Voice Flow engine silently: %s -m voice_flow.main (cwd=%s)", pythonw, src_dir)
        try:
            self.child_process = subprocess.Popen(
                [pythonw, "-m", "voice_flow.main"],
                cwd=src_dir,
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
            log.info("Voice Flow started with PID %d", self.child_process.pid)
            # A fresh process needs cold-start time (imports alone take ~10s)
            # before the API port can bind; also clear strikes left over from a
            # previous process so it is never killed on its first probe.
            self._child_started_at = time.time()
            self._unhealthy_strikes = 0
            return True
        except Exception as e:
            log.error("Failed to spawn Voice Flow: %s", e, exc_info=True)
            return False

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
                log.warning("Supervised Voice Flow process (PID %d) terminated with code %s.", self.child_process.pid, ret)
                self.child_process = None
                return False
            # The process is alive, but a main thread deadlock (Tk/COM) would
            # leave it hung forever. Require the REST API to answer; two
            # consecutive probe failures count as unhealthy.
            if self._child_started_at is not None and time.time() - self._child_started_at < self.startup_grace_seconds:
                return True
            if runtime_is_compatible(port=8991, timeout=0.5):
                self._unhealthy_strikes = 0
                return True
            self._unhealthy_strikes += 1
            if self._unhealthy_strikes >= 2:
                log.warning("Supervised Voice Flow process (PID %d) is alive but not responding on port 8991; killing it.", self.child_process.pid)
                try:
                    self.child_process.kill()
                except Exception:
                    pass
                self.child_process = None
                return False
            return True

        # If child_process is not directly tracked, check if a compatible Voice Flow runtime is responding on port 8991
        if runtime_is_compatible(port=8991, timeout=0.5):
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

                if self.is_shutdown_requested():
                    log.info("Shutdown requested. Watchdog stopping cleanly.")
                    break

                if not self.check_health():
                    if self.is_shutdown_requested():
                        break

                    backoff = self.record_crash()
                    crash_count = len(self.recent_crashes)
                    if crash_count >= self.max_rapid_crashes * 2:
                        # Circuit breaker: an engine that dies at startup (broken
                        # DB, import error, port conflict) would otherwise be
                        # respawned forever. Stop permanently and flag it.
                        log.critical(
                            "Giving up: %d crashes within %.0fs. Voice Flow is not restartable right now; "
                            "a manual start (desktop shortcut) will spawn a fresh watchdog.",
                            crash_count, self.crash_window_seconds,
                        )
                        try:
                            (data_dir() / "watchdog_gave_up.flag").write_text(
                                f"gave up at {time.time()} after {crash_count} crashes", encoding="utf-8"
                            )
                        except Exception:
                            pass
                        break

                    if backoff > 0:
                        time.sleep(backoff)

                    if self.is_shutdown_requested():
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
        is_running = runtime_is_compatible(port=8991, timeout=0.5)
        lock_file = data_dir() / "watchdog.lock"
        watchdog_pid = lock_file.read_text().strip() if lock_file.exists() else "Not running"
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
