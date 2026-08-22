"""System-wide Video Flow composer and player launcher.

The composer is intentionally independent of the desktop dashboard.  It is
attached to the floating bar's Tk root so selected text can become a video
without opening the main Voice Flow application.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from voice_flow.video_flow_documents import DOCUMENT_EXTENSIONS, MAX_DOCUMENT_BYTES, extract_document_text


LOCAL_MODEL_REF = "local/deterministic"

# Keep this palette scoped to the native Video Flow composer.  It does not
# modify the dashboard or the rest of the application-wide Tk styling.
COMPOSER_COLORS = {
    "background": "#fff8f3",
    "surface": "#ffffff",
    "surface_soft": "#fff0e6",
    "text": "#2b211b",
    "muted": "#74635a",
    "border": "#f0c8b2",
    "orange": "#ff6b19",
    "orange_dark": "#d95009",
    "orange_active": "#e95d10",
}


class VideoFlowScreenWidget:
    """Always-on-top composer that delegates queued jobs to the main runtime."""

    def __init__(self) -> None:
        self.root: tk.Tk | None = None
        self.win: tk.Toplevel | None = None
        self.on_generate: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self._source_text = ""
        self._source_name = ""
        self._mode = "summary"
        self._controls: dict[str, Any] = {}
        self._model_options: dict[str, dict[str, str]] = {}
        self._theme_options: dict[str, dict[str, str]] = {}

    def attach_root(self, root: tk.Tk) -> None:
        self.root = root

    def launch(self, selected_text: str = "", mode: str = "summary") -> "VideoFlowScreenWidget":
        """Public, stable entrypoint for callers outside the dashboard."""
        self.show_composer(selected_text, mode)
        return self

    @staticmethod
    def catalog_model_options(catalog: dict[str, Any] | None) -> list[dict[str, str]]:
        """Build the same selectable model list used by the in-app catalog."""
        catalog = catalog or {}
        external: list[dict[str, str]] = []
        selectable_refs: set[str] = set()
        seen_refs: set[str] = set()

        for item in catalog.get("models", ()) or ():
            if not isinstance(item, dict):
                continue
            ref = str(item.get("full_id") or "").strip()
            # Matches vfSelectableVideoModels(): connected/available,
            # explicitly enabled, and capable of original scene authorship.
            if not ref or ref == LOCAL_MODEL_REF or not item.get("available") or item.get("is_active") is False:
                continue
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            selectable_refs.add(ref)
            provider = str(item.get("provider_name") or item.get("provider") or ref.split("/", 1)[0]).strip()
            display_name = str(item.get("display_name") or item.get("model_id") or ref.split("/", 1)[-1]).strip()
            capabilities = [str(value).replace("_", " ") for value in item.get("capabilities", ()) or () if value]
            detail = f"{provider} · {ref}"
            if capabilities:
                detail += " · " + ", ".join(capabilities[:2])
            external.append({"ref": ref, "label": f"{provider} · {display_name}", "detail": detail})

        combos: list[dict[str, str]] = []
        for combo in catalog.get("combos", ()) or ():
            if not isinstance(combo, dict):
                continue
            members = [str(ref).strip() for ref in combo.get("models", ()) or () if str(ref).strip()]
            name = str(combo.get("name") or "").strip()
            ref = str(combo.get("ref") or (f"combo:{name}" if name else "")).strip()
            if not ref or not members or not all(member in selectable_refs for member in members):
                continue
            strategy = str(combo.get("strategy") or "fallback").replace("_", " ")
            combos.append({
                "ref": ref,
                "label": f"Model combo · {name or ref.removeprefix('combo:')}",
                "detail": f"{len(members)} models · {strategy}",
            })

        options = [*combos, *external]
        used_labels: set[str] = set()
        for option in options:
            label = option["label"]
            if label in used_labels:
                label = f"{label} · {option['ref']}"
            used_labels.add(label)
            option["label"] = label
        return options

    @staticmethod
    def catalog_theme_options(catalog: dict[str, Any] | None) -> list[dict[str, str]]:
        """Build supported visual themes with a user-facing Auto default."""
        catalog = catalog or {}
        options: list[dict[str, str]] = []
        seen: set[str] = set()
        for value in ["auto", *(catalog.get("themes", ()) or ())]:
            theme = str(value or "").strip().lower()
            if not theme or theme in seen:
                continue
            seen.add(theme)
            label = "Auto" if theme == "auto" else theme.replace("-", " ").replace("_", " ").title()
            detail = "Adapts the visual language to the source" if theme == "auto" else f"{label} visual language"
            options.append({"ref": theme, "label": label, "detail": detail})
        return options

    def show_composer(self, selected_text: str = "", mode: str = "summary") -> None:
        clean = (selected_text or "").strip()
        self._mode = mode if mode in {"summary", "full"} else "summary"

        def _show() -> None:
            if not self.root:
                return
            if not self.win or not self.win.winfo_exists():
                self._build()
            if not self.win:
                return
            text = self._controls["source"]
            text.delete("1.0", "end")
            text.insert("1.0", clean)
            self._source_text = clean
            self._source_name = "Selected text" if clean else ""
            self._controls["mode"].set(self._mode)
            self._controls["file_label"].set(self._source_name or "No document selected")
            self._controls["status"].set("Selected text is ready." if clean else "Paste text or choose a document.")
            self._refresh_models()
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
            self.win.focus_force()
            self._center()

        self._run_on_ui(_show)

    def _build(self) -> None:
        if not self.root:
            return
        colors = COMPOSER_COLORS
        win = tk.Toplevel(self.root)
        self.win = win
        win.withdraw()
        win.title("Video Flow — Create video")
        win.geometry("560x600")
        win.minsize(520, 560)
        win.resizable(True, True)
        win.attributes("-topmost", True)
        win.configure(bg=colors["background"])
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        self._configure_styles(win)

        viewport = tk.Frame(win, bg=colors["background"])
        viewport.pack(fill="both", expand=True)

        scroll_canvas = tk.Canvas(
            viewport,
            bg=colors["background"],
            highlightthickness=0,
            bd=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        shell = tk.Frame(scroll_canvas, bg=colors["background"], padx=18, pady=16)
        shell_window = scroll_canvas.create_window((0, 0), window=shell, anchor="nw")

        def sync_scroll_region(_event: object | None = None) -> None:
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def sync_shell_width(event: tk.Event) -> None:
            scroll_canvas.itemconfigure(shell_window, width=max(1, event.width))

        shell.bind("<Configure>", sync_scroll_region)
        scroll_canvas.bind("<Configure>", sync_shell_width)

        def scroll_wheel(event: tk.Event) -> str:
            try:
                if event.widget.winfo_toplevel() != win:
                    return "break"
                delta = int(getattr(event, "delta", 0))
                steps = -int(delta / 120) if delta else 0
                if not steps:
                    steps = -1 if delta > 0 else 1
                scroll_canvas.yview_scroll(steps, "units")
            except (AttributeError, tk.TclError, ValueError):
                pass
            return "break"

        def scroll_button(event: tk.Event) -> str:
            try:
                if event.widget.winfo_toplevel() == win:
                    scroll_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
            except (AttributeError, tk.TclError):
                pass
            return "break"

        win.bind_all("<MouseWheel>", scroll_wheel, add="+")
        win.bind_all("<Button-4>", scroll_button, add="+")
        win.bind_all("<Button-5>", scroll_button, add="+")
        tk.Label(shell, text="VIDEO FLOW", bg=colors["background"], fg=colors["orange_dark"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(shell, text="Turn text or documents into video", bg=colors["background"], fg=colors["text"], font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(3, 2))
        tk.Label(shell, text="Create from selected text, a paste, or a document — no dashboard required.", bg=colors["background"], fg=colors["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 10))

        mode_var = tk.StringVar(value=self._mode)
        mode_row = tk.Frame(shell, bg=colors["background"])
        mode_row.pack(fill="x", pady=(0, 8))
        mode_buttons: dict[str, tk.Radiobutton] = {}
        for value, icon, label, hint in (
            ("summary", "✦", "Summary video", "Clear highlights"),
            ("full", "≡", "Full explanation", "Every detail"),
        ):
            button = tk.Radiobutton(
                mode_row,
                text=f"{icon}  {label}\n{hint}",
                value=value,
                variable=mode_var,
                indicatoron=False,
                justify="left",
                anchor="w",
                bg=colors["surface"],
                fg=colors["text"],
                selectcolor=colors["orange"],
                activebackground=colors["surface_soft"],
                activeforeground=colors["orange_dark"],
                highlightthickness=1,
                highlightbackground=colors["border"],
                bd=0,
                padx=14,
                pady=7,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 7 if value == "summary" else 0))
            mode_buttons[value] = button

        def refresh_mode_cards(*_args: object) -> None:
            selected = mode_var.get()
            for value, button in mode_buttons.items():
                is_selected = value == selected
                button.configure(
                    bg=colors["orange"] if is_selected else colors["surface"],
                    fg="#ffffff" if is_selected else colors["text"],
                    activebackground=colors["orange_active"] if is_selected else colors["surface_soft"],
                    activeforeground="#ffffff" if is_selected else colors["orange_dark"],
                    highlightbackground=colors["orange"] if is_selected else colors["border"],
                )

        mode_var.trace_add("write", refresh_mode_cards)
        refresh_mode_cards()

        model_ref_var = tk.StringVar(value="")
        model_display_var = tk.StringVar(value="Connect an AI model")
        model_detail_var = tk.StringVar(value="Original Scene Programs require a connected model.")
        theme_ref_var = tk.StringVar(value="auto")
        theme_display_var = tk.StringVar(value="Auto")
        theme_detail_var = tk.StringVar(value="Adapts the visual language to the source")
        file_label = tk.StringVar(value="No document selected")
        status_var = tk.StringVar(value="Paste text or choose a document.")

        self._label(shell, "Document")
        document_row = tk.Frame(shell, bg=colors["background"])
        document_row.pack(fill="x", pady=(3, 8))
        choose = tk.Button(document_row, text="Choose document", command=self._choose_file, bg=colors["surface"], fg=colors["orange_dark"], activebackground=colors["surface_soft"], activeforeground=colors["orange_dark"], relief="flat", bd=0, highlightthickness=1, highlightbackground=colors["border"], padx=12, pady=8, font=("Segoe UI", 9, "bold"), cursor="hand2")
        choose.pack(side="left")
        tk.Label(document_row, textvariable=file_label, bg=colors["background"], fg=colors["muted"], font=("Segoe UI", 8), anchor="w").pack(side="left", fill="x", expand=True, padx=10)
        generate = tk.Button(document_row, text="Generate video", command=self._generate, bg=colors["orange"], fg="#ffffff", activebackground=colors["orange_active"], activeforeground="#ffffff", relief="flat", bd=0, highlightthickness=0, padx=16, pady=9, font=("Segoe UI", 9, "bold"), cursor="hand2")
        generate.pack(side="right")

        title_var = tk.StringVar()
        self._label(shell, "Video title (optional)")
        title = tk.Entry(shell, textvariable=title_var, bg=colors["surface"], fg=colors["text"], insertbackground=colors["text"], relief="flat", highlightthickness=1, highlightbackground=colors["border"], highlightcolor=colors["orange"], font=("Segoe UI", 10))
        title.pack(fill="x", ipady=6, pady=(3, 8))

        self._label(shell, "Source text")
        source = tk.Text(shell, height=6, wrap="word", bg=colors["surface"], fg=colors["text"], insertbackground=colors["text"], relief="flat", highlightthickness=1, highlightbackground=colors["border"], highlightcolor=colors["orange"], padx=10, pady=7, font=("Segoe UI", 10), undo=True)
        source.pack(fill="x", expand=False, pady=(3, 7))

        self._label(shell, "Your visual direction (optional)")
        visual_direction = tk.Text(shell, height=3, wrap="word", bg=colors["surface"], fg=colors["text"], insertbackground=colors["text"], relief="flat", highlightthickness=1, highlightbackground=colors["border"], highlightcolor=colors["orange"], padx=10, pady=7, font=("Segoe UI", 9), undo=True)
        visual_direction.pack(fill="x", expand=False, pady=(3, 7))

        selector_row = tk.Frame(shell, bg=colors["background"])
        selector_row.pack(fill="x", pady=(0, 3))
        selector_row.grid_columnconfigure(0, weight=1)
        selector_row.grid_columnconfigure(1, weight=1)

        model_cell = tk.Frame(selector_row, bg=colors["background"])
        model_cell.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._label(model_cell, "Model provider · model")
        model = ttk.Combobox(model_cell, textvariable=model_display_var, state="readonly", style="VideoFlow.TCombobox", width=28)
        model.pack(fill="x", ipady=2, pady=(2, 0))

        theme_cell = tk.Frame(selector_row, bg=colors["background"])
        theme_cell.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._label(theme_cell, "Visual theme")
        theme = ttk.Combobox(theme_cell, textvariable=theme_display_var, state="readonly", style="VideoFlow.TCombobox", width=18)
        theme.pack(fill="x", ipady=2, pady=(2, 0))

        tk.Label(shell, textvariable=status_var, bg=colors["background"], fg=colors["muted"], font=("Segoe UI", 8), anchor="w").pack(fill="x")

        self._controls = {
            "visual_direction": visual_direction,
            "mode": mode_var, "title": title_var, "source": source,
            "file_label": file_label, "model": model_ref_var, "model_display": model_display_var,
            "model_detail": model_detail_var, "model_box": model, "theme": theme_ref_var,
            "theme_display": theme_display_var, "theme_detail": theme_detail_var, "theme_box": theme,
            "status": status_var, "generate": generate,
            "scroll_canvas": scroll_canvas, "scrollbar": scrollbar,
        }
        model.bind("<<ComboboxSelected>>", self._on_model_selected)
        theme.bind("<<ComboboxSelected>>", self._on_theme_selected)

    @staticmethod
    def _configure_styles(master: tk.Misc) -> None:
        colors = COMPOSER_COLORS
        style = ttk.Style(master)
        style.configure("VideoFlow.TCombobox", foreground=colors["text"], fieldbackground=colors["surface"], background=colors["surface"], arrowcolor=colors["orange_dark"], padding=(8, 4))
        style.map("VideoFlow.TCombobox", fieldbackground=[("readonly", colors["surface"])], foreground=[("readonly", colors["text"])], selectbackground=[("readonly", colors["surface_soft"])], selectforeground=[("readonly", colors["text"])])

    @staticmethod
    def _label(parent: tk.Misc, text: str) -> None:
        tk.Label(parent, text=text, bg=COMPOSER_COLORS["background"], fg=COMPOSER_COLORS["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")

    def _refresh_models(self) -> None:
        catalog: dict[str, Any] = {}
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:8991/api/video-flow/catalog", timeout=3) as response:
                loaded = json.loads(response.read().decode("utf-8"))
            if isinstance(loaded, dict):
                catalog = loaded
        except Exception:
            catalog = {}
        self._apply_catalog(catalog if isinstance(catalog, dict) else {})

    def _apply_catalog(self, catalog: dict[str, Any]) -> None:

        model_options = self.catalog_model_options(catalog)
        self._model_options = {option["label"]: option for option in model_options}
        self._controls["model_box"]["values"] = tuple(self._model_options)
        if not model_options:
            self._controls["model"].set("")
            self._controls["model_display"].set("Connect an AI model")
            self._controls["model_detail"].set("Original Scene Programs require a connected model.")
            self._controls["generate"].configure(state="disabled")
        else:
            self._controls["generate"].configure(state="normal")
            requested_model = str(
                catalog.get("active_model") or self._controls["model"].get() or ""
            )
            model = next(
                (option for option in model_options if option["ref"] == requested_model),
                None,
            )
            if model is None:
                model = model_options[0]
            self._set_model_option(model)
        theme_options = self.catalog_theme_options(catalog)
        self._theme_options = {option["label"]: option for option in theme_options}
        self._controls["theme_box"]["values"] = tuple(self._theme_options)
        requested_theme = str(self._controls["theme"].get() or "auto").lower()
        theme = next((option for option in theme_options if option["ref"] == requested_theme), theme_options[0])
        self._set_theme_option(theme)

    def _set_model_option(self, option: dict[str, str]) -> None:
        self._controls["model"].set(option["ref"])
        self._controls["model_display"].set(option["label"])
        self._controls["model_detail"].set(option["detail"])

    def _set_theme_option(self, option: dict[str, str]) -> None:
        self._controls["theme"].set(option["ref"])
        self._controls["theme_display"].set(option["label"])
        self._controls["theme_detail"].set(option["detail"])

    def _on_model_selected(self, _event: object | None = None) -> None:
        option = self._model_options.get(self._controls["model_display"].get())
        if option:
            self._set_model_option(option)

    def _on_theme_selected(self, _event: object | None = None) -> None:
        option = self._theme_options.get(self._controls["theme_display"].get())
        if option:
            self._set_theme_option(option)

    def _choose_file(self) -> None:
        if not self.win:
            return
        patterns = " ".join(f"*{extension}" for extension in sorted(DOCUMENT_EXTENSIONS))
        path = filedialog.askopenfilename(parent=self.win, title="Choose a document for Video Flow", filetypes=(("Supported documents", patterns), ("All files", "*.*")))
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            if len(raw) > MAX_DOCUMENT_BYTES:
                raise ValueError("Document is larger than 8 MB.")
            text = extract_document_text(Path(path).name, base64.b64encode(raw).decode("ascii"))
            source = self._controls["source"]
            source.delete("1.0", "end")
            source.insert("1.0", text)
            self._source_name = Path(path).name
            self._controls["file_label"].set(self._source_name)
            if not self._controls["title"].get().strip():
                self._controls["title"].set(Path(path).stem)
            self._controls["status"].set(f"{len(text):,} characters ready.")
        except Exception as exc:
            messagebox.showerror("Video Flow", str(exc), parent=self.win)

    def _generate(self) -> None:
        source = self._controls["source"].get("1.0", "end-1c").strip()
        if not source:
            messagebox.showwarning("Video Flow", "Paste text or choose a document first.", parent=self.win)
            return
        if not self.on_generate:
            messagebox.showerror("Video Flow", "The Video Flow runtime is not connected.", parent=self.win)
            return
        payload = {
            "source_text": source,
            "source_name": self._source_name,
            "title": self._controls["title"].get().strip(),
            "mode": self._controls["mode"].get(),
            "model_ref": self._controls["model"].get(),
            "theme": self._controls["theme"].get() or "auto",
            "visual_direction": self._controls["visual_direction"].get("1.0", "end-1c").strip()[:1000],
        }
        if not payload["model_ref"]:
            messagebox.showwarning("Video Flow", "Connect and select an AI model first.", parent=self.win)
            return

        local_prefixes = ("local/", "ollama/", "lmstudio/", "llamacpp/")
        if not payload["model_ref"].startswith(local_prefixes):
            allowed = messagebox.askyesno(
                "Allow external AI planning?",
                "The selected source will be sent to the chosen provider for scene planning. Narration and rendering remain on this PC.",
                parent=self.win,
            )
            if not allowed:
                return
            payload["allow_external_ai"] = True
        else:
            payload["allow_external_ai"] = False
        self._controls["generate"].configure(state="disabled")
        self._controls["status"].set("Starting Video Flow…")

        def _queue() -> None:
            try:
                result = self.on_generate(payload) or {}
                if not result.get("id"):
                    raise RuntimeError("Video Flow did not return a job.")
                self._run_on_ui(self._queued)
            except Exception as exc:
                self._run_on_ui(lambda: self._generation_error(str(exc)))

        threading.Thread(target=_queue, daemon=True, name="video-flow-screen-queue").start()

    def _queued(self) -> None:
        if self.win:
            self.win.withdraw()
        self._controls["generate"].configure(state="normal")
        self._controls["status"].set("Queued. Watch the circle beside the Voice Flow bar.")

    def _generation_error(self, message: str) -> None:
        self._controls["generate"].configure(state="normal")
        self._controls["status"].set(message[:120])
        if self.win:
            messagebox.showerror("Video Flow", message, parent=self.win)

    def open_player(self, video_id: str) -> None:
        if not video_id:
            return
        python_exe = sys.executable
        if os.name == "nt" and python_exe.lower().endswith("python.exe"):
            pythonw = python_exe[:-10] + "pythonw.exe"
            if os.path.exists(pythonw):
                python_exe = pythonw
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
        subprocess.Popen(
            [python_exe, "-m", "voice_flow.video_flow_player", video_id],
            creationflags=creation_flags,
            close_fds=True,
        )

    def _center(self) -> None:
        if not self.root or not self.win:
            return
        self.win.update_idletasks()
        width = self.win.winfo_width()
        height = self.win.winfo_height()
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.win.geometry(f"{width}x{height}+{x}+{y}")

    def _run_on_ui(self, callback: Callable[[], None]) -> None:
        if self.root:
            try:
                self.root.after(0, callback)
            except Exception:
                pass


video_flow_widget = VideoFlowScreenWidget()


def launch_video_flow_composer(
    selected_text: str = "",
    mode: str = "summary",
    *,
    root: tk.Tk | None = None,
    on_generate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> VideoFlowScreenWidget:
    """Open the shared composer from an overlay or another native surface."""
    if root is not None:
        video_flow_widget.attach_root(root)
    if on_generate is not None:
        video_flow_widget.on_generate = on_generate
    return video_flow_widget.launch(selected_text, mode)


# A readable alias for callers that think in terms of opening a surface.
open_video_flow_composer = launch_video_flow_composer


__all__ = [
    "VideoFlowScreenWidget",
    "launch_video_flow_composer",
    "open_video_flow_composer",
    "video_flow_widget",
]
