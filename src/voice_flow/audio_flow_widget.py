"""Sunrise White Audio Flow Circular Button Widget.

Anchors strictly at the mouse release coordinates (x, y) at the end of selected text.
Displays 🔊 when idle, and ⏸/⏹ with real-time speed control while playing.
STAYS 100% VISIBLE ON SCREEN during the entire audio playback until playback finishes
completely or user clicks to stop.

Visual language: "Sunrise" design system — spacious white glass cards with a warm
BORDER outline, ORANGE accents, INK text, rounded corners, and a chic 3x2 dot-grid
motif beside the mode labels (static ORANGE_SOFT when idle, cascading orange wave
while the summary flow is processing).
"""

from __future__ import annotations

import ctypes
import logging
import math
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageTk
from typing import Any, Callable

log = logging.getLogger(__name__)


def _get_font(size: int, bold: bool = True) -> Any:
    """Load high-legibility system TrueType font for supersampled PIL text rendering."""
    candidates = (
        ("segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf")
        if bold
        else ("segoeui.ttf", "arial.ttf")
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _enable_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness on Windows to prevent blurry rendering or clipping."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


_enable_dpi_awareness()

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# --- "Sunrise" design system --------------------------------------------------
ORANGE = "#FF6A00"
ORANGE_DEEP = "#E85D04"
ORANGE_SOFT = "#FFE3D0"
ORANGE_FAINT = "#FFF4EC"
ORANGE_BORDER = "#FFC59E"
WHITE = "#FFFFFF"
INK = "#241708"
GRAY = "#8A8A93"
GREEN = "#12B76A"
RED = "#F04438"
BORDER = "#FFD6BA"
BORDER_LIGHT = "#FFE8D8"

# Chic dot-grid motif (3x2) with a bounded cascading wave (80ms stagger).
WAVE_TONES = (ORANGE_SOFT, "#FFC29E", "#FF9E66", ORANGE, ORANGE_DEEP)
ANIM_INTERVAL_MS = 80
GRID_DOT_R = 1.3
GRID_SPACING = 3.6


def _is_short_text(text: str) -> bool:
    """Return True if text is non-empty and approximately half-page to one-page or shorter.

    A standard printed or single-spaced document page is ~350-400 words (or ~1,800 chars).
    Texts under ~1,800 chars or under 350 words qualify as short for summary purposes.
    """
    if not text or not text.strip():
        return False
    clean = text.strip()
    words = clean.split()
    return len(clean) < 1800 or len(words) < 350


is_short_text_for_summary = _is_short_text


class AudioFlowFloatingWidget:
    """Crisp Sunrise White circular audio button anchored strictly at selected text end."""

    SIZE = 30  # 30x30px circle button
    STAGE_MINIMAL = "minimal"
    STAGE_MODE_SELECT = "mode_select"
    STAGE_SHORT_WARNING = "short_warning"
    STAGE_DEPTH_SELECT = "depth_select"
    STAGE_SUMMARIZING = "summarizing"
    STAGE_PLAYBACK_CONTROL = "playback_control"

    SPEEDS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]

    def __init__(self, root: tk.Tk | None = None, on_trigger: Callable[..., None] | None = None) -> None:
        self.root = root
        self.win: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.on_trigger = on_trigger or (lambda text, mode="full", summary_depth=None: None)
        self.on_stop = (lambda: None)
        self.on_pause_toggle = (lambda: None)
        self.on_speed_change: Callable[[float], None] | None = None
        self.on_voice_change: Callable[[str], None] | None = None

        self._is_visible = False
        self._is_playing = False
        self._is_paused = False
        self._current_text = ""
        self._pos_x = 100
        self._pos_y = 100
        self._anchor_x = 100
        self._anchor_y = 100
        self._stage = self.STAGE_MINIMAL
        self._hide_timer: threading.Timer | None = None
        self._pending_show: tuple[int, int, str] | None = None
        self._show_generation = 0
        self._hover: int | None = None
        self._anim_after_id = None
        self._anim_frame = 0
        self._image_cache: dict[Any, Any] = {}
        self._icon_cache: dict[int, Image.Image] = {}
        self._is_dragging = False
        self._press_x = 0
        self._press_y = 0
        self._drag_root_x = 0
        self._drag_root_y = 0
        self._press_root_x = 0
        self._press_root_y = 0
        self._prev_dimensions = (30, 30)
        self._last_stage_change_time = 0.0

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

        self.win.config(bg=ORANGE_DEEP)

        try:
            from voice_flow.installer import get_icon_path
            ico = get_icon_path()
            if ico.exists() and hasattr(self.win, "iconbitmap"):
                self.win.iconbitmap(str(ico))
            p = ico.parent / "icon-32.png"
            if p.exists() and hasattr(self.win, "iconphoto"):
                self._icon_photo = tk.PhotoImage(file=str(p))
                self.win.iconphoto(False, self._icon_photo)
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self.win,
            width=self.SIZE,
            height=self.SIZE,
            bg=ORANGE_DEEP,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)

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

    def _apply_window_shape(self, w: int, h: int) -> None:
        """Natively clip the window boundary via Win32 SetWindowRgn for smooth, fringe-free edges."""
        if sys.platform != "win32" or not self.win:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            if not hwnd:
                hwnd = self.win.winfo_id()
            if self._stage == self.STAGE_MINIMAL:
                # Smooth elliptic region — border-color canvas bg eliminates white fringe
                rgn = ctypes.windll.gdi32.CreateEllipticRgn(0, 0, w + 1, h + 1)
            else:
                rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, 14, 14)
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

        # Swap background colors: circle stages use border color, card stages use white/dark card
        try:
            if self._stage == self.STAGE_MINIMAL:
                min_bg = "#3b3834" if self._is_theme_dark() else ORANGE_DEEP
                self.win.config(bg=min_bg)
                if self.canvas:
                    self.canvas.config(bg=min_bg)
            else:
                card_bg = "#20201f" if self._is_theme_dark() else WHITE
                self.win.config(bg=card_bg)
                if self.canvas:
                    self.canvas.config(bg=card_bg)
        except Exception:
            pass

    def _is_theme_dark(self) -> bool:
        try:
            from voice_flow.storage import storage
            return str(storage.get_setting("on_screen_ui_theme", "light") or "light").strip().lower() == "dark"
        except Exception:
            return False

    def _get_current_dimensions(self) -> tuple[int, int]:
        if self._stage == self.STAGE_MODE_SELECT:
            return 286, 32
        if self._stage == self.STAGE_SHORT_WARNING:
            return 384, 96
        if self._stage == self.STAGE_DEPTH_SELECT:
            return 265, 32
        if self._stage == self.STAGE_SUMMARIZING:
            return 160, 32
        if self._stage == self.STAGE_PLAYBACK_CONTROL:
            return 145, 32
        return self.SIZE, self.SIZE

    def _get_current_speed(self) -> float:
        from voice_flow.storage import storage
        try:
            return float(storage.get_setting("audio_flow_speed", 1.0) or 1.0)
        except Exception:
            return 1.0

    def _get_display_speed(self) -> str:
        spd = self._get_current_speed()
        if spd == int(spd):
            return f"{int(spd)}.0"
        return f"{spd:g}"

    def _set_speed(self, speed: float) -> None:
        from voice_flow.storage import storage
        speed_clamped = max(0.5, min(3.0, float(speed)))
        storage.save_setting("audio_flow_speed", speed_clamped)
        if self.on_speed_change:
            self.on_speed_change(speed_clamped)
        self._draw()

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
        self._show_generation += 1

        def _do():
            if not self.win:
                self._init_tk()
            if not self.win:
                return

            self._current_text = clean_text
            self._is_visible = True
            self._is_playing = False
            self._is_paused = False
            self._stage = self.STAGE_MINIMAL
            self._hover = None

            self._anchor_x = x + 4
            self._anchor_y = y + 4

            self._update_geometry_and_draw()
            self._reset_hide_timer()

        self._run_on_ui(_do)

    def _virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height) of the full virtual desktop for clamping."""
        if self.root is not None:
            try:
                vx = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
                vy = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
                vw = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
                vh = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
                if vw > 0 and vh > 0:
                    return vx, vy, vw, vh
            except Exception:
                pass
            return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        return 0, 0, 1920, 1080

    def _update_geometry_and_draw(self) -> None:
        if not self.win or not self.canvas:
            return
        w, h = self._get_current_dimensions()
        vx, vy, vw, vh = self._virtual_screen_bounds()

        self._pos_x = max(vx + 10, min(self._anchor_x, vx + vw - w - 10))
        self._pos_y = max(vy + 10, min(self._anchor_y, vy + vh - h - 10))

        self.canvas.config(width=w, height=h)
        self.win.geometry(f"{w}x{h}+{self._pos_x}+{self._pos_y}")
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self._apply_win32_noactivate()
        self._apply_window_shape(w, h)
        self._hover = None
        self._draw()
        self._ensure_animation()
        try:
            self.win.update()
        except Exception:
            pass

    def hide(self) -> None:
        """Hide button, reset state, and invalidate a pre-Tk selection."""
        self._pending_show = None
        generation = self._show_generation

        def _do():
            if generation != self._show_generation and self._is_playing:
                return
            self._is_visible = False
            self._is_playing = False
            self._is_paused = False
            self._stage = self.STAGE_MINIMAL
            self._current_text = ""
            self._hover = None
            self._stop_anim_loop()
            if self.win:
                try:
                    self.win.withdraw()
                except Exception:
                    pass
            if self._hide_timer:
                self._hide_timer.cancel()
                self._hide_timer = None

        if self.root:
            if threading.current_thread() is threading.main_thread():
                _do()
            else:
                self._run_on_ui(_do)
        else:
            _do()

    def contains_point(self, x: int, y: int) -> bool:
        """Check if screen point (x, y) falls inside the audio flow button window or interaction zone."""
        if not getattr(self, "_is_visible", False) or not self.win:
            return False
        try:
            # Primary coordinates from thread-safe Python state
            cur_x = getattr(self, "_pos_x", 0)
            cur_y = getattr(self, "_pos_y", 0)
            # Refine with window root coordinates if on main thread
            if threading.current_thread() is threading.main_thread():
                try:
                    rx = self.win.winfo_rootx()
                    ry = self.win.winfo_rooty()
                    if rx > 0 and ry > 0:
                        cur_x, cur_y = rx, ry
                except Exception:
                    pass

            w, h = self._get_current_dimensions()
            # Grace period for stage transitions (e.g. short warning -> depth select)
            if hasattr(self, "_last_stage_change_time") and (time.time() - self._last_stage_change_time < 1.2):
                prev_w, prev_h = getattr(self, "_prev_dimensions", (w, h))
                w = max(w, prev_w)
                h = max(h, prev_h)

            margin = 16
            return (cur_x - margin <= x <= cur_x + w + margin) and (cur_y - margin <= y <= cur_y + h + margin)
        except Exception:
            return False

    def set_playing(self, playing: bool) -> None:
        """Update playback state. Keep selection widget hidden during playback."""
        self._is_playing = bool(playing)
        if not playing:
            self._is_paused = False
            self._stage = self.STAGE_MINIMAL
        self.hide()

    def show_summarizing(self) -> None:
        """Hide selection widget while summary is generating."""
        self.hide()

    def set_paused(self, paused: bool) -> None:
        """Sync the widget's paused glyph with the engine's true pause state."""
        generation = self._show_generation

        def _do():
            if generation != self._show_generation:
                return
            if self._is_playing and self._is_paused != bool(paused):
                self._is_paused = bool(paused)
                self._draw()
        self._run_on_ui(_do)

    def _reset_hide_timer(self, timeout: float = 5.0) -> None:
        if self._hide_timer:
            self._hide_timer.cancel()
        if not self._is_playing:
            self._hide_timer = threading.Timer(timeout, self.hide)
            self._hide_timer.daemon = True
            self._hide_timer.start()

    def _get_highres_logo(self, target_size: int = 17) -> Image.Image | None:
        """Fetch and cache high-res application logo downsampled with Lanczos."""
        cached = getattr(self, "_icon_cache", {}).get(target_size)
        if cached is not None:
            return cached
        try:
            from voice_flow.installer import get_icon_path
            ico_base = get_icon_path().parent
            for candidate in ("icon-64.png", "icon-48.png", "icon-32.png", "icon-24.png"):
                p = ico_base / candidate
                if p.exists():
                    img = Image.open(p).convert("RGBA")
                    resized = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
                    if not hasattr(self, "_icon_cache"):
                        self._icon_cache = {}
                    self._icon_cache[target_size] = resized
                    return resized
        except Exception:
            pass
        return None

    def _render_minimal_image(self, is_hover: bool, is_playing: bool, is_paused: bool, anim_frame: int) -> ImageTk.PhotoImage:
        scale = 4  # 4x supersample for crisp antialiasing
        s = self.SIZE
        S = s * scale
        is_dark = self._is_theme_dark()

        if is_dark:
            # App Dark Studio palette: dark matte card with champagne/peach secondary accent
            border_col = (230, 176, 146) if (is_hover or is_playing) else (59, 56, 52)
            bg_col = (43, 37, 32) if (is_hover or is_playing) else (32, 32, 31)
        else:
            # Sunrise White ceramic disk with vibrant orange border
            border_col = (255, 95, 10) if (is_hover or is_playing) else (235, 88, 0)
            bg_col = (255, 248, 242) if (is_hover or is_playing) else (255, 255, 255)

        img = Image.new("RGB", (S, S), border_col)
        draw = ImageDraw.Draw(img)

        border_w = int(1.8 * scale) if (is_hover or is_playing) else int(1.6 * scale)

        # Outer filled circle — border fills from edge inward
        draw.ellipse([0, 0, S - 1, S - 1], fill=border_col)
        # Inner filled circle — ceramic interior
        inset = border_w
        draw.ellipse([inset, inset, S - 1 - inset, S - 1 - inset], fill=bg_col)

        cx = S / 2.0
        cy = S / 2.0

        if is_playing:
            # Rotating progress track and arc
            arc_m = 3.2 * scale
            if is_dark:
                track_col = (59, 56, 52)
                arc_col = (230, 176, 146)
                glyph_col = (245, 241, 234) if is_hover else (230, 176, 146)
            else:
                track_col = (255, 220, 195)
                arc_col = (235, 88, 0)
                glyph_col = (215, 60, 0) if is_hover else (235, 88, 0)

            draw.ellipse([arc_m, arc_m, S - arc_m, S - arc_m], outline=track_col, width=int(1.6 * scale))
            start = (anim_frame * 30) % 360
            draw.arc(
                [arc_m, arc_m, S - arc_m, S - arc_m],
                start=start,
                end=start + 90,
                fill=arc_col,
                width=int(2.0 * scale),
            )
            # Center vector glyph
            if is_paused:
                tri_r = 3.6 * scale
                pts = [
                    (cx - tri_r * 0.7, cy - tri_r),
                    (cx - tri_r * 0.7, cy + tri_r),
                    (cx + tri_r * 1.1, cy),
                ]
                draw.polygon(pts, fill=glyph_col)
            else:
                bar_w = 1.3 * scale
                bar_h = 4.2 * scale
                gap = 2.0 * scale
                draw.rounded_rectangle([cx - gap - bar_w, cy - bar_h, cx - gap, cy + bar_h], radius=0.8 * scale, fill=glyph_col)
                draw.rounded_rectangle([cx + gap, cy - bar_h, cx + gap + bar_w, cy + bar_h], radius=0.8 * scale, fill=glyph_col)
        else:
            # Crisp Acoustic Waveform
            if is_dark:
                c_deep = (245, 195, 168) if is_hover else (230, 176, 146)
                c_mid = (230, 176, 146) if is_hover else (212, 148, 116)
                c_dot = (255, 215, 195) if is_hover else (230, 176, 146)
            else:
                c_deep = (210, 60, 0) if not is_hover else (230, 75, 0)
                c_mid = (245, 90, 0) if not is_hover else (255, 110, 10)
                c_dot = (255, 140, 55)

            # Center pillar (bold & tall)
            h_center = (16.5 if is_hover else 15.0) * scale
            w_center = 3.2 * scale
            draw.rounded_rectangle(
                [cx - w_center / 2, cy - h_center / 2, cx + w_center / 2, cy + h_center / 2],
                radius=w_center / 2,
                fill=c_deep,
            )

            # Left & Right flanking pillars
            h_side = (11.0 if is_hover else 9.5) * scale
            w_side = 2.6 * scale
            gap = 4.8 * scale
            draw.rounded_rectangle(
                [cx - gap - w_side / 2, cy - h_side / 2, cx - gap + w_side / 2, cy + h_side / 2],
                radius=w_side / 2,
                fill=c_mid,
            )
            draw.rounded_rectangle(
                [cx + gap - w_side / 2, cy - h_side / 2, cx + gap + w_side / 2, cy + h_side / 2],
                radius=w_side / 2,
                fill=c_mid,
            )

            # Symmetrical satellite pulse dots
            r_dot = 1.15 * scale
            gap_dot = 8.2 * scale
            draw.ellipse(
                [cx - gap_dot - r_dot, cy - r_dot, cx - gap_dot + r_dot, cy + r_dot],
                fill=c_dot,
            )
            draw.ellipse(
                [cx + gap_dot - r_dot, cy - r_dot, cx + gap_dot + r_dot, cy + r_dot],
                fill=c_dot,
            )

        # Downsample with LANCZOS for maximum sharpness
        res = img.resize((s, s), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(res)

    def _render_mode_select_image(self, w: int, h: int, hover: int | None) -> ImageTk.PhotoImage:
        scale = 4
        W, H = w * scale, h * scale
        is_dark = self._is_theme_dark()

        card_bg = (32, 32, 31) if is_dark else (255, 255, 255)
        card_border = (59, 56, 52) if is_dark else (255, 214, 186)
        img = Image.new("RGB", (W, H), card_bg)
        draw = ImageDraw.Draw(img)

        # 1. Outer rounded card
        card_margin = 0.5 * scale
        draw.rounded_rectangle(
            [card_margin, card_margin, W - card_margin - 1, H - card_margin - 1],
            radius=7.5 * scale,
            fill=card_bg,
            outline=card_border,
            width=int(1.2 * scale),
        )

        font = _get_font(int(9.5 * scale), bold=True)

        # Two actions only: verbatim Read and NotebookLM Summary. Settings is
        # deliberately an icon, not a third Audio Flow mode.
        pills = [
            (4, 106, 0),
            (110, 222, 1),
            (226, 252, 2),
        ]
        for x1, x2, idx in pills:
            is_h = (hover == idx)
            px1, px2 = x1 * scale, x2 * scale
            py1, py2 = 3.5 * scale, (h - 3.5) * scale
            r = 5.0 * scale

            if is_dark:
                if is_h:
                    fill = (55, 44, 37)          # Warm dark tint
                    border = (230, 176, 146)     # Warm peach accent
                    text_col = (230, 176, 146)
                elif idx == 0:
                    fill = (43, 37, 32)          # Read default elevated card
                    border = (82, 64, 53)
                    text_col = (230, 176, 146)
                else:
                    fill = (40, 39, 37)          # Surface well
                    border = (59, 56, 52)
                    text_col = (245, 241, 234)   # Warm text
            else:
                if is_h:
                    fill = (255, 106, 0)
                    border = (232, 93, 4)
                    text_col = (255, 255, 255)
                elif idx == 0:
                    fill = (255, 246, 240)
                    border = (255, 195, 160)
                    text_col = (232, 93, 4)
                else:
                    fill = (255, 255, 255)
                    border = (255, 224, 204)
                    text_col = (36, 23, 8)

            draw.rounded_rectangle([px1, py1, px2, py2], radius=r, fill=fill, outline=border, width=int(1.1 * scale))

            if idx == 0:
                # Vector dialogue speech bubble
                bx1, by1, bx2, by2 = 20 * scale, 11 * scale, 31 * scale, 20.5 * scale
                draw.rounded_rectangle([bx1, by1, bx2, by2], radius=3.0 * scale, fill=text_col)
                draw.polygon([(23 * scale, 20.5 * scale), (26 * scale, 20.5 * scale), (21 * scale, 23 * scale)], fill=text_col)
                dot_c = ((55, 44, 37) if is_h else (43, 37, 32)) if is_dark else ((255, 106, 0) if is_h else (255, 246, 240))
                draw.ellipse([23 * scale, 14.5 * scale, 25 * scale, 16.5 * scale], fill=dot_c)
                draw.ellipse([26.5 * scale, 14.5 * scale, 28.5 * scale, 16.5 * scale], fill=dot_c)
                draw.text((35 * scale, 9.5 * scale), "Read", fill=text_col, font=font)
            elif idx == 1:
                # Vector speaker icon
                pts = [(123 * scale, 10 * scale), (118 * scale, 16 * scale), (121.5 * scale, 16 * scale), (120 * scale, 22 * scale), (125 * scale, 15 * scale), (122 * scale, 15 * scale)]
                draw.polygon(pts, fill=text_col)
                draw.text((130 * scale, 9.5 * scale), "Summary", fill=text_col, font=font)
        # Vector gear inside the settings icon pill.
        is_set_h = (hover == 2)
        gcx = 239.0 * scale
        gcy = (h / 2.0) * scale
        gr = 4.8 * scale
        if is_dark:
            gear_col = (230, 176, 146) if is_set_h else (182, 174, 162)
            gear_bg = (55, 44, 37) if is_set_h else (40, 39, 37)
        else:
            gear_col = (255, 255, 255) if is_set_h else (90, 78, 70)
            gear_bg = (255, 106, 0) if is_set_h else (255, 255, 255)
        for i in range(8):
            ang = i * (math.pi / 4.0)
            gx1 = gcx + (gr - 1.0 * scale) * math.cos(ang)
            gy1 = gcy + (gr - 1.0 * scale) * math.sin(ang)
            gx2 = gcx + (gr + 2.0 * scale) * math.cos(ang)
            gy2 = gcy + (gr + 2.0 * scale) * math.sin(ang)
            draw.line([gx1, gy1, gx2, gy2], fill=gear_col, width=int(1.6 * scale))
        draw.ellipse([gcx - gr, gcy - gr, gcx + gr, gcy + gr], fill=gear_col)
        hole_r = gr * 0.42
        draw.ellipse([gcx - hole_r, gcy - hole_r, gcx + hole_r, gcy + hole_r], fill=gear_bg)

        # Dot grid / grip handle (275, 279) - glowing highlight on hover
        is_grip_h = (hover == 3)
        if is_dark:
            dot_col = (230, 176, 146) if is_grip_h else (113, 108, 100)
        else:
            dot_col = (255, 106, 0) if is_grip_h else (255, 190, 150)
        dot_r = 1.3 * scale
        for col_x in (265, 269):
            for row_y in (10, 16, 22):
                dx = col_x * scale
                dy = row_y * scale
                draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=dot_col)

        res = img.resize((w, h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(res)

    def _render_short_warning_image(self, w: int, h: int, hover: int | None, anim_frame: int = 0) -> ImageTk.PhotoImage:
        scale = 4
        W, H = w * scale, h * scale
        is_dark = self._is_theme_dark()
        card_bg = (32, 32, 31) if is_dark else (255, 255, 255)
        card_border = (59, 56, 52) if is_dark else (255, 214, 186)
        img = Image.new("RGB", (W, H), card_bg)
        draw = ImageDraw.Draw(img)

        # 1. Outer rounded card
        card_margin = 0.5 * scale
        draw.rounded_rectangle(
            [card_margin, card_margin, W - card_margin - 1, H - card_margin - 1],
            radius=11.0 * scale,
            fill=card_bg,
            outline=card_border,
            width=int(1.2 * scale),
        )

        # Row 1: Warning Notice Banner (y: 6 to 46, height 40 base)
        ny1 = 6.0 * scale
        ny2 = 46.0 * scale
        banner_bg = (43, 37, 32) if is_dark else (255, 248, 240)
        banner_border = (82, 64, 53) if is_dark else (255, 222, 198)
        banner_text = (230, 176, 146) if is_dark else (125, 60, 15)
        draw.rounded_rectangle(
            [6.0 * scale, ny1, (w - 6.0) * scale, ny2],
            radius=6.5 * scale,
            fill=banner_bg,
            outline=banner_border,
            width=int(1.1 * scale),
        )

        font_notice = _get_font(int(11.4 * scale), bold=True)
        notice_text = "💡 Summary is for long docs · Use Read for short text"
        bbox_n = draw.textbbox((0, 0), notice_text, font=font_notice)
        tw_n = bbox_n[2] - bbox_n[0]
        th_n = bbox_n[3] - bbox_n[1]
        cy_n = (ny1 + ny2) / 2.0
        avail_w = (w - 48.0) * scale
        start_nx = 6.0 * scale + max(6.0 * scale, (avail_w - tw_n) / 2.0)
        draw.text((start_nx, cy_n - th_n / 2.0 - bbox_n[1]), notice_text, fill=banner_text, font=font_notice)

        # Animated wave dots on Row 1 (at right: 356, 365; y: 20, 26, 32)
        dot_r = 1.55 * scale
        wave_rgb = [
            (55, 44, 37),
            (82, 64, 53),
            (182, 123, 94),
            (212, 148, 116),
            (230, 176, 146),
        ] if is_dark else [
            (255, 227, 208),
            (255, 194, 158),
            (255, 158, 102),
            (255, 106, 0),
            (232, 93, 4),
        ]
        for col_i, col_x in enumerate([356, 365]):
            for row_i, row_y in enumerate([20, 26, 32]):
                idx = row_i * 2 + col_i
                col_rgb = wave_rgb[(anim_frame + idx) % len(wave_rgb)]
                dx = col_x * scale
                dy = row_y * scale
                draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=col_rgb)

        # Row 2: Action buttons (y: 52 to 90, height 38 base)
        by1 = 52.0 * scale
        by2 = 90.0 * scale
        b_cy = (by1 + by2) / 2.0
        r_pill = 7.0 * scale

        # Button 0: "⚡ Use Read" (6..186)
        is_read_h = (hover == 0)
        if is_dark:
            p0_fill = (55, 44, 37) if is_read_h else (43, 37, 32)
            p0_border = (230, 176, 146) if is_read_h else (82, 64, 53)
            p0_text_col = (230, 176, 146)
        else:
            p0_fill = (255, 106, 0) if is_read_h else (255, 246, 240)
            p0_border = (232, 93, 4) if is_read_h else (255, 185, 145)
            p0_text_col = (255, 255, 255) if is_read_h else (232, 93, 4)
        draw.rounded_rectangle(
            [6.0 * scale, by1, 186.0 * scale, by2],
            radius=r_pill,
            fill=p0_fill,
            outline=p0_border,
            width=int(1.1 * scale),
        )

        font_btn = _get_font(int(10.8 * scale), bold=True)
        read_lbl = "⚡ Use Read"
        bbox_r = draw.textbbox((0, 0), read_lbl, font=font_btn)
        tw_r = bbox_r[2] - bbox_r[0]
        th_r = bbox_r[3] - bbox_r[1]
        p0_cx = (6.0 + 186.0) * scale / 2.0
        draw.text((p0_cx - tw_r / 2.0, b_cy - th_r / 2.0 - bbox_r[1]), read_lbl, fill=p0_text_col, font=font_btn)

        # Button 1: "Make Anyway →" (192..w - 6)
        is_make_h = (hover == 1)
        if is_dark:
            p1_fill = (55, 44, 37) if is_make_h else (40, 39, 37)
            p1_border = (230, 176, 146) if is_make_h else (59, 56, 52)
            p1_text_col = (230, 176, 146) if is_make_h else (245, 241, 234)
        else:
            p1_fill = (255, 106, 0) if is_make_h else (255, 255, 255)
            p1_border = (232, 93, 4) if is_make_h else (255, 214, 186)
            p1_text_col = (255, 255, 255) if is_make_h else (45, 30, 15)
        draw.rounded_rectangle(
            [192.0 * scale, by1, (w - 6.0) * scale, by2],
            radius=r_pill,
            fill=p1_fill,
            outline=p1_border,
            width=int(1.1 * scale),
        )

        make_lbl = "Make Anyway →"
        bbox_m = draw.textbbox((0, 0), make_lbl, font=font_btn)
        tw_m = bbox_m[2] - bbox_m[0]
        th_m = bbox_m[3] - bbox_m[1]
        p1_cx = (192.0 + (w - 6.0)) * scale / 2.0
        draw.text((p1_cx - tw_m / 2.0, b_cy - th_m / 2.0 - bbox_m[1]), make_lbl, fill=p1_text_col, font=font_btn)

        res = img.resize((w, h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(res)

    def _render_depth_select_image(self, w: int, h: int, hover: int | None, anim_frame: int) -> ImageTk.PhotoImage:
        scale = 4
        W, H = w * scale, h * scale
        is_dark = self._is_theme_dark()
        card_bg = (32, 32, 31) if is_dark else (255, 255, 255)
        card_border = (59, 56, 52) if is_dark else (255, 214, 186)
        img = Image.new("RGB", (W, H), card_bg)
        draw = ImageDraw.Draw(img)

        # 1. Outer rounded card with subtle warm Sunrise border
        card_margin = 0.5 * scale
        draw.rounded_rectangle(
            [card_margin, card_margin, W - card_margin - 1, H - card_margin - 1],
            radius=7.5 * scale,
            fill=card_bg,
            outline=card_border,
            width=int(1.2 * scale),
        )

        font = _get_font(int(8.5 * scale), bold=True)

        # 3 refined depth options: Short, Balanced, Deep Dive
        pills = [
            (4.0, 78.0, 0, "Short"),
            (82.0, 170.0, 1, "Balanced"),
            (174.0, 246.0, 2, "Deep Dive"),
        ]
        cy = (h / 2.0) * scale
        py1, py2 = 3.5 * scale, (h - 3.5) * scale
        r = 5.0 * scale

        for x1, x2, idx, label in pills:
            is_h = (hover == idx)
            px1, px2 = x1 * scale, x2 * scale

            if is_dark:
                if is_h:
                    fill = (55, 44, 37)
                    border = (230, 176, 146)
                    text_col = (230, 176, 146)
                    icon_col = (230, 176, 146)
                elif idx == 1:
                    # Balanced: elevated warm card
                    fill = (43, 37, 32)
                    border = (82, 64, 53)
                    text_col = (230, 176, 146)
                    icon_col = (230, 176, 146)
                else:
                    fill = (40, 39, 37)
                    border = (59, 56, 52)
                    text_col = (245, 241, 234)
                    icon_col = (182, 174, 162)
            else:
                if is_h:
                    fill = (255, 106, 0)
                    border = (232, 93, 4)
                    text_col = (255, 255, 255)
                    icon_col = (255, 255, 255)
                elif idx == 1:
                    # Balanced: subtle warm ivory glow as default balance
                    fill = (255, 250, 246)
                    border = (255, 205, 175)
                    text_col = (36, 23, 8)
                    icon_col = (232, 93, 4)
                else:
                    # Short & Deep Dive: pristine ceramic white
                    fill = (255, 255, 255)
                    border = (255, 224, 204)
                    text_col = (36, 23, 8)
                    icon_col = (245, 90, 0)

            draw.rounded_rectangle([px1, py1, px2, py2], radius=r, fill=fill, outline=border, width=int(1.1 * scale))

            # Dynamic horizontal & vertical centering
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            iw = 10.0 * scale
            gap = 3.2 * scale
            cw = iw + gap + tw
            p_w = px2 - px1
            start_x = px1 + (p_w - cw) / 2.0
            icx = start_x + iw / 2.0
            icy = cy
            tx = start_x + iw + gap
            ty = cy - th / 2.0 - bbox[1]

            # Vector icons
            if idx == 0:
                # Short: sharp modern lightning bolt
                pts_bolt = [
                    (icx + 0.6 * scale, icy - 5.2 * scale),
                    (icx - 3.4 * scale, icy - 0.2 * scale),
                    (icx - 0.4 * scale, icy - 0.2 * scale),
                    (icx - 1.0 * scale, icy + 5.2 * scale),
                    (icx + 3.2 * scale, icy + 0.2 * scale),
                    (icx + 0.2 * scale, icy + 0.2 * scale),
                ]
                draw.polygon(pts_bolt, fill=icon_col)
            elif idx == 1:
                # Balanced: 4-pointed diamond sparkle starburst with satellite glint
                r_maj = 5.0 * scale
                r_min = 1.3 * scale
                star_pts = [
                    (icx, icy - r_maj),
                    (icx + r_min, icy - r_min),
                    (icx + r_maj, icy),
                    (icx + r_min, icy + r_min),
                    (icx, icy + r_maj),
                    (icx - r_min, icy + r_min),
                    (icx - r_maj, icy),
                    (icx - r_min, icy - r_min),
                ]
                draw.polygon(star_pts, fill=icon_col)
                draw.ellipse(
                    [icx + 3.4 * scale, icy - 4.4 * scale, icx + 4.8 * scale, icy - 3.0 * scale],
                    fill=icon_col,
                )
            elif idx == 2:
                # Deep Dive: open book / layered pages with spine highlight
                pw = 3.8 * scale
                ph = 4.6 * scale
                draw.polygon([
                    (icx, icy + ph),
                    (icx - pw, icy + ph - 1.0 * scale),
                    (icx - pw, icy - ph + 1.0 * scale),
                    (icx, icy - ph),
                ], fill=icon_col)
                draw.polygon([
                    (icx, icy + ph),
                    (icx + pw, icy + ph - 1.0 * scale),
                    (icx + pw, icy - ph + 1.0 * scale),
                    (icx, icy - ph),
                ], fill=icon_col)
                spine_col = fill if is_h else (255, 255, 255)
                draw.line([(icx, icy - ph + 0.5 * scale), (icx, icy + ph - 0.5 * scale)], fill=spine_col, width=int(1.0 * scale))

            draw.text((tx, ty), label, fill=text_col, font=font)

        # Wave dot grid (columns at 253, 258; rows at 10, 16, 22)
        is_grip_h = (hover == 3)
        dot_r = 1.35 * scale
        wave_rgb = [
            (255, 227, 208),
            (255, 194, 158),
            (255, 158, 102),
            (255, 106, 0),
            (232, 93, 4),
        ]
        for col_i, col_x in enumerate([253, 258]):
            for row_i, row_y in enumerate([10, 16, 22]):
                idx_dot = row_i * 2 + col_i
                col_rgb = (255, 106, 0) if is_grip_h else wave_rgb[(anim_frame + idx_dot) % len(wave_rgb)]
                dx = col_x * scale
                dy = row_y * scale
                draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=col_rgb)

        res = img.resize((w, h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(res)
    def _render_summarizing_image(self, w: int, h: int, anim_frame: int) -> ImageTk.PhotoImage:
        scale = 4
        W, H = w * scale, h * scale
        is_dark = self._is_theme_dark()
        card_bg = (32, 32, 31) if is_dark else (255, 255, 255)
        card_border = (59, 56, 52) if is_dark else (255, 214, 186)
        img = Image.new("RGB", (W, H), card_bg)
        draw = ImageDraw.Draw(img)

        card_margin = 0.5 * scale
        draw.rounded_rectangle(
            [card_margin, card_margin, W - card_margin - 1, H - card_margin - 1],
            radius=7.5 * scale,
            fill=card_bg,
            outline=card_border,
            width=int(1.2 * scale),
        )

        pill_bg = (43, 37, 32) if is_dark else (255, 106, 0)
        pill_border = (82, 64, 53) if is_dark else (232, 93, 4)
        pill_text = (230, 176, 146) if is_dark else (255, 255, 255)

        draw.rounded_rectangle(
            [4 * scale, 3.5 * scale, 126 * scale, (h - 3.5) * scale],
            radius=5.0 * scale,
            fill=pill_bg,
            outline=pill_border,
            width=int(1.1 * scale),
        )

        font = _get_font(int(9.5 * scale), bold=True)
        pts = [
            (18 * scale, 10.5 * scale),
            (14 * scale, 15.5 * scale),
            (17 * scale, 15.5 * scale),
            (15.5 * scale, 21.5 * scale),
            (20 * scale, 15 * scale),
            (17.5 * scale, 15 * scale),
        ]
        draw.polygon(pts, fill=pill_text)
        draw.text((24 * scale, 9.5 * scale), "Summarizing…", fill=pill_text, font=font)

        dot_r = 1.35 * scale
        wave_rgb = [
            (55, 44, 37),
            (82, 64, 53),
            (182, 123, 94),
            (212, 148, 116),
            (230, 176, 146),
        ] if is_dark else [
            (255, 227, 208),
            (255, 194, 158),
            (255, 158, 102),
            (255, 106, 0),
            (232, 93, 4),
        ]
        for col_i, col_x in enumerate([138, 144]):
            for row_i, row_y in enumerate([10, 16, 22]):
                idx = row_i * 2 + col_i
                col_rgb = wave_rgb[(anim_frame + idx) % len(wave_rgb)]
                dx = col_x * scale
                dy = row_y * scale
                draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=col_rgb)

        res = img.resize((w, h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(res)

    def _render_playback_image(self, w: int, h: int, hover: int | None) -> ImageTk.PhotoImage:
        scale = 4
        W, H = w * scale, h * scale
        is_dark = self._is_theme_dark()
        card_bg = (32, 32, 31) if is_dark else (255, 255, 255)
        card_border = (59, 56, 52) if is_dark else (255, 214, 186)
        img = Image.new("RGB", (W, H), card_bg)
        draw = ImageDraw.Draw(img)

        card_margin = 0.5 * scale
        draw.rounded_rectangle(
            [card_margin, card_margin, W - card_margin - 1, H - card_margin - 1],
            radius=7.5 * scale,
            fill=card_bg,
            outline=card_border,
            width=int(1.2 * scale),
        )

        font = _get_font(int(9.5 * scale), bold=True)
        spd_disp = self._get_display_speed()

        # 0: Pause/Play (4..42, center = 23)
        if is_dark:
            p0_fill = (55, 44, 37) if hover == 0 else (40, 39, 37)
            p0_border = (230, 176, 146) if hover == 0 else (59, 56, 52)
            p0_glyph_col = (230, 176, 146) if hover == 0 else (245, 241, 234)
        else:
            p0_fill = (255, 242, 235) if hover == 0 else (255, 255, 255)
            p0_border = (255, 106, 0) if hover == 0 else (255, 214, 186)
            p0_glyph_col = (232, 93, 4) if hover == 0 else (255, 106, 0)
        draw.rounded_rectangle([4 * scale, 3.5 * scale, 42 * scale, (h - 3.5) * scale], radius=5.0 * scale, fill=p0_fill, outline=p0_border, width=int(1.1 * scale))
        if self._is_paused:
            pts = [(20.5 * scale, 11.5 * scale), (20.5 * scale, 20.5 * scale), (27.5 * scale, 16 * scale)]
            draw.polygon(pts, fill=p0_glyph_col)
        else:
            draw.rounded_rectangle([20 * scale, 11.5 * scale, 22.5 * scale, 20.5 * scale], radius=0.8 * scale, fill=p0_glyph_col)
            draw.rounded_rectangle([24.5 * scale, 11.5 * scale, 27 * scale, 20.5 * scale], radius=0.8 * scale, fill=p0_glyph_col)

        # 1: Stop (46..82, center = 64)
        if is_dark:
            p1_fill = (60, 25, 25) if hover == 1 else (40, 39, 37)
            p1_border = (248, 113, 113) if hover == 1 else (59, 56, 52)
            p1_col = (248, 113, 113) if hover == 1 else (245, 241, 234)
        else:
            p1_fill = (255, 238, 238) if hover == 1 else (255, 255, 255)
            p1_border = (240, 68, 56) if hover == 1 else (255, 214, 186)
            p1_col = (240, 68, 56) if hover == 1 else (36, 23, 8)
        draw.rounded_rectangle([46 * scale, 3.5 * scale, 82 * scale, (h - 3.5) * scale], radius=5.0 * scale, fill=p1_fill, outline=p1_border, width=int(1.1 * scale))
        draw.rounded_rectangle([60 * scale, 12 * scale, 68 * scale, 20 * scale], radius=1.5 * scale, fill=p1_col)

        # 2: Speed (86..140, center = 113)
        if is_dark:
            p2_fill = (55, 44, 37) if hover == 2 else (43, 37, 32)
            p2_border = (230, 176, 146) if hover == 2 else (82, 64, 53)
            p2_fg = (230, 176, 146)
        else:
            p2_fill = (255, 133, 51) if hover == 2 else (255, 106, 0)
            p2_border = (232, 93, 4)
            p2_fg = (255, 255, 255)
        draw.rounded_rectangle([86 * scale, 3.5 * scale, 140 * scale, (h - 3.5) * scale], radius=5.0 * scale, fill=p2_fill, outline=p2_border, width=int(1.1 * scale))
        pts = [
            (96 * scale, 11 * scale),
            (92.5 * scale, 15.5 * scale),
            (95 * scale, 15.5 * scale),
            (93.5 * scale, 21 * scale),
            (97.5 * scale, 15 * scale),
            (95.5 * scale, 15 * scale),
        ]
        draw.polygon(pts, fill=p2_fg)
        draw.text((99 * scale, 9.5 * scale), f"{spd_disp}x", fill=p2_fg, font=font)

        res = img.resize((w, h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(res)

    def _draw(self) -> None:
        if not self.canvas:
            return

        c = self.canvas
        c.delete("all")
        w, h = self._get_current_dimensions()
        is_dark = self._is_theme_dark()

        try:
            if self._stage == self.STAGE_MINIMAL:
                is_h = self._hover is not None
                key = ("minimal", is_h, self._is_playing, self._is_paused, (self._anim_frame % 12) if self._is_playing else 0, is_dark)
                if key not in self._image_cache:
                    self._image_cache[key] = self._render_minimal_image(is_h, self._is_playing, self._is_paused, self._anim_frame)
                photo = self._image_cache[key]
                c.create_image(0, 0, image=photo, anchor="nw")

            elif self._stage == self.STAGE_MODE_SELECT:
                key = ("mode_select", self._hover, is_dark)
                if key not in self._image_cache:
                    self._image_cache[key] = self._render_mode_select_image(w, h, self._hover)
                photo = self._image_cache[key]
                c.create_image(0, 0, image=photo, anchor="nw")

            elif self._stage == self.STAGE_SHORT_WARNING:
                key = ("short_warning", self._hover, self._anim_frame % len(WAVE_TONES), is_dark)
                if key not in self._image_cache:
                    self._image_cache[key] = self._render_short_warning_image(w, h, self._hover, self._anim_frame)
                photo = self._image_cache[key]
                c.create_image(0, 0, image=photo, anchor="nw")

            elif self._stage == self.STAGE_DEPTH_SELECT:
                key = ("depth_select", self._hover, self._anim_frame % len(WAVE_TONES), is_dark)
                if key not in self._image_cache:
                    self._image_cache[key] = self._render_depth_select_image(w, h, self._hover, self._anim_frame)
                photo = self._image_cache[key]
                c.create_image(0, 0, image=photo, anchor="nw")

            elif self._stage == self.STAGE_SUMMARIZING:
                key = ("summarizing", self._anim_frame % len(WAVE_TONES), is_dark)
                if key not in self._image_cache:
                    self._image_cache[key] = self._render_summarizing_image(w, h, self._anim_frame)
                photo = self._image_cache[key]
                c.create_image(0, 0, image=photo, anchor="nw")

            elif self._stage == self.STAGE_PLAYBACK_CONTROL:
                spd_disp = self._get_display_speed()
                key = ("playback", self._hover, self._is_paused, spd_disp, is_dark)
                if key not in self._image_cache:
                    self._image_cache[key] = self._render_playback_image(w, h, self._hover)
                photo = self._image_cache[key]
                c.create_image(0, 0, image=photo, anchor="nw")
        except Exception:
            # Fallback for mock canvas environments or testing without display
            self._draw_fallback(c, w, h)

    def _draw_fallback(self, c: tk.Canvas, w: int, h: int) -> None:
        """Pure canvas geometry fallback for headless or mock test environments."""
        is_dark = self._is_theme_dark()
        ink_col = "#f5f1ea" if is_dark else INK
        border_col = "#3b3834" if is_dark else BORDER
        pill_bg = "#282725" if is_dark else WHITE
        btn_txt = "#20201f" if is_dark else WHITE
        accent_col = "#e6b092" if is_dark else ORANGE

        if self._stage == self.STAGE_MINIMAL:
            pad = 1
            if is_dark:
                fill = "#282725" if (self._hover is not None or self._is_playing) else "#20201f"
                outline = "#e6b092" if (self._hover is not None or self._is_playing) else "#3b3834"
                glyph_col = "#e6b092" if (self._hover is not None or self._is_playing) else "#d49474"
            else:
                fill = "#FFF8F2" if (self._hover is not None or self._is_playing) else WHITE
                outline = "#FF5F0A" if (self._hover is not None or self._is_playing) else ORANGE_DEEP
                glyph_col = ORANGE_DEEP if not (self._hover is not None or self._is_playing) else "#D63C00"
            c.create_oval(pad, pad, w - pad, h - pad, fill=fill, outline=outline, width=2)
            glyph = "⏸" if self._is_playing and not self._is_paused else ("▶" if self._is_playing else "♫")
            c.create_text(w / 2, h / 2, text=glyph, fill=glyph_col, font=("Segoe UI", 9, "bold"), anchor="center")
        elif self._stage == self.STAGE_MODE_SELECT:
            self._draw_card(c, w, h)
            self._draw_pill(c, 4, 106, h, active=True, hovered=self._hover == 0)
            c.create_text(55, h / 2, text="🔊 Read", fill=btn_txt, font=("Segoe UI", 8, "bold"), anchor="center")
            self._draw_pill(c, 110, 222, h, hovered=self._hover == 1)
            c.create_text(166, h / 2, text="⚡ Summary", fill=accent_col if self._hover == 1 else ink_col, font=("Segoe UI", 8, "bold"), anchor="center")
            self._draw_pill(c, 226, 252, h, hovered=self._hover == 2)
            c.create_text(239, h / 2, text="⚙", fill=accent_col if self._hover == 2 else ink_col, font=("Segoe UI Symbol", 8), anchor="center")
            self._draw_grid(c, 266)
        elif self._stage == self.STAGE_SHORT_WARNING:
            self._draw_card(c, w, h)
            banner_bg = "#372c25" if is_dark else "#FFF8F0"
            banner_fg = "#e6b092" if is_dark else "#7D3C0F"
            self._rrect(c, 6, 6, w - 6, 46, 6, banner_bg)
            c.create_text(w / 2, 26, text="💡 Summary is for long docs · Use Read for short text", fill=banner_fg, font=("Segoe UI", 11, "bold"), anchor="center")
            self._draw_pill(c, 6, 186, 90, hovered=self._hover == 0, base_color="#d49474" if is_dark else "#FFB482", hover_color=accent_col)
            c.create_text(96, 71, text="⚡ Use Read", fill=btn_txt if self._hover == 0 else accent_col, font=("Segoe UI", 10, "bold"), anchor="center")
            self._draw_pill(c, 192, w - 6, 90, hovered=self._hover == 1, base_color=border_col, hover_color=accent_col)
            c.create_text(285, 71, text="Make Anyway →", fill=accent_col if self._hover == 1 else ink_col, font=("Segoe UI", 10, "bold"), anchor="center")
        elif self._stage == self.STAGE_DEPTH_SELECT:
            self._draw_card(c, w, h)
            self._draw_pill(c, 4, 78, h, hovered=self._hover == 0)
            c.create_text(41, h / 2, text="⚡ Short", fill=accent_col if self._hover == 0 else ink_col, font=("Segoe UI", 8, "bold"), anchor="center")
            self._draw_pill(c, 82, 170, h, hovered=self._hover == 1, base_color="#d49474" if is_dark else "#FFC59E")
            c.create_text(126, h / 2, text="✨ Balanced", fill=accent_col if self._hover == 1 else ink_col, font=("Segoe UI", 8, "bold"), anchor="center")
            self._draw_pill(c, 174, 246, h, hovered=self._hover == 2)
            c.create_text(210, h / 2, text="📚 Deep Dive", fill=accent_col if self._hover == 2 else ink_col, font=("Segoe UI", 8, "bold"), anchor="center")
            self._draw_grid(c, 253, animated=True)
        elif self._stage == self.STAGE_SUMMARIZING:
            self._draw_card(c, w, h)
            self._draw_pill(c, 4, 126, h, active=True)
            c.create_text(65, h / 2, text="⚡ Summarizing…", fill=btn_txt, font=("Segoe UI", 8, "bold"), anchor="center")
            self._draw_grid(c, 138, animated=True)
        elif self._stage == self.STAGE_PLAYBACK_CONTROL:
            self._draw_card(c, w, h)
            self._draw_pill(c, 4, 42, h, hovered=self._hover == 0)
            c.create_text(23, h / 2, text="▶" if self._is_paused else "⏸", fill=accent_col, font=("Segoe UI Symbol", 9, "bold"), anchor="center")
            self._draw_pill(c, 46, 82, h, hovered=self._hover == 1)
            c.create_text(64, h / 2, text="⏹", fill=RED if self._hover == 1 else ink_col, font=("Segoe UI Symbol", 9, "bold"), anchor="center")
            self._draw_pill(c, 86, 140, h, active=True, hovered=self._hover == 2)
            c.create_text(113, h / 2, text=f"⚡ {self._get_display_speed()}x", fill=btn_txt, font=("Segoe UI", 8, "bold"), anchor="center")

    def _draw_card(self, c: tk.Canvas, w: int, h: int) -> None:
        """Card background: dark studio paper (#20201f) with border (#3b3834) or white glass."""
        is_dark = self._is_theme_dark()
        border_col = "#3b3834" if is_dark else BORDER
        card_col = "#20201f" if is_dark else WHITE
        self._rrect(c, 1, 1, w - 1, h - 1, 6, border_col)
        self._rrect(c, 2, 2, w - 2, h - 2, 5, card_col)

    def _draw_pill(
        self,
        c: tk.Canvas,
        x1: float,
        x2: float,
        h: int,
        active: bool = False,
        hovered: bool = False,
        base_color: str | None = None,
        hover_color: str | None = None,
    ) -> None:
        """Pill outline/fill with dark/light mode awareness."""
        is_dark = self._is_theme_dark()
        if base_color is None:
            base_color = "#3b3834" if is_dark else BORDER
        if hover_color is None:
            hover_color = "#e6b092" if is_dark else ORANGE

        if active:
            active_outline = "#d49474" if is_dark else ORANGE_DEEP
            active_fill = "#e6b092" if is_dark else ORANGE
            self._rrect(c, x1, 4, x2, h - 4, 5, active_outline)
            self._rrect(c, x1 + 1, 5, x2 - 1, h - 5, 4, active_fill)
        else:
            outline = hover_color if hovered else base_color
            fill = ("#372c25" if hovered else "#282725") if is_dark else WHITE
            self._rrect(c, x1, 4, x2, h - 4, 5, outline)
            self._rrect(c, x1 + 1, 5, x2 - 1, h - 5, 4, fill)

    def _draw_grid(self, c: tk.Canvas, x0: float, animated: bool = False) -> None:
        """Chic 3x2 dot grid beside the labels; cascading orange wave when animating."""
        cy = self.SIZE / 2
        for row in range(2):
            for col in range(3):
                idx = row * 3 + col
                color = WAVE_TONES[(self._anim_frame + idx) % len(WAVE_TONES)] if animated else ORANGE_SOFT
                cx = x0 + col * GRID_SPACING
                gy = cy - GRID_SPACING / 2 + row * GRID_SPACING
                c.create_oval(cx - GRID_DOT_R, gy - GRID_DOT_R, cx + GRID_DOT_R, gy + GRID_DOT_R, fill=color, outline="")

    @staticmethod
    def _rrect(c: tk.Canvas, x1: float, y1: float, x2: float, y2: float, r: float, color: str) -> None:
        """Filled rounded rectangle (corner arcs + bands) with no outline seams."""
        c.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="pieslice", fill=color, outline="")
        c.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="pieslice", fill=color, outline="")
        c.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="pieslice", fill=color, outline="")
        c.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="pieslice", fill=color, outline="")
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline="")
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline="")

    def _show_voice_menu(self) -> None:
        """Open the complete on-screen Voice Model Catalog & Speed Settings dialog."""
        from voice_flow.audio_flow_dialog import open_audio_flow_settings
        from voice_flow.gui.api_server import runtime_controller
        ov = getattr(runtime_controller, "overlay", None) if runtime_controller else None
        open_audio_flow_settings(
            parent=ov or self.win or self.root,
            on_speed_change=self._set_speed,
            on_voice_change=lambda v: (
                self.on_voice_change(v) if self.on_voice_change else None,
                self._draw()
            ),
        )

    def _on_press(self, event: tk.Event) -> None:
        self._press_x = getattr(event, "x", 0)
        self._press_y = getattr(event, "y", 0)
        self._drag_root_x = getattr(event, "x_root", self._press_x)
        self._drag_root_y = getattr(event, "y_root", self._press_y)
        self._press_root_x = self._drag_root_x
        self._press_root_y = self._drag_root_y
        self._is_dragging = False

    def _on_drag(self, event: tk.Event) -> None:
        rx = getattr(event, "x_root", None)
        ry = getattr(event, "y_root", None)
        if rx is None or ry is None:
            return
        dx = rx - self._drag_root_x
        dy = ry - self._drag_root_y
        total_dist = math.hypot(rx - getattr(self, "_press_root_x", rx), ry - getattr(self, "_press_root_y", ry))
        if not self._is_dragging and total_dist > 8.0:
            self._is_dragging = True
        if self._is_dragging and self.win:
            w, h = self._get_current_dimensions()
            vx, vy, vw, vh = self._virtual_screen_bounds()
            new_x = self._pos_x + dx
            new_y = self._pos_y + dy
            # Clamp securely to virtual screen bounds so floating widget is never dragged off-screen
            self._pos_x = max(vx + 4, min(new_x, vx + vw - w - 4))
            self._pos_y = max(vy + 4, min(new_y, vy + vh - h - 4))
            self._anchor_x = self._pos_x
            self._anchor_y = self._pos_y
            self._drag_root_x = rx
            self._drag_root_y = ry
            try:
                self.win.geometry(f"{w}x{h}+{self._pos_x}+{self._pos_y}")
            except Exception:
                pass

    def _on_release(self, event: tk.Event) -> None:
        if self._is_dragging:
            self._is_dragging = False
            return
        self._on_click(event)

    def _on_click(self, event: tk.Event) -> None:
        """Handle click based on current menu stage."""
        if self._is_playing and self._stage == self.STAGE_MINIMAL:
            self._stage = self.STAGE_PLAYBACK_CONTROL
            self._update_geometry_and_draw()
            return

        if self._stage == self.STAGE_PLAYBACK_CONTROL:
            if event.x <= 44:
                # Verbatim Read has no resumable transport: Pause means stop.
                self._is_paused = False
                if self.on_pause_toggle:
                    self.on_pause_toggle()
                self.hide()
                self._draw()
            elif event.x <= 84:
                if self.on_stop:
                    self.on_stop()
                self.hide()
            else:
                # Real-time speed adjustment
                curr = self._get_current_speed()
                try:
                    idx = self.SPEEDS.index(curr)
                    next_speed = self.SPEEDS[(idx + 1) % len(self.SPEEDS)]
                except ValueError:
                    next_speed = 1.25 if curr == 1.0 else 1.0
                self._set_speed(next_speed)
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
            if event.x <= 108:
                # Read exactly the selected text with the app's native TTS.
                self.hide()
                if self.on_trigger:
                    self.on_trigger(text, mode="read")
            elif event.x <= 224:
                # NotebookLM summary depth selection:
                # Short text (< 1 page) shows the dedicated warning notice first.
                if _is_short_text(text):
                    self._stage = self.STAGE_SHORT_WARNING
                else:
                    self._stage = self.STAGE_DEPTH_SELECT
                self._update_geometry_and_draw()
                self._reset_hide_timer(8.0)
            elif event.x <= 254:
                # ⚙️ Voice / Speed settings menu
                self._show_voice_menu()
            else:
                # Grip handle zone (270..286): drag handle, not button trigger
                pass
            return

        if self._stage == self.STAGE_SUMMARIZING:
            self.hide()
            return

        if self._stage == self.STAGE_SHORT_WARNING:
            y = getattr(event, "y", 65)
            if y < 48:
                # Informative warning banner clicked (keep notice alive)
                self._reset_hide_timer(8.0)
                return
            if event.x <= 188:
                # User clicked "⚡ Use Read" button
                self.hide()
                if self.on_trigger:
                    self.on_trigger(text, mode="read")
            else:
                # User clicked "Make Anyway →" button
                self._prev_dimensions = self._get_current_dimensions()
                self._last_stage_change_time = time.time()
                # Center depth select window around click position
                self._anchor_y = self._pos_y + 16
                self._stage = self.STAGE_DEPTH_SELECT
                self._update_geometry_and_draw()
                self._reset_hide_timer(8.0)
            return

        if self._stage == self.STAGE_DEPTH_SELECT:
            if event.x <= 80:
                depth = "short"
            elif event.x <= 172:
                depth = "balanced"
            elif event.x <= 248:
                depth = "deep_dive"
            else:
                # Clicked on grip/dot-grid handle
                return

            self.hide()
            if self.on_trigger:
                self.on_trigger(text, mode="summary", summary_depth=depth)
            return

    def _hover_index(self, x: float, y: float | None = None) -> int | None:
        """Map a canvas (x, y) position to the hovered pill index for the current stage."""
        if self._stage == self.STAGE_MINIMAL:
            return 0
        if self._stage == self.STAGE_MODE_SELECT:
            if x <= 108:
                return 0
            if x <= 224:
                return 1
            if x <= 254:
                return 2
            if x <= 286:
                return 3  # Grip handle hovered
            return None
        if self._stage == self.STAGE_SHORT_WARNING:
            if y is not None and y < 48:
                return None
            if x <= 188:
                return 0
            return 1
        if self._stage == self.STAGE_DEPTH_SELECT:
            if x <= 80:
                return 0
            if x <= 172:
                return 1
            if x <= 248:
                return 2
            if x <= 265:
                return 3  # Dot-grid handle hovered
            return None
        if self._stage == self.STAGE_PLAYBACK_CONTROL:
            if x <= 44:
                return 0
            if x <= 84:
                return 1
            return 2
        return None

    def _on_motion(self, event: tk.Event) -> None:
        """Recolor the hovered pill (visual only; no click behavior changes)."""
        self._reset_hide_timer(8.0)
        index = self._hover_index(event.x, getattr(event, "y", None))
        if self.canvas:
            if (self._stage == self.STAGE_MODE_SELECT and index == 3) or (self._stage == self.STAGE_DEPTH_SELECT and index == 3):
                self.canvas.config(cursor="size_all")
            else:
                self.canvas.config(cursor="hand2")
        if index != self._hover:
            self._hover = index
            self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        if self.canvas:
            self.canvas.config(cursor="hand2")
        if self._hover is not None:
            self._hover = None
            self._draw()

    def _anim_active(self) -> bool:
        """The single bounded loop runs only while summarizing, warning, selecting depth, or playing."""
        if not self._is_visible or self.root is None:
            return False
        if self._stage in (self.STAGE_SHORT_WARNING, self.STAGE_DEPTH_SELECT, self.STAGE_SUMMARIZING):
            return True  # summary flow is processing -> grid wave
        return self._is_playing and self._stage == self.STAGE_MINIMAL  # progress shimmer

    def _ensure_animation(self) -> None:
        if self._anim_active():
            self._schedule_anim_tick()
        else:
            self._stop_anim_loop()

    def _schedule_anim_tick(self) -> None:
        if self._anim_after_id is not None or not self._anim_active() or not self.root:
            return
        try:
            self._anim_after_id = self.root.after(ANIM_INTERVAL_MS, self._anim_tick)
        except Exception:
            self._anim_after_id = None

    def _anim_tick(self) -> None:
        self._anim_after_id = None
        if not self._anim_active():
            return
        self._anim_frame += 1
        self._draw()
        self._schedule_anim_tick()

    def _stop_anim_loop(self) -> None:
        if self._anim_after_id is not None:
            if self.root:
                try:
                    self.root.after_cancel(self._anim_after_id)
                except Exception:
                    pass
            self._anim_after_id = None
        self._anim_frame = 0

    def _get_logo_image(self, size: int = 16) -> Any:
        attr = f"_logo_photo_{size}"
        if hasattr(self, attr):
            return getattr(self, attr)
        try:
            from voice_flow.installer import get_icon_path
            p = get_icon_path().parent / f"icon-{size}.png"
            if p.exists():
                photo = tk.PhotoImage(file=str(p))
                setattr(self, attr, photo)
                return photo
        except Exception:
            pass
        setattr(self, attr, None)
        return None

    def _run_on_ui(self, func: Callable[[], None]) -> None:
        if self.root:
            try:
                self.root.after(0, func)
            except Exception:
                pass


audio_flow_widget = AudioFlowFloatingWidget()
