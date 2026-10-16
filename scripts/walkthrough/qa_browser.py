"""Pick the Playwright engine for the DOM checks.

Playwright's WebKit hangs in new_page() on the GitHub macOS 14 image (22-33 min:
runs 38934873990, 38967036385, 38974404603, 38974393518). The checks only need a
browser engine against 127.0.0.1:8991, so macOS 14 uses Chromium (installed on
first use). Elsewhere WebKit, retried once, then Chromium.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import time

_installed = False


def use_chromium() -> bool:
    return platform.mac_ver()[0].split(".")[0] == "14" or os.environ.get("QA_BROWSER") == "chromium"


def _chromium(pw):
    global _installed
    if not _installed:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        _installed = True
    return pw.chromium.launch(timeout=90000)


def launch(pw):
    if use_chromium():
        return _chromium(pw)
    for _ in range(2):
        try:
            return pw.webkit.launch(timeout=90000)
        except Exception:
            time.sleep(5)
    return _chromium(pw)
