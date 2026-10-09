"""List local GUI assets referenced by the desktop UI that are not in the repo.

The scan covers ``src/voice_flow/gui/index.html``, ``app.js``, and the CSS
files beside them. Remote URLs, data URLs, and template placeholders are
ignored. The report is non-blocking: missing onboarding media is printed
and the process still exits 0.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUI_DIR = REPO_ROOT / "src" / "voice_flow" / "gui"
_ASSET_EXT = r"(?:mp3|mp4|png|jpe?g|svg|webp|gif|ico)"
_ATTR_RE = re.compile(
    rf"""(?:src|poster|href)\s*=\s*["']([^"']+\.{_ASSET_EXT}(?:\?[^"']*)?)["']""",
    re.IGNORECASE,
)
_URL_RE = re.compile(
    rf"""url\(\s*["']?([^"')]+\.{_ASSET_EXT}(?:\?[^"')]*?)?)["']?\s*\)""",
    re.IGNORECASE,
)
_QUOTED_RE = re.compile(
    rf"""["']([^"']+\.{_ASSET_EXT}(?:\?[^"']*)?)["']""",
    re.IGNORECASE,
)


def _source_files() -> list[Path]:
    files = [GUI_DIR / "index.html", GUI_DIR / "app.js"]
    files.extend(sorted(GUI_DIR.glob("*.css")))
    return [path for path in files if path.is_file()]


def _candidate_paths(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in (_ATTR_RE, _URL_RE):
        found.update(match.group(1) for match in pattern.finditer(text))
    for match in _QUOTED_RE.finditer(text):
        token = match.group(1)
        # Quoted download names such as "Card.png" are not file references.
        if "/" in token or "\\" in token:
            found.add(token)
    return found


def _local_asset(raw: str) -> Path | None:
    token = raw.strip().strip("\"'")
    token = token.split("#", 1)[0].split("?", 1)[0].strip()
    if not token or "${" in token or "{{" in token or "`" in token:
        return None
    lowered = token.lower()
    if lowered.startswith(("http://", "https://", "data:", "blob:", "javascript:", "//")):
        return None
    if not re.search(rf"\.{_ASSET_EXT}$", token, re.IGNORECASE):
        return None
    relative = token[1:] if token.startswith("/") else token
    if relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
        return None
    path = (GUI_DIR / relative).resolve()
    try:
        path.relative_to(GUI_DIR.resolve())
    except ValueError:
        return None
    return path


def missing_gui_assets() -> list[str]:
    """Return repo-relative paths of referenced local assets that are absent."""
    referenced: set[Path] = set()
    for source in _source_files():
        text = source.read_text(encoding="utf-8", errors="replace")
        for raw in _candidate_paths(text):
            resolved = _local_asset(raw)
            if resolved is not None:
                referenced.add(resolved)
    missing = [path for path in referenced if not path.is_file()]
    missing.sort(key=lambda path: path.as_posix())
    return [path.relative_to(REPO_ROOT).as_posix() for path in missing]


def main(argv: list[str] | None = None) -> int:
    del argv
    missing = missing_gui_assets()
    if not missing:
        print("No missing local GUI assets.")
        return 0
    print(f"Missing local GUI assets ({len(missing)}):")
    for path in missing:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
