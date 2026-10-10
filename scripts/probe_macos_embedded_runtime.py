"""Probe the built outer executable's real embedded Python/Cocoa identity."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

APP_NAME = "AI Productivity Flow"
BUNDLE_ID = "com.uzerkayat.aiproductivityflow"
LAUNCHER = "ai-productivity-flow-launcher"
_PROBE = """
import json, sys
from Foundation import NSBundle
bundle = NSBundle.mainBundle()
info = bundle.infoDictionary()
print(json.dumps({
    "executable": sys.executable,
    "prefix": sys.prefix,
    "bundlePath": str(bundle.bundlePath() or ''),
    "bundleIdentifier": str(bundle.bundleIdentifier() or ''),
    "CFBundleName": str(info.get('CFBundleName') or ''),
    "CFBundleDisplayName": str(info.get('CFBundleDisplayName') or ''),
    "CFBundleExecutable": str(info.get('CFBundleExecutable') or '')
}))
"""


def embedded_runtime_problem(text: str, app_path: str) -> str | None:
    try:
        if not isinstance(app_path, str) or not app_path.startswith("/") or not app_path.endswith(".app"):
            raise ValueError("invalid expected outer app path")
        report = json.loads(text)
        expected = {
            "executable": app_path + "/Contents/MacOS/" + LAUNCHER,
            "prefix": app_path + "/Contents/Resources/runtime/python",
            "bundlePath": app_path, "bundleIdentifier": BUNDLE_ID,
            "CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME,
            "CFBundleExecutable": LAUNCHER,
        }
        for field, value in expected.items():
            if report[field] != value:
                return f"embedded runtime {field} does not match outer application identity"
        return None
    except (ValueError, KeyError, TypeError) as exc:
        return f"missing or malformed embedded runtime evidence: {exc}"


def capture_embedded_runtime(app_path: Path, out: Path) -> None:
    app_path = app_path.resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run([str(app_path / "Contents/MacOS" / LAUNCHER), "-c", _PROBE],
                                capture_output=True, text=True, check=False, timeout=15)
    except subprocess.TimeoutExpired:
        (out / "embedded-runtime-stderr.txt").write_text("[outer runtime probe timed out after 15 seconds]\n", encoding="utf-8")
        raise
    (out / "embedded-runtime.json").write_text(result.stdout, encoding="utf-8")
    try:
        from scripts.report_macos_launch_failure import _SENSITIVE, _URL_QUERY
    except ModuleNotFoundError:
        from report_macos_launch_failure import _SENSITIVE, _URL_QUERY
    error_lines = result.stderr.splitlines()[-120:]
    redacted = "\n".join("[credential-bearing line redacted]" if _SENSITIVE.search(line)
                         else _URL_QUERY.sub(r"\1?[query redacted]", line)[:1500] for line in error_lines)
    (out / "embedded-runtime-stderr.txt").write_text(redacted[:65536], encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"actual outer embedded-runtime probe exited {result.returncode}")
    problem = embedded_runtime_problem((out / "embedded-runtime.json").read_text(encoding="utf-8"), str(app_path))
    if problem:
        raise RuntimeError(problem)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python3 scripts/probe_macos_embedded_runtime.py APP_PATH OUT_DIR", file=sys.stderr)
        return 2
    try:
        capture_embedded_runtime(Path(argv[1]), Path(argv[2]))
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"macOS embedded runtime failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
