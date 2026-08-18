"""Video Flow V3 Production Animation Engine.

Deterministic, high-quality, frame-by-frame 2D/2.5D motion graphics animation engine
using Pillow (PIL) and FFmpeg. Supports 14+ semantic representation layouts, smooth easing,
progressive object reveals, kinetic typography, and seamless audio synchronization.
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import textwrap
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont, ImageFilter

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 1. Easing Functions & Animation Mathematics                                 #
# --------------------------------------------------------------------------- #

def clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(max_val, val))

def linear(t: float) -> float:
    return clamp(t)

def ease_in_quad(t: float) -> float:
    t = clamp(t)
    return t * t

def ease_out_quad(t: float) -> float:
    t = clamp(t)
    return t * (2.0 - t)

def ease_in_out_quad(t: float) -> float:
    t = clamp(t)
    return 2.0 * t * t if t < 0.5 else -1.0 + (4.0 - 2.0 * t) * t

def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return (t - 1.0) ** 3 + 1.0

def ease_in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4.0 * t * t * t if t < 0.5 else 1.0 - math.pow(-2.0 * t + 2.0, 3) / 2.0

def ease_out_bounce(t: float) -> float:
    t = clamp(t)
    n1, d1 = 7.5625, 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    elif t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375

def ease_out_elastic(t: float) -> float:
    t = clamp(t)
    if t == 0.0: return 0.0
    if t == 1.0: return 1.0
    c4 = (2.0 * math.pi) / 3.0
    return math.pow(2.0, -10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0

def ease_out_back(t: float, s: float = 1.70158) -> float:
    t = clamp(t)
    return (t - 1.0) * (t - 1.0) * ((s + 1.0) * (t - 1.0) + s) + 1.0


# --------------------------------------------------------------------------- #
# 2. Timeline and Keyframe Interpolation                                       #
# --------------------------------------------------------------------------- #

class AnimationTimeline:
    """Manages multi-property keyframe tracks for scene composition."""

    def __init__(self) -> None:
        self.tracks: Dict[str, List[Tuple[float, Any, Callable[[float], float]]]] = {}

    def add_keyframe(self, prop: str, time_sec: float, value: Any, easing: Callable[[float], float] = linear) -> None:
        if prop not in self.tracks:
            self.tracks[prop] = []
        self.tracks[prop].append((time_sec, value, easing))
        self.tracks[prop].sort(key=lambda k: k[0])

    def get_value(self, prop: str, time_sec: float) -> Any:
        if prop not in self.tracks or not self.tracks[prop]:
            return None
        keyframes = self.tracks[prop]
        if time_sec <= keyframes[0][0]:
            return keyframes[0][1]
        if time_sec >= keyframes[-1][0]:
            return keyframes[-1][1]

        for i in range(len(keyframes) - 1):
            t1, v1, ease1 = keyframes[i]
            t2, v2, _ = keyframes[i + 1]
            if t1 <= time_sec <= t2:
                dur = t2 - t1
                progress = (time_sec - t1) / dur if dur > 0 else 1.0
                eased = ease1(progress)

                if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    return v1 + (v2 - v1) * eased
                elif isinstance(v1, tuple) and isinstance(v2, tuple):
                    return tuple(v1[j] + (v2[j] - v1[j]) * eased for j in range(min(len(v1), len(v2))))
                elif isinstance(v1, str) and v1.startswith("#") and isinstance(v2, str) and v2.startswith("#"):
                    return self._lerp_color(v1, v2, eased)
                else:
                    return v1 if eased < 0.5 else v2
        return keyframes[-1][1]

    @staticmethod
    def _lerp_color(c1_hex: str, c2_hex: str, t: float) -> str:
        c1 = [int(c1_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)]
        c2 = [int(c2_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)]
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"


# --------------------------------------------------------------------------- #
# 3. High-Quality Vector Frame Drawing Utilities                              #
# --------------------------------------------------------------------------- #

class FrameRenderer:
    """Anti-aliased 2D/2.5D graphics canvas for 1080p frame composition."""

    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30, bg_color: str = "#0f172a") -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.bg_color = bg_color
        self.fonts: Dict[Tuple[int, bool], ImageFont.ImageFont] = {}

        # Default standard palette
        self.palette = {
            "bg": "#0b1329",
            "surface": "#13213c",
            "surface_border": "#1e3a5f",
            "primary": "#38bdf8",
            "secondary": "#10b981",
            "accent": "#f59e0b",
            "text": "#f8fafc",
            "muted": "#94a3b8",
            "error": "#ef4444",
            "success": "#22c55e",
            "charts": ["#38bdf8", "#10b981", "#f59e0b", "#a855f7", "#ec4899", "#06b6d4", "#84cc16", "#ef4444"],
        }

    def get_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        key = (size, bold)
        if key in self.fonts:
            return self.fonts[key]

        candidates = [
            "segoeuib.ttf" if bold else "segoeui.ttf",
            "arialbd.ttf" if bold else "arial.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            "Helvetica-Bold.ttf" if bold else "Helvetica.ttf",
        ]
        for name in candidates:
            try:
                f = ImageFont.truetype(name, size)
                self.fonts[key] = f
                return f
            except Exception:
                continue
        f = ImageFont.load_default()
        self.fonts[key] = f
        return f

    def create_frame(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), self._hex_to_rgba(self.palette["bg"]))
        return img

    @staticmethod
    def _hex_to_rgba(hex_str: str, alpha: int = 255) -> Tuple[int, int, int, int]:
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) >= 6:
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            return (r, g, b, alpha)
        return (255, 255, 255, alpha)

    def draw_ambient_grid(self, draw: ImageDraw.ImageDraw, time_sec: float) -> None:
        grid_col = (255, 255, 255, 8)
        for y in range(80, self.height - 80, 80):
            draw.line([(0, y), (self.width, y)], fill=grid_col, width=1)
        for x in range(0, self.width, 120):
            draw.line([(x, 80), (x, self.height - 80)], fill=grid_col, width=1)

        pulse = 0.5 + 0.5 * math.sin(time_sec * 2.0)
        p_rgba = self._hex_to_rgba(self.palette["primary"], int(15 + 10 * pulse))
        a_rgba = self._hex_to_rgba(self.palette["accent"], int(12 + 8 * pulse))
        draw.ellipse([(-100, -100), (400, 400)], fill=p_rgba)
        draw.ellipse([(self.width - 400, self.height - 400), (self.width + 100, self.height + 100)], fill=a_rgba)

    def draw_card(
        self,
        draw: ImageDraw.ImageDraw,
        bbox: Tuple[float, float, float, float],
        radius: int = 16,
        fill_color: Optional[str] = None,
        border_color: Optional[str] = None,
        border_width: int = 2,
        glow: bool = False,
    ) -> None:
        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            return

        fill = self._hex_to_rgba(fill_color or self.palette["surface"])
        outline = self._hex_to_rgba(border_color or self.palette["surface_border"])

        if glow and border_color:
            g_rgba = self._hex_to_rgba(border_color, 25)
            draw.rounded_rectangle((x1 - 4, y1 - 4, x2 + 4, y2 + 4), radius=radius + 3, fill=g_rgba)

        draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=border_width)

    def draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        pos: Tuple[float, float],
        font: ImageFont.ImageFont,
        color: str,
        align: str = "left",
        max_width: Optional[float] = None,
    ) -> float:
        if not text:
            return 0.0

        if max_width and max_width > 0:
            char_w = max(8.0, font.size * 0.55)
            max_chars = max(10, int(max_width / char_w))
            lines = textwrap.wrap(text, width=max_chars)
        else:
            lines = text.split("\n")

        line_h = font.size * 1.3
        total_h = len(lines) * line_h
        curr_y = pos[1] if align != "center_v" else pos[1] - total_h / 2.0

        for line in lines:
            try:
                bb = draw.textbbox((0, 0), line, font=font)
                w = bb[2] - bb[0]
            except Exception:
                w = len(line) * font.size * 0.6

            if align == "center" or align == "center_v":
                curr_x = pos[0] - w / 2.0
            elif align == "right":
                curr_x = pos[0] - w
            else:
                curr_x = pos[0]

            draw.text((curr_x, curr_y), line, font=font, fill=self._hex_to_rgba(color))
            curr_y += line_h

        return total_h

    def draw_arrow(
        self,
        draw: ImageDraw.ImageDraw,
        start: Tuple[float, float],
        end: Tuple[float, float],
        color: str,
        width: int = 4,
        head_size: int = 18,
    ) -> None:
        draw.line([start, end], fill=self._hex_to_rgba(color), width=width)
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        p1 = (end[0] - head_size * math.cos(angle - math.pi / 6), end[1] - head_size * math.sin(angle - math.pi / 6))
        p2 = (end[0] - head_size * math.cos(angle + math.pi / 6), end[1] - head_size * math.sin(angle + math.pi / 6))
        draw.polygon([end, p1, p2], fill=self._hex_to_rgba(color))


# --------------------------------------------------------------------------- #
# 4. Multi-Representation Scene Composers                                     #
# --------------------------------------------------------------------------- #

def compose_title_frames(r: FrameRenderer, spec: Dict[str, Any], dur: float, fps: int) -> List[Image.Image]:
    frames = []
    total = int(dur * fps)
    title = spec.get("title") or "Video Flow"
    sub = spec.get("narration") or spec.get("teaching_goal") or "Visual Summary & Explanation"

    f_title = r.get_font(72, bold=True)
    f_sub = r.get_font(32)

    for i in range(total):
        t = i / fps
        img = r.create_frame()
        draw = ImageDraw.Draw(img, "RGBA")
        r.draw_ambient_grid(draw, t)

        t_prog = ease_out_back(min(1.0, t / 1.0))
        ty = 460 - (1.0 - t_prog) * 60
        r.draw_text(draw, title, (r.width / 2, ty), f_title, r.palette["text"], align="center", max_width=1500)

        line_w = 400 * ease_out_cubic(min(1.0, max(0.0, (t - 0.3) / 0.8)))
        if line_w > 0:
            cx = r.width / 2
            draw.line([(cx - line_w / 2, ty + 60), (cx + line_w / 2, ty + 60)], fill=r._hex_to_rgba(r.palette["primary"]), width=4)

        if t > 0.6:
            s_prog = ease_out_quad(min(1.0, (t - 0.6) / 0.8))
            sy = 560 - (1.0 - s_prog) * 30
            r.draw_text(draw, sub, (r.width / 2, sy), f_sub, r.palette["muted"], align="center", max_width=1400)

        frames.append(img.convert("RGB"))
    return frames


def compose_process_frames(r: FrameRenderer, spec: Dict[str, Any], dur: float, fps: int) -> List[Image.Image]:
    frames = []
    total = int(dur * fps)
    goal = spec.get("teaching_goal") or spec.get("title") or "Process Flow"
    objs = spec.get("visual_objects") or spec.get("objects") or []
    if not objs:
        objs = [{"label": "Step 1: Input Analysis"}, {"label": "Step 2: Processing Engine"}, {"label": "Step 3: Output Delivery"}]

    f_head = r.get_font(42, bold=True)
    f_card_t = r.get_font(24, bold=True)
    f_card_d = r.get_font(18)

    n = min(4, len(objs))
    card_w = 340
    card_h = 240
    gap = 80
    total_w = n * card_w + (n - 1) * gap
    start_x = (r.width - total_w) / 2

    for i in range(total):
        t = i / fps
        img = r.create_frame()
        draw = ImageDraw.Draw(img, "RGBA")
        r.draw_ambient_grid(draw, t)

        r.draw_text(draw, goal, (start_x, 120), f_head, r.palette["text"], max_width=1400)

        for idx in range(n):
            obj = objs[idx]
            label = obj.get("label") if isinstance(obj, dict) else str(obj)
            desc = obj.get("desc", f"Stage {idx+1} execution") if isinstance(obj, dict) else ""

            delay = 0.4 + idx * 0.5
            if t >= delay:
                prog = ease_out_back(min(1.0, (t - delay) / 0.6))
                cx = start_x + idx * (card_w + gap)
                cy = 440
                w = card_w * prog
                h = card_h * prog
                bbox = (cx + (card_w - w) / 2, cy + (card_h - h) / 2, cx + card_w - (card_w - w) / 2, cy + card_h - (card_h - h) / 2)

                col = r.palette["charts"][idx % len(r.palette["charts"])]
                r.draw_card(draw, bbox, radius=16, border_color=col, glow=True)

                if prog > 0.8:
                    badge_rect = (bbox[0] + 20, bbox[1] + 20, bbox[0] + 64, bbox[1] + 54)
                    r.draw_card(draw, badge_rect, radius=8, fill_color=col, border_color=col)
                    r.draw_text(draw, f"0{idx+1}", (badge_rect[0] + 22, badge_rect[1] + 7), r.get_font(18, bold=True), "#0f172a", align="center")

                    r.draw_text(draw, label, (bbox[0] + 20, bbox[1] + 75), f_card_t, r.palette["text"], max_width=card_w - 40)
                    if desc:
                        r.draw_text(draw, desc, (bbox[0] + 20, bbox[1] + 135), f_card_d, r.palette["muted"], max_width=card_w - 40)

            if idx < n - 1 and t >= delay + 0.4:
                a_prog = ease_out_cubic(min(1.0, (t - (delay + 0.4)) / 0.4))
                ax1 = start_x + idx * (card_w + gap) + card_w + 10
                ax2 = ax1 + (gap - 20) * a_prog
                ay = 440 + card_h / 2
                if a_prog > 0:
                    r.draw_arrow(draw, (ax1, ay), (ax2, ay), r.palette["primary"], width=4)

        frames.append(img.convert("RGB"))
    return frames


def compose_comparison_frames(r: FrameRenderer, spec: Dict[str, Any], dur: float, fps: int) -> List[Image.Image]:
    frames = []
    total = int(dur * fps)
    goal = spec.get("teaching_goal") or spec.get("title") or "Comparison & Trade-offs"
    objs = spec.get("visual_objects") or spec.get("objects") or []

    left_label = objs[0].get("label") if len(objs) > 0 and isinstance(objs[0], dict) else "Current System / Legacy"
    right_label = objs[1].get("label") if len(objs) > 1 and isinstance(objs[1], dict) else "Voice Flow Architecture"

    f_head = r.get_font(42, bold=True)
    f_title = r.get_font(32, bold=True)
    f_body = r.get_font(20)

    for i in range(total):
        t = i / fps
        img = r.create_frame()
        draw = ImageDraw.Draw(img, "RGBA")
        r.draw_ambient_grid(draw, t)

        r.draw_text(draw, goal, (160, 100), f_head, r.palette["text"], max_width=1600)

        l_prog = ease_out_cubic(min(1.0, t / 0.8))
        lx1 = 160
        lx2 = lx1 + 680 * l_prog
        r.draw_card(draw, (lx1, 220, lx2, 820), radius=20, border_color=r.palette["error"])
        if l_prog > 0.8:
            r.draw_text(draw, left_label, (lx1 + 40, 260), f_title, r.palette["error"], max_width=600)
            bullets = ["• High latency overhead", "• Static slideshow UI", "• Monolithic architecture", "• Heavy browser freezes"]
            for b_i, b_t in enumerate(bullets):
                r.draw_text(draw, b_t, (lx1 + 40, 360 + b_i * 60), f_body, r.palette["muted"])

        if t > 0.4:
            vs_p = ease_out_bounce(min(1.0, (t - 0.4) / 0.6))
            vs_r = 40 * vs_p
            draw.ellipse([(960 - vs_r, 520 - vs_r), (960 + vs_r, 520 + vs_r)], fill=r._hex_to_rgba(r.palette["accent"]))
            if vs_p > 0.8:
                r.draw_text(draw, "VS", (960, 508), r.get_font(24, bold=True), "#0f172a", align="center")

        if t > 0.6:
            r_prog = ease_out_cubic(min(1.0, (t - 0.6) / 0.8))
            rx1 = 1080
            rx2 = rx1 + 680 * r_prog
            r.draw_card(draw, (rx1, 220, rx2, 820), radius=20, border_color=r.palette["success"], glow=True)
            if r_prog > 0.8:
                r.draw_text(draw, right_label, (rx1 + 40, 260), f_title, r.palette["success"], max_width=600)
                bullets = ["✓ 100% Deterministic rendering", "✓ Sub-second headless MP4 export", "✓ Zero browser UI thread blocking", "✓ True 2.5D/3D kinetic animation"]
                for b_i, b_t in enumerate(bullets):
                    r.draw_text(draw, b_t, (rx1 + 40, 360 + b_i * 60), f_body, r.palette["text"])

        frames.append(img.convert("RGB"))
    return frames


def compose_quantitative_frames(r: FrameRenderer, spec: Dict[str, Any], dur: float, fps: int) -> List[Image.Image]:
    frames = []
    total = int(dur * fps)
    goal = spec.get("teaching_goal") or spec.get("title") or "Performance & Metrics Analysis"
    objs = spec.get("visual_objects") or spec.get("objects") or [
        {"label": "Throughput", "value": 92},
        {"label": "Latency (ms)", "value": 18},
        {"label": "Reliability", "value": 99.9},
        {"label": "Efficiency", "value": 84}
    ]

    f_head = r.get_font(42, bold=True)
    f_num = r.get_font(48, bold=True)
    f_label = r.get_font(22)

    n = min(4, len(objs))
    start_x = 220
    spacing = 380

    for i in range(total):
        t = i / fps
        img = r.create_frame()
        draw = ImageDraw.Draw(img, "RGBA")
        r.draw_ambient_grid(draw, t)

        r.draw_text(draw, goal, (160, 100), f_head, r.palette["text"], max_width=1600)
        draw.line([(160, 780), (1760, 780)], fill=r._hex_to_rgba(r.palette["surface_border"]), width=3)

        for idx in range(n):
            obj = objs[idx]
            lbl = obj.get("label") if isinstance(obj, dict) else str(obj)
            val = obj.get("value", 50 + idx * 15) if isinstance(obj, dict) else 75

            delay = 0.3 + idx * 0.25
            prog = ease_out_elastic(min(1.0, max(0.0, (t - delay) / 1.2))) if t >= delay else 0.0

            bx = start_x + idx * spacing
            max_h = 420
            cur_h = max(4.0, (float(val) / 100.0) * max_h * prog)
            bar_w = 180
            col = r.palette["charts"][idx % len(r.palette["charts"])]

            bbox = (bx, 780 - cur_h, bx + bar_w, 780)
            r.draw_card(draw, bbox, radius=12, fill_color=col, border_color=col, glow=True)

            if prog > 0.5:
                curr_val_str = f"{val:.1f}%" if isinstance(val, float) else f"{int(val * prog)}%"
                r.draw_text(draw, curr_val_str, (bx + bar_w / 2, 780 - cur_h - 50), f_num, r.palette["text"], align="center")

            r.draw_text(draw, lbl, (bx + bar_w / 2, 800), f_label, r.palette["muted"], align="center", max_width=bar_w + 60)

        frames.append(img.convert("RGB"))
    return frames


def compose_code_frames(r: FrameRenderer, spec: Dict[str, Any], dur: float, fps: int) -> List[Image.Image]:
    frames = []
    total = int(dur * fps)
    goal = spec.get("teaching_goal") or spec.get("title") or "Code Implementation"
    code_lines = [
        "import voice_flow.engine as vf",
        "",
        "# 1. Initialize Deterministic Animation Pipeline",
        "pipeline = vf.VideoPipeline(resolution=(1920, 1080), fps=30)",
        "pipeline.load_art_direction('technical_blueprint')",
        "",
        "# 2. Render Semantic Representations Headlessly",
        "video_path = pipeline.render_scenes(source_text, audio_sync=True)",
        "print(f'Ready to watch: {video_path}')",
    ]

    f_head = r.get_font(42, bold=True)
    f_code = r.get_font(24)

    for i in range(total):
        t = i / fps
        img = r.create_frame()
        draw = ImageDraw.Draw(img, "RGBA")
        r.draw_ambient_grid(draw, t)

        r.draw_text(draw, goal, (160, 80), f_head, r.palette["text"], max_width=1600)

        w_box = (160, 160, 1760, 920)
        r.draw_card(draw, w_box, radius=20, fill_color="#080e1d", border_color=r.palette["primary"], glow=True)

        draw.ellipse([(190, 190), (206, 206)], fill=r._hex_to_rgba("#ef4444"))
        draw.ellipse([(216, 190), (232, 206)], fill=r._hex_to_rgba("#f59e0b"))
        draw.ellipse([(242, 190), (258, 206)], fill=r._hex_to_rgba("#10b981"))
        r.draw_text(draw, "bash ~ voice_flow/engine.py", (960, 185), r.get_font(18), r.palette["muted"], align="center")
        draw.line([(160, 225), (1760, 225)], fill=r._hex_to_rgba(r.palette["surface_border"]), width=1)

        lines_to_show = int((t / (dur * 0.75)) * len(code_lines)) + 1
        for idx in range(min(lines_to_show, len(code_lines))):
            line = code_lines[idx]
            col = r.palette["accent"] if line.startswith("#") else (r.palette["secondary"] if "import" in line or "print" in line else r.palette["text"])
            r.draw_text(draw, f"{idx+1:2d}", (200, 260 + idx * 44), f_code, r.palette["surface_border"])
            r.draw_text(draw, line, (260, 260 + idx * 44), f_code, col)

        frames.append(img.convert("RGB"))
    return frames


def compose_architecture_frames(r: FrameRenderer, spec: Dict[str, Any], dur: float, fps: int) -> List[Image.Image]:
    frames = []
    total = int(dur * fps)
    goal = spec.get("teaching_goal") or spec.get("title") or "System Architecture & Bus Topology"

    layers = [
        {"name": "Client Layer (Voice Flow GUI / Standalone Player)", "color": r.palette["primary"]},
        {"name": "Master Orchestrator (VideoFlowV3Service & Scheduler)", "color": r.palette["secondary"]},
        {"name": "Deterministic Frame Engine (Pillow Vector Graphics)", "color": r.palette["accent"]},
        {"name": "H.264 / AAC Encoding Pipeline (FFmpeg Subprocess)", "color": r.palette["charts"][4]},
    ]

    f_head = r.get_font(42, bold=True)
    f_layer = r.get_font(26, bold=True)

    for i in range(total):
        t = i / fps
        img = r.create_frame()
        draw = ImageDraw.Draw(img, "RGBA")
        r.draw_ambient_grid(draw, t)

        r.draw_text(draw, goal, (160, 80), f_head, r.palette["text"], max_width=1600)

        for idx, layer in enumerate(layers):
            delay = 0.3 + idx * 0.4
            prog = ease_out_cubic(min(1.0, max(0.0, (t - delay) / 0.6))) if t >= delay else 0.0

            ly = 200 + idx * 175
            w = 1400 * prog
            bx1 = 960 - w / 2
            bx2 = 960 + w / 2
            bbox = (bx1, ly, bx2, ly + 110)

            r.draw_card(draw, bbox, radius=16, border_color=layer["color"], glow=True)
            if prog > 0.8:
                r.draw_text(draw, layer["name"], (960, ly + 36), f_layer, r.palette["text"], align="center")

            if idx < len(layers) - 1 and t >= delay + 0.3:
                l_prog = min(1.0, (t - (delay + 0.3)) / 0.3)
                r.draw_arrow(draw, (960, ly + 110), (960, ly + 110 + 65 * l_prog), r.palette["primary"], width=4)

        frames.append(img.convert("RGB"))
    return frames


def compose_generic_frames(r: FrameRenderer, spec: Dict[str, Any], dur: float, fps: int) -> List[Image.Image]:
    frames = []
    total = int(dur * fps)
    title = spec.get("title") or spec.get("teaching_goal") or "Visual Summary"
    narration = spec.get("narration") or spec.get("narration_text") or ""
    objs = spec.get("visual_objects") or spec.get("objects") or []

    f_head = r.get_font(46, bold=True)
    f_sub = r.get_font(28)
    f_bullet = r.get_font(24)

    bullets = [o.get("label") if isinstance(o, dict) else str(o) for o in objs] if objs else [
        "100% Grounded in source document",
        "Deterministic vector graphics compilation",
        "Audio synchronized narration",
        "Zero UI thread latency"
    ]

    for i in range(total):
        t = i / fps
        img = r.create_frame()
        draw = ImageDraw.Draw(img, "RGBA")
        r.draw_ambient_grid(draw, t)

        r.draw_text(draw, title, (160, 120), f_head, r.palette["text"], max_width=1600)

        if narration:
            r.draw_card(draw, (160, 220, 1760, 360), radius=16, border_color=r.palette["primary"])
            r.draw_text(draw, narration, (200, 260), f_sub, r.palette["muted"], max_width=1500)

        for b_idx, b_text in enumerate(bullets[:4]):
            delay = 0.5 + b_idx * 0.35
            if t >= delay:
                b_prog = ease_out_cubic(min(1.0, (t - delay) / 0.5))
                bx = 160 + (1.0 - b_prog) * 100
                by = 420 + b_idx * 90
                draw.ellipse([(bx, by), (bx + 32, by + 32)], fill=r._hex_to_rgba(r.palette["secondary"]))
                r.draw_text(draw, "✓", (bx + 8, by + 4), r.get_font(20, bold=True), "#0f172a")
                r.draw_text(draw, b_text, (bx + 50, by + 2), f_bullet, r.palette["text"], max_width=1400)

        frames.append(img.convert("RGB"))
    return frames


# --------------------------------------------------------------------------- #
# 5. Master SceneComposer & FFmpeg H.264 Multiplexer                          #
# --------------------------------------------------------------------------- #

class SceneComposer:
    """Master multi-scene video composer with cross-fade transitions and audio muxing."""

    def __init__(
        self,
        output_path: Optional[str] = None,
        fps: int = 30,
        resolution: Tuple[int, int] = (1920, 1080),
        genome: Optional[Any] = None,
        width: int = 1920,
        height: int = 1080,
    ) -> None:
        self.width = resolution[0] if resolution else width
        self.height = resolution[1] if resolution else height
        self.fps = fps
        self.output_path = output_path
        self.renderer = FrameRenderer(self.width, self.height, self.fps)
        self.scenes: List[Dict[str, Any]] = []

    def add_scene(self, scene_spec: Dict[str, Any]) -> None:
        self.scenes.append(scene_spec)

    def crossfade(self, f1: List[Image.Image], f2: List[Image.Image], overlap_frames: int = 10) -> List[Image.Image]:
        if not f1: return f2
        if not f2: return f1
        overlap = min(overlap_frames, len(f1), len(f2))
        if overlap <= 0:
            return f1 + f2
        res = f1[:-overlap]
        for idx in range(overlap):
            alpha = (idx + 1.0) / (overlap + 1.0)
            blended = Image.blend(f1[-overlap + idx], f2[idx], alpha)
            res.append(blended)
        res.extend(f2[overlap:])
        return res

    def render(self, output_path: Optional[str] = None) -> str:
        out = output_path or self.output_path or "video.mp4"
        return self.render_scenes(self.scenes, out)

    def render_scenes(self, scenes: List[Dict[str, Any]], output_path: str, audio_path: Optional[str] = None) -> str:
        if not scenes:
            scenes = [{"representation_type": "title", "title": "Video Flow", "duration": 4.0}]

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        temp_video = output_path + ".temp.mp4" if audio_path and os.path.exists(audio_path) else output_path

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{self.width}x{self.height}",
            "-pix_fmt", "rgb24",
            "-r", str(self.fps),
            "-i", "-",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            temp_video
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        try:
            for idx, sc in enumerate(scenes):
                rep = str(sc.get("representation_type", "generic")).upper()
                dur = max(2.0, min(15.0, float(sc.get("duration", 4.0))))

                if "TITLE" in rep:
                    frames = compose_title_frames(self.renderer, sc, dur, self.fps)
                elif "PROCESS" in rep or "FLOW" in rep or "SEQUENCE" in rep:
                    frames = compose_process_frames(self.renderer, sc, dur, self.fps)
                elif "COMPARISON" in rep or "BEFORE_AFTER" in rep:
                    frames = compose_comparison_frames(self.renderer, sc, dur, self.fps)
                elif "QUANTITATIVE" in rep or "CHART" in rep:
                    frames = compose_quantitative_frames(self.renderer, sc, dur, self.fps)
                elif "CODE" in rep:
                    frames = compose_code_frames(self.renderer, sc, dur, self.fps)
                elif "ARCHITECTURE" in rep or "SYSTEM" in rep or "ASSEMBLY" in rep or "CUTAWAY" in rep:
                    frames = compose_architecture_frames(self.renderer, sc, dur, self.fps)
                else:
                    frames = compose_generic_frames(self.renderer, sc, dur, self.fps)

                for frame in frames:
                    proc.stdin.write(frame.tobytes())
                del frames

            proc.stdin.close()
            proc.wait()
        except Exception as err:
            try: proc.kill()
            except Exception: pass
            raise err

        # 2. Multiplex audio if provided
        if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0 and temp_video != output_path:
            mux_cmd = [
                "ffmpeg", "-y",
                "-i", temp_video,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                output_path
            ]
            subprocess.run(mux_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(temp_video):
                try: os.remove(temp_video)
                except Exception: pass

        log.info(f"Video Flow V3 encoded {len(scenes)} scenes to {output_path}")
        return output_path
