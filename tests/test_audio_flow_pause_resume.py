"""Tests for Audio Flow pause/resume playback control.

Verifies:
1. TTSEngine pause/resume state machine (guards, MCI forwarding, no process kill).
2. _play_audio uses pausable MCI playback with correct command sequencing.
3. Widget playback-control stage (expand on click, pause toggle, stop).
4. main.py _toggle_audio_flow_pause wiring syncs widget with engine truth.
"""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

from voice_flow import main as main_module
from voice_flow.audio_flow_widget import AudioFlowFloatingWidget
from voice_flow.main import VoiceFlowApp
from voice_flow.tts_engine import TTSEngine


class _FakeWinmm:
    """Records mciSendStringW commands; status replies come from a queue."""

    def __init__(self, statuses: list[str] | None = None) -> None:
        self.commands: list[str] = []
        self._statuses = list(statuses or [])

    def mciSendStringW(self, command: str, buf, _size, _cb) -> int:
        self.commands.append(command)
        if command.startswith("status ") and buf is not None:
            buf.value = self._statuses.pop(0) if self._statuses else "stopped"
        return 0


def _patch_winmm(monkeypatch, statuses: list[str] | None = None) -> _FakeWinmm:
    winmm = _FakeWinmm(statuses)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(winmm=winmm))
    return winmm


def test_pause_resume_state_machine_guards() -> None:
    engine = TTSEngine()

    # Pausing while idle must be a no-op, not a stuck paused flag.
    engine.pause()
    assert engine.is_paused() is False

    # Resuming while not paused must be a no-op.
    engine.resume()
    assert engine.is_paused() is False

    engine._is_speaking = True
    engine._active_mci_alias = "vf_test_alias"
    engine.pause()
    assert engine.is_paused() is True
    engine.resume()
    assert engine.is_paused() is False


def test_pause_forwards_to_mci_and_resume_continues(monkeypatch) -> None:
    winmm = _patch_winmm(monkeypatch)
    engine = TTSEngine()
    engine._is_speaking = True
    engine._active_mci_alias = "vf_alias_x"

    engine.pause()
    assert "pause vf_alias_x" in winmm.commands
    assert engine.is_paused() is True

    engine.resume()
    assert "resume vf_alias_x" in winmm.commands
    assert engine.is_paused() is False


def test_pause_never_terminates_player_process() -> None:
    engine = TTSEngine()
    terminated: list[bool] = []
    engine._player_proc = SimpleNamespace(terminate=lambda: terminated.append(True))
    engine._is_speaking = True

    engine.pause()
    assert engine.is_paused() is True
    assert terminated == []  # pause must suspend, not kill, playback

    engine.stop()
    assert terminated == [True]


def test_play_audio_uses_pausable_mci_path(monkeypatch) -> None:
    statuses = ["playing", "playing", "paused", "stopped"]
    winmm = _patch_winmm(monkeypatch, statuses)
    engine = TTSEngine()
    engine._session = 7

    engine._play_audio(b"RIFF----fake-wav-bytes", session=7)

    assert winmm.commands[0].startswith('open "') and "alias " in winmm.commands[0]
    assert any(c.startswith("play ") for c in winmm.commands)
    assert any(c.startswith("status ") for c in winmm.commands)
    assert winmm.commands[-1].startswith("close ")
    # Alias bookkeeping restored so pause()/stop() reach nothing stale.
    assert engine._active_mci_alias is None


def _controlled_widget() -> tuple[AudioFlowFloatingWidget, SimpleNamespace]:
    widget = AudioFlowFloatingWidget()
    events: SimpleNamespace = SimpleNamespace(
        toggles=[], stops=[], draws=0, geometry=0,
    )
    widget.on_pause_toggle = lambda: events.toggles.append(True)
    widget.on_stop = lambda: events.stops.append(True)
    widget._draw = lambda: setattr(events, "draws", events.draws + 1)
    widget._update_geometry_and_draw = lambda: setattr(events, "geometry", events.geometry + 1)
    widget._is_playing = True
    widget._current_text = "some selected text"
    return widget, events


def test_widget_playing_click_expands_to_playback_controls() -> None:
    widget, events = _controlled_widget()

    widget._on_click(SimpleNamespace(x=17))

    assert widget._stage == AudioFlowFloatingWidget.STAGE_PLAYBACK_CONTROL
    assert widget._get_current_dimensions() == (90, 34)
    assert events.geometry == 1
    assert events.stops == []  # clicking no longer stops instantly


def test_widget_pause_toggle_and_stop_regions() -> None:
    widget, events = _controlled_widget()
    widget._stage = AudioFlowFloatingWidget.STAGE_PLAYBACK_CONTROL

    # Left region: pause, then resume.
    widget._on_click(SimpleNamespace(x=20))
    assert events.toggles == [True]
    assert widget._is_paused is True
    widget._on_click(SimpleNamespace(x=20))
    assert events.toggles == [True, True]
    assert widget._is_paused is False

    # Right region: stop and hide.
    hidden: list[bool] = []
    widget.hide = lambda: hidden.append(True)
    widget._on_click(SimpleNamespace(x=70))
    assert events.stops == [True]
    assert hidden == [True]


def test_widget_set_paused_syncs_only_while_playing() -> None:
    widget = AudioFlowFloatingWidget()
    executed: list[None] = []

    class Root:
        def after(self, _delay: int, callback) -> None:
            executed.append(None)
            callback()

    widget._init_tk = lambda: None  # Skip real Tk window creation (suite pattern).
    widget.attach_root(Root())
    widget._is_playing = True

    widget.set_paused(True)
    assert widget._is_paused is True
    widget.set_paused(True)  # Same state: no redraw churn, still consistent.
    assert widget._is_paused is True
    widget.set_paused(False)
    assert widget._is_paused is False

    # While not playing, set_paused must not stick a stale paused glyph.
    widget._is_playing = False
    widget.set_paused(True)
    assert widget._is_paused is False
    assert executed  # callbacks actually ran on the (fake) UI thread


def _pause_app(monkeypatch, speaking: bool, paused: bool) -> VoiceFlowApp:
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    calls: SimpleNamespace = SimpleNamespace(paused=0, resumed=0, widget_states=[])

    class TTS:
        """Stateful double: is_paused() reflects pause()/resume() like the engine."""

        def __init__(self) -> None:
            self._paused = paused

        def is_speaking(self) -> bool:
            return speaking

        def is_paused(self) -> bool:
            return self._paused

        def pause(self) -> None:
            calls.paused += 1
            self._paused = True

        def resume(self) -> None:
            calls.resumed += 1
            self._paused = False

    monkeypatch.setattr(main_module, "tts_engine", TTS())
    monkeypatch.setattr(
        main_module.audio_flow_widget,
        "set_paused",
        lambda state: calls.widget_states.append(state),
    )
    app._calls = calls
    return app


def test_main_toggle_pauses_while_speaking(monkeypatch) -> None:
    app = _pause_app(monkeypatch, speaking=True, paused=False)
    app._toggle_audio_flow_pause()
    assert app._calls.paused == 1
    assert app._calls.resumed == 0
    assert app._calls.widget_states == [True]


def test_main_toggle_resumes_while_paused(monkeypatch) -> None:
    app = _pause_app(monkeypatch, speaking=True, paused=True)
    app._toggle_audio_flow_pause()
    assert app._calls.resumed == 1
    assert app._calls.paused == 0
    assert app._calls.widget_states == [False]


def test_main_toggle_is_noop_when_not_speaking(monkeypatch) -> None:
    app = _pause_app(monkeypatch, speaking=False, paused=False)
    app._toggle_audio_flow_pause()
    assert app._calls.paused == 0
    assert app._calls.resumed == 0
    assert app._calls.widget_states == [False]
