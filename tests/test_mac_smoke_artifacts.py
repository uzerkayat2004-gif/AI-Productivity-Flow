from __future__ import annotations

from PIL import Image, ImageDraw

from pathlib import Path

from scripts.check_mac_smoke_artifacts import (
    app_exited,
    is_mostly_blank,
    logs_mention_system_browser_fallback,
    logs_mention_win32_keyboard_hook,
    main,
    window_report_problem,
)


def test_white_image_is_mostly_blank():
    assert is_mostly_blank(Image.new("RGB", (200, 200), "white"))


def test_black_image_is_mostly_blank():
    assert is_mostly_blank(Image.new("RGB", (200, 200), "black"))


def test_colored_content_is_not_mostly_blank():
    image = Image.new("RGB", (200, 200), "#f7f0e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 60, 140, 90), fill="#f97316")
    draw.rectangle((60, 100, 135, 125), fill="#2563eb")
    draw.rectangle((70, 132, 150, 145), fill="#6d28d9")
    for x in range(65, 136, 12):
        draw.rectangle((x, 108, x + 5, 115), fill="#1c1917")
    assert not is_mostly_blank(image)


def test_win32_keyboard_hook_log_is_detected():
    assert logs_mention_win32_keyboard_hook("Win32 keyboard hook stopped")
    assert not logs_mention_win32_keyboard_hook("pynput listener started")


def _colorful_screenshot(path: Path) -> None:
    image = Image.new("RGB", (80, 80), "#f7f0e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 70, 36), fill="#f97316")
    draw.rectangle((8, 42, 60, 72), fill="#2563eb")
    image.save(path)


def _healthy_out(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    _colorful_screenshot(out / "screen-30s.png")
    (out / "alive.txt").write_text("5s: running\n60s: running\n", encoding="utf-8")
    (out / "windows.txt").write_text(
        "Finder: Desktop\nAI Productivity Flow: AI Productivity Flow\n",
        encoding="utf-8",
    )
    (out / "app-stdout.txt").write_text("ready\n", encoding="utf-8")
    (out / "app-stderr.txt").write_text("", encoding="utf-8")
    return out


def test_healthy_smoke_artifacts_pass(tmp_path: Path):
    out = _healthy_out(tmp_path)
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 0


def test_exited_app_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "alive.txt").write_text("5s: running\n15s: EXITED\n", encoding="utf-8")
    assert app_exited((out / "alive.txt").read_text(encoding="utf-8"))
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_safari_window_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "windows.txt").write_text("Safari: AI Productivity Flow\n", encoding="utf-8")
    assert window_report_problem((out / "windows.txt").read_text(encoding="utf-8"))
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_other_browser_window_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "windows.txt").write_text("Google Chrome: AI Productivity Flow\n", encoding="utf-8")
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_missing_app_window_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "windows.txt").write_text("Finder: Desktop\n", encoding="utf-8")
    assert window_report_problem((out / "windows.txt").read_text(encoding="utf-8")) == "no app window"
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_system_browser_fallback_log_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "gui_launcher.log").write_text(
        "Native window backend unavailable; using the system browser.\n",
        encoding="utf-8",
    )
    assert logs_mention_system_browser_fallback((out / "gui_launcher.log").read_text(encoding="utf-8"))
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1
