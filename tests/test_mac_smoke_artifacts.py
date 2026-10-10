from __future__ import annotations

from PIL import Image, ImageDraw

import copy
import json
import sys

import pytest

from pathlib import Path

from scripts.check_mac_smoke_artifacts import (
    app_exited,
    is_mostly_blank,
    identity_report_problem,
    logs_mention_system_browser_fallback,
    logs_mention_win32_keyboard_hook,
    main,
    window_report_problem,
)


def test_white_image_is_mostly_blank():
    assert is_mostly_blank(Image.new("RGB", (200, 200), "white"))


def test_black_image_is_mostly_blank():
    assert is_mostly_blank(Image.new("RGB", (200, 200), "black"))


def test_colored_content_is_not_mostly_blank():
    image = Image.new("RGB", (200, 200), "#f7f0e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 60, 140, 90), fill="#f97316")
    draw.rectangle((60, 100, 135, 125), fill="#2563eb")
    draw.rectangle((70, 132, 150, 145), fill="#6d28d9")
    for x in range(65, 136, 12):
        draw.rectangle((x, 108, x + 5, 115), fill="#1c1917")
    assert not is_mostly_blank(image)


def test_win32_keyboard_hook_log_is_detected():
    assert logs_mention_win32_keyboard_hook("Win32 keyboard hook stopped")
    assert not logs_mention_win32_keyboard_hook("pynput listener started")


def _colorful_screenshot(path: Path) -> None:
    image = Image.new("RGB", (80, 80), "#f7f0e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 70, 36), fill="#f97316")
    draw.rectangle((8, 42, 60, 72), fill="#2563eb")
    image.save(path)


def _healthy_out(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    _colorful_screenshot(out / "screen-30s.png")
    (out / "alive.txt").write_text("5s: running\n60s: running\n", encoding="utf-8")
    (out / "windows.txt").write_text(
        "Finder: Desktop\nAI Productivity Flow: AI Productivity Flow\n",
        encoding="utf-8",
    )
    (out / "app-stdout.txt").write_text("ready\n", encoding="utf-8")
    (out / "app-stderr.txt").write_text("", encoding="utf-8")
    for seconds in (30, 60):
        (out / f"identity-{seconds}s.json").write_text(json.dumps(_identity()), encoding="utf-8")
    (out / "embedded-runtime.json").write_text(json.dumps(_embedded_runtime()), encoding="utf-8")
    return out


def test_healthy_smoke_artifacts_pass(tmp_path: Path):
    out = _healthy_out(tmp_path)
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 0


def test_exited_app_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "alive.txt").write_text("5s: running\n15s: EXITED\n", encoding="utf-8")
    assert app_exited((out / "alive.txt").read_text(encoding="utf-8"))
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_safari_window_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "windows.txt").write_text("Safari: AI Productivity Flow\n", encoding="utf-8")
    assert window_report_problem((out / "windows.txt").read_text(encoding="utf-8"))
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_other_browser_window_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "windows.txt").write_text("Google Chrome: AI Productivity Flow\n", encoding="utf-8")
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_missing_app_window_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "windows.txt").write_text("Finder: Desktop\n", encoding="utf-8")
    assert window_report_problem((out / "windows.txt").read_text(encoding="utf-8")) == "no app window"
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def test_system_browser_fallback_log_fails_smoke_check(tmp_path: Path):
    out = _healthy_out(tmp_path)
    (out / "gui_launcher.log").write_text(
        "Native window backend unavailable; using the system browser.\n",
        encoding="utf-8",
    )
    assert logs_mention_system_browser_fallback((out / "gui_launcher.log").read_text(encoding="utf-8"))
    assert main(["check_mac_smoke_artifacts.py", str(out)]) == 1


def _identity():
    return {
        "captureSource": "CGWindowList",
        "appPath": "/Applications/AI Productivity Flow.app",
        "frontmost": {"pid": 100, "localizedName": "AI Productivity Flow"},
        "applications": [{
            "pid": 100, "localizedName": "AI Productivity Flow",
            "bundleIdentifier": "com.uzerkayat.aiproductivityflow",
            "executablePath": "/Applications/AI Productivity Flow.app/Contents/MacOS/ai-productivity-flow-launcher",
            "activationPolicy": 0, "windows": ["AI Productivity Flow"],
            "windowMetadata": [{"windowNumber": 42, "ownerPid": 100, "layer": 0, "onScreen": True,
                                "alpha": 1.0, "width": 1100, "height": 800, "title": "AI Productivity Flow"}],
        }],
    }


def test_python_named_legacy_apf_window_is_rejected():
    assert window_report_problem("Finder:\npython3: tk\npython3: AI Productivity Flow")


def test_old_rc2_python_native_identity_is_rejected():
    report = _identity()
    report["applications"][0]["localizedName"] = "python3"
    assert "menu name" in identity_report_problem(json.dumps(report))


def test_two_dock_visible_pids_are_rejected():
    report = _identity()
    helper = copy.deepcopy(report["applications"][0])
    helper.update(pid=101, windows=["tk"])
    report["applications"].append(helper)
    assert "found 2" in identity_report_problem(json.dumps(report))


def test_accessory_helper_and_unrelated_python_are_allowed():
    report = _identity()
    helper = copy.deepcopy(report["applications"][0])
    helper.update(pid=101, localizedName="AI Productivity Flow", activationPolicy=1, windows=["tk"])
    unrelated = copy.deepcopy(helper)
    unrelated.update(pid=102, localizedName="python3", activationPolicy=0, executablePath="/usr/local/bin/python3")
    report["applications"].extend([helper, unrelated])
    assert identity_report_problem(json.dumps(report)) is None


def test_multiple_windows_and_identical_duplicate_pid_count_once():
    report = _identity()
    report["applications"][0]["windows"].append("Preferences")
    report["applications"].append(copy.deepcopy(report["applications"][0]))
    assert identity_report_problem(json.dumps(report)) is None


def test_conflicting_duplicate_pid_is_rejected():
    report = _identity()
    duplicate = copy.deepcopy(report["applications"][0])
    duplicate["activationPolicy"] = 1
    report["applications"].append(duplicate)
    assert "duplicate PID" in identity_report_problem(json.dumps(report))


@pytest.mark.parametrize("field", ["pid", "localizedName", "bundleIdentifier", "executablePath", "activationPolicy", "windows"])
def test_missing_application_identity_field_is_rejected(field):
    report = _identity()
    del report["applications"][0][field]
    assert "malformed" in identity_report_problem(json.dumps(report))


@pytest.mark.parametrize("field,value", [("pid", True), ("activationPolicy", "0"), ("activationPolicy", 3), ("windows", "AI Productivity Flow"), ("executablePath", ""), ("localizedName", None)])
def test_malformed_application_identity_field_is_rejected(field, value):
    report = _identity()
    report["applications"][0][field] = value
    assert "malformed" in identity_report_problem(json.dumps(report))


@pytest.mark.parametrize("text", ["", "{}", "[]", "null", "not JSON"])
def test_missing_or_malformed_identity_is_rejected(text):
    assert identity_report_problem(text)


def test_branded_gui_must_own_native_window():
    report = _identity()
    report["applications"][0]["windows"] = []
    report["applications"][0]["windowMetadata"] = []
    assert "own an app window" in identity_report_problem(json.dumps(report))


@pytest.mark.parametrize("seconds", [30, 60])
def test_each_identity_snapshot_is_required(tmp_path, seconds):
    out = _healthy_out(tmp_path)
    (out / f"identity-{seconds}s.json").unlink()
    assert main(["check", str(out)]) == 1


def test_invalid_first_snapshot_cannot_be_hidden_by_valid_second(tmp_path):
    out = _healthy_out(tmp_path)
    report = _identity()
    report["applications"][0]["localizedName"] = "python3"
    (out / "identity-30s.json").write_text(json.dumps(report), encoding="utf-8")
    assert main(["check", str(out)]) == 1


def test_capture_contract_uses_native_identity_without_command_lines():
    root = Path(__file__).resolve().parents[1]
    capture = (root / "scripts/capture_macos_app_identity.swift").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/mac-smoke-test.yml").read_text(encoding="utf-8")
    for field in ("pid", "localizedName", "bundleIdentifier", "executablePath", "activationPolicy", "windows", "frontmost"):
        assert field in capture
    assert "NSWorkspace" in capture
    assert "CGWindowListCopyWindowInfo" in capture
    assert "kCGWindowOwnerPID" in capture
    assert "System Events" not in capture and "AXUIElement" not in capture
    assert '"$t" = 30' in workflow and '"$t" = 60' in workflow
    assert "ps aux" not in workflow
    assert "capture_macos_app_identity.swift" in workflow


def test_frontmost_gui_menu_identity_is_cross_checked():
    report = _identity()
    report["frontmost"]["localizedName"] = "python3"
    assert "menu name" in identity_report_problem(json.dumps(report))


@pytest.mark.parametrize("frontmost", [{}, {"pid": "100", "localizedName": "AI Productivity Flow"}, {"pid": 100, "localizedName": ""}])
def test_malformed_frontmost_identity_is_rejected(frontmost):
    report = _identity()
    report["frontmost"] = frontmost
    assert "malformed" in identity_report_problem(json.dumps(report))


def test_built_bundle_ci_identity_smoke_contract():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    runner = (root / "scripts/run_macos_identity_smoke.py").read_text(encoding="utf-8")
    assert workflow.count("tests/test_macos_app_identity.py") == 2
    assert "run_macos_identity_smoke.py" in workflow
    assert "if: always()" in workflow
    assert "if seconds not in (30, 60):" in runner
    assert '"open", "-n", "-W"' in runner
    assert "check_mac_smoke_artifacts.py" in runner
    assert "_bundle_pids(app_path) - before" in runner
    assert "pkill" not in runner


@pytest.mark.parametrize("wrapper_exit, bundle_pids, expected", [(0, {101}, 1), (None, set(), 1), (None, {100, 101}, 0)])
def test_ci_runner_requires_engine_wrapper_and_bundle_alive(tmp_path, monkeypatch, wrapper_exit, bundle_pids, expected):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner

    bundle = tmp_path / "AI Productivity Flow.app"
    bundle.mkdir()
    out = tmp_path / "out"
    calls = iter([set(), bundle_pids, bundle_pids, set()])
    monkeypatch.setattr(runner.sys, "platform", "darwin")
    from scripts import probe_macos_embedded_runtime
    monkeypatch.setattr(probe_macos_embedded_runtime, "capture_embedded_runtime", lambda *args: None)
    monkeypatch.setattr(runner, "_record_state", lambda *args: None)
    monkeypatch.setattr(runner, "_compile_identity_capture", lambda root, out: out / "identity-capture")
    monkeypatch.setattr(runner, "_collect_diagnostics", lambda *args: None)
    monkeypatch.setattr(runner, "_bundle_pids", lambda path: next(calls))
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    wrapper = SimpleNamespace(poll=lambda: wrapper_exit, terminate=lambda: None, wait=lambda **kwargs: None)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: wrapper)

    def run(command, **kwargs):
        if str(command[0]).endswith("identity-capture"):
            kwargs["stdout"].write(json.dumps(_identity()))
        if "check_mac_smoke_artifacts.py" in str(command[1]):
            exited = "EXITED" in (out / "alive.txt").read_text(encoding="utf-8")
            return SimpleNamespace(returncode=int(exited))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    assert runner.main(["smoke", str(bundle), str(out)]) == expected
    assert ("EXITED" in (out / "alive.txt").read_text(encoding="utf-8")) == bool(expected)


def test_ci_runner_preserves_capture_failure_and_cleans_wrapper_when_inventory_fails(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner

    bundle = tmp_path / "AI Productivity Flow.app"
    bundle.mkdir()
    monkeypatch.setattr(runner.sys, "platform", "darwin")
    from scripts import probe_macos_embedded_runtime
    monkeypatch.setattr(probe_macos_embedded_runtime, "capture_embedded_runtime", lambda *args: None)
    monkeypatch.setattr(runner, "_record_state", lambda *args: None)
    monkeypatch.setattr(runner, "_compile_identity_capture", lambda root, out: out / "identity-capture")
    monkeypatch.setattr(runner, "_collect_diagnostics", lambda *args: None)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    inventories = iter([set(), RuntimeError("inventory unavailable")])

    def inventory(path):
        result = next(inventories)
        if isinstance(result, Exception):
            raise result
        return result

    terminated = []
    wrapper = SimpleNamespace(poll=lambda: None, terminate=lambda: terminated.append(True), wait=lambda **kwargs: None)
    monkeypatch.setattr(runner, "_bundle_pids", inventory)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: wrapper)
    def capture_failure(command, **kwargs):
        if str(command[0]).endswith("identity-capture"):
            raise RuntimeError("original capture failure")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(runner.subprocess, "run", capture_failure)
    with pytest.raises(RuntimeError, match="original capture failure"):
        runner.main(["smoke", str(bundle), str(tmp_path / "out")])
    assert terminated == [True]
    assert "inventory unavailable" in (tmp_path / "out/cleanup-errors.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["universalaccessd", "AppSSODaemon", "GamePolicyAgent"])
def test_unrelated_app_with_omitted_bundle_identifier_is_allowed(name):
    report = _identity()
    report["applications"].append({
        "pid": 342, "localizedName": name, "executablePath": f"/usr/libexec/{name}",
        "activationPolicy": 2, "windows": [],
    })
    assert identity_report_problem(json.dumps(report)) is None


@pytest.mark.parametrize("field,value", [("pid", "342"), ("activationPolicy", None), ("executablePath", "relative")])
def test_unrelated_app_still_requires_valid_scope_fields(field, value):
    report = _identity()
    unrelated = {"pid": 342, "activationPolicy": 2, "executablePath": "/usr/sbin/universalaccessd"}
    unrelated[field] = value
    report["applications"].append(unrelated)
    assert "malformed" in identity_report_problem(json.dumps(report))


def test_capture_optional_string_nil_serialization_contract():
    root = Path(__file__).resolve().parents[1]
    capture = (root / "scripts/capture_macos_app_identity.swift").read_text(encoding="utf-8")
    assert '"bundleIdentifier": app.bundleIdentifier ?? ""' in capture
    assert '"localizedName": app.localizedName ?? ""' in capture
    assert 'window[kCGWindowIsOnscreen as String] as? NSNumber)?.boolValue ?? true' in capture
    assert ".optionOnScreenOnly" in capture


def test_argv_free_os_inventory_finds_unregistered_bundle_process(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    bundle = tmp_path / "AI Productivity Flow.app"
    def inventory(command, **kwargs):
        assert command == ["ps", "-axo", "pid=,ppid=,comm="]
        return SimpleNamespace(stdout=f"100 1 {bundle}/Contents/Resources/runtime/python/bin/python3\n101 1 /usr/bin/python3\n")
    monkeypatch.setattr(runner.subprocess, "run", inventory)
    monkeypatch.setattr(runner, "_process_path", lambda pid: f"{bundle}/Contents/Resources/runtime/python/bin/python3" if pid == 100 else "/usr/bin/python3")
    assert runner._owned_processes(bundle) == [{"pid": 100, "ppid": 1, "executablePath": f"{bundle}/Contents/Resources/runtime/python/bin/python3", "comm": f"{bundle}/Contents/Resources/runtime/python/bin/python3"}]


def test_diagnostic_state_distinguishes_missing_native_registration_from_os_liveness(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="[]"))
    monkeypatch.setattr(runner, "_owned_processes", lambda path, errors=None: [{"pid": 100, "ppid": 1, "executablePath": str(path / "Contents/MacOS/python3")}])
    wrapper = SimpleNamespace(pid=99, poll=lambda: None)
    runner._record_state(tmp_path / "APF.app", tmp_path, wrapper, 5, runner.time.monotonic())
    state = json.loads((tmp_path / "launcher-status-5s.json").read_text(encoding="utf-8"))
    assert state["wrapperReturncode"] is None
    assert state["nativeBundlePids"] == []
    assert state["ownedProcesses"][0]["pid"] == 100


def test_kernel_path_finds_owned_process_when_comm_is_renamed(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    bundle = tmp_path / "APF.app"
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="100 1 AI Productivity Flow\n101 1 python3\n"))
    monkeypatch.setattr(runner, "_process_path", lambda pid: str(bundle) + "/Contents/Resources/runtime/python/bin/python3" if pid == 100 else "/usr/bin/python3")
    result = runner._owned_processes(bundle)
    assert [process["pid"] for process in result] == [100]
    assert result[0]["comm"] == "AI Productivity Flow"


def test_unresolved_kernel_path_is_recorded_as_uncertainty(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="100 1 Python\n"))
    def unresolved(pid):
        raise OSError("path access denied")
    monkeypatch.setattr(runner, "_process_path", unresolved)
    errors = []
    assert runner._owned_processes(tmp_path / "APF.app", errors) == []
    assert errors[0]["pid"] == "100"
    assert "path access denied" in errors[0]["error"]


def test_structured_ips_keeps_exception_and_faulting_stack_with_bounds_and_redaction(tmp_path):
    from scripts import run_macos_identity_smoke as runner
    report = tmp_path / "Python.ips"
    header = {"app_name": "Python", "os_version": "macOS 26.6.2", "timestamp": "2026-10-10"}
    body = {
        "procName": "AI Productivity Flow", "pid": 100, "procPath": "/Applications/APF.app/python3",
        "osVersion": {"train": "macOS 26.6.2"}, "exception": {"type": "EXC_BAD_ACCESS"},
        "termination": {"namespace": "SIGNAL", "code": 11}, "faultingThread": 1,
        "threads": [{"frames": [{"symbol": "not_crashed"}]}, {"triggered": True, "frames":
            [{"symbol": "api_key=fixture-do-not-upload"}, {"symbol": "https://example.test/path?credential=fixture"}]
            + [{"symbol": f"crashed_frame_{index}", "symbolLocation": "x" * 2000} for index in range(80)]}],
    }
    report.write_text(json.dumps(header) + "\n" + json.dumps(body), encoding="utf-8")
    excerpt = runner._crash_excerpt(report)
    assert "EXC_BAD_ACCESS" in excerpt and "SIGNAL" in excerpt and "macOS 26.6.2" in excerpt
    assert "crashed_frame_0" in excerpt and "frame 29:" in excerpt
    assert "frame 30:" not in excerpt and "not_crashed" not in excerpt
    assert "fixture-do-not-upload" not in excerpt and "credential=fixture" not in excerpt
    assert "[query redacted]" in excerpt and "credential-bearing line redacted" in excerpt
    assert len(excerpt) <= 65536 and len(excerpt.splitlines()) <= 120


def test_traditional_crash_keeps_header_and_crashed_thread_after_long_other_stack(tmp_path):
    from scripts import run_macos_identity_smoke as runner
    report = tmp_path / "Python.crash"
    report.write_text("Process: Python [100]\nException Type: EXC_BAD_ACCESS\nTermination Reason: SIGNAL 11\nsecret=fixture-do-not-upload\n"
        + "\n".join(f"other thread line {index}" for index in range(200))
        + "\nThread 3 Crashed:\n" + "\n".join(f"{index} frame_{index}" for index in range(80)), encoding="utf-8")
    excerpt = runner._crash_excerpt(report)
    assert "Exception Type: EXC_BAD_ACCESS" in excerpt and "Termination Reason: SIGNAL 11" in excerpt
    assert "Thread 3 Crashed:" in excerpt and "29 frame_29" in excerpt
    assert "30 frame_30" not in excerpt and "fixture-do-not-upload" not in excerpt
    assert len(excerpt) <= 65536



def _embedded_runtime():
    app = "/Applications/AI Productivity Flow.app"
    return {"executable": app + "/Contents/MacOS/ai-productivity-flow-launcher",
            "prefix": app + "/Contents/Resources/runtime/python", "bundlePath": app,
            "bundleIdentifier": "com.uzerkayat.aiproductivityflow", "CFBundleName": "AI Productivity Flow",
            "CFBundleDisplayName": "AI Productivity Flow", "CFBundleExecutable": "ai-productivity-flow-launcher"}


@pytest.mark.parametrize("field,bad", [
    ("executable", "/Applications/AI Productivity Flow.app/Contents/Resources/runtime/python/bin/python3"),
    ("prefix", "/usr/local"), ("bundlePath", "/Applications/Python.app"),
    ("bundleIdentifier", "org.python.python"), ("CFBundleName", "Python"),
    ("CFBundleDisplayName", "Python"), ("CFBundleExecutable", "python3"),
])
def test_real_embedded_metadata_rejects_wrong_runtime_identity(field, bad):
    from scripts.probe_macos_embedded_runtime import embedded_runtime_problem
    report = _embedded_runtime()
    report[field] = bad
    assert embedded_runtime_problem(json.dumps(report), "/Applications/AI Productivity Flow.app")


def test_branded_in_memory_python_executable_still_fails_native_identity():
    report = _identity()
    report["applications"][0]["executablePath"] = report["appPath"] + "/Contents/Resources/runtime/python/bin/python3"
    assert "outer native launcher" in identity_report_problem(json.dumps(report))


def test_accessory_child_must_also_use_outer_native_launcher():
    report = _identity()
    helper = copy.deepcopy(report["applications"][0])
    helper.update(pid=101, activationPolicy=1, executablePath=report["appPath"] + "/Contents/Resources/runtime/python/bin/python3")
    report["applications"].append(helper)
    assert identity_report_problem(json.dumps(report))


def test_embedded_runtime_evidence_required_by_smoke_checker(tmp_path):
    out = _healthy_out(tmp_path)
    (out / "embedded-runtime.json").unlink()
    assert main(["check", str(out)]) == 1


def test_embedded_runtime_probe_invokes_actual_outer_launcher_without_app_imports(tmp_path, monkeypatch):
    from pathlib import PurePosixPath
    from types import SimpleNamespace
    from scripts import probe_macos_embedded_runtime as probe
    app = PurePosixPath("/Applications/AI Productivity Flow.app")
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        assert kwargs["timeout"] == 15
        return SimpleNamespace(returncode=0, stdout=json.dumps(_embedded_runtime()),
                               stderr="api_key=fixture-do-not-upload\nhttps://example.test/path?credential=fixture\n")
    monkeypatch.setattr(probe.subprocess, "run", run)
    # Resolve a POSIX app path while output stays in the platform's temp fixture;
    # the real metadata validator remains active, including on Windows.
    probe.capture_embedded_runtime(SimpleNamespace(resolve=lambda: app), tmp_path / "out")
    assert commands[0][0] == str(app / "Contents/MacOS/ai-productivity-flow-launcher")
    assert commands[0][1] == "-c"
    assert "from Foundation import NSBundle" in commands[0][2]
    assert "AppKit" not in commands[0][2] and "voice_flow" not in commands[0][2]
    errors = (tmp_path / "out/embedded-runtime-stderr.txt").read_text(encoding="utf-8")
    assert "fixture-do-not-upload" not in errors and "credential=fixture" not in errors
    assert "redacted" in errors


@pytest.mark.parametrize("text", ["", "{}", "[]", "null", "not JSON"])
def test_missing_or_malformed_embedded_runtime_is_rejected(text):
    from scripts.probe_macos_embedded_runtime import embedded_runtime_problem
    assert embedded_runtime_problem(text, "/Applications/AI Productivity Flow.app")



def test_ci_refuses_existing_app_before_embedded_runtime_probe(tmp_path, monkeypatch):
    from scripts import run_macos_identity_smoke as runner
    from scripts import probe_macos_embedded_runtime as probe
    bundle = tmp_path / "AI Productivity Flow.app"
    bundle.mkdir()
    monkeypatch.setattr(runner.sys, "platform", "darwin")
    monkeypatch.setattr(runner, "_bundle_pids", lambda path: {100})
    monkeypatch.setattr(probe, "capture_embedded_runtime", lambda *args: pytest.fail("probe must not execute for a preexisting app"))
    assert runner.main(["smoke", str(bundle), str(tmp_path / "out")]) == 1


def test_release_runtime_probe_preserves_quarantine_diagnostic_order():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/mac-smoke-test.yml").read_text(encoding="utf-8")
    assert workflow.index("Gatekeeper and signing check") < workflow.index("xattr -dr com.apple.quarantine")
    assert workflow.index("xattr -dr com.apple.quarantine") < workflow.index("python3 scripts/probe_macos_embedded_runtime.py")
    assert workflow.index("python3 scripts/probe_macos_embedded_runtime.py") < workflow.index("Launch app and take screenshots")


@pytest.mark.parametrize("field,value", [
    ("ownerPid", 999), ("windowNumber", 0), ("windowNumber", True),
    ("layer", 1), ("onScreen", False), ("alpha", 0), ("width", 1),
    ("height", 1), ("width", "1100"), ("width", float("nan")),
])
def test_native_window_must_be_visible_sized_and_owned_by_gui(field, value):
    report = _identity()
    report["applications"][0]["windowMetadata"][0][field] = value
    assert identity_report_problem(json.dumps(report))


def test_native_window_ownership_survives_privacy_redacted_titles():
    report = _identity()
    report["applications"][0]["windows"] = []
    report["applications"][0]["windowMetadata"][0]["title"] = ""
    assert identity_report_problem(json.dumps(report)) is None
    assert window_report_problem(json.dumps(report)) is None


def test_titles_alone_cannot_satisfy_native_window_gate():
    report = _identity()
    del report["applications"][0]["windowMetadata"]
    assert identity_report_problem(json.dumps(report))


def test_accessory_python_name_is_also_rejected():
    report = _identity()
    helper = copy.deepcopy(report["applications"][0])
    helper.update(pid=101, activationPolicy=1, localizedName="Python")
    report["applications"].append(helper)
    assert "menu name" in identity_report_problem(json.dumps(report))


def test_runner_permission_evidence_is_captured_around_api_import():
    workflow = (Path(__file__).resolve().parents[1]/".github/workflows/ci.yml").read_text(encoding="utf-8")
    before = workflow.index("screen-before-api-import.png")
    imported = workflow.index("from voice_flow.gui.api_server import start_api_server")
    after = workflow.index("screen-after-api-import.png")
    assert before < imported < after < workflow.index("Build macOS Application Bundle")


def test_native_capture_compile_is_bounded_and_uses_workspace_source(tmp_path, monkeypatch):
    from scripts import run_macos_identity_smoke as runner
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/swiftc")
    calls = []
    def compile(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(b"native fixture")
    monkeypatch.setattr(runner.subprocess, "run", compile)
    assert runner._compile_identity_capture(tmp_path, tmp_path) == tmp_path/"identity-capture"
    assert calls[0][0][1] == str(tmp_path/"scripts/capture_macos_app_identity.swift")
    assert calls[0][1] == {"check": True, "timeout": 60}

@pytest.mark.skipif(sys.platform != "darwin", reason="compiles and queries native metadata on macOS")
def test_real_swift_capture_reports_schema_without_launching_app(tmp_path):
    import subprocess
    from scripts import run_macos_identity_smoke as runner
    root=Path(__file__).resolve().parents[1]
    capture=runner._compile_identity_capture(root,tmp_path)
    expected=tmp_path/"Never Launched.app"
    result=subprocess.run([str(capture),str(expected)],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
    report=json.loads(result.stdout)
    assert report["captureSource"] == "CGWindowList"
    assert report["appPath"] == str(expected.resolve())
    assert isinstance(report["applications"],list)
    assert all(type(app["pid"]) is int and type(app["activationPolicy"]) is int for app in report["applications"])
    assert not any(app["executablePath"].startswith(str(expected) + "/") for app in report["applications"])


def test_public_privacy_evidence_is_scoped_bounded_and_redacted(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    entries = [{"eventMessage": "old ignored record"} for _ in range(40)]
    entries += [{"processID": 100, "eventMessage": "org.python local network api_key=fixture-do-not-upload"},
                {"eventMessage": "https://example.test/path?credential=fixture", "privateData": "do-not-copy"}]
    entries += [{"timestamp": str(index), "eventMessage": "LocalNetwork responsible com.uzerkayat.aiproductivityflow " + "x" * 2000}
                for index in range(78)]
    def log(command, **kwargs):
        assert command[:7] == ["/usr/bin/log", "show", "--style", "json", "--info", "--last", "15m"]
        assert "--debug" not in command
        assert kwargs["capture_output"] and kwargs["text"] and kwargs["check"]
        assert 0 < kwargs["timeout"] <= 8
        if "LocalNetwork" in command[-1]:
            assert "process ==" not in command[-1]
            return SimpleNamespace(stdout=json.dumps(entries))
        assert 'process == "nehelper"' in command[-1] and 'process == "tccd"' in command[-1]
        assert "org.python" in command[-1]
        return SimpleNamespace(stdout="[]")
    monkeypatch.setattr(runner.subprocess, "run", log)
    runner._collect_privacy_evidence(tmp_path)
    text = (tmp_path / "local-network-privacy.redacted.txt").read_text(encoding="utf-8")
    assert "old ignored record" not in text and "fixture-do-not-upload" not in text
    assert "credential=fixture" not in text and "do-not-copy" not in text
    assert "credential-bearing line redacted" in text and "[query redacted]" in text
    assert "LocalNetwork responsible" in text
    assert len(text) <= 65536 and len(text.splitlines()) <= 120


def test_public_privacy_evidence_failure_is_best_effort(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    monkeypatch.setattr(runner, "_collect_privacy_evidence", lambda out: (_ for _ in ()).throw(ValueError("fixture unavailable")))
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="fixture version"))
    monkeypatch.setattr(runner.Path, "home", lambda: tmp_path / "home")
    runner._collect_diagnostics(tmp_path / "Never Launched.app", tmp_path, runner.time.time())
    assert "public privacy logs: ValueError: fixture unavailable" in (tmp_path / "diagnostic-errors.txt").read_text(encoding="utf-8")
    assert (tmp_path / "environment.json").is_file()


def test_privacy_phase_screenshots_locate_prompt_before_real_app_launch():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8").split("  macos-build:", 1)[1]
    phases = ["screen-before-api-import.png", "screen-after-api-import.png",
              "screen-after-platform-tests.png", "screen-after-regression-tests.png",
              "screen-after-bundle-build.png", "Verify built macOS native application identity"]
    assert [workflow.index(phase) for phase in phases] == sorted(workflow.index(phase) for phase in phases)
    runner = (root / "scripts/run_macos_identity_smoke.py").read_text(encoding="utf-8")
    assert runner.index("screen-before-app-launch.png") < runner.index("launcher = subprocess.Popen")


def test_network_privacy_query_covers_any_os_process_and_reserves_attribution_budget(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    calls = []
    def log(command, **kwargs):
        calls.append(command)
        if "LocalNetwork" in command[-1]:
            records = [{"processImagePath": "/usr/libexec/UserEventAgent", "subsystem": "com.apple.networkextension",
                        "eventMessage": "LocalNetwork: found bundle id org.python.python"}]
        else:
            records = [{"eventMessage": "old attribution " + str(index)} for index in range(100)]
        return SimpleNamespace(stdout=json.dumps(records))
    monkeypatch.setattr(runner.subprocess, "run", log)
    runner._collect_privacy_evidence(tmp_path)
    records = [json.loads(line) for line in (tmp_path / "local-network-privacy.redacted.txt").read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 2 and len(records) == 41
    assert records[0]["processImagePath"] == "/usr/libexec/UserEventAgent"
    assert records[0]["captureQuery"] == "local-network"
    assert all(record["captureQuery"] == "app-attribution" for record in records[1:])
    assert "old attribution 60" in records[1]["eventMessage"]


def test_public_privacy_queries_share_one_eight_second_deadline(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import run_macos_identity_smoke as runner
    times = iter([0, 1, 9])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(times))
    calls = []
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: calls.append(kwargs) or SimpleNamespace(stdout="[]"))
    with pytest.raises(TimeoutError, match="8 seconds"):
        runner._collect_privacy_evidence(tmp_path)
    assert len(calls) == 1 and calls[0]["timeout"] == 7
