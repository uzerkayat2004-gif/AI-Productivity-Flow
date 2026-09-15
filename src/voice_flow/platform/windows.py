"""Windows platform backend.

This wraps the Win32 behaviour Voice Flow has always used. It deliberately
**delegates to the existing, battle-tested modules** (``injector``,
``context_capture``, ``tts_engine``) rather than reimplementing clipboard and
paste logic, because that code already handles the awkward parts: clipboard
open retries, modifier-key release, synthetic-input marking, and per-app paste
quirks. Reimplementing it here would risk silent behaviour drift on the
platform that currently works.

Every delegation is a **lazy import inside the method**. Two reasons:

1. ``voice_flow.injector`` imports a large slice of the app. Importing it at
   module scope would create import cycles the moment the app itself starts
   depending on ``voice_flow.platform``.
2. It keeps ``import voice_flow.platform.windows`` cheap and side-effect free.

Where a dependency is unavailable, each method falls back to a self-contained
``ctypes`` implementation and finally to a safe ``False``/``""``. Nothing here
raises for "unsupported".
"""

from __future__ import annotations

import logging
import os
import sys

from voice_flow.platform.base import PermissionReport, PermissionState
from voice_flow.platform.wincompat import IS_WINDOWS, windll

log = logging.getLogger(__name__)

# HKCU\Software\Microsoft\Windows\CurrentVersion\Run — the single autostart
# mechanism the installer standardised on (see installer.py).
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "VoiceFlow"

# Clipboard formats / limits
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


class WindowsBackend:
    """Win32 implementation of :class:`~voice_flow.platform.base.PlatformBackend`."""

    name = "windows"

    # ------------------------------------------------------------------
    # clipboard
    # ------------------------------------------------------------------
    def copy_to_clipboard(self, text: str) -> bool:
        try:
            from voice_flow.injector import _safe_copy_to_clipboard

            return bool(_safe_copy_to_clipboard(text))
        except Exception as exc:
            log.debug("[WIN] injector clipboard unavailable (%s); using fallback", exc)
        return self._copy_fallback(text)

    def _copy_fallback(self, text: str) -> bool:
        """Minimal OpenClipboard/SetClipboardData path used only if injector fails."""
        if not IS_WINDOWS:
            return False
        try:
            import ctypes

            user32 = windll.user32
            kernel32 = windll.kernel32
            if not user32.OpenClipboard(None):
                return False
            try:
                user32.EmptyClipboard()
                buf = ctypes.create_unicode_buffer(text)
                size = ctypes.sizeof(buf)
                handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, size)
                if not handle:
                    return False
                lock = kernel32.GlobalLock(handle)
                if not lock:
                    kernel32.GlobalFree(handle)
                    return False
                try:
                    ctypes.memmove(lock, buf, size)
                finally:
                    kernel32.GlobalUnlock(handle)
                if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
                    kernel32.GlobalFree(handle)
                    return False
                return True
            finally:
                user32.CloseClipboard()
        except Exception as exc:
            log.debug("[WIN] clipboard fallback failed: %s", exc)
            return False

    def read_clipboard(self) -> str:
        try:
            from voice_flow.injector import _safe_paste_from_clipboard

            return _safe_paste_from_clipboard() or ""
        except Exception as exc:
            log.debug("[WIN] clipboard read unavailable: %s", exc)
        try:
            import pyperclip

            return pyperclip.paste() or ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # synthetic input
    # ------------------------------------------------------------------
    def send_paste(self) -> bool:
        try:
            from voice_flow.injector import _send_win32_ctrl_v

            _send_win32_ctrl_v()
            return True
        except Exception as exc:
            log.debug("[WIN] send_paste failed: %s", exc)
            return False

    def send_copy(self) -> bool:
        try:
            from voice_flow.injector import _send_win32_ctrl_c

            _send_win32_ctrl_c()
            return True
        except Exception as exc:
            log.debug("[WIN] send_copy failed: %s", exc)
            return False

    def send_enter(self) -> bool:
        try:
            from voice_flow.injector import _send_win32_enter

            _send_win32_enter()
            return True
        except Exception as exc:
            log.debug("[WIN] send_enter failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # window / focus
    # ------------------------------------------------------------------
    def active_window_title(self) -> str:
        try:
            from voice_flow.injector import get_active_window_title

            return get_active_window_title() or ""
        except Exception as exc:
            log.debug("[WIN] active_window_title failed: %s", exc)
            return ""

    def active_app_name(self) -> str:
        if not IS_WINDOWS:
            return ""
        try:
            import ctypes

            hwnd = windll.user32.GetForegroundWindow()
            if not hwnd:
                return ""
            pid = ctypes.c_ulong(0)
            windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return ""
            from voice_flow.injector import _get_process_name_safe

            return _get_process_name_safe(pid.value) or ""
        except Exception as exc:
            log.debug("[WIN] active_app_name failed: %s", exc)
            return ""

    def is_own_window_focused(self) -> bool:
        if not IS_WINDOWS:
            return False
        try:
            from voice_flow.injector import is_internal_window

            hwnd = windll.user32.GetForegroundWindow()
            return bool(is_internal_window(hwnd))
        except Exception as exc:
            log.debug("[WIN] is_own_window_focused failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------
    def get_selected_text(self) -> str:
        try:
            from voice_flow.injector import ClipboardInjector

            return ClipboardInjector().get_selected_text() or ""
        except Exception as exc:
            log.debug("[WIN] get_selected_text failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # feedback
    # ------------------------------------------------------------------
    def beep(self, kind: str = "start") -> bool:
        if not IS_WINDOWS:
            return False
        if os.environ.get("CI"):
            return True
        try:
            import winsound

            freq = {"start": 880, "stop": 660, "error": 330}.get(kind, 880)
            winsound.Beep(freq, 80)
            return True
        except Exception as exc:
            log.debug("[WIN] beep failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # autostart
    # ------------------------------------------------------------------
    def get_launch_at_login(self) -> bool:
        if not IS_WINDOWS:
            return False
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, _RUN_VALUE)
                return bool(value)
        except FileNotFoundError:
            return False
        except Exception as exc:
            log.debug("[WIN] get_launch_at_login failed: %s", exc)
            return False

    def set_launch_at_login(self, enabled: bool, command: str | None = None) -> bool:
        if not IS_WINDOWS:
            return False
        try:
            import winreg

            if not enabled:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
                    ) as key:
                        winreg.DeleteValue(key, _RUN_VALUE)
                except FileNotFoundError:
                    pass
                return True

            cmd = command or f'"{sys.executable}" -m voice_flow.main'
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, cmd)
            return True
        except Exception as exc:
            log.debug("[WIN] set_launch_at_login failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # permissions
    # ------------------------------------------------------------------
    def permission_report(self) -> PermissionReport:
        """Windows needs no up-front grants for Voice Flow's core features.

        Microphone *can* be blocked by the Windows privacy setting, so it is
        reported as an advisory (non-required, indeterminate) entry rather than
        pretending it is always granted.
        """
        mic_granted, mic_known = self._microphone_allowed()
        return PermissionReport(
            platform="windows",
            states=(
                PermissionState(
                    key="microphone",
                    label="Microphone",
                    granted=mic_granted,
                    required=False,
                    description=(
                        "Windows grants microphone access by default. If dictation "
                        "records silence, check Privacy & security > Microphone."
                    ),
                    settings_url="ms-settings:privacy-microphone",
                    indeterminate=not mic_known,
                ),
            ),
        )

    def _microphone_allowed(self) -> tuple[bool, bool]:
        """Return ``(granted, known)`` from the Windows privacy registry key."""
        if not IS_WINDOWS:
            return (False, False)
        try:
            import winreg

            path = (
                r"Software\Microsoft\Windows\CurrentVersion"
                r"\CapabilityAccessManager\ConsentStore\microphone"
            )
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, "Value")
                return (str(value).lower() == "allow", True)
        except Exception:
            return (True, False)

    def open_permission_settings(self, key: str) -> bool:
        if not IS_WINDOWS:
            return False
        target = {
            "microphone": "ms-settings:privacy-microphone",
        }.get(key)
        if not target:
            return False
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        except Exception as exc:
            log.debug("[WIN] open_permission_settings failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # tts
    # ------------------------------------------------------------------
    def system_tts_to_file(self, text: str, out_path: str, voice: str | None = None) -> bool:
        """Synthesize via SAPI. Delegates to tts_engine when it exposes a helper."""
        if not IS_WINDOWS or os.environ.get("CI"):
            return False
        try:
            import win32com.client  # type: ignore[import-not-found]

            engine = win32com.client.Dispatch("SAPI.SpVoice")
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            if voice:
                for candidate in engine.GetVoices():
                    if voice.lower() in candidate.GetDescription().lower():
                        engine.Voice = candidate
                        break
            stream.Open(out_path, 3)  # SSFMCreateForWrite
            engine.AudioOutputStream = stream
            engine.Speak(text)
            stream.Close()
            return os.path.exists(out_path)
        except Exception as exc:
            log.debug("[WIN] system_tts_to_file failed: %s", exc)
            return False

    def system_tts_voices(self) -> list[str]:
        if not IS_WINDOWS:
            return []
        # Query Windows Registry for SAPI voices first. This is fast, has zero COM
        # overhead, and works in headless CI runners without audio devices.
        try:
            import winreg

            voices: list[str] = []
            roots = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Speech\Voices\Tokens"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
            ]
            seen: set[str] = set()
            for root, base_path in roots:
                try:
                    with winreg.OpenKey(root, base_path) as k:
                        count, _, _ = winreg.QueryInfoKey(k)
                        for i in range(count):
                            subkey_name = winreg.EnumKey(k, i)
                            if subkey_name in seen:
                                continue
                            seen.add(subkey_name)
                            try:
                                with winreg.OpenKey(k, subkey_name) as sk:
                                    desc, _ = winreg.QueryValueEx(sk, "")
                                    if desc and str(desc) not in voices:
                                        voices.append(str(desc))
                            except Exception:
                                pass
                except Exception:
                    pass
            if voices:
                return voices
        except Exception:
            pass

        # If registry returned nothing and not in CI, fallback to COM Dispatch
        if not os.environ.get("CI"):
            try:
                import win32com.client  # type: ignore[import-not-found]

                engine = win32com.client.Dispatch("SAPI.SpVoice")
                return [v.GetDescription() for v in engine.GetVoices()]
            except Exception as exc:
                log.debug("[WIN] system_tts_voices COM fallback failed: %s", exc)
        return []


__all__ = ["WindowsBackend"]
