from __future__ import annotations
import threading
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.storage import storage

class FakeRoot:
    def __init__(self): self.pending = []
    def after(self, delay, callback):
        self.pending.append((delay, callback))
        return len(self.pending)

class FakeCanvas:
    def __init__(self): self.frames = 0
    def delete(self, *args): self.frames += 1
    def config(self, **kwargs): pass
    def __getattr__(self, name):
        if name.startswith('create_'): return lambda *args, **kwargs: None
        raise AttributeError(name)

def bar_fixture(monkeypatch):
    root = FakeRoot()
    bar = FloatingOverlayBar(root)
    bar.canvas = FakeCanvas()
    bar.win = object()
    bar._mainloop_running = True
    bar._main_thread_id = threading.get_ident()
    monkeypatch.setattr(bar, '_bring_to_top', lambda: None)
    monkeypatch.setattr(bar, '_position_window', lambda: None)
    return bar, root

def test_ui_thread_recording_start_draws_without_event_queue_roundtrip(monkeypatch):
    bar, root = bar_fixture(monkeypatch)
    monkeypatch.setattr(storage, 'get_setting', lambda key, default=None: default)
    bar.show_recording()
    assert bar.state == 'RECORDING'
    assert bar.canvas.frames == 1
    assert [delay for delay, _ in root.pending] == [66]

def test_recording_frame_uses_one_theme_snapshot(monkeypatch):
    bar, root = bar_fixture(monkeypatch)
    reads = []
    monkeypatch.setattr(storage, 'get_setting', lambda key, default=None: reads.append(key) or 'light')
    bar.state = 'RECORDING'
    bar._draw()
    assert len(reads) <= 1, f'{len(reads)} synchronous settings reads for one recording frame'

def test_worker_thread_recording_is_dispatched_to_ui(monkeypatch):
    bar, root = bar_fixture(monkeypatch)
    monkeypatch.setattr(storage, 'get_setting', lambda key, default=None: default)
    worker = threading.Thread(target=bar.show_recording)
    worker.start()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert bar.state == 'HIDDEN'
    assert root.pending[0][0] == 0
    root.pending.pop(0)[1]()
    assert bar.state == 'RECORDING'
    assert bar.canvas.frames == 1


def test_old_animation_and_completion_do_not_stomp_new_recording(monkeypatch):
    bar, root = bar_fixture(monkeypatch)
    monkeypatch.setattr(storage, 'get_setting', lambda key, default=None: default)
    # Exercise callbacks at their real seam without tying this stress test to
    # whether the same-thread dispatcher performs an event-loop roundtrip.
    monkeypatch.setattr(bar, '_run_on_ui', lambda callback: callback())
    for _ in range(20):
        bar.show_done()
        bar.show_recording()
        bar.show_error('recoverable')
        bar.show_recording()
    pending = root.pending[:]
    root.pending.clear()
    frames = bar.canvas.frames
    for _, callback in pending:
        callback()
    assert bar.state == 'RECORDING'
    assert bar.canvas.frames - frames <= 1
    assert len(root.pending) == 1


def test_theme_cache_expires_refreshes_and_tracks_account(monkeypatch):
    bar, root = bar_fixture(monkeypatch)
    clock = [100.0]
    theme = ['light']
    reads = []
    monkeypatch.setattr('voice_flow.overlay.time.monotonic', lambda: clock[0])
    monkeypatch.setattr(storage, 'get_setting', lambda key, default=None: reads.append(key) or theme[0])
    assert bar._is_theme_dark() is False
    for _ in range(100):
        assert bar._is_theme_dark() is False
    assert len(reads) == 1
    theme[0] = 'dark'
    clock[0] += 1.1
    assert bar._is_theme_dark() is True
    theme[0] = 'light'
    monkeypatch.setattr(storage, 'db_path', 'fake-account.db')
    assert bar._is_theme_dark() is False
    theme[0] = 'dark'
    bar.refresh()
    assert bar._is_theme_dark() is True
