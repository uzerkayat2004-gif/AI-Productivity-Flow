"""M-V-8: the risky-edit review step is not part of the 1.0.2 dictation pipeline."""
from __future__ import annotations

import ast
import inspect
import os
import sys
import textwrap
from pathlib import Path

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def test_dictation_pipeline_has_no_review_barrier_or_undefined_names():
    from voice_flow import main as main_module
    source = textwrap.dedent(inspect.getsource(main_module.VoiceFlowApp._process_dictation_pipeline))
    assert "check_user_review_barrier" not in source
    assert "get_review_manager" not in source
    tree = ast.parse(source)
    func = tree.body[0]
    assigned = {a.arg for a in func.args.args + func.args.kwonlyargs}
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            assigned.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.Lambda)) and node is not func:
            for a in node.args.args:
                assigned.add(a.arg)
    loaded = {n.id for n in ast.walk(func) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    # The removed block read `task` and `command_context`, which the
    # pipeline never defines; neither may be read without being assigned.
    for name in ("task", "command_context"):
        assert name not in loaded or name in assigned or hasattr(main_module, name)


def test_changelog_no_longer_lists_review_step():
    changelog = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Review before risky edits" not in changelog
