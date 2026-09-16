"""Sunrise Audio Flow Voice Model Catalog & Speed Settings Dialog.

A modern, elegant on-screen dialog displaying:
1. Real-time audio playback speed adjustment pills ([0.75x] [1.0x] [1.25x] [1.5x] [1.75x] [2.0x]).
2. The COMPLETE voice model catalog with all 32+ models across providers:
   - Microsoft Edge Neural (Free, high-quality human voices)
   - Deepgram Aura
   - OpenAI TTS
   - ElevenLabs
   - Google Cloud
   - System Windows SAPI5 / Local
"""

from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from voice_flow.storage import storage

log = logging.getLogger(__name__)

# --- "Sunrise" design system colors ---
ORANGE = "#FF6A00"
ORANGE_DEEP = "#E85D04"
ORANGE_SOFT = "#FFE3D0"
ORANGE_FAINT = "#FFF3EA"
WHITE = "#FFFFFF"
INK = "#241708"
GRAY = "#8A8A93"
BORDER = "#FFD0B0"
BG_LIGHT = "#FAFAFA"

SPEEDS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]


def calculate_anchored_dialog_geometry(
    win: tk.Tk | tk.Toplevel,
    parent: tk.Tk | tk.Toplevel | None = None,
    default_w: int = 420,
    default_h: int = 520,
    gap: int = 10,
) -> tuple[int, int, int, int]:
    """Calculate (w, h, x, y) to position a dialog window directly attached above its floating bar."""
    try:
        win.update_idletasks()
    except Exception:
        pass

    try:
        w = win.winfo_width()
        if w < 100:
            w = default_w
    except Exception:
        w = default_w

    try:
        h = win.winfo_height()
        if h < 100:
            h = default_h
    except Exception:
        h = default_h

    # Virtual desktop bounds across all monitors
    min_x, min_y = 0, 0
    sw, sh = 1920, 1080
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            vx = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
            vy = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
            vw = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
            vh = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
            if vw > 0 and vh > 0:
                min_x, min_y, sw, sh = vx, vy, vw, vh
        except Exception:
            pass

    if sw <= 0:
        try:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080

    # Determine anchor position from floating overlay bar
    anchor_x, anchor_y, anchor_w, anchor_h = None, None, None, None

    # Helper to resolve overlay bar instance
    ov = None
    if parent is not None:
        if hasattr(parent, "_drawn_width") or hasattr(parent, "_user_pos"):
            ov = parent
        elif hasattr(parent, "overlay") and getattr(parent, "overlay", None) is not None:
            ov = getattr(parent, "overlay", None)

    if ov is None:
        try:
            from voice_flow.gui.api_server import runtime_controller
            if runtime_controller and getattr(runtime_controller, "overlay", None):
                ov = runtime_controller.overlay
        except Exception:
            pass

    if ov is not None:
        try:
            drawn_fn = getattr(ov, "_drawn_width", None)
            ow = drawn_fn() if callable(drawn_fn) else getattr(ov, "width", 280)
            oh = getattr(ov, "height", 26)
            # Check user-dragged position first
            user_pos = getattr(ov, "_user_pos", None)
            if user_pos is not None and isinstance(user_pos, (tuple, list)) and len(user_pos) == 2:
                anchor_cx, anchor_by = user_pos
                anchor_x = int(anchor_cx - ow // 2)
                anchor_y = int(anchor_by - oh)
                anchor_w = int(ow)
                anchor_h = int(oh)
            elif getattr(ov, "win", None) and hasattr(ov.win, "winfo_exists") and ov.win.winfo_exists():
                try:
                    ov.win.update_idletasks()
                except Exception:
                    pass
                px = ov.win.winfo_rootx() if hasattr(ov.win, "winfo_rootx") else ov.win.winfo_x()
                py = ov.win.winfo_rooty() if hasattr(ov.win, "winfo_rooty") else ov.win.winfo_y()
                if px > 0 or py > 0:
                    anchor_x, anchor_y, anchor_w, anchor_h = px, py, ow, oh
                else:
                    # Parse geometry string as fallback
                    import re
                    geom = ov.win.geometry()
                    m = re.search(r'\+([+-]?\d+)\+([+-]?\d+)', geom)
                    if m:
                        anchor_x = int(m.group(1))
                        anchor_y = int(m.group(2))
                        anchor_w = int(ow)
                        anchor_h = int(oh)

            if anchor_x is None:
                # Calculate from dock setting
                dock = getattr(ov, "dock", "bottom")
                if dock == "left":
                    anchor_x = min_x + 8
                    anchor_y = min_y + (sh - oh) // 2
                elif dock == "right":
                    anchor_x = min_x + sw - ow - 8
                    anchor_y = min_y + (sh - oh) // 2
                else:
                    anchor_x = min_x + (sw - ow) // 2
                    anchor_y = min_y + sh - oh - 60
                anchor_w = int(ow)
                anchor_h = int(oh)
        except Exception:
            pass

    # Fallback to checking parent Tkinter widget directly if overlay object wasn't found
    if anchor_x is None and parent and hasattr(parent, "winfo_exists") and parent.winfo_exists():
        try:
            px = parent.winfo_rootx() if hasattr(parent, "winfo_rootx") else parent.winfo_x()
            py = parent.winfo_rooty() if hasattr(parent, "winfo_rooty") else parent.winfo_y()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            if pw > 0 and ph > 0:
                anchor_x, anchor_y, anchor_w, anchor_h = px, py, pw, ph
        except Exception:
            pass

    if anchor_x is not None and anchor_y is not None and anchor_w is not None and anchor_h is not None:
        # Center horizontally directly with the anchor floating bar
        center_x = anchor_x + anchor_w // 2
        x = center_x - w // 2

        # Position directly attached above the anchor floating bar with specified gap
        y = anchor_y - h - gap

        # If not enough room above (e.g. bar is near the top edge), position below the floating bar
        if y < min_y + 10:
            y = anchor_y + anchor_h + gap
    else:
        # Default to screen center
        x = min_x + (sw - w) // 2
        y = min_y + (sh - h) // 2

    # Clamp strictly within visible desktop bounds
    max_x = min_x + sw
    max_y = min_y + sh
    x = max(min_x + 10, min(x, max_x - w - 10))
    y = max(min_y + 10, min(y, max_y - h - 10))

    return w, h, x, y


class AudioFlowSettingsDialog:
    """On-screen Voice Model Catalog and Real-Time Speed Settings Dialog."""

    _instance: AudioFlowSettingsDialog | None = None

    @classmethod
    def show_dialog(
        cls,
        parent: Any = None,
        on_speed_change: Callable[[float], None] | None = None,
        on_voice_change: Callable[[str], None] | None = None,
    ) -> AudioFlowSettingsDialog:
        if cls._instance is not None and cls._instance.win and cls._instance.win.winfo_exists():
            if parent is not None:
                cls._instance.parent = parent
                cls._instance._anchor_win = parent
            if on_speed_change is not None:
                cls._instance.on_speed_change = on_speed_change
            if on_voice_change is not None:
                cls._instance.on_voice_change = on_voice_change
            cls._instance._center_window()
            cls._instance.win.deiconify()
            cls._instance.win.state("normal")
            cls._instance.win.lift()
            cls._instance.win.attributes("-topmost", True)
            cls._instance.win.focus_force()
            return cls._instance

        inst = cls(parent, on_speed_change, on_voice_change)
        cls._instance = inst
        return inst

    def __init__(
        self,
        parent: Any = None,
        on_speed_change: Callable[[float], None] | None = None,
        on_voice_change: Callable[[str], None] | None = None,
    ) -> None:
        self.parent = parent
        self._anchor_win = parent
        self.on_speed_change = on_speed_change
        self.on_voice_change = on_voice_change

        # Safely resolve Tkinter widget master from parent object or default root
        master = None
        if isinstance(parent, (tk.Tk, tk.Toplevel, tk.BaseWidget)):
            master = parent
        elif parent is not None:
            master = getattr(parent, "win", None) or getattr(parent, "root", None)
        if master is None:
            master = getattr(tk, "_default_root", None)

        self.root = master
        self.win = tk.Toplevel(master) if master is not None else tk.Tk()
        self.win.withdraw()
        self.win.title("Audio Flow Settings & Voice Catalog")
        self.win.geometry("420x520")
        self.win.minsize(380, 460)
        self.win.config(bg=BG_LIGHT)
        self.win.attributes("-topmost", True)

        try:
            self.win.attributes("-alpha", 0.99)
        except Exception:
            pass

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

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._render_models_list())

        self._build_ui()
        self._center_window()

        self.win.deiconify()
        self.win.state("normal")
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.win.focus_force()

    def _center_window(self) -> None:
        if not self.win or not self.win.winfo_exists():
            return
        try:
            anchor = getattr(self, "_anchor_win", None) or self.parent
            w, h, x, y = calculate_anchored_dialog_geometry(
                self.win,
                parent=anchor,
                default_w=420,
                default_h=520,
                gap=10,
            )
            self.win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _get_current_speed(self) -> float:
        try:
            return float(storage.get_setting("audio_flow_speed", 1.0) or 1.0)
        except Exception:
            return 1.0

    def _get_active_voice(self) -> str:
        return storage.get_setting("exec_audio_policy_model", "edge/en-US-AvaNeural") or "edge/en-US-AvaNeural"

    def _set_speed(self, speed: float) -> None:
        storage.save_setting("audio_flow_speed", speed)
        if self.on_speed_change:
            self.on_speed_change(speed)
        self._refresh_speed_pills()

    def _select_voice(self, model_id: str) -> None:
        storage.save_setting("exec_audio_policy_model", model_id)
        if self.on_voice_change:
            self.on_voice_change(model_id)
        self._render_models_list()

    def _build_ui(self) -> None:
        # Header Frame
        header = tk.Frame(self.win, bg=WHITE, bd=0, highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x", padx=0, pady=0)

        title_lbl = tk.Label(
            header,
            text="🎙️ Audio Flow Settings",
            bg=WHITE,
            fg=INK,
            font=("Segoe UI", 12, "bold"),
            padx=16,
            pady=12,
        )
        title_lbl.pack(side="left")

        def _save_and_close() -> None:
            try:
                storage.save_setting("audio_flow_speed", self._get_current_speed())
                storage.save_setting("exec_audio_policy_model", self._get_active_voice())
                if self.on_speed_change:
                    self.on_speed_change(self._get_current_speed())
                if self.on_voice_change:
                    self.on_voice_change(self._get_active_voice())
            except Exception:
                pass
            self.win.destroy()

        self.win.bind("<Escape>", lambda _: self.win.destroy())

        close_btn = tk.Button(
            header,
            text="✕",
            bg=WHITE,
            fg=GRAY,
            activebackground=ORANGE_FAINT,
            activeforeground=ORANGE_DEEP,
            font=("Segoe UI", 10, "bold"),
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self.win.destroy,
            padx=8,
            pady=4,
        )
        close_btn.pack(side="right", padx=(4, 12))

        save_btn = tk.Button(
            header,
            text="💾 Save",
            bg=ORANGE,
            fg=WHITE,
            activebackground=ORANGE_DEEP,
            activeforeground=WHITE,
            font=("Segoe UI", 9, "bold"),
            bd=0,
            cursor="hand2",
            command=_save_and_close,
            padx=16,
            pady=6,
        )
        save_btn.pack(side="right", padx=(0, 4))
        self._save_btn = save_btn

        # Main Body
        body = tk.Frame(self.win, bg=BG_LIGHT, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        # 1. Real-Time Audio Speed Section
        spd_lbl = tk.Label(
            body,
            text=f"⚡ PLAYBACK SPEED (REAL-TIME) — ACTIVE: {self._get_current_speed():g}x",
            bg=BG_LIGHT,
            fg=ORANGE_DEEP,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        spd_lbl.pack(fill="x", pady=(0, 6))
        self._speed_header_lbl = spd_lbl

        self.speed_frame = tk.Frame(body, bg=BG_LIGHT)
        self.speed_frame.pack(fill="x", pady=(0, 14))
        self.speed_buttons: list[tk.Button] = []
        self._refresh_speed_pills()

        # 2. Voice Model Catalog Section
        cat_header = tk.Frame(body, bg=BG_LIGHT)
        cat_header.pack(fill="x", pady=(0, 6))

        cat_lbl = tk.Label(
            cat_header,
            text="🎙️ VOICE MODEL CATALOG",
            bg=BG_LIGHT,
            fg=INK,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        cat_lbl.pack(side="left")

        cat_sub = tk.Label(
            cat_header,
            text="(All 32+ Models)",
            bg=BG_LIGHT,
            fg=GRAY,
            font=("Segoe UI", 7),
            anchor="w",
        )
        cat_sub.pack(side="left", padx=6)

        # Search Bar
        search_frame = tk.Frame(body, bg=WHITE, bd=0, highlightthickness=1, highlightbackground=BORDER)
        search_frame.pack(fill="x", pady=(0, 8))

        search_icon = tk.Label(search_frame, text="🔍", bg=WHITE, fg=GRAY, font=("Segoe UI", 9))
        search_icon.pack(side="left", padx=(10, 4))

        search_entry = tk.Entry(
            search_frame,
            textvariable=self._search_var,
            bg=WHITE,
            fg=INK,
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
            insertbackground=ORANGE,
        )
        search_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))
        search_entry.bind("<FocusIn>", lambda _: search_frame.config(highlightbackground=ORANGE))
        search_entry.bind("<FocusOut>", lambda _: search_frame.config(highlightbackground=BORDER))

        # Models Scrollable List
        list_container = tk.Frame(body, bg=WHITE, bd=0, highlightthickness=1, highlightbackground=BORDER)
        list_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_container, bg=WHITE, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=WHITE)
        self._list_inner = tk.Frame(self.scrollable_frame, bg=WHITE)
        self._list_inner.pack(fill="both", expand=True)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width),
        )
        self.canvas.configure(xscrollcommand=None, yscrollcommand=scrollbar.set)

        # Mouse wheel support with clean enter/leave scoping
        def _on_mousewheel(event):
            try:
                if self.canvas and self.canvas.winfo_exists():
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.canvas.bind("<Enter>", lambda _: self.canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.canvas.bind("<Leave>", lambda _: self.canvas.unbind_all("<MouseWheel>"))
        self.win.bind("<Destroy>", lambda _: self.canvas.unbind_all("<MouseWheel>") if getattr(self, "canvas", None) else None)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._render_models_list()

    def _refresh_speed_pills(self) -> None:
        for w in self.speed_frame.winfo_children():
            w.destroy()
        self.speed_buttons.clear()

        curr_speed = self._get_current_speed()
        if hasattr(self, "_speed_header_lbl") and self._speed_header_lbl.winfo_exists():
            self._speed_header_lbl.config(text=f"⚡ PLAYBACK SPEED (REAL-TIME) — ACTIVE: {curr_speed:g}x")

        for spd in SPEEDS:
            is_active = abs(spd - curr_speed) < 0.01
            bg_col = ORANGE if is_active else WHITE
            fg_col = WHITE if is_active else INK
            bd_col = ORANGE_DEEP if is_active else BORDER

            btn = tk.Button(
                self.speed_frame,
                text=f"{spd:g}x",
                bg=bg_col,
                fg=fg_col,
                activebackground=ORANGE_DEEP,
                activeforeground=WHITE,
                font=("Segoe UI", 8, "bold"),
                bd=0,
                relief="flat",
                highlightthickness=1,
                highlightbackground=bd_col,
                cursor="hand2",
                command=lambda s=spd: self._set_speed(s),
                padx=8,
                pady=5,
            )
            if not is_active:
                btn.bind("<Enter>", lambda e, b=btn: [b.config(bg=ORANGE_FAINT, fg=ORANGE_DEEP, highlightbackground=ORANGE)])
                btn.bind("<Leave>", lambda e, b=btn: [b.config(bg=WHITE, fg=INK, highlightbackground=BORDER)])

            btn.pack(side="left", expand=True, fill="x", padx=2)
            self.speed_buttons.append(btn)

    def _render_models_list(self) -> None:
        for w in self._list_inner.winfo_children():
            w.destroy()

        policy = storage.get_exec_audio_policy_options(include_all_catalog=True)
        all_models = policy.get("models", [])
        active_voice = self._get_active_voice()
        search_term = self._search_var.get().lower().strip()

        # Group models by provider
        groups: dict[str, list[dict]] = {}
        for m in all_models:
            full_id = m.get("full_id") or ""
            label = m.get("display_name") or m.get("label") or full_id
            prov = (m.get("provider") or (full_id.split("/")[0] if "/" in full_id else "edge")).upper()

            if search_term and (search_term not in label.lower() and search_term not in full_id.lower() and search_term not in prov.lower()):
                continue

            groups.setdefault(prov, []).append(m)

        if not groups:
            no_lbl = tk.Label(
                self._list_inner,
                text="No voice models match your search.",
                bg=WHITE,
                fg=GRAY,
                font=("Segoe UI", 9),
                pady=20,
            )
            no_lbl.pack(fill="x")
            return

        prov_map = {
            "EDGE": "⚡ Microsoft Edge Neural",
            "DEEPGRAM": "🌐 Deepgram Aura",
            "OPENAI": "🧠 OpenAI TTS",
            "ELEVENLABS": "🎙️ ElevenLabs",
            "GOOGLE": "☁️ Google Cloud",
            "SYSTEM": "💻 System Windows",
            "LOCAL": "💻 Local Deterministic",
        }

        for prov, models in groups.items():
            # Group Header
            gh = tk.Frame(self._list_inner, bg=ORANGE_FAINT, padx=10, pady=5)
            gh.pack(fill="x", pady=(6, 2))
            header_title = prov_map.get(prov, f"● {prov}")
            glbl = tk.Label(
                gh,
                text=f"{header_title} ({len(models)} voices)",
                bg=ORANGE_FAINT,
                fg=ORANGE_DEEP,
                font=("Segoe UI", 8, "bold"),
                anchor="w",
            )
            glbl.pack(fill="x")

            for m in models:
                fid = m.get("full_id") or ""
                disp = m.get("display_name") or m.get("label") or fid
                is_sel = fid == active_voice

                row = tk.Frame(
                    self._list_inner,
                    bg=ORANGE_SOFT if is_sel else WHITE,
                    padx=10,
                    pady=6,
                    cursor="hand2",
                )
                row.pack(fill="x", pady=1)

                # Fixed-geometry selection indicator (zero text-jumping)
                ind_lbl = tk.Label(
                    row,
                    text="✓" if is_sel else "○",
                    bg=ORANGE_SOFT if is_sel else WHITE,
                    fg=ORANGE_DEEP if is_sel else BORDER,
                    font=("Segoe UI", 9, "bold" if is_sel else "normal"),
                    width=2,
                    anchor="center",
                )
                ind_lbl.pack(side="left", padx=(0, 4))

                txt_lbl = tk.Label(
                    row,
                    text=disp,
                    bg=ORANGE_SOFT if is_sel else WHITE,
                    fg=ORANGE_DEEP if is_sel else INK,
                    font=("Segoe UI", 8, "bold" if is_sel else "normal"),
                    anchor="w",
                )
                txt_lbl.pack(side="left", fill="x", expand=True)

                short_prov = prov.title() if prov else "Neural"
                prov_tag = tk.Label(
                    row,
                    text=short_prov,
                    bg=ORANGE_FAINT if is_sel else "#F5F5F7",
                    fg=ORANGE_DEEP if is_sel else GRAY,
                    font=("Segoe UI", 7, "bold"),
                    padx=6,
                    pady=2,
                )
                prov_tag.pack(side="right", padx=(6, 0))

                if not is_sel:
                    def _hover_enter(e, r=row, l=txt_lbl, i=ind_lbl, t=prov_tag):
                        r.config(bg=ORANGE_FAINT)
                        l.config(bg=ORANGE_FAINT, fg=ORANGE_DEEP)
                        i.config(bg=ORANGE_FAINT, fg=ORANGE)
                        t.config(bg=WHITE, fg=ORANGE_DEEP)

                    def _hover_leave(e, r=row, l=txt_lbl, i=ind_lbl, t=prov_tag):
                        r.config(bg=WHITE)
                        l.config(bg=WHITE, fg=INK)
                        i.config(bg=WHITE, fg=BORDER)
                        t.config(bg="#F5F5F7", fg=GRAY)

                    for widget_item in (row, txt_lbl, ind_lbl, prov_tag):
                        widget_item.bind("<Enter>", _hover_enter)
                        widget_item.bind("<Leave>", _hover_leave)

                def _bind_click(widget, target_id=fid):
                    widget.bind("<Button-1>", lambda _: self._select_voice(target_id))

                for widget_item in (row, txt_lbl, ind_lbl, prov_tag):
                    _bind_click(widget_item)


def open_audio_flow_settings(parent: tk.Tk | tk.Toplevel | None = None, on_speed_change: Callable[[float], None] | None = None, on_voice_change: Callable[[str], None] | None = None) -> AudioFlowSettingsDialog:
    """Convenience helper to show the settings dialog."""
    return AudioFlowSettingsDialog.show_dialog(parent, on_speed_change, on_voice_change)