"""macOS platform backend.

Implements the Voice Flow platform contract using the ctypes bindings in
:mod:`voice_flow.platform.macos_native`, plus a small number of shell-outs to
tools that ship with every macOS install (``pbcopy``/``pbpaste``, ``say``,
``afplay``, ``open``).

Why shell-outs for the clipboard instead of ``NSPasteboard``?
``pbcopy``/``pbpaste`` are stable, need no permissions, handle UTF-8 correctly,
and avoid pulling PyObjC into the dependency tree. The cost is a ~10ms process
spawn, which is irrelevant next to the human-scale actions these serve.

Permission model (the part that differs most from Windows):

=================  ========  ==========================================
Permission         Required  How Voice Flow uses it
=================  ========  ==========================================
Microphone         yes       dictation / speech-to-text
Accessibility      yes       reading the user's text selection
Input Monitoring   yes       global hotkeys
=================  ========  ==========================================

macOS cannot grant these programmatically. The backend can only *detect* state
and *open* the right Settings pane; the user must flip the switch themselves.
That is why :meth:`MacOSBackend.permission_report` exists and why the first-run
onboarding screen is mandatory on this platform.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

from voice_flow.platform import macos_native as native
from voice_flow.platform.base import PermissionReport, PermissionState

log = logging.getLogger(__name__)

IS_MACOS = sys.platform == "darwin"

# x-apple.systempreferences: URLs for the three panes we care about.
_PANE = "x-apple.systempreferences:com.apple.preference.security"
_SETTINGS_URLS = {
    "microphone": f"{_PANE}?Privacy_Microphone",
    "accessibility": f"{_PANE}?Privacy_Accessibility",
    "input_monitoring": f"{_PANE}?Privacy_ListenEvent",
}

_LAUNCH_AGENT_LABEL = "com.voiceflow.app"


def _run(cmd: list[str], *, text_input: str | None = None, timeout: float = 5.0):
    """Run a short-lived helper process. Returns CompletedProcess or None."""
    try:
        return subprocess.run(
            cmd,
            input=text_input,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        log.debug("[MACOS] command %s failed: %s", cmd[:1], exc)
        return None


class MacOSBackend:
    """macOS implementation of the platform contract."""

    name = "macos"

    # ------------------------------------------------------------------
    # clipboard
    # ------------------------------------------------------------------
    def copy_to_clipboard(self, text: str) -> bool:
        if not IS_MACOS:
            return False
        result = _run(["pbcopy"], text_input=text)
        return bool(result and result.returncode == 0)

    def read_clipboard(self) -> str:
        if not IS_MACOS:
            return ""
        result = _run(["pbpaste"])
        if result and result.returncode == 0:
            return result.stdout or ""
        return ""

    # ------------------------------------------------------------------
    # synthetic input
    # ------------------------------------------------------------------
    def send_paste(self) -> bool:
        """Cmd+V. Requires Accessibility trust; returns False when untrusted."""
        return native.send_key_combo(native.KEY_V, native.kCGEventFlagMaskCommand)

    def send_copy(self) -> bool:
        return native.send_key_combo(native.KEY_C, native.kCGEventFlagMaskCommand)

    def send_enter(self) -> bool:
        return native.send_return_key()

    # ------------------------------------------------------------------
    # window / focus
    # ------------------------------------------------------------------
    def active_window_title(self) -> str:
        info = native.frontmost_window_owner()
        return str(info.get("title", "")) if info else ""

    def active_app_name(self) -> str:
        info = native.frontmost_window_owner()
        return str(info.get("app", "")) if info else ""

    def is_own_window_focused(self) -> bool:
        """True when the frontmost window belongs to this process.

        Compares the frontmost window's owner PID against our own, which is
        more reliable than matching on app name (the bundle name differs
        between a dev run and a packaged .app).
        """
        info = native.frontmost_window_owner()
        if not info:
            return False
        pid = info.get("pid")
        if isinstance(pid, int) and pid > 0:
            return pid == os.getpid()
        app = str(info.get("app", "")).lower()
        return "voice flow" in app or "voiceflow" in app or "python" in app

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------
    def get_selected_text(self) -> str:
        """Read the selection via the Accessibility API.

        Falls back to a clipboard round-trip (Cmd+C, read, restore) when the
        Accessibility query returns nothing — many Electron and Java apps do
        not expose ``AXSelectedText``. The original clipboard is restored so
        the user's copy buffer is not silently clobbered.
        """
        direct = native.focused_selected_text()
        if direct:
            return direct

        if not native.accessibility_trusted():
            return ""

        import time

        saved = self.read_clipboard()
        try:
            if not self.send_copy():
                return ""
            time.sleep(0.12)
            grabbed = self.read_clipboard()
            if grabbed and grabbed != saved:
                return grabbed
            return ""
        finally:
            if saved:
                self.copy_to_clipboard(saved)

    # ------------------------------------------------------------------
    # feedback
    # ------------------------------------------------------------------
    def beep(self, kind: str = "start") -> bool:
        if not IS_MACOS:
            return False
        sound = {
            "start": "/System/Library/Sounds/Tink.aiff",
            "stop": "/System/Library/Sounds/Pop.aiff",
            "error": "/System/Library/Sounds/Basso.aiff",
        }.get(kind, "/System/Library/Sounds/Tink.aiff")
        if not os.path.exists(sound):
            return False
        try:
            subprocess.Popen(
                ["afplay", sound],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as exc:
            log.debug("[MACOS] beep failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # autostart  (LaunchAgent plist — the macOS analogue of the HKCU Run key)
    # ------------------------------------------------------------------
    def _agent_path(self) -> str:
        return os.path.expanduser(
            f"~/Library/LaunchAgents/{_LAUNCH_AGENT_LABEL}.plist"
        )

    def get_launch_at_login(self) -> bool:
        return os.path.exists(self._agent_path())

    def set_launch_at_login(self, enabled: bool, command: str | None = None) -> bool:
        if not IS_MACOS:
            return False
        path = self._agent_path()
        try:
            if not enabled:
                if os.path.exists(path):
                    _run(["launchctl", "unload", path])
                    os.remove(path)
                return True

            os.makedirs(os.path.dirname(path), exist_ok=True)
            if command:
                args = command.split()
            else:
                args = [sys.executable, "-m", "voice_flow.main"]
            args_xml = "\n".join(f"        <string>{a}</string>" for a in args)
            plist = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n'
                "<dict>\n"
                "    <key>Label</key>\n"
                f"    <string>{_LAUNCH_AGENT_LABEL}</string>\n"
                "    <key>ProgramArguments</key>\n"
                "    <array>\n"
                f"{args_xml}\n"
                "    </array>\n"
                "    <key>RunAtLoad</key>\n"
                "    <true/>\n"
                "    <key>KeepAlive</key>\n"
                "    <false/>\n"
                "</dict>\n"
                "</plist>\n"
            )
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(plist)
            _run(["launchctl", "load", path])
            return True
        except Exception as exc:
            log.debug("[MACOS] set_launch_at_login failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # permissions
    # ------------------------------------------------------------------
    def permission_report(self) -> PermissionReport:
        mic_status = native.microphone_status()
        if mic_status is None:
            mic_granted, mic_unknown = False, True
        else:
            mic_granted = mic_status == native.AV_STATUS_AUTHORIZED
            mic_unknown = mic_status == native.AV_STATUS_NOT_DETERMINED

        ax_granted = native.accessibility_trusted(prompt=False)

        im_status = native.input_monitoring_status()
        im_granted = im_status == native.IOHID_ACCESS_GRANTED
        im_unknown = im_status == native.IOHID_ACCESS_UNKNOWN

        return PermissionReport(
            platform="macos",
            states=(
                PermissionState(
                    key="microphone",
                    label="Microphone",
                    granted=mic_granted,
                    required=True,
                    description="Required to record your voice for dictation.",
                    settings_url=_SETTINGS_URLS["microphone"],
                    indeterminate=mic_unknown,
                ),
                PermissionState(
                    key="accessibility",
                    label="Accessibility",
                    granted=ax_granted,
                    required=True,
                    description=(
                        "Required to paste text into other apps and to read your "
                        "current selection."
                    ),
                    settings_url=_SETTINGS_URLS["accessibility"],
                    indeterminate=False,
                ),
                PermissionState(
                    key="input_monitoring",
                    label="Input Monitoring",
                    granted=im_granted,
                    required=True,
                    description="Required for the global hotkey to work in every app.",
                    settings_url=_SETTINGS_URLS["input_monitoring"],
                    indeterminate=im_unknown,
                ),
            ),
        )

    def open_permission_settings(self, key: str) -> bool:
        if not IS_MACOS:
            return False
        url = _SETTINGS_URLS.get(key)
        if not url:
            return False
        result = _run(["open", url])
        return bool(result and result.returncode == 0)

    def request_permission(self, key: str) -> bool:
        """Trigger the OS consent prompt where one exists.

        Only microphone and Accessibility can prompt. Input Monitoring has no
        prompting API, so the caller must open Settings instead.
        """
        if key == "microphone":
            return native.request_microphone_access()
        if key == "accessibility":
            return native.accessibility_trusted(prompt=True)
        if key == "input_monitoring":
            return native.request_input_monitoring() == native.IOHID_ACCESS_GRANTED
        return False

    # ------------------------------------------------------------------
    # tts
    # ------------------------------------------------------------------
    def system_tts_to_file(self, text: str, out_path: str, voice: str | None = None) -> bool:
        """Synthesize with ``say``.

        ``say`` writes AIFF natively. When an ``.aiff`` path is requested it is
        produced directly; other extensions are converted with ``afconvert``
        (also stock). Returns False rather than writing a mislabelled file.
        """
        if not IS_MACOS or not shutil.which("say"):
            return False
        root, ext = os.path.splitext(out_path)
        ext = ext.lower()
        aiff_path = out_path if ext == ".aiff" else f"{root}.aiff"

        cmd = ["say", "-o", aiff_path]
        if voice:
            cmd += ["-v", voice]
        cmd += ["--", text]
        result = _run(cmd, timeout=120.0)
        if not result or result.returncode != 0 or not os.path.exists(aiff_path):
            return False
        if aiff_path == out_path:
            return True

        fmt = {".m4a": "m4af", ".caf": "caff", ".wav": "WAVE"}.get(ext)
        if fmt is None:
            log.debug("[MACOS] unsupported tts output extension %s", ext)
            return False
        conv = _run(["afconvert", "-f", fmt, "-d", "LEI16", aiff_path, out_path], timeout=120.0)
        try:
            os.remove(aiff_path)
        except OSError:
            pass
        return bool(conv and conv.returncode == 0 and os.path.exists(out_path))

    def system_tts_voices(self) -> list[str]:
        if not IS_MACOS or not shutil.which("say"):
            return []
        result = _run(["say", "-v", "?"])
        if not result or result.returncode != 0:
            return []
        voices: list[str] = []
        for line in (result.stdout or "").splitlines():
            if not line.strip():
                continue
            # "Alex                en_US    # Most people recognize me..."
            parts = line.split()
            if parts:
                voices.append(parts[0])
        return voices


__all__ = ["MacOSBackend"]
