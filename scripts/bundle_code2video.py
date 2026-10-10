"""Copy the vendored Code2Video tree into an app bundle without secrets."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

_SECRET_KEYS = {"api_key", "apikey", "secret", "token", "access_token"}
_PLACEHOLDER_VALUES = {"", "...", "…", "changeme", "your_api_key", "your_iconfinder_key"}
_PLACEHOLDER_CONFIG = {
    "gemini": {"base_url": "...", "api_key": "..."},
    "gpt41": {"base_url": "...", "api_key": "..."},
    "gpt5": {"base_url": "...", "api_key": "..."},
    "gpto4mini": {"base_url": "...", "api_key": "..."},
    "gpt4o": {"base_url": "...", "api_key": "..."},
    "claude": {"base_url": "...", "api_key": "..."},
    "iconfinder": {"api_key": "YOUR_ICONFINDER_KEY"},
}


def _secret_values(obj: object) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and str(key).lower() in _SECRET_KEYS:
                found.append(value.strip())
            else:
                found.extend(_secret_values(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_secret_values(item))
    return found


def api_config_is_placeholder(path: Path) -> bool:
    """Return whether an api_config.json contains only placeholder secrets."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    values = _secret_values(data)
    if not values:
        return False
    for value in values:
        lowered = value.lower()
        if lowered in _PLACEHOLDER_VALUES or lowered.startswith("your_"):
            continue
        if value and set(value) <= set(".*xX-"):
            continue
        return False
    return True


def _ignore(directory: str, names: list[str]) -> set[str]:
    del directory
    ignored: set[str] = set()
    for name in names:
        lowered = name.lower()
        if name == "__pycache__" or lowered.endswith((".pyc", ".pyo", ".pyd")):
            ignored.add(name)
        elif lowered in {".env", "credentials.json", "token.json"} or lowered.endswith(
            (".pem", ".key", ".env")
        ):
            ignored.add(name)
    return ignored


def copy_code2video(source: Path, destination: Path) -> Path:
    """Copy Code2Video into ``destination``, replacing real API configs."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=_ignore)
    for config in destination.rglob("api_config.json"):
        if not api_config_is_placeholder(config):
            config.write_text(
                json.dumps(_PLACEHOLDER_CONFIG, indent=4) + "\n",
                encoding="utf-8",
            )
    return destination
