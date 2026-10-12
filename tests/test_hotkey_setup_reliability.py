from unittest.mock import MagicMock, patch
import pytest
from voice_flow.hotkeys import InputTriggerListener, parse_hotkey_string, _vk_for_key_name

@pytest.fixture
def listener():
    with patch('voice_flow.hotkeys.Win32KeyboardHook'), patch('voice_flow.hotkeys.Win32MouseHook'), patch('voice_flow.hotkeys.InputTriggerListener.reload_config'):
        item = InputTriggerListener(MagicMock(), MagicMock(), MagicMock())
    item._hotkey_trigger = 'custom'
    item._custom_trigger_type = 'toggle'
    item._trigger_mode = 'hybrid'
    return item

@pytest.mark.parametrize('shortcut,base', [('Ctrl+-','minus'), ('Ctrl++','plus')])
def test_recorded_punctuation_preserved(shortcut, base):
    assert parse_hotkey_string(shortcut)['base_key'] == base

@pytest.mark.parametrize('shortcut', ['Ctrl+Unknown', 'Ctrl+A+B', 'Ctrl+'])
def test_invalid_shortcut_rejected(shortcut):
    assert parse_hotkey_string(shortcut).get('valid') is False

@pytest.mark.parametrize('shortcut,vk', [('F8', 0x77), ('Alt', 0x12)])
def test_unrelated_key_does_not_start_shortcut(listener, shortcut, vk):
    listener._parsed_custom_keys = parse_hotkey_string(shortcut)
    with patch('voice_flow.hotkeys._is_ctrl_down', return_value=False), patch('voice_flow.hotkeys._is_win_down', return_value=False), patch('voice_flow.hotkeys._is_shift_down', return_value=False), patch('voice_flow.hotkeys._is_alt_down', return_value=shortcut == 'Alt'), patch('voice_flow.hotkeys._is_key_down', return_value=True), patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_native_key(ord('A'), True, False, 0)
    assert not listener._is_recording

def test_toggle_release_after_long_press_stays_recording(listener):
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_hotkey_triggered = True
    listener._is_recording = True
    listener._hotkey_press_time = 10.0
    with patch('voice_flow.hotkeys.time.time', return_value=11.0), patch('voice_flow.hotkeys._is_ctrl_down', return_value=False), patch('voice_flow.hotkeys._is_win_down', return_value=False), patch('voice_flow.hotkeys._is_shift_down', return_value=False), patch('voice_flow.hotkeys._is_alt_down', return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_native_key(0x77, False, True, 0)
    assert listener._is_recording

def test_native_repeat_does_not_finish_double_tap_recording(listener):
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_trigger_type = 'double_tap'
    with patch('voice_flow.hotkeys.time.time', return_value=100.0), patch('voice_flow.hotkeys._is_ctrl_down', return_value=False), patch('voice_flow.hotkeys._is_win_down', return_value=False), patch('voice_flow.hotkeys._is_shift_down', return_value=False), patch('voice_flow.hotkeys._is_alt_down', return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_native_key(0x77, True, False, 0)
        listener._on_native_key(0x77, False, True, 0)
        listener._on_native_key(0x77, True, False, 0)
        assert listener._is_recording
        listener._on_native_key(0x77, True, False, 0)
    assert listener._is_recording

def test_disabled_mode_does_not_start_keyboard(listener):
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._trigger_mode = 'disabled'
    with patch('voice_flow.hotkeys._is_ctrl_down', return_value=False), patch('voice_flow.hotkeys._is_win_down', return_value=False), patch('voice_flow.hotkeys._is_shift_down', return_value=False), patch('voice_flow.hotkeys._is_alt_down', return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_native_key(0x77, True, False, 0)
    assert not listener._is_recording

def test_reload_active_keeps_current_binding_until_release(listener):
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_hotkey_str = 'F8'
    listener._custom_hotkey_triggered = True
    listener._custom_trigger_type = 'hold'
    listener._is_recording = True
    with patch('voice_flow.storage.storage.get_setting', side_effect=lambda name, default=None: default):
        InputTriggerListener.reload_config(listener, {'hotkey_trigger': 'custom', 'custom_hotkey': 'F9', 'custom_trigger_type': 'hold', 'dictation_trigger_mode': 'hybrid'})
    with patch('voice_flow.hotkeys._is_ctrl_down', return_value=False), patch('voice_flow.hotkeys._is_win_down', return_value=False), patch('voice_flow.hotkeys._is_shift_down', return_value=False), patch('voice_flow.hotkeys._is_alt_down', return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_native_key(0x77, False, True, 0)
    assert not listener._is_recording

@pytest.mark.parametrize('shortcut,canonical', [('Control-Shift-d','Ctrl+Shift+D'), ('Windows+control','Ctrl+Win'), ('Double-Ctrl','Double Ctrl'), ('menu+return','Alt+Enter'), ('Ctrl+\\','Ctrl+Backslash')])
def test_supported_aliases_are_canonical(shortcut, canonical):
    result = parse_hotkey_string(shortcut)
    assert result['valid']
    assert result['canonical'] == canonical

@pytest.mark.parametrize('shortcut,vk', [('Ctrl+-',189),('Ctrl++',187),('Ctrl+,',188),('Ctrl+/',191),('F24',135)])
def test_punctuation_has_native_key_mapping(shortcut, vk):
    assert _vk_for_key_name(parse_hotkey_string(shortcut)['base_key']) == vk

@pytest.mark.parametrize('behavior', ['hold','toggle','double_tap'])
def test_custom_release_uses_behavior_even_with_global_ptt(listener, behavior):
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_trigger_type = behavior
    listener._trigger_mode = 'ptt_only'
    listener._custom_hotkey_triggered = True
    listener._is_recording = True
    with patch('voice_flow.hotkeys._is_ctrl_down', return_value=False), patch('voice_flow.hotkeys._is_win_down', return_value=False), patch('voice_flow.hotkeys._is_shift_down', return_value=False), patch('voice_flow.hotkeys._is_alt_down', return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_native_key(0x77, False, True, 0)
    assert listener._is_recording == (behavior != 'hold')

def test_capture_lease_blocks_real_event_paths_and_expires(listener, monkeypatch):
    from voice_flow import hotkey_config
    from pynput import keyboard
    monkeypatch.setattr(hotkey_config, '_capture_lease', ('',0.0))
    clock = [100.0]
    monkeypatch.setattr(hotkey_config.time, 'monotonic', lambda: clock[0])
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    assert listener.begin_shortcut_capture('fixture-owner')
    assert not listener.begin_shortcut_capture('other-owner')
    assert not listener.end_shortcut_capture('other-owner')
    with patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_native_key(0x77, True, False, 0)
        listener._on_key_press(keyboard.Key.f8)
    assert not listener._is_recording
    clock[0] = 125
    assert listener.renew_shortcut_capture('fixture-owner')
    clock[0] = 156
    assert not hotkey_config.shortcut_capture_active()
    assert not listener.renew_shortcut_capture('fixture-owner')
    assert listener.end_shortcut_capture('fixture-owner')

def test_capture_refuses_active_listener_or_mouse(listener, monkeypatch):
    from voice_flow import hotkey_config
    monkeypatch.setattr(hotkey_config, '_capture_lease', ('',0.0))
    listener._is_recording = True
    assert not listener.begin_shortcut_capture('fixture')
    listener._is_recording = False
    listener._mouse_hook._is_recording = True
    assert not listener.begin_shortcut_capture('fixture')
    assert not hotkey_config.shortcut_capture_active()

def test_capture_middle_pair_passes_through_after_expiry(monkeypatch):
    from voice_flow import mouse_hook, hotkey_config
    from types import SimpleNamespace
    passed = []
    monkeypatch.setattr(mouse_hook, 'user32', SimpleNamespace(SetWindowsHookExW=lambda *args: 123,CallNextHookEx=lambda *args: passed.append(args[2]) or 42))
    monkeypatch.setattr(mouse_hook, 'kernel32', SimpleNamespace(GetModuleHandleW=lambda *args: 1,GetLastError=lambda: 0))
    monkeypatch.setattr(hotkey_config, '_capture_lease', ('fixture',130.0))
    clock = [100.0]
    monkeypatch.setattr(hotkey_config.time,'monotonic',lambda: clock[0])
    hook = mouse_hook.Win32MouseHook(lambda:None,lambda:None,lambda:None)
    assert hook._install_hook()
    assert hook._hook_proc_ptr(0,mouse_hook.WM_MBUTTONDOWN,0) == 42
    clock[0] = 131.0
    assert hook._hook_proc_ptr(0,mouse_hook.WM_MBUTTONUP,0) == 42
    assert not hook._is_recording
    assert hook._control_queue.empty()
    assert passed == [mouse_hook.WM_MBUTTONDOWN,mouse_hook.WM_MBUTTONUP]

def test_fallback_repeat_does_not_finish_double_tap(listener):
    from pynput import keyboard
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_trigger_type = 'double_tap'
    with patch('voice_flow.hotkeys.time.time',return_value=100.0), patch('voice_flow.hotkeys._is_ctrl_down', return_value=False), patch('voice_flow.hotkeys._is_win_down', return_value=False), patch('voice_flow.hotkeys._is_shift_down', return_value=False), patch('voice_flow.hotkeys._is_alt_down', return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        listener._on_key_press(keyboard.Key.f8)
        listener._on_key_release(keyboard.Key.f8)
        listener._on_key_press(keyboard.Key.f8)
        assert listener._is_recording
        listener._on_key_press(keyboard.Key.f8)
    assert listener._is_recording

def test_no_change_reload_preserves_pending_timer(listener):
    timer = MagicMock()
    listener._ctrl_check_timer = timer
    settings = {'hotkey_trigger':'custom','custom_hotkey':'Alt+Space','custom_trigger_type':'toggle','dictation_trigger_mode':'hybrid','ctrl_key_dictation_enabled':False}
    with patch('voice_flow.storage.storage.get_setting',side_effect=lambda name,default=None:default):
        listener.reload_config(settings)
    assert listener._ctrl_check_timer is timer
    timer.cancel.assert_not_called()

def test_changed_inactive_reload_clears_pending_timer_and_tap(listener):
    timer = MagicMock()
    listener._ctrl_check_timer = timer
    listener._last_custom_release_time = 100.0
    with patch('voice_flow.storage.storage.get_setting',side_effect=lambda name,default=None:default):
        listener.reload_config({'hotkey_trigger':'custom','custom_hotkey':'F9','custom_trigger_type':'hold'})
    timer.cancel.assert_called_once()
    assert listener._ctrl_check_timer is None
    assert listener._last_custom_release_time == 0.0

@pytest.mark.parametrize('char,base', [('-','minus'),('+','plus'),(',','comma')])
def test_fallback_punctuation_character_matches(char, base):
    from pynput import keyboard
    from voice_flow.hotkeys import _key_matches_name
    assert _key_matches_name(keyboard.KeyCode.from_char(char),base)

@pytest.mark.parametrize('path', ['native','fallback'])
def test_active_hold_release_survives_disabled_reload(listener, path):
    from pynput import keyboard
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_hotkey_str = 'F8'
    listener._custom_trigger_type = 'hold'
    with patch('voice_flow.hotkeys._is_ctrl_down',return_value=False), patch('voice_flow.hotkeys._is_win_down',return_value=False), patch('voice_flow.hotkeys._is_shift_down',return_value=False), patch('voice_flow.hotkeys._is_alt_down',return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        if path == 'native': listener._on_native_key(0x77,True,False,0)
        else: listener._on_key_press(keyboard.Key.f8)
        assert listener._is_recording
        with patch('voice_flow.storage.storage.get_setting',side_effect=lambda name,default=None:default):
            listener.reload_config({'hotkey_trigger':'custom','custom_hotkey':'F9','custom_trigger_type':'hold','dictation_trigger_mode':'disabled'})
        if path == 'native': listener._on_native_key(0x77,False,True,0)
        else: listener._on_key_release(keyboard.Key.f8)
    assert not listener._is_recording

@pytest.mark.parametrize('path',['native','fallback'])
def test_capture_end_quarantines_held_key_until_physical_release(listener, monkeypatch, path):
    from voice_flow import hotkey_config
    from pynput import keyboard
    monkeypatch.setattr(hotkey_config,'_capture_lease',('',0.0))
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    assert listener.begin_shortcut_capture('fixture')
    with patch('voice_flow.hotkeys._is_ctrl_down',return_value=False), patch('voice_flow.hotkeys._is_win_down',return_value=False), patch('voice_flow.hotkeys._is_shift_down',return_value=False), patch('voice_flow.hotkeys._is_alt_down',return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        if path == 'native': listener._on_native_key(0x77,True,False,0)
        else: listener._on_key_press(keyboard.Key.f8)
        assert listener.end_shortcut_capture('fixture')
        if path == 'native': listener._on_native_key(0x77,True,False,0)
        else: listener._on_key_press(keyboard.Key.f8)
        assert not listener._is_recording
        if path == 'native':
            listener._on_native_key(0x77,False,True,0)
            listener._on_native_key(0x77,True,False,0)
        else:
            listener._on_key_release(keyboard.Key.f8)
            listener._on_key_press(keyboard.Key.f8)
    assert listener._is_recording

def test_native_hook_message_repeat_uses_physical_edges(listener, monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from voice_flow import hotkeys
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_trigger_type = 'double_tap'
    monkeypatch.setattr(hotkeys,'user32',SimpleNamespace(SetWindowsHookExW=lambda *args:123,CallNextHookEx=lambda *args:0))
    monkeypatch.setattr(hotkeys,'kernel32',SimpleNamespace(GetLastError=lambda:0))
    hook = hotkeys.Win32KeyboardHook(listener._on_native_key)
    assert hook._install_hook()
    event = hotkeys.KBDLLHOOKSTRUCT(vkCode=0x77)
    with patch('voice_flow.hotkeys.time.time',return_value=100.0), patch('voice_flow.hotkeys._is_ctrl_down',return_value=False), patch('voice_flow.hotkeys._is_win_down',return_value=False), patch('voice_flow.hotkeys._is_shift_down',return_value=False), patch('voice_flow.hotkeys._is_alt_down',return_value=False), patch('voice_flow.hotkeys.threading.Thread'):
        hook._hook_proc_ptr(0,hotkeys.WM_KEYDOWN,ctypes.addressof(event))
        hook._hook_proc_ptr(0,hotkeys.WM_KEYUP,ctypes.addressof(event))
        hook._hook_proc_ptr(0,hotkeys.WM_KEYDOWN,ctypes.addressof(event))
        assert listener._is_recording
        hook._hook_proc_ptr(0,hotkeys.WM_KEYDOWN,ctypes.addressof(event))
    assert listener._is_recording

@pytest.mark.parametrize('vk', [ord('A'),ord('C'),0x25])
def test_native_unrelated_repeat_passes_through_while_custom_hold_active(listener,vk):
    import ctypes
    from types import SimpleNamespace
    from voice_flow import hotkeys
    listener._parsed_custom_keys = parse_hotkey_string('F8')
    listener._custom_trigger_type = 'hold'
    forwarded=[]
    with patch.object(hotkeys,'user32',SimpleNamespace(SetWindowsHookExW=lambda *args:123,CallNextHookEx=lambda *args:forwarded.append(args[2]) or 42)), patch.object(hotkeys,'kernel32',SimpleNamespace(GetLastError=lambda:0)), patch('voice_flow.hotkeys._is_ctrl_down',return_value=False), patch('voice_flow.hotkeys._is_win_down',return_value=False), patch('voice_flow.hotkeys._is_shift_down',return_value=False), patch('voice_flow.hotkeys._is_alt_down',return_value=False), patch('voice_flow.hotkeys._is_key_down',side_effect=lambda key:key==0x77), patch('voice_flow.hotkeys.threading.Thread'):
        hook=hotkeys.Win32KeyboardHook(listener._on_native_key)
        assert hook._install_hook()
        start=hotkeys.KBDLLHOOKSTRUCT(vkCode=0x77)
        unrelated=hotkeys.KBDLLHOOKSTRUCT(vkCode=vk)
        assert hook._hook_proc_ptr(0,hotkeys.WM_KEYDOWN,ctypes.addressof(start))==1
        assert listener._is_recording
        assert hook._hook_proc_ptr(0,hotkeys.WM_KEYDOWN,ctypes.addressof(unrelated))==42
        assert hook._hook_proc_ptr(0,hotkeys.WM_KEYDOWN,ctypes.addressof(unrelated))==42
        assert hook._hook_proc_ptr(0,hotkeys.WM_KEYUP,ctypes.addressof(unrelated))==42

@pytest.mark.parametrize('path',['native','fallback'])
@pytest.mark.parametrize('trigger',['alt_space','alt_tab','ctrl_win'])
@pytest.mark.parametrize('mode',['ptt_only','toggle_only','hybrid'])
@pytest.mark.parametrize('duration',[0.1,1.0])
def test_preset_release_mode_matrix(listener,path,trigger,mode,duration):
    from pynput import keyboard
    listener._hotkey_trigger=trigger
    listener._trigger_mode=mode
    listener._ctrl_key_dictation_enabled=False
    vk=0x5B if trigger=='ctrl_win' else (0x20 if trigger=='alt_space' else 0x09)
    key=keyboard.Key.cmd if trigger=='ctrl_win' else (keyboard.Key.space if trigger=='alt_space' else keyboard.Key.tab)
    with patch('voice_flow.hotkeys._is_ctrl_down',return_value=trigger=='ctrl_win'), patch('voice_flow.hotkeys._is_win_down',return_value=trigger=='ctrl_win'), patch('voice_flow.hotkeys._is_shift_down',return_value=False), patch('voice_flow.hotkeys._is_alt_down',return_value=trigger!='ctrl_win'), patch('voice_flow.hotkeys._is_key_down',return_value=False), patch('voice_flow.hotkeys._suppress_win_start_menu'), patch('voice_flow.hotkeys.threading.Thread'), patch('voice_flow.hotkeys.time.time',return_value=100.0) as clock:
        if path=='native': listener._on_native_key(vk,True,False,0)
        else: listener._on_key_press(key)
        assert listener._is_recording
        clock.return_value=100.0+duration
        if path=='native': listener._on_native_key(vk,False,True,0)
        else: listener._on_key_release(key)
    assert listener._is_recording==(mode=='toggle_only' or (mode=='hybrid' and duration<0.25))

@pytest.mark.parametrize('path',['native','fallback'])
@pytest.mark.parametrize('trigger',['custom','alt_space','alt_tab','ctrl_win','double_ctrl'])
def test_toggle_can_finish_old_binding_after_disabled_reload(listener,path,trigger):
    from pynput import keyboard
    listener._hotkey_trigger=trigger
    listener._trigger_mode='toggle_only'
    listener._custom_trigger_type='toggle'
    listener._parsed_custom_keys=parse_hotkey_string('F8')
    listener._custom_hotkey_str='F8'
    vk={'custom':0x77,'alt_space':0x20,'alt_tab':0x09,'ctrl_win':0x5B,'double_ctrl':0x11}[trigger]
    key={'custom':keyboard.Key.f8,'alt_space':keyboard.Key.space,'alt_tab':keyboard.Key.tab,'ctrl_win':keyboard.Key.cmd,'double_ctrl':keyboard.Key.ctrl}[trigger]
    with patch('voice_flow.hotkeys._is_ctrl_down',return_value=trigger=='ctrl_win'),patch('voice_flow.hotkeys._is_win_down',return_value=trigger=='ctrl_win'),patch('voice_flow.hotkeys._is_shift_down',return_value=False),patch('voice_flow.hotkeys._is_alt_down',return_value=trigger in ('alt_space','alt_tab')),patch('voice_flow.hotkeys._is_key_down',return_value=False),patch('voice_flow.hotkeys._suppress_win_start_menu'),patch('voice_flow.hotkeys.threading.Thread'),patch('voice_flow.hotkeys.time.time',return_value=100.0):
        def down():
            if path=='native': listener._on_native_key(vk,True,False,0)
            else: listener._on_key_press(key)
        def up():
            if path=='native': listener._on_native_key(vk,False,True,0)
            else: listener._on_key_release(key)
        down();up()
        if trigger=='double_ctrl': down();up()
        assert listener._is_recording
        with patch('voice_flow.storage.storage.get_setting',side_effect=lambda name,default=None:default):
            listener.reload_config({'hotkey_trigger':'custom','custom_hotkey':'F9','custom_trigger_type':'hold','dictation_trigger_mode':'disabled','ctrl_key_dictation_enabled':False})
        down();up()
        assert not listener._is_recording
        listener._on_native_key(0x78,True,False,0)
        assert not listener._is_recording

@pytest.mark.parametrize('path',['native','fallback'])
@pytest.mark.parametrize('altgr',[False,True])
@pytest.mark.parametrize('recording',[False,True])
@pytest.mark.parametrize('vk,char',[(0x43,'c'),(0x56,'v'),(0x58,'x'),(0x41,'a'),(0x25,None)])
def test_normal_control_chords_preserve_custom_session(listener,path,altgr,recording,vk,char):
    from pynput import keyboard
    listener._parsed_custom_keys=parse_hotkey_string('F8')
    listener._custom_trigger_type='hold'
    listener._ctrl_key_dictation_enabled=False
    listener._is_recording=recording
    listener._custom_hotkey_triggered=recording
    key=keyboard.Key.left if char is None else keyboard.KeyCode.from_char(char)
    with patch('voice_flow.hotkeys._is_ctrl_down',return_value=True),patch('voice_flow.hotkeys._is_alt_down',return_value=altgr),patch('voice_flow.hotkeys._is_win_down',return_value=False),patch('voice_flow.hotkeys._is_shift_down',return_value=False),patch('voice_flow.hotkeys._is_key_down',return_value=recording),patch('voice_flow.storage.storage.get_setting',side_effect=lambda name,default=None:default),patch('voice_flow.hotkeys.threading.Thread'):
        if path=='native':
            assert listener._on_native_key(0x11,True,False,0) is False
            assert listener._on_native_key(vk,True,False,0) is False
            assert listener._on_native_key(vk,True,False,0) is False
            assert listener._on_native_key(vk,False,True,0) is False
            assert listener._on_native_key(0x11,False,True,0) is False
        else:
            listener._on_key_press(keyboard.Key.ctrl)
            listener._on_key_press(key)
            listener._on_key_press(key)
            listener._on_key_release(key)
            listener._on_key_release(keyboard.Key.ctrl)
    assert listener._is_recording is recording
    assert listener._custom_hotkey_triggered is recording
    listener._on_start.assert_not_called()
    listener._on_finish.assert_not_called()

@pytest.mark.parametrize('path',['native','fallback'])
@pytest.mark.parametrize('shortcut',['Double Escape','Double Ctrl+Escape'])
def test_validated_escape_double_tap_cannot_silently_fail(listener,path,shortcut):
    from pynput import keyboard
    parsed=parse_hotkey_string(shortcut)
    listener._parsed_custom_keys=parsed
    listener._custom_trigger_type='double_tap'
    with patch('voice_flow.hotkeys._is_ctrl_down',return_value='Ctrl' in shortcut),patch('voice_flow.hotkeys._is_alt_down',return_value=False),patch('voice_flow.hotkeys._is_win_down',return_value=False),patch('voice_flow.hotkeys._is_shift_down',return_value=False),patch('voice_flow.hotkeys.threading.Thread'),patch('voice_flow.hotkeys.time.time',return_value=100.0):
        if path=='native':
            listener._on_native_key(0x1B,True,False,0)
            listener._on_native_key(0x1B,False,True,0)
            listener._on_native_key(0x1B,True,False,0)
        else:
            listener._on_key_press(keyboard.Key.esc)
            listener._on_key_release(keyboard.Key.esc)
            listener._on_key_press(keyboard.Key.esc)
    assert not parsed['valid'] or listener._is_recording

@pytest.mark.parametrize('shortcut',['Escape','Ctrl+Escape','Double Esc'])
def test_escape_is_reserved_for_cancel(shortcut):
    parsed=parse_hotkey_string(shortcut)
    assert not parsed['valid']
    assert 'cancel' in parsed['error'].lower()

@pytest.mark.parametrize('shortcut',['A','7','Minus','Plus','Comma','Period','Backquote'])
def test_standalone_typing_keys_warn_without_removing_support(shortcut):
    parsed=parse_hotkey_string(shortcut)
    assert parsed['valid']
    assert any('normal typing' in warning for warning in parsed['warnings'])

@pytest.mark.parametrize('path',['native','fallback'])
def test_capture_refusal_keeps_escape_cancel_available(listener,path,monkeypatch):
    from pynput import keyboard
    from voice_flow import hotkey_config
    monkeypatch.setattr(hotkey_config,'_capture_lease',('',0.0))
    listener._is_recording=True
    assert not listener.begin_shortcut_capture('fixture')
    with patch('voice_flow.hotkeys._is_ctrl_down',return_value=False),patch('voice_flow.hotkeys._is_alt_down',return_value=False),patch('voice_flow.hotkeys._is_win_down',return_value=False),patch('voice_flow.hotkeys._is_shift_down',return_value=False),patch('voice_flow.hotkeys.threading.Thread'):
        if path=='native': assert listener._on_native_key(0x1B,True,False,0) is True
        else: listener._on_key_press(keyboard.Key.esc)
    assert not listener._is_recording
