"""Uninstaller helper: remove every Voice Flow autostart registration.

Run by the installer's uninstall step (``python -m voice_flow.release_cleanup_autorun``).
Removes the current user's app-owned logon task, legacy Run-value names, and
Startup-folder shortcuts. User data under ~/.voice_flow is preserved by design.
"""

from __future__ import annotations

import os
from pathlib import Path

from voice_flow import windows_startup
try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAMES = ("VoiceFlow", "Voice Flow", "AI Productivity Flow")
STARTUP_LNK_NAMES = ("Voice Flow.lnk", "VoiceFlow.lnk", "voiceFlow.lnk", "AI Productivity Flow.lnk")


def remove_registry_autorun() -> tuple[int, bool]:
    """Delete all known Voice Flow value names from the HKCU Run key."""
    if winreg is None:
        return 0, False
    removed = 0
    success = True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in RUN_VALUE_NAMES:
                try:
                    winreg.DeleteValue(key, name)
                    removed += 1
                except FileNotFoundError:
                    pass
                except OSError:
                    success = False
    except FileNotFoundError:
        pass
    except OSError:
        success = False
    return removed, success


def remove_startup_folder_shortcuts() -> tuple[int, bool]:
    """Delete all known Voice Flow shortcut names from the Startup folder."""
    removed = 0
    success = True
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return 0, False
    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    for name in STARTUP_LNK_NAMES:
        shortcut = startup_dir / name
        if not shortcut.exists():
            continue
        try:
            shortcut.unlink()
            removed += 1
        except OSError:
            success = False
    return removed, success


def main() -> bool:
    task = windows_startup.unregister_task()
    registry_removed, registry_ok = remove_registry_autorun()
    shortcut_removed, shortcut_ok = remove_startup_folder_shortcuts()
    success = task.success and registry_ok and shortcut_ok
    message = (
        f"task={'removed' if task.success else 'failed'}, "
        f"Run values removed={registry_removed}, shortcuts removed={shortcut_removed}"
    )
    print(f"[{'OK' if success else 'ERROR'}] Auto-start cleanup: {message}")
    return success


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
