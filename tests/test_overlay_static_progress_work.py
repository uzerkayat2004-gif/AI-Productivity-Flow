from types import SimpleNamespace
from unittest.mock import patch
import pytest
import voice_flow.overlay as module
from test_overlay_saved_center_bottom import FakeCanvas, FakeWin, FakeRoot

class Root(FakeRoot):
    def __init__(self): self.delays=[]
    def after(self, delay, callback): self.delays.append(delay); return "scheduled"

@pytest.fixture
def measured(monkeypatch):
    reads=[]; theme=["light"]
    def get(key, default=None):
        reads.append(key)
        return theme[0] if key=="on_screen_ui_theme" else default
    spy=SimpleNamespace(get_setting=get)
    monkeypatch.setattr(module,"storage",spy)
    monkeypatch.setattr(__import__("sys").modules["voice_flow.storage"],"storage",spy)
    bar=module.FloatingOverlayBar(Root());bar.state="READY"
    bar.win,bar.canvas=FakeWin(),FakeCanvas()
    bar._get_screen_bounds=lambda:(0,0,1920,1080)
    bar._user_pos=(1000,1004);bar._position_window()
    return bar,reads,theme

def test_static_ready_jobs_do_not_start_a_90ms_timer(measured):
    bar,_,_=measured
    for i in range(13):bar.show_audio_summary_progress(50,"Synthetic",job_id=str(i))
    assert 90 not in bar.root.delays

@pytest.mark.parametrize("rows",[1,13])
def test_one_theme_lookup_per_draw_and_next_frame_theme_change(measured,rows):
    bar,reads,theme=measured
    for i in range(rows):bar.show_audio_summary_progress(50,"Synthetic",job_id=str(i))
    for chosen in ("light","dark"):
        theme[0]=chosen;reads.clear()
        with patch.object(module.time,"monotonic",return_value=50 if chosen=="light" else 51):bar._draw()
        assert reads==["on_screen_ui_theme"]
        assert bar._last_draw_sig[-1] is (chosen=="dark")
        assert getattr(bar,"_frame_theme_dark",None) is None

def test_active_voice_animation_still_schedules_66ms(measured):
    bar,_,_=measured;bar.state="PROCESSING"
    phase=bar._anim_phase;bar._animate()
    assert bar._anim_phase>phase
    assert bar.root.delays[-1]==66

def test_nested_theme_snapshot_restored_after_exception(measured,monkeypatch):
    bar,_,_=measured;bar._frame_theme_dark=True
    def fail():
        assert bar._is_theme_dark() is True
        raise RuntimeError("synthetic")
    monkeypatch.setattr(bar,"_draw_frame",fail,raising=False)
    with pytest.raises(RuntimeError,match="synthetic"):bar._draw()
    assert bar._frame_theme_dark is True
