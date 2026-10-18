"""Windows build runtime pins: Node satisfies HyperFrames, downloads are hash-checked."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "release" / "assemble_windows_staging.py"
# hyperframes@0.7.96 package.json: "engines": {"node": ">=22"}, enforced at
# startup by dist/runtimeVersion.js (MINIMUM_NODE_MAJOR = 22).
HYPERFRAMES_MIN_NODE_MAJOR = {"0.7.96": 22}


def _load():
    spec = importlib.util.spec_from_file_location("apf_assemble_staging", STAGING)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hyperframes_gets_a_node_that_meets_its_minimum():
    """Bundled Node stays 20.18.1 (small updates for v1.0.6 installs); the
    app-managed download supplies the Node HyperFrames needs."""
    from voice_flow import bundled_runtime, node_component

    staging = _load()
    assert staging.NODE_VERSION == bundled_runtime.WINDOWS_NODE == "20.18.1"
    assert staging.HYPERFRAMES_VERSION == bundled_runtime.WINDOWS_HYPERFRAMES
    minimum = HYPERFRAMES_MIN_NODE_MAJOR[staging.HYPERFRAMES_VERSION]
    assert node_component.HYPERFRAMES_MIN_NODE_MAJOR == minimum
    assert int(node_component.MANAGED_NODE_VERSION.split(".")[0]) >= minimum
    assert node_component.MANAGED_NODE_SHA256 == "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71"
    assert node_component.MANAGED_NODE_URL.startswith("https://nodejs.org/dist/v22.23.3/")


def test_runtime_downloads_are_pinned():
    source = STAGING.read_text(encoding="utf-8")
    for name in ("NODE_SHA256", "PYTHON_SHA256", "FFMPEG_SHA256"):
        assert f", {name})" in source, name


def test_download_rejects_a_cached_file_with_the_wrong_hash(tmp_path, monkeypatch):
    staging = _load()
    monkeypatch.setattr(staging, "CACHE", tmp_path)
    good = b"real archive"
    (tmp_path / "x.zip").write_bytes(b"tampered")
    fetched = []

    class _Resp:
        def __init__(self):
            self._data = [good, b""]

        def read(self, *_a):
            return self._data.pop(0)

        def __enter__(self):
            fetched.append(1)
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(staging.urllib.request, "urlopen", lambda *a, **k: _Resp())
    path = staging.download("https://example.invalid/x.zip", "x.zip", hashlib.sha256(good).hexdigest())
    assert path.read_bytes() == good and fetched == [1]


def test_download_fails_loudly_on_a_mismatched_fresh_file(tmp_path, monkeypatch):
    staging = _load()
    monkeypatch.setattr(staging, "CACHE", tmp_path)

    class _Resp:
        def __init__(self):
            self._data = [b"evil", b""]

        def read(self, *_a):
            return self._data.pop(0)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(staging.urllib.request, "urlopen", lambda *a, **k: _Resp())
    with pytest.raises(SystemExit):
        staging.download("https://example.invalid/y.zip", "y.zip", "0" * 64)
    assert not (tmp_path / "y.zip").exists()


def test_installer_does_not_reuse_the_old_default_group():
    iss = (ROOT / "release" / "installer" / "apf-setup.iss").read_text(encoding="utf-8")
    assert "DefaultGroupName={#MyAppName}" in iss
    assert "UsePreviousGroup=no" in iss
