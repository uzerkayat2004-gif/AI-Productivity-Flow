"""Filesystem locations for Voice Flow runtime data."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Return the runtime data directory, with an opt-in test/portable override."""
    override = os.environ.get("VOICE_FLOW_DATA_DIR")
    return Path(override).expanduser() if override else Path.home() / ".voice_flow"


def harden_private_dir(path: str | os.PathLike[str]) -> bool:
    """Create ``path`` if needed and make it readable by this user only (POSIX).

    The data folder holds the SQLite settings database (provider API keys and
    the token-encryption key) and the NotebookLM session cookies. With the
    default umask those are created 0755/0644 under a home folder that other
    local accounts can traverse on macOS, so a second user on the same Mac
    could read them. Windows profiles are already private by ACL, so this is a
    no-op there. Folders owned by someone else are left alone. Never raises.
    """
    if os.name == "nt":
        return False
    try:
        target = Path(path).expanduser()
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        st = target.stat()
        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            return False
        if st.st_mode & 0o077:
            os.chmod(target, st.st_mode & 0o700 | 0o700)
        return True
    except OSError:
        return False


def harden_private_data_dirs() -> None:
    """Restrict the app data folder and the NotebookLM profile root to this user."""
    harden_private_dir(data_dir())
    notebooklm_home = os.environ.get("NOTEBOOKLM_HOME")
    harden_private_dir(Path(notebooklm_home) if notebooklm_home else Path.home() / ".notebooklm")
