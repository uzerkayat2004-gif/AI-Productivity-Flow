"""Install and first-launch performance fixes (Oct 18, 2026, v1.0.6 report).

Covers: the non-topmost splash, the warming-up window, the light launcher
import, Sentry's auto-enabling integrations, below-normal engine startup,
the render browser moved out of the installer, and the installer's smaller
file set with precompiled bytecode.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ISS = (ROOT / "release" / "installer" / "apf-setup.iss").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Splash: an ordinary window, never topmost
# --------------------------------------------------------------------------

def _load_splash():
    path = SRC / "voice_flow" / "gui" / "early_splash.py"
    spec = importlib.util.spec_from_file_location("apf_early_splash_perf", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_splash_is_not_topmost_and_has_a_taskbar_button():
    splash = _load_splash()
    assert not splash.SPLASH_EX_STYLE & splash.WS_EX_TOPMOST
    assert not splash.SPLASH_EX_STYLE & splash.WS_EX_TOOLWINDOW
    assert splash.SPLASH_EX_STYLE & splash.WS_EX_APPWINDOW
    assert splash.SPLASH_STYLE & splash.WS_MINIMIZEBOX
    assert splash.SPLASH_STYLE & splash.WS_SYSMENU
    source = (SRC / "voice_flow" / "gui" / "early_splash.py").read_text(encoding="utf-8")
    create = source.split("user32.CreateWindowExW(", 1)[1].split(")", 1)[0]
    assert "SPLASH_EX_STYLE" in create and "SPLASH_STYLE" in create
    assert "0x00000008" not in create  # WS_EX_TOPMOST literal is gone
    # Nothing re-applies HWND_TOPMOST later.
    assert "HWND_TOPMOST" not in source


def test_splash_title_reads_well_but_never_matches_the_app_window():
    splash = _load_splash()
    assert splash.WINDOW_TITLE not in splash.APP_WINDOW_TITLES
    assert splash.WINDOW_TITLE.startswith("AI Productivity Flow")
    # The class stays the reliable check, and an old splash is still recognised.
    assert splash.is_startup_splash("anything", "APFEarlySplash")
    assert splash.is_startup_splash("APFEarlySplash", "Other")
    assert splash.is_startup_splash(splash.WINDOW_TITLE, "Other")
    assert not splash.is_startup_splash("AI Productivity Flow", "Chrome_WidgetWin_1")
    launcher = (ROOT / "release" / "installer" / "launch_apf.pyw").read_text(encoding="utf-8")
    assert '"AI Productivity Flow (starting)"' in launcher and '"APFEarlySplash"' in launcher


def test_splash_and_main_window_share_one_app_id():
    splash = _load_splash()
    launcher = (SRC / "voice_flow" / "gui" / "desktop_launcher.py").read_text(encoding="utf-8")
    assert f"'{splash.APP_USER_MODEL_ID}'" in launcher


# --------------------------------------------------------------------------
# Imports: the launcher stays light, Sentry does not import every library
# --------------------------------------------------------------------------

def _clean_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), env.get("PYTHONPATH", "")])
    env["CI"] = "1"
    env["VOICE_FLOW_CRASH_REPORTS_NO_SEND"] = "1"
    return env


def test_launcher_import_does_not_load_the_api_stack():
    code = (
        "import sys, voice_flow.gui.desktop_launcher as d\n"
        "heavy = [m for m in ('voice_flow.gui.api_server', 'scipy', 'openai', 'huggingface_hub', "
        "'faster_whisper', 'voice_flow.audio') if m in sys.modules]\n"
        "print('HEAVY=' + ','.join(heavy))\n"
        "print('PORT=%s' % d.PORT)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], env=_clean_env(), capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    assert "HEAVY=\n" in result.stdout + "\n", result.stdout
    from voice_flow.gui import api_server, desktop_launcher
    assert desktop_launcher.PORT == api_server.PORT


def test_launcher_api_fallback_imports_on_demand(monkeypatch):
    from voice_flow.gui import api_server, desktop_launcher

    calls = []
    monkeypatch.setattr(api_server, "start_api_server", lambda *a, **k: calls.append((a, k)) or "started")
    assert desktop_launcher.start_api_server(host="127.0.0.1") == "started"
    assert calls == [((), {"host": "127.0.0.1"})]


def test_crash_reporting_turns_off_sentry_auto_enabling_integrations(monkeypatch):
    from voice_flow import crash_reporting

    fake = types.SimpleNamespace(init=MagicMock())
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    monkeypatch.setattr(crash_reporting, "is_crash_reporting_enabled", lambda: True)
    monkeypatch.setattr(crash_reporting, "_CRASH_REPORTING_INITIALIZED", False)
    crash_reporting.init_crash_reporting()
    fake.init.assert_called_once()
    assert fake.init.call_args.kwargs["auto_enabling_integrations"] is False


# --------------------------------------------------------------------------
# Warming-up window
# --------------------------------------------------------------------------

@pytest.fixture
def launcher(monkeypatch):
    from voice_flow.gui import desktop_launcher
    from voice_flow.storage import storage

    monkeypatch.setattr(desktop_launcher, "set_windows_auto_startup", lambda _enable: None)
    monkeypatch.setattr(desktop_launcher, "_defer_autostart_registration", lambda: None)
    monkeypatch.setattr(storage, "get_setting", lambda _key, default=None: True)
    monkeypatch.setattr(desktop_launcher, "_poke_overlay_show", MagicMock())
    monkeypatch.setattr(desktop_launcher, "_poke_keepalive_refresh", MagicMock())
    monkeypatch.delenv("VOICE_FLOW_EARLY_WINDOW", raising=False)
    return desktop_launcher


def test_cold_start_opens_the_window_before_the_engine_is_ready(launcher, monkeypatch):
    engine = {"ready": False, "probes": 0}

    def engine_ready(**_kwargs):
        engine["probes"] += 1
        if engine["probes"] >= 6:
            engine["ready"] = True
        return engine["ready"]

    monkeypatch.setattr(launcher, "is_engine_ready", engine_ready)
    monkeypatch.setattr(launcher, "is_api_server_ready", lambda **_kwargs: True)
    monkeypatch.setattr(launcher, "ensure_backend_running", lambda: True)
    monkeypatch.setattr(launcher.time, "sleep", lambda _s: None)
    webview = MagicMock()
    window = MagicMock()
    webview.create_window.return_value = window

    def load_url(url):
        assert engine["ready"], "app UI loaded before the engine was ready"

    window.load_url.side_effect = load_url
    monkeypatch.setattr(launcher, "webview", webview)

    launcher.launch_desktop_gui()

    # The window was created at once, on the local warming page, with no URL.
    webview.create_window.assert_called_once()
    kwargs = webview.create_window.call_args.kwargs
    assert "url" not in kwargs
    assert 'data-apf-warming="1"' in kwargs["html"]
    assert kwargs["title"] == "AI Productivity Flow"
    assert engine["probes"] == 1  # only the launch probe ran before the window
    webview.start.assert_called_once()
    attach = webview.start.call_args.kwargs["func"]
    assert webview.start.call_args.kwargs["private_mode"] is False

    attach()  # pywebview runs this on its own thread once the window loop is up

    window.load_url.assert_called_once_with(f"http://127.0.0.1:{launcher.PORT}/index.html")
    assert engine["probes"] == 6


def test_warm_engine_still_opens_the_app_url_directly(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "is_engine_ready", lambda **_kwargs: True)
    monkeypatch.setattr(launcher, "is_api_server_ready", lambda **_kwargs: True)
    webview = MagicMock()
    monkeypatch.setattr(launcher, "webview", webview)

    launcher.launch_desktop_gui()

    assert webview.create_window.call_args.kwargs["url"].endswith("/index.html")
    assert "func" not in webview.start.call_args.kwargs


def test_early_window_can_be_turned_off(launcher, monkeypatch):
    monkeypatch.setenv("VOICE_FLOW_EARLY_WINDOW", "0")
    monkeypatch.setattr(launcher, "is_engine_ready", lambda **_kwargs: False)
    monkeypatch.setattr(launcher, "is_api_server_ready", lambda **_kwargs: True)
    monkeypatch.setattr(launcher, "ensure_backend_running", lambda: True)
    sleeps = []
    monkeypatch.setattr(launcher.time, "sleep", sleeps.append)
    webview = MagicMock()
    monkeypatch.setattr(launcher, "webview", webview)

    launcher.launch_desktop_gui()

    assert len(sleeps) == 200  # the old blocking wait
    assert "url" in webview.create_window.call_args.kwargs


def test_background_wait_accepts_api_after_the_engine_deadline(launcher, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(launcher.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(launcher.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(launcher, "is_engine_ready", lambda **_kwargs: False)
    monkeypatch.setattr(launcher, "is_api_server_ready", lambda **_kwargs: True)
    started = MagicMock()
    monkeypatch.setattr(launcher, "start_api_server", started)

    assert launcher._wait_for_backend_in_background(True, 0.0, engine_wait_seconds=5.0) is True
    assert clock["t"] >= 5.0
    started.assert_not_called()


def test_background_wait_starts_the_api_fallback_only_without_an_engine(launcher, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(launcher.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(launcher.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(launcher, "is_engine_ready", lambda **_kwargs: False)
    monkeypatch.setattr(launcher, "is_api_server_ready", lambda **_kwargs: False)
    threads = []

    class FakeThread:
        def __init__(self, *, target, **_kwargs):
            threads.append(target)

        def start(self):
            return None

    monkeypatch.setattr(launcher.threading, "Thread", FakeThread)

    monkeypatch.setattr(launcher, "_is_backend_running", lambda: True)
    assert launcher._wait_for_backend_in_background(True, 0.0, engine_wait_seconds=1.0, max_seconds=3.0) is False
    assert threads == []  # never steal the port from a starting engine

    monkeypatch.setattr(launcher, "_is_backend_running", lambda: False)
    clock["t"] = 0.0
    assert launcher._wait_for_backend_in_background(False, 0.0, engine_wait_seconds=1.0, max_seconds=3.0) is False
    assert threads == [launcher.start_api_server]  # started once


def test_background_wait_stops_when_the_window_closes(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "is_engine_ready", lambda **_kwargs: False)
    monkeypatch.setattr(launcher.time, "sleep", lambda _s: None)
    assert launcher._wait_for_backend_in_background(True, 0.0, is_window_open=lambda: False) is False


def test_warming_page_is_self_contained():
    from voice_flow.gui import desktop_launcher

    html = desktop_launcher.WARMING_HTML
    assert "http" not in html.replace("http-equiv", "")  # no network fetches
    assert "<script src" not in html and "<link" not in html
    assert "#0b0c16" in html  # matches the window background, no white flash


# --------------------------------------------------------------------------
# Engine: below-normal priority while starting, no focus steal
# --------------------------------------------------------------------------

def test_engine_spawn_flags(monkeypatch):
    from voice_flow import startup_priority as sp

    monkeypatch.setattr(sp, "_is_windows", lambda: True)
    monkeypatch.delenv("VOICE_FLOW_STARTUP_PRIORITY", raising=False)
    assert sp.engine_startup_creationflags() == sp.BELOW_NORMAL_PRIORITY_CLASS
    monkeypatch.setenv("VOICE_FLOW_STARTUP_PRIORITY", "normal")
    assert sp.engine_startup_creationflags() == 0
    monkeypatch.setattr(sp, "_is_windows", lambda: False)
    monkeypatch.delenv("VOICE_FLOW_STARTUP_PRIORITY", raising=False)
    assert sp.engine_startup_creationflags() == 0
    assert sp.background_creationflags() == 0


def test_restore_normal_priority_only_raises_a_lowered_process():
    from voice_flow import startup_priority as sp

    class FakeKernel32:
        def __init__(self, current):
            self.current = current
            self.set_to = None

        def GetCurrentProcess(self):
            return 1

        def GetPriorityClass(self, _handle):
            return self.current

        def SetPriorityClass(self, _handle, value):
            self.set_to = value
            return 1

    lowered = FakeKernel32(sp.BELOW_NORMAL_PRIORITY_CLASS)
    assert sp.restore_normal_priority(kernel32=lowered) is True
    assert lowered.set_to == sp.NORMAL_PRIORITY_CLASS
    high = FakeKernel32(0x00000080)  # HIGH_PRIORITY_CLASS set by the user
    assert sp.restore_normal_priority(kernel32=high) is False
    assert high.set_to is None


def test_watchdog_starts_the_engine_below_normal(monkeypatch, tmp_path):
    from voice_flow import startup_priority as sp
    from voice_flow import watchdog

    monkeypatch.setattr(watchdog, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sp, "_is_windows", lambda: True)
    monkeypatch.setattr(watchdog, "prepare_runtime_port", lambda **_k: types.SimpleNamespace(status="free"))
    monkeypatch.setattr(watchdog, "get_pythonw_executable", lambda: "pythonw.exe")
    monkeypatch.setattr(watchdog, "get_silent_windows_spawn_kwargs", lambda: {"creationflags": 0x08000000})
    popen = MagicMock()
    popen.return_value.pid = 4242
    monkeypatch.setattr(watchdog.subprocess, "Popen", popen)

    supervisor = watchdog.WatchdogSupervisor()
    assert supervisor.spawn_voice_flow() is True
    flags = popen.call_args.kwargs["creationflags"]
    assert flags & sp.BELOW_NORMAL_PRIORITY_CLASS
    assert flags & 0x08000000  # still no console window


def test_engine_does_not_focus_a_window_its_launcher_owns(monkeypatch):
    from voice_flow.gui import api_server, desktop_launcher
    from voice_flow.main import VoiceFlowApp
    from voice_flow.video_flow_engine import notebooklm

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.hotkeys = MagicMock()
    app.overlay = MagicMock()
    app._watch_gui_state_file = MagicMock()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(api_server, "start_api_server", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "register_runtime_controller", lambda *a, **k: None)
    monkeypatch.setattr(notebooklm, "start_keepalive_daemon", lambda: False)
    monkeypatch.setattr(notebooklm, "trigger_keepalive_now", lambda *a, **k: False)
    monkeypatch.setattr(desktop_launcher, "_launcher_mutex_held", lambda: True)
    focus = MagicMock(return_value=True)
    monkeypatch.setattr(desktop_launcher, "_focus_existing_window", focus)
    popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(app, "_finish_startup", lambda: None)
    monkeypatch.setattr("voice_flow.hotkeys.platform_input_defaults", lambda: {"ready_line": "x"})

    app.run()

    focus.assert_not_called()
    popen.assert_not_called()


# --------------------------------------------------------------------------
# Installer: no render-browser download, fewer files, bytecode shipped
# --------------------------------------------------------------------------

def test_installer_no_longer_downloads_the_render_browser():
    run = ISS.split("[Run]", 1)[1].split("\n[", 1)[0]
    commands = [line for line in run.splitlines() if line.strip() and not line.lstrip().startswith(";")]
    assert not any("browser ensure" in line or "hyperframes" in line for line in commands)
    # The app's own launch stays a postinstall, nowait step.
    assert any("launch_apf.pyw" in line and "nowait" in line for line in commands)


def test_installer_leaves_out_pip_and_headers():
    files = ISS.split("[Files]", 1)[1].split("\n[", 1)[0]
    runtime = [line for line in files.splitlines() if line.startswith("Source:") and "runtime\\*" in line][0]
    assert "Excludes:" in runtime
    for pattern in ("\\python\\Lib\\site-packages\\pip", "\\python\\include"):
        assert pattern in runtime


def _load_build_script():
    spec = importlib.util.spec_from_file_location("apf_build_windows_release", ROOT / "release" / "build_windows_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prune_staging_removes_only_unused_files(tmp_path):
    build = _load_build_script()
    runtime = tmp_path / "runtime"
    site = runtime / "python" / "Lib" / "site-packages"
    files = {
        site / "scipy" / "signal" / "tests" / "test_x.py": False,
        site / "scipy" / "signal" / "_signaltools.py": True,
        site / "numpy" / "_core" / "tests" / "data" / "a.csv": False,
        site / "numpy" / "testing" / "__init__.py": True,  # numpy.testing is imported at runtime
        site / "Cryptodome" / "SelfTest" / "__init__.py": False,
        site / "pkg" / "__init__.pyi": False,
        site / "voice_flow" / "main.py": True,
        runtime / "hyperframes" / "node_modules" / "zod" / "index.d.ts": False,
        runtime / "hyperframes" / "node_modules" / "zod" / "index.js.map": False,
        runtime / "hyperframes" / "node_modules" / "zod" / "README.md": False,
        runtime / "hyperframes" / "node_modules" / "zod" / "LICENSE.md": True,
        runtime / "hyperframes" / "node_modules" / "zod" / "index.js": True,
        runtime / "python" / "Lib" / "site-packages" / "pkg" / "README.md": True,  # Python packages untouched
    }
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    removed = build.prune_staging_for_install(tmp_path)
    for path, keep in files.items():
        assert path.exists() is keep, path
    assert removed["test_dirs"] == 3
    build.prune_staging_for_install(tmp_path)  # idempotent


def test_bytecode_precompile_uses_checked_hash_for_the_app(tmp_path):
    build = _load_build_script()
    site = tmp_path / "runtime" / "python" / "Lib" / "site-packages"
    package = site / "voice_flow"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    commands = build.compileall_commands(Path(sys.executable), tmp_path)
    assert commands[0][-1].endswith("Lib")
    assert "checked-hash" in commands[1] and str(package) in commands[1]
    subprocess.run(commands[1], check=True, capture_output=True)
    pyc = next(package.rglob("__init__.*.pyc"))
    flags = int.from_bytes(pyc.read_bytes()[4:8], "little")
    assert flags == 0b11  # hash-based, checked against the source


def test_build_runs_prune_and_precompile_before_preflight():
    source = (ROOT / "release" / "build_windows_release.py").read_text(encoding="utf-8")
    main = source.split("def main() -> None:", 1)[1]
    assert main.index("prune_staging_for_install") < main.index("precompile_runtime_bytecode") < main.index("preflight(")


# --------------------------------------------------------------------------
# Render browser: background, idle priority, one download at a time
# --------------------------------------------------------------------------

def test_render_browser_prefetch_is_scheduled_once_on_installed_windows(monkeypatch):
    from voice_flow import runtime_env

    monkeypatch.setattr(runtime_env, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(runtime_env, "is_installed", lambda: True)
    monkeypatch.setattr(runtime_env, "render_browser_cache", lambda: None)
    monkeypatch.setattr(runtime_env, "browser_executable", lambda: None)
    monkeypatch.setattr(runtime_env, "_RENDER_BROWSER_PREFETCH_SCHEDULED", False)
    monkeypatch.delenv("VOICE_FLOW_RENDER_BROWSER_PREFETCH", raising=False)
    timers = []

    class FakeTimer:
        def __init__(self, delay, fn):
            timers.append((delay, fn))
            self.daemon = False
            self.name = ""

        def start(self):
            return None

    monkeypatch.setattr(runtime_env.threading, "Timer", FakeTimer)
    assert runtime_env.schedule_render_browser_prefetch() is True
    assert runtime_env.schedule_render_browser_prefetch() is False  # once per process
    assert timers[0][0] == runtime_env.RENDER_BROWSER_PREFETCH_DELAY_SECONDS >= 300


def test_render_browser_prefetch_skipped_off_windows_or_when_present(monkeypatch):
    from voice_flow import runtime_env

    monkeypatch.setattr(runtime_env, "_RENDER_BROWSER_PREFETCH_SCHEDULED", False)
    monkeypatch.setattr(runtime_env, "sys", types.SimpleNamespace(platform="darwin"))
    assert runtime_env.schedule_render_browser_prefetch() is False
    monkeypatch.setattr(runtime_env, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(runtime_env, "is_installed", lambda: True)
    monkeypatch.setattr(runtime_env, "render_browser_cache", lambda: Path("chrome-headless-shell.exe"))
    assert runtime_env.schedule_render_browser_prefetch() is False


def test_background_render_browser_runs_hidden_at_idle_priority(monkeypatch, tmp_path):
    from voice_flow import runtime_env
    from voice_flow.startup_priority import IDLE_PRIORITY_CLASS

    cli = tmp_path / "hyperframes" / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")
    monkeypatch.setattr(runtime_env, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(runtime_env, "render_browser_cache", lambda: None)
    monkeypatch.setattr(runtime_env, "browser_executable", lambda: None)
    monkeypatch.setattr(runtime_env, "node_executable", lambda: tmp_path / "node.exe")
    monkeypatch.setattr(runtime_env, "runtime_root", lambda: tmp_path)
    run = MagicMock()
    monkeypatch.setattr(subprocess, "run", run)

    runtime_env.ensure_render_browser(background=True)
    flags = run.call_args.kwargs["creationflags"]
    assert flags & IDLE_PRIORITY_CLASS and flags & 0x08000000

    runtime_env.ensure_render_browser()  # on demand: hidden, normal priority
    flags = run.call_args.kwargs["creationflags"]
    assert flags == 0x08000000


def test_engine_restores_priority_before_it_can_spawn_a_window():
    """A Windows child inherits below-normal priority; the window must not."""
    source = (SRC / "voice_flow" / "main.py").read_text(encoding="utf-8")
    run = source.split("    def run(self) -> None:", 1)[1].split("\n    def ", 1)[0]
    assert run.index("self._restore_startup_priority()") < run.index('"voice_flow.gui.desktop_launcher"')
