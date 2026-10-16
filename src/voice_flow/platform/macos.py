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

Voice Flow defaults push-to-talk to Command+Option on macOS. Middle-click is a
Windows-only trigger; when Accessibility or Input Monitoring is missing, the
hotkey listener prompts once and never retries the Win32 hook.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time

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

# The login item is named after the app's bundle id. Builds before v1.0.3 used
# "com.voiceflow.app"; that file is migrated (removed) whenever the setting is
# read or written so a user never ends up with two login items.
_LAUNCH_AGENT_LABEL = "com.uzerkayat.aiproductivityflow"
_LEGACY_LAUNCH_AGENT_LABELS = ("com.voiceflow.app",)


# Accessibility roles whose AXSelectedText answer is authoritative (an empty
# answer really means "nothing selected"), so no Cmd+C probe is sent.
_NATIVE_TEXT_ROLES = frozenset({"AXTextArea", "AXTextField", "AXComboBox"})
# Apps where a synthetic Cmd+C after a drag copies files/objects, not text.
_NO_COPY_FALLBACK_APPS = frozenset({"Finder", "Dock", "SystemUIServer", "Screenshot", "screencaptureui"})
_FILE_PASTEBOARD_TYPES = frozenset({"public.file-url", "NSFilenamesPboardType", "com.apple.pasteboard.promised-file-url"})
_OWN_APP_NAMES = frozenset({"ai productivity flow", "voice flow", "voiceflow"})
_selection_ax_warned = False


def _warn_selection_needs_accessibility() -> None:
    global _selection_ax_warned
    if _selection_ax_warned:
        return
    _selection_ax_warned = True
    log.warning(
        "[MACOS] Reading selected text for Audio Flow needs Accessibility. Enable AI Productivity Flow in "
        "System Settings > Privacy & Security > Accessibility."
    )


def _general_pasteboard():
    try:
        from AppKit import NSPasteboard
    except Exception:
        return None
    try:
        return NSPasteboard.generalPasteboard()
    except Exception:
        return None


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _autorelease_pool():
    try:
        import objc

        return objc.autorelease_pool()
    except Exception:
        return _NullContext()


def _pasteboard_snapshot(pasteboard) -> list[dict]:
    """Copy every item/type currently on the pasteboard (text, images, files...)."""
    items: list[dict] = []
    for item in list(pasteboard.pasteboardItems() or []):
        entry: dict = {}
        for kind in list(item.types() or []):
            data = item.dataForType_(kind)
            if data is not None:
                entry[str(kind)] = data
        if entry:
            items.append(entry)
    return items


def _pasteboard_restore(pasteboard, snapshot: list[dict]) -> None:
    from AppKit import NSPasteboardItem

    pasteboard.clearContents()
    restored = []
    for entry in snapshot:
        item = NSPasteboardItem.alloc().init()
        for kind, data in entry.items():
            item.setData_forType_(data, kind)
        restored.append(item)
    if restored:
        pasteboard.writeObjects_(restored)


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
    def can_post_events(self) -> bool:
        """Whether macOS will deliver our synthetic Cmd+V / Cmd+C to other apps."""
        return native.can_post_events()

    def send_paste(self) -> bool:
        """Cmd+V. Returns False when macOS would silently drop the event.

        Without Accessibility (or the post-event grant) ``CGEventPost`` still
        "succeeds" but no app ever receives the keystroke, so reporting True
        there turned a lost paste into a fake success.
        """
        if not native.can_post_events():
            return False
        return native.send_key_combo(native.KEY_V, native.kCGEventFlagMaskCommand)

    def send_copy(self) -> bool:
        if not native.can_post_events():
            return False
        return native.send_key_combo(native.KEY_C, native.kCGEventFlagMaskCommand)

    def send_enter(self) -> bool:
        if not native.can_post_events():
            return False
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

    def is_own_app(self, info: dict | None) -> bool:
        """True when a window-owner record belongs to AI Productivity Flow.

        The engine (floating bar, Audio Flow widget) and the main window run
        in separate processes of the same app, so match the app name too."""
        if not info:
            return False
        pid = info.get("pid")
        if isinstance(pid, int) and pid > 0 and pid == os.getpid():
            return True
        app = str(info.get("app", "")).strip().lower()
        return bool(app) and app in _OWN_APP_NAMES

    def restore_paste_target_focus(self, timeout: float = 0.8) -> dict:
        """Give keyboard focus back to the user's app before Cmd+V.

        Clicking the floating bar or the Audio Flow widget makes this engine
        process the active app. Its windows are not normal (layer 0) windows,
        so the frontmost document window still belongs to e.g. TextEdit, but
        the Cmd+V keystroke goes to the active app -- us -- and the paste is
        lost (seen on macOS 15, Oct 2026). When that happens, re-activate the
        app that owns the frontmost normal window and wait until it is active.

        Returns a small report for logging; never raises."""
        report: dict = {"restored": False}
        if not IS_MACOS:
            return report
        try:
            from AppKit import NSApplication, NSRunningApplication, NSWorkspace

            def _active(running) -> bool | None:
                try:
                    return bool(running.isActive()) if running is not None else False
                except Exception:
                    return None

            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            front_pid = int(front.processIdentifier()) if front is not None else 0
            report["active_pid"] = front_pid
            own = None
            try:
                own = NSRunningApplication.currentApplication()
            except Exception:
                own = None
            own_active = _active(own)
            if own_active is None:
                own_active = front_pid == os.getpid()
            front_active = _active(front)
            if front_active is None:
                front_active = front is not None
            report["own_active"] = own_active
            # Act when we hold keyboard activation -- even if frontmostApplication
            # (the menu-bar owner) still names the user's app: macOS 14 CI, Escape
            # on our widget menu left our accessory app active while TextEdit kept
            # the menu bar, and Cmd+V reached us -- or when nothing is active.
            # Never take focus from another app the user activated
            # (Spotlight-style panels too).
            if not own_active and front_pid not in (0, os.getpid()) and front_active:
                return report
            target = native.frontmost_window_owner() or {}
            pid = target.get("pid")
            report["target"] = {"app": target.get("app"), "pid": pid}
            if not isinstance(pid, int) or pid <= 0 or pid == os.getpid() or self.is_own_app(target):
                return report
            app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if app is None:
                return report
            try:
                # macOS 14+: cooperative activation -- the active app yields.
                ns_app = NSApplication.sharedApplication()
                if hasattr(ns_app, "yieldActivationToApplication_"):
                    ns_app.yieldActivationToApplication_(app)
            except Exception:
                pass
            try:
                from AppKit import NSApplicationActivateIgnoringOtherApps

                options = NSApplicationActivateIgnoringOtherApps
            except Exception:
                options = 2
            app.activateWithOptions_(options)
            deadline = time.monotonic() + max(0.1, timeout)
            used_open = False
            while time.monotonic() < deadline:
                time.sleep(0.04)
                target_active = _active(app)
                if target_active is None:
                    now_front = NSWorkspace.sharedWorkspace().frontmostApplication()
                    target_active = now_front is not None and int(now_front.processIdentifier()) == pid
                if target_active:
                    report["restored"] = True
                    break
                if not used_open and time.monotonic() > deadline - timeout / 2:
                    # Fallback through LaunchServices (no Automation permission).
                    used_open = True
                    url = app.bundleURL()
                    path = str(url.path()) if url is not None else ""
                    if path:
                        subprocess.run(["/usr/bin/open", "-a", path], timeout=2,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            report["used_open"] = used_open
            if report["restored"]:
                # Let the target's key window take first responder again.
                time.sleep(0.08)
            log.info("[MACOS] Paste target focus restore: %s", report)
        except Exception as exc:
            report["error"] = repr(exc)
            log.debug("[MACOS] restore_paste_target_focus failed", exc_info=True)
        return report

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------
    def get_selected_text(self) -> str:
        """Read the user's current selection without disturbing their clipboard.

        1. Accessibility ``AXSelectedText`` of the focused element. Native text
           views (TextEdit, Notes, Mail, Safari fields, ...) answer this
           directly; when such a view answers "no selection" we trust it and
           never send a keystroke.
        2. Otherwise (Electron, Chrome web content, Java apps) fall back to a
           synthetic Cmd+C, read the copied text and restore every pasteboard
           item that was there before, so the user's clipboard (including
           images and files) is unchanged. Nothing is restored or touched when
           Cmd+C copied nothing.

        Without Accessibility neither path works (macOS drops synthetic keys),
        so this returns "" and logs once instead of pretending.
        """
        info = native.focused_selection_info()
        if not info.get("trusted"):
            _warn_selection_needs_accessibility()
            return ""
        text = str(info.get("text") or "")
        if text.strip():
            return text
        if info.get("status") == 0 and str(info.get("role") or "") in _NATIVE_TEXT_ROLES:
            return ""
        owner = native.frontmost_window_owner()
        if self.is_own_app(owner) or str(owner.get("app", "")) in _NO_COPY_FALLBACK_APPS:
            return ""
        return self._copy_selection_preserving_clipboard()

    def _copy_selection_preserving_clipboard(self) -> str:
        if not native.can_post_events():
            return ""
        # After a hotkey such as Ctrl+Option+L the user may still hold the
        # modifiers; Cmd+C would then arrive as Cmd+Ctrl+Option+C.
        if not native.wait_for_modifiers_released(1.0):
            log.debug("[MACOS] modifiers still held; skipping Cmd+C selection probe")
            return ""
        pasteboard = _general_pasteboard()
        if pasteboard is None:
            return self._copy_selection_via_pbcopy()
        import time

        with _autorelease_pool():
            try:
                before = int(pasteboard.changeCount())
                snapshot = _pasteboard_snapshot(pasteboard)
            except Exception as exc:
                log.debug("[MACOS] pasteboard snapshot failed: %s", exc)
                return ""
            if not native.send_key_combo(native.KEY_C, native.kCGEventFlagMaskCommand):
                return ""
            deadline = time.monotonic() + 0.4
            while time.monotonic() < deadline and int(pasteboard.changeCount()) == before:
                time.sleep(0.02)
            after = int(pasteboard.changeCount())
            if after == before:
                return ""  # nothing was selected/copied; clipboard untouched
            text = ""
            try:
                types = {str(t) for t in (pasteboard.types() or [])}
                if not types.intersection(_FILE_PASTEBOARD_TYPES):
                    text = str(pasteboard.stringForType_("public.utf8-plain-text") or "")
            finally:
                # Restore unless something else (the user) wrote meanwhile.
                if int(pasteboard.changeCount()) == after:
                    try:
                        _pasteboard_restore(pasteboard, snapshot)
                    except Exception as exc:
                        log.warning("[MACOS] could not restore clipboard after selection read: %s", exc)
            return text

    def _copy_selection_via_pbcopy(self) -> str:
        """Fallback without AppKit: sentinel round-trip through pbcopy/pbpaste."""
        import time
        import uuid

        saved = self.read_clipboard()
        sentinel = f"__apf_selection_probe_{uuid.uuid4().hex}__"
        if not self.copy_to_clipboard(sentinel):
            return ""
        grabbed = ""
        try:
            if not native.send_key_combo(native.KEY_C, native.kCGEventFlagMaskCommand):
                return ""
            for _ in range(10):
                time.sleep(0.04)
                grabbed = self.read_clipboard()
                if grabbed and grabbed != sentinel:
                    break
            return grabbed if grabbed and grabbed != sentinel else ""
        finally:
            current = self.read_clipboard()
            if current in (sentinel, grabbed):
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
    def _agent_path(self, label: str = _LAUNCH_AGENT_LABEL) -> str:
        return os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")

    def _legacy_agent_paths(self) -> list[str]:
        return [self._agent_path(label) for label in _LEGACY_LAUNCH_AGENT_LABELS]

    def _remove_legacy_agents(self) -> bool:
        """Delete old-named login items. Returns True if one was present."""
        found = False
        for legacy in self._legacy_agent_paths():
            if os.path.exists(legacy):
                found = True
                try:
                    os.remove(legacy)
                except OSError as exc:
                    log.debug("[MACOS] could not remove legacy login item %s: %s", legacy, exc)
        return found

    def migrate_legacy_login_item(self) -> bool:
        """Rename an old "com.voiceflow.app" login item to the bundle id name."""
        if not IS_MACOS or not any(os.path.exists(p) for p in self._legacy_agent_paths()):
            return False
        if os.path.exists(self._agent_path()):
            self._remove_legacy_agents()
            return True
        return self.set_launch_at_login(True)

    def get_launch_at_login(self) -> bool:
        if os.path.exists(self._agent_path()):
            return True
        return any(os.path.exists(p) for p in self._legacy_agent_paths())

    def set_launch_at_login(self, enabled: bool, command: str | None = None) -> bool:
        if not IS_MACOS:
            return False
        path = self._agent_path()
        try:
            if not enabled:
                # Only delete the file. "launchctl unload" would SIGTERM the
                # running app when it was itself started at login.
                if os.path.exists(path):
                    os.remove(path)
                self._remove_legacy_agents()
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
            # launchd reads ~/Library/LaunchAgents at the next login. Do not
            # "launchctl load" now: RunAtLoad would start a second copy of the
            # app immediately.
            self._remove_legacy_agents()
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
