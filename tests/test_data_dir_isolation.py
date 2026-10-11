"""Regression: the test suite must never touch the user's real ~/.voice_flow.

Tests such as test_crash_reporting.py call storage.save_setting(...). Before
tests/conftest.py pinned VOICE_FLOW_DATA_DIR to a temp folder, those calls wrote
to the real settings database, e.g. silently switching off a developer's
crash-reporting opt-in after every run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


REAL_USER_DATA_DIR = Path.home() / ".voice_flow"


@pytest.fixture
def test_data_dir(isolate_voice_flow_data_dir: Path) -> Path:
    """The temp data dir conftest pins for every test."""
    return isolate_voice_flow_data_dir


def _is_inside(path: str | Path, root: Path) -> bool:
    return Path(path).resolve().is_relative_to(root.resolve())


def _real_db_state() -> tuple[bool, int, int]:
    db = REAL_USER_DATA_DIR / "voice_flow.db"
    if not db.exists():
        return (False, 0, 0)
    st = db.stat()
    return (True, st.st_mtime_ns, st.st_size)


def test_data_dir_points_at_temp_folder_not_real_home(test_data_dir: Path):
    from voice_flow.paths import data_dir

    assert test_data_dir.resolve() != REAL_USER_DATA_DIR.resolve()
    assert test_data_dir.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert data_dir().resolve() == test_data_dir.resolve()
    assert not _is_inside(data_dir(), REAL_USER_DATA_DIR)


def test_module_level_db_paths_are_isolated(test_data_dir: Path):
    from voice_flow import config, storage

    assert _is_inside(storage.DB_PATH, test_data_dir)
    assert _is_inside(storage.storage.db_path, test_data_dir)
    assert _is_inside(config.DB_PATH, test_data_dir)


def test_saving_a_setting_writes_temp_db_and_leaves_real_db_untouched(test_data_dir: Path):
    from voice_flow.storage import storage

    before = _real_db_state()
    key = "test_isolation_probe"
    storage.save_setting(key, "probe-value")
    try:
        assert storage.get_setting(key) == "probe-value"
        assert _is_inside(storage.db_path, test_data_dir)
        assert Path(storage.db_path).exists()
    finally:
        storage.save_setting(key, None)
    assert _real_db_state() == before


def test_sandbox_default_projects_root_follows_data_dir(test_data_dir: Path):
    from voice_flow.video_flow_engine.sandbox import prepare_job_directory

    job_dir = prepare_job_directory("isolation-probe-job")
    assert _is_inside(job_dir, test_data_dir / "v3_projects")


def test_subprocesses_inherit_the_temp_data_dir(test_data_dir: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    code = "from voice_flow.paths import data_dir; print(data_dir().resolve())"
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert Path(proc.stdout.strip()) == test_data_dir.resolve()
