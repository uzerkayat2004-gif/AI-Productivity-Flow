"""Floating pill bar UI for Voice Flow using tkinter and Win32 extended styles."""

from __future__ import annotations

import ctypes
import math
import time
import tkinter as tk
from typing import Callable

from voice_flow.config import config

# Win32 Constants for non-activating window
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


class FloatingOverlayBar:
    """Always-on-top, non-activating floating pill bar that mirrors Wispr Flow's UI."""

    def __init__(
        self,
        root: tk.Tk,
        on_cancel: Callable[[], None],
        on_finish: Callable[[], None],
        get_audio_level: Callable[[], float],
    ) -> None:
        self.root = root
        self.on_cancel = on_cancel
        self.on_finish = on_finish
        self.get_audio_level = get_audio_level

        self.state = "HIDDEN"  # HIDDEN, RECORDING, PROCESSING, DONE
        self._anim_phase = 0.0

        # Window setup
        self.win = tk.Toplevel(root)
        self.win.withdraw()  # start hidden
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        # Make background transparent / dark pill
        self.win.config(bg="#000001")
        self.win.attributes("-transparentcolor", "#000001")

        # Dimensions
        self.width = config.bar_width
        self.height = config.bar_height

        # Canvas for custom drawn rounded pill & items
        self.canvas = tk.Canvas(
            self.win,
            width=self.width,
            height=self.height,
            bg="#000001",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Bind mouse clicks on canvas
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        self._position_window()
        self._apply_win32_styles()

    def _position_window(self) -> None:
        """Position the bar at bottom-center of primary display."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        x = (screen_w - self.width) // 2
        y = screen_h - self.height - config.bar_bottom_margin

        self.win.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _apply_win32_styles(self) -> None:
        """Apply Win32 WS_EX_NOACTIVATE so window never steals keyboard focus."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            if not hwnd:
                hwnd = self.win.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass  # Fallback gracefully if non-Windows or API failure

    def show_recording(self) -> None:
        """Switch state to RECORDING and make window visible."""
        self.state = "RECORDING"
        self._position_window()
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self._animate()

    def show_processing(self) -> None:
        """Switch state to PROCESSING."""
        self.state = "PROCESSING"

    def show_done(self) -> None:
        """Switch state to DONE, display brief confirmation, then hide."""
        self.state = "DONE"
        self.draw()
        self.root.after(config.done_display_ms, self.hide)

    def hide(self) -> None:
        """Hide the overlay window."""
        self.state = "HIDDEN"
        self.win.withdraw()

    def _on_canvas_click(self, event: tk.Event) -> None:
        """Handle clicks on ✕ cancel and ✓ finish buttons."""
        if self.state != "RECORDING":
            return

        x, y = event.x, event.y
        # Cancel button is on left (x < 50)
        if x < 50:
            self.on_cancel()
        # Finish button is on right (x > width - 50)
        elif x > self.width - 50:
            self.on_finish()

    def _animate(self) -> None:
        """Animation loop for waveform and processing spinner."""
        if self.state == "HIDDEN":
            return

        self._anim_phase += 0.15
        self.draw()

        if self.state in ("RECORDING", "PROCESSING"):
            self.root.after(40, self._animate)

    def draw(self) -> None:
        """Redraw the canvas based on current state."""
        self.canvas.delete("all")
        w, h = self.width, self.height

        # Draw dark rounded pill background
        r = config.bar_corner_radius
        self._draw_rounded_rect(0, 0, w, h, r, config.bar_bg)

        if self.state == "RECORDING":
            # 1. Left Cancel button (✕)
            self.canvas.create_text(
                28,
                h / 2,
                text="✕",
                fill=config.bar_cancel_color,
                font=(config.bar_font_family, 13, "bold"),
            )

            # 2. Center Waveform dots
            level = self.get_audio_level()
            num_dots = config.waveform_dot_count
            dot_r = config.waveform_dot_radius
            spacing = config.waveform_dot_spacing
            total_w = num_dots * (dot_r * 2 + spacing) - spacing
            start_x = (w - total_w) / 2

            for i in range(num_dots):
                cx = start_x + i * (dot_r * 2 + spacing) + dot_r
                cy_center = h / 2

                # Add a sine wave modulation + audio level scaling
                wave = math.sin(self._anim_phase + i * 0.6)
                offset = wave * (2 + level * config.waveform_max_amplitude)

                # Draw glowing animated dot/bar
                dot_h = max(dot_r * 2, abs(offset) * 2)
                self.canvas.create_oval(
                    cx - dot_r,
                    cy_center - dot_h / 2,
                    cx + dot_r,
                    cy_center + dot_h / 2,
                    fill=config.bar_accent,
                    outline="",
                )

            # 3. Right Finish button (✓)
            self.canvas.create_text(
                w - 28,
                h / 2,
                text="✓",
                fill=config.bar_finish_color,
                font=(config.bar_font_family, 15, "bold"),
            )

        elif self.state == "PROCESSING":
            # Animated sparkle / dots with "Processing..." text
            dots = "." * (int(self._anim_phase * 2) % 4)
            self.canvas.create_text(
                w / 2,
                h / 2,
                text=f"✦ Transcribing{dots}",
                fill=config.bar_fg,
                font=(config.bar_font_family, config.bar_font_size, "bold"),
            )

        elif self.state == "DONE":
            # Done state
            self.canvas.create_text(
                w / 2,
                h / 2,
                text="✓ Done",
                fill=config.bar_finish_color,
                font=(config.bar_font_family, config.bar_font_size, "bold"),
            )

    def _draw_rounded_rect(
        self, x1: float, y1: float, x2: float, y2: float, r: float, color: str
    ) -> None:
        """Helper to draw a smooth rounded rectangle on canvas."""
        points = [
            x1 + r,
            y1,
            x2 - r,
            y1,
            x2,
            y1,
            x2,
            y1 + r,
            x2,
            y2 - r,
            x2,
            y2,
            x2 - r,
            y2,
            x1 + r,
            y2,
            x1,
            y2,
            x1,
            y2 - r,
            x1,
            y1 + r,
            x1,
            y1,
        ]
        self.canvas.create_polygon(points, fill=color, smooth=True)
