"""Uninstaller helper: remove the app's HKCU autostart registration.

Run by the installer's uninstall step (``python -m voice_flow.release_cleanup_autorun``).
Only the VoiceFlow Run value is touched; user data under ~/.voice_flow is
preserved by design.
"""

from __future__ import annotations

import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def main() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "VoiceFlow")
    except FileNotFoundError:
        pass
    except OSError:
        pass


if __name__ == "__main__":
    main()
