"""Settings contract probes: disposable databases and mocked runtime/native work."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_api_server import test_server, _post, _get
from voice_flow.gui import api_server
from voice_flow.recovery import AudioArchive


@pytest.mark.parametrize('key,value', [('click_to_paste_enabled','false'), ('show_in_taskbar','false'), ('on_screen_ui_theme','invalid')])
def test_general_setting_invalid_values_rejected_without_save(test_server, monkeypatch, key, value):
    monkeypatch.setattr('voice_flow.gui.desktop_launcher._apply_taskbar_visibility', Mock())
    before = test_server['storage'].get_setting(key)
    code, _, body = _post(test_server['base_url'] + '/api/settings/update', {'key':key,'value':value})
    assert code == 400 and not body['success']
    assert test_server['storage'].get_setting(key) == before


@pytest.mark.parametrize('endpoint', ['/api/settings/theme','/api/settings/on-screen-ui-theme'])
def test_theme_save_failure_not_reported_success(test_server, monkeypatch, endpoint):
    monkeypatch.setattr(test_server['storage'], 'save_setting', lambda *args: False)
    code, _, body = _post(test_server['base_url'] + endpoint, {'theme':'dark'})
    assert code == 500 and not body['success']


def test_taskbar_apply_failure_reports_saved_not_applied(test_server, monkeypatch):
    monkeypatch.setattr('voice_flow.gui.desktop_launcher._apply_taskbar_visibility', Mock(side_effect=RuntimeError('fake apply failure')))
    code, _, body = _post(test_server['base_url'] + '/api/settings/update', {'key':'show_in_taskbar','value':False})
    assert code == 503 and not body['success'] and body['saved']


def test_restart_busy_dictation_does_not_invoke_restart(test_server, monkeypatch):
    restart = Mock(return_value=True)
    monkeypatch.setattr('voice_flow.lifecycle.restart_suite', restart)
    test_server['controller'].state = SimpleNamespace(value='recording')
    test_server['controller'].audio.is_recording = True
    code, _, body = _post(test_server['base_url'] + '/api/app/restart', {})
    assert code == 409 and not body['success']
    restart.assert_not_called()


def test_clear_cache_busy_capture_retains_audio(test_server, monkeypatch, tmp_path):
    wav = tmp_path / 'retained.wav'
    wav.write_bytes(b'disposable recording')
    monkeypatch.setattr(api_server, 'archive', AudioArchive(tmp_path))
    test_server['controller'].audio.is_recording = True
    code, _, body = _post(test_server['base_url'] + '/api/storage/clear-audio-cache', {})
    assert code == 409 and not body['success']
    assert wav.exists()


def test_clear_cache_preserves_retained_history_recording(test_server, monkeypatch, tmp_path):
    wav = tmp_path / 'history-recovery.wav'
    wav.write_bytes(b'disposable retained recording')
    monkeypatch.setattr(api_server, 'archive', AudioArchive(tmp_path))
    test_server['controller'].audio.is_recording = False
    test_server['controller'].state = SimpleNamespace(value='idle')
    code, _, body = _post(test_server['base_url'] + '/api/storage/clear-audio-cache', {})
    assert code == 200 and body['success']
    assert wav.exists(), 'Clear temporary cache must preserve fourteen-day recovery recordings'


def test_account_switch_busy_capture_does_not_switch(test_server, monkeypatch):
    manager = Mock()
    monkeypatch.setattr('voice_flow.account_manager.get_account_manager', lambda: manager)
    test_server['controller'].audio.is_recording = True
    code, _, body = _post(test_server['base_url'] + '/api/auth/switch', {'account_id':'disposable'})
    assert code == 409 and not body['success']
    manager.switch_account.assert_not_called()


def test_update_check_failure_not_reported_success(test_server, monkeypatch):
    monkeypatch.setattr('voice_flow.update_checker.check_for_updates', lambda **kwargs: {'checked':False,'error':'mock offline','update_available':False})
    code, _, body = _get(test_server['base_url'] + '/api/updates/check')
    assert not body['success'] and body['checked'] is False


@pytest.mark.parametrize('changes', [{'username':' '}, {'avatar_color':'not-a-color'}, {'username':123}])
def test_profile_invalid_values_do_not_change_account(tmp_path, changes):
    from voice_flow.account_manager import AccountManager
    manager = AccountManager(tmp_path)
    account = manager.get_active_account()
    before = manager.get_account_by_id(account['id'])
    with pytest.raises(ValueError):
        manager.update_profile(account['id'], **changes)
    assert manager.get_account_by_id(account['id']) == before


def test_missing_overlay_is_not_success(test_server, monkeypatch):
    monkeypatch.setattr(api_server, 'runtime_controller', None)
    code, _, body = _post(test_server['base_url'] + '/api/overlay/show', {})
    assert code == 503 and not body['success']


def test_raising_overlay_is_not_success(test_server):
    test_server['controller'].overlay.show.side_effect = RuntimeError('fake show failure')
    code, _, body = _post(test_server['base_url'] + '/api/overlay/show', {})
    assert code == 503 and not body['success']


def test_autostart_save_failure_rolls_back_native_preference(test_server, monkeypatch):
    calls = []
    monkeypatch.setattr(api_server, 'get_launch_at_login', lambda: SimpleNamespace(applied=False,error=None))
    monkeypatch.setattr(api_server, 'set_launch_at_login', lambda val: calls.append(val) or SimpleNamespace(applied=True,error=None))
    monkeypatch.setattr(test_server['storage'], 'save_setting', lambda *args: False)
    code, _, body = _post(test_server['base_url'] + '/api/settings/autostart/toggle', {'enabled':True})
    assert code == 500 and not body['success']
    assert calls == [True, False]


def test_get_reset_busy_does_not_reset_state(test_server):
    test_server['controller'].audio.is_recording = True
    code, _, body = _get(test_server['base_url'] + '/api/overlay/reset-and-refresh')
    assert code == 409 and not body['success']
    test_server['controller'].reset_state_and_refresh.assert_not_called()


@pytest.mark.parametrize('table,column', [('audio_summary_history','status'), ('video_flow_jobs','state')])
def test_durable_media_busy_prevents_restart(test_server, monkeypatch, table, column):
    restart = Mock(return_value=True)
    monkeypatch.setattr('voice_flow.lifecycle.restart_suite', restart)
    store = test_server['storage']
    with store._get_conn() as conn:
        conn.execute(f'DROP TABLE IF EXISTS {table}')
        conn.execute(f'CREATE TABLE {table} ({column} TEXT)')
        conn.execute(f'INSERT INTO {table} VALUES (?)', ('running',))
        conn.commit()
    test_server['controller'].audio.is_recording = False
    code, _, body = _post(test_server['base_url'] + '/api/app/restart', {})
    assert code == 409 and not body['success']
    restart.assert_not_called()


def test_cache_partial_failure_preserves_recent_audio(tmp_path, monkeypatch):
    import os, time
    recent = tmp_path / 'recent.wav'; recent.write_bytes(b'recovery')
    old = tmp_path / '.writing-old.wav'; old.write_bytes(b'temporary')
    expired = tmp_path / 'expired.wav'; expired.write_bytes(b'expired')
    now = time.time()
    os.utime(old, (now-7200,now-7200)); os.utime(expired,(now-15*86400,now-15*86400))
    original = type(old).unlink
    def unlink(path, *args, **kwargs):
        if path == old:
            raise PermissionError('disposable denied')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(type(old),'unlink',unlink)
    result = AudioArchive(tmp_path).clear_temporary_cache(now)
    assert result == {'deleted':1,'preserved':1,'errors':1}
    assert recent.exists() and old.exists() and not expired.exists()


def test_legacy_boolean_false_read_normalized(test_server):
    test_server['storage'].save_setting('click_to_paste_enabled','false')
    code, _, body = _get(test_server['base_url'] + '/api/settings/get?key=click_to_paste_enabled')
    assert code == 200 and body['value'] is False


def test_saved_generic_setting_invalidates_runtime_cache(test_server):
    code, _, body = _post(test_server['base_url'] + '/api/settings/update', {'key':'click_to_paste_enabled','value':True})
    assert code == 200 and body['success']
    test_server['controller'].invalidate_cached_setting.assert_called_once_with('click_to_paste_enabled')


def test_account_runtime_apply_failure_reports_saved(test_server, monkeypatch):
    from voice_flow.account_manager import AccountRuntimeApplyError
    manager = Mock()
    manager.switch_account.side_effect = AccountRuntimeApplyError('Account changed but apply failed')
    monkeypatch.setattr('voice_flow.account_manager.get_account_manager',lambda:manager)
    test_server['controller'].audio.is_recording = False
    code, _, body = _post(test_server['base_url'] + '/api/auth/switch', {'account_id':'disposable'})
    assert code == 503 and body['saved'] and not body['success']


def test_dashboard_and_overlay_themes_are_separate(test_server):
    store = test_server['storage']
    store.save_setting('vf_theme','light')
    code, _, body = _post(test_server['base_url'] + '/api/settings/on-screen-ui-theme', {'theme':'dark'})
    assert code == 200 and body['success']
    assert store.get_setting('vf_theme') == 'light'
    assert store.get_setting('on_screen_ui_theme') == 'dark'
    test_server['controller'].overlay.refresh.assert_called_once()


@pytest.mark.parametrize('endpoint,body', [('/api/app/restart',{}),('/api/auth/switch',{'account_id':'disposable'})])
def test_audio_read_pending_blocks_destructive_account_or_restart(test_server, monkeypatch, endpoint, body):
    restart = Mock(return_value=True)
    manager = Mock()
    monkeypatch.setattr('voice_flow.lifecycle.restart_suite',restart)
    monkeypatch.setattr('voice_flow.account_manager.get_account_manager',lambda:manager)
    controller = test_server['controller']
    controller.audio.is_recording = False
    controller.state = SimpleNamespace(value='idle')
    controller._read_pending = True
    controller._read_active = False
    code, _, result = _post(test_server['base_url'] + endpoint,body)
    assert code == 409 and not result['success']
    restart.assert_not_called(); manager.switch_account.assert_not_called()


def test_direct_active_account_switch_busy_preserves_account_state(tmp_path, monkeypatch):
    from voice_flow import account_manager
    manager = account_manager.AccountManager(tmp_path)
    before = manager.get_active_account()
    monkeypatch.setattr(account_manager,'_account_manager',manager)
    monkeypatch.setattr(api_server,'settings_busy_reason',lambda:'Recording in progress')
    with pytest.raises(account_manager.AccountRuntimeBusyError):
        manager.switch_account(before['id'])
    with pytest.raises(account_manager.AccountRuntimeBusyError):
        manager.logout_account()
    assert manager.get_active_account() == before


def test_overlay_toggle_preserves_recording_state(test_server):
    from voice_flow.overlay import FloatingOverlayBar
    class Overlay:
        visible = True
        state = 'RECORDING'
        win = None
        _run_on_ui = staticmethod(lambda callback: callback())
        set_visible = FloatingOverlayBar.set_visible
        def hide(self):
            self.visible = False; self.state = 'HIDDEN'
        def show(self):
            self.visible = True
    overlay = Overlay()
    test_server['controller'].overlay = overlay
    for expected in (False,True):
        code, _, body = _post(test_server['base_url'] + '/api/overlay/toggle',{})
        assert code == 200 and body['success']
        assert overlay.visible is expected and overlay.state == 'RECORDING'


def test_overlay_unsupported_top_dock_rejected(test_server):
    code, _, body = _post(test_server['base_url'] + '/api/overlay/dock',{'dock':'top'})
    assert code == 400 and not body['success']
    test_server['controller'].overlay.set_dock.assert_not_called()


@pytest.mark.parametrize('value', [[],{}])
def test_malformed_list_theme_rejected(test_server, value):
    code, _, body = _post(test_server['base_url'] + '/api/settings/update',{'key':'on_screen_ui_theme','value':value})
    assert code == 400 and not body['success']

@pytest.mark.parametrize('actual,error', [(True,None),(False,'unavailable')])
def test_autostart_failed_rollback_reports_actual_native_state(test_server, monkeypatch, actual, error):
    statuses = iter([SimpleNamespace(applied=False,error=None),SimpleNamespace(applied=actual,error=error)])
    monkeypatch.setattr(api_server,'get_launch_at_login',lambda:next(statuses))
    results = iter([SimpleNamespace(applied=True,error=None),SimpleNamespace(applied=False,error='rollback failed')])
    monkeypatch.setattr(api_server,'set_launch_at_login',lambda val:next(results))
    monkeypatch.setattr(test_server['storage'],'save_setting',lambda *args:False)
    code, _, body = _post(test_server['base_url']+'/api/settings/autostart/toggle',{'enabled':True})
    assert code == 500 and not body['success']
    assert body['enabled'] is (None if error else actual)
    assert body['rollback_applied'] is False

def test_overlay_false_dock_result_is_not_success(test_server):
    test_server['controller'].overlay.set_dock.return_value = False
    code, _, body = _post(test_server['base_url']+'/api/overlay/dock',{'dock':'left'})
    assert code == 503 and not body['success']
