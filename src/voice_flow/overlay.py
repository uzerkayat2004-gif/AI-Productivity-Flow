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
    ORANGE_ACCENT = "#ff6b19"
    ACCENT_ORANGE = ORANGE_ACCENT
    TEXT_WHITE = "#ffffff"

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
        self.selected_text = ""
        self._selection_generation = 0
        self.video_job_id = ""
        self.video_status = ""
        self.video_progress = 0
        self.video_stage = ""
        self._video_animation_generation = 0

        self.state = "HIDDEN"  # HIDDEN, READY, RECORDING, PROCESSING, DONE, ERROR
        self._anim_phase = 0.0
        self._animation_generation = 0
        self.error_message = ""
        self._hover_zone: str | None = None  # "cancel", "finish", or None
        self._is_mouse_over = False

        self.idle_width = 70
        self.expanded_width = 180
        self.recording_width = 240
        self.ready_actions_width = 250
        self.video_action_width = 82
        self.working_width = 286
        self.working_height = 104
        self.video_progress_width = 238
        self.video_progress_height = 14
        self.video_progress_hover_height = 24
        self.idle_height = 14
        self.hover_height = 32
        self.width = self.idle_width
        self.height = self.idle_height
        self.padding = 8

    def _set_bar_size(self, new_width: int, new_height: int) -> None:
        if self.width != new_width or self.height != new_height:
            self.width = new_width
            self.height = new_height
            if self.win and self.canvas:
                self.canvas.config(width=self.width, height=self.height)
                self._position_window()

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
        if self.root:
            from voice_flow.audio_flow_widget import audio_flow_widget
            from voice_flow.video_flow_widget import video_flow_widget
            audio_flow_widget.attach_root(self.root)
            video_flow_widget.attach_root(self.root)

        if self.win:
            self.state = "READY"
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
            self._draw()
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

    def set_selected_text(self, text: str, timeout_ms: int = 15000) -> None:
        """Keep selected text available for the next Video Flow launch."""
        clean = text.strip()
        if not clean:
            self.clear_selected_text()
            return

        def _do():
            self.selected_text = clean
            self._selection_generation += 1
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

    def _clear_selection_if_current(self, generation: int) -> None:
        if generation == self._selection_generation and not self._is_mouse_over:
            self.selected_text = ""
            if self.state == "READY":
                self._draw()
    def show_ready(self) -> None:
        """Display the idle system-wide floating bar (ready state)."""
        def _do():
            if not self.win: return
            self.state = "READY"
            self._anim_phase = 0.0
            self._animation_generation += 1
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
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
            self._position_window()
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
            self._animate(generation)
        self._run_on_ui(_do)

    def show_processing(self) -> None:
        def _do():
            if not self.win: return
            self.state = "PROCESSING"
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._draw()
            self._animate(generation)
        self._run_on_ui(_do)

    def show_done(self, text: str = "") -> None:
        def _do():
            if not self.win: return
            self.state = "DONE"
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self._draw()
            self.root.after(config.done_display_ms, lambda: self._show_ready_if_current(generation, "DONE"))
        self._run_on_ui(_do)

    def show_error(self, message: str) -> None:
        """Show a recoverable error without leaving the bar stuck recording."""
        def _do():
            if not self.win: return
            self.state = "ERROR"
            self.error_message = message[:90]
            self._anim_phase = 0.0
            self._animation_generation += 1
            generation = self._animation_generation
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._draw()
            self.root.after(max(config.done_display_ms, 2500), lambda: self._show_ready_if_current(generation, "ERROR"))
        self._run_on_ui(_do)

    def _show_ready_if_current(self, generation: int, expected_state: str) -> None:
        """Ignore delayed UI cleanup belonging to an older session state."""
        if self._animation_generation == generation and self.state == expected_state:
            self.show_ready()

    def hide(self) -> None:
        def _do():
            if not self.win: return
            self.state = "HIDDEN"
            self.win.withdraw()
        self._run_on_ui(_do)

    # -- Mouse Events & Dragging --

    def _get_zone(self, x: int, y: int | None = None) -> str | None:
        if self.video_status == "processing" and y is not None:
            if self.state == "READY" and self._is_mouse_over:
                if y <= self.video_progress_hover_height and x >= self.width - 36:
                    return "video_cancel"
            elif self.state != "READY":
                progress_top = self.height - self.video_progress_hover_height
                if y >= progress_top and x >= self.width - 36:
                    return "video_cancel"
        has_status_slot = bool(self.video_status and self.video_status != "processing")
        if self.state == "READY" and has_status_slot and x >= self.width - 42:
            return "video_status"
        content_width = self.width - (44 if has_status_slot else 0)
        if self.state == "READY":
            if not self._is_mouse_over or self.width < self.ready_actions_width:
                return "speak"
            video_left = content_width - self.video_action_width
            if x < video_left:
                return "speak"
            if x < content_width:
                return "video_flow"
        if x < 52:
            return "cancel"
        if x > content_width - 52:
            return "finish"
        return None
    def _on_press(self, event: tk.Event) -> None:
        self.drag_x = event.x
        self.drag_y = event.y
        zone = self._get_zone(event.x, event.y)
        if zone == "video_cancel" and self.video_job_id:
            if self.on_video_cancel:
                self.on_video_cancel(self.video_job_id)
            self.clear_video_status()
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
                    self.on_video_flow(selected)
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

        self._is_mouse_over = False
    def _on_drag(self, event: tk.Event) -> None:
        dx = event.x - self.drag_x
        dy = event.y - self.drag_y
        new_x = self.win.winfo_x() + dx
        new_y = self.win.winfo_y() + dy
        self.win.geometry(f"+{new_x}+{new_y}")

    def _on_motion(self, event: tk.Event) -> None:
        was_over = self._is_mouse_over
        self._is_mouse_over = True
        zone = self._get_zone(event.x, event.y)
        if zone != self._hover_zone or not was_over:
            self._hover_zone = zone
            if zone in ("cancel", "finish", "video_status", "video_cancel") or self.state == "READY":
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.config(cursor="arrow")
            if self.state == "READY" or self.video_status == "processing":
                self._draw()
    def _on_leave(self, _event: tk.Event) -> None:
        self._hover_zone = None
        self._is_mouse_over = False
        self.canvas.config(cursor="arrow")
        if self.state == "READY" or self.video_status == "processing":
            self._draw()
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
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
            self._draw()
            self._animate(generation)
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
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
            self._draw()
            self._animate(generation)
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
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self._apply_win32_styles()
            self._draw()
            self._animate(generation)
        self._run_on_ui(_do)

    def _animate(self, generation: int = -1) -> None:
        if generation != -1 and generation != self._animation_generation:
            return
        if self.state == "HIDDEN":
            return
        self._anim_phase += 0.12
        self._draw()
        if self.state in ("RECORDING", "PROCESSING", "READING", "SUMMARIZING", "GENERATING_AUDIO"):
            self.root.after(33, lambda: self._animate(generation))

    # -- Drawing --

    def _draw(self) -> None:
        c = self.canvas

        base_height = self.hover_height
        if self.state == "READY":
            if getattr(self, "_is_mouse_over", False):
                ready_width = self.ready_actions_width + (44 if self.video_status and self.video_status != "processing" else 0)
                if self.video_status == "processing":
                    self._set_bar_size(
                        max(ready_width, self.video_progress_width),
                        self.hover_height + self.video_progress_hover_height + 4,
                    )
                else:
                    self._set_bar_size(ready_width, self.hover_height)
            elif self.video_status == "processing":
                self._set_bar_size(self.video_progress_width, self.video_progress_height)
            else:
                idle_width = self.idle_width + (32 if self.video_status else 0)
                self._set_bar_size(idle_width, self.idle_height)
        elif self.state == "RECORDING":
            base_height = self.hover_height
            extra = self.video_progress_hover_height + 4 if self.video_status == "processing" else 0
            self._set_bar_size(max(self.recording_width, self.video_progress_width), base_height + extra)
        elif self.state in ("PROCESSING", "READING", "SUMMARIZING", "GENERATING_AUDIO", "ERROR"):
            base_height = self.working_height
            extra = self.video_progress_hover_height + 4 if self.video_status == "processing" else 0
            self._set_bar_size(max(self.working_width, self.video_progress_width), base_height + extra)
        elif self.state == "DONE":
            base_height = self.hover_height
            extra = self.video_progress_hover_height + 4 if self.video_status == "processing" else 0
            self._set_bar_size(max(self.expanded_width, self.video_progress_width if extra else 0), base_height + extra)

        c.delete("all")
        w, h = self.width, self.height
        flow_height = h
        if self.video_status == "processing" and self.state != "READY":
            flow_height = h - self.video_progress_hover_height - 4

        if self.state in ("PROCESSING", "READING", "SUMMARIZING", "GENERATING_AUDIO", "ERROR"):
            self._draw_working_shell(w, flow_height)
        elif not (self.state == "READY" and self.video_status == "processing"):
            self._draw_pill(2, 2, w - 2, flow_height - 2, flow_height // 2 - 2, self.BG, self.BORDER_COLOR)

        if self.state == "READY":
            self._draw_ready(w, h)
        elif self.state == "RECORDING":
            self._draw_recording(w, flow_height)
        elif self.state == "PROCESSING":
            self._draw_processing(w, flow_height)
        elif self.state == "SUMMARIZING":
            self._draw_working_state(w, flow_height, "Summarizing")
        elif self.state == "GENERATING_AUDIO":
            self._draw_working_state(w, flow_height, "Generating Audio")
        elif self.state == "READING":
            self._draw_reading(w, flow_height)
        elif self.state == "DONE":
            self._draw_done(w, flow_height)
        elif self.state == "ERROR":
            self._draw_error(w, flow_height)

        if self.video_status == "processing" and self.state != "READY":
            self._draw_video_progress_strip(w, flow_height + 4, h, expanded=self._is_mouse_over)
    def _draw_ready(self, w: int, h: int) -> None:
        has_video = bool(self.video_status)
        content_width = w - (44 if has_video and self.video_status != "processing" and self._is_mouse_over else 30 if has_video and self.video_status != "processing" else 0)
        if not getattr(self, "_is_mouse_over", False):
            if self.video_status == "processing":
                self._draw_video_progress_strip(w, 0, h, expanded=False)
                return
            if self.selected_text:
                cy = h / 2
                center = content_width / 2
                for x in (center - 8, center, center + 8):
                    self.canvas.create_oval(x - 2, cy - 2, x + 2, cy + 2, fill=self.WAVEFORM_HOT, outline="")
            if has_video:
                self._draw_video_status(w, h, compact=True)
            return

        c = self.canvas
        progress_offset = self.video_progress_hover_height + 4 if self.video_status == "processing" else 0
        action_top = progress_offset
        action_height = h - action_top
        cy = action_top + action_height / 2
        if self.video_status == "processing":
            self._draw_video_progress_strip(w, 0, self.video_progress_hover_height, expanded=True)
            self._draw_pill(2, action_top + 2, w - 2, h - 2, action_height // 2 - 2, self.BG, self.BORDER_COLOR)
        video_left = content_width - self.video_action_width
        if self._hover_zone == "speak":
            self._draw_pill(4, action_top + 4, video_left - 4, h - 4, 12, self.BG_HOVER, self.ORANGE_ACCENT)
        if self._hover_zone == "video_flow":
            self._draw_pill(video_left + 4, action_top + 4, content_width - 4, h - 4, 12, self.BG_HOVER, self.ORANGE_ACCENT)
        c.create_text(video_left / 2, cy, text="Click to speak", fill=self.ORANGE_ACCENT if self._hover_zone == "speak" else self.TEXT_WHITE, font=(config.bar_font_family, 9, "bold"), anchor="center")
        c.create_line(video_left, action_top + 7, video_left, h - 7, fill=self.BORDER_COLOR, width=1)
        c.create_text(video_left + self.video_action_width / 2, cy, text="⋯ Video", fill=self.ORANGE_ACCENT if self._hover_zone == "video_flow" else self.TEXT_WHITE, font=(config.bar_font_family, 8, "bold"), anchor="center")
        if has_video and self.video_status != "processing":
            c.create_line(content_width, action_top + 7, content_width, h - 7, fill=self.BORDER_COLOR, width=1)
            self._draw_video_status(w, h, compact=False)

    def _draw_video_progress_strip(self, w: int, top: int, bottom: int, *, expanded: bool) -> None:
        """Draw Video Flow as a compact luminous rail, independent of active Voice/Audio UI."""
        c = self.canvas
        mid = (top + bottom) / 2
        if expanded:
            self._draw_pill(2, top + 1, w - 2, bottom - 1, 10, "#0a1117", "#253441")
            c.create_text(11, top + 7, text="VIDEO FLOW", fill="#ff7a2f", font=(config.bar_font_family, 6, "bold"), anchor="w")
            c.create_text(w - 42, top + 7, text=f"{self.video_progress}%", fill=self.TEXT_WHITE, font=(config.bar_font_family, 7, "bold"), anchor="e")
            track_y = bottom - 6
        else:
            track_y = mid
            c.create_text(
                10,
                mid,
                text="Video Flow",
                fill=self.ORANGE_ACCENT,
                font=(config.bar_font_family, 6, "bold"),
                anchor="w",
            )

        track_left = 70 if not expanded else 8
        track_right = w - 34
        fraction = max(0.0, min(1.0, self.video_progress / 100.0))
        fill_right = track_left + (track_right - track_left) * fraction
        c.create_line(track_left, track_y, track_right, track_y, fill="#20303d", width=4, capstyle="round")
        if fill_right > track_left:
            c.create_line(track_left, track_y, fill_right, track_y, fill="#71301a", width=7, capstyle="round")
            c.create_line(track_left, track_y, fill_right, track_y, fill="#ff6b19", width=3, capstyle="round")
            gleam = min(fill_right, max(track_left, fill_right - 10 + math.sin(self._anim_phase * 2.8) * 5))
            c.create_line(max(track_left, gleam - 7), track_y, gleam, track_y, fill="#ffd2b8", width=2, capstyle="round")

        knob_x = w - 18
        if expanded or self.state != "READY":
            c.create_oval(knob_x - 9, mid - 9, knob_x + 9, mid + 9, fill="#17232c", outline="#ff6b19", width=1)
            c.create_rectangle(knob_x - 3, mid - 4, knob_x - 1, mid + 4, fill="#ffffff", outline="")
            c.create_rectangle(knob_x + 2, mid - 4, knob_x + 4, mid + 4, fill="#ffffff", outline="")
    def _draw_video_status(self, w: int, h: int, *, compact: bool) -> None:
        c = self.canvas
        cx = w - (15 if compact else 22)
        cy = h / 2
        radius = 5 if compact else 9
        if self.video_status == "processing":
            c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline="#31445a", width=2)
            angle = self._anim_phase * 5
            dot_x = cx + math.cos(angle) * radius
            dot_y = cy + math.sin(angle) * radius
            c.create_oval(dot_x - 2, dot_y - 2, dot_x + 2, dot_y + 2, fill="#06cfe5", outline="")
            if not compact:
                c.create_text(cx - 42, cy, text="Video Flow", fill=self.ORANGE_ACCENT, font=(config.bar_font_family, 8, "bold"), anchor="e")
            if not compact:
                c.create_text(cx, cy, text=str(max(0, min(99, int(self.video_progress)))), fill=self.TEXT_PRIMARY, font=(config.bar_font_family, 6, "bold"), anchor="center")
        elif self.video_status == "ready":
            c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=self.DONE_GREEN, outline="")
            c.create_line(cx - 4, cy, cx - 1, cy + 3, fill="white", width=2, capstyle="round")
            c.create_line(cx - 1, cy + 3, cx + 5, cy - 4, fill="white", width=2, capstyle="round")
        else:
            c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=self.CANCEL_HOVER, outline="")
            c.create_text(cx, cy, text="!", fill="white", font=(config.bar_font_family, 8, "bold"), anchor="center")
    def _draw_reading(self, w: int, h: int) -> None:
        self._draw_working_state(w, h, "Audio Flow")

    def _draw_recording(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2

        cancel_color = self.CANCEL_HOVER if self._hover_zone == "cancel" else self.CANCEL_NORMAL
        cx_cancel = 28
        size = 6
        c.create_line(cx_cancel - size, cy - size, cx_cancel + size, cy + size, fill=cancel_color, width=2, capstyle="round")
        c.create_line(cx_cancel + size, cy - size, cx_cancel - size, cy + size, fill=cancel_color, width=2, capstyle="round")

        try:
            level = float(self.get_audio_level() or 0.0)
            if math.isnan(level) or math.isinf(level):
                level = 0.0
        except Exception:
            level = 0.0

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
        self._draw_working_state(w, h, "Transcribing")

    def _draw_working_shell(self, w: int, h: int) -> None:
        """Draw the two-section dark card used only while a flow is working."""
        c = self.canvas
        self._draw_pill(2, 2, w - 2, h - 2, 11, "#120c0a", "#251611")
        c.create_rectangle(6, 6, w - 6, 40, fill="#0a0e0f", outline="")
        c.create_rectangle(7, 40, w - 7, 41, fill="#24120d", outline="")

    def _draw_working_state(self, w: int, h: int, flow_name: str) -> None:
        """Match the reference scan-line card and travelling orange waveform."""
        c = self.canvas
        c.create_text(
            w / 2,
            23,
            text=flow_name,
            fill="#f7f5f1",
            font=("Consolas", 12, "bold"),
            anchor="center",
        )

        scan_left = 62
        scan_right = w - 26
        scan_center = 64
        scan_colors = ("#32100b", "#49140c", "#6a1b0e", "#8c2411", "#6a1b0e", "#49140c", "#32100b")
        for index, color in enumerate(scan_colors):
            y = scan_center + (index - 3) * 4
            shimmer = (math.sin(self._anim_phase * 2.4 + index * 0.8) + 1.0) / 2.0
            inset = int((1.0 - shimmer) * 18)
            c.create_line(scan_left + inset, y, scan_right - inset, y, fill=color, width=2)

        cycle = (self._anim_phase * 0.18) % 1.0
        pulse_center = -0.08 + cycle * 1.16
        points: list[float] = []
        point_count = 54
        for index in range(point_count):
            position = index / (point_count - 1)
            x = scan_left + position * (scan_right - scan_left)
            distance = position - pulse_center
            envelope = math.exp(-((distance / 0.16) ** 2))
            leading = math.sin(distance * 31.0 - self._anim_phase * 1.9)
            secondary = math.sin(distance * 67.0 + self._anim_phase * 1.2) * 0.38
            y = scan_center - (leading + secondary) * envelope * 17
            points.extend((x, y))

        c.create_line(*points, fill="#5b1a0c", width=8, smooth=True, splinesteps=14)
        c.create_line(*points, fill="#a62a10", width=5, smooth=True, splinesteps=14)
        c.create_line(*points, fill="#ff6428", width=2, smooth=True, splinesteps=14)

        label_x = 18
        label_y = h - 13
        for offset_x, offset_y in ((-2, 0), (2, 0), (0, -1), (0, 1)):
            c.create_text(
                label_x + offset_x,
                label_y + offset_y,
                text="WORKING",
                fill="#64110b",
                font=("Consolas", 10, "bold"),
                anchor="w",
            )
        c.create_text(
            label_x,
            label_y,
            text="WORKING",
            fill="#ff2a18",
            font=("Consolas", 10, "bold"),
            anchor="w",
        )

    def _draw_done(self, w: int, h: int) -> None:
        c = self.canvas
        cy = h / 2
        circle_x = w / 2 - 45
        r = 8
        c.create_oval(circle_x - r, cy - r, circle_x + r, cy + r, fill=self.DONE_GREEN, outline="")
        c.create_line(circle_x - 3, cy, circle_x - 1, cy + 3, fill="white", width=2, capstyle="round")
        c.create_line(circle_x - 1, cy + 3, circle_x + 4, cy - 3, fill="white", width=2, capstyle="round")
        c.create_text(w / 2 + 10, cy, text="Done", fill=self.DONE_GREEN, font=(config.bar_font_family, 12, "bold"), anchor="center")

    def _draw_error(self, w: int, h: int) -> None:
        """Keep recoverable failures neutral and avoid exposing raw provider errors."""
        self.canvas.create_text(
            w / 2,
            h / 2,
            text="Working",
            fill=self.TEXT_WHITE,
            font=(config.bar_font_family, 10, "bold"),
            anchor="center",
        )

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
