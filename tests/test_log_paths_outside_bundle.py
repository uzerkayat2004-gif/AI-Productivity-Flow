"""B4: debug log and crash log must live in ~/.voice_flow/logs, never in the app bundle.

main.py can't be imported in every test environment (GUI deps), so the helper is
extracted from the source and executed on its own.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "main.py"
SOURCE = MAIN.read_text(encoding="utf-8")


def _load_helper():
    tree = ast.parse(SOURCE)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_voice_flow_log_dir")
    namespace: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(MAIN), "exec"), namespace)
    return namespace["_voice_flow_log_dir"]


def test_log_dir_is_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(tmp_path / ".voice_flow"))
    result = _load_helper()()
    assert result == tmp_path / ".voice_flow" / "logs"
    assert result.is_dir()


def test_unwritable_data_dir_disables_file_logging(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(blocker))
    assert _load_helper()() is None


def test_no_log_writes_relative_to_package_or_bundle():
    for name in ("voice_flow_debug.log", "crash_log.txt"):
        for line in SOURCE.splitlines():
            if name in line:
                assert "__file__" not in line, line
    assert "logging.FileHandler(" not in SOURCE
    assert "RotatingFileHandler" in SOURCE and "maxBytes=5 * 1024 * 1024" in SOURCE


def test_crash_log_write_is_guarded():
    idx = SOURCE.index('"crash_log.txt"')
    block = SOURCE[idx - 300: idx + 400]
    assert "_voice_flow_log_dir()" in block
    assert "except Exception:" in block
