"""macOS application lifecycle: one instance per user, real Quit, no zombies.

The packaged Mac app runs two processes from the same bundle executable:

* the *engine* (``voice_flow.main``): hotkeys, floating bar (Tk), local API,
  llama-server / node / ffmpeg helpers. Cocoa "accessory" app, no Dock icon.
* the *desktop window* (``voice_flow.gui.desktop_launcher``): the pywebview
  window. Cocoa "regular" app with the Dock icon and the app menu.

Rules implemented here (all no-ops off macOS):

* Cmd+Q, the app menu's Quit, Dock > Quit and an Apple Event quit end the
  whole app: the window process tells the engine (``POST /api/app/quit``),
  the engine stops its children, reaps them and exits within seconds.
* Closing the window (red button / Cmd+W) only closes the window. The engine
  keeps dictation running and offers a way back plus a Quit item from its
  menu bar status item and the floating bar's right-click menu.
* One engine per user: an exclusive ``flock`` on ``~/.voice_flow/engine.lock``.
  A second launch (for example the copy inside the DMG while the
  /Applications copy runs) asks the running engine to show its window and
  exits before it registers any hotkey.
* One window process per user: ``~/.voice_flow/desktop.lock`` plus a small
  Unix socket the running window listens on to come to the front.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

IS_MACOS = sys.platform == "darwin"
APP_NAME = "AI Productivity Flow"
BUNDLE_ID = "com.uzerkayat.aiproductivityflow"
ENGINE_LOCK_NAME = "engine.lock"
DESKTOP_LOCK_NAME = "desktop.lock"
DESKTOP_SOCKET_NAME = "desktop.sock"
DEFAULT_PORT = 8991

# Total time a Quit may take before the engine hard-exits regardless.
QUIT_HARD_DEADLINE_SECONDS = 6.0


def _data_dir() -> Path:
    from voice_flow.paths import data_dir

    return data_dir()


# --------------------------------------------------------------------------
# Single instance lock (flock: released by the kernel when the process dies,
# so a crashed or kill -9'd instance can never leave a stale lock behind).
# --------------------------------------------------------------------------

class InstanceLock:
    """An exclusive, non-blocking advisory lock held for the process lifetime."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fd: Optional[int] = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> bool:
        if self._fd is not None:
            return True
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        try:
            # Children must not inherit the lock descriptor: a surviving child
            # would otherwise keep "the app" locked after the engine exited.
            os.set_inheritable(fd, False)
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
        except OSError:
            pass
        self._fd = fd
        return True

    def owner_pid(self) -> Optional[int]:
        try:
            text = self.path.read_text(encoding="utf-8").strip()
            return int(text.split()[0]) if text else None
        except (OSError, ValueError, IndexError):
            return None

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


_engine_lock: Optional[InstanceLock] = None
_desktop_lock: Optional[InstanceLock] = None


def acquire_engine_lock(path: Optional[Path] = None) -> bool:
    """Take the per-user engine lock. True when this process is the engine."""
    global _engine_lock
    if _engine_lock is not None and _engine_lock.held:
        return True
    lock = InstanceLock(path or (_data_dir() / ENGINE_LOCK_NAME))
    try:
        ok = lock.acquire()
    except Exception as exc:  # unreadable data dir must not block startup
        log.warning("[MAC] Engine lock unavailable (%s); continuing without it.", exc)
        return True
    if ok:
        _engine_lock = lock
    return ok


def release_engine_lock() -> None:
    global _engine_lock
    if _engine_lock is not None:
        _engine_lock.release()
        _engine_lock = None


def acquire_desktop_lock(path: Optional[Path] = None) -> bool:
    global _desktop_lock
    if _desktop_lock is not None and _desktop_lock.held:
        return True
    lock = InstanceLock(path or (_data_dir() / DESKTOP_LOCK_NAME))
    try:
        ok = lock.acquire()
    except Exception as exc:
        log.warning("[MAC] Window lock unavailable (%s); continuing without it.", exc)
        return True
    if ok:
        _desktop_lock = lock
    return ok


# --------------------------------------------------------------------------
# Talking to the running engine over the loopback API.
# --------------------------------------------------------------------------

def _post(path: str, *, port: int = DEFAULT_PORT, timeout: float = 1.5, body: Optional[dict] = None) -> Optional[dict]:
    import voice_flow.local_http  # noqa: F401  loopback calls bypass HTTP(S) proxies

    req = urllib.request.Request(
        f"http://127.0.0.1:{int(port)}{path}",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read() or b"{}"
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        data.setdefault("status", res.status)
        return data


def ask_running_engine_to_show_window(
    *, port: int = DEFAULT_PORT, wait_seconds: float = 20.0, poll: float = 0.5,
    post: Callable[..., Optional[dict]] = _post, sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Second launch: bring the existing app forward. Waits while it boots."""
    deadline = clock() + wait_seconds
    while True:
        try:
            data = post("/api/app/open-window", port=port, timeout=2.0)
            if data and data.get("success"):
                return True
        except Exception:
            pass
        if clock() >= deadline:
            return False
        sleep(poll)


def notify_engine_quit(*, port: int = DEFAULT_PORT, reason: str = "window-quit",
                       post: Callable[..., Optional[dict]] = _post) -> bool:
    """The window process asks the engine to end the whole app."""
    try:
        data = post("/api/app/quit", port=port, timeout=1.5, body={"reason": reason})
        return bool(data and data.get("success"))
    except Exception as exc:
        log.debug("[MAC] Quit request to engine failed: %s", exc)
        return False


# --------------------------------------------------------------------------
# Child process hygiene in the engine.
# --------------------------------------------------------------------------

def reap_when_done(process: subprocess.Popen, on_exit: Optional[Callable[[int], None]] = None) -> threading.Thread:
    """Wait for *process* in the background so it never lingers as <defunct>."""

    def _wait() -> None:
        try:
            code = process.wait()
        except Exception:
            code = -1
        if on_exit is not None:
            try:
                on_exit(code)
            except Exception:
                pass

    thread = threading.Thread(target=_wait, daemon=True, name=f"reap-{getattr(process, 'pid', '?')}")
    thread.start()
    return thread


def stop_process(process: Optional[subprocess.Popen], timeout: float = 1.5) -> None:
    """SIGTERM, wait, then SIGKILL; always reaps. Never raises."""
    if process is None:
        return
    try:
        if process.poll() is not None:
            return
        process.terminate()
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        return
    try:
        process.kill()
        process.wait(timeout=timeout)
    except Exception:
        pass


def terminate_descendants(timeout: float = 1.5) -> list[int]:
    """Terminate (then kill) every remaining descendant of this process and reap it."""
    try:
        import psutil
    except Exception:
        return []
    try:
        children = psutil.Process(os.getpid()).children(recursive=True)
    except Exception:
        return []
    pids = []
    for child in children:
        try:
            child.terminate()
            pids.append(child.pid)
        except Exception:
            pass
    try:
        _gone, alive = psutil.wait_procs(children, timeout=timeout)
    except Exception:
        alive = children
    for child in alive:
        try:
            child.kill()
        except Exception:
            pass
    if alive:
        try:
            psutil.wait_procs(alive, timeout=timeout)
        except Exception:
            pass
    # Reap anything that was our direct child (psutil waits do reap, but a
    # child that exited between listing and waiting would still be defunct).
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        except OSError:
            break
        if pid == 0:
            break
    return pids


# --------------------------------------------------------------------------
# Window process: control socket so a second launch can raise the window.
# --------------------------------------------------------------------------

def desktop_socket_path() -> Path:
    return _data_dir() / DESKTOP_SOCKET_NAME


def serve_desktop_control(on_show: Callable[[], None], path: Optional[Path] = None) -> Optional[threading.Thread]:
    """Listen on a per-user Unix socket; every "show" line raises the window."""
    if not hasattr(socket, "AF_UNIX"):
        return None
    sock_path = Path(path or desktop_socket_path())
    try:
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            sock_path.unlink()
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sock_path))
        os.chmod(str(sock_path), 0o600)
        server.listen(4)
    except OSError as exc:
        log.debug("[MAC] Window control socket unavailable: %s", exc)
        return None

    def _loop() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            try:
                conn.settimeout(1.0)
                data = conn.recv(64)
                if data.strip().startswith(b"show"):
                    try:
                        on_show()
                    except Exception:
                        log.debug("[MAC] show handler failed", exc_info=True)
                    conn.sendall(b"ok\n")
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    thread = threading.Thread(target=_loop, daemon=True, name="MacWindowControl")
    thread.start()
    return thread


def send_desktop_show(path: Optional[Path] = None, timeout: float = 1.5) -> bool:
    """Ask the running window process to come to the front."""
    if not hasattr(socket, "AF_UNIX"):
        return False
    sock_path = Path(path or desktop_socket_path())
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(sock_path))
            client.sendall(b"show\n")
            return client.recv(16).startswith(b"ok")
    except OSError:
        return False


def activate_process(pid: int) -> bool:
    """Best-effort: bring another process of this app to the front."""
    if not IS_MACOS:
        return False
    try:
        from AppKit import (
            NSApplicationActivateAllWindows,
            NSApplicationActivateIgnoringOtherApps,
            NSRunningApplication,
        )

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if app is None:
            return False
        app.unhide()
        return bool(app.activateWithOptions_(NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps))
    except Exception:
        return False


def install_terminate_observer(callback: Callable[[], None]) -> bool:
    """Window process: run *callback* when Cocoa terminates the app.

    Cmd+Q, the app menu's Quit, Dock > Quit and the Apple Event quit all go
    through -[NSApplication terminate:], which posts this notification right
    before exit(). Closing the last window stops the run loop instead and
    never posts it, which is how a Quit is told apart from a window close.
    """
    if not IS_MACOS:
        return False
    try:
        from AppKit import NSApplicationWillTerminateNotification
        from Foundation import NSNotificationCenter

        observer = _terminate_observer_class().alloc().init()
        observer.callback = callback
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            observer, "appWillTerminate:", NSApplicationWillTerminateNotification, None
        )
        _keepalive.append(observer)
        return True
    except Exception:
        log.warning("[MAC] Could not watch for app termination", exc_info=True)
        return False


_keepalive: list[Any] = []
_observer_cls: Any = None
_status_target_cls: Any = None


def _terminate_observer_class():
    global _observer_cls
    if _observer_cls is None:
        from Foundation import NSObject

        class APFTerminateObserver(NSObject):  # type: ignore[misc]
            callback = None

            def appWillTerminate_(self, _notification):
                cb = self.callback
                if cb is not None:
                    try:
                        cb()
                    except Exception:
                        pass

        _observer_cls = APFTerminateObserver
    return _observer_cls


# --------------------------------------------------------------------------
# Engine: menu bar status item ("way back" + Quit while the window is closed).
# --------------------------------------------------------------------------

STATUS_MENU_OPEN = f"Open {APP_NAME}"
STATUS_MENU_BAR = "Show Floating Bar"
STATUS_MENU_QUIT = f"Quit {APP_NAME}"


def _status_target_class():
    global _status_target_cls
    if _status_target_cls is None:
        from Foundation import NSObject

        class APFStatusMenuTarget(NSObject):  # type: ignore[misc]
            actions = None

            def openApp_(self, _sender):
                self._run("open")

            def showBar_(self, _sender):
                self._run("bar")

            def quitApp_(self, _sender):
                self._run("quit")

            def _run(self, key):
                fn = (self.actions or {}).get(key)
                if fn is not None:
                    try:
                        fn()
                    except Exception:
                        log.debug("[MAC] status menu action %s failed", key, exc_info=True)

        _status_target_cls = APFStatusMenuTarget
    return _status_target_cls


def _status_icon():
    try:
        from AppKit import NSBundle, NSImage

        path = NSBundle.mainBundle().pathForResource_ofType_("AppIcon", "icns")
        if not path:
            exe = Path(sys.executable).resolve()
            candidate = exe.parent.parent / "Resources" / "AppIcon.icns"
            path = str(candidate) if candidate.is_file() else None
        if not path:
            return None
        image = NSImage.alloc().initWithContentsOfFile_(path)
        if image is None:
            return None
        image.setSize_((18, 18))
        return image
    except Exception:
        return None


def install_status_item(on_open: Callable[[], None], on_quit: Callable[[], None],
                        on_show_bar: Optional[Callable[[], None]] = None) -> Any:
    """Add the menu bar item. Must run on the main (Tk/Cocoa) thread."""
    if not IS_MACOS:
        return None
    try:
        from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength

        target = _status_target_class().alloc().init()
        target.actions = {"open": on_open, "quit": on_quit, "bar": on_show_bar}
        item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = item.button() if hasattr(item, "button") else None
        icon = _status_icon()
        if button is not None:
            if icon is not None:
                button.setImage_(icon)
            else:
                button.setTitle_("APF")
            button.setToolTip_(APP_NAME)
        menu = NSMenu.alloc().initWithTitle_(APP_NAME)
        menu.setAutoenablesItems_(False)
        entries = [(STATUS_MENU_OPEN, "openApp:", "")]
        if on_show_bar is not None:
            entries.append((STATUS_MENU_BAR, "showBar:", ""))
        for title, action, key in entries:
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            mi.setTarget_(target)
            mi.setEnabled_(True)
            menu.addItem_(mi)
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(STATUS_MENU_QUIT, "quitApp:", "q")
        quit_item.setTarget_(target)
        quit_item.setEnabled_(True)
        menu.addItem_(quit_item)
        item.setMenu_(menu)
        _keepalive.extend([target, item, menu])
        log.info("[MAC] Menu bar item installed (Open / Quit %s).", APP_NAME)
        return item
    except Exception:
        log.warning("[MAC] Could not add the menu bar item", exc_info=True)
        return None


def install_tk_app_handlers(root: Any, on_quit: Callable[[], None], on_reopen: Callable[[], None]) -> bool:
    """Route Tk's Apple Event hooks (Quit, Dock/Finder reopen) to the engine."""
    if not IS_MACOS or root is None or not hasattr(root, "createcommand"):
        return False
    ok = True
    for name, fn in (("::tk::mac::Quit", on_quit), ("::tk::mac::ReopenApplication", on_reopen)):
        try:
            root.createcommand(name, fn)
        except Exception:
            ok = False
    return ok
