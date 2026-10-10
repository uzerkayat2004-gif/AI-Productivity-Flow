"""Print bounded, redacted CI startup diagnostics without importing the app."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Drop whole credential-bearing lines, including traceback source lines.
_SENSITIVE = re.compile(
    r"api[_ -]?key|token|password|secret|authorization|bearer|cookie|dsn|"
    r"https?://[^/\s]+@|"
    r"gh[pousr]_|github_pat_|sk-[A-Za-z0-9]|AIza[A-Za-z0-9]",
    re.IGNORECASE,
)
_URL_QUERY = re.compile(r"(https?://[^\s?#]+)\?[^\s]*", re.IGNORECASE)
MAX_BYTES = 64 * 1024
MAX_LINES = 120


def log_tail(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - MAX_BYTES))
            content = stream.read(MAX_BYTES).decode("utf-8", errors="replace")
        if size > MAX_BYTES:
            # The first partial line may begin inside a credential.
            content = content.partition("\n")[2]
    except OSError:
        return "[log unavailable]"
    lines = content.splitlines()[-MAX_LINES:]
    return "\n".join(
        "[credential-bearing line redacted]" if _SENSITIVE.search(line)
        else _URL_QUERY.sub(r"\1?[query redacted]", line)
        for line in lines
    ) or "[log empty]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args()
    report = "\n\n".join(f"=== {path.name} ===\n{log_tail(path)}" for path in args.logs) + "\n"
    args.output.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
