"""macOS app lifecycle: single instance, real Quit, reaped children, login item.

These run on any POSIX host: the Mac-only code paths are exercised by
patching ``sys.platform`` or calling the platform helpers directly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX process semantics (flock, AF_UNIX, zombies)")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

from voice_flow.platform import macos_lifecycle as ml  # noqa: E402


# ---------------------------------------------------------------- locks

def test_instance_lock_is_exclusive_and_released_on_close(tmp_path):
    first = ml.InstanceLock(tmp_path / "engine.lock")
    second = ml.InstanceLock(tmp_path / "engine.lock")
    assert first.acquire()
    assert first.owner_pid() == os.getpid()
    assert not second.acquire(), "a second engine must not get the lock"
    first.release()
    assert second.acquire(), "lock must be free once the owner releases it"
    second.release()


def test_instance_lock_is_released_when_owner_process_dies(tmp_path):
    lock_path = tmp_path / "engine.lock"
    code = (
        "import sys, time; sys.path.insert(0, %r)\n"
        "from voice_flow.platform.macos_lifecycle import InstanceLock\n"
        "l = InstanceLock(%r); assert l.acquire(); print('held', flush=True); time.sleep(60)\n"
    ) % (str(SRC), str(lock_path))
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "held"
        probe = ml.InstanceLock(lock_path)
        assert not probe.acquire(), "lock held by a live process must block a second copy"
        proc.kill()
        proc.wait(5)
        assert probe.acquire(), "kill -9 of the owner must not leave a stale lock"
        probe.release()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(5)


def test_lock_descriptor_is_not_inherited_by_children(tmp_path):
    lock = ml.InstanceLock(tmp_path / "engine.lock")
    assert lock.acquire()
    try:
        assert os.get_inheritable(lock._fd) is False
    finally:
        lock.release()


# ---------------------------------------------------------- second launch

def test_second_launch_asks_running_engine_to_show_window():
    calls = []

    def post(path, **kw):
        calls.append(path)
        return {"success": len(calls) >= 3}  # engine still booting for 2 polls

    t = [0.0]
    ok = ml.ask_running_engine_to_show_window(post=post, sleep=lambda s: t.__setitem__(0, t[0] + s),
                                              clock=lambda: t[0], wait_seconds=5)
    assert ok and calls == ["/api/app/open-window"] * 3


def test_second_launch_gives_up_without_hanging():
    t = [0.0]

    def post(path, **kw):
        raise OSError("refused")

    ok = ml.ask_running_engine_to_show_window(post=post, sleep=lambda s: t.__setitem__(0, t[0] + s),
                                              clock=lambda: t[0], wait_seconds=3)
    assert ok is False


def test_engine_main_exits_when_lock_held(monkeypatch):
    import voice_flow.main as main_mod

    shown = []
    monkeypatch.setattr(ml, "acquire_engine_lock", lambda: False)
    monkeypatch.setattr(ml, "ask_running_engine_to_show_window", lambda **kw: shown.append(1) or True)
    assert main_mod._mac_take_engine_lock() is False
    assert shown == [1]


def test_engine_main_does_not_start_second_engine_on_compatible_port(monkeypatch):
    """Mac: a live engine (old copy without the lock) means show it, never start a 2nd."""
    import voice_flow.main as main_mod
    import voice_flow.runtime_guard as rg

    monkeypatch.setattr(main_mod.sys, "platform", "darwin")
    monkeypatch.setattr(rg, "prepare_runtime_port", lambda **kw: SimpleNamespace(status="compatible"))
    shown = []
    monkeypatch.setattr(main_mod, "_mac_show_running_instance", lambda: shown.append(1) or True)
    started = []
    monkeypatch.setattr(main_mod, "VoiceFlowApp", lambda *a, **k: started.append(1))
    monkeypatch.setattr(sys, "argv", ["voice_flow.main"])
    main_mod.main()
    assert shown == [1] and started == []


# ------------------------------------------------------------- quit API

class _FakeHandler:
    def __init__(self):
        self.sent = None

    def send_json_response(self, payload, status=200):
        self.sent = (status, payload)


def _post_api(monkeypatch, path, controller, platform="darwin", body=b"{}"):
    import voice_flow.gui.api_server as api

    monkeypatch.setattr(api, "runtime_controller", controller)
    monkeypatch.setattr(api.sys, "platform", platform)
    handler = api.VoiceFlowApiHandler.__new__(api.VoiceFlowApiHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
    import io
    handler.rfile = io.BytesIO(body)
    sent = []
    handler.send_json_response = lambda payload, status=200: sent.append((status, payload))
    handler.client_address = ("127.0.0.1", 5555)
    return api, handler, sent


def test_quit_endpoint_calls_request_quit_on_mac(monkeypatch):
    calls = []
    controller = SimpleNamespace(request_quit=lambda reason: calls.append(reason) or True,
                                 open_desktop_window=lambda: True)
    api, handler, sent = _post_api(monkeypatch, "/api/app/quit", controller, body=b'{"reason":"window-quit"}')
    handler.do_POST()
    assert calls == ["window-quit"]
    assert sent[-1] == (200, {"success": True})


def test_open_window_endpoint_on_mac(monkeypatch):
    calls = []
    controller = SimpleNamespace(request_quit=lambda reason: True,
                                 open_desktop_window=lambda: calls.append(1) or True)
    api, handler, sent = _post_api(monkeypatch, "/api/app/open-window", controller)
    handler.do_POST()
    assert calls == [1] and sent[-1][0] == 200


def test_quit_endpoint_not_available_on_windows(monkeypatch):
    calls = []
    controller = SimpleNamespace(request_quit=lambda reason: calls.append(reason) or True)
    api, handler, sent = _post_api(monkeypatch, "/api/app/quit", controller, platform="win32")
    handler.do_POST()
    assert calls == [] and sent[-1][0] == 404


# ------------------------------------------------- engine quit + reaping

def _bare_app():
    import voice_flow.main as main_mod

    app = main_mod.VoiceFlowApp.__new__(main_mod.VoiceFlowApp)
    app.overlay = SimpleNamespace(hide=lambda: None, show=lambda: None, root=None)
    app.stop = lambda: None
    return main_mod, app


def test_request_quit_kills_window_children_and_exits(monkeypatch):
    main_mod, app = _bare_app()
    window = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    app._desktop_proc = window
    exited = threading.Event()
    codes = []
    monkeypatch.setattr(app, "_final_exit", lambda code=0: (codes.append(code), exited.set()))
    t0 = time.monotonic()
    assert app.request_quit("test") is True
    assert app.request_quit("again") is True  # idempotent
    assert exited.wait(8), "quit must finish well within the hard deadline"
    assert time.monotonic() - t0 < ml.QUIT_HARD_DEADLINE_SECONDS
    assert codes == [0]
    assert window.poll() is not None, "window process must be stopped on Quit"
    assert helper.poll() is not None, "helper processes (llama-server, node, ffmpeg) must be stopped"
    assert app._shutdown_requested is True


def test_window_close_reaps_child_no_zombie(monkeypatch):
    """Closing the window ends the window process; the engine must reap it."""
    main_mod, app = _bare_app()
    monkeypatch.setattr(main_mod.sys, "platform", "darwin")
    import voice_flow.watchdog as wd
    monkeypatch.setattr(wd, "get_pythonw_executable", lambda: sys.executable)
    monkeypatch.setattr(wd, "get_pythonw_env", lambda *a, **k: dict(os.environ))
    real_popen = subprocess.Popen

    def fake_popen(args, **kw):
        return real_popen([sys.executable, "-c", "pass"], **{k: v for k, v in kw.items() if k in ("env",)})

    monkeypatch.setattr(main_mod.subprocess, "Popen", fake_popen)
    assert app._spawn_desktop_window()
    proc = app._desktop_proc
    deadline = time.time() + 5
    while time.time() < deadline and getattr(app, "_desktop_proc", None) is not None:
        time.sleep(0.05)
    assert app._desktop_proc is None
    assert proc.returncode is not None, "exited window process must be reaped (no <defunct>)"
    import psutil
    assert not any(c.pid == proc.pid for c in psutil.Process().children())


def test_open_desktop_window_raises_existing_or_spawns(monkeypatch):
    main_mod, app = _bare_app()
    monkeypatch.setattr(ml, "send_desktop_show", lambda *a, **k: False)
    spawned = []
    monkeypatch.setattr(app, "_spawn_desktop_window", lambda: spawned.append(1) or True)
    assert app.open_desktop_window() is True and spawned == [1]

    monkeypatch.setattr(ml, "send_desktop_show", lambda *a, **k: True)
    spawned.clear()
    assert app.open_desktop_window() is True and spawned == []

    app._shutdown_requested = True
    assert app.open_desktop_window() is False


def test_stop_process_and_descendants_leave_no_zombies():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    ml.stop_process(proc, timeout=2)
    assert proc.returncode is not None
    stubborn = subprocess.Popen([sys.executable, "-c",
                                 "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])
    time.sleep(0.3)
    pids = ml.terminate_descendants(timeout=0.5)
    assert stubborn.pid in pids
    stubborn.wait(3)
    import psutil
    assert not [c for c in psutil.Process().children() if c.status() == psutil.STATUS_ZOMBIE]


# ------------------------------------------------- window control socket

def test_window_control_socket_raises_window(tmp_path):
    sock = tmp_path / "d.sock"
    shown = threading.Event()
    assert ml.serve_desktop_control(shown.set, path=sock) is not None
    assert ml.send_desktop_show(path=sock) is True
    assert shown.wait(2)
    assert ml.send_desktop_show(path=tmp_path / "missing.sock") is False


def test_duplicate_window_launcher_exits(monkeypatch):
    import voice_flow.gui.desktop_launcher as dl

    monkeypatch.setattr(dl.sys, "platform", "darwin")
    monkeypatch.setattr(ml, "acquire_desktop_lock", lambda *a, **k: False)
    raised = []
    monkeypatch.setattr(ml, "send_desktop_show", lambda *a, **k: raised.append(1) or True)
    assert dl._mac_window_already_running() is True and raised == [1]
    with pytest.raises(SystemExit):
        dl._run_desktop_launcher()


def test_window_quit_notifies_engine():
    calls = []
    assert ml.notify_engine_quit(post=lambda path, **kw: calls.append((path, kw.get("body"))) or {"success": True})
    assert calls == [("/api/app/quit", {"reason": "window-quit"})]
    assert ml.notify_engine_quit(post=lambda *a, **k: (_ for _ in ()).throw(OSError())) is False


def test_mac_engine_lock_probe_used_by_desktop_backend_check(monkeypatch, tmp_path):
    import voice_flow.gui.desktop_launcher as dl

    monkeypatch.setattr(dl.sys, "platform", "darwin")
    monkeypatch.setattr(dl, "_data_dir", lambda: tmp_path)
    assert dl._mac_engine_lock_held() is False
    holder = ml.InstanceLock(tmp_path / ml.ENGINE_LOCK_NAME)
    assert holder.acquire()
    try:
        assert dl._mac_engine_lock_held() is True
    finally:
        holder.release()


def test_tk_apple_event_handlers_registered(monkeypatch):
    monkeypatch.setattr(ml, "IS_MACOS", True)
    registered = {}
    root = SimpleNamespace(createcommand=lambda name, fn: registered.__setitem__(name, fn))
    assert ml.install_tk_app_handlers(root, lambda: "q", lambda: "r")
    assert registered["::tk::mac::Quit"]() == "q"
    assert registered["::tk::mac::ReopenApplication"]() == "r"


# ------------------------------------------------------------- login item

def test_login_item_uses_bundle_id_and_migrates_legacy(monkeypatch, tmp_path):
    import voice_flow.platform.macos as mac

    monkeypatch.setattr(mac, "IS_MACOS", True)
    monkeypatch.setenv("HOME", str(tmp_path))
    ran = []
    monkeypatch.setattr(mac, "_run", lambda cmd, **kw: ran.append(cmd))
    backend = mac.MacOSBackend.__new__(mac.MacOSBackend)
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    legacy = agents / "com.voiceflow.app.plist"
    legacy.write_text("<plist/>")
    assert backend.get_launch_at_login() is True
    assert backend.migrate_legacy_login_item() is True
    new = agents / "com.uzerkayat.aiproductivityflow.plist"
    assert new.exists() and not legacy.exists()
    assert "<string>com.uzerkayat.aiproductivityflow</string>" in new.read_text()
    assert not any("load" in c for c in ran), "enabling must not launchctl-load (would start a 2nd copy)"
    assert backend.set_launch_at_login(False) is True
    assert not new.exists() and backend.get_launch_at_login() is False
    assert not any("unload" in c for c in ran), "disabling must not SIGTERM the running app"


# ---------------------------------------------------- bytecode in bundle

def test_launchers_disable_bytecode_writes():
    c_src = (ROOT / "scripts" / "native_macos_launcher.c").read_text()
    assert 'setenv("PYTHONDONTWRITEBYTECODE", "1", 1)' in c_src
    build = (ROOT / "scripts" / "build_macos_app.py").read_text()
    assert "export PYTHONDONTWRITEBYTECODE=1" in build
    assert '"--invalidation-mode", "unchecked-hash"' in build
    assert "precompile_bundle_bytecode()" in build


# -------------------------------------------- startup console noise (UI)

def test_api_me_optional_probe_is_not_an_error():
    import voice_flow.google_auth as ga

    sent = []
    orig = ga._send_json
    try:
        ga._send_json = lambda handler, payload, status=200, **kw: sent.append((status, payload))
        orig_current = ga.current_user
        ga.current_user = lambda handler: None
        ga.handle_me(object(), optional=True)
        ga.handle_me(object())
    finally:
        ga._send_json = orig
        ga.current_user = orig_current
    assert sent[0][0] == 200 and sent[0][1]["authenticated"] is False
    assert sent[1][0] == 401


def test_video_page_makes_no_render_calls_when_gated_on_mac():
    js = (SRC / "voice_flow" / "gui" / "video-flow.js").read_text()
    assert 'fetch("/api/me?optional=1"' in js
    i = js.index("async function analyzeSourceDocument")
    body = js[i:i + 2000]
    assert "vfVideoFlowGatedOnMac" in body and "!vfGated" in body
    j = js.index('"/api/video-flow/documents/extract"')
    assert "vfVideoFlowGatedOnMac" in js[j - 900:j]


def test_pyobjc_classes_have_valid_selector_prototypes():
    """PyObjC turns every method into a selector: arg count must equal colons.

    A helper method like ``_run(self, key)`` raised BadPrototypeError on a real
    Mac and the menu bar item was never added.
    """
    import ast

    tree = ast.parse((SRC / "voice_flow" / "platform" / "macos_lifecycle.py").read_text())
    checked = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(getattr(b, "id", "") == "NSObject" for b in node.bases):
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef):
                    decorators = [ast.unparse(d) for d in fn.decorator_list]
                    if any("python_method" in d for d in decorators):
                        continue
                    colons = fn.name.lstrip("_").count("_")  # leading "_" is not a colon
                    args = len(fn.args.args) - 1
                    assert colons == args, f"{node.name}.{fn.name}: {args} args but selector has {colons} colons"
                    checked += 1
    assert checked >= 4


def test_floating_bar_menu_offers_open_and_quit(monkeypatch):
    import voice_flow.overlay as ov

    items, popups = [], []

    class FakeMenu:
        def __init__(self, *a, **k): pass
        def add_command(self, label, command): items.append((label, command))
        def add_separator(self): items.append(("-", None))
        def tk_popup(self, x, y): popups.append((x, y))
        def grab_release(self): pass

    monkeypatch.setattr(ov.tk, "Menu", FakeMenu)
    bar = ov.FloatingOverlayBar.__new__(ov.FloatingOverlayBar)
    bar.root = object()
    calls = []
    bar.app_menu_actions = {"open": lambda: calls.append("open"), "quit": lambda: calls.append("quit")}
    assert bar._show_app_menu(SimpleNamespace(x_root=10, y_root=20)) == "break"
    assert popups == [(10, 20)]
    labels = [label for label, _ in items]
    assert labels == ["Open AI Productivity Flow", "-", "Quit AI Productivity Flow"]
    items[0][1](); items[2][1]()
    assert calls == ["open", "quit"]
    # Bound for right-click (Tk 8.6 = Button-2, Tk 9 = Button-3) and Control-click on Mac only.
    src = (SRC / "voice_flow" / "overlay.py").read_text()
    for seq in ("<ButtonPress-2>", "<ButtonPress-3>", "<Control-ButtonPress-1>", "<Control-ButtonRelease-1>"):
        assert f'self.canvas.bind("{seq}"' in src


def test_quit_stops_watchdog_parent_only(monkeypatch):
    import psutil

    terminated = []

    class P:
        def __init__(self, cmd): self._cmd = cmd
        def cmdline(self): return self._cmd
        def terminate(self): terminated.append(self._cmd)

    monkeypatch.setattr(psutil, "Process", lambda pid: P(["launcher", "-m", "voice_flow.watchdog"]))
    assert ml.stop_supervisor_parent() is True
    monkeypatch.setattr(psutil, "Process", lambda pid: P(["/sbin/launchd"]))
    assert ml.stop_supervisor_parent() is False
    assert terminated == [["launcher", "-m", "voice_flow.watchdog"]]


# ---------------------------------------------------------------- bar right-click

def test_right_click_on_bar_opens_menu_via_cocoa_monitor(monkeypatch):
    """Aqua does not hand a right-click on the bar to Tk; the NSEvent monitor does.

    The monitor runs inside Tcl_DoOneEvent with the Tcl lock held, so it must
    not call Tk (a winfo/after call there deadlocked the engine on a real Mac);
    it only queues the menu for the UI pump."""
    import queue
    import voice_flow.overlay as ov

    bar = ov.FloatingOverlayBar.__new__(ov.FloatingOverlayBar)

    class NoTk:
        def __getattr__(self, name):
            raise AssertionError(f"Tk call {name} from inside the Cocoa monitor")

    bar.win = NoTk()
    bar.root = NoTk()
    bar._ui_dispatcher = SimpleNamespace(pending=queue.Queue())
    shown = []
    monkeypatch.setattr(bar, "_show_app_menu", lambda ev: shown.append((ev.x_root, ev.y_root)), raising=False)
    assert bar._mac_secondary_click(512, 692, True) is True     # on the pill: swallow, queue menu
    assert bar._mac_secondary_click(100, 100, False) is False   # elsewhere: pass through
    assert bar._ui_dispatcher.pending.qsize() == 1
    bar._ui_dispatcher.pending.get_nowait()()
    assert shown == [(512, 692)]
    src = (SRC / "voice_flow" / "overlay.py").read_text()
    assert "addLocalMonitorForEventsMatchingMask_handler_" in src
    assert "self._mac_install_menu_monitor()" in src
    handler_src = src[src.index("def _handler(event):"):src.index("self._mac_menu_handler = _handler")]
    for forbidden in ("winfo", ".after(", "self.root", "self.win.", "submit("):
        assert forbidden not in handler_src


def test_audio_player_quit_ends_whole_app_and_is_reaped(monkeypatch):
    import voice_flow.audio_summary_player as asp

    observed = []
    monkeypatch.setattr(ml, "install_terminate_observer", lambda cb: observed.append(cb) or True)
    posts = []
    monkeypatch.setattr(ml, "notify_engine_quit", lambda **k: posts.append(k) or True)
    assert asp._install_mac_player_quit("http://127.0.0.1:8991") is True
    observed[0]()
    assert posts == [{"port": 8991, "reason": "player-quit"}]
    src = (SRC / "voice_flow" / "audio_summary_player.py").read_text()
    assert "reap_when_done(proc)" in src


def test_bar_menu_not_opened_twice_for_one_click(monkeypatch):
    import voice_flow.overlay as ov

    popups = []

    class FakeMenu:
        def __init__(self, *a, **k): pass
        def add_command(self, label, command): pass
        def add_separator(self): pass
        def tk_popup(self, x, y): popups.append((x, y))
        def grab_release(self): pass

    monkeypatch.setattr(ov.tk, "Menu", FakeMenu)
    bar = ov.FloatingOverlayBar.__new__(ov.FloatingOverlayBar)
    bar.root = object()
    bar.app_menu_actions = {"open": lambda: None, "quit": lambda: None}
    ev = SimpleNamespace(x_root=1, y_root=2)
    bar._show_app_menu(ev)
    bar._show_app_menu(ev)  # Tk binding + Cocoa monitor for the same click
    assert popups == [(1, 2)]


# ---------------------------------------------------------------- Settings > Restart

def test_relaunch_command_uses_app_bundle(tmp_path):
    exe = tmp_path / "AI Productivity Flow.app" / "Contents" / "MacOS" / "ai-productivity-flow-launcher"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert ml.relaunch_command(str(exe)) == ["/usr/bin/open", str(tmp_path / "AI Productivity Flow.app")]
    plain = tmp_path / "python3"
    plain.write_text("")
    assert ml.relaunch_command(str(plain)) == [str(plain), "-m", "voice_flow.main"]


def test_engine_pid_comes_from_engine_lock(tmp_path):
    lock = ml.InstanceLock(tmp_path / "engine.lock")
    assert lock.acquire()
    try:
        assert ml.engine_pid(tmp_path / "engine.lock") == os.getpid()
    finally:
        lock.release()
    (tmp_path / "other.lock").write_text("424242\n")
    assert ml.engine_pid(tmp_path / "other.lock") == 424242


def test_relaunch_waits_for_engine_pid_and_survives_quit(tmp_path):
    import psutil

    engine = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
    marker = tmp_path / "relaunched"
    assert ml.spawn_relaunch_after_exit(
        engine.pid, [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ok')"], max_wait=10)
    # The waiter is not our descendant, so Quit's terminate_descendants() spares it.
    kids = [p.pid for p in psutil.Process().children(recursive=True)]
    assert kids == [engine.pid]
    time.sleep(0.8)
    assert not marker.exists()          # engine still running: not relaunched yet
    engine.wait()
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.read_text() == "ok"


def test_restart_on_mac_quits_real_engine_then_relaunches(monkeypatch, tmp_path):
    from voice_flow import lifecycle

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(lifecycle, "data_dir", lambda: tmp_path)
    spawned, quits = [], []
    monkeypatch.setattr(ml, "engine_pid", lambda path=None: 4321)
    monkeypatch.setattr(ml, "relaunch_command", lambda executable=None: ["/usr/bin/open", "/Applications/X.app"])
    monkeypatch.setattr(ml, "spawn_relaunch_after_exit", lambda pid, cmd, **k: spawned.append((pid, cmd)) or True)
    swept = []
    monkeypatch.setattr(lifecycle, "terminate_suite_processes", lambda *a, **k: swept.append(1) or [])
    controller = SimpleNamespace(request_quit=lambda reason: quits.append(reason) or True)
    assert lifecycle.restart_suite(controller) is True
    time.sleep(0.8)
    assert spawned == [(4321, ["/usr/bin/open", "/Applications/X.app"])]
    assert quits == ["restart"]
    assert swept == []  # no process-name sweep on the Mac
