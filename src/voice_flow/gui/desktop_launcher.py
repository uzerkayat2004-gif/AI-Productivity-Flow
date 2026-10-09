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

# Ensure WebView2 allows audio autoplay without requiring initial user gesture
_wv2_args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
if "--autoplay-policy=no-user-gesture-required" not in _wv2_args:
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        f"{_wv2_args} --autoplay-policy=no-user-gesture-required".strip()
    )

webview = None  # type: ignore[assignment]

if not os.environ.get("CI"):
    try:
        import webview
    except Exception:  # missing desktop dependency falls back to browser launcher
        import traceback
        try:
            crash_path = Path(os.path.expanduser("~")) / ".voice_flow" / "gui_crash.log"
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

_launcher_log_path = Path(os.path.expanduser("~")) / ".voice_flow" / "gui_launcher.log"

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


try:
    from voice_flow.gui.api_server import start_api_server, PORT
    from voice_flow.runtime_guard import runtime_is_compatible
    _API_IMPORT_ERROR = None
except Exception as _import_exc:  # broken/partial install must never die silently
    import urllib.request as _urlreq

    start_api_server = None
    PORT = 8991
    _API_IMPORT_ERROR = _import_exc

    def runtime_is_compatible(*, host: str = "127.0.0.1", port: int = PORT, timeout: float = 1.0) -> bool:
        try:
            with _urlreq.urlopen(f"http://{host}:{port}/api/runtime", timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False

    try:
        from voice_flow.paths import data_dir
        import traceback
        (data_dir() / "gui_crash.log").write_text(
            "desktop_launcher import failure:\n" + traceback.format_exc(), encoding="utf-8"
        )
    except Exception:
        pass
    _launcher_log(f"api_server import failed: {_import_exc}")


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
        with urllib.request.urlopen(req, timeout=2.0):
            pass
        _launcher_log("Sent /api/video-flow/notebooklm/keepalive/refresh on window open/focus")
    except Exception as e:
        _launcher_log(f"/api/video-flow/notebooklm/keepalive/refresh ping error: {e}")



def _is_backend_running() -> bool:
    """Check if Voice Flow watchdog or main engine is already running."""
    try:
        if is_api_server_ready(timeout=0.1):
            return True
    except Exception:
        pass

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
        if not hwnd and window is not None:
            native = getattr(window, "native", None)
            if native is not None and hasattr(native, "Handle"):
                try:
                    hwnd = int(native.Handle)
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
        if hicon_lg:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_lg)
    except Exception as exc:
        _launcher_log(f"Failed to apply window icon: {exc}")


def _fallback_to_browser(url: str, on_quit_callback=None, keep_alive: bool = True) -> None:
    """Fallback to opening URL in the system default browser if pywebview fails."""
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


def launch_desktop_gui(on_quit_callback=None, fallback_keep_alive: bool = True) -> None:
    """Launch API server, system auto-startup configuration, and native desktop window."""
    # Configure auto-startup based on user setting (default enabled on first launch)
    try:
        from voice_flow.storage import storage
        autostart_pref = storage.get_setting("autostart_enabled", None)
        if autostart_pref is None:
            # First launch is an explicit default-on registration. Persist it
            # only when the operating-system change actually succeeded.
            if set_windows_auto_startup(True):
                storage.save_setting("autostart_enabled", True)
        else:
            # Reconcile the registration but leave stored intent to explicit UI
            # toggles. The status API reads the actual OS state independently.
            reconcile_windows_auto_startup(bool(autostart_pref))
    except Exception as exc:
        _launcher_log(f"Auto-startup initialization warning: {exc}")

    # Fast-path: Check if background API server is ALREADY active and ready
    backend_spawned = False
    if not is_api_server_ready(timeout=0.15):
        # Background engine / watchdog not responding yet; ensure it is started
        backend_spawned = bool(ensure_backend_running())

        # Poll until API server responds cleanly from background engine
        poll_iterations = 200 if (backend_spawned or _is_backend_running()) else 40
        for _ in range(poll_iterations):
            if is_api_server_ready(timeout=0.1):
                break
            time.sleep(0.05)

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
            _fallback_to_browser(f"http://127.0.0.1:{PORT}/index.html", on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)
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
            _fallback_to_browser(f"http://127.0.0.1:{PORT}/index.html", on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)
            return

    try:
        from voice_flow.storage import storage
        show_in_taskbar = bool(storage.get_setting("show_in_taskbar", True))
    except Exception:
        show_in_taskbar = True

    url = f"http://127.0.0.1:{PORT}/index.html"
    print(f"[GUI] Opening Voice Flow Desktop App window at {url}...")

    # Icon path
    ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "icon.ico"))
    if not os.path.exists(ico_path):
        ico_path = None

    # Create native desktop window matching desktop application layout
    create_kwargs = {
        "title": "AI Productivity Flow",
        "url": url,
        "width": 1160,
        "height": 760,
        "resizable": True,
        "min_size": (900, 600),
        "background_color": "#0b0c16",
    }

    # Set Windows AppUserModelID so taskbar groups properly and uses our icon
    if sys.platform.startswith("win"):
        try:
            import ctypes
            myappid = 'antigravity.voiceflow.desktop.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    if webview is None:
        _fallback_to_browser(url, on_quit_callback, keep_alive=True)
        return

    try:
        window = webview.create_window(**create_kwargs)

        def on_shown():
            _apply_taskbar_visibility(window, show_in_taskbar)
            if ico_path:
                _apply_window_icon(ico_path, window=window)

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
        _launcher_log("webview window created")

        def on_closed():
            if on_quit_callback:
                try:
                    on_quit_callback()
                except Exception:
                    pass
            _launcher_log("webview window closed by user - exiting launcher process")
            try:
                global _LAUNCHER_MUTEX_HANDLE
                if _LAUNCHER_MUTEX_HANDLE:
                    ctypes.windll.kernel32.CloseHandle(_LAUNCHER_MUTEX_HANDLE)
                    _LAUNCHER_MUTEX_HANDLE = None
            except Exception:
                pass
            os._exit(0)

        try:
            window.events.closed += on_closed
        except Exception:
            pass

        # Start pywebview loop with custom icon
        if ico_path:
            webview.start(icon=ico_path)
        else:
            webview.start()
    except Exception as exc:
        print(f"[GUI WARNING] pywebview failed to initialize native window: {exc}. Falling back to default web browser.")
        _fallback_to_browser(url, on_quit_callback=on_quit_callback, keep_alive=fallback_keep_alive)


def _focus_existing_window() -> bool:
    """Focus an already-running Desktop App window instead of opening a duplicate.

    The engine spawns this launcher on every boot (including watchdog
    auto-recovery); without this guard each restart stacks another window.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "AI Productivity Flow") or user32.FindWindowW(None, "Voice Flow")
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
        _launcher_log(f"launcher mutex {outcome} without a window appearing - proceeding with launch")

    launch_desktop_gui()
    _launcher_log("webview loop ended (window closed)")


if __name__ == "__main__":
    _launcher_log(f"desktop_launcher starting (pid={os.getpid()}, argv={sys.argv[1:]})")
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
