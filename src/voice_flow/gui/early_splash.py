"""A branded window shown before heavy imports.

This module imports only the standard library so a launcher can load it by
file path without pulling in the rest of Voice Flow.
"""

from __future__ import annotations

import os
import sys

WINDOW_TITLE = "AI Productivity Flow"
_CLASS_NAME = "APFEarlySplash"


def close_early_splash(hwnd: int | None = None) -> None:
    """Destroy the startup window once the real UI exists."""
    if not sys.platform.startswith("win"):
        return
    raw = hwnd if hwnd else os.environ.get("VOICE_FLOW_EARLY_SPLASH_HWND")
    if not raw:
        return
    try:
        import ctypes

        ctypes.windll.user32.DestroyWindow(int(raw))
    except Exception:
        pass
    os.environ.pop("VOICE_FLOW_EARLY_SPLASH_HWND", None)


def show_early_splash() -> int | None:
    """Show a topmost branded window and return its handle.

    Returns None when this is not an interactive Windows launch.
    """
    if not sys.platform.startswith("win") or os.environ.get("CI"):
        return None
    existing = os.environ.get("VOICE_FLOW_EARLY_SPLASH_HWND")
    if existing:
        try:
            return int(existing)
        except ValueError:
            return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        def _wnd_proc(hwnd, msg, wparam, lparam):
            if msg == 0x000F:  # WM_PAINT
                ps = ctypes.create_string_buffer(64)
                hdc = user32.BeginPaint(hwnd, ps)
                rect = wintypes.RECT()
                user32.GetClientRect(hwnd, ctypes.byref(rect))
                brush = gdi32.CreateSolidBrush(0x002060FF)  # #ff6020 in BGR
                user32.FillRect(hdc, ctypes.byref(rect), brush)
                gdi32.DeleteObject(brush)
                gdi32.SetBkMode(hdc, 1)  # TRANSPARENT
                gdi32.SetTextColor(hdc, 0x00FFFFFF)
                user32.DrawTextW(
                    hdc,
                    "AI Productivity Flow",
                    -1,
                    ctypes.byref(rect),
                    0x00000001 | 0x00000004 | 0x00000020,  # CENTER | VCENTER | SINGLELINE
                )
                user32.EndPaint(hwnd, ps)
                return 0
            if msg == 0x0002:  # WM_DESTROY
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        # Keep the callback alive for the process lifetime.
        global _SPLASH_WNDPROC
        _SPLASH_WNDPROC = WNDPROC(_wnd_proc)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        instance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASS()
        wc.lpfnWndProc = _SPLASH_WNDPROC
        wc.hInstance = instance
        wc.lpszClassName = _CLASS_NAME
        wc.hbrBackground = gdi32.CreateSolidBrush(0x002060FF)
        user32.RegisterClassW(ctypes.byref(wc))

        width, height = 460, 180
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        WS_POPUP = 0x80000000
        WS_VISIBLE = 0x10000000
        WS_EX_TOPMOST = 0x00000008
        WS_EX_TOOLWINDOW = 0x00000080
        hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            _CLASS_NAME,
            WINDOW_TITLE,
            WS_POPUP | WS_VISIBLE,
            x,
            y,
            width,
            height,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            return None
        user32.ShowWindow(hwnd, 5)
        user32.UpdateWindow(hwnd)
        # Pump once so the window actually paints before imports block the thread.
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        os.environ["VOICE_FLOW_EARLY_SPLASH_HWND"] = str(int(hwnd))
        return int(hwnd)
    except Exception:
        return None


_SPLASH_WNDPROC = None
