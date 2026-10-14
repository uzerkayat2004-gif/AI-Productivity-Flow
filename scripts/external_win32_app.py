#!/usr/bin/env python3
"""A standalone external Win32 application with a standard multiline EDIT control.

Runs as an independent external process (PID != Voice Flow test process) to prove
that Voice Flow pastes text reliably into standard third-party Windows applications
without relying on Notepad-specific controls or class names.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import threading
import time

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t)

def main():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t

    WS_OVERLAPPEDWINDOW = 0x00CF0000
    WS_VISIBLE = 0x10000000
    WS_CHILD = 0x40000000
    ES_MULTILINE = 0x0004
    ES_AUTOVSCROLL = 0x0040
    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010

    def py_wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wnd_proc = WNDPROC(py_wnd_proc)

    h_instance = kernel32.GetModuleHandleW(None)
    class_name = "VF_ExternalAppClass"

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HCURSOR),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = wnd_proc
    wc.hInstance = h_instance
    wc.lpszClassName = class_name
    wc.hbrBackground = 6  # COLOR_WINDOW + 1

    user32.RegisterClassExW(ctypes.byref(wc))

    hwnd_parent = user32.CreateWindowExW(
        0, class_name, "External Win32 Text Editor - Test Target",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        100, 100, 500, 400,
        None, None, h_instance, None
    )

    hwnd_edit = user32.CreateWindowExW(
        0, "EDIT", "",
        WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_AUTOVSCROLL,
        10, 10, 460, 340,
        hwnd_parent, None, h_instance, None
    )

    user32.ShowWindow(hwnd_parent, 5)  # SW_SHOW
    user32.UpdateWindow(hwnd_parent)
    user32.SetFocus(hwnd_edit)

    sys.stdout.write(f"HWND_PARENT:{hwnd_parent}\nHWND_EDIT:{hwnd_edit}\n")
    sys.stdout.flush()

    # Read stdin in a thread: if stdin closes or sends quit, exit
    def _read_stdin():
        try:
            sys.stdin.read()
        except Exception:
            pass
        user32.PostMessageW(hwnd_parent, WM_CLOSE, 0, 0)

    t = threading.Thread(target=_read_stdin, daemon=True)
    t.start()

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

if __name__ == "__main__":
    main()
