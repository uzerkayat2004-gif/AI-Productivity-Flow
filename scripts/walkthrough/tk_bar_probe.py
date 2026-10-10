"""Diagnose how the floating bar's Tk window renders on macOS.

Run with the app's *bundled* Python. Draws the same 48x10 rest pill the
overlay draws (dark #17171C on a #010101 window, alpha 0.95), plus a large
copy, using one variant of window setup per invocation, then screenshots it.

usage: tk_bar_probe.py VARIANT OUT_DIR
variants: plain | accessory | transparent | accessory_transparent
"""
from __future__ import annotations

import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path

variant, out_dir = sys.argv[1], Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
info: dict = {"variant": variant, "tk_version": tk.TkVersion, "tcl_patch": None, "errors": []}

root = tk.Tk()
info["tcl_patch"] = root.tk.call("info", "patchlevel")
info["windowingsystem"] = root.tk.call("tk", "windowingsystem")
if "accessory" in variant:
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        info["policy_set"] = bool(NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory))
        info["nsapp_class"] = type(NSApplication.sharedApplication()).__name__
    except Exception as exc:  # pragma: no cover - diagnostic only
        info["errors"].append(f"policy: {exc!r}")
root.withdraw()

wins = []
RECTS = ((48, 10, 488, 600), (240, 50, 392, 450), (48, 28, 100, 150), (144, 28, 100, 250),
         (248, 28, 100, 350), (100, 10, 600, 150), (48, 20, 600, 250), (60, 40, 600, 350))
if "threaded" in variant:
    RECTS = ((48, 10, 488, 600), (240, 50, 392, 450))
if variant == "reverse":
    RECTS = tuple(reversed(RECTS))
for (w, h, x, y) in RECTS:
    win = tk.Toplevel(root)
    win.withdraw()
    win.overrideredirect(True)
    try:
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.95)
    except Exception as exc:
        info["errors"].append(f"alpha/topmost: {exc!r}")
    bg = "#010101"
    if "transparent" in variant:
        # Aqua Tk's own transparency: -transparent + systemTransparent background.
        try:
            win.attributes("-transparent", True)
            bg = "systemTransparent"
        except Exception as exc:
            info["errors"].append(f"-transparent: {exc!r}")
    win.config(bg=bg)
    try:
        win.attributes("-transparentcolor", "#010101")
        info["transparentcolor_supported"] = True
    except Exception as exc:
        info["transparentcolor_supported"] = False
        info["transparentcolor_error"] = str(exc)
    c = tk.Canvas(win, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
    c.pack(fill="both", expand=True)
    r = min(h / 2, 14)
    def pts(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    c.create_polygon(pts(1, 1, w - 1, h - 1, r), fill="#2C2C36", smooth=True)
    c.create_polygon(pts(2, 2, w - 2, h - 2, r - 1), fill="#17171C", smooth=True)
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.deiconify()
    win.lift()
    wins.append((win, w, h, x, y))


def shoot():
    info["rects"] = [[w, h, x, y] for (_, w, h, x, y) in wins]
    info["screen_points"] = [root.winfo_screenwidth(), root.winfo_screenheight()]
    png = out_dir / f"tkprobe-{variant}.png"
    subprocess.run(["screencapture", "-x", str(png)], check=False)
    try:
        from PIL import Image
        im = Image.open(png).convert("RGB")
        sx = im.size[0] / root.winfo_screenwidth()
        samples = {}
        for (_, w, h, x, y) in wins:
            samples[f"{w}x{h}"] = {
                "center": im.getpixel((int((x + w / 2) * sx), int((y + h / 2) * sx))),
                "corner": im.getpixel((int((x + 1) * sx), int((y + 1) * sx))),
            }
        info["pixels"] = samples
    except Exception as exc:
        info["errors"].append(f"pixels: {exc!r}")
    (out_dir / f"tkprobe-{variant}.json").write_text(json.dumps(info, indent=2, default=str))
    root.destroy()


if "threaded" in variant:
    import threading
    info["after_from_thread_ran"] = False
    def grow():
        win, w, h, x, y = wins[0]
        info["after_from_thread_ran"] = True
        c = win.winfo_children()[0]
        c.delete("all")
        c.config(width=248, height=28)
        win.geometry("248x28+388+600")
        c.create_rectangle(0, 0, 248, 28, fill="#17171C", outline="")
        wins[0] = (win, 248, 28, 388, 600)
    threading.Timer(1.0, lambda: root.after(0, grow)).start()
    # Candidate fix: worker threads only enqueue; the Tk thread polls the queue.
    import queue
    q: "queue.Queue" = queue.Queue()
    info["queue_poll_ran"] = False
    def recolor():
        info["queue_poll_ran"] = True
        win, w, h, x, y = wins[1]
        c = win.winfo_children()[0]
        c.delete("all")
        c.create_rectangle(0, 0, w, h, fill="#FF6A00", outline="")
    def pump():
        try:
            while True:
                q.get_nowait()()
        except queue.Empty:
            pass
        root.after(30, pump)
    root.after(30, pump)
    threading.Timer(1.0, lambda: q.put(recolor)).start()

root.after(3500, shoot)
root.mainloop()
