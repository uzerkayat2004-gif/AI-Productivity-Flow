"""Uninstaller helper: remove every Voice Flow autostart registration.

Run by the installer's uninstall step (``python -m voice_flow.release_cleanup_autorun``).
Removes all legacy Run-value names and any Startup-folder shortcut so an
uninstall/upgrade cannot leave a second boot mechanism behind (a second boot
mechanism launches two app instances at logon). User data under ~/.voice_flow
is preserved by design.
"""

from __future__ import annotations

import os
from pathlib import Path
try:
    import winreg
except ImportError:
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAMES = ("VoiceFlow", "Voice Flow", "AI Productivity Flow")
STARTUP_LNK_NAMES = ("Voice Flow.lnk", "VoiceFlow.lnk", "voiceFlow.lnk", "AI Productivity Flow.lnk")


def remove_registry_autorun() -> int:
    """Delete all known Voice Flow value names from the HKCU Run key."""
    if winreg is None:
        return 0
    removed = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in RUN_VALUE_NAMES:
                try:
                    winreg.DeleteValue(key, name)
                    removed += 1
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
    except (FileNotFoundError, OSError):
        pass
    return removed


def remove_startup_folder_shortcuts() -> int:
    """Delete all known Voice Flow shortcut names from the Startup folder."""
    removed = 0
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return 0
    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    for name in STARTUP_LNK_NAMES:
        shortcut = startup_dir / name
        if not shortcut.exists():
            continue
        try:
            shortcut.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def main() -> None:
    remove_registry_autorun()
    remove_startup_folder_shortcuts()


if __name__ == "__main__":
    main()
