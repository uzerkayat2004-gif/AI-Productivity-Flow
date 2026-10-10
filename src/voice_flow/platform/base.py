"""Platform backend contract.

Every OS-specific behaviour Voice Flow needs is declared here once. Windows and
macOS each provide a concrete implementation; ``voice_flow.platform`` picks one
at import time based on ``sys.platform``.

Design rules:
  * Methods return values, they do not raise for "unsupported". A backend that
    cannot do something returns ``False`` / ``""`` / ``None`` and logs.
  * No method blocks for more than ~1s.
  * Nothing here touches the OS at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PermissionState:
    """One OS permission Voice Flow depends on."""

    key: str
    label: str
    granted: bool
    required: bool
    description: str = ""
    settings_url: str = ""
    # True when the backend cannot actually determine the state (e.g. macOS
    # Accessibility can only be probed indirectly). Callers should present this
    # as "unknown" rather than "denied".
    indeterminate: bool = False


@dataclass(frozen=True)
class PermissionReport:
    """Aggregate permission status used by the onboarding screen."""

    platform: str
    states: tuple[PermissionState, ...] = field(default_factory=tuple)

    @property
    def all_required_granted(self) -> bool:
        return all(s.granted for s in self.states if s.required)

    @property
    def missing_required(self) -> tuple[PermissionState, ...]:
        return tuple(s for s in self.states if s.required and not s.granted)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "allRequiredGranted": self.all_required_granted,
            "permissions": [
                {
                    "key": s.key,
                    "label": s.label,
                    "granted": s.granted,
                    "required": s.required,
                    "description": s.description,
                    "settingsUrl": s.settings_url,
                    "indeterminate": s.indeterminate,
                }
                for s in self.states
            ],
        }


@runtime_checkable
class PlatformBackend(Protocol):
    """OS-specific operations required by the Voice Flow runtime."""

    name: str

    # -- clipboard ---------------------------------------------------------
    def copy_to_clipboard(self, text: str) -> bool:
        """Place ``text`` on the system clipboard. Returns success."""
        ...

    def read_clipboard(self) -> str:
        """Read text from the system clipboard ("" when empty/unavailable)."""
        ...

    # -- synthetic input ---------------------------------------------------
    def send_paste(self) -> bool:
        """Send the OS paste chord (Ctrl+V / Cmd+V) to the focused app."""
        ...

    def send_copy(self) -> bool:
        """Send the OS copy chord (Ctrl+C / Cmd+C) to the focused app."""
        ...

    def send_enter(self) -> bool:
        """Send Return to the focused app."""
        ...

    # -- window / focus ----------------------------------------------------
    def active_window_title(self) -> str:
        """Title of the frontmost window ("" when unavailable)."""
        ...

    def active_app_name(self) -> str:
        """Bundle/executable name of the frontmost app ("" when unavailable)."""
        ...

    def is_own_window_focused(self) -> bool:
        """True when Voice Flow itself owns the frontmost window."""
        ...

    # -- selection ---------------------------------------------------------
    def get_selected_text(self) -> str:
        """Best-effort read of the user's current text selection."""
        ...

    # -- feedback ----------------------------------------------------------
    def beep(self, kind: str = "start") -> bool:
        """Play a short non-blocking UI sound. ``kind`` in {start, stop, error}."""
        ...

    # -- autostart ---------------------------------------------------------
    def get_launch_at_login(self) -> bool:
        ...

    def set_launch_at_login(self, enabled: bool, command: str | None = None) -> bool:
        ...

    # -- permissions -------------------------------------------------------
    def permission_report(self) -> PermissionReport:
        """Describe the OS permissions Voice Flow needs and their state."""
        ...

    def open_permission_settings(self, key: str) -> bool:
        """Open the OS settings pane for permission ``key``."""
        ...

    # -- tts ---------------------------------------------------------------
    def system_tts_to_file(self, text: str, out_path: str, voice: str | None = None) -> bool:
        """Synthesize ``text`` to ``out_path`` using the OS voice engine."""
        ...

    def system_tts_voices(self) -> list[str]:
        """List OS TTS voice identifiers."""
        ...


__all__ = ["PlatformBackend", "PermissionState", "PermissionReport"]
