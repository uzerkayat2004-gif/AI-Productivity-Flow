"""A branded window shown before heavy imports.

This module imports only the standard library so a launcher can load it by
file path without pulling in the rest of Voice Flow. On 64-bit Windows every
user32/gdi32 call uses pointer-sized argument types: a c_long LPARAM overflows
inside the window procedure and the process stops answering.
"""

from __future__ import annotations

import os
import re
import sys
import threading

# Win32 title and class stay distinct from the real desktop window. The
# launcher used to call FindWindowW("AI Productivity Flow") and treat this
# 420x210 splash as the app, then exit before the main window existed.
WINDOW_TITLE = "APFEarlySplash"
BRAND_TITLE = "AI Productivity Flow"
SPLASH_CLASS_NAME = "APFEarlySplash"
APP_WINDOW_TITLES = ("AI Productivity Flow", "Voice Flow")
_CLASS_NAME = SPLASH_CLASS_NAME
_LOG_NAME = "launch.log"
# The splash closes itself after this long even if nobody asks it to. Startup
# waits up to about a minute for the engine and then 15 s for the window, so a
# splash still up after two minutes means something failed, and a topmost
# "Starting..." box over every app is worse than no splash.
MAX_SPLASH_SECONDS = 120
_ANIMATION_TIMER_ID = 1
_DEADLINE_TIMER_ID = 2

# Cream #FFF8F3, accent #FF6A1A, ink #1C140F, muted #5C564F, as COLORREF (BGR).
_CREAM = 0x00F3F8FF
_ACCENT = 0x001A6AFF
_INK = 0x000F141C
_MUTED = 0x004F565C

_WM_DESTROY = 0x0002
_WM_CLOSE = 0x0010
_WM_PAINT = 0x000F
_WM_ERASEBKGND = 0x0014
_WM_TIMER = 0x0113
_DT_CENTER_LINE = 0x00000001 | 0x00000004 | 0x00000020

_user32 = None
_gdi32 = None
_kernel32 = None
_SPLASH_WNDPROC = None
_SPLASH_HWND = 0
_phase = 0
_icon = None
_font_title = None
_font_body = None
_brush_cream = None
_brush_accent = None
_ready = threading.Event()


def is_startup_splash(title: str, class_name: str) -> bool:
    """True for the early splash, including one a test has not retitled yet.

    Class is the reliable check. The title is checked too so a splash that
    still uses the app name cannot pass a title-only search.
    """
    return (class_name or "") == SPLASH_CLASS_NAME or (title or "") == WINDOW_TITLE


def read_app_version() -> str:
    """Read ``__version__`` from _version.py without importing the package.

    ``_version.py`` is the one source of truth for the build that is running
    (update checks and the installer read the same value). Returns "" when the
    file cannot be read, so the splash shows no version rather than a wrong one.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "_version.py")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""


def version_label() -> str:
    version = read_app_version()
    return f"Version {version}" if version else ""


def _log(message: str) -> None:
    try:
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        folder = os.path.join(home, ".voice_flow", "logs")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, _LOG_NAME), "a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except Exception:
        pass


def _ensure_bindings():
    """Bind user32/gdi32 with pointer-sized prototypes. Safe to call more than once."""
    global _user32, _gdi32, _kernel32
    if _user32 is not None:
        return _user32
    import ctypes
    from ctypes import wintypes

    lresult = ctypes.c_ssize_t
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = lresult
    user32.RegisterClassW.argtypes = [ctypes.c_void_p]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.UpdateWindow.argtypes = [wintypes.HWND]
    user32.UpdateWindow.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.c_void_p]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.c_void_p]
    user32.DispatchMessageW.restype = lresult
    user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.BeginPaint.restype = wintypes.HDC
    user32.EndPaint.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.EndPaint.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.FillRect.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.HBRUSH]
    user32.FillRect.restype = ctypes.c_int
    user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.UINT]
    user32.DrawTextW.restype = ctypes.c_int
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
    user32.SetTimer.restype = ctypes.c_size_t
    user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    user32.KillTimer.restype = wintypes.BOOL
    user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
    user32.InvalidateRect.restype = wintypes.BOOL
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.DrawIconEx.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
        ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT,
    ]
    user32.DrawIconEx.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    user32.SetWindowRgn.restype = ctypes.c_int
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL

    gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.SetTextColor.restype = wintypes.COLORREF
    gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
    gdi32.CreateFontW.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    gdi32.CreateFontW.restype = wintypes.HFONT
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

    _user32 = user32
    _gdi32 = gdi32
    _kernel32 = kernel32
    return user32


def def_window_proc(hwnd, msg, wparam, lparam):
    """Call DefWindowProcW with a pointer-sized LPARAM.

    A missing prototype converts LPARAM as a 32-bit int and raises
    OverflowError for values such as ``1 << 42`` (WM_NCCREATE on 64-bit Windows).
    """
    user32 = _ensure_bindings()
    return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))


def _paint(hwnd) -> None:
    import ctypes
    from ctypes import wintypes

    global _phase
    user32 = _user32
    gdi32 = _gdi32
    ps = _PAINTSTRUCT()
    hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
    try:
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        user32.FillRect(hdc, ctypes.byref(rect), _brush_cream)
        bar = wintypes.RECT(0, 0, rect.right, 8)
        user32.FillRect(hdc, ctypes.byref(bar), _brush_accent)
        if _icon:
            icon_x = max(0, (rect.right - 56) // 2)
            user32.DrawIconEx(hdc, icon_x, 24, _icon, 56, 56, 0, None, 3)
        gdi32.SetBkMode(hdc, 1)
        title = wintypes.RECT(20, 90, max(21, rect.right - 20), 124)
        gdi32.SetTextColor(hdc, _INK)
        previous = gdi32.SelectObject(hdc, _font_title)
        user32.DrawTextW(hdc, BRAND_TITLE, -1, ctypes.byref(title), _DT_CENTER_LINE)
        version = wintypes.RECT(20, 124, max(21, rect.right - 20), 152)
        gdi32.SelectObject(hdc, _font_body)
        gdi32.SetTextColor(hdc, _MUTED)
        label = version_label()
        if label:
            user32.DrawTextW(hdc, label, -1, ctypes.byref(version), _DT_CENTER_LINE)
        dots = wintypes.RECT(20, 160, max(21, rect.right - 20), 190)
        gdi32.SetTextColor(hdc, _ACCENT)
        user32.DrawTextW(hdc, "Starting" + ("." * ((_phase % 3) + 1)), -1, ctypes.byref(dots), _DT_CENTER_LINE)
        if previous:
            gdi32.SelectObject(hdc, previous)
    finally:
        user32.EndPaint(hwnd, ctypes.byref(ps))


def _wnd_proc(hwnd, msg, wparam, lparam):
    try:
        if msg == _WM_PAINT:
            _paint(hwnd)
            return 0
        if msg == _WM_TIMER:
            if int(wparam or 0) == _DEADLINE_TIMER_ID:
                _log(f"splash closed after {MAX_SPLASH_SECONDS}s startup deadline hwnd={int(hwnd or 0)}")
                _user32.DestroyWindow(hwnd)
                return 0
            global _phase
            _phase += 1
            _user32.InvalidateRect(hwnd, None, False)
            return 0
        if msg == _WM_ERASEBKGND:
            return 1
        if msg == _WM_CLOSE:
            _user32.DestroyWindow(hwnd)
            return 0
        if msg == _WM_DESTROY:
            try:
                _user32.KillTimer(hwnd, _ANIMATION_TIMER_ID)
                _user32.KillTimer(hwnd, _DEADLINE_TIMER_ID)
            except Exception:
                pass
            _user32.PostQuitMessage(0)
            return 0
    except Exception as exc:
        _log(f"splash window procedure failed: {exc}")
        return 0
    try:
        return def_window_proc(hwnd, msg, wparam, lparam)
    except Exception as exc:
        _log(f"splash DefWindowProcW failed: {exc}")
        return 0


_PAINTSTRUCT = None


def _create_window():
    import ctypes
    from ctypes import wintypes

    global _SPLASH_WNDPROC, _PAINTSTRUCT, _icon, _font_title, _font_body, _brush_cream, _brush_accent
    user32 = _ensure_bindings()
    gdi32 = _gdi32
    kernel32 = _kernel32
    lresult = ctypes.c_ssize_t

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hdc", wintypes.HDC),
            ("fErase", wintypes.BOOL),
            ("rcPaint", wintypes.RECT),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", ctypes.c_byte * 32),
        ]

    _PAINTSTRUCT = PAINTSTRUCT
    wndproc_type = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASS(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", wndproc_type),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    _brush_cream = gdi32.CreateSolidBrush(_CREAM)
    _brush_accent = gdi32.CreateSolidBrush(_ACCENT)
    _font_title = gdi32.CreateFontW(-22, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
    _font_body = gdi32.CreateFontW(-15, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
    if os.path.isfile(icon_path):
        _icon = user32.LoadImageW(None, icon_path, 1, 56, 56, 0x00000010)

    _SPLASH_WNDPROC = wndproc_type(_wnd_proc)
    instance = kernel32.GetModuleHandleW(None)
    window_class = WNDCLASS()
    window_class.lpfnWndProc = _SPLASH_WNDPROC
    window_class.hInstance = instance
    window_class.lpszClassName = _CLASS_NAME
    window_class.hbrBackground = _brush_cream
    window_class.hIcon = _icon
    user32.RegisterClassW(ctypes.byref(window_class))

    width, height = 420, 210
    screen_w = user32.GetSystemMetrics(0) or 1280
    screen_h = user32.GetSystemMetrics(1) or 800
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    hwnd = user32.CreateWindowExW(
        0x00000008 | 0x00000080,  # WS_EX_TOPMOST | WS_EX_TOOLWINDOW
        _CLASS_NAME,
        WINDOW_TITLE,
        0x80000000 | 0x10000000,  # WS_POPUP | WS_VISIBLE
        x, y, width, height,
        None, None, instance, None,
    )
    if not hwnd:
        _log("splash CreateWindowExW returned no window")
        return None
    region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, 28, 28)
    if region:
        user32.SetWindowRgn(hwnd, region, True)
    user32.ShowWindow(hwnd, 5)
    user32.UpdateWindow(hwnd)
    user32.SetTimer(hwnd, _ANIMATION_TIMER_ID, 450, None)
    user32.SetTimer(hwnd, _DEADLINE_TIMER_ID, int(MAX_SPLASH_SECONDS * 1000), None)
    return hwnd


def _pump(hwnd) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = _user32
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    _log(f"splash closed hwnd={int(hwnd)}")


def _splash_thread() -> None:
    global _SPLASH_HWND
    try:
        hwnd = _create_window()
        if hwnd:
            _SPLASH_HWND = int(hwnd)
            os.environ["VOICE_FLOW_EARLY_SPLASH_HWND"] = str(int(hwnd))
            _log(f"splash shown hwnd={int(hwnd)}")
        _ready.set()
        if hwnd:
            _pump(hwnd)
    except Exception as exc:
        _log(f"splash failed: {exc}")
        _ready.set()


def _owned_splash_windows() -> list[int]:
    """Every splash window that belongs to this process.

    The installed launcher loads this file by path (module ``apf_early_splash``)
    and desktop_launcher imports it again as ``voice_flow.gui.early_splash``.
    The two copies do not share globals, so if the first splash is slow to
    appear the second copy can create another one. Closing by class and
    process closes both, and never touches another program's window.
    """
    if not sys.platform.startswith("win"):
        return []
    import ctypes
    from ctypes import wintypes

    user32 = _ensure_bindings()
    pid = os.getpid()
    found: list[int] = []
    hwnd = None
    for _ in range(64):
        hwnd = user32.FindWindowExW(None, hwnd, SPLASH_CLASS_NAME, None)
        if not hwnd:
            break
        owner = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if int(owner.value) == pid:
            found.append(int(hwnd))
    return found


def _is_own_splash(hwnd: int) -> bool:
    try:
        return int(hwnd) in _owned_splash_windows()
    except Exception:
        return False


def close_early_splash(hwnd: int | None = None) -> None:
    """Ask the splash thread to close. DestroyWindow is not safe across threads.

    Only splash windows owned by this process are closed. A handle inherited
    through the environment from another process may by now belong to an
    unrelated window, so it is never posted to blindly.
    """
    if not sys.platform.startswith("win"):
        return
    targets: list[int] = []
    try:
        targets = _owned_splash_windows()
    except Exception as exc:
        _log(f"splash lookup failed: {exc}")
    if not targets:
        raw = hwnd if hwnd else os.environ.get("VOICE_FLOW_EARLY_SPLASH_HWND") or _SPLASH_HWND
        if raw and _SPLASH_HWND and int(raw) == int(_SPLASH_HWND):
            targets = [int(raw)]
    try:
        user32 = _ensure_bindings()
        for target in targets:
            user32.PostMessageW(int(target), _WM_CLOSE, 0, 0)
    except Exception as exc:
        _log(f"splash close failed: {exc}")
    os.environ.pop("VOICE_FLOW_EARLY_SPLASH_HWND", None)


def show_early_splash() -> int | None:
    """Show a topmost branded window on its own message thread.

    Returns None when this is not an interactive Windows launch, or when the
    window cannot be created. Failures are logged and never raised: startup
    continues either way. ``CI`` skips the window so headless jobs stay quiet;
    the Windows launch smoke test unsets ``CI`` in its child process.
    """
    if not sys.platform.startswith("win") or os.environ.get("CI"):
        return None
    existing = os.environ.get("VOICE_FLOW_EARLY_SPLASH_HWND")
    if existing:
        try:
            if _is_own_splash(int(existing)):
                return int(existing)
        except ValueError:
            pass
        # Inherited from the process that started this one; not our window.
        os.environ.pop("VOICE_FLOW_EARLY_SPLASH_HWND", None)
    try:
        owned = _owned_splash_windows()
    except Exception:
        owned = []
    if owned:
        os.environ["VOICE_FLOW_EARLY_SPLASH_HWND"] = str(owned[0])
        return owned[0]
    try:
        _ready.clear()
        threading.Thread(target=_splash_thread, name="apf-early-splash", daemon=True).start()
        _ready.wait(3.0)
        raw = os.environ.get("VOICE_FLOW_EARLY_SPLASH_HWND")
        if not raw:
            _log("splash did not appear; continuing startup")
            return None
        return int(raw)
    except Exception as exc:
        _log(f"splash start failed: {exc}")
        return None
