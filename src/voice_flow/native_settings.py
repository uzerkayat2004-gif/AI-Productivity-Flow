"""Small, testable Windows integrations used by the desktop shell.

Nothing in this module changes the machine at import time. Registry access is
kept here so callers can report an honest result when it is unavailable.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "VoiceFlow"


@dataclass(frozen=True)
class NativeResult:
    applied: bool
    error: str | None = None
    restart_required: bool = False


def _winreg(registry: Any | None = None) -> Any | None:
    if registry is not None:
        return registry
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def default_launch_command() -> str:
    """Use the silent launcher when it is available in the installed project."""
    vbs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "VoiceFlowLauncher.vbs"))
    if os.path.exists(vbs_path):
        return f'wscript.exe "{vbs_path}"'
    return f'"{sys.executable}" -m voice_flow.main'


def get_launch_at_login(registry: Any | None = None) -> NativeResult:
    reg = _winreg(registry)
    if reg is None:
        return NativeResult(False, "Windows launch-at-login is unavailable on this platform")
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            reg.QueryValueEx(key, RUN_VALUE)
        return NativeResult(True)
    except FileNotFoundError:
        return NativeResult(False)
    except OSError as exc:
        return NativeResult(False, f"Could not read Windows launch-at-login: {exc}")


def set_launch_at_login(enabled: bool, command: str | None = None, registry: Any | None = None) -> NativeResult:
    """Set only Voice Flow's HKCU startup value; never mutate it on import."""
    if not isinstance(enabled, bool):
        return NativeResult(False, "launch_at_login must be a boolean")
    reg = _winreg(registry)
    if reg is None:
        return NativeResult(False, "Windows launch-at-login is unavailable on this platform")
    try:
        access = getattr(reg, "KEY_SET_VALUE", reg.KEY_WRITE)
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, access) as key:
            if enabled:
                reg.SetValueEx(key, RUN_VALUE, 0, reg.REG_SZ, command or default_launch_command())
            else:
                try:
                    reg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return NativeResult(True)
    except OSError as exc:
        return NativeResult(False, f"Could not update Windows launch-at-login: {exc}")
