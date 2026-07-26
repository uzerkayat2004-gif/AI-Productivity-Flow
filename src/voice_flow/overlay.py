"""Floating pill bar UI for Voice Flow — polished Wispr Flow-style overlay.

Uses tkinter with Win32 extended styles for a non-activating, always-on-top,
translucent dark pill bar with animated waveform, cancel/finish buttons,
and smooth state transitions.
"""

from __future__ import annotations

import ctypes
import math
import tkinter as tk
from typing import Callable

from voice_flow.config import config

# Win32 Constants
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000


class FloatingOverlayBar:
    """Always-on-top, non-activating floating pill bar that mirrors Wispr Flow's UI."""

    # Colors
    BG = "#161627"
    BG_HOVER = "#1e1e3a"
    CANCEL_NORMAL = "#8b8b9e"
    CANCEL_HOVER = "#ff6b6b"
    FINISH_NORMAL = "#8b8b9e"
    FINISH_HOVER = "#51cf66"
    WAVEFORM_BASE = "#4a4a6a"
    WAVEFORM_ACTIVE = "#7c6cf6"
    WAVEFORM_HOT = "#a78bfa"
    TEXT_PRIMARY = "#e8e8f0"
    TEXT_DIM = "#9090a8"
    PROCESSING_ACCENT = "#7c6cf6"
    DONE_GREEN = "#51cf66"
    BORDER_COLOR = "#2a2a4a"

    def __init__(
        self,
        root: tk.Tk | None = None,
        on_cancel: Callable[[], None] | None = None,
        on_finish: Callable[[], None] | None = None,
        get_audio_level: Callable[[], float] | None = None,
    ) -> None:
        self.root = root
        self.win = None
        self.canvas = None
        self.on_cancel = on_cancel or (lambda: None)
        self.on_finish = on_finish or (lambda: None)
        self.get_audio_level = get_audio_level or (lambda: 0.0)

        self.on_cancel_click = None
        self.on_finish_click = None

        self.state = "HIDDEN"  # HIDDEN, READY, RECORDING, PROCESSING, DONE
        self._anim_phase = 0.0
        self._hover_zone: str | None = None  # "cancel", "finish", or None

        self.width = 360
        self.height = 52
        self.padding = 16

    def _init_tk(self) -> None:
        if self.root is None:
            self.root = tk.Tk()
            self.root.withdraw()

        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.95)

        self._trans_color = "#010101"
        self.win.config(bg=self._trans_color)
        self.win.attributes("-transparentcolor", self._trans_color)

        self.canvas = tk.Canvas(
            self.win,
            width=self.width,
            height=self.height,
            bg=self._trans_color,
            highlightthickness=0,
            bd=0,
            cursor="arrow",
        )
        self.canvas.pack(fill="both", expand=True)

        self.drag_x = 0
        self.drag_y = 0
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)

        self._position_window()
        self.win.bind("<Map>", self._on_map)

    def run_loop(self) -> None:
        """Start the Tkinter event loop for floating overlay bar."""
        self._init_tk()
        self.show_ready()
        self.root.mainloop()

    def _on_map(self, _event: tk.Event) -> None:
        self._apply_win32_styles()
        self.win.unbind("<Map>")

    def _position_window(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - self.width) // 2
        y = screen_h - self.height - config.bar_bottom_margin
        self.win.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _apply_win32_styles(self) -> None:
        try:
            self.win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            if not hwnd:
                hwnd = self.win.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    # -- Public State API --

    def _run_on_ui(self, func: Callable[[], None]) -> None:
        if self.root and self.win:
            try:
                self.root.after(0, func)
            except Exception:
                pass

    def show_ready(self) -> None:
        """Display the idle system-wide floating bar (ready state)."""
        def _do():
            if not self.win: return
            self.state = "READY"
            self._anim_phase = 0.0
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
            self._draw()
        self._run_on_ui(_do)

    def show_recording(self, level_provider: Callable[[], float] | None = None) -> None:
        if level_provider:
            self.get_audio_level = level_provider
        def _do():
            if not self.win: return
            self.state = "RECORDING"
            self._anim_phase = 0.0
            self._position_window()
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
            self._animate()
        self._run_on_ui(_do)

    def show_processing(self) -> None:
        def _do():
            if not self.win: return
            self.state = "PROCESSING"
            self._anim_phase = 0.0
        self._run_on_ui(_do)

    def show_done(self, text: str = "") -> None:
        def _do():
            if not self.win: return
            self.state = "DONE"
            self._anim_phase = 0.0
            self._draw()
            self.root.after(config.done_display_ms, self.show_ready)
        self._run_on_ui(_do)

    def hide(self) -> None:
        def _do():
            if not self.win: return
            self.state = "HIDDEN"
            self.win.withdraw()
        self._run_on_ui(_do)

    # -- Mouse Events & Dragging --

    def _get_zone(self, x: int) -> str | None:
        if x < 52:
            return "cancel"
        if x > self.width - 52:
            return "finish"
        return None

    def _on_press(self, event: tk.Event) -> None:
        self.drag_x = event.x
        self.drag_y = event.y
        if self.state == "READY":
            if self.on_finish_click:
                self.on_finish_click()
            else:
                self.on_finish()
        elif self.state == "RECORDING":
            zone = self._get_zone(event.x)
            if zone == "cancel":
                if self.on_cancel_click:
                    self.on_cancel_click()
                else:
                    self.on_cancel()
            elif zone == "finish":
                if self.on_finish_click:
                    self.on_finish_click()
                else:
                    self.on_finish()

    def _on_drag(self, event: tk.Event) -> None:
        dx = event.x - self.drag_x
        dy = event.y - self.drag_y
        new_x = self.win.winfo_x() + dx
        new_y = self.win.winfo_y() + dy
        self.win.geometry(f"+{new_x}+{new_y}")

    def _on_motion(self, event: tk.Event) -> None:
        zone = self._get_zone(event.x)
        if zone != self._hover_zone:
            self._hover_zone = zone
            if zone in ("cancel", "finish") or self.state == "READY":
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.config(cursor="arrow")

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover_zone = None
        self.canvas.config(cursor="arrow")

    # -- Animation Loop --

    def _animate(self) -> None:
        if self.state == "HIDDEN":
            return
        self._anim_phase += 0.12
        self._draw()
        if self.state in ("RECORDING", "PROCESSING"):
            self.root.after(33, self._animate)

    # -- Drawing --

    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = self.width, self.height

        self._draw_pill(2, 2, w - 2, h - 2, h // 2 - 2, self.BG, self.BORDER_COLOR)

        if self.state == "READY":
            self._draw_ready(w, h)
        elif self.state == "RECORDING":
            self._draw_recording(w, h)
        elif self.state == "PROCESSING":
            self._draw_processing(w, h)
        elif self.state == "DONE":
            self._draw_done(w, h)

    def _draw_ready(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2
        # Green indicator dot
        c.create_oval(24, cy - 4, 32, cy + 4, fill=self.DONE_GREEN, outline="")
        c.create_text(w / 2 + 10, cy, text="Ready to do this and all • Click to speak", fill=self.TEXT_PRIMARY, font=(config.bar_font_family, 10, "bold"), anchor="center")

    def _draw_recording(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2

        cancel_color = self.CANCEL_HOVER if self._hover_zone == "cancel" else self.CANCEL_NORMAL
        cx_cancel = 28
        size = 6
        c.create_line(cx_cancel - size, cy - size, cx_cancel + size, cy + size, fill=cancel_color, width=2, capstyle="round")
        c.create_line(cx_cancel + size, cy - size, cx_cancel - size, cy + size, fill=cancel_color, width=2, capstyle="round")

        level = self.get_audio_level()
        num_bars = 15
        bar_width = 3
        bar_gap = 5
        total_w = num_bars * (bar_width + bar_gap) - bar_gap
        start_x = (w - total_w) / 2

        for i in range(num_bars):
            bx = start_x + i * (bar_width + bar_gap)
            wave = math.sin(self._anim_phase * 1.5 + i * 0.5)
            center_factor = 1.0 - abs(i - num_bars / 2) / (num_bars / 2) * 0.5
            bar_h = 4 + abs(wave) * (3 + level * 14) * center_factor

            color = self.WAVEFORM_HOT if level > 0.3 else (self.WAVEFORM_ACTIVE if level > 0.05 else self.WAVEFORM_BASE)
            c.create_rectangle(bx, cy - bar_h / 2, bx + bar_width, cy + bar_h / 2, fill=color, outline="", width=0)

        finish_color = self.FINISH_HOVER if self._hover_zone == "finish" else self.FINISH_NORMAL
        cx_finish = w - 28
        c.create_line(cx_finish - 7, cy, cx_finish - 2, cy + 5, fill=finish_color, width=2.5, capstyle="round")
        c.create_line(cx_finish - 2, cy + 5, cx_finish + 7, cy - 5, fill=finish_color, width=2.5, capstyle="round")

    def _draw_processing(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2
        dot_text = "·" * (int(self._anim_phase * 3) % 4)
        sparkle_x = w / 2 - 55
        alpha = abs(math.sin(self._anim_phase * 2))
        sparkle_color = self.PROCESSING_ACCENT if alpha > 0.5 else self.TEXT_DIM

        c.create_text(sparkle_x, cy, text="✦", fill=sparkle_color, font=(config.bar_font_family, 12), anchor="center")
        c.create_text(w / 2 + 5, cy, text=f"Transcribing{dot_text}", fill=self.TEXT_PRIMARY, font=(config.bar_font_family, 11), anchor="center")

    def _draw_done(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2
        circle_x = w / 2 - 45
        r = 8
        c.create_oval(circle_x - r, cy - r, circle_x + r, cy + r, fill=self.DONE_GREEN, outline="")
        c.create_line(circle_x - 3, cy, circle_x - 1, cy + 3, fill="white", width=2, capstyle="round")
        c.create_line(circle_x - 1, cy + 3, circle_x + 4, cy - 3, fill="white", width=2, capstyle="round")
        c.create_text(w / 2 + 10, cy, text="Done", fill=self.DONE_GREEN, font=(config.bar_font_family, 12, "bold"), anchor="center")

    def _draw_pill(self, x1: float, y1: float, x2: float, y2: float, radius: float, fill_color: str, border_color: str) -> None:
        r = radius
        pts_outer = self._pill_points(x1, y1, x2, y2, r)
        self.canvas.create_polygon(pts_outer, fill=border_color, smooth=True)
        pts_inner = self._pill_points(x1 + 1, y1 + 1, x2 - 1, y2 - 1, r - 1)
        self.canvas.create_polygon(pts_inner, fill=fill_color, smooth=True)

    @staticmethod
    def _pill_points(x1: float, y1: float, x2: float, y2: float, r: float) -> list[float]:
        return [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
