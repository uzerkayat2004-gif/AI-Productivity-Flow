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
    STAGE_MINIMAL = "minimal"
    STAGE_MODE_SELECT = "mode_select"
    STAGE_DEPTH_SELECT = "depth_select"

    def __init__(self, root: tk.Tk | None = None, on_trigger: Callable[..., None] | None = None) -> None:
        self.root = root
        self.win: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.on_trigger = on_trigger or (lambda text, mode="full", summary_depth=None: None)
        self.on_stop = (lambda: None)

        self._is_visible = False
        self._is_playing = False
        self._current_text = ""
        self._pos_x = 100
        self._pos_y = 100
        self._anchor_x = 100
        self._anchor_y = 100
        self._stage = self.STAGE_MINIMAL
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

    def _get_current_dimensions(self) -> tuple[int, int]:
        if self._stage == self.STAGE_MODE_SELECT:
            return 176, 34
        if self._stage == self.STAGE_DEPTH_SELECT:
            return 216, 34
        return 34, 34

    def show_at(self, x: int, y: int, selected_text: str) -> None:
        """Display the white circle button anchored strictly at (x, y)."""
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
            self._stage = self.STAGE_MINIMAL

            self._anchor_x = x + 4
            self._anchor_y = y + 4

            self._update_geometry_and_draw()
            self._reset_hide_timer()

        self._run_on_ui(_do)

    def _update_geometry_and_draw(self) -> None:
        if not self.win or not self.canvas:
            return
        w, h = self._get_current_dimensions()
        screen_w = self.root.winfo_screenwidth() if self.root else 1920
        screen_h = self.root.winfo_screenheight() if self.root else 1080

        self._pos_x = max(10, min(self._anchor_x, screen_w - w - 10))
        self._pos_y = max(10, min(self._anchor_y, screen_h - h - 10))

        self.canvas.config(width=w, height=h)
        self.win.geometry(f"{w}x{h}+{self._pos_x}+{self._pos_y}")
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self._apply_win32_noactivate()
        self._draw()
        try:
            self.win.update()
        except Exception:
            pass

    def hide(self) -> None:
        """Hide button, reset state, and invalidate a pre-Tk selection."""
        self._pending_show = None

        def _do():
            self._is_visible = False
            self._is_playing = False
            self._stage = self.STAGE_MINIMAL
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
            if playing:
                if self._hide_timer:
                    self._hide_timer.cancel()
                    self._hide_timer = None
                self._stage = self.STAGE_MINIMAL
                if self.win and self._is_visible:
                    self._update_geometry_and_draw()
            else:
                self.hide()
        self._run_on_ui(_do)

    def _reset_hide_timer(self, timeout: float = 5.0) -> None:
        if self._hide_timer:
            self._hide_timer.cancel()
        if not self._is_playing:
            self._hide_timer = threading.Timer(timeout, self.hide)
            self._hide_timer.daemon = True
            self._hide_timer.start()

    def _draw(self) -> None:
        if not self.canvas:
            return

        c = self.canvas
        c.delete("all")
        w, h = self._get_current_dimensions()

        if self._stage == self.STAGE_MINIMAL:
            s = self.SIZE
            c.create_oval(1, 1, s - 1, s - 1, fill="#0f172a", outline="", width=0)
            c.create_oval(2, 2, s - 2, s - 2, fill="#ffffff", outline="#ffd700" if self._is_playing else "#64748b", width=1.5)
            cy, cx = s / 2, s / 2
            if self._is_playing:
                c.create_text(cx, cy, text="⏸", fill="#0f172a", font=("Segoe UI Symbol", 10, "bold"), anchor="center")
            else:
                c.create_text(cx, cy, text="🔊", fill="#0f172a", font=("Segoe UI Emoji", 11), anchor="center")
        elif self._stage == self.STAGE_MODE_SELECT:
            c.create_rectangle(1, 1, w - 1, h - 1, fill="#0f172a", outline="#334155", width=1)
            c.create_rectangle(3, 3, 85, h - 3, fill="#ffffff", outline="#64748b", width=1)
            c.create_text(44, h / 2, text="Full Audio", fill="#0f172a", font=("Segoe UI", 9, "bold"), anchor="center")

            c.create_rectangle(89, 3, w - 3, h - 3, fill="#ff6b00", outline="#ff8533", width=1)
            c.create_text(89 + (w - 3 - 89) / 2, h / 2, text="⚡ Summary", fill="#ffffff", font=("Segoe UI", 9, "bold"), anchor="center")
        elif self._stage == self.STAGE_DEPTH_SELECT:
            c.create_rectangle(1, 1, w - 1, h - 1, fill="#0f172a", outline="#334155", width=1)

            btn_w = (w - 8) / 3
            # Quick
            c.create_rectangle(3, 3, 3 + btn_w - 2, h - 3, fill="#1e293b", outline="#ff6b00", width=1)
            c.create_text(3 + btn_w / 2 - 1, h / 2, text="Quick", fill="#ffffff", font=("Segoe UI", 8, "bold"), anchor="center")
            # Standard
            c.create_rectangle(3 + btn_w + 1, 3, 3 + 2 * btn_w - 1, h - 3, fill="#ff6b00", outline="#ff8533", width=1)
            c.create_text(3 + 1.5 * btn_w, h / 2, text="Standard", fill="#ffffff", font=("Segoe UI", 8, "bold"), anchor="center")
            # Detailed
            c.create_rectangle(3 + 2 * btn_w + 2, 3, w - 3, h - 3, fill="#1e293b", outline="#06cfe5", width=1)
            c.create_text(3 + 2.5 * btn_w + 1, h / 2, text="Detailed", fill="#ffffff", font=("Segoe UI", 8, "bold"), anchor="center")

    def _on_click(self, event: tk.Event) -> None:
        """Handle click based on current menu stage."""
        if self._is_playing:
            if self.on_stop:
                self.on_stop()
            self.hide()
            return

        text = self._current_text
        if not text:
            return

        if self._stage == self.STAGE_MINIMAL:
            self._stage = self.STAGE_MODE_SELECT
            self._update_geometry_and_draw()
            self._reset_hide_timer(8.0)
            return

        if self._stage == self.STAGE_MODE_SELECT:
            if event.x <= 87:
                # Full Audio selected
                self.set_playing(True)
                if self.on_trigger:
                    self.on_trigger(text, mode="full")
            else:
                # Summary selected -> go to depth selection stage
                self._stage = self.STAGE_DEPTH_SELECT
                self._update_geometry_and_draw()
                self._reset_hide_timer(8.0)
            return

        if self._stage == self.STAGE_DEPTH_SELECT:
            w, _ = self._get_current_dimensions()
            btn_w = (w - 8) / 3
            if event.x < 3 + btn_w:
                depth = "quick"
            elif event.x < 3 + 2 * btn_w:
                depth = "standard"
            else:
                depth = "detailed"

            self.set_playing(True)
            if self.on_trigger:
                self.on_trigger(text, mode="summary", summary_depth=depth)

    def _run_on_ui(self, func: Callable[[], None]) -> None:
        if self.root:
            try:
                self.root.after(0, func)
            except Exception:
                pass


audio_flow_widget = AudioFlowFloatingWidget()
