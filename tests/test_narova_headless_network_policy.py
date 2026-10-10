"""App renders cannot start or refresh HyperFrames' external Studio listeners."""
import json
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest

from voice_flow.video_flow_engine import narova_runner

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("installed", [False, True])
def test_app_render_environment_always_disables_studio_refresh(monkeypatch, tmp_path, installed):
    monkeypatch.setattr(narova_runner.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(narova_runner.runtime_env, "is_installed", lambda: installed)
    monkeypatch.setattr(narova_runner.runtime_env, "runtime_root", lambda: tmp_path / "runtime")
    monkeypatch.setattr(narova_runner.runtime_env, "python_executable", lambda: "fixture-python")
    monkeypatch.setenv("NAROVA_HEADLESS_APP", "0")
    environment = narova_runner._safe_environment()
    assert environment["NAROVA_HEADLESS_APP"] == "1"


@pytest.mark.parametrize("app_job", [True, False])
def test_real_preview_refresh_helper_has_no_app_side_effects(app_job):
    node = shutil.which("node")
    assert node, "The listener policy regression requires Node.js on local/CI runners"
    source = (ROOT / "third_party/narova/tool/bin/narova.js").read_text(encoding="utf-8")
    start = source.index("function refreshPreviewIfLive(out) {")
    end = source.index("\nconst fmtTime", start)
    # Evaluate only the actual helper with instrumented collaborators, not the
    # CLI entrypoint or a renderer. No filesystem/network/process effects run.
    helper = source[start:end]
    fixture = textwrap.dedent("""
        const vm = require('vm');
        const assert = require('assert/strict');
        const path = require('path');
        const calls = [];
        const context = {
          process: {env: {NAROVA_HEADLESS_APP: APP_JOB ? '1' : '0'}},
          path,
          findHfDir: out => { calls.push('directory'); return path.join(out, 'hf'); },
          livePreviewPid: file => { calls.push('pid'); return 42; },
          previewPort: file => { calls.push('port'); return 3210; },
          stopHfPreview: file => { calls.push('stop'); },
          startHfPreview: (dir, options) => {
            calls.push('start');
            assert.equal(options.port, 3210);
            return {url: 'http://127.0.0.1:3210', pid: 43};
          },
          console: {log: () => {}, error: message => { throw new Error(message); }}
        };
        vm.createContext(context);
        vm.runInContext(HELPER, context);
        context.refreshPreviewIfLive('fixture-output');
        assert.deepEqual(calls, APP_JOB ? [] : ['directory', 'pid', 'port', 'stop', 'start']);
    """)
    script = "const APP_JOB = " + json.dumps(app_job) + ";\nconst HELPER = " + json.dumps(helper) + ";\n" + fixture
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
