"""Voice Flow Desktop App Launcher.
Launches local REST API server, system-wide floating overlay bar, and native Desktop UI window.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]
from pathlib import Path

# Ensure src and project root directories are in sys.path
_current_file = Path(__file__).resolve()
_src_dir = str(_current_file.parent.parent.parent)
_project_root = str(_current_file.parent.parent.parent.parent)

for _p in (_src_dir, _project_root):
    if _p and _p not in sys.path and os.path.exists(_p):
        sys.path.insert(0, _p)

# Ensure virtualenv site-packages are loaded even when invoked via base pythonw / python
_venv_site = Path(_project_root) / ".venv" / "Lib" / "site-packages"
if _venv_site.is_dir():
    try:
        import site
        site.addsitedir(str(_venv_site))
    except Exception:
        pass
if sys.platform != "win32":
    import glob
    for _ps in glob.glob(str(Path(_project_root) / ".venv" / "lib" / "python*" / "site-packages")):
        if os.path.isdir(_ps):
            try:
                import site
                site.addsitedir(_ps)
            except Exception:
                pass

# A direct `pythonw -m voice_flow.gui.desktop_launcher` still imports this
# module before the window. Paint the splash before WebView and the API stack.
if __name__ == "__main__" and not os.environ.get("VOICE_FLOW_EARLY_SPLASH_HWND"):
    try:
        from voice_flow.gui.early_splash import show_early_splash
        show_early_splash()
    except Exception:
        pass

# Ensure WebView2 allows audio autoplay without requiring initial user gesture
_wv2_args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
if "--autoplay-policy=no-user-gesture-required" not in _wv2_args:
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        f"{_wv2_args} --autoplay-policy=no-user-gesture-required".strip()
    )

from voice_flow.platform.macos_app import configure_macos_app
from voice_flow.paths import data_dir as _data_dir

# main imports this module for focus helpers; only the executable entry point
# owns the regular desktop role. Set its identity before webview can load Cocoa.
if __name__ == "__main__":
    configure_macos_app("desktop")

webview = None  # type: ignore[assignment]
_WEBVIEW_IMPORT_FAILED = False

def _should_import_webview() -> bool:
    """Keep headless CI imports light, except for the macOS native GUI smoke test."""
    return sys.platform == "darwin" or not os.environ.get("CI")


if _should_import_webview():
    try:
        import webview
    except Exception:  # missing desktop dependency falls back to browser launcher
        _WEBVIEW_IMPORT_FAILED = True
        import traceback
        try:
            crash_path = _data_dir() / "gui_crash.log"
            crash_path.parent.mkdir(parents=True, exist_ok=True)
            crash_path.write_text(
                "desktop_launcher optional import failure:\n" + traceback.format_exc(), encoding="utf-8"
            )
        except Exception:
            pass

# Hide console window on Windows immediately so the GUI runs silently
if sys.platform == "win32" and not os.environ.get("CI"):
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            if "--show-console" not in sys.argv:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
    except Exception:
        pass

if sys.stdout is None:
    class DummyWriter:
        encoding = "utf-8"
        errors = "replace"
        def write(self, x): pass
        def flush(self): pass
        def isatty(self): return False
    sys.stdout = DummyWriter()
    sys.stderr = DummyWriter()

_launcher_log_path = _data_dir() / "gui_launcher.log"

try:
    from voice_flow.crash_reporting import init_crash_reporting
    init_crash_reporting()
except Exception:
    pass


def _launcher_log(message: str) -> None:
    """Persist launcher diagnostics; stdout is None under pythonw so logs are
    the only way to see why a window did (or did not) open."""
    try:
        os.makedirs(os.path.dirname(_launcher_log_path), exist_ok=True)
        from datetime import datetime
        with open(_launcher_log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except Exception:
        pass


def _process_age_seconds() -> float | None:
    """Seconds since this process started (pythonw.exe launch), or None."""
    try:
        import psutil
        return max(0.0, time.time() - psutil.Process(os.getpid()).create_time())
    except Exception:
        return None


def _log_launch_phase(phase: str) -> None:
    """Timing line for gui_launcher.log: how long after the click each phase ran."""
    age = _process_age_seconds()
    _launcher_log(f"[timing] {phase} at {age:.1f}s after process start" if age is not None
                  else f"[timing] {phase}")


if _WEBVIEW_IMPORT_FAILED and sys.platform == "darwin":
    _launcher_log(
        "pywebview import failed; ensure pyobjc-core, pyobjc-framework-Cocoa, "
        "and pyobjc-framework-WebKit are installed."
    )


# Same value as voice_flow.gui.api_server.PORT (a test keeps them equal).
# The launcher does NOT import api_server at startup any more: that module
# pulls in scipy.signal, sounddevice/PortAudio, the Video Flow service and
# more (about 1.3 s of imports on a fast machine, many seconds on a cold
# low-end PC while Defender scans each new DLL). The engine process already
# loads all of that; the launcher only needs it for the rare in-process API
# fallback, so it is imported on demand there.
PORT = 8991
_API_IMPORT_ERROR = None


def start_api_server(*args, **kwargs):
    """In-process API fallback. Imports the API stack only when it is used."""
    global _API_IMPORT_ERROR
    try:
        from voice_flow.gui.api_server import start_api_server as _start_api_server
    except Exception as exc:  # broken/partial install must never die silently
        _API_IMPORT_ERROR = exc
        try:
            import traceback
            (_data_dir() / "gui_crash.log").write_text(
                "desktop_launcher import failure:\n" + traceback.format_exc(), encoding="utf-8"
            )
        except Exception:
            pass
        _launcher_log(f"api_server import failed: {exc}")
        return None
    return _start_api_server(*args, **kwargs)


try:
    from voice_flow.runtime_guard import runtime_is_compatible, runtime_is_engine_ready
except Exception as _import_exc:  # broken/partial install must never die silently
    import urllib.request as _urlreq

    def runtime_is_compatible(*, host: str = "127.0.0.1", port: int = PORT, timeout: float = 1.0) -> bool:
        try:
            _opener = _urlreq.build_opener(_urlreq.ProxyHandler({}))  # loopback: never via proxy
            with _opener.open(f"http://{host}:{port}/api/runtime", timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False

    # An API-only response cannot prove that dictation is available. If the
    # runtime guard itself could not be imported, fail closed and let startup
    # attempt the normal watchdog path.
    def runtime_is_engine_ready(*, host: str = "127.0.0.1", port: int = PORT, timeout: float = 1.0) -> bool:
        return False

    _launcher_log(f"runtime_guard import failed: {_import_exc}")


def _is_pid_alive(pid: int) -> bool:
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
                    return "voice_flow" in cmdline or "python" in proc_name
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    return "python" in proc_name or "voice_flow" in proc_name
        return False
    except Exception:
        pass


def _poke_overlay_show() -> None:
    """Bring the floating bar forward and redraw it without resetting active state."""
    for endpoint in ("/api/app/restore-and-refresh", "/api/overlay/show", "/api/overlay/refresh"):
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{PORT}{endpoint}",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            # Loopback: runtime_guard's import installed the no-proxy-for-loopback opener.
            with urllib.request.urlopen(req, timeout=1.0) as res:
                if res.status == 200:
                    _launcher_log(f"Sent {endpoint} to restore floating bar & refresh UI")
                    return
        except Exception as e:
            _launcher_log(f"{endpoint} ping error: {e}")


def _poke_keepalive_refresh() -> None:
    """Signal the background API server to run a silent NotebookLM session check/refresh."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/video-flow/notebooklm/keepalive/refresh",
            data=b'{"background": true, "force": false}',
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2.0):  # loopback: never proxied (local_http)
            pass
        _launcher_log("Sent /api/video-flow/notebooklm/keepalive/refresh on window open/focus")
    except Exception as e:
        _launcher_log(f"/api/video-flow/notebooklm/keepalive/refresh ping error: {e}")



def _mac_engine_lock_held() -> bool:
    """macOS: True while an engine process holds the per-user engine lock."""
    if sys.platform != "darwin":
        return False
    try:
        from voice_flow.platform.macos_lifecycle import ENGINE_LOCK_NAME, InstanceLock
        probe = InstanceLock(_data_dir() / ENGINE_LOCK_NAME)
        if probe.acquire():
            probe.release()
            return False
        return True
    except Exception:
        return False


def _is_backend_running() -> bool:
    """Check if Voice Flow watchdog or main engine is already running."""
    try:
        if is_engine_ready(timeout=0.1):
            return True
    except Exception:
        pass

    # The packaged Mac engine runs as the bundle executable, not "python", so
    # the process scan below cannot see it; its lock is the reliable signal.
    if _mac_engine_lock_held():
        return True

    try:
        from voice_flow.paths import data_dir
        lock_file = data_dir() / "watchdog.lock"
        if lock_file.exists():
            pid_str = lock_file.read_text(encoding="utf-8").strip()
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if pid != os.getpid() and _is_pid_alive(pid):
                    return True
    except Exception:
        pass

    try:
        import psutil
        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["pid"] == current_pid:
                    continue
                pname = (proc.info.get("name") or "").lower()
                if "python" in pname:
                    cmdline = " ".join(proc.cmdline() or []).lower()
                    if "voice_flow.watchdog" in cmdline or "voice_flow.main" in cmdline:
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    return False


def _get_pythonw_executable() -> str:
    """Find the best silent pythonw.exe binary available on the system."""
    try:
        from voice_flow import runtime_env
        installed_pyw = runtime_env.pythonw_executable()
        if installed_pyw:
            return installed_pyw
    except Exception:
        pass

    try:
        from voice_flow.watchdog import get_pythonw_executable
        return get_pythonw_executable()
    except Exception:
        pass

    project_root = Path(__file__).resolve().parent.parent.parent.parent
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


def ensure_backend_running() -> bool:
    """Ensure Voice Flow background supervisor / main engine is running silently."""
    if _is_backend_running():
        return False

    pythonw = _get_pythonw_executable()
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    from voice_flow.watchdog import get_pythonw_env, get_silent_windows_spawn_kwargs
    env = get_pythonw_env(extra_env={"VOICE_FLOW_GUI_STARTED": "1"})
    spawn_kwargs = get_silent_windows_spawn_kwargs()

    try:
        subprocess.Popen(
            [pythonw, "-m", "voice_flow.watchdog"],
            cwd=src_dir,
            env=env,
            close_fds=True,
            **spawn_kwargs,
        )
        _launcher_log("Started Voice Flow background supervisor (watchdog)")
        print("[GUI] Started Voice Flow background supervisor (watchdog).")
        return True
    except Exception as exc:
        _launcher_log(f"Could not start Voice Flow watchdog: {exc}")
        print(f"[GUI WARNING] Could not start Voice Flow watchdog: {exc}")
        # Direct fallback to voice_flow.main
        try:
            from voice_flow.startup_priority import engine_startup_creationflags
            extra_flags = engine_startup_creationflags()
            if extra_flags:
                spawn_kwargs = dict(spawn_kwargs)
                spawn_kwargs["creationflags"] = spawn_kwargs.get("creationflags", 0) | extra_flags
            subprocess.Popen(
                [pythonw, "-m", "voice_flow.main"],
                cwd=src_dir,
                env=env,
                close_fds=True,
                **spawn_kwargs,
            )
            _launcher_log("Started Voice Flow main engine directly")
            return True
        except Exception as e2:
            _launcher_log(f"Could not start main engine directly: {e2}")
            return False


def set_windows_auto_startup(enable: bool = True) -> bool:
    """Explicitly configure the current user's native auto-start registration."""
    try:
        from voice_flow.installer import set_autostart
        return set_autostart(enable)
    except Exception as exc:
        _launcher_log(f"Could not update auto-startup: {exc}")
        return False


def reconcile_windows_auto_startup(enable: bool) -> bool:
    """Apply a saved preference while respecting a task disabled in Windows."""
    try:
        from voice_flow.installer import reconcile_autostart
        return reconcile_autostart(enable)
    except Exception as exc:
        _launcher_log(f"Could not reconcile auto-startup: {exc}")
        return False


def is_api_server_ready(timeout: float = 0.2) -> bool:
    try:
        return runtime_is_compatible(port=PORT, timeout=timeout)
    except Exception:
        return False


def is_engine_ready(timeout: float = 0.2) -> bool:
    """Return whether the compatible local API has a live dictation engine."""
    try:
        return runtime_is_engine_ready(port=PORT, timeout=timeout)
    except Exception:
        return False


def _apply_taskbar_visibility(window, visible: bool) -> bool:
    """Apply taskbar styles only to this installation's verified desktop window."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        import psutil
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError.argtypes = [ctypes.c_ulong]
        kernel32.SetLastError.restype = None
        kernel32.GetLastError.argtypes = []
        kernel32.GetLastError.restype = ctypes.c_ulong
        hwnd_type = ctypes.c_void_p
        pid_type = ctypes.c_ulong
        user32.GetWindowThreadProcessId.argtypes = [hwnd_type, ctypes.POINTER(pid_type)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        user32.GetWindowTextW.argtypes = [hwnd_type, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.SetWindowPos.argtypes = [hwnd_type, hwnd_type, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.SetWindowPos.restype = ctypes.c_int
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_style.argtypes = [hwnd_type, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [hwnd_type, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        project = Path(__file__).resolve().parents[3]

        def owned(hwnd):
            pid = pid_type()
            if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
                return False
            if pid.value == os.getpid():
                return True
            process = psutil.Process(pid.value)
            arguments = process.cmdline()
            return ("-m" in arguments
                    and arguments[arguments.index("-m") + 1] == "voice_flow.gui.desktop_launcher"
                    and Path(process.cwd()).resolve() in {project, project / "src"})

        candidates = []
        native = getattr(window, "native", None) if window is not None else None
        handle = getattr(native, "Handle", None)
        if handle is not None:
            to_int64 = getattr(handle, "ToInt64", None)
            candidates.append(int(to_int64() if callable(to_int64) else handle))
        else:
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, hwnd_type, ctypes.c_ssize_t)
            def collect(hwnd, _parameter):
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, len(title))
                if title.value in {"AI Productivity Flow", "Voice Flow"}:
                    candidates.append(hwnd)
                return 1
            user32.EnumWindows.argtypes = [callback_type, ctypes.c_ssize_t]
            user32.EnumWindows.restype = ctypes.c_int
            if not user32.EnumWindows(callback_type(collect), 0):
                return False
        for hwnd in candidates:
            try:
                if not owned(hwnd):
                    continue
            except (psutil.Error, OSError, ValueError, IndexError):
                continue
            kernel32.SetLastError(0)
            style = get_style(hwnd, -20)
            if style == 0 and kernel32.GetLastError():
                return False
            style = (style | 0x40000) & ~0x80 if visible else (style | 0x80) & ~0x40000
            kernel32.SetLastError(0)
            previous = set_style(hwnd, -20, style)
            if previous == 0 and kernel32.GetLastError():
                return False
            return bool(user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004))
        return False
    except Exception as exc:
        print(f"[SYSTEM WARNING] Could not apply taskbar preference: {exc}")
        return False


def _apply_window_icon(ico_path: str, window=None, hwnd=None) -> None:
    """Explicitly assign both ICON_BIG and ICON_SMALL to the native window HWND on Windows."""
    if not sys.platform.startswith("win") or not ico_path or not os.path.exists(ico_path):
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # HWND/HICON and message parameters are pointer-sized on 64-bit Windows.
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.LoadImageW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        ]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        if not hwnd and window is not None:
            native = getattr(window, "native", None)
            if native is not None and hasattr(native, "Handle"):
                try:
                    handle = native.Handle
                    hwnd = int(handle.ToInt64()) if hasattr(handle, "ToInt64") else int(handle)
                except Exception:
                    hwnd = None
        if not hwnd:
            hwnd = user32.FindWindowW(None, "AI Productivity Flow") or user32.FindWindowW(None, "Voice Flow")
        if not hwnd:
            return
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        sm_cx = user32.GetSystemMetrics(49)  # SM_CXSMICON
        sm_cy = user32.GetSystemMetrics(50)  # SM_CYSMICON
        lg_cx = user32.GetSystemMetrics(11)  # SM_CXICON
        lg_cy = user32.GetSystemMetrics(12)  # SM_CYICON

        hicon_sm = user32.LoadImageW(0, ico_path, IMAGE_ICON, sm_cx, sm_cy, LR_LOADFROMFILE)
        hicon_lg = user32.LoadImageW(0, ico_path, IMAGE_ICON, lg_cx, lg_cy, LR_LOADFROMFILE)

        if hicon_sm:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
        else:
            _launcher_log("Could not load the small Windows window icon.")
        if hicon_lg:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_lg)
        else:
            _launcher_log("Could not load the large Windows window icon.")
    except Exception as exc:
        _launcher_log(f"Failed to apply window icon: {exc}")


def _fallback_to_browser(url: str, on_quit_callback=None, keep_alive: bool = True) -> None:
    """Fallback to opening URL in the system default browser if pywebview fails."""
    _close_startup_splash()
    import webbrowser
    print(f"[GUI] Launching Voice Flow Desktop in default browser at {url}...")
    try:
        webbrowser.open(url)
    except Exception as exc:
        print(f"[GUI ERROR] Failed to open default web browser: {exc}")

    if not keep_alive:
        if on_quit_callback:
            try:
                on_quit_callback()
            except Exception:
                pass
        return

    print("[GUI] Voice Flow is running in browser fallback mode. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1.0)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if on_quit_callback:
            try:
                on_quit_callback()
            except Exception:
                pass


def _close_startup_splash() -> None:
    try:
        from voice_flow.gui.early_splash import close_early_splash
        close_early_splash()
    except Exception:
        pass


def _defer_autostart_registration() -> None:
    """Register login startup off the window path. Task Scheduler can take seconds."""
    try:
        from voice_flow.storage import storage
        autostart_pref = storage.get_setting("autostart_enabled", None)
        if autostart_pref is None:
            if set_windows_auto_startup(True):
                storage.save_setting("autostart_enabled", True)
        else:
            reconcile_windows_auto_startup(bool(autostart_pref))
    except Exception as exc:
        _launcher_log(f"Auto-startup initialization warning: {exc}")


# ---------------------------------------------------------------------------
# Cold start: open the window at once with a "warming up" page.
# ---------------------------------------------------------------------------
# Up to 1.0.6 the launcher blocked for up to 200 polls (about 30 s on Windows)
# waiting for the engine before it created any window, behind a topmost splash.
# On a slow first launch that read as a frozen app. The window now opens
# straight away on a small local page, and a background thread swaps in the
# real UI once the engine answers. The UI still never attaches to an API-only
# listener while a real engine is starting.

# How long the warming window waits for the dictation engine before it accepts
# a compatible API-only listener. It keeps polling after this either way.
WARMING_ENGINE_WAIT_SECONDS = 120.0
WARMING_POLL_SECONDS = 0.25
WARMING_PROGRESS_LOG_SECONDS = 30.0

WARMING_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AI Productivity Flow</title>
<style>
html,body{margin:0;height:100%;background:#0b0c16;color:#fff8f3;
font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,system-ui,sans-serif}
.wrap{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;text-align:center;padding:0 32px}
h1{font-size:24px;font-weight:600;margin:0}
.bar{width:220px;height:4px;border-radius:2px;background:#24263a;overflow:hidden}
.bar i{display:block;width:40%;height:100%;background:#ff6a1a;border-radius:2px;animation:slide 1.4s ease-in-out infinite}
@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(250%)}}
p{margin:0;color:#b9b3ad;font-size:14px;max-width:460px;line-height:1.5}
small{color:#7d7872;font-size:12px}
</style></head>
<body><div class="wrap" id="apf-warming" data-apf-warming="1">
<h1>AI Productivity Flow</h1>
<div class="bar"><i></i></div>
<p id="msg">Warming up&hellip;</p>
<small id="elapsed"></small>
</div>
<script>
(function(){var t0=Date.now(),m=document.getElementById('msg'),e=document.getElementById('elapsed');
function tick(){var s=Math.round((Date.now()-t0)/1000);
if(s>=150){m.textContent='Still starting. If nothing changes in a few minutes, close this window and open the app again.';}
else if(s>=45){m.textContent='Still warming up. The first start after installing or updating takes longer while Windows checks the new files.';}
else if(s>=12){m.textContent='Loading the speech engine in the background. You can keep using your PC.';}
e.textContent=s>=3?(s+' s'):'';}
tick();setInterval(tick,1000);})();
</script></body></html>"""


def _early_window_enabled() -> bool:
    """Open the window before the engine is ready (default on)."""
    return os.environ.get("VOICE_FLOW_EARLY_WINDOW", "1").strip().lower() not in ("0", "false", "no", "off")


def _wait_for_backend_in_background(backend_spawned: bool, startup_began: float, *,
                                    engine_wait_seconds: float = WARMING_ENGINE_WAIT_SECONDS,
                                    poll_seconds: float = WARMING_POLL_SECONDS,
                                    max_seconds: float | None = None,
                                    is_window_open=lambda: True) -> bool:
    """Wait for a usable backend off the UI thread. True when the UI can load.

    Prefers a live dictation engine. After ``engine_wait_seconds`` a compatible
    API (for example an older API-only listener) is accepted too, and when no
    engine is starting at all the in-process API fallback is started, as the
    blocking path always did. ``max_seconds`` bounds the wait for tests; the
    window itself keeps waiting for as long as it is open.
    """
    began = time.monotonic()
    next_progress = began + WARMING_PROGRESS_LOG_SECONDS
    fallback_started = False
    while is_window_open():
        if is_engine_ready(timeout=0.25):
            _launcher_log(f"engine ready {time.monotonic() - startup_began:.1f}s after launch (window was warming up)")
            return True
        now = time.monotonic()
        if now - began >= engine_wait_seconds:
            if is_api_server_ready(timeout=0.5):
                _launcher_log(f"engine still not ready after {now - began:.0f}s; using the compatible API")
                return True
            if not fallback_started and not (backend_spawned or _is_backend_running()):
                fallback_started = True
                _launcher_log("no engine is starting; starting the in-process API fallback")
                threading.Thread(target=start_api_server, daemon=True, name="VoiceFlowApiServer").start()
        if now >= next_progress:
            next_progress = now + WARMING_PROGRESS_LOG_SECONDS
            _launcher_log(f"still waiting for the engine ({now - startup_began:.0f}s after launch)")
        if max_seconds is not None and now - began >= max_seconds:
            return False
        time.sleep(poll_seconds)
    return False


def _launch_warming_window(*, url: str, ico_path, show_in_taskbar: bool, backend_spawned: bool,
                           startup_began: float, on_quit_callback=None,
                           fallback_keep_alive: bool = True) -> None:
    """Show the window now; load the app once the engine is ready."""
    create_kwargs = dict(_WINDOW_KWARGS)
    create_kwargs["html"] = WARMING_HTML
    try:
        window = webview.create_window(**create_kwargs)
    except Exception as exc:
        _launcher_log(f"warming window could not be created ({exc}); waiting for the engine instead")
        _close_startup_splash()
        if _wait_for_backend_in_background(backend_spawned, startup_began, max_seconds=WARMING_ENGINE_WAIT_SECONDS + 30):
            _fallback_to_browser(url, on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)
        return
    _launcher_log(f"warming window created {time.monotonic() - startup_began:.1f}s after launch")
    state = {"closed": False}
    _wire_window(window, ico_path=ico_path, show_in_taskbar=show_in_taskbar,
                 startup_began=startup_began, on_quit_callback=on_quit_callback,
                 refresh_session_on_shown=False, state=state)

    def _attach_when_ready() -> None:
        ready = _wait_for_backend_in_background(
            backend_spawned, startup_began, is_window_open=lambda: not state["closed"])
        if not ready:
            return
        try:
            window.load_url(url)
            _launcher_log(f"app UI loaded {time.monotonic() - startup_began:.1f}s after launch")
        except Exception as exc:
            _launcher_log(f"could not load the app UI into the window: {exc}")
            return
        threading.Thread(target=_poke_overlay_show, daemon=True).start()
        threading.Thread(target=_poke_keepalive_refresh, daemon=True).start()

    try:
        _start_webview_loop(ico_path, func=_attach_when_ready)
    except Exception as exc:
        print(f"[GUI WARNING] pywebview failed to initialize native window: {exc}. Falling back to default web browser.")
        _close_startup_splash()
        if _wait_for_backend_in_background(backend_spawned, startup_began, max_seconds=WARMING_ENGINE_WAIT_SECONDS + 30):
            _fallback_to_browser(url, on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)


_WINDOW_KWARGS = {
    "title": "AI Productivity Flow",
    "width": 1160,
    "height": 760,
    "resizable": True,
    "min_size": (900, 600),
    "background_color": "#0b0c16",
}


def _start_webview_loop(ico_path, func=None) -> None:
    """Start pywebview. private_mode=False keeps the WebView profile
    (localStorage: onboarding flags, theme) across launches; pywebview
    defaults to a throwaway private profile."""
    kwargs = {}
    if ico_path:
        kwargs["icon"] = ico_path
    if func is not None:
        kwargs["func"] = func
    webview.start(private_mode=False, http_server=False, **kwargs)


def _wire_window(window, *, ico_path, show_in_taskbar: bool, startup_began: float,
                 on_quit_callback=None, refresh_session_on_shown: bool = True,
                 state: dict | None = None) -> None:
    """Shown/closed handlers shared by the cold (warming) and warm paths."""
    # If the native window never reports shown, don't leave the splash up.
    splash_watch = threading.Timer(15.0, _close_startup_splash)
    splash_watch.daemon = True
    splash_watch.start()

    def on_shown():
        _launcher_log(f"main window shown {time.monotonic() - startup_began:.1f}s after launch")
        _close_startup_splash()
        _apply_taskbar_visibility(window, show_in_taskbar)
        if ico_path:
            _apply_window_icon(ico_path, window=window)

        if refresh_session_on_shown:
            # Silently touch/refresh NotebookLM session on window open
            threading.Thread(target=_poke_keepalive_refresh, daemon=True).start()

        # Safety net: WebView2 occasionally births the window minimized at
        # (-32000, -32000) where it is unreachable. Restore it into view.
        def _ensure_visible():
            try:
                window.restore()
                window.show()
                if ico_path:
                    _apply_window_icon(ico_path, window=window)
            except Exception:
                pass
        try:
            timer = threading.Timer(3.0, _ensure_visible)
            timer.daemon = True
            timer.start()
        except Exception:
            pass

    try:
        window.events.shown += on_shown
    except Exception:
        pass

    def on_closed():
        if state is not None:
            state["closed"] = True
        if on_quit_callback:
            try:
                on_quit_callback()
            except Exception:
                pass
        _launcher_log("webview window closed by user - exiting launcher process")
        try:
            global _LAUNCHER_MUTEX_HANDLE
            if _LAUNCHER_MUTEX_HANDLE:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(_LAUNCHER_MUTEX_HANDLE)
                _LAUNCHER_MUTEX_HANDLE = None
        except Exception:
            pass
        os._exit(0)

    try:
        window.events.closed += on_closed
    except Exception:
        pass

    if sys.platform == "darwin":
        _install_mac_window_lifecycle(window)


def _read_show_in_taskbar() -> bool:
    try:
        from voice_flow.storage import storage
        return bool(storage.get_setting("show_in_taskbar", True))
    except Exception:
        return True


def _app_icon_path():
    ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "icon.ico"))
    return ico_path if os.path.exists(ico_path) else None


def _set_windows_app_id() -> None:
    # Set Windows AppUserModelID so taskbar groups properly and uses our icon.
    # The early splash sets the same id, so both share one taskbar button.
    if sys.platform.startswith("win"):
        try:
            import ctypes
            myappid = 'antigravity.voiceflow.desktop.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass


def launch_desktop_gui(on_quit_callback=None, fallback_keep_alive: bool = True) -> None:
    """Launch API server, system auto-startup configuration, and native desktop window."""
    configure_macos_app("desktop")
    try:
        from voice_flow.gui.early_splash import show_early_splash
        show_early_splash()
    except Exception:
        pass
    threading.Thread(target=_defer_autostart_registration, name="apf-autostart", daemon=True).start()

    # Start the supervisor whenever the dictation engine is missing. API
    # readiness remains a separate concern below so an API-only listener can
    # still serve the desktop UI while the watchdog recovers the engine.
    backend_spawned = False
    startup_began = time.monotonic()
    _log_launch_phase("launcher ready to open a window")
    url = f"http://127.0.0.1:{PORT}/index.html"
    if not is_engine_ready(timeout=0.15):
        backend_spawned = bool(ensure_backend_running())
        backend_starting = backend_spawned or _is_backend_running()
        _launcher_log(f"engine not ready at launch; supervisor spawned={backend_spawned}")

        # Cold start with a real engine on its way: show the window now and
        # load the UI when the engine answers (see _launch_warming_window).
        if backend_starting and webview is not None and _early_window_enabled():
            print("[GUI] Opening Voice Flow Desktop App window; the engine is still starting...")
            _set_windows_app_id()
            _launch_warming_window(
                url=url, ico_path=_app_icon_path(), show_in_taskbar=_read_show_in_taskbar(),
                backend_spawned=backend_spawned, startup_began=startup_began,
                on_quit_callback=on_quit_callback, fallback_keep_alive=fallback_keep_alive,
            )
            return

        # When an engine process is starting, wait for its readiness probe so
        # the UI does not attach to a compatible API-only listener just as the
        # watchdog reclaims its port. Keep the existing bounded startup window;
        # after it expires the regular API/browser fallback below still applies.
        poll_iterations = 200 if backend_starting else 40
        ready = False
        for _ in range(poll_iterations):
            ready = (
                is_engine_ready(timeout=0.1)
                if backend_starting
                else is_api_server_ready(timeout=0.1)
            )
            if ready:
                break
            time.sleep(0.05)
        _launcher_log(
            f"engine wait finished after {time.monotonic() - startup_began:.1f}s "
            f"({'ready' if ready else 'not ready'}; waited for {'engine' if backend_starting else 'API'})"
        )

    # If the backend is ready, bring the floating bar forward without changing active work.
    if is_api_server_ready(timeout=0.5):
        threading.Thread(target=_poke_overlay_show, daemon=True).start()
    else:
        # Fallback: start local API server in this process ONLY if background failed to spawn and is not running
        # Never bind the API-only fallback while a cold watchdog/engine is
        # alive; doing so steals its port and leaves dictation unavailable.
        if not is_api_server_ready() and not (backend_spawned or _is_backend_running()):
            if start_api_server is not None:
                server_thread = threading.Thread(target=start_api_server, daemon=True, name="VoiceFlowApiServer")
                server_thread.start()
                for _ in range(20):
                    if is_api_server_ready():
                        break
                    time.sleep(0.05)

    if not is_api_server_ready(timeout=0.5):
        # A Voice Flow engine the probe could not classify is still better than
        # nothing: show the UI in the browser rather than failing silently.
        if _is_backend_running() or backend_spawned:
            _launcher_log("backend probe failed but a Voice Flow engine is running - browser fallback")
            _fallback_to_browser(url, on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)
            return
        if start_api_server is not None:
            try:
                server_thread = threading.Thread(target=start_api_server, daemon=True, name="VoiceFlowApiServer")
                server_thread.start()
                for _ in range(20):
                    if is_api_server_ready():
                        break
                    time.sleep(0.05)
            except Exception:
                pass
        if not is_api_server_ready(timeout=0.2):
            _fallback_to_browser(url, on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)
            return

    show_in_taskbar = _read_show_in_taskbar()
    print(f"[GUI] Opening Voice Flow Desktop App window at {url}...")
    ico_path = _app_icon_path()

    # Create native desktop window matching desktop application layout
    create_kwargs = dict(_WINDOW_KWARGS)
    create_kwargs["url"] = url
    _set_windows_app_id()

    if webview is None:
        _launcher_log("Native window backend unavailable; using the system browser.")
        _fallback_to_browser(url, on_quit_callback, keep_alive=True)
        return

    try:
        window = webview.create_window(**create_kwargs)
        _wire_window(window, ico_path=ico_path, show_in_taskbar=show_in_taskbar,
                     startup_began=startup_began, on_quit_callback=on_quit_callback)
        _launcher_log(f"webview window created {time.monotonic() - startup_began:.1f}s after launch")
        _start_webview_loop(ico_path)
    except Exception as exc:
        print(f"[GUI WARNING] pywebview failed to initialize native window: {exc}. Falling back to default web browser.")
        _close_startup_splash()
        _fallback_to_browser(url, on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)


def _install_mac_window_lifecycle(window) -> None:
    """macOS: Quit ends the whole app; a second launch raises this window.

    Closing the window (red button / Cmd+W) still only closes the window: the
    engine keeps dictation running and its menu bar item / floating bar menu
    offer "Open" and "Quit AI Productivity Flow".
    """
    try:
        from voice_flow.platform import macos_lifecycle
    except Exception as exc:
        _launcher_log(f"mac lifecycle unavailable: {exc}")
        return

    def _quit_everything() -> None:
        _launcher_log("app quit (Cmd+Q / Dock / Apple Event) - asking the engine to quit")
        macos_lifecycle.notify_engine_quit(port=PORT, reason="window-quit")

    def _show() -> None:
        try:
            window.restore()
        except Exception:
            pass
        window.show()

    if macos_lifecycle.install_terminate_observer(_quit_everything):
        _launcher_log("mac quit observer installed")
    macos_lifecycle.serve_desktop_control(_show)


def _mac_window_already_running() -> bool:
    """macOS single window process: raise the running one and report True."""
    if sys.platform != "darwin":
        return False
    try:
        from voice_flow.platform import macos_lifecycle
    except Exception:
        return False
    if macos_lifecycle.acquire_desktop_lock():
        return False
    for _ in range(20):  # the other window may still be starting
        if macos_lifecycle.send_desktop_show():
            break
        time.sleep(0.25)
    return True


def _native_window_text(user32, hwnd, getter_name: str) -> str:
    """Read a window title or class. Empty when the handle is not a real window."""
    try:
        import ctypes
        getter = getattr(user32, getter_name)
        getter.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        getter.restype = ctypes.c_int
        buf = ctypes.create_unicode_buffer(512)
        if not getter(hwnd, buf, len(buf)):
            return ""
        return buf.value or ""
    except Exception:
        return ""


def _reject_startup_splash(user32, hwnd) -> bool:
    """True when this handle is the early splash and must not count as the app."""
    if not hwnd:
        return False
    try:
        from voice_flow.gui.early_splash import is_startup_splash
    except Exception:
        is_startup_splash = None
    title = _native_window_text(user32, hwnd, "GetWindowTextW")
    class_name = _native_window_text(user32, hwnd, "GetClassNameW")
    if is_startup_splash is not None and is_startup_splash(title, class_name):
        return True
    return class_name == "APFEarlySplash" or title in ("APFEarlySplash", "AI Productivity Flow (starting)")


def _focus_existing_window() -> bool:
    """Focus an already-running Desktop App window instead of opening a duplicate.

    The engine spawns this launcher on every boot (including watchdog
    auto-recovery); without this guard each restart stacks another window.
    The startup splash shares neither the app title nor its window class.
    A title-and-size match is not enough: the splash is 420x210, which used
    to pass the old 100x50 ghost check and make this launch exit.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "AI Productivity Flow") or user32.FindWindowW(None, "Voice Flow")
        if hwnd and _reject_startup_splash(user32, hwnd):
            _launcher_log(f"ignoring startup splash hwnd={hwnd}")
            hwnd = None
        if not hwnd:
            return False

        if hasattr(user32, "IsWindow") and not user32.IsWindow(hwnd):
            return False

        # If minimized, restore it first
        if hasattr(user32, "IsIconic") and user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # 9 = SW_RESTORE

        # If hidden / not visible, attempt to show and restore
        if hasattr(user32, "IsWindowVisible") and not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 9)  # 9 = SW_RESTORE / SW_SHOWNORMAL

        # Verify the window is truly open, visible and on-screen
        if hasattr(user32, "IsWindowVisible") and not user32.IsWindowVisible(hwnd):
            return False

        # Reject dead zombie windows: only if NOT iconic and collapsed offscreen
        try:
            import ctypes.wintypes as _wt
            rect = _wt.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                is_iconic = hasattr(user32, "IsIconic") and user32.IsIconic(hwnd)
                if not is_iconic and (rect.left <= -20000 or rect.top <= -20000 or width < 100 or height < 50):
                    _launcher_log(f"ignoring ghost window hwnd={hwnd} rect=({rect.left},{rect.top},{width}x{height})")
                    return False
        except Exception:
            pass

        # Bring window to foreground with thread attachment
        try:
            user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass
        try:
            kernel32 = ctypes.windll.kernel32
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            cur_tid = kernel32.GetCurrentThreadId()
            target_tid = user32.GetWindowThreadProcessId(hwnd, None)
            if fg_tid and fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, True)
                if target_tid and target_tid != cur_tid:
                    user32.AttachThreadInput(cur_tid, target_tid, True)
                user32.BringWindowToTop(hwnd)
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                if target_tid and target_tid != cur_tid:
                    user32.AttachThreadInput(cur_tid, target_tid, False)
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
        except Exception:
            if hasattr(user32, "SetForegroundWindow"):
                user32.SetForegroundWindow(hwnd)

        # Ensure window has the correct icon applied
        ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "icon.ico"))
        if os.path.exists(ico_path):
            _apply_window_icon(ico_path, hwnd=hwnd)

        # Re-trigger floating bar display so the user sees it immediately.
        threading.Thread(target=_poke_overlay_show, daemon=True).start()
        # Silently touch/refresh NotebookLM session when window is focused
        threading.Thread(target=_poke_keepalive_refresh, daemon=True).start()
        return True
    except Exception:
        return False


_LAUNCHER_MUTEX_NAME = "Local\\VoiceFlowDesktopLauncherMutex_v1"
_LAUNCHER_MUTEX_HANDLE = None

# Long enough for the early splash to appear, short enough that a second
# click is not stuck. Timeout still refuses to open another window.
_DUPLICATE_LAUNCH_WAIT_SECONDS = 5.0
_DUPLICATE_LAUNCH_POLL_INTERVAL = 0.1


def _get_kernel32():
    """kernel32 bound with use_last_error=True so GetLastError is captured.

    ``ctypes.windll`` never syncs the ctypes-private error variable, so
    ``ctypes.get_last_error()`` after ``ctypes.windll.kernel32.CreateMutexW``
    always returned 0 and ERROR_ALREADY_EXISTS (183) was never detected -
    which silently disabled the launcher single-instance mutex and let the
    Windows boot race open two app windows."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _acquire_launcher_mutex() -> bool:
    """Ensure only one desktop launcher process runs at a time."""
    global _LAUNCHER_MUTEX_HANDLE
    inherited = os.environ.get("VOICE_FLOW_LAUNCHER_MUTEX_HANDLE")
    inherited_pid = os.environ.get("VOICE_FLOW_LAUNCHER_MUTEX_PID")
    # launch_apf.pyw takes the mutex and then runs this launcher in the same
    # process. A handle that came from another process (through a child's
    # environment) is not ours. Older launch_apf.pyw files set no PID.
    if inherited and inherited_pid and inherited_pid != str(os.getpid()):
        _launcher_log(f"ignoring launcher mutex handle inherited from pid {inherited_pid}")
        inherited = None
    if inherited:
        try:
            _LAUNCHER_MUTEX_HANDLE = int(inherited)
            return True
        except ValueError:
            pass
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        kernel32 = _get_kernel32()
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, _LAUNCHER_MUTEX_NAME)
        last_err = ctypes.get_last_error()
        if handle and last_err == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        _LAUNCHER_MUTEX_HANDLE = handle
        return True
    except Exception:
        return True


def _launcher_mutex_held() -> bool:
    """True while ANOTHER desktop launcher process still holds the mutex."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        kernel32 = _get_kernel32()
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, _LAUNCHER_MUTEX_NAME)
        last_err = ctypes.get_last_error()
        if handle:
            kernel32.CloseHandle(handle)
        return bool(handle) and last_err == ERROR_ALREADY_EXISTS
    except Exception:
        return False


def _wait_for_existing_window(
    total_seconds: float = _DUPLICATE_LAUNCH_WAIT_SECONDS,
    poll_interval: float = _DUPLICATE_LAUNCH_POLL_INTERVAL,
    *,
    sleep=time.sleep,
    clock=time.monotonic,
    focus=None,
    mutex_held=None,
) -> str:
    """Poll for the first launcher's window while it holds the mutex.

    Boot-safe duplicate guard: a single point-in-time window check decides
    'fresh start' too early at logon (the first launcher only creates its
    webview window after the 10-25s cold API start), which opened two
    windows. This polls for the existing window for up to ``total_seconds``
    and watches the launcher mutex so the second launcher exits (focusing
    the existing window) instead of spawning its own suite.

    Returns one of:
      'focused'  - an existing window was focused; caller must exit,
      'released' - the other launcher exited without opening a window;
                   caller may start fresh,
      'timeout'  - the other launcher is still active but no window appeared
                   (e.g. browser-fallback mode); caller may start fresh as a
                   last-resort fallback.
    """
    focus_fn = focus if focus is not None else _focus_existing_window
    mutex_fn = mutex_held if mutex_held is not None else _launcher_mutex_held
    deadline = clock() + total_seconds
    while True:
        if focus_fn():
            return "focused"
        if not mutex_fn():
            return "released"
        if clock() >= deadline:
            return "timeout"
        sleep(poll_interval)


def _run_desktop_launcher() -> None:
    """Single-instance entry flow shared by direct and boot launches."""
    if _mac_window_already_running():
        _launcher_log("window process already running - raised it, exiting duplicate launcher")
        sys.exit(0)

    if _focus_existing_window():
        _launcher_log("existing window focused - exiting duplicate launcher")
        print("[GUI] Desktop App window already open — focusing it instead of launching a duplicate.")
        sys.exit(0)

    if not _acquire_launcher_mutex():
        _launcher_log("another desktop_launcher process is already starting/active - waiting to focus")
        outcome = _wait_for_existing_window()
        if outcome == "focused":
            _launcher_log("existing window focused after waiting - exiting duplicate launcher")
            print("[GUI] Desktop App window already open — focusing it instead of launching a duplicate.")
            sys.exit(0)
        if outcome == "timeout":
            # The first launch still holds the mutex. Opening another window
            # is what stacked two apps when the first start was slow.
            _launcher_log("another launcher still holds the mutex; not opening a second window")
            print("[GUI] AI Productivity Flow is already starting.")
            sys.exit(0)
        _launcher_log(f"launcher mutex {outcome} without a window appearing - proceeding with launch")

    launch_desktop_gui()
    _launcher_log("webview loop ended (window closed)")


if __name__ == "__main__":
    _launcher_log(f"desktop_launcher starting (pid={os.getpid()}, argv={sys.argv[1:]})")
    _log_launch_phase("launcher imports finished")
    try:
        _run_desktop_launcher()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("[GUI] Exiting Desktop App launcher.")
        sys.exit(0)
    except Exception as exc:
        try:
            from voice_flow.paths import data_dir
            crash_file = data_dir() / "gui_crash.log"
            import traceback
            crash_file.write_text(f"Exception in desktop_launcher: {exc}\n{traceback.format_exc()}", encoding="utf-8")
        except Exception:
            pass
        print(f"[GUI CRASH] Unhandled error in desktop_launcher: {exc}")
        raise
