"""Crisp White Audio Flow Circular Button Widget.

Anchors strictly at the mouse release coordinates (x, y) at the end of selected text.
Displays 🔊 when idle, and ⏸/⏹ while playing.
STAYS 100% VISIBLE ON SCREEN during the entire audio playback until playback finishes
completely or user clicks to stop.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
import tkinter as tk
from typing import Callable

log = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


class AudioFlowFloatingWidget:
    """Crisp White circular audio button anchored strictly at selected text end."""

    SIZE = 34  # Crisp 34x34px circle button

    def __init__(self, root: tk.Tk | None = None, on_trigger: Callable[[str], None] | None = None) -> None:
        self.root = root
        self.win: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.on_trigger = on_trigger or (lambda text: None)
        self.on_stop = (lambda: None)

        self._is_visible = False
        self._is_playing = False
        self._current_text = ""
        self._pos_x = 100
        self._pos_y = 100
        self._hide_timer: threading.Timer | None = None
        self._pending_show: tuple[int, int, str] | None = None

    def attach_root(self, root: tk.Tk) -> None:
        """Attach to main Tkinter root window and replay an early selection."""
        self.root = root
        self._init_tk()
        pending = self._pending_show
        if pending is not None:
            self._pending_show = None
            self.show_at(*pending)

    def _init_tk(self) -> None:
        if self.root is None or self.win is not None:
            return

        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.98)

        self._trans_color = "#010101"
        self.win.config(bg=self._trans_color)
        self.win.attributes("-transparentcolor", self._trans_color)

        self.canvas = tk.Canvas(
            self.win,
            width=self.SIZE,
            height=self.SIZE,
            bg=self._trans_color,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_click)

        self._draw()

    def _apply_win32_noactivate(self) -> None:
        if not self.win:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            if not hwnd:
                hwnd = self.win.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def show_at(self, x: int, y: int, selected_text: str) -> None:
        """Display the crisp white circle button anchored strictly at (x, y)."""
        if not selected_text or not selected_text.strip():
            self.hide()
            return

        clean_text = selected_text.strip()
        if self.root is None:
            self._pending_show = (x, y, clean_text)
            return
        self._pending_show = None

        def _do():
            if not self.win:
                self._init_tk()
            if not self.win:
                return

            self._current_text = clean_text
            self._is_visible = True
            self._is_playing = False

            screen_w = self.root.winfo_screenwidth() if self.root else 1920
            screen_h = self.root.winfo_screenheight() if self.root else 1080

            self._pos_x = max(10, min(x + 4, screen_w - self.SIZE - 10))
            self._pos_y = max(10, min(y + 4, screen_h - self.SIZE - 10))

            self.win.geometry(f"{self.SIZE}x{self.SIZE}+{self._pos_x}+{self._pos_y}")
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_noactivate()
            self._draw()
            try:
                self.win.update()
            except Exception:
                pass

            self._reset_hide_timer()

        self._run_on_ui(_do)

    def hide(self) -> None:
        """Hide button, reset state, and invalidate a pre-Tk selection."""
        self._pending_show = None

        def _do():
            self._is_visible = False
            self._is_playing = False
            self._current_text = ""
            if self.win:
                self.win.withdraw()
            if self._hide_timer:
                self._hide_timer.cancel()
                self._hide_timer = None

        if self.root:
            self._run_on_ui(_do)
        else:
            _do()

    def set_playing(self, playing: bool) -> None:
        """Update playback state. WHILE PLAYING, STAY 100% VISIBLE ON SCREEN!"""
        def _do():
            self._is_playing = playing
            # Cancel hide timer while playing so button NEVER disappears during audio!
            if playing:
                if self._hide_timer:
                    self._hide_timer.cancel()
                    self._hide_timer = None
                if self.win and self._is_visible:
                    self.win.deiconify()
                    self.win.lift()
                    self.win.attributes("-topmost", True)
                    self._draw()
            else:
                self.hide()
        self._run_on_ui(_do)

    def _reset_hide_timer(self) -> None:
        if self._hide_timer:
            self._hide_timer.cancel()
        # Auto hide after 5s ONLY IF NOT PLAYING
        if not self._is_playing:
            self._hide_timer = threading.Timer(5.0, self.hide)
            self._hide_timer.daemon = True
            self._hide_timer.start()

    def _draw(self) -> None:
        if not self.canvas:
            return

        c = self.canvas
        c.delete("all")
        s = self.SIZE

        # Crisp Circle Button Container
        c.create_oval(1, 1, s - 1, s - 1, fill="#0f172a", outline="", width=0)
        c.create_oval(2, 2, s - 2, s - 2, fill="#ffffff", outline="#ffd700" if self._is_playing else "#64748b", width=1.5)

        cy = s / 2
        cx = s / 2

        if self._is_playing:
            # Minimalist Pause/Stop icon inside circle while playing
            c.create_text(cx, cy, text="⏸", fill="#0f172a", font=("Segoe UI Symbol", 10, "bold"), anchor="center")
        else:
            # Minimalist speaker icon
            c.create_text(cx, cy, text="🔊", fill="#0f172a", font=("Segoe UI Emoji", 11), anchor="center")

    def _on_click(self, _event: tk.Event) -> None:
        """Handle click: If playing, stop & hide. If idle, start reading."""
        if self._is_playing:
            if self.on_stop:
                self.on_stop()
            self.hide()
        else:
            text = self._current_text
            if text and self.on_trigger:
                self.set_playing(True)
                self.on_trigger(text)

    def _run_on_ui(self, func: Callable[[], None]) -> None:
        if self.root:
            try:
                self.root.after(0, func)
            except Exception:
                pass


audio_flow_widget = AudioFlowFloatingWidget()
