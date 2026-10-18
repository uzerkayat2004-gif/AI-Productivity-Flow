"""The data folder (API keys, encryption key, NotebookLM cookies) must be private on POSIX."""

from __future__ import annotations

import os
import stat

import pytest

from voice_flow import paths

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")


@posix_only
def test_existing_world_readable_dir_is_restricted(tmp_path):
    target = tmp_path / ".voice_flow"
    target.mkdir(mode=0o755)
    os.chmod(target, 0o755)
    assert paths.harden_private_dir(target) is True
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


@posix_only
def test_missing_dir_is_created_private(tmp_path):
    target = tmp_path / "nested" / ".notebooklm"
    assert paths.harden_private_dir(target) is True
    assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0


@posix_only
def test_harden_private_data_dirs_covers_app_and_notebooklm(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    nlm_dir = tmp_path / "nlm"
    app_dir.mkdir()
    nlm_dir.mkdir()
    os.chmod(app_dir, 0o755)
    os.chmod(nlm_dir, 0o755)
    monkeypatch.setenv("VOICE_FLOW_DATA_DIR", str(app_dir))
    monkeypatch.setenv("NOTEBOOKLM_HOME", str(nlm_dir))
    paths.harden_private_data_dirs()
    assert stat.S_IMODE(app_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(nlm_dir.stat().st_mode) == 0o700


def test_never_raises_on_bad_path(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert paths.harden_private_dir(blocker / "child") is False


def test_windows_is_a_no_op(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.os, "name", "nt")
    assert paths.harden_private_dir(tmp_path / "x") is False
