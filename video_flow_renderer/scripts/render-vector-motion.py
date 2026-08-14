from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 720
INK = "#171717"
PAPER = "#fbfaf5"
MUTED = "#696761"
DEFAULT_ACCENTS = ["#ff8a1f", "#ffd65a", "#8bd7e6", "#89c95d", "#ef4b43"]
FONT_REGULAR = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")
CURRENT_ART_DIRECTION: dict[str, Any] = {}
# Kept for legacy manifest diagnostics and compatibility-test discovery.
LEGACY_RENDERER_ID = "procedural-vector-v1"
PUBLIC_DIR = Path(".")
ASSET_CACHE: dict[str, Image.Image] = {}
FONT_SYSTEMS = {
    "humanist": ("segoeui.ttf", "segoeuib.ttf"),
    "grotesk": ("arial.ttf", "arialbd.ttf"),
    "condensed": ("bahnschrift.ttf", "bahnschrift.ttf"),
    "mono": ("consola.ttf", "consolab.ttf"),
    "display": ("impact.ttf", "impact.ttf"),
    "serif": ("georgia.ttf", "georgiab.ttf"),
    "handwritten": ("segoepr.ttf", "segoeprb.ttf"),
    "editorial": ("trebuc.ttf", "trebucbd.ttf"),
    "rounded": ("comic.ttf", "comicbd.ttf"),
}


def configure_art_direction(art_direction: dict[str, Any], palette: dict[str, Any]) -> None:
    global CURRENT_ART_DIRECTION, FONT_REGULAR, FONT_BOLD, INK, PAPER, MUTED, DEFAULT_ACCENTS
    CURRENT_ART_DIRECTION = art_direction
    regular_name, bold_name = FONT_SYSTEMS.get(str(art_direction.get("fontSystem") or "humanist"), FONT_SYSTEMS["humanist"])
    regular = Path(r"C:\Windows\Fonts") / regular_name
    bold = Path(r"C:\Windows\Fonts") / bold_name
    FONT_REGULAR = regular if regular.exists() else Path(r"C:\Windows\Fonts\segoeui.ttf")
    FONT_BOLD = bold if bold.exists() else Path(r"C:\Windows\Fonts\segoeuib.ttf")
    INK = str(palette.get("text") or INK)
    PAPER = str(palette.get("background") or PAPER)
    MUTED = str(palette.get("muted") or MUTED)
    DEFAULT_ACCENTS = list(palette.get("accents") or DEFAULT_ACCENTS)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), max(10, size))


def stable_seed(value: str) -> int:
    return zlib.crc32(value.encode("utf-8"))


def rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = color.lstrip("#")
    if len(value) < 6:
        value = "171717"
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (alpha,)


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1 - (1 - value) ** 4


def progress(frame: int, start: float, end: float) -> float:
    if end <= start:
        return 1.0 if frame >= end else 0.0
    return ease((frame - start) / (end - start))


def action_family(kind: str) -> str:
    if re.search(r"travel|route|flow|race|spread|transfer|reroute|branch", kind):
        return "travel"
    if re.search(r"orbit|circle|evaporate|gather|scatter", kind):
        return "orbit"
    if re.search(r"flip|stack|compile|assemble|combine|merge|mix", kind):
        return "construct"
    if re.search(r"block|intercept|shield|lock|contain|verify|stamp", kind):
        return "impact"
    if re.search(r"count|measure|score|rank|plot|scan", kind):
        return "measure"
    if re.search(r"grow|bloom|heal|recover|level-up|charge", kind):
        return "grow"
    if re.search(r"write|sketch|trace|underline|annotate|label|highlight", kind):
        return "draw"
    return "transform"


def movement(action: dict[str, Any], amount: float, seed: int) -> tuple[float, float, float, float]:
    family = action_family(str(action.get("kind") or ""))
    direction = str(action.get("direction") or "up")
    physics = str(CURRENT_ART_DIRECTION.get("motionPhysics") or "drawn")
    if physics == "snap":
        amount = min(1.0, amount * 1.65)
    elif physics == "slam":
        amount = min(1.0, amount * 1.35)
    dx = -1 if direction == "left" else 1 if direction == "right" else 0
    dy = -1 if direction == "up" else 1 if direction == "down" else 0
    wobble = math.sin(amount * math.pi * (2 + abs(seed % 3))) * (1 - amount)
    if family == "travel":
        result = (dx * (1 - amount) * 170, dy * (1 - amount) * 125 + wobble * 15, wobble * 7, .76 + amount * .24)
    elif family == "orbit":
        result = (math.cos(amount * math.pi * 2) * (1 - amount) * 100, math.sin(amount * math.pi * 2) * (1 - amount) * 75, (1 - amount) * 24, .72 + amount * .28)
    elif family == "construct":
        result = (dx * (1 - amount) * 55, (1 - amount) * -82, (1 - amount) * (26 if seed % 2 else -26), .55 + amount * .45)
    elif family == "impact":
        result = (wobble * 11, 0, wobble * 4, .84 + amount * .16 + math.sin(amount * math.pi) * .1)
    elif family == "measure":
        result = (0, (1 - amount) * 26, 0, .6 + amount * .4)
    elif family == "grow":
        result = (0, (1 - amount) * 48, wobble * 3, .25 + amount * .75)
    elif family == "draw":
        result = (dx * (1 - amount) * 24, dy * (1 - amount) * 18, (1 - amount) * -3, .94 + amount * .06)
    else:
        result = (dx * (1 - amount) * 62, dy * (1 - amount) * 48, wobble * 8, .7 + amount * .3)
    x, y, rotation, scale = result
    if physics == "glide":
        return x * .48, y * .48, rotation * .25, .88 + (scale - .88) * .55
    if physics in {"drift", "float"}:
        return x * .35 + math.sin(amount * math.pi) * 18, y * .35 - math.sin(amount * math.pi * 2) * 10, rotation * .18, .9 + (scale - .9) * .5
    if physics == "slam":
        return x * 1.55, y * 1.2, rotation * 1.5, .25 + amount * .75
    if physics == "bounce":
        bounce = math.sin(amount * math.pi * 2.5) * (1 - amount)
        return x * .8, y * .8 - bounce * 24, rotation + bounce * 8, scale + bounce * .1
    if physics == "jitter":
        jitter = math.sin((amount * 30) + seed % 7) * (1 - amount)
        return x + jitter * 8, y + jitter * 4, rotation + jitter * 3, scale
    if physics == "mechanical":
        return round(x / 12) * 12, round(y / 12) * 12, 0, scale
    if physics == "measured":
        return x * .55, y * .55, rotation * .2, .82 + (scale - .82) * .7
    return result
def wrap(text: str, maximum: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > maximum:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines[:4]


def paper_background(palette: dict[str, Any]) -> Image.Image:
    mode = str(CURRENT_ART_DIRECTION.get("background") or "editorial-paper")
    image = Image.new("RGB", (WIDTH, HEIGHT), palette.get("background") or PAPER)
    draw = ImageDraw.Draw(image)
    accents = palette.get("accents") or DEFAULT_ACCENTS
    if mode == "notebook-paper":
        pattern = str(CURRENT_ART_DIRECTION.get("paperPattern") or "clean")
        rule = rgba("#a8a39a", 22)[:3]
        if pattern == "ruled":
            for y in range(74, HEIGHT, 58):
                draw.line((0, y, WIDTH, y), fill=rule, width=1)
            draw.line((58, 0, 58, HEIGHT), fill=rgba(accents[0], 40)[:3], width=2)
        elif pattern == "graph":
            for x in range(0, WIDTH, 48):
                draw.line((x, 0, x, HEIGHT), fill=rule, width=1)
            for y in range(0, HEIGHT, 48):
                draw.line((0, y, WIDTH, y), fill=rule, width=1)
            draw.line((38, 0, 38, HEIGHT), fill=rgba(accents[0], 45)[:3], width=2)
        elif pattern == "ledger":
            for y in range(92, HEIGHT, 72):
                draw.line((36, y, WIDTH - 36, y), fill=rule, width=1)
            for x in (115, 430, 745, 1060):
                draw.line((x, 0, x, HEIGHT), fill=rgba(accents[2], 20)[:3], width=1)
            draw.rectangle((25, 25, WIDTH - 25, HEIGHT - 25), outline=rgba(MUTED, 28)[:3], width=1)
        elif pattern == "archive":
            draw.rectangle((34, 28, WIDTH - 34, HEIGHT - 28), outline=rgba(accents[0], 65)[:3], width=2)
            draw.rectangle((46, 40, WIDTH - 46, HEIGHT - 40), outline=rgba(MUTED, 28)[:3], width=1)
            draw.ellipse((WIDTH - 180, 38, WIDTH - 68, 150), outline=rgba(accents[0], 30)[:3], width=5)
        elif pattern == "field":
            for index in range(7):
                y = 120 + index * 78
                draw.arc((28 + index * 23, y, 260 + index * 23, y + 145), 198, 326, fill=rgba(accents[index % len(accents)], 26)[:3], width=2)
        # Paper grain is common craftsmanship; layout and mark language are not.
        for index in range(150):
            x = (index * 191 + 37) % WIDTH
            y = (index * 113 + 19) % HEIGHT
            shade = 225 + (index % 8)
            draw.point((x, y), fill=(shade, shade - 2, shade - 6))
    elif mode in {"editorial-paper", "archive"}:
        step = 32 if mode == "editorial-paper" else 44
        for y in range(0, HEIGHT, step):
            draw.line((0, y, WIDTH, y), fill=rgba(MUTED, 35)[:3], width=1)
        if mode == "editorial-paper":
            for x in range(0, WIDTH, step):
                draw.line((x, 0, x, HEIGHT), fill=rgba(MUTED, 25)[:3], width=1)
        else:
            draw.rectangle((45, 35, WIDTH - 45, HEIGHT - 35), outline=rgba(accents[0], 120)[:3], width=3)
            draw.ellipse((WIDTH - 220, 55, WIDTH - 75, 200), outline=rgba(accents[0], 90)[:3], width=6)
    elif mode in {"swiss-grid", "blueprint"}:
        step = 60 if mode == "swiss-grid" else 40
        grid = rgba(accents[0], 52 if mode == "blueprint" else 34)[:3]
        for x in range(0, WIDTH, step): draw.line((x, 0, x, HEIGHT), fill=grid, width=1)
        for y in range(0, HEIGHT, step): draw.line((0, y, WIDTH, y), fill=grid, width=1)
        draw.line((70, 0, 70, HEIGHT), fill=rgba(accents[1], 100)[:3], width=2)
        draw.line((0, HEIGHT - 55, WIDTH, HEIGHT - 55), fill=rgba(accents[0], 100)[:3], width=2)
    elif mode == "cinematic-noir":
        for index in range(8):
            shade = 10 + index * 3
            draw.polygon([(index * 180 - 220, 0), (index * 180 + 80, 0), (index * 180 + 380, HEIGHT), (index * 180 + 80, HEIGHT)], fill=(shade, shade, shade))
        draw.rectangle((0, HEIGHT - 10, WIDTH, HEIGHT), fill=rgba(accents[0])[:3])
    elif mode == "poster-blocks":
        draw.rectangle((0, 0, WIDTH, 115), fill=rgba(accents[1])[:3])
        draw.rectangle((WIDTH - 290, 115, WIDTH, HEIGHT), fill=rgba(accents[0])[:3])
        draw.polygon([(0, HEIGHT - 190), (520, HEIGHT - 290), (620, HEIGHT), (0, HEIGHT)], fill=rgba(accents[3])[:3])
    elif mode == "soft-field":
        draw.ellipse((-180, -150, 520, 420), fill=rgba(accents[1], 60)[:3])
        draw.ellipse((850, 360, 1450, 880), fill=rgba(accents[2], 65)[:3])
        draw.ellipse((470, 220, 900, 650), outline=rgba(accents[0], 60)[:3], width=18)
    elif mode == "chalkboard":
        for x in range(10, WIDTH, 37):
            for y in range(12, HEIGHT, 43):
                if (x * 7 + y * 11) % 5 == 0: draw.point((x, y), fill=rgba(INK, 50)[:3])
        draw.line((55, 80, WIDTH - 55, 80), fill=rgba(accents[0], 110)[:3], width=3)
    elif mode == "collage":
        draw.polygon([(-20, 80), (390, 35), (430, 310), (15, 340)], fill=rgba(accents[2], 90)[:3])
        draw.polygon([(930, 30), (1290, 105), (1240, 420), (880, 360)], fill=rgba(accents[1], 75)[:3])
        draw.polygon([(40, 570), (560, 510), (610, 760), (0, 760)], fill=rgba(accents[0], 65)[:3])
    elif mode == "terminal":
        for y in range(0, HEIGHT, 5): draw.line((0, y, WIDTH, y), fill=rgba(accents[0], 18)[:3], width=1)
        for x in range(30, WIDTH, 120): draw.text((x, (x * 13) % HEIGHT), "01", font=font(12), fill=rgba(accents[0], 55)[:3])
    elif mode == "folk-pattern":
        for x in range(-20, WIDTH, 90):
            for y in range(-20, HEIGHT, 90):
                color = accents[(x // 90 + y // 90) % len(accents)]
                draw.ellipse((x, y, x + 24, y + 24), fill=rgba(color, 70)[:3])
                draw.rectangle((x + 30, y + 30, x + 44, y + 44), fill=rgba(color, 55)[:3])
    elif mode == "data-space":
        for x in range(30, WIDTH, 55):
            for y in range(30, HEIGHT, 55):
                radius = 2 if (x + y) % 3 else 4
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(accents[(x + y) % len(accents)], 90)[:3])
        for radius in (140, 240, 340): draw.ellipse((WIDTH // 2 - radius, HEIGHT // 2 - radius, WIDTH // 2 + radius, HEIGHT // 2 + radius), outline=rgba(accents[1], 35)[:3], width=2)
    return image
def icon(draw: ImageDraw.ImageDraw, name: str, box: tuple[int, int, int, int], color: str, amount: float) -> None:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    w, h = x2 - x1, y2 - y1
    fill = rgba(color, int(85 + 95 * amount))
    line = rgba(INK)
    category = (
        "study" if re.search(r"book|bookmark|pencil|brain|question", name)
        else "security" if re.search(r"shield|lock|warning|key|packet", name)
        else "technology" if re.search(r"chip|terminal|network|database|robot", name)
        else "science" if re.search(r"flask|atom|microscope|molecule|wave", name)
        else "health" if re.search(r"heart|pulse|cross|cell|care", name)
        else "food" if re.search(r"bowl|timer|flame|ingredient", name)
        else "nature" if re.search(r"leaf|globe|drop|sun|tree", name)
        else "gaming" if re.search(r"controller|trophy|flag|gem|map", name)
        else "business" if re.search(r"chart|target|coin|briefcase|arrow-up", name)
        else "general"
    )
    if category == "security":
        if "lock" in name:
            draw.rounded_rectangle((x1 + 11, cy - 2, x2 - 11, y2 - 4), radius=7, fill=fill, outline=line, width=3)
            draw.arc((cx - 19, y1 + 4, cx + 19, cy + 15), 180, 360, fill=line, width=4)
            draw.ellipse((cx - 4, cy + 12, cx + 4, cy + 20), fill=line)
        elif "warning" in name:
            draw.polygon([(cx, y1 + 2), (x2 - 3, y2 - 5), (x1 + 3, y2 - 5)], fill=fill, outline=line)
            draw.line((cx, y1 + 21, cx, cy + 10), fill=line, width=5); draw.ellipse((cx - 3, y2 - 18, cx + 3, y2 - 12), fill=line)
        elif "key" in name:
            draw.ellipse((x1 + 4, cy - 15, x1 + 34, cy + 15), fill=fill, outline=line, width=3)
            draw.line((x1 + 32, cy, x2 - 4, cy), fill=line, width=5); draw.line((x2 - 20, cy, x2 - 20, cy + 12), fill=line, width=4)
        elif "packet" in name:
            draw.rounded_rectangle((x1 + 3, y1 + 10, x2 - 3, y2 - 10), radius=7, fill=fill, outline=line, width=3)
            draw.line((x1 + 5, y1 + 14, cx, cy + 7, x2 - 5, y1 + 14), fill=line, width=3)
        else:
            points = [(cx, y1), (x2 - 5, y1 + h // 4), (x2 - 11, y2 - 13), (cx, y2), (x1 + 11, y2 - 13), (x1 + 5, y1 + h // 4)]
            draw.polygon(points, fill=fill, outline=line, width=3)
            draw.line((cx - 13, cy, cx - 3, cy + 11, cx + 17, cy - 13), fill=line, width=4, joint="curve")
    elif category == "study":
        draw.polygon([(x1, y1 + 8), (cx, y1 + 16), (cx, y2), (x1, y2 - 10)], fill=fill, outline=line)
        draw.polygon([(cx, y1 + 16), (x2, y1 + 8), (x2, y2 - 10), (cx, y2)], fill=fill, outline=line)
        draw.line((cx, y1 + 16, cx, y2), fill=line, width=3)
    elif category == "technology":
        draw.rounded_rectangle((x1 + 7, y1 + 7, x2 - 7, y2 - 7), radius=9, fill=fill, outline=line, width=3)
        draw.rectangle((x1 + 21, y1 + 21, x2 - 21, y2 - 21), outline=line, width=3)
        for delta in (16, 30, 44):
            draw.line((x1 - 3, y1 + delta, x1 + 7, y1 + delta), fill=line, width=2)
            draw.line((x2 - 7, y1 + delta, x2 + 3, y1 + delta), fill=line, width=2)
    elif category == "science":
        draw.polygon([(cx - 9, y1 + 5), (cx + 9, y1 + 5), (cx + 9, cy - 7), (x2 - 7, y2 - 8), (x1 + 7, y2 - 8), (cx - 9, cy - 7)], fill=fill, outline=line)
        draw.line((x1 + 14, cy + 12, x2 - 14, cy + 12), fill=line, width=3)
    elif category == "health":
        draw.polygon([(cx, y2), (x1 + 5, cy), (x1 + 10, y1 + 15), (cx - 4, y1 + 20), (cx, y1 + 34), (cx + 6, y1 + 20), (x2 - 10, y1 + 15), (x2 - 5, cy)], fill=fill, outline=line)
    elif category == "food":
        draw.pieslice((x1, y1 - 10, x2, y2), 0, 180, fill=fill, outline=line, width=3)
        for dx in (-15, 0, 15):
            draw.arc((cx + dx - 7, y1, cx + dx + 7, cy), 180, 360, fill=line, width=2)
    elif category == "nature":
        draw.ellipse((x1 + 6, y1 + 4, x2 - 6, y2 - 4), fill=fill, outline=line, width=3)
        draw.line((x1 + 14, y2 - 9, x2 - 12, y1 + 12), fill=line, width=3)
    elif category == "gaming":
        draw.rounded_rectangle((x1 + 4, y1 + 15, x2 - 4, y2 - 8), radius=18, fill=fill, outline=line, width=3)
        draw.line((x1 + 17, cy, x1 + 38, cy), fill=line, width=3); draw.line((x1 + 27, cy - 10, x1 + 27, cy + 10), fill=line, width=3)
        draw.ellipse((x2 - 36, cy - 10, x2 - 28, cy - 2), fill=line); draw.ellipse((x2 - 24, cy + 2, x2 - 16, cy + 10), fill=line)
    elif category == "business":
        draw.line((x1 + 5, y2 - 5, x1 + 5, y1 + 5), fill=line, width=3); draw.line((x1 + 5, y2 - 5, x2 - 3, y2 - 5), fill=line, width=3)
        for index, height in enumerate((18, 31, 46)):
            left = x1 + 15 + index * 17
            draw.rectangle((left, y2 - 6 - height, left + 10, y2 - 6), fill=fill, outline=line, width=2)
    else:
        draw.ellipse((x1 + 8, y1 + 3, x2 - 8, y2 - 18), fill=fill, outline=line, width=3)
        draw.line((cx - 10, y2 - 15, cx + 10, y2 - 15), fill=line, width=3)


def node_layer(item: dict[str, Any], action: dict[str, Any], amount: float, palette: dict[str, Any], style: str) -> Image.Image:
    accents = palette.get("accents") or DEFAULT_ACCENTS
    accent = accents[int(item.get("accent") or 0) % len(accents)]
    shape = str(CURRENT_ART_DIRECTION.get("shapeLanguage") or "ink-annotations")
    width = 360 if shape == "type-blocks" else 315 if item.get("emphasis") == "primary" else 270
    height = 170 if shape in {"type-blocks", "silhouette-cuts"} else 145
    layer = Image.new("RGBA", (width + 54, height + 54), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = (17, 18, width + 16, height + 17)
    background = str(palette.get("background") or PAPER)
    if shape == "geometric-modules":
        draw.rectangle(box, fill=rgba(background, 238), outline=rgba(accent), width=5)
        draw.line((17, 45, width + 16, 45), fill=rgba(accent), width=3)
    elif shape == "technical-wireframe":
        draw.rectangle(box, fill=rgba(background, 210), outline=rgba(accent), width=3)
        for offset in (7, 13): draw.rectangle((17 + offset, 18 + offset, width + 16 - offset, height + 17 - offset), outline=rgba(accent, 65), width=1)
    elif shape == "silhouette-cuts":
        points = [(18, 32), (width - 25, 18), (width + 16, 54), (width - 3, height + 17), (42, height + 7)]
        draw.polygon(points, fill=rgba("#242424", 245), outline=rgba(accent))
        draw.line(points + [points[0]], fill=rgba(accent), width=4)
    elif shape == "type-blocks":
        draw.rectangle(box, fill=rgba(accent, 248), outline=rgba(INK), width=7)
        draw.rectangle((28, 30, width + 5, height + 5), outline=rgba(INK, 85), width=2)
    elif shape == "organic-blobs":
        draw.ellipse((10, 5, width + 30, height + 35), fill=rgba(accent, 85), outline=rgba(INK), width=3)
    elif shape == "chalk-marks":
        draw.rounded_rectangle(box, radius=9, fill=rgba(background, 170), outline=rgba(accent), width=4)
        draw.line((28, height + 5, width, height + 12), fill=rgba(accent, 145), width=6)
    elif shape == "torn-paper":
        points = [(22, 18), (width - 10, 25), (width + 16, height - 9), (width - 18, height + 17), (35, height + 9), (17, 48)]
        draw.polygon(points, fill=rgba(accent, 150), outline=rgba(INK))
        draw.line(points + [points[0]], fill=rgba(INK), width=3, joint="curve")
    elif shape == "terminal-windows":
        draw.rectangle(box, fill=rgba("#07110a", 246), outline=rgba(accent), width=3)
        draw.rectangle((17, 18, width + 16, 43), fill=rgba(accent, 75))
        for x in (30, 45, 60): draw.ellipse((x, 26, x + 7, 33), fill=rgba(accent))
    elif shape == "pattern-tiles":
        draw.rounded_rectangle(box, radius=40, fill=rgba(accent, 210), outline=rgba(INK), width=4)
        for x in range(35, width, 42): draw.ellipse((x, height - 18, x + 12, height - 6), fill=rgba(background, 150))
    elif shape == "document-stamps":
        draw.rectangle(box, fill=rgba(background, 246), outline=rgba(INK), width=2)
        draw.rectangle((24, 25, width + 8, height + 7), outline=rgba(accent, 120), width=3)
        draw.ellipse((width - 74, 28, width + 5, 107), outline=rgba(accent, 150), width=4)
    elif shape == "light-nodes":
        draw.rounded_rectangle(box, radius=height // 2, fill=rgba(background, 205), outline=rgba(accent), width=3)
        draw.ellipse((30, 34, 55, 59), fill=rgba(accent), outline=rgba(INK), width=2)
    else:
        if style == "cutout":
            points = [(22, 17), (width + 6, 22), (width + 15, height), (width - 7, height + 16), (17, height + 8), (16, 31)]
            draw.polygon(points, fill=rgba(background, 238), outline=rgba(INK)); draw.line(points + [points[0]], fill=rgba(INK), width=3, joint="curve")
        elif style == "label":
            draw.line((18, height + 10, width + 13, height + 10), fill=rgba(accent), width=8)
        else:
            draw.rounded_rectangle(box, radius=18, fill=rgba(background, 235), outline=rgba(INK), width=3)
    show_icon = shape not in {"type-blocks", "terminal-windows", "document-stamps"} and style != "label"
    if show_icon:
        icon(draw, str(item.get("glyph") or "bulb"), (width - 57, 2, width + 17, 72), accent, amount)
    action_label = str(action.get("kind") or item.get("emphasis") or "idea").replace("-", " ").upper()
    prefix = "> " if shape == "terminal-windows" else ""
    label_color = "#111111" if shape in {"type-blocks", "pattern-tiles"} else INK
    draw.text((31, 28 if shape != "terminal-windows" else 53), prefix + action_label, font=font(13, True), fill=rgba(label_color if shape == "type-blocks" else MUTED))
    label = str(item.get("label") or "Key idea")
    label_size = 27 if shape == "type-blocks" else 22 if item.get("emphasis") == "primary" else 19
    for line_index, line in enumerate(wrap(label.upper() if shape == "type-blocks" else label, 24 if width > 300 else 20)):
        draw.text((31, 58 + line_index * 27), line, font=font(label_size, True), fill=rgba(label_color))
    if shape not in {"type-blocks", "terminal-windows", "light-nodes"}:
        draw.line((31, height - 12, 31 + int((width - 75) * amount), height - 12), fill=rgba(accent), width=6)
    return layer
def curve_points(start: tuple[float, float], end: tuple[float, float], bend: float, amount: float) -> list[tuple[float, float]]:
    count = max(2, int(34 * max(.04, amount)))
    cx, cy = (start[0] + end[0]) / 2 + bend, (start[1] + end[1]) / 2 - bend
    points = []
    for index in range(count):
        t = (index / max(1, count - 1)) * amount
        x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * cx + t ** 2 * end[0]
        y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * cy + t ** 2 * end[1]
        points.append((x, y))
    return points


def _semantic_amounts(scene: dict[str, Any], frame: int, duration: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[float]]:
    plan = scene["motionPlan"]
    objects = list(plan.get("objects") or [])[:5]
    actions = {str(action.get("targetId")): action for action in plan.get("actions") or []}
    amounts: list[float] = []
    for index, item in enumerate(objects):
        action = actions.get(str(item.get("id")))
        if action:
            start = float(action.get("startRatio") or .06) * duration
            end = float(action.get("endRatio") or min(.95, .18 + index * .13)) * duration
        else:
            start = duration * (.06 + index * .13)
            end = start + duration * .13
        amounts.append(progress(frame, start, end))
    return objects, actions, amounts


def _semantic_title(draw: ImageDraw.ImageDraw, scene: dict[str, Any], amount: float, accent: str, *, center: bool = False, y: int = 54, size: int = 48) -> int:
    title = str(scene.get("title") or "Video explanation")
    lines = wrap(title, 42 if not center else 34)[:3]
    block_height = len(lines) * (size + 4)
    for index, line in enumerate(lines):
        face = font(size, True)
        box = draw.textbbox((0, 0), line, font=face)
        width = box[2] - box[0]
        x = (WIDTH - width) / 2 if center else 70
        x += (1 - amount) * (-24 if not center else 0)
        draw.text((x, y + index * (size + 4)), line, font=face, fill=rgba(INK, int(255 * amount)))
    underline_y = y + block_height + 8
    if center:
        draw.line((WIDTH / 2 - 120 * amount, underline_y, WIDTH / 2 + 120 * amount, underline_y), fill=rgba(accent, int(255 * amount)), width=6)
    else:
        draw.line((70, underline_y, 70 + 260 * amount, underline_y), fill=rgba(accent, int(255 * amount)), width=6)
    return underline_y


def _semantic_card(item: dict[str, Any], amount: float, accent: str, width: int = 250, height: int = 116, number: int | None = None) -> Image.Image:
    layer = Image.new("RGBA", (width + 24, height + 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    fill = rgba(PAPER, 245)
    draw.rounded_rectangle((10, 10, width + 10, height + 10), radius=18, fill=fill, outline=rgba(INK, int(210 * amount)), width=2)
    draw.rounded_rectangle((10, 10, 24, height + 10), radius=7, fill=rgba(accent, int(255 * amount)))
    if number is not None:
        draw.ellipse((32, 25, 72, 65), fill=rgba(accent, int(235 * amount)))
        draw.text((46, 32), str(number), font=font(18, True), fill=rgba(PAPER, int(255 * amount)), anchor="mm")
        text_x = 84
    else:
        icon(draw, str(item.get("glyph") or "bulb"), (31, 22, 81, 72), accent, amount)
        text_x = 91
    label = str(item.get("label") or "Key idea")
    for line_index, line in enumerate(wrap(label, 19)[:3]):
        draw.text((text_x, 27 + line_index * 23), line, font=font(18, line_index == 0), fill=rgba(INK, int(255 * amount)))
    layer.putalpha(layer.getchannel("A").point(lambda value: int(value * amount)))
    return layer


def _composite_at(image: Image.Image, layer: Image.Image, x: float, y: float, amount: float, *, rise: int = 22) -> None:
    image.alpha_composite(layer, (int(x), int(y + (1 - amount) * rise)))


def _grammar_points(operator: str, count: int, seed: int) -> list[tuple[float, float]]:
    count = max(1, count)
    if operator in {"path", "step", "cascade", "track", "route"}:
        return [(150 + i * (970 / max(1, count - 1)), 390 + math.sin(i * 1.7 + seed % 5) * 125) for i in range(count)]
    if operator in {"split", "mirror", "balance", "before-after", "diverge"}:
        return [(260 if i < math.ceil(count / 2) else 1010, 285 + (i % math.ceil(count / 2)) * 145) for i in range(count)]
    if operator in {"orbit", "loop", "ring", "radial-flow", "spiral"}:
        points = []
        for i in range(count):
            angle = -math.pi / 2 + i * (2 * math.pi / count)
            radius = 155 + (i * 24 if operator == "spiral" else 0)
            points.append((780 + math.cos(angle) * radius, 410 + math.sin(angle) * radius))
        return points
    if operator in {"tree", "branch", "funnel", "nested", "stack"}:
        base = [(640, 245), (390, 390), (890, 390), (260, 555), (520, 555), (760, 555), (1020, 555)]
        return base[:count]
    if operator in {"scale", "accumulate", "rank", "plot", "radial-measure"}:
        return [(520 + i * (620 / max(1, count - 1)), 555 - ((seed >> (i * 2)) & 7) * 43) for i in range(count)]
    if operator in {"cluster", "constellation", "flow", "field", "scatter", "zones"}:
        return [(245 + ((seed >> (i * 3)) & 15) * 57, 245 + ((seed >> (i * 4 + 5)) & 7) * 56) for i in range(count)]
    return [(190 + i * (900 / max(1, count - 1)), 385 + (i % 2) * 125) for i in range(count)]


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], amount: float, color: str, width: int = 5) -> None:
    ex = start[0] + (end[0] - start[0]) * amount
    ey = start[1] + (end[1] - start[1]) * amount
    draw.line((start[0], start[1], ex, ey), fill=rgba(color, 220), width=width)
    if amount > .82:
        angle = math.atan2(ey - start[1], ex - start[0])
        wing = 15
        left = (ex - math.cos(angle - .55) * wing, ey - math.sin(angle - .55) * wing)
        right = (ex - math.cos(angle + .55) * wing, ey - math.sin(angle + .55) * wing)
        draw.polygon([(ex, ey), left, right], fill=rgba(color, 230))


def _draw_grammar_mark(draw: ImageDraw.ImageDraw, mark: str, item: dict[str, Any], x: float, y: float, size: float, amount: float, color: str, metric: str) -> None:
    alpha = int(255 * amount)
    r = size * (.72 + .28 * amount)
    label = str(item.get("label") or "Key idea")
    if mark in {"number"}:
        value = metric or re.search(r"\b\d+(?:[.,]\d+)?(?:%|x|×)?\b", label or "")
        value = value if isinstance(value, str) else (value.group(0) if value else str(max(1, int(size // 25))))
        draw.text((x, y), value, font=font(int(r * .9), True), fill=rgba(color, alpha), anchor="mm")
    elif mark in {"bar", "meter", "measure"}:
        height = r * 1.6 * amount
        draw.rounded_rectangle((x - r * .45, y + r * .75 - height, x + r * .45, y + r * .75), radius=10, fill=rgba(color, alpha), outline=rgba(INK, alpha), width=3)
    elif mark in {"ring", "arc", "orbit", "circle", "cell"}:
        box = (x - r, y - r, x + r, y + r)
        if mark == "arc":
            draw.arc(box, -90, -90 + 340 * amount, fill=rgba(color, alpha), width=max(3, int(r * .12)))
        else:
            draw.ellipse(box, fill=rgba(color, int(35 * amount)), outline=rgba(color, alpha), width=max(3, int(r * .1)))
            if mark in {"cell", "orbit"}:
                draw.ellipse((x - r * .36, y - r * .36, x + r * .36, y + r * .36), outline=rgba(INK, int(180 * amount)), width=3)
    elif mark in {"node", "dot", "particle", "packet", "port", "pulse"}:
        draw.ellipse((x - r * .45, y - r * .45, x + r * .45, y + r * .45), fill=rgba(color, alpha), outline=rgba(INK, alpha), width=3)
        if mark in {"pulse", "packet"}:
            draw.ellipse((x - r * .72, y - r * .72, x + r * .72, y + r * .72), outline=rgba(color, int(110 * amount)), width=3)
    elif mark in {"boundary", "container", "zone", "frame", "page", "terminal"}:
        box = (x - r * 1.15, y - r * .72, x + r * 1.15, y + r * .72)
        draw.rounded_rectangle(box, radius=14 if mark != "page" else 2, fill=rgba(PAPER, int(205 * amount)), outline=rgba(color, alpha), width=4)
        if mark == "terminal":
            draw.line((box[0], box[1] + 24, box[2], box[1] + 24), fill=rgba(color, alpha), width=3)
            draw.text((box[0] + 15, box[1] + 36), "> " + label[:18].lower(), font=font(14, True), fill=rgba(color, alpha))
    elif mark in {"line", "slope", "plot", "area", "wave", "pulse", "steam", "root", "trace", "path"}:
        points = []
        for i in range(24):
            t = i / 23 * amount
            px = x - r + t * r * 2
            if mark in {"slope", "plot", "area"}:
                py = y + r * .55 - t * r * 1.15 + math.sin(t * math.pi * 3) * r * .12
            else:
                py = y + math.sin(t * math.pi * (3 if mark == "wave" else 2)) * r * .35
            points.append((px, py))
        if len(points) > 1:
            draw.line(points, fill=rgba(color, alpha), width=6, joint="curve")
        if mark == "area" and points:
            draw.polygon([*points, (points[-1][0], y + r), (points[0][0], y + r)], fill=rgba(color, int(50 * amount)))
    elif mark in {"underline", "highlight", "brace"}:
        if mark == "highlight":
            draw.rounded_rectangle((x - r, y - r * .2, x - r + 2 * r * amount, y + r * .2), radius=8, fill=rgba(color, int(125 * amount)))
        elif mark == "brace":
            draw.arc((x - r, y - r, x, y + r), -90, 90, fill=rgba(color, alpha), width=5)
            draw.arc((x, y - r, x + r, y + r), 90, 270, fill=rgba(color, alpha), width=5)
        else:
            draw.line((x - r, y, x - r + 2 * r * amount, y), fill=rgba(color, alpha), width=8)
    elif mark in {"arrow", "branch"}:
        _draw_arrow(draw, (x - r, y + r * .45), (x + r, y - r * .45), amount, color, 7)
        if mark == "branch":
            _draw_arrow(draw, (x, y), (x + r * .85, y + r * .75), amount, color, 4)
    elif mark in {"target"}:
        for index in range(3):
            rr = r * (1 - index * .27)
            draw.ellipse((x - rr, y - rr, x + rr, y + rr), outline=rgba(color if index % 2 == 0 else INK, alpha), width=4)
    elif mark in {"burst", "alert", "badge", "stamp"}:
        points = []
        for index in range(16):
            angle = index * math.pi / 8
            rr = r if index % 2 == 0 else r * .66
            points.append((x + math.cos(angle) * rr, y + math.sin(angle) * rr))
        draw.polygon(points, fill=rgba(color, int(175 * amount)), outline=rgba(INK, alpha))
    else:
        icon(draw, str(item.get("glyph") or mark or "bulb"), (x - r, y - r, x + r, y + r), color, amount)
    if mark not in {"type", "number", "underline", "highlight", "brace"}:
        lines = wrap(label, 18)[:2]
        for line_index, line in enumerate(lines):
            box = draw.textbbox((0, 0), line, font=font(16, line_index == 0))
            draw.text((x - (box[2] - box[0]) / 2, y + r + 12 + line_index * 20), line, font=font(16, line_index == 0), fill=rgba(INK, alpha))


def _short_label(value: str, maximum: int = 24) -> str:
    words = re.sub(r"\s+", " ", value).strip().split()
    return " ".join(words[:4])[:maximum].rstrip()


def _draw_illustration_prop(
    draw: ImageDraw.ImageDraw,
    kind: str,
    center: tuple[float, float],
    size: float,
    color: str,
    amount: float,
) -> None:
    """Draw a concrete editorial illustration prop, never a UI card."""
    cx, cy = center
    s = max(24.0, size * (.58 + .42 * ease(amount)))
    x1, y1, x2, y2 = cx - s, cy - s, cx + s, cy + s
    alpha = max(10, int(255 * amount))
    line = rgba(INK, alpha)
    fill = rgba(color, int(70 + 150 * amount))
    pale = rgba(color, int(28 + 72 * amount))
    k = kind.lower()

    if k in {"email", "credential", "request"}:
        draw.rounded_rectangle((x1, y1 + s * .18, x2, y2 - s * .18), radius=int(s * .12), fill=fill, outline=line, width=max(2, int(s * .055)))
        draw.line((x1 + s * .08, y1 + s * .3, cx, cy + s * .08, x2 - s * .08, y1 + s * .3), fill=line, width=max(2, int(s * .045)), joint="curve")
        if k == "credential":
            draw.ellipse((cx - s * .2, cy - s * .03, cx - s * .02, cy + s * .15), outline=line, width=max(2, int(s * .035)))
            draw.line((cx + s * .05, cy + s * .03, cx + s * .45, cy + s * .03), fill=line, width=max(2, int(s * .04)))
    elif k in {"document", "page", "ledger", "annotation"}:
        draw.polygon([(x1 + s * .2, y1), (x2 - s * .25, y1), (x2, y1 + s * .28), (x2, y2), (x1 + s * .2, y2)], fill=fill, outline=line)
        draw.line((x2 - s * .25, y1, x2 - s * .25, y1 + s * .3, x2, y1 + s * .3), fill=line, width=max(2, int(s * .035)))
        for offset in (.0, .22, .44):
            draw.line((x1 + s * .38, cy - s * .25 + s * offset, x2 - s * .25, cy - s * .25 + s * offset), fill=line, width=max(2, int(s * .025)))
    elif k in {"laptop", "terminal"}:
        draw.rounded_rectangle((x1, y1, x2, y2 - s * .2), radius=int(s * .1), fill=pale, outline=line, width=max(3, int(s * .055)))
        draw.rectangle((x1 + s * .17, y1 + s * .17, x2 - s * .17, y2 - s * .42), fill=rgba(PAPER, int(220 * amount)), outline=rgba(color, alpha), width=max(2, int(s * .035)))
        draw.polygon([(x1 - s * .16, y2 - s * .17), (x2 + s * .16, y2 - s * .17), (x2 + s * .34, y2), (x1 - s * .34, y2)], fill=fill, outline=line)
        if k == "terminal":
            draw.text((cx, cy - s * .08), ">_", font=font(max(12, int(s * .42)), True), fill=line, anchor="mm")
    elif k in {"server", "database", "service", "queue"}:
        if k == "database":
            draw.ellipse((x1, y1, x2, y1 + s * .55), fill=fill, outline=line, width=max(2, int(s * .04)))
            draw.rectangle((x1, y1 + s * .27, x2, y2 - s * .27), fill=fill, outline=line, width=max(2, int(s * .04)))
            draw.arc((x1, y2 - s * .55, x2, y2), 0, 180, fill=line, width=max(2, int(s * .04)))
        else:
            draw.rounded_rectangle((x1, y1, x2, y2), radius=int(s * .12), fill=fill, outline=line, width=max(3, int(s * .05)))
            for row in (-.42, 0, .42):
                draw.line((x1 + s * .18, cy + row * s, x2 - s * .18, cy + row * s), fill=line, width=max(2, int(s * .03)))
                draw.ellipse((x1 + s * .25, cy + row * s - s * .06, x1 + s * .37, cy + row * s + s * .06), fill=line)
    elif k == "chip":
        draw.rounded_rectangle((x1 + s * .2, y1 + s * .2, x2 - s * .2, y2 - s * .2), radius=int(s * .08), fill=fill, outline=line, width=max(3, int(s * .05)))
        draw.rectangle((x1 + s * .5, y1 + s * .5, x2 - s * .5, y2 - s * .5), outline=line, width=max(2, int(s * .035)))
        for delta in (-.55, -.18, .18, .55):
            draw.line((x1, cy + delta * s, x1 + s * .2, cy + delta * s), fill=line, width=3); draw.line((x2 - s * .2, cy + delta * s, x2, cy + delta * s), fill=line, width=3)
            draw.line((cx + delta * s, y1, cx + delta * s, y1 + s * .2), fill=line, width=3); draw.line((cx + delta * s, y2 - s * .2, cx + delta * s, y2), fill=line, width=3)
    elif k in {"shield", "lock", "gate", "key", "fingerprint"}:
        if k == "shield":
            draw.polygon([(cx, y1), (x2, y1 + s * .35), (x2 - s * .18, y2 - s * .15), (cx, y2), (x1 + s * .18, y2 - s * .15), (x1, y1 + s * .35)], fill=fill, outline=line)
            draw.line((cx - s * .38, cy, cx - s * .08, cy + s * .3, cx + s * .46, cy - s * .38), fill=line, width=max(3, int(s * .07)), joint="curve")
        elif k == "key":
            draw.ellipse((x1, cy - s * .35, x1 + s * .7, cy + s * .35), fill=fill, outline=line, width=max(3, int(s * .05)))
            draw.line((x1 + s * .65, cy, x2, cy), fill=line, width=max(4, int(s * .09)))
            draw.line((x2 - s * .35, cy, x2 - s * .35, cy + s * .3), fill=line, width=max(3, int(s * .06)))
        elif k == "fingerprint":
            for inset in (.05, .28, .5, .7):
                draw.arc((x1 + s * inset, y1 + s * inset, x2 - s * inset, y2 - s * inset), 195, 520, fill=line, width=max(2, int(s * .035)))
        else:
            draw.rounded_rectangle((x1, cy - s * .08, x2, y2), radius=int(s * .12), fill=fill, outline=line, width=max(3, int(s * .05)))
            if k == "lock": draw.arc((cx - s * .5, y1, cx + s * .5, cy + s * .35), 180, 360, fill=line, width=max(4, int(s * .07)))
            else:
                for offset in (-.48, 0, .48): draw.line((cx + offset * s, y1, cx + offset * s, y2), fill=line, width=max(3, int(s * .04)))
    elif k in {"clock", "timer", "gauge", "risk-meter"}:
        draw.ellipse((x1, y1, x2, y2), fill=pale, outline=line, width=max(3, int(s * .055)))
        for angle in range(0, 360, 45):
            a = math.radians(angle); draw.line((cx + math.cos(a) * s * .72, cy + math.sin(a) * s * .72, cx + math.cos(a) * s * .88, cy + math.sin(a) * s * .88), fill=line, width=2)
        theta = (-.7 + amount * 1.8) * math.pi
        draw.line((cx, cy, cx + math.cos(theta) * s * .58, cy + math.sin(theta) * s * .58), fill=rgba(color, alpha), width=max(4, int(s * .07)))
        draw.ellipse((cx - s * .08, cy - s * .08, cx + s * .08, cy + s * .08), fill=line)
    elif k in {"book", "question", "brain", "pencil", "memory-path", "example"}:
        if k == "book":
            draw.polygon([(x1, y1 + s * .2), (cx, y1 + s * .38), (cx, y2), (x1, y2 - s * .18)], fill=fill, outline=line)
            draw.polygon([(cx, y1 + s * .38), (x2, y1 + s * .2), (x2, y2 - s * .18), (cx, y2)], fill=fill, outline=line)
        elif k == "pencil":
            draw.polygon([(x1, y2 - s * .18), (x1 + s * .28, y2), (x2, y1 + s * .28), (x2 - s * .28, y1)], fill=fill, outline=line)
        elif k == "brain":
            for ox, oy, rr in [(-.35,-.15,.42),(.0,-.35,.45),(.35,-.12,.42),(-.2,.28,.4),(.25,.3,.38)]: draw.ellipse((cx+(ox-rr)*s,cy+(oy-rr)*s,cx+(ox+rr)*s,cy+(oy+rr)*s), fill=fill, outline=line, width=max(2,int(s*.035)))
        else:
            draw.ellipse((x1, y1, x2, y2), fill=pale, outline=line, width=max(3, int(s * .05)))
            draw.text((cx, cy), "?" if k == "question" else "→", font=font(max(18, int(s * .9)), True), fill=line, anchor="mm")
    elif k in {"flask", "molecule", "atom", "microscope", "specimen", "cell", "wave", "scan"}:
        if k == "flask":
            draw.polygon([(cx-s*.2,y1),(cx+s*.2,y1),(cx+s*.2,cy-s*.2),(x2,y2),(x1,y2),(cx-s*.2,cy-s*.2)], fill=fill, outline=line)
            draw.line((x1+s*.18,cy+s*.42,x2-s*.18,cy+s*.42), fill=line, width=max(2,int(s*.04)))
        elif k in {"molecule", "atom"}:
            for angle in (0, 60, 120): draw.ellipse((cx-s, cy-s*.38, cx+s, cy+s*.38), outline=line, width=max(2,int(s*.035))) if angle == 0 else draw.arc((x1,y1,x2,y2), angle, angle+250, fill=line, width=max(2,int(s*.035)))
            draw.ellipse((cx-s*.13,cy-s*.13,cx+s*.13,cy+s*.13), fill=fill, outline=line)
        elif k == "wave":
            points=[]
            for index in range(25):
                x=x1+index*(2*s/24); points.append((x,cy+math.sin(index/24*math.pi*4)*s*.45*amount))
            draw.line(points, fill=line, width=max(3,int(s*.06)), joint="curve")
        else:
            draw.ellipse((x1,y1,x2,y2), fill=pale, outline=line, width=max(3,int(s*.05)))
            for angle in range(0,360,60):
                a=math.radians(angle); px=cx+math.cos(a)*s*.58; py=cy+math.sin(a)*s*.58; draw.ellipse((px-s*.11,py-s*.11,px+s*.11,py+s*.11), fill=fill, outline=line)
    elif k in {"heart", "pulse", "body", "care-team", "medicine", "recovery-path"}:
        if k == "heart":
            draw.polygon([(cx,y2),(x1,cy),(x1+s*.12,y1+s*.35),(cx-s*.08,y1+s*.42),(cx,y1+s*.72),(cx+s*.12,y1+s*.42),(x2-s*.12,y1+s*.35),(x2,cy)], fill=fill, outline=line)
        elif k == "medicine":
            draw.rounded_rectangle((x1,cy-s*.35,x2,cy+s*.35),radius=int(s*.35),fill=fill,outline=line,width=max(3,int(s*.05))); draw.line((cx,cy-s*.35,cx,cy+s*.35),fill=line,width=3)
        elif k == "pulse":
            draw.line([(x1,cy),(cx-s*.35,cy),(cx-s*.15,cy-s*.5),(cx+s*.05,cy+s*.45),(cx+s*.3,cy),(x2,cy)], fill=line, width=max(3,int(s*.06)), joint="curve")
        else:
            draw.ellipse((cx-s*.25,y1,cx+s*.25,y1+s*.5),fill=fill,outline=line); draw.line((cx,cy-s*.45,cx,cy+s*.55),fill=line,width=max(3,int(s*.06))); draw.line((cx-s*.55,cy-s*.05,cx+s*.55,cy-s*.05),fill=line,width=max(3,int(s*.05)))
    elif k in {"bowl", "pan", "plate", "ingredient", "flame", "steam", "knife"}:
        if k == "flame":
            draw.polygon([(cx,y1),(cx+s*.25,cy-s*.15),(x2,cy+s*.25),(cx,y2),(x1,cy+s*.25),(cx-s*.18,cy-s*.05)], fill=fill, outline=line)
        elif k in {"bowl", "pan", "plate"}:
            draw.pieslice((x1,y1-s*.25,x2,y2),0,180,fill=fill,outline=line,width=max(3,int(s*.05)))
            if k == "pan": draw.line((x2-s*.1,cy,x2+s*.65,cy-s*.2),fill=line,width=max(4,int(s*.08)))
        elif k == "knife": draw.polygon([(x1,cy-s*.15),(x2-s*.25,cy-s*.28),(x2,cy),(x1,cy+s*.16)],fill=fill,outline=line)
        else:
            for offset in (-.42,0,.42): draw.arc((cx+offset*s-s*.18,y1,cx+offset*s+s*.18,y2),190,350,fill=line,width=max(2,int(s*.035)))
    elif k in {"tree", "leaf", "river", "cloud", "sun", "root", "animal", "water-drop"}:
        if k == "tree":
            draw.rectangle((cx-s*.13,cy,x2-s*.72,y2),fill=fill,outline=line); draw.ellipse((x1,y1,x2,cy+s*.35),fill=pale,outline=line,width=max(3,int(s*.05)))
        elif k == "cloud":
            for ox,oy,rr in [(-.4,.1,.42),(0,-.2,.55),(.45,.08,.4)]: draw.ellipse((cx+(ox-rr)*s,cy+(oy-rr)*s,cx+(ox+rr)*s,cy+(oy+rr)*s),fill=fill,outline=line,width=max(2,int(s*.03)))
        elif k == "sun":
            draw.ellipse((cx-s*.55,cy-s*.55,cx+s*.55,cy+s*.55),fill=fill,outline=line,width=3)
            for angle in range(0,360,45): a=math.radians(angle); draw.line((cx+math.cos(a)*s*.7,cy+math.sin(a)*s*.7,cx+math.cos(a)*s,cy+math.sin(a)*s),fill=line,width=3)
        elif k == "water-drop":
            draw.polygon([(cx,y1),(x2,cy+s*.25),(cx,y2),(x1,cy+s*.25)],fill=fill,outline=line)
        elif k == "river":
            for offset in (-.22,.22): draw.arc((x1,y1+offset*s,x2,y2+offset*s),190,350,fill=line,width=max(3,int(s*.05)))
        else:
            draw.ellipse((x1+s*.18,y1,x2-s*.18,y2),fill=fill,outline=line,width=max(3,int(s*.05))); draw.line((x1+s*.28,y2-s*.15,x2-s*.28,y1+s*.15),fill=line,width=3)
    elif k in {"controller", "level-map", "trophy", "health-bar", "skill-tree", "boss", "player"}:
        if k == "controller":
            draw.rounded_rectangle((x1,y1+s*.25,x2,y2-s*.12),radius=int(s*.35),fill=fill,outline=line,width=max(3,int(s*.05)))
            draw.line((x1+s*.32,cy,x1+s*.75,cy),fill=line,width=4); draw.line((x1+s*.54,cy-s*.22,x1+s*.54,cy+s*.22),fill=line,width=4)
            draw.ellipse((x2-s*.62,cy-s*.2,x2-s*.42,cy),fill=line); draw.ellipse((x2-s*.38,cy,x2-s*.18,cy+s*.2),fill=line)
        elif k == "trophy":
            draw.pieslice((cx-s*.55,y1,cx+s*.55,cy+s*.2),0,180,fill=fill,outline=line); draw.line((cx,cy+s*.1,cx,y2-s*.2),fill=line,width=5); draw.rectangle((cx-s*.45,y2-s*.22,cx+s*.45,y2),fill=fill,outline=line)
        elif k == "health-bar":
            draw.rounded_rectangle((x1,cy-s*.2,x2,cy+s*.2),radius=int(s*.18),outline=line,width=3); draw.rectangle((x1+s*.1,cy-s*.1,x1+s*.1+(2*s-s*.2)*amount,cy+s*.1),fill=fill)
        else:
            draw.ellipse((cx-s*.3,y1,cx+s*.3,y1+s*.6),fill=fill,outline=line); draw.line((cx,cy-s*.35,cx,cy+s*.55),fill=line,width=5); draw.line((cx-s*.55,cy,cx+s*.55,cy),fill=line,width=4)
    elif k in {"coin", "bar-chart", "scale", "target", "market-arrow", "customer"}:
        if k == "coin":
            draw.ellipse((x1,y1,x2,y2),fill=fill,outline=line,width=max(3,int(s*.05))); draw.text((cx,cy),"$",font=font(max(14,int(s*.8)),True),fill=line,anchor="mm")
        elif k == "bar-chart":
            for index,height in enumerate((.45,.72,1.0)): draw.rectangle((x1+s*(.12+index*.58),y2-s*height,x1+s*(.42+index*.58),y2),fill=fill,outline=line,width=2)
        elif k == "target":
            for radius in (1,.66,.32): draw.ellipse((cx-s*radius,cy-s*radius,cx+s*radius,cy+s*radius),outline=line,width=max(2,int(s*.035)))
            draw.ellipse((cx-s*.12,cy-s*.12,cx+s*.12,cy+s*.12),fill=fill)
        elif k == "scale":
            draw.line((cx,y1,cx,y2),fill=line,width=5); draw.line((x1+s*.15,cy-s*.4,x2-s*.15,cy-s*.4),fill=line,width=5)
            draw.arc((x1,cy-s*.4,cx,cy+s*.5),0,180,fill=line,width=4); draw.arc((cx,cy-s*.4,x2,cy+s*.5),0,180,fill=line,width=4)
        else:
            draw.line((x1,y2-s*.2,cx-s*.15,cy,x2, y1+s*.15),fill=line,width=max(4,int(s*.07)),joint="curve"); draw.polygon([(x2,y1+s*.15),(x2-s*.4,y1+s*.12),(x2-s*.1,y1+s*.48)],fill=fill,outline=line)
    elif k == "cursor":
        draw.polygon([(x1,y1),(x2-s*.15,cy),(cx+s*.1,cy+s*.08),(x2-s*.02,y2-s*.05),(cx+s*.28,y2),(cx,cy+s*.25),(x1+s*.05,y2)],fill=fill,outline=line)
    else:
        # Unknown content remains an illustration mark, not a container/card.
        icon(draw, k, (int(x1), int(y1), int(x2), int(y2)), color, amount)


def _load_illustration_asset(relative_path: str) -> Image.Image:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"Unsafe illustration asset path: {relative_path}")
    root = PUBLIC_DIR.resolve()
    asset_path = (root / relative).resolve()
    if root != asset_path and root not in asset_path.parents:
        raise RuntimeError(f"Illustration asset escaped public directory: {relative_path}")
    key = str(asset_path)
    cached = ASSET_CACHE.get(key)
    if cached is None:
        if not asset_path.is_file():
            raise RuntimeError(f"Missing editorial illustration asset: {relative_path}")
        with Image.open(asset_path) as source:
            cached = source.convert("RGBA")
        ASSET_CACHE[key] = cached
    return cached.copy()


def _composite_illustration_asset(
    canvas: Image.Image,
    asset_file: str,
    *,
    x: float,
    y: float,
    width: int,
    amount: float,
    seed: int,
) -> tuple[int, int]:
    source = _load_illustration_asset(asset_file)
    reveal = max(0.0, min(1.0, amount))
    animated_width = max(24, int(width * (.78 + .22 * reveal)))
    animated_height = max(24, round(source.height * animated_width / max(1, source.width)))
    source = source.resize((animated_width, animated_height), Image.Resampling.LANCZOS)
    angle = ((seed % 9) - 4) * .35 * (1 - reveal)
    if abs(angle) > .05:
        source = source.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    alpha_factor = max(0.0, min(1.0, reveal * 1.45))
    if alpha_factor < .999:
        source.putalpha(source.getchannel("A").point(lambda value: int(value * alpha_factor)))
    destination = (round(x - source.width / 2), round(y - source.height / 2))
    canvas.alpha_composite(source, destination)
    return source.size


def _construction_points(construction: str, count: int) -> list[tuple[float, float]]:
    horizontal = [(150 + index * (980 / max(1, count - 1)), 375) for index in range(count)]
    presets: dict[str, list[tuple[float, float]]] = {
        "editorial-cover": [(900, 350), (1090, 225), (1090, 495), (765, 530), (770, 205)],
        "question-led": [(640, 360), (350, 255), (930, 255), (370, 520), (910, 520)],
        "object-hero": [(640, 355), (230, 470), (1050, 470), (350, 225), (930, 225)],
        "cold-open": [(285, 365), (700, 230), (1000, 345), (690, 520), (1080, 520)],
        "annotated-poster": [(640, 330), (260, 235), (1020, 235), (310, 520), (970, 520)],
        "causal-chain": horizontal,
        "step-ladder": [(180 + index * (920 / max(1, count - 1)), 535 - index * (285 / max(1, count - 1))) for index in range(count)],
        "layered-flow": [(230, 255), (640, 255), (1050, 255), (430, 505), (850, 505)],
        "domino": [(170 + index * (930 / max(1, count - 1)), 300 + (150 if index % 2 else 0)) for index in range(count)],
        "radial-process": [(640 + math.cos(-math.pi / 2 + index * 2 * math.pi / count) * 360, 390 + math.sin(-math.pi / 2 + index * 2 * math.pi / count) * 190) for index in range(count)],
        "balance": [(315, 330), (965, 330), (640, 515), (185, 525), (1095, 525)],
        "before-after": [(270, 350), (1010, 350), (640, 510), (390, 530), (890, 530)],
        "fork": [(640, 245), (330, 465), (950, 465), (185, 545), (1095, 545)],
        "spectrum": [(150 + index * (980 / max(1, count - 1)), 410 - abs((count - 1) / 2 - index) * 45) for index in range(count)],
        "evidence-columns": [(230, 275), (640, 275), (1050, 275), (430, 520), (850, 520)],
        "columns": [(760, 250), (920, 390), (1080, 520), (800, 535), (1120, 250)],
        "horizontal-bars": [(760, 220), (880, 330), (1000, 440), (1120, 550), (760, 550)],
        "line-plot": [(735, 515), (835, 440), (950, 340), (1080, 235), (1160, 175)],
        "slope": [(760, 520), (880, 430), (1000, 320), (1120, 210), (760, 235)],
        "annotated-number": [(935, 360), (740, 225), (1130, 225), (760, 535), (1110, 535)],
        "hub-spoke": [(640, 375), (270, 230), (1010, 230), (290, 535), (990, 535)],
        "boundary-crossing": [(250, 350), (510, 350), (790, 350), (1050, 350), (640, 535)],
        "layered-cutaway": [(250, 245), (640, 245), (1030, 245), (440, 510), (840, 510)],
        "evidence-board": [(640, 375), (220, 230), (1060, 230), (290, 535), (990, 535)],
        "orbit-map": [(640 + math.cos(-math.pi / 2 + index * 2 * math.pi / count) * 380, 385 + math.sin(-math.pi / 2 + index * 2 * math.pi / count) * 205) for index in range(count)],
        "emblem": [(640, 370), (360, 470), (920, 470), (440, 220), (840, 220)],
        "resolved-system": [(640, 380), (250, 380), (1030, 380), (430, 540), (850, 540)],
        "seal": [(640, 385), (355, 255), (925, 255), (355, 525), (925, 525)],
        "before-after-summary": [(285, 380), (995, 380), (640, 525), (470, 230), (810, 230)],
        "synthesis-map": [(640, 360), (300, 245), (980, 245), (330, 520), (950, 520)],
        "margin-essay": [(860, 350), (1050, 235), (1070, 505), (685, 535), (690, 210)],
        "cause-map": [(220, 360), (520, 260), (800, 445), (1080, 300), (1040, 535)],
        "object-story": [(430, 360), (785, 250), (990, 430), (730, 540), (220, 525)],
        "annotated-cutaway": [(640, 375), (260, 245), (1020, 245), (300, 525), (980, 525)],
        "visual-equation": [(220, 370), (510, 370), (800, 370), (1080, 370), (640, 535)],
    }
    points = presets.get(construction, horizontal)
    return points[:count]


def _draw_explanation_connector(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    amount: float,
    color: str,
    style: str,
    label: str,
    paper: str,
) -> None:
    amount = max(0.0, min(1.0, amount))
    if amount <= 0:
        return
    sx, sy = start; ex, ey = end
    if style == "right-angle":
        control = [(sx, sy), ((sx + ex) / 2, sy), ((sx + ex) / 2, ey), (ex, ey)]
    elif style in {"curved", "loop"}:
        bend = 95 if style == "loop" else 55
        cx, cy = (sx + ex) / 2, (sy + ey) / 2 - bend
        control = [
            ((1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t ** 2 * ex,
             (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t ** 2 * ey)
            for t in [index / 18 for index in range(19)]
        ]
    else:
        control = [(sx + (ex - sx) * index / 18, sy + (ey - sy) * index / 18) for index in range(19)]
    sampled: list[tuple[float, float]] = []
    for index in range(len(control) - 1):
        ax, ay = control[index]; bx, by = control[index + 1]
        for step in range(5):
            t = step / 5
            sampled.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    sampled.append(control[-1])
    visible = sampled[:max(2, round((len(sampled) - 1) * amount) + 1)]
    width = 8 if style == "ribbon" else 4
    if style == "dashed":
        for index in range(0, len(visible) - 1, 6):
            segment = visible[index:min(len(visible), index + 4)]
            if len(segment) > 1:
                draw.line(segment, fill=rgba(color, 210), width=4)
    else:
        draw.line(visible, fill=rgba(color, 205), width=width, joint="curve")
        if style == "ribbon":
            draw.line(visible, fill=rgba(paper, 210), width=2, joint="curve")
    if amount > .86 and len(visible) > 1:
        px, py = visible[-2]; tx, ty = visible[-1]
        angle = math.atan2(ty - py, tx - px)
        size = 13
        head = [(tx, ty), (tx - math.cos(angle - .55) * size, ty - math.sin(angle - .55) * size), (tx - math.cos(angle + .55) * size, ty - math.sin(angle + .55) * size)]
        draw.polygon(head, fill=rgba(color, 230))
    if label and amount > .58:
        mx, my = control[len(control) // 2]
        label_font = font(17, True)
        box = draw.textbbox((0, 0), label, font=label_font)
        half_w = (box[2] - box[0]) / 2 + 10
        draw.rounded_rectangle((mx - half_w, my - 15, mx + half_w, my + 15), radius=8, fill=rgba(paper, 238), outline=rgba(color, 90), width=1)
        draw.text((mx, my), label, font=label_font, fill=rgba(INK, 235), anchor="mm")

def _entry_position(
    construction: str,
    family: str,
    index: int,
    amount: float,
    final: tuple[float, float],
    positions: dict[str, tuple[float, float]],
    props: list[dict[str, Any]],
    motion_profile: str,
    seed: int,
) -> tuple[float, float]:
    x, y = final
    eased = 1 - (1 - max(0.0, min(1.0, amount))) ** 3
    hero = positions.get(str(props[0].get("id") or ""), (640.0, 380.0)) if props else (640.0, 380.0)
    sx, sy = x, y
    if construction == "cold-open":
        sx, sy = (-180, y + 35) if index == 0 else (WIDTH + 160, y - 55 + index * 18)
    elif construction == "object-hero":
        if index == 0:
            sx, sy = (x, y + 145)
        else:
            sx, sy = hero
    elif construction == "editorial-cover":
        sx, sy = (WIDTH + 180, y) if index else (x + 220, y)
    elif construction == "question-led":
        angle = -math.pi / 2 + index * 1.7
        sx, sy = (115 + math.cos(angle) * 80, 330 + math.sin(angle) * 105)
    elif construction == "annotated-poster":
        sx, sy = (x, -145 if index % 2 == 0 else HEIGHT + 145)
    elif family == "sequence":
        if construction == "causal-chain" and index:
            sx, sy = positions.get(str(props[index - 1].get("id") or ""), (x - 180, y))
        elif construction == "step-ladder":
            sx, sy = (x, HEIGHT + 130)
        elif construction == "layered-flow":
            sx, sy = (x, -120 if index < 3 else HEIGHT + 120)
        elif construction == "domino":
            sx, sy = (x - 170, y - 120 if index % 2 else y + 120)
        else:
            sx, sy = (640, 390)
    elif family == "comparison":
        if construction == "fork":
            sx, sy = hero
        elif construction == "spectrum":
            sx, sy = (x, 610)
        else:
            sx, sy = (-140, y) if x < WIDTH / 2 else (WIDTH + 140, y)
    elif family == "measure":
        sx, sy = (x, 630)
    elif family == "network":
        if construction in {"hub-spoke", "evidence-board", "orbit-map"}:
            sx, sy = hero
        else:
            sx, sy = (-120, y) if index % 2 == 0 else (WIDTH + 120, y)
    elif family == "closing":
        sx, sy = (640, 390)
    elif family == "concept":
        sx, sy = (-150, y) if index % 2 == 0 else (WIDTH + 150, y)

    if "piece" in motion_profile or "folk" in motion_profile:
        sy -= math.sin(eased * math.pi) * (38 + index * 3)
        sx += math.sin(eased * math.pi * 2) * (12 if index % 2 else -12)
    elif "evidence" in motion_profile or "document" in motion_profile:
        sy -= (1 - eased) * (24 + index * 5)
    elif "trace" in motion_profile or "precise" in motion_profile or "packet" in motion_profile:
        # Technical motion stays linear and diagrammatic.
        eased = min(1.0, max(0.0, amount) * 1.08)
    elif "gentle" in motion_profile:
        sy += math.sin(eased * math.pi) * 24
    return (sx + (x - sx) * eased, sy + (y - sy) * eased)

def render_illustrated_scene(scene: dict[str, Any], frame: int, fps: int, palette: dict[str, Any], background: Image.Image) -> Image.Image:
    plan = scene["motionPlan"]
    illustration = plan.get("illustrationPlan") or {}
    explanation = plan.get("explanationPlan") or {}
    construction = str(explanation.get("construction") or "")
    relations = list(explanation.get("relations") or [])
    duration = max(1, math.ceil(float(scene.get("durationSeconds") or 1) * fps))
    image = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    accents = palette.get("accents") or DEFAULT_ACCENTS
    props = list(illustration.get("props") or [])
    events = list(illustration.get("events") or [])
    event_by_subject = {str(event.get("subjectId") or ""): event for event in events}
    amounts = {str(event.get("subjectId") or ""): progress(frame, float(event.get("startRatio") or 0) * duration, float(event.get("endRatio") or .15) * duration) for event in events}
    composition = str(illustration.get("composition") or "landscape")
    layout_variant = int(illustration.get("layoutVariant") or 0) % 4
    world = str(illustration.get("world") or "story-landscape")
    seed = stable_seed(str(illustration.get("signature") or plan.get("signature") or scene.get("title")))
    explanation_family = str(explanation.get("family") or "concept")
    motion_profile = str(CURRENT_ART_DIRECTION.get("motionPhysics") or "measured-draw")
    global_amount = max(amounts.values(), default=progress(frame, duration * .03, duration * .2))

    # Scene-world structure: environmental strokes, not panels or cards.
    horizon = 565 + (seed % 35)
    if any(token in world for token in ("landscape", "route", "journey", "map", "field", "level")):
        draw.line((0, horizon, WIDTH, horizon - 18), fill=rgba(accents[2 % len(accents)], 75), width=5)
        for index in range(7):
            x = 35 + index * 205 + seed % 53
            draw.line((x, horizon, x + 55, horizon - 35 - (index % 3) * 22), fill=rgba(MUTED, 55), width=2)
    elif any(token in world for token in ("bench", "table", "counter", "workbench")):
        draw.line((45, 565, WIDTH - 45, 565), fill=rgba(INK, 115), width=6)
        draw.line((85, 580, WIDTH - 80, 580), fill=rgba(accents[1 % len(accents)], 70), width=18)
    elif any(token in world for token in ("room", "cutaway", "boundary", "arena")):
        draw.line((90, 150, 90, 620, WIDTH - 90, 620, WIDTH - 90, 150), fill=rgba(MUTED, 70), width=3)
        draw.line((WIDTH * .5, 620, WIDTH * .5, 180), fill=rgba(accents[0], 40), width=2)

    positions = {str(prop.get("id")): (float(prop.get("x") or .5) * WIDTH, float(prop.get("y") or .5) * HEIGHT) for prop in props}
    prop_count = max(1, len(props))
    mirror = -1 if seed % 2 else 1
    if construction:
        directed_points = _construction_points(construction, prop_count)
        positions = {str(prop.get("id")): directed_points[index] for index, prop in enumerate(props)}
    layout_mode = composition if not construction else ""
    # Each semantic composition gets its own editorial stage. This is the
    # structural diversity the old renderer lacked; assets no longer sit in
    # the same generic constellation for every document.
    if layout_mode == "chapter-card":
        chapter_variants = [
            [(1030, 335), (900, 515), (1140, 545), (875, 190), (1165, 155)],
            [(180, 480), (70, 315), (390, 405), (85, 615), (415, 610)],
            [(640, 405), (340, 430), (940, 430), (485, 585), (795, 585)],
            [(640, 290), (330, 285), (950, 285), (470, 115), (810, 115)],
        ]
        chapter_points = chapter_variants[layout_variant]
        positions = {str(prop.get("id")): chapter_points[index % len(chapter_points)] for index, prop in enumerate(props)}
    elif layout_mode in {"timeline", "journey"}:
        if layout_variant == 0:
            path_points = [(145 + index * (990 / max(1, prop_count - 1)), 315 + (100 if index % 2 else 0)) for index in range(prop_count)]
        elif layout_variant == 1:
            path_points = [(1135 - index * (990 / max(1, prop_count - 1)), 330 + (85 if index % 2 else 0)) for index in range(prop_count)]
        elif layout_variant == 2:
            path_points = [(150 + index * (985 / max(1, prop_count - 1)), 520 - index * (230 / max(1, prop_count - 1))) for index in range(prop_count)]
        else:
            path_points = [(180 + index * (920 / max(1, prop_count - 1)), 330 + math.sin(index * 1.7) * 105) for index in range(prop_count)]
        positions = {str(prop.get("id")): path_points[index] for index, prop in enumerate(props)}
    elif layout_mode == "comparison":
        if layout_variant in {0, 2}:
            left = [prop for index, prop in enumerate(props) if index < math.ceil(prop_count / 2)]
            right = [prop for index, prop in enumerate(props) if index >= math.ceil(prop_count / 2)]
            positions = {}
            for index, prop in enumerate(left):
                positions[str(prop.get("id"))] = (285, 275 + index * 145)
            for index, prop in enumerate(right):
                positions[str(prop.get("id"))] = (965, 300 + index * 165)
        else:
            positions = {
                str(prop.get("id")): (
                    240 + (index % 3) * 400,
                    275 if index < math.ceil(prop_count / 2) else 540,
                )
                for index, prop in enumerate(props)
            }
    elif layout_mode in {"portrait", "closing", "hero"}:
        portrait_variants = [
            [(640, 390), (365, 405), (915, 405), (470, 575), (810, 575)],
            [(435, 380), (760, 260), (920, 445), (700, 575), (250, 560)],
            [(840, 385), (470, 265), (300, 455), (570, 585), (1030, 560)],
            [(640, 420), (330, 300), (950, 300), (300, 570), (980, 570)],
        ]
        portrait_points = portrait_variants[layout_variant]
        if mirror < 0:
            portrait_points = [(WIDTH - x, y) for x, y in portrait_points]
        positions = {str(prop.get("id")): portrait_points[index % len(portrait_points)] for index, prop in enumerate(props)}
    elif layout_mode == "measure":
        measure_variants = [
            [(770, 285), (940, 285), (1110, 285), (860, 505), (1040, 505)],
            [(760, 500), (900, 385), (1040, 270), (1160, 170), (1090, 540)],
            [(760, 260), (940, 440), (1120, 260), (830, 565), (1060, 565)],
            [(785, 340), (930, 230), (1075, 340), (930, 510), (1150, 525)],
        ]
        points = measure_variants[layout_variant]
        positions = {str(prop.get("id")): points[index % len(points)] for index, prop in enumerate(props)}
    if construction:
        connector_style = str(CURRENT_ART_DIRECTION.get("connectorStyle") or "curved")
        paper_color = str(palette.get("background") or PAPER)
        for index, relation in enumerate(relations):
            source_id = str(relation.get("from") or "")
            target_id = str(relation.get("to") or "")
            if source_id not in positions or target_id not in positions:
                continue
            relation_amount = progress(
                frame,
                float(relation.get("startRatio") or .2) * duration,
                float(relation.get("endRatio") or .55) * duration,
            )
            _draw_explanation_connector(
                draw, positions[source_id], positions[target_id], relation_amount,
                accents[(index + 1) % len(accents)], connector_style,
                str(relation.get("label") or ""), paper_color,
            )
    elif composition in {"journey", "timeline", "cycle", "cutaway"}:
        for index in range(len(props) - 1):
            start = positions[str(props[index]["id"])]
            end = positions[str(props[index + 1]["id"])]
            next_amount = amounts.get(str(props[index + 1]["id"]), 0.0)
            _draw_arrow(draw, start, end, next_amount, accents[(index + 1) % len(accents)], 4)
        if composition == "cycle" and len(props) > 2:
            _draw_arrow(draw, positions[str(props[-1]["id"])], positions[str(props[0]["id"])], amounts.get(str(props[-1]["id"]), 0), accents[0], 4)
    if composition == "comparison":
        split_amount = max(amounts.values(), default=0)
        if layout_variant in {0, 2}:
            draw.line((WIDTH / 2, 165, WIDTH / 2, 635 * split_amount), fill=rgba(accents[0], int(150 * split_amount)), width=4)
        else:
            draw.line((110, 390, 1170 * split_amount, 390), fill=rgba(accents[0], int(150 * split_amount)), width=4)
    if composition == "measure":
        metric = str((plan.get("visualGrammar") or {}).get("metric") or "")
        chart_amount = progress(frame, duration * .08, duration * .46)
        axis_color = rgba(INK, int(155 * chart_amount))
        chart_color = accents[1 % len(accents)]
        if layout_variant == 0:
            draw.line((88, 586, 650, 586), fill=axis_color, width=2)
            draw.line((88, 586, 88, 216), fill=axis_color, width=2)
            for index, target_height in enumerate((74, 166, 318)):
                x1 = 145 + index * 128
                height = target_height * chart_amount
                draw.rectangle((x1, 586 - height, x1 + 66, 586), fill=rgba(chart_color, int(225 * chart_amount)), outline=rgba(INK, int(115 * chart_amount)), width=1)
                draw.text((x1 + 33, 603), f"{index + 1}", font=font(13, True), fill=rgba(MUTED, int(210 * chart_amount)), anchor="ma")
            draw.line((520, 510, 615, 310), fill=rgba(accents[0], int(190 * chart_amount)), width=4)
            draw.polygon([(615, 310), (598, 319), (609, 333)], fill=rgba(accents[0], int(190 * chart_amount)))
        elif layout_variant == 1:
            draw.line((105, 205, 105, 590), fill=axis_color, width=2)
            for index, target_width in enumerate((150, 290, 480)):
                y1 = 245 + index * 112
                width = target_width * chart_amount
                draw.rounded_rectangle((105, y1, 105 + width, y1 + 58), radius=8, fill=rgba(chart_color, int(215 * chart_amount)), outline=rgba(INK, int(110 * chart_amount)), width=1)
                draw.text((82, y1 + 29), str(index + 1), font=font(14, True), fill=rgba(MUTED, int(210 * chart_amount)), anchor="mm")
        elif layout_variant == 2:
            draw.line((100, 580, 650, 580), fill=axis_color, width=2)
            points = [(165, 505), (310, 430), (455, 320), (600, 215)]
            revealed = max(1, math.ceil(len(points) * chart_amount))
            for index, (x, y) in enumerate(points[:revealed]):
                draw.line((x, 580, x, y), fill=rgba(chart_color, int(135 * chart_amount)), width=4)
                draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=rgba(chart_color, int(225 * chart_amount)), outline=axis_color, width=2)
                if index:
                    draw.line((points[index - 1][0], points[index - 1][1], x, y), fill=rgba(accents[0], int(185 * chart_amount)), width=3)
        else:
            draw.line((95, 580, 650, 580), fill=axis_color, width=2)
            draw.line((95, 580, 95, 215), fill=axis_color, width=2)
            curve = [(105, 535), (195, 510), (285, 460), (375, 405), (465, 300), (555, 250), (640, 165)]
            visible = curve[:max(2, math.ceil(len(curve) * chart_amount))]
            draw.line(visible, fill=rgba(chart_color, int(230 * chart_amount)), width=7, joint="curve")
            for x, y in visible:
                draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=rgba(PAPER, int(250 * chart_amount)), outline=rgba(INK, int(170 * chart_amount)), width=2)
        if metric:
            draw.text((92, 170), metric, font=font(68, True), fill=rgba(accents[0], int(240 * global_amount)))

    for index, prop in enumerate(props):
        prop_id = str(prop.get("id") or "")
        amount = amounts.get(prop_id, progress(frame, duration * (.04 + index * .08), duration * (.16 + index * .08)))
        event = event_by_subject.get(prop_id, {})
        kind = str(event.get("kind") or "reveal")
        x, y = positions[prop_id]
        if kind in {"travel", "route", "transfer"} and index:
            px, py = positions[str(props[index - 1]["id"])]
            x = px + (x - px) * amount; y = py + (y - py) * amount
        elif kind == "orbit":
            x += math.cos(amount * math.pi * 2) * (1 - amount) * 52
            y += math.sin(amount * math.pi * 2) * (1 - amount) * 38
        elif kind in {"grow", "assemble", "transform"}:
            y += (1 - amount) * 42
        if construction:
            x, y = _entry_position(
                construction, explanation_family, index, amount, (x, y),
                positions, props, motion_profile, seed,
            )
        scale = float(prop.get("scale") or 1)
        accent = accents[int(prop.get("accent") or index) % len(accents)]
        asset_file = str(prop.get("assetFile") or "")
        if asset_file:
            role = str(prop.get("role") or "support")
            base_width = 310 if role == "hero" else 245 if role == "outcome" else 215
            if composition in {"timeline", "journey"}:
                base_width = 205 if role == "hero" else 168
            elif composition == "chapter-card":
                base_width = 290 if role == "hero" else 175
            elif composition in {"portrait", "closing", "hero"}:
                base_width = 380 if role == "hero" else 185
            elif composition == "comparison":
                base_width = 245 if role == "hero" else 190
            elif composition == "measure":
                base_width = 185 if role == "hero" else 150
            asset_width, asset_height = _composite_illustration_asset(
                image,
                asset_file,
                x=x,
                y=y,
                width=max(120, int(base_width * scale)),
                amount=amount,
                seed=seed + index * 101,
            )
            size = asset_width * .42
            label_y = y + asset_height * .43
        else:
            # Legacy manifests remain renderable, but new v5 manifests are
            # validated in main() and can never silently use these primitives.
            size = (64 if prop.get("role") == "hero" else 49) * scale
            _draw_illustration_prop(draw, str(prop.get("kind") or "idea"), (x, y), size, accent, amount)
            label_y = y + size + 17
        label = _short_label(str(prop.get("label") or ""))
        if label and amount > .55 and composition != "chapter-card":
            draw.text((x, label_y), label, font=font(18 if construction else 15, index == 0), fill=rgba(INK, int(235 * min(1, (amount - .5) * 2))), anchor="ma")
        if kind in {"scan", "focus", "circle"} and 0 < amount < 1:
            radius = size * (1.2 + amount * .28)
            draw.arc((x-radius,y-radius,x+radius,y+radius), -90, -90 + 330 * amount, fill=rgba(accent, 220), width=5)
            if kind == "scan": draw.line((x-radius, y-radius+2*radius*amount, x+radius, y-radius+2*radius*amount), fill=rgba(accent, 170), width=3)
        if kind in {"lock", "resolve", "stabilize"} and amount > .75:
            ring = size * (1.32 + math.sin(amount * math.pi) * .08)
            draw.ellipse((x-ring,y-ring,x+ring,y+ring), outline=rgba(accent, int(180 * (amount-.7)/.3)), width=5)

    takeaway = str(explanation.get("takeaway") or "")
    takeaway_stage = next((stage for stage in explanation.get("stages") or [] if stage.get("purpose") == "takeaway"), {})
    takeaway_amount = progress(
        frame,
        float(takeaway_stage.get("startRatio") or .74) * duration,
        float(takeaway_stage.get("endRatio") or .92) * duration,
    )
    if takeaway and takeaway_amount > 0:
        band = (42, 648, WIDTH - 42, 705)
        draw.rounded_rectangle(
            band, radius=15,
            fill=rgba(palette.get("background") or PAPER, int(246 * takeaway_amount)),
            outline=rgba(accents[0], int(120 * takeaway_amount)), width=2,
        )
        draw.ellipse((59, 670, 69, 680), fill=rgba(accents[0], int(235 * takeaway_amount)))
        draw.text((84, 676), takeaway, font=font(23, True), fill=rgba(INK, int(245 * takeaway_amount)), anchor="lm")

    title_amount = progress(frame, duration * .015, duration * .11)
    title = str(scene.get("title") or "Video explanation")
    if construction in {"editorial-cover", "question-led", "object-hero", "cold-open", "annotated-poster"}:
        chapter = int(illustration.get("chapterNumber") or 1)
        color = accents[0]
        if construction == "editorial-cover":
            draw.rectangle((0, 0, 58 * title_amount, HEIGHT), fill=rgba(color, int(225 * title_amount)))
            draw.text((92, 72), f"SECTION {chapter:02d}", font=font(17, True), fill=rgba(color, int(245 * title_amount)))
            for line_index, line in enumerate(wrap(title, 20)[:4]):
                draw.text((92, 120 + line_index * 58), line, font=font(49 if line_index == 0 else 43, False), fill=rgba(INK, int(255 * title_amount)))
        elif construction == "question-led":
            draw.text((70, 115), "?", font=font(245, True), fill=rgba(color, int(75 * title_amount)))
            for line_index, line in enumerate(wrap(title, 34)[:2]):
                draw.text((640, 46 + line_index * 51), line, font=font(43, False), fill=rgba(INK, int(255 * title_amount)), anchor="ma")
            draw.line((510, 146, 770, 146), fill=rgba(color, int(210 * title_amount)), width=5)
        elif construction == "object-hero":
            draw.text((640, 45), f"{chapter:02d} / VISUAL EXPLANATION", font=font(16, True), fill=rgba(color, int(230 * title_amount)), anchor="ma")
            for line_index, line in enumerate(wrap(title, 38)[:2]):
                draw.text((640, 77 + line_index * 46), line, font=font(39, False), fill=rgba(INK, int(255 * title_amount)), anchor="ma")
        elif construction == "cold-open":
            draw.line((560, 48, 1210 * title_amount, 48), fill=rgba(color, int(220 * title_amount)), width=8)
            for line_index, line in enumerate(wrap(title, 28)[:3]):
                draw.text((1195, 72 + line_index * 45), line, font=font(38, False), fill=rgba(INK, int(255 * title_amount)), anchor="ra")
        else:
            draw.rounded_rectangle((42, 34, 1238 * title_amount, 142), radius=18, fill=rgba(color, int(225 * title_amount)))
            draw.text((78, 56), f"NOTE {chapter:02d}", font=font(17, True), fill=rgba(PAPER, int(245 * title_amount)))
            for line_index, line in enumerate(wrap(title, 38)[:2]):
                draw.text((230, 52 + line_index * 42), line, font=font(36, False), fill=rgba(INK, int(255 * title_amount)))
    elif composition == "chapter-card":
        color = accents[0]
        chapter = int(illustration.get("chapterNumber") or 1)
        if layout_variant == 0:
            panel = (34, 72, 34 + (515 - 34) * title_amount, 648)
            number_xy, number_size = (68, 130), 214
            section_xy = (76, 390)
            pill = (335, 248, 985, 474)
            title_xy, title_width = (390, 292), 22
        elif layout_variant == 1:
            panel = (1246 - (1246 - 765) * title_amount, 72, 1246, 648)
            number_xy, number_size = (958, 130), 214
            section_xy = (982, 390)
            pill = (210, 92, 865, 302)
            title_xy, title_width = (265, 132), 22
        elif layout_variant == 2:
            panel = (32, 42, 1248, 42 + 168 * title_amount)
            number_xy, number_size = (62, 42), 126
            section_xy = (78, 163)
            pill = (225, 68, 1055, 192)
            title_xy, title_width = (285, 93), 34
        else:
            panel = (32, 678 - 168 * title_amount, 1248, 678)
            number_xy, number_size = (62, 510), 126
            section_xy = (78, 628)
            pill = (225, 530, 1055, 660)
            title_xy, title_width = (285, 555), 34
        draw.rounded_rectangle(panel, radius=22, fill=rgba(color, int(235 * title_amount)))
        draw.text(
            number_xy, str(chapter),
            font=font(number_size, True),
            fill=rgba(PAPER, int(250 * title_amount)),
            stroke_width=3,
            stroke_fill=rgba(INK, int(230 * title_amount)),
        )
        draw.text(section_xy, f"SECTION {chapter:02d}", font=font(18, True), fill=rgba(INK, int(215 * title_amount)))
        draw.rounded_rectangle(
            pill,
            radius=62 if layout_variant > 1 else 104,
            fill=rgba(PAPER, int(250 * title_amount)),
            outline=rgba(INK, int(170 * title_amount)),
            width=2,
        )
        for line_index, line in enumerate(wrap(title, title_width)[:3]):
            draw.text(
                (title_xy[0], title_xy[1] + line_index * (49 if layout_variant > 1 else 55)),
                line,
                font=font(42 if layout_variant > 1 else (46 if line_index == 0 else 39), False),
                fill=rgba(INK, int(255 * title_amount)),
            )
    elif composition in {"portrait", "closing", "hero"}:
        lines = wrap(title, 30)[:2]
        for line_index, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font(48 if line_index == 0 else 38, False))
            x = (WIDTH - (bbox[2] - bbox[0])) / 2
            draw.text((x, 44 + line_index * 52), line, font=font(48 if line_index == 0 else 38, False), fill=rgba(INK, int(255 * title_amount)))
        draw.line((540, 152, 740, 152), fill=rgba(accents[0], int(210 * title_amount)), width=4)
    else:
        x = 54
        for line_index, line in enumerate(wrap(title, 38)[:2]):
            draw.text((x, 38 + line_index * 45), line, font=font(39 if line_index == 0 else 33, False), fill=rgba(INK, int(255 * title_amount)))
        draw.line((x, 132, x + 205 * title_amount, 132), fill=rgba(accents[0], int(210 * title_amount)), width=4)
    return image.convert("RGB")

def render_visual_grammar(scene: dict[str, Any], frame: int, fps: int, palette: dict[str, Any], background: Image.Image) -> Image.Image:
    plan = scene["motionPlan"]
    grammar = plan.get("visualGrammar") or {}
    duration = max(1, math.ceil(float(scene.get("durationSeconds") or 1) * fps))
    image = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    accents = palette.get("accents") or DEFAULT_ACCENTS
    seed = stable_seed(str(grammar.get("fingerprint") or plan.get("signature") or scene.get("title")))
    objects, actions, amounts = _semantic_amounts(scene, frame, duration)
    marks = list(grammar.get("marks") or ["circle", "arrow", "label"])
    primary = str((grammar.get("operators") or ["focus"])[0])
    positions = _grammar_points(primary, max(len(objects), len(marks)), seed)
    global_amount = max(amounts or [progress(frame, duration * .05, duration * .3)])

    # Atmosphere is generated from the document fingerprint and art direction.
    for index, atmosphere in enumerate(grammar.get("atmosphere") or []):
        color = accents[index % len(accents)]
        phase = progress(frame, duration * (.02 + index * .02), duration * (.25 + index * .04))
        if atmosphere == "ghost-type":
            word = str(grammar.get("metaphor") or scene.get("title") or "IDEA").split()[0].upper()
            draw.text((WIDTH - 30, HEIGHT - 75 - index * 65), word, font=font(115, True), fill=rgba(color, int(24 * phase)), anchor="rs")
        elif atmosphere == "field-dots":
            for dot in range(18):
                x = 70 + ((seed >> (dot % 16)) + dot * 83) % 1140
                y = 80 + ((seed >> ((dot + 3) % 16)) + dot * 47) % 560
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=rgba(color, int(70 * phase)))
        elif atmosphere == "contour-lines":
            for offset in range(3):
                draw.arc((650 - offset * 90, 80 + offset * 25, 1310 + offset * 70, 700 - offset * 20), 80, 290 * phase, fill=rgba(color, int(65 * phase)), width=2)
        elif atmosphere == "registration-lines":
            draw.line((38, 70 + index * 22, 38 + 300 * phase, 70 + index * 22), fill=rgba(color, int(110 * phase)), width=2)
            draw.line((WIDTH - 38, HEIGHT - 70 - index * 22, WIDTH - 38 - 300 * phase, HEIGHT - 70 - index * 22), fill=rgba(color, int(110 * phase)), width=2)
        elif atmosphere == "moving-rule":
            y = 180 + index * 100
            draw.line((0, y, WIDTH * phase, y), fill=rgba(color, int(65 * phase)), width=3)

    # Title construction changes with the spatial operator instead of using one universal header.
    title_amount = progress(frame, duration * .02, duration * .13)
    title = str(scene.get("title") or "Video explanation")
    if primary in {"split", "mirror", "balance", "before-after", "diverge"}:
        _semantic_title(draw, scene, title_amount, accents[0], center=True, y=35, size=42)
    elif primary in {"orbit", "loop", "ring", "radial-flow", "spiral"}:
        for i, line in enumerate(wrap(title, 26)[:3]):
            draw.text((75, 135 + i * 55), line, font=font(50, True), fill=rgba(INK, int(255 * title_amount)))
        draw.text((78, 315), str(grammar.get("metaphor") or "")[:44], font=font(18), fill=rgba(accents[0], int(230 * title_amount)))
    elif primary in {"scale", "accumulate", "rank", "plot", "radial-measure"}:
        draw.text((70, 50), title, font=font(43, True), fill=rgba(INK, int(255 * title_amount)))
        draw.line((70, 112, WIDTH - 70, 112), fill=rgba(accents[0], int(210 * title_amount)), width=4)
    else:
        _semantic_title(draw, scene, title_amount, accents[0], y=42, size=44)

    # Relations are marks too: draw only when the chosen operator implies them.
    connective = primary in {"path", "step", "cascade", "track", "route", "tree", "branch", "flow", "cluster", "constellation"}
    if connective:
        for index in range(min(len(positions) - 1, max(0, len(objects) - 1))):
            edge_amount = amounts[min(index + 1, len(amounts) - 1)] if amounts else global_amount
            _draw_arrow(draw, positions[index], positions[index + 1], edge_amount, accents[(index + 1) % len(accents)], 4 + index % 3)

    metric = str(grammar.get("metric") or "")
    count = max(len(objects), min(len(marks), 7))
    for index in range(count):
        item = objects[index % len(objects)] if objects else {"label": title, "glyph": "bulb"}
        mark = marks[index % len(marks)]
        x, y = positions[index]
        amount = amounts[index % len(amounts)] if amounts else global_amount
        verb = str((grammar.get("motionVerbs") or ["reveals"])[index % len(grammar.get("motionVerbs") or ["reveals"])])
        if verb in {"travels", "routes", "crosses", "hands-off"}:
            x -= (1 - amount) * (120 if index % 2 == 0 else -120)
        elif verb in {"grows", "fills", "expands", "assembles"}:
            y += (1 - amount) * 55
        elif verb in {"orbits", "circulates", "loops"}:
            x += math.cos(amount * math.pi * 2) * (1 - amount) * 60
            y += math.sin(amount * math.pi * 2) * (1 - amount) * 60
        color = accents[(seed + index * 3) % len(accents)]
        _draw_grammar_mark(draw, mark, item, x, y, 55 + (seed + index * 17) % 34, amount, color, metric if index == 0 else "")

    # A small semantic caption makes the metaphor inspectable without imposing a fixed footer UI.
    if str(grammar.get("metaphor") or "") and primary not in {"orbit", "loop", "ring", "radial-flow", "spiral"}:
        caption = str(grammar.get("metaphor"))[:70]
        draw.text((WIDTH - 55, HEIGHT - 32), caption, font=font(13, True), fill=rgba(MUTED, int(165 * global_amount)), anchor="rs")
    return image.convert("RGB")

def render_semantic_composition(scene: dict[str, Any], frame: int, fps: int, palette: dict[str, Any], background: Image.Image) -> Image.Image:
    plan = scene["motionPlan"]
    family = str(plan.get("compositionFamily") or "hero-path")
    duration = max(1, math.ceil(float(scene.get("durationSeconds") or 1) * fps))
    image = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    accents = palette.get("accents") or DEFAULT_ACCENTS
    accent = accents[stable_seed(str(plan.get("signature") or family)) % len(accents)]
    objects, actions, amounts = _semantic_amounts(scene, frame, duration)
    title_amount = progress(frame, duration * .015, duration * .11)
    global_amount = max(amounts or [progress(frame, duration * .08, duration * .35)])

    if family == "hero-path":
        _semantic_title(draw, scene, title_amount, accent, y=54, size=50)
        start, end = (150, 455), (1050, 420)
        path_amount = max(amounts[1:] or amounts or [global_amount])
        points = curve_points(start, end, -135, path_amount)
        if len(points) > 1:
            draw.line(points, fill=rgba(accent, 225), width=5, joint="curve")
            px, py = points[-1]
            draw.ellipse((px - 11, py - 11, px + 11, py + 11), fill=rgba(accent), outline=rgba(INK), width=2)
        first = objects[0] if objects else {"glyph": "bulb", "label": "Starting point"}
        last = objects[-1] if objects else {"glyph": "target", "label": "Outcome"}
        icon(draw, str(first.get("glyph") or "bulb"), (82, 386, 218, 522), accent, amounts[0] if amounts else global_amount)
        icon(draw, str(last.get("glyph") or "target"), (960, 315, 1145, 500), accents[2 % len(accents)], amounts[-1] if amounts else global_amount)
        for index, item in enumerate(objects[1:4]):
            amount = amounts[index + 1]
            x = 350 + index * 215
            y = 465 - (index % 2) * 72
            layer = _semantic_card(item, amount, accents[(index + 1) % len(accents)], 185, 82)
            _composite_at(image, layer, x - 95, y, amount, rise=16)

    elif family == "process-path":
        _semantic_title(draw, scene, title_amount, accent, y=46, size=46)
        items = objects[:4]
        positions = [(70, 285), (345, 415), (620, 285), (895, 415)]
        route_amount = max(amounts or [global_amount])
        route = [(x + 125, y + 58) for x, y in positions[:len(items)]]
        for index in range(max(0, len(route) - 1)):
            local = progress(route_amount, index / max(1, len(route) - 1), (index + 1) / max(1, len(route) - 1))
            pts = curve_points(route[index], route[index + 1], -48 if index % 2 == 0 else 48, local)
            if len(pts) > 1:
                draw.line(pts, fill=rgba(accents[index % len(accents)], 225), width=5)
        for index, item in enumerate(items):
            amount = amounts[index]
            x, y = positions[index]
            layer = _semantic_card(item, amount, accents[index % len(accents)], 245, 118, index + 1)
            _composite_at(image, layer, x, y, amount)

    elif family == "network-trace":
        _semantic_title(draw, scene, title_amount, accent, y=52, size=47)
        items = objects[:4]
        xs = [175, 485, 795, 1105][:len(items)]
        y = 405
        for index in range(max(0, len(items) - 1)):
            edge_amount = amounts[min(index + 1, len(amounts) - 1)] if amounts else global_amount
            points = curve_points((xs[index] + 60, y), (xs[index + 1] - 60, y), -45 if index % 2 == 0 else 45, edge_amount)
            if len(points) > 1:
                draw.line(points, fill=rgba(accents[(index + 1) % len(accents)]), width=5)
        for index, item in enumerate(items):
            amount = amounts[index]
            radius = 58 + int(8 * math.sin(amount * math.pi))
            x = xs[index]
            color = accents[index % len(accents)]
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(PAPER, int(245 * amount)), outline=rgba(color, int(255 * amount)), width=5)
            icon(draw, str(item.get("glyph") or "circle"), (x - 34, y - 34, x + 34, y + 34), color, amount)
            label = wrap(str(item.get("label") or "Node"), 16)[:2]
            for line_index, line in enumerate(label):
                box = draw.textbbox((0, 0), line, font=font(17, line_index == 0))
                draw.text((x - (box[2] - box[0]) / 2, y + 78 + line_index * 22), line, font=font(17, line_index == 0), fill=rgba(INK, int(255 * amount)))
            if index == len(items) - 1:
                ring = radius + int(26 * amount)
                draw.ellipse((x - ring, y - ring, x + ring, y + ring), outline=rgba(color, int(100 * amount)), width=3)

    elif family == "metric-focus":
        _semantic_title(draw, scene, title_amount, accent, y=45, size=43)
        source_text = " ".join([str(scene.get("body") or ""), *(str(item.get("label") or "") for item in objects)])
        match = re.search(r"\b\d+(?:[.,]\d+)?(?:%|x|×)?\b", source_text)
        metric = match.group(0) if match else str(max(3, len(objects)))
        metric_amount = amounts[0] if amounts else global_amount
        metric_size = 150 if len(metric) <= 4 else 116
        draw.text((78, 276 + (1 - metric_amount) * 30), metric, font=font(metric_size, True), fill=rgba(accent, int(255 * metric_amount)))
        draw.text((86, 455), str((objects[0] if objects else {}).get("label") or "key result"), font=font(25, True), fill=rgba(INK, int(255 * metric_amount)))
        cx, cy = 900, 405
        ring_amount = max(amounts[1:] or [global_amount])
        for ring_index in range(3):
            radius = 72 + ring_index * 54
            draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), -90, -90 + 350 * ring_amount, fill=rgba(accents[(ring_index + 1) % len(accents)], 210), width=7 - ring_index)
        target = objects[-1] if objects else {"glyph": "target"}
        icon(draw, str(target.get("glyph") or "target"), (cx - 65, cy - 65, cx + 65, cy + 65), accents[2 % len(accents)], ring_amount)
        for index, item in enumerate(objects[1:4]):
            amount = amounts[index + 1]
            label = str(item.get("label") or "signal")
            draw.rounded_rectangle((735, 565 + index * 34, 1085, 593 + index * 34), radius=14, fill=rgba(accents[(index + 1) % len(accents)], int(55 * amount)), outline=rgba(accents[(index + 1) % len(accents)], int(180 * amount)), width=2)
            draw.text((752, 569 + index * 34), label[:32], font=font(15, True), fill=rgba(INK, int(255 * amount)))

    elif family == "split-contrast":
        _semantic_title(draw, scene, title_amount, accent, center=True, y=39, size=44)
        panel_amount = max(amounts or [global_amount])
        left_color = accents[0]
        right_color = accents[3 % len(accents)]
        draw.rounded_rectangle((60, 220, 610, 645), radius=28, fill=rgba(left_color, int(35 * panel_amount)), outline=rgba(left_color, int(220 * panel_amount)), width=4)
        draw.rounded_rectangle((670, 220, 1220, 645), radius=28, fill=rgba(right_color, int(35 * panel_amount)), outline=rgba(right_color, int(220 * panel_amount)), width=4)
        draw.text((92, 247), "BEFORE", font=font(19, True), fill=rgba(left_color, int(255 * panel_amount)))
        draw.text((702, 247), "AFTER", font=font(19, True), fill=rgba(right_color, int(255 * panel_amount)))
        midpoint = max(1, math.ceil(len(objects) / 2))
        for index, item in enumerate(objects):
            right_side = index >= midpoint
            local_index = index - midpoint if right_side else index
            amount = amounts[index]
            x = 700 if right_side else 90
            y = 315 + local_index * 115
            layer = _semantic_card(item, amount, right_color if right_side else left_color, 470, 82)
            _composite_at(image, layer, x, y, amount, rise=12)
        arrow_amount = amounts[midpoint] if len(amounts) > midpoint else panel_amount
        draw.line((615, 430, 660, 430), fill=rgba(INK, int(255 * arrow_amount)), width=5)
        draw.polygon([(660, 430), (645, 420), (645, 440)], fill=rgba(INK, int(255 * arrow_amount)))

    elif family == "timeline-track":
        _semantic_title(draw, scene, title_amount, accent, y=48, size=46)
        items = objects[:5]
        y = 410
        xs = [130 + index * (1020 / max(1, len(items) - 1)) for index in range(len(items))]
        track_amount = max(amounts or [global_amount])
        draw.line((130, y, 130 + 1020 * track_amount, y), fill=rgba(accent, 220), width=7)
        for index, item in enumerate(items):
            amount = amounts[index]
            x = xs[index]
            color = accents[index % len(accents)]
            draw.ellipse((x - 23, y - 23, x + 23, y + 23), fill=rgba(color, int(255 * amount)), outline=rgba(PAPER, int(255 * amount)), width=5)
            draw.text((x, y), str(index + 1), font=font(17, True), fill=rgba(PAPER, int(255 * amount)), anchor="mm")
            label = wrap(str(item.get("label") or f"Step {index + 1}"), 18)[:3]
            label_y = y - 105 if index % 2 == 0 else y + 48
            for line_index, line in enumerate(label):
                box = draw.textbbox((0, 0), line, font=font(17, line_index == 0))
                draw.text((x - (box[2] - box[0]) / 2, label_y + line_index * 22), line, font=font(17, line_index == 0), fill=rgba(INK, int(255 * amount)))

    elif family == "quote-focus":
        quote_amount = max(title_amount, amounts[0] if amounts else global_amount)
        draw.text((85, 90), "“", font=font(210, True), fill=rgba(accent, int(90 * quote_amount)))
        _semantic_title(draw, scene, quote_amount, accent, center=True, y=235, size=58)
        if objects:
            label = str(objects[-1].get("label") or "")
            box = draw.textbbox((0, 0), label, font=font(20, False))
            draw.text(((WIDTH - (box[2] - box[0])) / 2, 565), label, font=font(20), fill=rgba(MUTED, int(255 * quote_amount)))

    else:  # synthesis
        _semantic_title(draw, scene, title_amount, accent, y=48, size=46)
        items = objects[:3]
        for index, item in enumerate(items):
            amount = amounts[index]
            layer = _semantic_card(item, amount, accents[index % len(accents)], 610, 102, index + 1)
            _composite_at(image, layer, 70, 250 + index * 128, amount)
        outcome_amount = amounts[-1] if amounts else global_amount
        cx, cy = 1010, 425
        draw.ellipse((cx - 112, cy - 112, cx + 112, cy + 112), fill=rgba(accent, int(42 * outcome_amount)), outline=rgba(accent, int(235 * outcome_amount)), width=6)
        target = objects[-1] if objects else {"glyph": "shield"}
        icon(draw, str(target.get("glyph") or "shield"), (cx - 65, cy - 65, cx + 65, cy + 65), accent, outcome_amount)
        draw.line((955, 430, 995, 470, 1075, 360), fill=rgba(accent, int(255 * outcome_amount)), width=12, joint="curve")

    footer = f"{family.replace('-', ' ').upper()}  ·  {str(plan.get('semanticMode') or 'concept').replace('-', ' ').upper()}"
    draw.text((WIDTH - 350, HEIGHT - 32), footer, font=font(12, True), fill=rgba(MUTED, 165))
    return image.convert("RGB")

def render_scene(scene: dict[str, Any], frame: int, fps: int, palette: dict[str, Any], background: Image.Image) -> Image.Image:
    plan = scene["motionPlan"]
    if plan.get("illustrationPlan"):
        return render_illustrated_scene(scene, frame, fps, palette, background)
    if plan.get("visualGrammar"):
        return render_visual_grammar(scene, frame, fps, palette, background)
    if plan.get("compositionFamily"):
        return render_semantic_composition(scene, frame, fps, palette, background)
    duration = max(1, math.ceil(float(scene.get("durationSeconds") or 1) * fps))
    image = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    actions = {action["targetId"]: action for action in plan.get("actions") or []}
    action_progress = [progress(frame, float(a["startRatio"]) * duration, float(a["endRatio"]) * duration) for a in plan.get("actions") or []]
    camera_t = sum(action_progress) / max(1, len(action_progress))
    direction = str(plan.get("camera", {}).get("direction") or "right")
    sign = -1 if direction in {"left", "up", "counterclockwise"} else 1
    camera_mode = str(plan.get("camera", {}).get("mode") or "push")
    camera_x = sign * camera_t * (20 if camera_mode in {"push", "track"} else 34 if camera_mode == "pan" else 8)
    camera_y = sign * camera_t * (18 if camera_mode == "tilt" else 7)
    positions: dict[str, tuple[float, float, float, float]] = {}
    for item in plan.get("objects") or []:
        action = actions.get(item["id"], {})
        amount = progress(frame, float(action.get("startRatio") or .04) * duration, float(action.get("endRatio") or .18) * duration)
        dx, dy, rotation, scale = movement(action, amount, stable_seed(item["id"] + plan["signature"]))
        x = float(item["x"]) * WIDTH + dx + camera_x
        y = float(item["y"]) * HEIGHT + dy + camera_y
        positions[item["id"]] = (x, y, amount, scale)
    accents = palette.get("accents") or DEFAULT_ACCENTS
    layout_name = str(plan.get("layout", {}).get("algorithm") or "")
    if re.search(r"orbit|rings|cycle|spiral|ripple|arena", layout_name) and plan.get("objects"):
        motif = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        motif_draw = ImageDraw.Draw(motif)
        icon(motif_draw, str(plan["objects"][0].get("glyph") or "bulb"), (20, 20, 220, 220), accents[2 % len(accents)], 1)
        motif.putalpha(motif.getchannel("A").point(lambda value: int(value * .075)))
        image.alpha_composite(motif, (WIDTH // 2 - 120, HEIGHT // 2 - 105))
    for index, edge in enumerate(plan.get("edges") or []):
        if edge["from"] not in positions or edge["to"] not in positions:
            continue
        action = (plan.get("actions") or [])[min(index + 1, len(plan.get("actions") or []) - 1)]
        amount = progress(frame, float(action["startRatio"]) * duration, float(action["endRatio"]) * duration)
        start = positions[edge["from"]][:2]; end = positions[edge["to"]][:2]
        points = curve_points(start, end, (stable_seed(edge["id"] + plan["signature"]) % 80) - 40, amount)
        if len(points) > 1:
            color = accents[int(edge.get("accent") or 0) % len(accents)]
            draw.line(points, fill=rgba(color), width=7 if edge.get("style") == "marker" else 4, joint="curve")
            if edge.get("style") == "double":
                draw.line([(x, y + 6) for x, y in points], fill=rgba(INK), width=2)
    style = str(plan.get("surfaceStyle") or "panel")
    for item in plan.get("objects") or []:
        action = actions.get(item["id"], {})
        x, y, amount, motion_scale = positions[item["id"]]
        layer = node_layer(item, action, amount, palette, style)
        total_scale = max(.15, float(item.get("scale") or 1) * motion_scale * .82)
        layer = layer.resize((max(1, int(layer.width * total_scale)), max(1, int(layer.height * total_scale))), Image.Resampling.LANCZOS)
        angle = float(item.get("rotation") or 0) + movement(action, amount, stable_seed(item["id"] + plan["signature"]))[2]
        layer = layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        if amount < .999:
            alpha = layer.getchannel("A").point(lambda value: int(value * amount))
            layer.putalpha(alpha)
        image.alpha_composite(layer, (int(x - layer.width / 2), int(y - layer.height / 2)))
    title_amount = progress(frame, duration * .015, duration * .1)
    title_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)); title_draw = ImageDraw.Draw(title_layer)
    placement = str(plan.get("titlePlacement") or "top-left")
    treatment = str(CURRENT_ART_DIRECTION.get("titleTreatment") or "editorial")
    right = placement.endswith("right"); side = placement.startswith("side")
    title_text = str(scene.get("title") or "Video explanation")
    if treatment == "giant-type":
        title_text = title_text.upper(); right = False; side = False; max_width = 1120; x = 42; y = 35; title_size = max(58, min(84, int(96 - len(title_text) * .35)))
    elif treatment == "noir":
        title_text = title_text.upper(); max_width = 760; x = WIDTH - 80 - max_width if right else 80; y = 55; title_size = max(45, min(66, int(76 - len(title_text) * .28)))
    elif treatment == "prompt":
        title_text = "> " + title_text.lower(); right = False; side = False; max_width = 1050; x = 55; y = 52; title_size = 42
    elif treatment == "technical":
        title_text = "FIG.  " + title_text.upper(); right = False; side = False; max_width = 1050; x = 70; y = 48; title_size = 42
    elif treatment == "masthead":
        title_text = title_text.upper(); right = False; side = False; max_width = 1050; x = 70; y = 45; title_size = 50
    elif treatment in {"serif", "playful", "cutout", "chalk"}:
        max_width = 850; x = WIDTH - 75 - max_width if right else 75; y = 55; title_size = max(44, min(62, int(72 - len(title_text) * .22)))
    else:
        max_width = 480 if side else 760; x = WIDTH - 80 - max_width if right else 80; y = 170 if side else 58; title_size = max(36, min(52, int(61 - len(title_text) * .25)))
    lines = wrap(title_text, 30 if side else 44)
    for index, line in enumerate(lines[:3]):
        bbox = title_draw.textbbox((0, 0), line, font=font(title_size, True)); tx = x + max_width - (bbox[2] - bbox[0]) if right else x
        title_draw.text((tx + (1 - title_amount) * (24 if right else -24), y + index * (title_size + 4)), line, font=font(title_size, True), fill=rgba(INK, int(255 * title_amount)))
    accent = accents[stable_seed(plan["signature"]) % len(accents)]
    underline_y = y + min(3, len(lines)) * (title_size + 4) + 8
    if right:
        title_draw.line((x + max_width - int(280 * title_amount), underline_y, x + max_width, underline_y - 5), fill=rgba(accent, int(255 * title_amount)), width=7)
    else:
        title_draw.line((x, underline_y, x + int(280 * title_amount), underline_y - 5), fill=rgba(accent, int(255 * title_amount)), width=7)
    image.alpha_composite(title_layer)
    footer = f"{str(CURRENT_ART_DIRECTION.get('name') or 'Adaptive Motion').upper()}  ·  {str(plan.get('semanticMode') or 'concept').replace('-', ' ').upper()}"
    draw.text((WIDTH - 370, HEIGHT - 35), footer, font=font(12, True), fill=rgba(MUTED, 190))
    return image.convert("RGB")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: render-vector-motion <manifest> <public-dir> <output-dir>")
    global PUBLIC_DIR
    manifest_path, public_dir, output_dir = map(Path, sys.argv[1:])
    PUBLIC_DIR = public_dir.resolve()
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); fps = int(manifest.get("fps") or 24)
    if int((manifest.get("motionSystem") or {}).get("version") or 0) >= 5:
        missing_explanations = [
            index + 1
            for index, scene in enumerate(manifest.get("scenes") or [])
            if not ((scene.get("motionPlan") or {}).get("explanationPlan") or {}).get("construction")
        ]
        if missing_explanations:
            raise RuntimeError(
                f"V5 scenes require explanation constructions; missing in scenes {missing_explanations}."
            )
    if int((manifest.get("motionSystem") or {}).get("version") or 0) >= 4:
        missing_assets = [
            str(prop.get("id") or "unknown")
            for scene in manifest.get("scenes") or []
            for prop in ((scene.get("motionPlan") or {}).get("illustrationPlan") or {}).get("props") or []
            if not prop.get("assetFile")
        ]
        if missing_assets:
            raise RuntimeError(
                "Notebook editorial render refused primitive fallback; missing assets for: "
                + ", ".join(missing_assets[:12])
            )
    sample_step = 2 if fps >= 24 else 1
    packed_fps = fps / sample_step
    art_direction = manifest.get("artDirection") or {}
    palette = art_direction.get("palette") or (manifest.get("visualLanguage") or {}).get("palette") or {"background": PAPER, "text": INK, "muted": MUTED, "accents": DEFAULT_ACCENTS}
    configure_art_direction(art_direction, palette)
    background = paper_background(palette)
    tasks: list[tuple[dict[str, Any], int, Path]] = []; results = []; packed_from = 0; full_frames = 0
    for scene_index, scene in enumerate(manifest.get("scenes") or []):
        motion = scene.get("motionPlan")
        if not motion:
            raise RuntimeError(f"Scene {scene_index + 1} has no semantic motion plan.")
        scene_frames = max(1, math.ceil(float(scene.get("durationSeconds") or 1) * fps)); scene_dir = output_dir / f"scene-{scene_index + 1:03d}"; scene_dir.mkdir(parents=True, exist_ok=True)
        requested = motion.get("renderWindows") or [{"startRatio": 0, "endRatio": min(.25, 48 / scene_frames)}]
        windows = sorted((max(0, min(scene_frames - 1, math.floor(float(w.get("startRatio") or 0) * scene_frames))), max(0, min(scene_frames - 1, math.ceil(float(w.get("endRatio") or .1) * scene_frames)))) for w in requested)
        normalized: list[list[int]] = []
        for start, end in windows:
            if normalized and start <= normalized[-1][1] + 1:
                normalized[-1][1] = max(normalized[-1][1], end)
            else:
                normalized.append([start, max(start, end)])
        still_frames = [0, *(end for _, end in normalized)]; stills = []
        for still_index, local_frame in enumerate(still_frames):
            destination = scene_dir / f"hold-{still_index}.jpg"; tasks.append((scene, local_frame, destination)); stills.append({"localFrame": local_frame, "path": str(destination)})
        rendered_windows = []
        for start, end in normalized:
            packed_start = packed_from
            sampled_frames = list(range(start, end + 1, sample_step))
            if sampled_frames[-1] != end:
                sampled_frames.append(end)
            for local_frame in sampled_frames:
                destination = output_dir / f"packed-{packed_from:08d}.jpg"; tasks.append((scene, local_frame, destination)); packed_from += 1
            rendered_windows.append({"startFrame": start, "endFrame": end, "packedStartFrame": packed_start, "packedFrameCount": len(sampled_frames), "path": str(output_dir / "packed-motion.mp4")})
        results.append({"sceneIndex": scene_index, "durationSeconds": float(scene.get("durationSeconds") or 1), "durationFrames": scene_frames, "audioFile": scene.get("audioFile"), "motionPlan": motion, "windows": rendered_windows, "stills": stills})
        full_frames += scene_frames
    render_started = time.perf_counter()
    def render_task(task: tuple[dict[str, Any], int, Path]) -> None:
        scene, local_frame, destination = task
        render_scene(scene, local_frame, fps, palette, background).save(destination, "JPEG", quality=92, optimize=False, subsampling=0)
    workers = min(8, max(2, (os.cpu_count() or 4) - 2))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(render_task, tasks))
    vector_seconds = time.perf_counter() - render_started
    packed_path = output_dir / "packed-motion.mp4"
    encode_started = time.perf_counter()
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(packed_fps), "-i", str(output_dir / "packed-%08d.jpg"), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(packed_path)]
    encoded = subprocess.run(command, capture_output=True, text=True)
    if encoded.returncode != 0:
        raise RuntimeError(f"Packed motion encoding failed: {encoded.stderr[-1600:]}")
    report = {"fps": fps, "packedFps": packed_fps, "motionSampleStep": sample_step, "renderer": "editorial-storyboard-v5", "packedMotionFrames": packed_from, "equivalentFullFrames": full_frames, "motionFraction": packed_from / max(1, full_frames), "timings": {"vectorFrameSeconds": vector_seconds, "packedEncodeSeconds": time.perf_counter() - encode_started}, "scenes": results}
    (output_dir / "motion-islands.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
