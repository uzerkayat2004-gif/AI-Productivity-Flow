"""Cocoa identity and process-role regressions without launching a GUI."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from voice_flow.platform import macos_app

SRC = Path(__file__).resolve().parents[1] / "src" / "voice_flow"


@pytest.fixture
def cocoa(monkeypatch):
    monkeypatch.setattr(macos_app, "_identity_configured", False)
    events = []
    base = {"CFBundleName": "Python", "Keep": "value"}
    localized = {"CFBundleName": "python3"}
    bundle = SimpleNamespace(infoDictionary=lambda: base,
                             localizedInfoDictionary=lambda: localized)
    process = SimpleNamespace(setProcessName_=lambda name: events.append(("name", name)))
    app = SimpleNamespace(setActivationPolicy_=lambda policy: events.append(("policy", policy)) or True)

    def shared():
        assert events[0] == ("name", macos_app.APP_NAME)
        assert base["CFBundleName"] == localized["CFBundleName"] == macos_app.APP_NAME
        events.append(("application", None))
        return app

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Foundation", SimpleNamespace(
        NSBundle=SimpleNamespace(mainBundle=lambda: bundle),
        NSProcessInfo=SimpleNamespace(processInfo=lambda: process)))
    monkeypatch.setitem(sys.modules, "AppKit", SimpleNamespace(
        NSApplication=SimpleNamespace(sharedApplication=shared),
        NSApplicationActivationPolicyAccessory=1,
        NSApplicationActivationPolicyRegular=0))
    return events, base, localized, bundle


@pytest.mark.parametrize("role,policy", [("engine", 1), ("desktop", 0)])
def test_identity_precedes_application_and_selects_role(cocoa, role, policy):
    events, base, localized, _ = cocoa
    assert macos_app.configure_macos_app(role)
    assert events == [("name", macos_app.APP_NAME), ("application", None), ("policy", policy)]
    assert base["Keep"] == "value"
    assert base["CFBundleDisplayName"] == localized["CFBundleDisplayName"] == macos_app.APP_NAME


def test_bundle_without_localized_dictionary(cocoa):
    events, _, _, bundle = cocoa
    bundle.localizedInfoDictionary = lambda: None
    # This test uses a sharedApplication stub without a localized-name assertion.
    sys.modules["AppKit"].NSApplication.sharedApplication = lambda: SimpleNamespace(
        setActivationPolicy_=lambda policy: events.append(("policy", policy)) or True)
    assert macos_app.configure_macos_app("engine")
    assert events[-1] == ("policy", 1)


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_platforms_do_not_touch_cocoa(monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setitem(sys.modules, "Foundation", None)
    monkeypatch.setitem(sys.modules, "AppKit", None)
    assert macos_app.configure_macos_app("desktop") is False


def test_missing_cocoa_is_nonfatal(monkeypatch, caplog):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Foundation", None)
    assert macos_app.configure_macos_app("engine") is False
    assert "Could not configure macOS application identity" in caplog.text


def test_rejected_activation_policy_is_reported(cocoa):
    sys.modules["AppKit"].NSApplication.sharedApplication = lambda: SimpleNamespace(
        setActivationPolicy_=lambda policy: False)
    assert macos_app.configure_macos_app("desktop") is False


def test_importing_desktop_focus_helpers_does_not_promote_engine():
    # Execute the actual identity entry guard in isolation from the launcher's
    # unrelated server/config imports. Its __name__ condition is the regression.
    tree = ast.parse((SRC / "gui" / "desktop_launcher.py").read_text(encoding="utf-8"))
    guards = [node for node in tree.body if isinstance(node, ast.If)
              and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                      and child.func.id == "configure_macos_app" for child in ast.walk(node))]
    assert len(guards) == 1
    calls = []
    code = compile(ast.Module(body=guards, type_ignores=[]), "desktop identity guard", "exec")
    exec(code, {"__name__": "voice_flow.gui.desktop_launcher", "configure_macos_app": calls.append})
    assert calls == []
    exec(code, {"__name__": "__main__", "configure_macos_app": calls.append})
    assert calls == ["desktop"]
    guard_line = guards[0].lineno
    webview_import = next(node.lineno for node in ast.walk(tree)
                          if isinstance(node, ast.Import) and any(a.name == "webview" for a in node.names))
    assert guard_line < webview_import


def test_engine_identity_precedes_overlay_import_and_reapplies_after_tk():
    main = (SRC / "main.py").read_text(encoding="utf-8")
    assert main.index('configure_macos_app("engine", apply_policy=False)') < main.index("from voice_flow.overlay import")
    tree = ast.parse((SRC / "overlay.py").read_text(encoding="utf-8"))
    create = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  and node.name == "_create_window")
    calls = [node for node in ast.walk(create) if isinstance(node, ast.Call)]
    tk_call = next(node for node in calls if isinstance(node.func, ast.Attribute) and node.func.attr == "Tk")
    policy_call = next(node for node in calls if isinstance(node.func, ast.Name)
                       and node.func.id == "configure_macos_app")
    assert policy_call.args[0].value == "engine"
    assert policy_call.lineno > tk_call.lineno


def test_policy_reapplication_does_not_rename_after_threads_start(cocoa):
    events, _, _, _ = cocoa
    assert macos_app.configure_macos_app("engine")
    assert macos_app.configure_macos_app("engine")
    assert [event for event in events if event[0] == "name"] == [("name", macos_app.APP_NAME)]
    assert [event for event in events if event[0] == "policy"] == [("policy", 1), ("policy", 1)]


def test_early_engine_branding_leaves_application_creation_to_tk(cocoa, monkeypatch):
    events, base, localized, _ = cocoa
    # Any AppKit import would fail: early engine branding uses Foundation only.
    monkeypatch.setitem(sys.modules, "AppKit", None)
    assert macos_app.configure_macos_app("engine", apply_policy=False)
    assert events == [("name", macos_app.APP_NAME)]
    assert base["CFBundleName"] == localized["CFBundleName"] == macos_app.APP_NAME
