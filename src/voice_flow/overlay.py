"""Floating pill bar UI for Voice Flow — polished Wispr Flow-style overlay.

Uses tkinter with Win32 extended styles for a non-activating, always-on-top,
translucent pill bar with animated waveform, cancel/finish buttons,
and smooth state transitions.

Visual language: "Sunrise" design system — white glass pill, orange accents,
ink text, a 3x2 dot-grid state indicator, and a right-edge grip handle.
At idle rest (no mouse, no active feature) the bar collapses to a calm dark
pill with a single soft orange dot; hovering expands it back to the full
Sunrise layout. A 14px right-edge grip strip is reserved in every state.
"""

from __future__ import annotations

import ctypes
import math
import sys
import time
import tkinter as tk
from typing import Callable

from voice_flow.config import config
from voice_flow.storage import storage

# Win32 Constants
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
HWND_TOPMOST = -1


def _safe_done_label(text: object) -> str:
    """Return display-safe completion feedback without ever showing dictation."""
    value = str(text or "").strip()
    # Existing callers may append a command label or transcript.  Keep only
    # the fixed outcome so the compact pill never overflows or exposes text.
    for outcome in ("AI polished", "Cleaned locally"):
        if value == outcome or value.startswith(f"{outcome}:") or value.startswith(f"{outcome} —"):
            return outcome
    return "Done"


def _enable_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness on Windows to prevent blurry rendering or clipping."""
    if sys.platform != "win32":
        return
    try:
        # Per-monitor DPI aware v2 (Windows 10 1703+)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            # Per-monitor DPI aware v1 (Windows 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                # System DPI aware
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


_enable_dpi_awareness()


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _get_cursor_pos() -> tuple[int, int] | None:
    """Return physical cursor screen position (x, y) on Windows."""
    if sys.platform == "win32":
        try:
            pt = _POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return int(pt.x), int(pt.y)
        except Exception:
            pass
    return None


class _ThemeColor:
    """Descriptor providing dynamic color tokens based on on_screen_ui_theme."""

    def __init__(self, light_val: str, dark_val: str) -> None:
        self.light_val = light_val
        self.dark_val = dark_val

    def __get__(self, instance: Any, owner: Any = None) -> str:
        if instance is None:
            return self.light_val
        if getattr(instance, "_is_theme_dark", lambda: False)():
            return self.dark_val
        return self.light_val


class FloatingOverlayBar:
    """Always-on-top, non-activating floating pill bar that mirrors Wispr Flow's UI."""

    def _is_theme_dark(self) -> bool:
        try:
            from voice_flow.storage import storage
            return str(storage.get_setting("on_screen_ui_theme", "light") or "light").strip().lower() == "dark"
        except Exception:
            return False

    # Colors — "Sunrise" design system with dark studio mode support matching studio-polish & design-system tokens
    ORANGE = _ThemeColor("#FF6A00", "#e6b092")        # Warm secondary peach accent (--polish-accent)
    ORANGE_DEEP = _ThemeColor("#E85D04", "#d49474")   # Active accent
    ORANGE_SOFT = _ThemeColor("#FFE3D0", "#372c25")   # Row tint (--polish-tint)
    ORANGE_FAINT = _ThemeColor("#FFF3EA", "#282725")  # Well container bg (--polish-well)
    WHITE = _ThemeColor("#FFFFFF", "#20201f")         # Card surface (--polish-paper)
    OFFWHITE = _ThemeColor("#FFF8F3", "#20201f")
    INK = _ThemeColor("#241708", "#f5f1ea")           # Primary text ink (--polish-ink)
    GRAY = _ThemeColor("#8A8A93", "#b6aea2")          # Muted text (--polish-muted)
    GREEN = _ThemeColor("#12B76A", "#34d399")
    RED = _ThemeColor("#F04438", "#f87171")
    BORDER = _ThemeColor("#FFD0B0", "#3b3834")        # Subtle border line (--polish-line)

    # Dark rest state (idle, no mouse, no active feature) — strictly preserved untouched
    BG_REST = "#17171C"
    BORDER_REST = "#2C2C36"
    GRIP_REST = "#55555F"  # subtle gray grip dots on the dark rest pill

    # Layout: the last GRIP_W pixels of the bar are always the drag grip.
    GRIP_W = 14
    # Redraws closer than this are skipped when nothing meaningful changed.
    REDRAW_MIN_INTERVAL = 0.040

    # Legacy aliases (kept for callers/tests; mapped onto the Sunrise palette)
    BG = WHITE
    BG_HOVER = ORANGE_FAINT
    CANCEL_NORMAL = GRAY
    CANCEL_HOVER = RED
    FINISH_NORMAL = GRAY
    FINISH_HOVER = GREEN
    WAVEFORM_BASE = ORANGE_FAINT
    WAVEFORM_ACTIVE = ORANGE
    WAVEFORM_HOT = ORANGE_DEEP
    TEXT_PRIMARY = INK
    TEXT_DIM = GRAY
    PROCESSING_ACCENT = ORANGE
    DONE_GREEN = GREEN
    BORDER_COLOR = BORDER
    ORANGE_ACCENT = ORANGE
    ACCENT_ORANGE = ORANGE
    TEXT_WHITE = INK  # in dark mode this will be INK (#f5f1ea), in light mode INK (#241708)

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
        self.on_start = (lambda: None)
        self.get_audio_level = get_audio_level or (lambda: 0.0)

        self.on_start_click = None
        self.on_cancel_click = None
        self.on_finish_click = None
        self.on_listen_selected: Callable[[str], None] | None = None
        self.on_video_flow: Callable[[str], None] | None = None
        self.on_video_ready: Callable[[str], None] | None = None
        self.on_video_cancel: Callable[[str], None] | None = None
        self.on_audio_speed_cycle: Callable[[], None] | None = None
        self.on_audio_pause_toggle: Callable[[], None] | None = None
        self.on_audio_stop: Callable[[], None] | None = None
        self.on_open_settings: Callable[[], None] | None = None
        self.selected_text = ""
        self._selection_generation = 0
        self.video_job_id = ""
        self.video_status = ""
        self.video_progress = 0
        self.video_stage = ""
        self._video_animation_generation = 0
        self.audio_summary_status = ""
        self.audio_summary_progress = 0
        self.audio_summary_stage = ""
        self._audio_summary_animation_generation = 0
        self.on_audio_summary_cancel: Callable[[], None] | None = None

        self.state = "HIDDEN"  # HIDDEN, READY, RECORDING, PROCESSING, DONE, ERROR
        self._anim_phase = 0.0
        self._animation_generation = 0
        self.error_message = ""
        self.done_label = "Done"
        self._hover_zone: str | None = None  # "cancel", "finish", "grip", or None
        self._is_mouse_over = False
        # True while a text selection is live — expands bar without hover so
        # the user can click "⋯ Video" immediately after selecting text.
        self._selection_expanded = False

        # Redraw throttle: skip frames where nothing meaningful changed.
        self._last_draw_at = 0.0
        self._last_draw_sig: tuple | None = None
        self._last_draw_canvas = None
        # Width of the last fully drawn frame; grip hit-testing uses this so
        # event.x is always compared against the current on-screen geometry.
        self._last_drawn_width: int | None = None

        self.idle_width = 48
        self.expanded_width = 144
        self.recording_width = 192
        self.ready_actions_width = 248
        self.video_action_width = 66
        self.settings_action_width = 26
        self.audio_playback_width = 272
        self.working_width = 250
        self.working_height = 28
        self.video_progress_width = 280
        self.video_progress_height = 26
        self.video_progress_hover_height = 26
        self.audio_summary_progress_width = 280
        self.audio_summary_progress_height = 26
        self.audio_summary_progress_hover_height = 26
        self.video_ready_width = 280
        self.video_failed_width = 280
        self.video_status_height = 26
        self.idle_height = 10
        self.hover_height = 28
        self.width = self.idle_width
        self.height = self.idle_height
        self.padding = 6
        self.visible = True
        self.dock = "bottom"
        self._user_pos: tuple[int, int] | None = None
        self._heartbeat_at: float | None = None
        self._proximity_after_id = None

    def set_visible(self, visible: bool) -> bool:
        """Runtime hook for the Hub; hiding the bar deliberately leaves hotkeys live."""
        self.visible = bool(visible)

        def _do():
            if not self.win:
                return
            if self.visible:
                if self.state != "HIDDEN":
                    self._bring_to_top()
                    self._draw()
            else:
                self._animation_generation += 1
                self.win.withdraw()
        self._run_on_ui(_do)
        return True

    def set_dock(self, dock) -> bool:
        """Runtime hook for the Hub's persisted Flow Bar location."""
        value = str(dock or "bottom").strip().lower()
        if value not in ("bottom", "left", "right"):
            return False
        self.dock = value
        self._user_pos = None
        self._run_on_ui(self._position_window)
        return True

    def show(self) -> None:
        """Bring the floating bar to the front immediately."""
        self.visible = True

        def _do():
            if not self.win:
                return
            if self.state == "HIDDEN":
                self.state = "READY"
            if self._user_pos is not None:
                anchor_cx, anchor_by = self._user_pos
                target_x = int(anchor_cx - self.width / 2)
                target_y = int(anchor_by - self.height)
                if self._is_offscreen(target_x, target_y):
                    self._user_pos = None
                    self._position_window()
            self._bring_to_top()
            self._draw()

        self._run_on_ui(_do)

    def reset_position(self) -> None:
        """Reset floating bar to default dock position and bring to front."""
        self._user_pos = None

        def _do():
            if not self.win:
                return
            self._position_window()
            self._bring_to_top()
            self._draw()

        self._run_on_ui(_do)

    def _set_bar_size(self, new_width: int, new_height: int) -> None:
        if self.width != new_width or self.height != new_height:
            self.width = new_width
            self.height = new_height
            self._last_drawn_width = new_width
            if self.win and self.canvas:
                if hasattr(self.canvas, "config"):
                    self.canvas.config(width=self.width, height=self.height)
                self._position_window()

    def _drawn_width(self) -> int:
        """Width the bar was last drawn at (current on-screen geometry)."""
        last = getattr(self, "_last_drawn_width", None)
        return last if last else self.width

    def _grip_left(self) -> float:
        """Left edge of the reserved 14px grip strip, from the current width."""
        return self._drawn_width() - self.GRIP_W

    def _create_window(self) -> None:
        """Create and initialize the Tkinter toplevel overlay and canvas."""
        _enable_dpi_awareness()
        if self.root is None:
            self.root = tk.Tk()
            self.root.withdraw()
            try:
                from voice_flow.installer import get_icon_path
                ico = get_icon_path()
                if ico.exists() and hasattr(self.root, "iconbitmap"):
                    self.root.iconbitmap(str(ico))
                p = ico.parent / "icon-32.png"
                if p.exists() and hasattr(self.root, "iconphoto"):
                    self._root_icon_photo = tk.PhotoImage(file=str(p))
                    self.root.iconphoto(True, self._root_icon_photo)
            except Exception:
                pass

        if self.win is not None:
            try:
                if getattr(self.win, "winfo_exists", lambda: True)():
                    return
            except Exception:
                pass

        self.win = tk.Toplevel(self.root)
        if hasattr(self.win, "withdraw"):
            self.win.withdraw()
        if hasattr(self.win, "overrideredirect"):
            self.win.overrideredirect(True)
        try:
            from voice_flow.installer import get_icon_path
            ico = get_icon_path()
            if ico.exists() and hasattr(self.win, "iconbitmap"):
                self.win.iconbitmap(str(ico))
        except Exception:
            pass
        if hasattr(self.win, "attributes"):
            try:
                self.win.attributes("-topmost", True)
                self.win.attributes("-alpha", 0.95)
            except Exception:
                pass

        self._trans_color = "#010101"
        if hasattr(self.win, "config"):
            self.win.config(bg=self._trans_color)
        if hasattr(self.win, "attributes"):
            try:
                self.win.attributes("-transparentcolor", self._trans_color)
            except Exception:
                pass

        self.canvas = tk.Canvas(
            self.win,
            width=self.width,
            height=self.height,
            bg=self._trans_color,
            highlightthickness=0,
            bd=0,
            cursor="arrow",
        )
        if hasattr(self.canvas, "pack"):
            self.canvas.pack(fill="both", expand=True)

        self.drag_x = 0
        self.drag_y = 0
        # Session-only dragged position anchor (center_x, bottom_y). Never
        # persisted: every app start begins at the default dock position; a
        # system sleep/resume also resets it.
        self._user_pos: tuple[int, int] | None = None
        self._heartbeat_at: float | None = None
        if hasattr(self.canvas, "bind"):
            self.canvas.bind("<ButtonPress-1>", self._on_press)
            self.canvas.bind("<B1-Motion>", self._on_drag)
            self.canvas.bind("<Motion>", self._on_motion)
            self.canvas.bind("<Leave>", self._on_leave)

        self._position_window()
        if hasattr(self.win, "bind"):
            self.win.bind("<Map>", self._on_map)
        self._bring_to_top()
        self._draw()
        self._schedule_proximity_poll()

    def _init_tk(self) -> None:
        self._create_window()

    def run_loop(self) -> None:
        """Start the Tkinter event loop for floating overlay bar."""
        self._create_window()
        if self.root:
            from voice_flow.audio_flow_widget import audio_flow_widget
            from voice_flow.video_flow_widget import video_flow_widget
            audio_flow_widget.attach_root(self.root)
            video_flow_widget.attach_root(self.root)

        if self.win:
            self.state = "READY"
            self._position_window()
            self._bring_to_top()
            self._schedule_heartbeat()
            self._draw()
        if self.root:
            self.root.mainloop()

    def _on_map(self, _event: tk.Event) -> None:
        self._apply_win32_styles()
        if self.win and hasattr(self.win, "unbind"):
            self.win.unbind("<Map>")

    def _get_screen_bounds(self) -> tuple[int, int, int, int]:
        """Return (min_x, min_y, max_x, max_y) across all connected monitors."""
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                vx = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
                vy = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
                vw = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
                vh = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
                if vw > 0 and vh > 0:
                    return vx, vy, vx + vw, vy + vh
            except Exception:
                pass
        screen_w = self.root.winfo_screenwidth() if self.root and hasattr(self.root, "winfo_screenwidth") else 1920
        screen_h = self.root.winfo_screenheight() if self.root and hasattr(self.root, "winfo_screenheight") else 1080
        return 0, 0, screen_w, screen_h

    def _is_offscreen(self, x: int, y: int) -> bool:
        """Check if the bar at (x, y) is outside visible screen bounds."""
        min_x, min_y, max_x, max_y = self._get_screen_bounds()
        if (x + self.width <= min_x) or (x >= max_x) or (y + self.height <= min_y) or (y >= max_y):
            return True
        return False

    def contains_point(self, x: int, y: int) -> bool:
        """Check if screen point (x, y) falls inside the overlay bar window or its surround activation zone."""
        if not getattr(self, "visible", True) or self.state == "HIDDEN" or not self.win:
            return False
        try:
            cur_x = self.win.winfo_rootx() if hasattr(self.win, "winfo_rootx") else (self.win.winfo_x() if hasattr(self.win, "winfo_x") else 0)
            cur_y = self.win.winfo_rooty() if hasattr(self.win, "winfo_rooty") else (self.win.winfo_y() if hasattr(self.win, "winfo_y") else 0)
            w = self._drawn_width()
            is_expanded = getattr(self, "_is_mouse_over", False) or getattr(self, "_selection_expanded", False)
            h = max(self.height, self.hover_height) if is_expanded else self.height
            if is_expanded:
                w = max(w, self.ready_actions_width)

            # When docked at bottom and collapsed, expansion moves upper boundary UPWARDS
            if getattr(self, "dock", "bottom") == "bottom" and not is_expanded:
                y_min = cur_y - (self.hover_height - self.height) - 4
                y_max = cur_y + self.height + 4
            else:
                y_min = cur_y - 4
                y_max = cur_y + h + 4

            if is_expanded:
                anchor_cx = cur_x + w // 2
                exp_w = max(w, self.ready_actions_width)
                x_min = anchor_cx - exp_w // 2 - 4
                x_max = anchor_cx + exp_w // 2 + 4
            else:
                x_min = cur_x - 4
                x_max = cur_x + w + 4

            return (x_min <= x <= x_max) and (y_min <= y <= y_max)
        except Exception:
            return False

    def _clamp_to_screen(self, x: int, y: int, screen_w: int | None = None, screen_h: int | None = None) -> tuple[int, int]:
        min_x, min_y, max_x, max_y = self._get_screen_bounds()
        if screen_w is not None and max_x == 0:
            max_x = screen_w
        if screen_h is not None and max_y == 0:
            max_y = screen_h
        clamped_x = max(min_x, min(x, max_x - self.width))
        clamped_y = max(min_y, min(y, max_y - self.height))
        return clamped_x, clamped_y

    def _position_window(self) -> None:
        if not self.win:
            return
        screen_w = self.root.winfo_screenwidth() if self.root and hasattr(self.root, "winfo_screenwidth") else 1920
        screen_h = self.root.winfo_screenheight() if self.root and hasattr(self.root, "winfo_screenheight") else 1080
        if self._user_pos is not None:
            anchor_cx, anchor_by = self._user_pos
            target_x = int(anchor_cx - self.width // 2)
            target_y = int(anchor_by - self.height)
            x, y = self._clamp_to_screen(target_x, target_y, screen_w, screen_h)
        elif getattr(self, "dock", "bottom") == "left":
            x, y = 8, (screen_h - self.height) // 2
        elif getattr(self, "dock", "bottom") == "right":
            x, y = screen_w - self.width - 8, (screen_h - self.height) // 2
        else:
            x = (screen_w - self.width) // 2
            margin = getattr(config, "bar_bottom_margin", 60)
            y = screen_h - self.height - margin
        if hasattr(self.win, "geometry"):
            self._suppress_leave_until = time.monotonic() + 0.15
            self.win.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _bring_to_top(self) -> None:
        """Ensure overlay window is deiconified, topmost, and has Win32 styles applied."""
        if not self.win:
            return
        try:
            if hasattr(self.win, "deiconify"):
                self.win.deiconify()
        except Exception:
            pass
        try:
            if hasattr(self.win, "lift"):
                self.win.lift()
        except Exception:
            pass
        try:
            if hasattr(self.win, "attributes"):
                self.win.attributes("-topmost", True)
        except Exception:
            pass
        self._apply_win32_styles()

    def _schedule_heartbeat(self) -> None:
        """Reset to the default position after the machine sleeps.

        Tk timers pause while the system sleeps, so a heartbeat that fires
        far later than its 20s interval means a suspend/resume happened —
        the bar then returns to the default dock position."""
        import time as _time

        if not (self.win and getattr(self.win, "winfo_exists", lambda: True)()):
            return
        now = _time.time()
        if self._heartbeat_at is not None and now - self._heartbeat_at > 90:
            self._heartbeat_at = now
            self._handle_resume()
        else:
            self._heartbeat_at = now
        if self.visible and self.state != "HIDDEN":
            self._bring_to_top()
        if hasattr(self.win, "after"):
            self.win.after(20000, self._schedule_heartbeat)

    def _handle_resume(self) -> None:
        """System woke from sleep: return the bar to the default position."""
        if self._user_pos is not None:
            self._user_pos = None
            self._position_window()
        if self.visible and self.state != "HIDDEN":
            self._bring_to_top()
            self._draw()

    def _apply_win32_styles(self) -> None:
        if sys.platform != "win32":
            return
        if not self.win or not hasattr(self.win, "winfo_id"):
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            if not hwnd:
                hwnd = self.win.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            target = style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            if style != target:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, target)
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
                )
            else:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )
        except Exception:
            pass

    # -- Public State API --

    def _run_on_ui(self, func: Callable[[], None]) -> None:
        if self.root and self.win:
            try:
                self.root.after(0, func)
            except Exception:
                pass
        else:
            func()

    def refresh(self) -> None:
        """Thread-safe redraw request: routes _draw through the UI loop."""
        self._run_on_ui(self._draw)

    def set_selected_text(self, text: str, timeout_ms: int = 15000) -> None:
        """Keep selected text available for the next Video Flow launch.

        Also expands the bar immediately so the user can click '⋯ Video'
        without having to move the cursor to the bar first.
        """
        clean = text.strip()
        if not clean:
            self.clear_selected_text()
            return

        def _do():
            self.selected_text = clean
            self._selection_generation += 1
            self._selection_expanded = True  # Expand bar immediately on selection
            generation = self._selection_generation
            if self.state == "READY":
                self._draw()
            if self.root and timeout_ms > 0:
                self.root.after(timeout_ms, lambda: self._clear_selection_if_current(generation))

        self._run_on_ui(_do)

    def clear_selected_text(self) -> None:
        def _do():
            self.selected_text = ""
            self._selection_generation += 1
            self._selection_expanded = False  # Collapse back to rest pill
            if self.state == "READY":
                self._draw()
        self._run_on_ui(_do)

    def show_video_progress(self, video_id: str, progress: int = 0, stage: str = "Creating video") -> None:
        """Show a persistent animated circle beside the bar while a video renders."""
        def _do():
            self.video_job_id = video_id
            self.video_status = "processing"
            self.video_progress = max(0, min(100, int(progress)))
            self.video_stage = stage[:80]
            self.selected_text = ""
            self._selection_generation += 1
            self._video_animation_generation += 1
            generation = self._video_animation_generation
            if self.state == "READY":
                self._draw()
            self._tick_video_animation(generation)
        self._run_on_ui(_do)

    def show_video_ready(self, video_id: str) -> None:
        """Replace the spinner with a green checkmark that opens the player."""
        def _do():
            self.video_job_id = video_id
            self.video_status = "ready"
            self.video_progress = 100
            self.video_stage = "Video ready"
            self._video_animation_generation += 1
            if self.state == "READY":
                self._draw()
        self._run_on_ui(_do)

    def show_video_failed(self, video_id: str, message: str = "Video generation failed") -> None:
        def _do():
            self.video_job_id = video_id
            self.video_status = "failed"
            self.video_stage = message[:80]
            self._video_animation_generation += 1
            if self.state == "READY":
                self._draw()
        self._run_on_ui(_do)

    def clear_video_status(self) -> None:
        def _do():
            self.video_job_id = ""
            self.video_status = ""
            self.video_progress = 0
            self.video_stage = ""
            self._video_animation_generation += 1
            if self.state == "READY":
                self._draw()
        self._run_on_ui(_do)

    def _tick_video_animation(self, generation: int) -> None:
        if generation != self._video_animation_generation or self.video_status != "processing":
            return
        self._anim_phase += 0.16
        if self.state == "READY":
            self._draw()
        if self.root:
            self.root.after(45, lambda: self._tick_video_animation(generation))

    def show_audio_summary_progress(self, progress: int = 0, stage: str = "Generating summary audio") -> None:
        """Show a persistent animated progress rail on the floating bar while an audio summary generates."""
        def _do():
            self.audio_summary_status = "processing"
            self.audio_summary_progress = max(0, min(100, int(progress)))
            self.audio_summary_stage = stage[:80]
            self.selected_text = ""
            self._selection_generation += 1
            self._audio_summary_animation_generation += 1
            generation = self._audio_summary_animation_generation
            if self.state in ("READY", "SUMMARIZING", "GENERATING_AUDIO"):
                self._draw()
            self._tick_audio_summary_animation(generation)
        self._run_on_ui(_do)

    def clear_audio_summary_status(self) -> None:
        def _do():
            self.audio_summary_status = ""
            self.audio_summary_progress = 0
            self.audio_summary_stage = ""
            self._audio_summary_animation_generation += 1
            if self.state in ("READY", "SUMMARIZING", "GENERATING_AUDIO"):
                self._draw()
        self._run_on_ui(_do)

    def _tick_audio_summary_animation(self, generation: int) -> None:
        if generation != self._audio_summary_animation_generation or self.audio_summary_status != "processing":
            return
        self._anim_phase += 0.16
        if self.state in ("READY", "SUMMARIZING", "GENERATING_AUDIO"):
            self._draw()
        if self.root:
            self.root.after(45, lambda: self._tick_audio_summary_animation(generation))

    def _clear_selection_if_current(self, generation: int) -> None:
        if generation == self._selection_generation and not self._is_mouse_over:
            self.selected_text = ""
            self._selection_expanded = False
            if self.state == "READY":
                self._draw()

    def show_ready(self) -> None:
        """Display the idle system-wide floating bar (ready state)."""
        def _do():
            if not self.win: return
            self.state = "READY"
            self.done_label = "Done"
            self._anim_phase = 0.0
            self._animation_generation += 1
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
        self._run_on_ui(_do)

    def show_recording(self, level_provider: Callable[[], float] | None = None) -> None:
        def _do():
            if level_provider:
                self.get_audio_level = level_provider
            if not self.win: return
            self.state = "RECORDING"
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
            if self.root and hasattr(self.root, "after"):
                self.root.after(66, lambda: self._animate(generation))
        self._run_on_ui(_do)

    def show_processing(self) -> None:
        def _do():
            if not self.win: return
            self.state = "PROCESSING"
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
            if self.root and hasattr(self.root, "after"):
                self.root.after(66, lambda: self._animate(generation))
        self._run_on_ui(_do)

    def show_done(self, text: str = "") -> None:
        def _do():
            if not self.win: return
            self.state = "DONE"
            self.done_label = _safe_done_label(text)
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
            if self.root and hasattr(self.root, "after"):
                self.root.after(66, lambda: self._animate(generation))
                delay = max(config.done_display_ms, 4000) if self.done_label != "Done" else config.done_display_ms
                self.root.after(delay, lambda: self._show_ready_if_current(generation, "DONE"))
        self._run_on_ui(_do)

    def show_error(self, message: str) -> None:
        """Show a recoverable error without leaving the bar stuck recording."""
        def _do():
            if not self.win: return
            self.state = "ERROR"
            self.error_message = message[:90]
            self.done_label = _safe_done_label(message)
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
            if self.root and hasattr(self.root, "after"):
                self.root.after(66, lambda: self._animate(generation))
                delay = max(config.done_display_ms, 5000 if self.done_label != "Done" else 2500)
                self.root.after(delay, lambda: self._show_ready_if_current(generation, "ERROR"))
        self._run_on_ui(_do)

    def _show_ready_if_current(self, generation: int, expected_state: str) -> None:
        """Ignore delayed UI cleanup belonging to an older session state."""
        if self._animation_generation == generation and self.state == expected_state:
            self.show_ready()

    def hide(self) -> None:
        def _do():
            if not self.win: return
            self.state = "HIDDEN"
            if hasattr(self.win, "withdraw"):
                self.win.withdraw()
        self._run_on_ui(_do)

    # -- Mouse Events & Dragging --

    def _get_zone(self, x: int, y: int | None = None) -> str | None:
        # All zone math uses the width the bar was last drawn at, so hit boxes
        # always match the on-screen geometry (never stale constants).
        w = self._drawn_width()
        grip_left = w - self.GRIP_W

        # Drag grip is always the rightmost 14px
        if x >= grip_left:
            return "grip"

        cancel_btn_left = grip_left - 18

        # 1. Processing Video Flow progress rail
        if self.video_status == "processing":
            if self.state == "READY":
                is_stacked = getattr(self, "_is_mouse_over", False) and self.height > self.hover_height
                if is_stacked and y is not None:
                    if y <= self.video_progress_hover_height and cancel_btn_left <= x < grip_left:
                        return "video_cancel"
                elif cancel_btn_left <= x < grip_left:
                    return "video_cancel"
            elif self.state != "READY":
                progress_top = self.height - self.video_progress_hover_height
                if (y is None or y >= progress_top) and cancel_btn_left <= x < grip_left:
                    return "video_cancel"

        # 1b. Processing Audio Flow summary progress rail
        if self.audio_summary_status == "processing":
            if self.state in ("READY", "SUMMARIZING", "GENERATING_AUDIO"):
                is_stacked = getattr(self, "_is_mouse_over", False) and self.height > self.hover_height
                if is_stacked and y is not None:
                    if y <= self.audio_summary_progress_hover_height and cancel_btn_left <= x < grip_left:
                        return "audio_summary_cancel"
                elif cancel_btn_left <= x < grip_left:
                    return "audio_summary_cancel"
            elif self.state != "READY":
                progress_top = self.height - self.audio_summary_progress_hover_height
                if (y is None or y >= progress_top) and cancel_btn_left <= x < grip_left:
                    return "audio_summary_cancel" 

        # 2. Standalone Ready / Failed status pill (when not in text-selection action mode)
        sel_active = getattr(self, "_selection_expanded", False)
        if self.state == "READY" and self.video_status in ("ready", "failed"):
            if not sel_active:
                if cancel_btn_left <= x < grip_left:
                    return "video_cancel"
                return "video_status"
            else:
                # In selection mode: status badge is at the right
                if w - 48 <= x < grip_left:
                    return "video_status"

        has_status_slot = bool(self.video_status and self.video_status != "processing" and sel_active)
        content_width = grip_left - (34 if has_status_slot else 0)

        if self.state == "READING":
            if 108 <= x < 148:
                return "audio_pause"
            if 148 <= x < 184:
                return "audio_stop"
            if 184 <= x < 222:
                return "audio_settings"
            if 222 <= x < grip_left:
                return "cancel"
            return "speak"

        if self.state == "READY":
            if w >= 120:
                settings_width = getattr(self, "settings_action_width", 26)
                settings_left = content_width - settings_width
                video_left = settings_left - self.video_action_width
                video_hit_left = video_left - 4

                if settings_left <= x < content_width:
                    return "settings"
                if video_left > 0 and video_hit_left <= x < settings_left:
                    return "video_flow"
            return "speak"

        if x < 40:
            return "cancel"
        return "finish"

    def _on_press(self, event: tk.Event) -> None:
        self.drag_x = event.x
        self.drag_y = event.y
        self._press_start_x = event.x
        self._press_start_y = event.y
        self._is_dragging = False
        zone = self._get_zone(event.x, event.y)
        self._press_zone = zone
        if zone == "video_cancel" and self.video_job_id:
            if self.on_video_cancel:
                self.on_video_cancel(self.video_job_id)
            self.clear_video_status()
        elif zone == "audio_summary_cancel":
            if self.on_audio_summary_cancel:
                try:
                    self.on_audio_summary_cancel()
                except Exception:
                    pass
            self.clear_audio_summary_status()
            self.show_ready()
        elif zone == "grip":
            pass  # grip presses only drag the bar (handled by _on_drag)
        elif zone in ("settings", "audio_settings"):
            if self.on_open_settings:
                self.on_open_settings()
        elif zone == "audio_pause":
            if self.on_audio_pause_toggle:
                self.on_audio_pause_toggle()
            self._draw()
        elif zone in ("audio_stop", "cancel") and self.state == "READING":
            if self.on_audio_stop:
                self.on_audio_stop()
            self.clear_selected_text()
            self.show_ready()
        elif self.state == "READY":
            selected = self.selected_text
            if zone == "video_status" and self.video_status in {"ready", "failed"} and self.video_job_id:
                if self.video_status == "ready" and self.on_video_ready:
                    self.on_video_ready(self.video_job_id)
                elif self.video_status == "failed":
                    self.show_error(self.video_stage or "Video generation failed")
                self.clear_video_status()
            elif zone == "video_flow":
                if selected:
                    self.clear_selected_text()
                if self.on_video_flow:
                    self.on_video_flow(selected or "")
            elif zone == "speak" and selected and self.on_listen_selected:
                self.clear_selected_text()
                self.on_listen_selected(selected)
            elif zone == "speak" and self.on_start_click:
                self.on_start_click()
            elif zone == "speak" and self.on_start:
                self.on_start()
        elif self.state == "RECORDING":
            if zone == "cancel":
                if self.on_cancel_click:
                    self.on_cancel_click()
                else:
                    self.on_cancel()
            else:
                if self.on_finish_click:
                    self.on_finish_click()
                else:
                    self.on_finish()

        if zone not in ("video_flow", "settings", "audio_settings", "audio_pause"):
            self._is_mouse_over = False

    def _on_drag(self, event: tk.Event) -> None:
        dx = event.x - self.drag_x
        dy = event.y - self.drag_y
        dist = math.hypot(event.x - getattr(self, "_press_start_x", event.x), event.y - getattr(self, "_press_start_y", event.y))
        # Only start dragging if user pressed the dedicated grip strip OR intentionally dragged > 6px
        if getattr(self, "_press_zone", None) != "grip" and dist < 6.0 and not getattr(self, "_is_dragging", False):
            return

        self._is_dragging = True
        new_x = (self.win.winfo_x() if hasattr(self.win, "winfo_x") else 0) + dx
        new_y = (self.win.winfo_y() if hasattr(self.win, "winfo_y") else 0) + dy
        clamped_x, clamped_y = self._clamp_to_screen(new_x, new_y)
        if hasattr(self.win, "geometry"):
            self.win.geometry(f"+{clamped_x}+{clamped_y}")
        # Store bottom-center anchor point so all states remain concentric
        self._user_pos = (clamped_x + self.width // 2, clamped_y + self.height)

    def _on_motion(self, event: tk.Event) -> None:
        was_over = self._is_mouse_over
        self._is_mouse_over = True
        zone = self._get_zone(event.x, event.y)
        if zone != self._hover_zone or not was_over:
            previous_zone = self._hover_zone
            self._hover_zone = zone
            if hasattr(self.canvas, "config"):
                if zone == "grip":
                    self.canvas.config(cursor="fleur")
                elif zone in ("cancel", "finish", "video_status", "video_cancel") or self.state == "READY":
                    self.canvas.config(cursor="hand2")
                else:
                    self.canvas.config(cursor="arrow")
            if self.state == "READY" or self.video_status == "processing" or zone == "grip" or previous_zone == "grip":
                self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        if time.monotonic() < getattr(self, "_suppress_leave_until", 0.0):
            return
        cur_pos = _get_cursor_pos()
        if cur_pos is not None and self.win:
            cx, cy = cur_pos
            if self.contains_point(cx, cy):
                return
        self._hover_zone = None
        self._is_mouse_over = False
        if hasattr(self.canvas, "config"):
            self.canvas.config(cursor="arrow")
        if self.state == "READY" or self.video_status == "processing":
            self._draw()

    def _proximity_poll(self) -> None:
        """Surround-proximity cursor tracking to eliminate hover gaps and jitter."""
        if not self.win or not getattr(self.win, "winfo_exists", lambda: True)():
            return
        try:
            if not self.visible or self.state != "READY" or getattr(self, "_selection_expanded", False) or bool(self.video_status):
                return

            cur_pos = _get_cursor_pos()
            if cur_pos is None:
                return
            cx, cy = cur_pos

            wx = self.win.winfo_rootx() if hasattr(self.win, "winfo_rootx") else 0
            wy = self.win.winfo_rooty() if hasattr(self.win, "winfo_rooty") else 0
            ww = self._drawn_width()
            wh = self.height

            # 1. When resting (collapsed to rest pill):
            if not self._is_mouse_over:
                anchor_cx = wx + ww // 2
                anchor_by = wy + wh

                # A. 32px generous surround margin around the rest pill
                rest_near = (wx - 32 <= cx <= wx + ww + 32) and (wy - 32 <= cy <= wy + wh + 32)
                # B. Area where expanded bar will appear + 20px surround margin
                exp_x1 = anchor_cx - self.ready_actions_width // 2 - 20
                exp_x2 = anchor_cx + self.ready_actions_width // 2 + 20
                exp_y1 = anchor_by - self.hover_height - 20
                exp_y2 = anchor_by + 20
                exp_near = (exp_x1 <= cx <= exp_x2) and (exp_y1 <= cy <= exp_y2)

                if rest_near or exp_near:
                    self._is_mouse_over = True
                    self._hover_zone = self._get_zone(int(cx - (anchor_cx - self.ready_actions_width // 2)), int(cy - (anchor_by - self.hover_height)))
                    self._draw()
            else:
                # 2. When already expanded: keep alive with generous hysteresis buffer
                leave_x1 = wx - 28
                leave_x2 = wx + ww + 28
                leave_y1 = wy - 28
                leave_y2 = wy + wh + 28
                if not (leave_x1 <= cx <= leave_x2 and leave_y1 <= cy <= leave_y2):
                    self._is_mouse_over = False
                    self._hover_zone = None
                    self._draw()
                else:
                    # Update hover zone for live button highlights
                    zone = self._get_zone(cx - wx, cy - wy)
                    if zone != self._hover_zone:
                        self._hover_zone = zone
                        self._draw()
        except Exception:
            pass
        finally:
            self._schedule_proximity_poll()

    def _schedule_proximity_poll(self) -> None:
        if self.win and hasattr(self.win, "after"):
            try:
                # Idle (hidden / collapsed rest pill / non-ready states) needs no 40ms tracking;
                # keep 40ms only while in READY state and expanded/interactive.
                not_ready = (
                    not self.visible
                    or self.state != "READY"
                    or (
                        not getattr(self, "_is_mouse_over", False)
                        and not getattr(self, "_selection_expanded", False)
                    )
                )
                self._proximity_after_id = self.win.after(200 if not_ready else 40, self._proximity_poll)
            except Exception:
                pass

    # -- Animation Loop --

    def show_reading(self, snippet: str = "Reading selected text...") -> None:
        """Display the animated READING state while TTS audio is playing."""
        def _do():
            if not self.win: return
            self.state = "READING"
            self.reading_snippet = snippet
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
            if self.root and hasattr(self.root, "after"):
                self.root.after(66, lambda: self._animate(generation))
        self._run_on_ui(_do)

    def show_summarizing(self, snippet: str = "Summarizing selected text...") -> None:
        """Display the animated SUMMARIZING state while LLM creates the narration."""
        def _do():
            if not self.win: return
            self.state = "SUMMARIZING"
            self.reading_snippet = snippet
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
            if self.root and hasattr(self.root, "after"):
                self.root.after(66, lambda: self._animate(generation))
        self._run_on_ui(_do)

    def show_generating_audio(self, snippet: str = "Generating audio...") -> None:
        """Display the animated GENERATING_AUDIO state during TTS synthesis."""
        def _do():
            if not self.win: return
            self.state = "GENERATING_AUDIO"
            self.reading_snippet = snippet
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._set_bar_size(*self._target_size())
            self._bring_to_top()
            self._draw()
            if self.root and hasattr(self.root, "after"):
                self.root.after(66, lambda: self._animate(generation))
        self._run_on_ui(_do)

    def _animate(self, generation: int = -1) -> None:
        if generation != -1 and generation != self._animation_generation:
            return
        if self.state == "HIDDEN":
            return
        self._anim_phase += 0.12
        self._draw()
        if self.state in ("RECORDING", "PROCESSING", "READING", "SUMMARIZING", "GENERATING_AUDIO", "ERROR"):
            self.root.after(66, lambda: self._animate(generation))
        elif self.state == "DONE" and self._anim_phase < 1.5:
            # DONE only animates its one-shot green flash, then holds.
            self.root.after(66, lambda: self._animate(generation))

    # -- Drawing --

    def _target_size(self) -> tuple[int, int]:
        """Bar size for the current state/hover — geometry changes only on transitions."""
        has_video_proc = self.video_status == "processing"
        has_audio_proc = self.audio_summary_status == "processing"
        has_proc = has_video_proc or has_audio_proc
        proc_w = self.video_progress_width if has_video_proc else self.audio_summary_progress_width
        proc_h = self.video_progress_hover_height if has_video_proc else self.audio_summary_progress_hover_height
        proc_normal_h = self.video_progress_height if has_video_proc else self.audio_summary_progress_height

        if self.state == "READY":
            sel_expanded = getattr(self, "_selection_expanded", False)
            is_hovered = getattr(self, "_is_mouse_over", False)
            if has_proc:
                if is_hovered or sel_expanded:
                    ready_width = self.ready_actions_width
                    return (
                        max(ready_width, proc_w),
                        self.hover_height + proc_h + 4,
                    )
                return proc_w, proc_normal_h
            if self.video_status == "failed":
                if sel_expanded:
                    return self.ready_actions_width + 34, self.hover_height
                return self.video_failed_width, self.video_status_height
            if self.video_status == "ready":
                if sel_expanded:
                    return self.ready_actions_width + 34, self.hover_height
                return self.video_ready_width, self.video_status_height
            if is_hovered or sel_expanded:
                return self.ready_actions_width, self.hover_height
            return self.idle_width, self.idle_height
        if self.state == "RECORDING":
            extra = proc_h + 4 if has_proc else 0
            return max(self.recording_width, proc_w if extra else 0), self.hover_height + extra
        if self.state == "READING":
            return self.audio_playback_width, self.hover_height
        if self.state in ("PROCESSING", "SUMMARIZING", "GENERATING_AUDIO", "ERROR"):
            if self.state in ("SUMMARIZING", "GENERATING_AUDIO") and has_audio_proc and not has_video_proc:
                return proc_w, proc_normal_h
            extra = proc_h + 4 if has_proc else 0
            return max(self.working_width, proc_w if extra else 0), self.working_height + extra
        if self.state == "DONE":
            extra = proc_h + 4 if has_proc else 0
            outcome_width = max(self.expanded_width, 180) if self.done_label != "Done" else self.expanded_width
            return max(outcome_width, proc_w if extra else 0), self.hover_height + extra
        return self.width, self.height
    def _draw_signature(self) -> tuple:
        """Meaningful-change key: state, hover zone, rounded level buckets.

        NOTE: _anim_phase is intentionally excluded — it advances every
        animation tick, which previously defeated the 40ms redraw throttle
        below. Animated states still redraw via the _animate loop itself
        (its 66ms cadence already exceeds the throttle window), while
        redundant _draw calls with no meaningful change now early-return.
        """
        level_bucket = 0.0
        if self.state == "RECORDING":
            try:
                level_bucket = float(self.get_audio_level() or 0.0)
                if math.isnan(level_bucket) or math.isinf(level_bucket):
                    level_bucket = 0.0
            except Exception:
                level_bucket = 0.0
        return (
            self.state,
            self._hover_zone,
            getattr(self, "_is_mouse_over", False),
            getattr(self, "_selection_expanded", False),
            self.video_status,
            self.video_stage,
            self.video_progress,
            self.audio_summary_status,
            self.audio_summary_stage,
            self.audio_summary_progress,
            self.selected_text,
            self.error_message,
            self.done_label,
            round(level_bucket, 2),
            self.width,
            self.height,
            getattr(self, "dock", "bottom"),
            self._is_theme_dark(),
        )

    def _draw(self) -> None:
        c = self.canvas
        if c is None:
            return
        now = time.monotonic()
        if (
            self._last_draw_canvas is c
            and self._last_draw_sig is not None
            and now - self._last_draw_at < self.REDRAW_MIN_INTERVAL
            and self._draw_signature() == self._last_draw_sig
        ):
            return  # throttled: nothing meaningful changed within 40ms

        # Resize once per state/hover transition, then draw one full frame.
        target_w, target_h = self._target_size()
        if self.width != target_w or self.height != target_h:
            self._set_bar_size(target_w, target_h)

        c.delete("all")
        w, h = self.width, self.height
        flow_height = h
        has_video_proc = self.video_status == "processing"
        has_audio_proc = self.audio_summary_status == "processing"
        has_proc = has_video_proc or has_audio_proc
        proc_h = self.video_progress_hover_height if has_video_proc else self.audio_summary_progress_hover_height

        if has_proc and self.state not in ("READY", "SUMMARIZING", "GENERATING_AUDIO"):
            flow_height = h - proc_h - 4

        is_rest = (
            self.state == "READY"
            and not getattr(self, "_is_mouse_over", False)
            and not getattr(self, "_selection_expanded", False)
            and not self.video_status
            and not self.audio_summary_status
        )
        if self.state in ("PROCESSING", "READING", "SUMMARIZING", "GENERATING_AUDIO", "ERROR"):
            if self.state in ("SUMMARIZING", "GENERATING_AUDIO") and has_audio_proc and not has_video_proc:
                pass  # Audio summary progress strip manages its own background pill
            else:
                self._draw_working_shell(w, flow_height)
        elif self.state == "READY" and has_proc:
            pass  # Video or audio progress strip manages its own background pill(s)
        elif self.state == "READY" and self.video_status in ("ready", "failed") and not getattr(self, "_selection_expanded", False):
            pass  # Dedicated ready/failed status pill manages its own background pill
        elif not is_rest:
            self._draw_pill(1, 1, w - 1, flow_height - 1, min(flow_height / 2, 16), self.WHITE, self.BORDER)

        if self.state == "READY":
            self._draw_ready(w, h)
        elif self.state == "RECORDING":
            self._draw_recording(w, flow_height)
        elif self.state == "PROCESSING":
            self._draw_processing(w, flow_height)
        elif self.state == "SUMMARIZING":
            if has_audio_proc and not has_video_proc:
                self._draw_audio_summary_progress_strip(w, 0, h, expanded=self._is_mouse_over)
            else:
                self._draw_working_state(w, flow_height, "Summarizing")
        elif self.state == "GENERATING_AUDIO":
            if has_audio_proc and not has_video_proc:
                self._draw_audio_summary_progress_strip(w, 0, h, expanded=self._is_mouse_over)
            else:
                self._draw_working_state(w, flow_height, "Generating Audio")
        elif self.state == "READING":
            self._draw_reading(w, flow_height)
        elif self.state == "DONE":
            self._draw_done(w, flow_height)
        elif self.state == "ERROR":
            self._draw_error(w, flow_height)

        # The reserved 14px grip strip exists in every state, rest pill included.
        self._draw_grip(w, flow_height)

        if has_proc and self.state not in ("READY", "SUMMARIZING", "GENERATING_AUDIO"):
            if has_video_proc:
                self._draw_video_progress_strip(w, flow_height + 4, h, expanded=self._is_mouse_over)
            elif has_audio_proc:
                self._draw_audio_summary_progress_strip(w, flow_height + 4, h, expanded=self._is_mouse_over)

        self._last_draw_at = now
        self._last_draw_sig = self._draw_signature()
        self._last_draw_canvas = c
        self._last_drawn_width = self.width

    def _draw_ready(self, w: int, h: int) -> None:
        has_video = bool(self.video_status)
        has_audio = bool(self.audio_summary_status)
        sel_active = getattr(self, "_selection_expanded", False)
        is_expanded = self._is_mouse_over or sel_active

        if not is_expanded:
            if self.video_status == "processing":
                self._draw_video_progress_strip(w, 0, h, expanded=False)
                return
            if self.audio_summary_status == "processing":
                self._draw_audio_summary_progress_strip(w, 0, h, expanded=False)
                return
            if self.video_status in ("ready", "failed"):
                self._draw_video_status_pill(w, h)
                return
            if not has_video and not has_audio:
                # Calm dark rest pill: no white glass, no animation.
                self._draw_rest_pill(w, h)
                return

        if not sel_active and self.video_status in ("ready", "failed"):
            self._draw_video_status_pill(w, h)
            return

        c = self.canvas
        has_video_proc = self.video_status == "processing"
        has_audio_proc = self.audio_summary_status == "processing"
        progress_offset = (
            self.video_progress_hover_height + 4
            if has_video_proc
            else (self.audio_summary_progress_hover_height + 4 if has_audio_proc else 0)
        )
        action_top = progress_offset
        action_height = h - action_top
        cy = action_top + action_height / 2
        has_status_slot = bool(has_video and self.video_status != "processing" and sel_active)
        content_width = w - self.GRIP_W - (34 if has_status_slot else 0)

        if has_video_proc:
            self._draw_video_progress_strip(w, 0, self.video_progress_hover_height, expanded=True)
            self._draw_pill(2, action_top + 2, w - 2, h - 2, max(2.0, min(action_height / 2 - 2, 16)), self.WHITE, self.BORDER)
        elif has_audio_proc:
            self._draw_audio_summary_progress_strip(w, 0, self.audio_summary_progress_hover_height, expanded=True)
            self._draw_pill(2, action_top + 2, w - 2, h - 2, max(2.0, min(action_height / 2 - 2, 16)), self.WHITE, self.BORDER)

        settings_width = getattr(self, "settings_action_width", 26)
        settings_left = content_width - settings_width
        video_left = settings_left - self.video_action_width
        hover_radius = max(2.0, min(action_height / 2 - 3, 16))

        # Speak zone highlight (hover only)
        if self._hover_zone == "speak":
            self._draw_pill(4, action_top + 3, video_left - 4, h - 3, hover_radius, self.ORANGE_FAINT, self.ORANGE_ACCENT)

        # Video zone: permanent orange glow when selection is active (even without hover);
        # brighter/full orange when hovered on top of that.
        if self._hover_zone == "video_flow":
            self._draw_pill(video_left + 2, action_top + 3, settings_left - 2, h - 3, hover_radius, self.ORANGE_FAINT, self.ORANGE_ACCENT)
        elif sel_active:
            # Soft persistent glow: signals "your text is ready, click here"
            self._draw_pill(video_left + 2, action_top + 3, settings_left - 2, h - 3, hover_radius, self.ORANGE_FAINT, self.ORANGE_FAINT)

        # Settings zone highlight (hover only)
        if self._hover_zone == "settings":
            self._draw_pill(settings_left + 2, action_top + 3, content_width - 2, h - 3, hover_radius, self.ORANGE_FAINT, self.ORANGE_ACCENT)

        # "Click to speak" label — dimmed when selection mode (video is the intent)
        speak_fill = self.ACCENT_ORANGE if self._hover_zone == "speak" else (self.BORDER if sel_active else self.INK)
        c.create_text(video_left / 2, cy, text="Click to speak", fill=speak_fill, font=(config.bar_font_family, 9, "bold"), anchor="center")
        c.create_line(video_left, action_top + 7, video_left, h - 7, fill=self.BORDER, width=1)

        # "⋯ Video" label — orange when selection active or hovered
        video_fill = self.ACCENT_ORANGE if (self._hover_zone == "video_flow" or sel_active) else self.TEXT_WHITE
        c.create_text(video_left + self.video_action_width / 2, cy, text="⋯ Video", fill=video_fill, font=(config.bar_font_family, 8, "bold"), anchor="center")
        c.create_line(settings_left, action_top + 7, settings_left, h - 7, fill=self.BORDER, width=1)

        # Crisp Vector Settings Gear Icon
        settings_fill = self.ACCENT_ORANGE if self._hover_zone == "settings" else self.INK
        settings_bg = self.ORANGE_FAINT if self._hover_zone == "settings" else self.WHITE
        self._draw_gear_icon(settings_left + settings_width / 2, cy, r=4.5, color=settings_fill, bg_color=settings_bg)

        if has_status_slot:
            c.create_line(content_width, action_top + 7, content_width, h - 7, fill=self.BORDER, width=1)
            self._draw_video_status(w, h, compact=True)
    def _draw_rest_pill(self, w: int, h: int) -> None:
        """Calm dark rest pill: nothing drawn on it at all.

        The user asked for a fully quiet rest state — no dots, no accents, no
        grip marks. The grip strip stays functional (cursor + drag) even
        though it is invisible at rest."""
        self._draw_pill(1, 1, w - 1, h - 1, min(h / 2, 14), self.BG_REST, self.BORDER_REST)

    def _draw_video_progress_strip(self, w: int, top: int, bottom: int, *, expanded: bool) -> None:
        """Draw Video Flow as a spacious, modern orange rail with dedicated element slots."""
        c = self.canvas
        mid = (top + bottom) / 2
        h_strip = bottom - top

        # Draw white glass pill background with smooth border
        self._draw_pill(1, top + 1, w - 1, bottom - 1, min(h_strip / 2, 13), self.WHITE, self.BORDER)
        if expanded:
            self._draw_dot_texture(5, top + 4, w - 5, bottom - 4)

        # 1. Left: Product title [🎬 Video Flow] at x=12
        c.create_text(
            12,
            mid,
            text="Video Flow",
            fill=self.ORANGE,
            font=(config.bar_font_family, 8, "bold"),
            anchor="w",
        )

        # 2. Next: 3x2 dot-grid cascading animation indicator at x=86
        self._draw_grid_indicator(86, mid - 2.5, "cascade")

        # 3. Middle: Wide progress track with glowing orange fill, smooth rounded caps & light gleam
        track_left = 115
        track_right = w - 74
        track_y = mid
        c.create_line(track_left, track_y, track_right, track_y, fill=self.ORANGE_FAINT, width=4, capstyle="round")

        fraction = max(0.0, min(1.0, self.video_progress / 100.0))
        fill_right = track_left + (track_right - track_left) * fraction
        if fill_right > track_left:
            c.create_line(track_left, track_y, fill_right, track_y, fill=self.ORANGE, width=4, capstyle="round")
            gleam = min(fill_right, max(track_left, fill_right - 8 + math.sin(self._anim_phase * 2.8) * 4))
            c.create_line(max(track_left, gleam - 5), track_y, gleam, track_y, fill=self.WHITE, width=1.5, capstyle="round")

        # 4. Right: Bold percentage text at w - 48
        c.create_text(
            w - 48,
            mid,
            text=f"{self.video_progress}%",
            fill=self.INK,
            font=(config.bar_font_family, 8, "bold"),
            anchor="center",
        )

        # 5. Far Right: Subtle cancel ✕ button at w - 22
        grip_left = w - self.GRIP_W
        cx_cancel = grip_left - 8
        hover = self._hover_zone == "video_cancel"
        cancel_color = self.RED if hover else self.GRAY
        if hover:
            c.create_oval(cx_cancel - 6, mid - 6, cx_cancel + 6, mid + 6, fill=self.ORANGE_FAINT, outline=self.RED, width=1)
        c.create_line(cx_cancel - 3, mid - 3, cx_cancel + 3, mid + 3, fill=cancel_color, width=1.5, capstyle="round")
        c.create_line(cx_cancel + 3, mid - 3, cx_cancel - 3, mid + 3, fill=cancel_color, width=1.5, capstyle="round")


    def _draw_audio_summary_progress_strip(self, w: int, top: int, bottom: int, *, expanded: bool) -> None:
        """Draw Audio Flow summary progress as a spacious, modern orange rail matching Video Flow."""
        c = self.canvas
        mid = (top + bottom) / 2
        h_strip = bottom - top

        # Draw white glass pill background with smooth border
        self._draw_pill(1, top + 1, w - 1, bottom - 1, min(h_strip / 2, 13), self.WHITE, self.BORDER)
        if expanded:
            self._draw_dot_texture(5, top + 4, w - 5, bottom - 4)

        # 1. Left: Product title [Audio Flow] at x=12
        c.create_text(
            12,
            mid,
            text="Audio Flow",
            fill=self.ORANGE,
            font=(config.bar_font_family, 8, "bold"),
            anchor="w",
        )

        # 2. Next: 3x2 dot-grid cascading animation indicator at x=86
        self._draw_grid_indicator(86, mid - 2.5, "cascade")

        # 3. Middle: Wide progress track with glowing orange fill, smooth rounded caps & light gleam
        track_left = 115
        track_right = w - 74
        track_y = mid
        c.create_line(track_left, track_y, track_right, track_y, fill=self.ORANGE_FAINT, width=4, capstyle="round")

        fraction = max(0.0, min(1.0, self.audio_summary_progress / 100.0))
        fill_right = track_left + (track_right - track_left) * fraction
        if fill_right > track_left:
            c.create_line(track_left, track_y, fill_right, track_y, fill=self.ORANGE, width=4, capstyle="round")
            gleam = min(fill_right, max(track_left, fill_right - 8 + math.sin(self._anim_phase * 2.8) * 4))
            c.create_line(max(track_left, gleam - 5), track_y, gleam, track_y, fill=self.WHITE, width=1.5, capstyle="round")

        # 4. Right: Bold percentage text at w - 48
        c.create_text(
            w - 48,
            mid,
            text=f"{self.audio_summary_progress}%",
            fill=self.INK,
            font=(config.bar_font_family, 8, "bold"),
            anchor="center",
        )

        # 5. Far Right: Subtle cancel ✕ button at w - 22
        grip_left = w - self.GRIP_W
        cx_cancel = grip_left - 8
        hover = self._hover_zone == "audio_summary_cancel"
        cancel_color = self.RED if hover else self.GRAY
        if hover:
            c.create_oval(cx_cancel - 6, mid - 6, cx_cancel + 6, mid + 6, fill=self.ORANGE_FAINT, outline=self.RED, width=1)
        c.create_line(cx_cancel - 3, mid - 3, cx_cancel + 3, mid + 3, fill=cancel_color, width=1.5, capstyle="round")
        c.create_line(cx_cancel + 3, mid - 3, cx_cancel - 3, mid + 3, fill=cancel_color, width=1.5, capstyle="round")
    def _draw_video_status_pill(self, w: int, h: int) -> None:
        """Draw standalone ready or failed video status pill in READY state."""
        c = self.canvas
        cy = h / 2

        # Draw white glass pill background with smooth border
        self._draw_pill(1, 1, w - 1, h - 1, min(h / 2, 13), self.WHITE, self.BORDER)

        grip_left = w - self.GRIP_W
        cx_cancel = grip_left - 8

        if self.video_status == "ready":
            # Green checkmark circle badge at cx = 14
            badge_x = 14
            c.create_oval(badge_x - 6, cy - 6, badge_x + 6, cy + 6, fill=self.GREEN, outline="")
            c.create_line(badge_x - 3, cy, badge_x - 1, cy + 2, fill="white", width=1.5, capstyle="round")
            c.create_line(badge_x - 1, cy + 2, badge_x + 3, cy - 3, fill="white", width=1.5, capstyle="round")

            text_fill = self.GREEN if self._hover_zone == "video_status" else self.INK
            c.create_text(
                26,
                cy,
                text="▶ Video Ready — Click to play",
                fill=text_fill,
                font=(config.bar_font_family, 8, "bold"),
                anchor="w",
            )
        elif self.video_status == "failed":
            # Red exclamation circle badge at cx = 14
            badge_x = 14
            c.create_oval(badge_x - 6, cy - 6, badge_x + 6, cy + 6, fill=self.RED, outline="")
            c.create_text(badge_x, cy, text="!", fill="white", font=(config.bar_font_family, 7, "bold"), anchor="center")

            text_fill = self.RED if self._hover_zone == "video_status" else self.INK
            c.create_text(
                26,
                cy,
                text="Video failed — click to view",
                fill=text_fill,
                font=(config.bar_font_family, 8, "bold"),
                anchor="w",
            )

        # Subtle cancel / dismiss ✕ button
        hover_cancel = self._hover_zone == "video_cancel"
        cancel_col = self.RED if hover_cancel else self.GRAY
        if hover_cancel:
            c.create_oval(cx_cancel - 6, cy - 6, cx_cancel + 6, cy + 6, fill=self.ORANGE_FAINT, outline=self.RED, width=1)
        c.create_line(cx_cancel - 3, cy - 3, cx_cancel + 3, cy + 3, fill=cancel_col, width=1.5, capstyle="round")
        c.create_line(cx_cancel + 3, cy - 3, cx_cancel - 3, cy + 3, fill=cancel_col, width=1.5, capstyle="round")

    def _draw_video_status(self, w: int, h: int, *, compact: bool = True) -> None:
        c = self.canvas
        cx = w - self.GRIP_W - 10  # centered in the status zone, clear of the grip strip
        cy = h / 2
        radius = 4 if compact else 8
        if self.video_status == "processing":
            c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=self.ORANGE_SOFT, width=2)
            angle = self._anim_phase * 5
            dot_x = cx + math.cos(angle) * radius
            dot_y = cy + math.sin(angle) * radius
            c.create_oval(dot_x - 2, dot_y - 2, dot_x + 2, dot_y + 2, fill=self.ORANGE, outline="")
            if not compact:
                c.create_text(cx - 42, cy, text="Video Flow", fill=self.ORANGE, font=(config.bar_font_family, 8, "bold"), anchor="e")
                c.create_text(cx, cy, text=str(max(0, min(99, int(self.video_progress)))), fill=self.INK, font=(config.bar_font_family, 6, "bold"), anchor="center")
        elif self.video_status == "ready":
            c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=self.GREEN, outline="")
            c.create_line(cx - 3, cy, cx - 1, cy + 2, fill="white", width=1.5, capstyle="round")
            c.create_line(cx - 1, cy + 2, cx + 3, cy - 3, fill="white", width=1.5, capstyle="round")
        else:
            c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=self.RED, outline="")
            c.create_text(cx, cy, text="!", fill="white", font=(config.bar_font_family, 8, "bold"), anchor="center")
    def _draw_gear_icon(self, cx: float, cy: float, r: float = 4.5, color: str = "#241708", bg_color: str = "#FFFFFF") -> None:
        """Draw a 100% crisp, pixel-perfect vector gear icon using canvas geometry."""
        c = self.canvas
        if not c:
            return
        import math
        # Draw 6 symmetrical gear teeth radiating outward
        teeth_count = 6
        tooth_len = r + 1.8
        tooth_w = 2.0
        for i in range(teeth_count):
            angle = i * (math.pi / 3)
            x1 = cx + (r - 1.2) * math.cos(angle)
            y1 = cy + (r - 1.2) * math.sin(angle)
            x2 = cx + tooth_len * math.cos(angle)
            y2 = cy + tooth_len * math.sin(angle)
            c.create_line(x1, y1, x2, y2, fill=color, width=tooth_w, capstyle="round")

        # Outer circular body
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline=color, width=1)
        # Inner center hub hole
        hole_r = max(1.5, r * 0.42)
        c.create_oval(cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r, fill=bg_color, outline=bg_color)

    def _draw_reading(self, w: int, h: int) -> None:
        """Dedicated audio playback strip on the floating bar (no speed control during playback)."""
        c = self.canvas
        cy = h / 2

        # Draw white card base with rounded border
        self._draw_pill(1, 1, w - 1, h - 1, min(h / 2, 14), self.WHITE, self.BORDER)

        # Audio Flow label + animated sound dots on left
        self._draw_grid_indicator(14, cy - 2.5, "wave")
        c.create_text(32, cy, text="Audio Flow", fill=self.INK, font=(config.bar_font_family, 8, "bold"), anchor="w")
        c.create_line(104, 6, 104, h - 6, fill=self.BORDER, width=1)

        # Pause / Resume button [▶ / ⏸]
        pause_hover = self._hover_zone == "audio_pause"
        self._draw_pill(110, 4, 146, h - 4, 5, self.ORANGE_FAINT if pause_hover else self.WHITE, self.ORANGE if pause_hover else self.BORDER)
        from voice_flow.tts_engine import tts_engine
        glyph = "▶" if getattr(tts_engine, "_is_paused", False) else "⏸"
        c.create_text(128, cy, text=glyph, fill=self.ORANGE_DEEP if pause_hover else self.ORANGE, font=("Segoe UI Symbol", 8, "bold"), anchor="center")

        # Stop button [⏹]
        stop_hover = self._hover_zone == "audio_stop"
        self._draw_pill(150, 4, 182, h - 4, 5, self.ORANGE_FAINT if stop_hover else self.WHITE, self.RED if stop_hover else self.BORDER)
        c.create_text(166, cy, text="⏹", fill=self.RED if stop_hover else self.INK, font=("Segoe UI Symbol", 8, "bold"), anchor="center")

        # Settings button [⚙]
        set_hover = self._hover_zone == "audio_settings"
        self._draw_pill(186, 4, 220, h - 4, 5, self.ORANGE_FAINT if set_hover else self.WHITE, self.ORANGE if set_hover else self.BORDER)
        set_bg = self.ORANGE_FAINT if set_hover else self.WHITE
        self._draw_gear_icon(203, cy, r=4.5, color=self.ORANGE_DEEP if set_hover else self.INK, bg_color=set_bg)

        # Dismiss [✕]
        cancel_hover = self._hover_zone == "cancel"
        cx_cancel = 236
        sz = 4
        c.create_line(cx_cancel - sz, cy - sz, cx_cancel + sz, cy + sz, fill=self.CANCEL_HOVER if cancel_hover else self.CANCEL_NORMAL, width=2, capstyle="round")
        c.create_line(cx_cancel + sz, cy - sz, cx_cancel - sz, cy + sz, fill=self.CANCEL_HOVER if cancel_hover else self.CANCEL_NORMAL, width=2, capstyle="round")

    def _draw_recording(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2

        cancel_color = self.CANCEL_HOVER if self._hover_zone == "cancel" else self.CANCEL_NORMAL
        cx_cancel = 18
        size = 5
        c.create_line(cx_cancel - size, cy - size, cx_cancel + size, cy + size, fill=cancel_color, width=2, capstyle="round")
        c.create_line(cx_cancel + size, cy - size, cx_cancel - size, cy + size, fill=cancel_color, width=2, capstyle="round")

        self._draw_grid_indicator(32, cy - 2.5, "wave")

        try:
            level = float(self.get_audio_level() or 0.0)
            if math.isnan(level) or math.isinf(level):
                level = 0.0
        except Exception:
            level = 0.0

        num_bars = 15
        bar_width = 2
        bar_gap = 2
        total_w = num_bars * (bar_width + bar_gap) - bar_gap
        wave_left, wave_right = 48, w - 34
        start_x = (wave_left + wave_right - total_w) / 2

        c.create_line(start_x, cy, start_x + total_w, cy, fill=self.WAVEFORM_BASE, width=1)

        level_t = max(0.0, min(1.0, level))
        if level_t < 0.5:
            bar_color = self._lerp_color(self.ORANGE_SOFT, self.ORANGE, level_t * 2)
        else:
            bar_color = self._lerp_color(self.ORANGE, self.ORANGE_DEEP, (level_t - 0.5) * 2)

        for i in range(num_bars):
            bx = start_x + i * (bar_width + bar_gap)
            wave = math.sin(self._anim_phase * 1.5 + i * 0.5)
            center_factor = 1.0 - abs(i - num_bars / 2) / (num_bars / 2) * 0.5
            bar_h = 3 + abs(wave) * (2 + level * 9) * center_factor
            c.create_rectangle(bx, cy - bar_h / 2, bx + bar_width, cy + bar_h / 2, fill=bar_color, outline="", width=0)

        finish_color = self.FINISH_HOVER if self._hover_zone == "finish" else self.FINISH_NORMAL
        cx_finish = w - self.GRIP_W - 9  # clear of the reserved grip strip
        c.create_line(cx_finish - 6, cy, cx_finish - 2, cy + 4, fill=finish_color, width=2.5, capstyle="round")
        c.create_line(cx_finish - 2, cy + 4, cx_finish + 6, cy - 4, fill=finish_color, width=2.5, capstyle="round")

    def _draw_processing(self, w: int, h: int) -> None:
        self._draw_working_state(w, h, "Transcribing")

    def _draw_working_shell(self, w: int, h: int) -> None:
        """Draw the white glass card used only while a flow is working.

        The faint dot texture is deliberately NOT drawn here anymore: it was
        recreated every animation frame (flicker-prone) and is now reserved
        for the expanded video strip only."""
        self._draw_pill(1, 1, w - 1, h - 1, min(h / 2, 16), self.WHITE, self.BORDER)

    def _draw_working_state(self, w: int, h: int, flow_name: str) -> None:
        """White glass card: dot-grid cascade indicator + status title + progress rail."""
        c = self.canvas
        title_y = int(h * 0.34) if h >= 48 else int(h * 0.5)
        self._draw_grid_indicator(14, title_y - 2.5, "cascade")
        c.create_text(
            32,
            title_y,
            text=flow_name,
            fill=self.INK,
            font=(config.bar_font_family, 9, "bold"),
            anchor="w",
        )

        if h >= 48:
            track_y = int(h * 0.70)
            track_left = 14
            track_right = w - 40
            c.create_line(track_left, track_y, track_right, track_y, fill=self.ORANGE_FAINT, width=3, capstyle="round")
            position = (self._anim_phase * 0.45) % 1.0
            dot_x = track_left + position * (track_right - track_left)
            c.create_oval(dot_x - 2, track_y - 2, dot_x + 2, track_y + 2, fill=self.ORANGE, outline="")

    def _draw_done(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2
        # Preserve the established centered "Done" geometry for ordinary
        # callers.  Fixed outcome labels use the available left side instead.
        circle_x = int(w * 0.5) - 36 if self.done_label == "Done" else 14
        r = 7
        c.create_oval(circle_x - r, cy - r, circle_x + r, cy + r, fill=self.GREEN, outline="")
        c.create_line(circle_x - 3, cy, circle_x - 1, cy + 3, fill="white", width=2, capstyle="round")
        c.create_line(circle_x - 1, cy + 3, circle_x + 4, cy - 3, fill="white", width=2, capstyle="round")
        c.create_text(circle_x + 15, cy, text=self.done_label, fill=self.GREEN, font=(config.bar_font_family, 9, "bold"), anchor="w")
        self._draw_grid_indicator(w - 26, cy - 2.5, "done")

    def _draw_error(self, w: int, h: int) -> None:
        """Keep recoverable failures neutral and avoid exposing raw provider errors."""
        label = self.done_label if self.done_label != "Done" else "Working"
        if label != "Working":
            self.canvas.create_text(
                29,
                h / 2,
                text=label,
                fill=self.TEXT_WHITE,
                font=(config.bar_font_family, 9, "bold"),
                anchor="w",
            )
            self._draw_grid_indicator(w - 26, h / 2 - 2.5, "error")
            return
        self.canvas.create_text(
            w / 2 - 6,
            h / 2,
            text=label,
            fill=self.TEXT_WHITE,
            font=(config.bar_font_family, 9, "bold"),
            anchor="e",
        )
        self._draw_grid_indicator(w / 2 + 4, h / 2 - 2.5, "error")

    # -- Sunrise signature elements --

    def _draw_grid_indicator(self, x: float, y: float, mode: str) -> None:
        """3x2 mini-grid state indicator: (x, y) is the top-left dot center."""
        for i in range(6):
            col, row = i % 3, i // 3
            radius, color = self._grid_dot_style(i, mode)
            dx = x + col * 5
            dy = y + row * 5
            self.canvas.create_oval(dx - radius, dy - radius, dx + radius, dy + radius, fill=color, outline="")

    def _grid_dot_style(self, i: int, mode: str) -> tuple[float, str]:
        """Per-dot radius/color for each grid animation mode, driven by _anim_phase."""
        if mode == "ready":
            if self.selected_text:
                return 1.5, self.ORANGE
            return 1.5, self.ORANGE if i in (1, 4) else self.ORANGE_SOFT
        if mode == "wave":
            s = (math.sin(self._anim_phase * 2.2 + i * 0.7) + 1.0) / 2.0
            return 1.1 + 0.9 * s, self._lerp_color(self.ORANGE, self.ORANGE_DEEP, s)
        if mode == "cascade":
            stagger = 0.29  # ~80ms per dot at the existing tick rates
            window = 1.5
            cycle = 6 * stagger + window
            t = self._anim_phase % cycle
            local = t - i * stagger
            if local < 0:
                local += cycle
            on = min(local / 0.22, 1.0) * max(0.0, min((window - local) / 0.22, 1.0))
            depth = max(0.0, min(local / 1.1, 1.0))
            color = self._lerp_color(self.ORANGE, self.ORANGE_DEEP, depth) if on > 0 else self.ORANGE_SOFT
            return 1.2 + 0.6 * on, color
        if mode == "done":
            pulse = math.sin(min(self._anim_phase / 1.0, 1.0) * math.pi)
            return 1.5 + 0.9 * pulse, self.GREEN
        if mode == "error":
            s = (math.sin(self._anim_phase * 4.0) + 1.0) / 2.0
            return 1.2 + 0.6 * s, self.RED
        return 1.5, self.ORANGE_SOFT

    def _draw_dot_texture(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Static sparse dot-grid texture (fixed 10px grid), expanded video strip only."""
        if x2 - x1 < 16 or y2 - y1 < 8:
            return
        c = self.canvas
        gx = x1 + 5
        while gx < x2 - 2:
            gy = y1 + 5
            while gy < y2 - 2:
                c.create_oval(gx - 0.5, gy - 0.5, gx + 0.5, gy + 0.5, fill=self.ORANGE_SOFT, outline="")
                gy += 10
            gx += 10

    def _draw_grip(self, w: int, h: int) -> None:
        """Vertical 2x3 grip dots centered inside the reserved 14px strip.

        The dots are laid out around the strip's center so the visual dots and
        the [w-GRIP_W, w) hit zone coincide exactly. Subtle gray on the dark
        rest pill, current Sunrise style (gray / orange on hover) elsewhere."""
        c = self.canvas
        if self.state == "READY" and not self._is_mouse_over and not self.video_status:
            # Rest state draws nothing — the strip remains an invisible,
            # fully functional drag handle (cursor + drag only).
            return
        color = self.ORANGE if self._hover_zone == "grip" else self.GRAY
        cy = h / 2
        strip_mid = w - self.GRIP_W / 2
        for col in range(2):
            for row in range(3):
                gx = strip_mid + (col - 0.5) * 3.5
                gy = cy - 3.5 + row * 3.5
                c.create_oval(gx - 1, gy - 1, gx + 1, gy + 1, fill=color, outline="")

    @staticmethod
    def _lerp_color(color_a: str, color_b: str, t: float) -> str:
        t = max(0.0, min(1.0, t))

        def parse(value: str) -> tuple[int, int, int]:
            return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)

        r1, g1, b1 = parse(color_a)
        r2, g2, b2 = parse(color_b)
        return f"#{int(r1 + (r2 - r1) * t):02x}{int(g1 + (g2 - g1) * t):02x}{int(b1 + (b2 - b1) * t):02x}"

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
