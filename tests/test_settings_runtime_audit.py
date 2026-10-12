"""Runtime Settings audit through isolated real method seams."""
import threading
from unittest.mock import Mock
from voice_flow.overlay import FloatingOverlayBar
from voice_flow.main import VoiceFlowApp
import voice_flow.main as main

def fake_overlay():
    overlay=object.__new__(FloatingOverlayBar)
    overlay.win=Mock()
    overlay.visible=False
    overlay.state='HIDDEN'
    overlay._animation_generation=0
    overlay._run_on_ui=lambda callback:callback()
    overlay._draw=Mock()
    overlay._bring_to_top=Mock()
    overlay._position_window=Mock()
    overlay._persist_position=Mock()
    overlay._user_pos=(500,500)
    return overlay

def test_visible_setting_restores_previously_hidden_bar():
    overlay=fake_overlay()
    assert overlay.set_visible(True)
    overlay._bring_to_top.assert_called_once()
    assert overlay.state=='READY'

def test_reset_position_restores_hidden_bar_without_resetting_jobs():
    overlay=fake_overlay()
    overlay.audio_summary_jobs={'audio':{'state':'running'}}
    overlay.video_jobs={'video':{'state':'running'}}
    overlay.reset_position()
    assert overlay.visible
    assert overlay.state=='READY'
    assert overlay.audio_summary_jobs=={'audio':{'state':'running'}}
    assert overlay.video_jobs=={'video':{'state':'running'}}

def test_settings_cache_does_not_cross_account_boundary(monkeypatch):
    app=object.__new__(VoiceFlowApp)
    app._settings_cache={}
    app._settings_cache_lock=threading.Lock()
    values={'database':'account-a','enabled':True}
    source=Mock()
    source.db_path='account-a'
    source.get_setting=lambda name,default=None:values['enabled']
    monkeypatch.setattr(main,'storage',source)
    monkeypatch.setattr(main.time,'monotonic',lambda:100.0)
    assert app._get_cached_setting('voice_flow_enabled') is True
    source.db_path='account-b'
    values['enabled']=False
    assert app._get_cached_setting('voice_flow_enabled') is False


def test_next_account_capture_loads_that_accounts_microphone(monkeypatch):
    from tests.test_demand_pipeline_lifecycle import _Lease, _recording_app
    from voice_flow.main import DictationSession
    from voice_flow.config import config
    events=[]
    lease=_Lease(events)
    app=_recording_app(DictationSession(123,'Editor','smart_clean','smart_clean',0.0),events,lease)
    app._capture_target_hwnd=lambda:123
    app._start_window_tracker=lambda session:None
    app._start_stream_for_session=lambda session:None
    seen=[]
    monkeypatch.setattr(config,'selected_mic_device','account-a-microphone')
    source=Mock()
    source.db_path='account-b'
    source.get_setting=lambda key,default=None:'account-b-microphone' if key=='selected_mic_device' else default
    monkeypatch.setattr(main,'storage',source)
    monkeypatch.setattr('voice_flow.microphone_devices.load_microphone_preference',lambda storage:'account-b-microphone')
    monkeypatch.setattr('voice_flow.local_model_resources.acquire_model_use',lambda kind:lease)
    monkeypatch.setattr(main,'_warm_voice_gemini_transport',lambda *args:None)
    app.audio.start=lambda:seen.append(config.selected_mic_device) or True
    try:
        assert app._on_dictation_start()
        assert seen==['account-b-microphone']
    finally:
        if app._record_watchdog:app._record_watchdog.cancel()

def test_overlay_show_keeps_active_voice_and_media_rows():
    overlay=fake_overlay()
    overlay.state='RECORDING'
    overlay.audio_summary_jobs={'a':{'state':'running'}}
    overlay.video_jobs={'v':{'state':'running'}}
    overlay.show()
    assert overlay.visible and overlay.state=='RECORDING'
    assert overlay.audio_summary_jobs['a']['state']=='running'
    assert overlay.video_jobs['v']['state']=='running'

def test_overlay_reset_keeps_active_voice_and_media_rows():
    overlay=fake_overlay()
    overlay.visible=True
    overlay.state='PROCESSING'
    overlay.audio_summary_jobs={'a':{'state':'running'}}
    overlay.video_jobs={'v':{'state':'running'}}
    overlay.reset_position()
    assert overlay.state=='PROCESSING'
    assert overlay.audio_summary_jobs['a']['state']=='running'
    assert overlay.video_jobs['v']['state']=='running'

def test_overlay_theme_cache_changes_immediately_for_new_account(monkeypatch):
    import voice_flow.overlay as module
    overlay=fake_overlay()
    source=Mock()
    source.db_path='a'
    theme=['light']
    source.get_setting=lambda name,default=None:theme[0]
    monkeypatch.setattr(module,'storage',source)
    monkeypatch.setattr(module.time,'monotonic',lambda:100.0)
    assert not overlay._is_theme_dark()
    source.db_path='b'
    theme[0]='dark'
    assert overlay._is_theme_dark()

def test_native_startup_reports_failure_honestly(monkeypatch):
    from voice_flow import native_settings,installer
    monkeypatch.setattr(native_settings.sys,'platform','win32')
    monkeypatch.setattr(installer,'set_autostart',lambda enabled:False)
    result=native_settings.set_launch_at_login(True)
    assert not result.applied and result.error

def test_native_startup_status_uses_verified_installer(monkeypatch):
    from voice_flow import native_settings,installer
    monkeypatch.setattr(native_settings.sys,'platform','win32')
    monkeypatch.setattr(installer,'get_autostart_status',lambda:(False,'scheduler unavailable'))
    result=native_settings.get_launch_at_login()
    assert not result.applied and result.error=='scheduler unavailable'

def test_taskbar_setting_never_mutates_foreign_same_title_window(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from voice_flow.gui import desktop_launcher
    calls=[]
    user32=SimpleNamespace(FindWindowW=lambda *args:123,GetWindowLongW=lambda *args:0,SetWindowLongW=lambda *args:calls.append(args),SetWindowPos=lambda *args:calls.append(args),GetWindowThreadProcessId=lambda hwnd,pid:setattr(pid._obj,'value',999999))
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=user32,kernel32=SimpleNamespace(SetLastError=lambda value:None,GetLastError=lambda:0)))
    monkeypatch.setattr(desktop_launcher.sys,'platform','win32')
    desktop_launcher._apply_taskbar_visibility(None,False)
    assert calls==[]

def test_dock_settings_validate_and_keep_active_jobs():
    overlay=fake_overlay()
    overlay.state='RECORDING'
    overlay.visible=True
    assert not overlay.set_dock('unsupported')
    assert overlay._user_pos==(500,500)
    assert overlay.set_dock('left')
    assert overlay.dock=='left' and overlay._user_pos is None
    assert overlay.state=='RECORDING' and overlay.visible

def test_hiding_bar_preserves_active_dictation_state():
    overlay=fake_overlay()
    overlay.visible=True
    overlay.state='RECORDING'
    assert overlay.set_visible(False)
    assert not overlay.visible and overlay.state=='RECORDING'
    overlay.win.withdraw.assert_called_once()

def taskbar_user32(monkeypatch,pid,handles=(123,),failure=False):
    import ctypes
    from types import SimpleNamespace
    from voice_flow.gui import desktop_launcher
    calls=[]
    def enum(callback,param):
        for handle in handles:callback(handle,param)
        return 1
    def title(handle,buffer,size):buffer.value='AI Productivity Flow';return 20
    def owner(handle,pointer):pointer._obj.value=pid;return 1
    def set_style(*args):calls.append(('style',args));return 1
    def position(*args):calls.append(('position',args));return 0 if failure else 1
    user32=SimpleNamespace(EnumWindows=enum,GetWindowTextW=title,GetWindowThreadProcessId=owner,GetWindowLongW=lambda *args:0,SetWindowLongW=set_style,GetWindowLongPtrW=lambda *args:0,SetWindowLongPtrW=set_style,SetWindowPos=position)
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=user32,kernel32=SimpleNamespace(SetLastError=lambda value:None,GetLastError=lambda:0)))
    monkeypatch.setattr(desktop_launcher.sys,'platform','win32')
    return calls

def test_taskbar_uses_verified_native_handle(monkeypatch):
    import os
    from types import SimpleNamespace
    from voice_flow.gui import desktop_launcher
    calls=taskbar_user32(monkeypatch,os.getpid())
    assert desktop_launcher._apply_taskbar_visibility(SimpleNamespace(native=SimpleNamespace(Handle=321)),True)
    assert calls[0][1][0]==321


def test_taskbar_converts_managed_intptr_with_to_int64(monkeypatch):
    import os
    from types import SimpleNamespace
    from voice_flow.gui import desktop_launcher
    class ManagedHandle:
        def __int__(self):
            raise TypeError('System.IntPtr cannot be converted directly')
        def ToInt64(self):
            return 321
    calls=taskbar_user32(monkeypatch,os.getpid())
    assert desktop_launcher._apply_taskbar_visibility(SimpleNamespace(native=SimpleNamespace(Handle=ManagedHandle())),True)
    assert calls[0][1][0]==321


def test_taskbar_noncallable_to_int64_keeps_integer_fallback(monkeypatch):
    import os
    from types import SimpleNamespace
    from voice_flow.gui import desktop_launcher
    class IntegerHandle:
        ToInt64=None
        def __int__(self):
            return 321
    calls=taskbar_user32(monkeypatch,os.getpid())
    assert desktop_launcher._apply_taskbar_visibility(SimpleNamespace(native=SimpleNamespace(Handle=IntegerHandle())),True)
    assert calls[0][1][0]==321

def test_taskbar_supports_separate_managed_gui_process(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import psutil
    from voice_flow.gui import desktop_launcher
    calls=taskbar_user32(monkeypatch,999999)
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(cmdline=lambda:['pythonw.exe','-m','voice_flow.gui.desktop_launcher'],cwd=lambda:str(Path(desktop_launcher.__file__).resolve().parents[3])))
    assert desktop_launcher._apply_taskbar_visibility(None,False)
    assert calls


def test_taskbar_supports_managed_gui_started_from_project_src(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import psutil
    from voice_flow.gui import desktop_launcher
    calls=taskbar_user32(monkeypatch,999999)
    project=Path(desktop_launcher.__file__).resolve().parents[3]
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(cmdline=lambda:['pythonw.exe','-m','voice_flow.gui.desktop_launcher'],cwd=lambda:str(project/'src')))
    assert desktop_launcher._apply_taskbar_visibility(None,False)
    assert calls


def test_taskbar_rejects_foreign_src_and_unrelated_project_child(monkeypatch,tmp_path):
    from pathlib import Path
    from types import SimpleNamespace
    import psutil
    from voice_flow.gui import desktop_launcher
    project=Path(desktop_launcher.__file__).resolve().parents[3]
    for cwd in (tmp_path/'src',project/'tests',project/'src'/'voice_flow'):
        calls=taskbar_user32(monkeypatch,999999)
        monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(cmdline=lambda:['pythonw.exe','-m','voice_flow.gui.desktop_launcher'],cwd=lambda:str(cwd)))
        assert not desktop_launcher._apply_taskbar_visibility(None,False)
        assert not calls

def test_taskbar_rejects_other_checkout(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import psutil
    from voice_flow.gui import desktop_launcher
    calls=taskbar_user32(monkeypatch,999999)
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(cmdline=lambda:['pythonw.exe','-m','voice_flow.gui.desktop_launcher'],cwd=lambda:str(tmp_path)))
    assert not desktop_launcher._apply_taskbar_visibility(None,False)
    assert not calls

def test_taskbar_missing_window_and_native_failure_are_false(monkeypatch):
    import os
    from voice_flow.gui import desktop_launcher
    calls=taskbar_user32(monkeypatch,os.getpid(),handles=())
    assert not desktop_launcher._apply_taskbar_visibility(None,True)
    assert not calls
    taskbar_user32(monkeypatch,os.getpid(),failure=True)
    assert not desktop_launcher._apply_taskbar_visibility(None,True)

def test_runtime_sync_refuses_active_capture_without_changing_mic(monkeypatch):
    from voice_flow.main import DictationState
    from voice_flow.config import config
    import pytest
    app=object.__new__(VoiceFlowApp)
    app._state_lock=threading.RLock()
    app.state=DictationState.RECORDING
    monkeypatch.setattr(config,'selected_mic_device','active-session')
    with pytest.raises(RuntimeError):app.sync_runtime_preferences()
    assert config.selected_mic_device=='active-session'

def test_taskbar_foreign_title_process_module_is_rejected(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import psutil
    from voice_flow.gui import desktop_launcher
    calls=taskbar_user32(monkeypatch,999999)
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(cmdline=lambda:['pythonw.exe','-m','foreign.app'],cwd=lambda:str(Path(desktop_launcher.__file__).resolve().parents[3])))
    assert not desktop_launcher._apply_taskbar_visibility(None,False)
    assert not calls

def test_ordinary_dictation_start_does_not_sync_again(monkeypatch):
    from tests.test_demand_pipeline_lifecycle import _Lease,_recording_app
    from voice_flow.main import DictationSession
    events=[]
    lease=_Lease(events)
    app=_recording_app(DictationSession(123,'Editor','smart_clean','smart_clean',0.0),events,lease)
    app._runtime_preferences_token=(id(main.storage),getattr(main.storage,'db_path',None))
    app.sync_runtime_preferences=Mock(side_effect=AssertionError('unnecessary preference reload'))
    app._capture_target_hwnd=lambda:123
    app._start_window_tracker=lambda session:None
    app._start_stream_for_session=lambda session:None
    monkeypatch.setattr(main.storage,'get_setting',lambda key,default=None:default)
    monkeypatch.setattr('voice_flow.local_model_resources.acquire_model_use',lambda kind:lease)
    monkeypatch.setattr(main,'_warm_voice_gemini_transport',lambda *args:None)
    try:
        assert app._on_dictation_start()
        app.sync_runtime_preferences.assert_not_called()
    finally:
        if app._record_watchdog:app._record_watchdog.cancel()

def test_account_cache_slow_old_read_does_not_poison_new_account(monkeypatch):
    app=object.__new__(VoiceFlowApp)
    app._settings_cache={}
    app._settings_cache_lock=threading.Lock()
    source=Mock()
    source.db_path='a'
    entered=threading.Event()
    release=threading.Event()
    def read(key,default=None):
        if source.db_path=='a':
            entered.set()
            assert release.wait(3)
            return 'value-a'
        return 'value-b'
    source.get_setting=read
    monkeypatch.setattr(main,'storage',source)
    monkeypatch.setattr(main.time,'monotonic',lambda:100.0)
    result=[]
    thread=threading.Thread(target=lambda:result.append(app._get_cached_setting('key')))
    thread.start()
    assert entered.wait(1)
    source.db_path='b'
    assert app._get_cached_setting('key')=='value-b'
    release.set()
    thread.join(1)
    assert result==['value-a']
    assert app._get_cached_setting('key')=='value-b'

def test_saved_setting_invalidation_applies_without_ttl_delay(monkeypatch):
    app=object.__new__(VoiceFlowApp)
    source=Mock()
    source.db_path='a'
    value=[False]
    source.get_setting=lambda key,default=None:value[0]
    monkeypatch.setattr(main,'storage',source)
    monkeypatch.setattr(main.time,'monotonic',lambda:100.0)
    assert not app._get_cached_setting('click_to_paste_enabled')
    value[0]=True
    app.invalidate_cached_setting('click_to_paste_enabled')
    assert app._get_cached_setting('click_to_paste_enabled')


def test_save_invalidation_prevents_pending_old_read_from_recaching(monkeypatch):
    app=object.__new__(VoiceFlowApp)
    source=Mock()
    source.db_path='a'
    value=[False]
    entered=threading.Event()
    release=threading.Event()
    calls=[]
    def read(key,default=None):
        snapshot=value[0]
        calls.append(snapshot)
        if len(calls)==1:
            entered.set()
            assert release.wait(3)
        return snapshot
    source.get_setting=read
    monkeypatch.setattr(main,'storage',source)
    monkeypatch.setattr(main.time,'monotonic',lambda:100.0)
    result=[]
    thread=threading.Thread(target=lambda:result.append(app._get_cached_setting('click_to_paste_enabled')))
    thread.start()
    try:
        assert entered.wait(1)
        value[0]=True
        app.invalidate_cached_setting('click_to_paste_enabled')
    finally:
        release.set()
        thread.join(1)
    assert not thread.is_alive()
    assert result==[False]
    assert app._get_cached_setting('click_to_paste_enabled') is True
    assert app._get_cached_setting('click_to_paste_enabled') is True
    assert calls==[False,True]

def test_overlay_many_color_reads_share_theme_snapshot_and_refresh(monkeypatch):
    import voice_flow.overlay as module
    overlay=fake_overlay()
    source=Mock()
    source.db_path='a'
    value=['light']
    calls=[]
    source.get_setting=lambda key,default=None:calls.append(key) or value[0]
    monkeypatch.setattr(module,'storage',source)
    monkeypatch.setattr(module.time,'monotonic',lambda:100.0)
    light=overlay.ORANGE
    for _ in range(10):
        overlay.ORANGE
        overlay.ORANGE_DEEP
        overlay.ORANGE_SOFT
    assert len(calls)==1
    value[0]='dark'
    overlay.refresh()
    assert overlay.ORANGE!=light
    assert len(calls)==2
    source.db_path='b'
    value[0]='light'
    assert overlay.ORANGE==light
    assert len(calls)==3

def test_taskbar_native_style_error_is_reported(monkeypatch):
    import os,ctypes
    from types import SimpleNamespace
    from voice_flow.gui import desktop_launcher
    calls=taskbar_user32(monkeypatch,os.getpid())
    error=[0]
    ctypes.windll.kernel32=SimpleNamespace(SetLastError=lambda value:error.__setitem__(0,value),GetLastError=lambda:error[0])
    def failed_style(*args):error[0]=5;return 0
    ctypes.windll.user32.SetWindowLongPtrW=failed_style
    assert not desktop_launcher._apply_taskbar_visibility(None,True)
    assert not calls
