from unittest.mock import Mock, patch

from voice_flow.audio import AudioRecorder
from voice_flow.config import config
from voice_flow.microphone_devices import build_input_catalog, resolve_input_device, load_microphone_preference, display_input_catalog
import numpy as np
import pytest


def test_selected_native_only_microphone_never_switches_to_default(monkeypatch):
    monkeypatch.setattr(config, 'selected_mic_device', 'USB Headset')
    rows = [{'name': 'Laptop', 'max_input_channels': 1, 'default_samplerate': 16000},
            {'name': 'USB Headset', 'max_input_channels': 1, 'default_samplerate': 48000}]
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if kwargs['samplerate'] == 16000 and kwargs.get('device') is not None:
            raise ValueError('unsupported sample rate')
        return Mock()
    def query(device=None, kind=None):
        return rows if kind is None else rows[1]
    with patch('voice_flow.audio.sd.query_devices', side_effect=query), patch('voice_flow.audio.sd.query_hostapis', return_value=[]), patch('voice_flow.audio.sd.InputStream', side_effect=create):
        recorder = AudioRecorder()
        assert recorder.start()
        recorder.close()
    assert all(call.get('device') in ('USB Headset', 1) for call in calls), calls
    assert config.selected_mic_device == 'USB Headset'


def test_missing_microphone_keeps_preference(monkeypatch):
    monkeypatch.setattr(config, 'selected_mic_device', 'USB Headset')
    with patch('voice_flow.audio.sd.query_devices', return_value=[]), patch('voice_flow.audio.sd.query_hostapis', return_value=[]), patch('voice_flow.audio.sd.InputStream', return_value=Mock()):
        recorder = AudioRecorder()
        assert not recorder.start()
        assert recorder.last_device_error
        recorder.close()
    assert config.selected_mic_device == 'USB Headset'


def catalog_rows():
    return [{'name': 'Laptop', 'hostapi': 0, 'max_input_channels': 1, 'default_samplerate': 16000},
            {'name': '耳机', 'hostapi': 1, 'max_input_channels': 2, 'default_samplerate': 48000},
            {'name': 'Headphones output', 'hostapi': 1, 'max_input_channels': 0}]


def test_catalog_input_capabilities_and_index_zero_default():
    catalog = build_input_catalog(catalog_rows(), [{'name': 'MME'}, {'name': 'Windows WASAPI'}], 0)
    assert len(catalog) == 2
    assert catalog[0]['is_default']
    assert not catalog[1]['is_default']
    assert catalog[1]['name'] == '耳机'


def test_stable_identity_reorder_disconnect_reconnect_and_hostapi_collision():
    rows = catalog_rows()
    apis = [{'name': 'MME'}, {'name': 'Windows WASAPI'}]
    preference = build_input_catalog(rows, apis)[1]['identity']
    assert resolve_input_device(preference, build_input_catalog([rows[1], rows[0], rows[2]], apis))['index'] == 0
    assert resolve_input_device(preference, build_input_catalog(rows[:1], apis)) is None
    rows.insert(0, dict(rows[1], hostapi=0))
    assert resolve_input_device(preference, build_input_catalog(rows, apis))['index'] == 2
    assert resolve_input_device('耳机', build_input_catalog(rows, apis))['hostapi'] == 'Windows WASAPI'


def test_duplicates_unknown_hostapi_and_bad_identity_are_not_guessed():
    row = catalog_rows()[1]
    catalog = build_input_catalog([row, row], [])
    assert all(r['ambiguous'] for r in catalog)
    assert resolve_input_device(catalog[0]['identity'], catalog) is None
    for invalid in ['vfmic:{', 'vfmic:[]', 'vfmic:[1,2]', True, -1, 'USB']:
        assert resolve_input_device(invalid, catalog) is None
    singleton = build_input_catalog([row], [])
    assert resolve_input_device(0, singleton) == singleton[0]
    assert resolve_input_device('耳机', singleton) == singleton[0]
    assert build_input_catalog([], []) == []


@pytest.mark.parametrize('values,expected', [
    ({'selected_mic_device': 'vfmic:["USB","MME"]'}, 'vfmic:["USB","MME"]'),
    ({'selected_mic_device': None, 'selected_microphone': 'old'}, None),
    ({'selected_microphone': 'old'}, 'old'), ({}, None)])
def test_startup_preference_no_device_query_or_setting_mutation(values, expected):
    settings = Mock()
    settings.get_setting.side_effect = lambda key, default=None: values.get(key, default)
    with patch('voice_flow.audio.sd.query_devices', side_effect=AssertionError('startup discovery')):
        assert load_microphone_preference(settings) == expected
    settings.save_setting.assert_not_called()
    # Execute the actual startup block alone, without desktop/model init.
    from pathlib import Path
    from types import SimpleNamespace
    source = (Path(__file__).parents[1] / 'src/voice_flow/main.py').read_text(encoding='utf-8')
    start = source.index('        from voice_flow.microphone_devices import load_microphone_preference')
    end = source.index('        self.transcriber = Transcriber()', start)
    import textwrap
    cfg = SimpleNamespace(selected_mic_device='stale')
    exec(textwrap.dedent(source[start:end]), {'config': cfg, 'storage': settings, 'self': SimpleNamespace()})
    assert cfg.selected_mic_device == expected


def test_native_stereo_negotiation_retains_initial_final_frames(monkeypatch):
    monkeypatch.setattr(config, 'selected_mic_device', 'USB Headset')
    row = {'name': 'USB Headset', 'max_input_channels': 2, 'default_samplerate': 48000}
    calls = []
    recorder = AudioRecorder()
    initial = np.full((480, 2), .05, dtype=np.float32)
    final = np.full((480, 2), .1, dtype=np.float32)
    def create(**kwargs):
        calls.append(kwargs)
        if (kwargs['samplerate'], kwargs['channels']) != (48000, 2):
            raise ValueError('native stereo only')
        stream = Mock()
        stream.start.side_effect = lambda: recorder._audio_callback(initial, 480, None, None)
        stream.stop.side_effect = lambda: recorder._audio_callback(final, 480, None, None)
        return stream
    with patch('voice_flow.audio.sd.query_devices', return_value=[row]), patch('voice_flow.audio.sd.query_hostapis', return_value=[]), patch('voice_flow.audio.sd.InputStream', side_effect=create):
        recorder.begin_stream_input_buffering()
        assert recorder.start()
        audio, tail, overlap = recorder.stop_and_take_open_chunk()
    assert len(calls) == 3
    assert all(call['device'] == 0 for call in calls)
    assert audio.shape == (320,)
    np.testing.assert_array_equal(tail, np.concatenate([initial, final]))
    assert overlap == 0
    assert config.selected_mic_device == 'USB Headset'


def test_default_format_retry_stays_on_windows_default(monkeypatch):
    monkeypatch.setattr(config, 'selected_mic_device', None)
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if kwargs['samplerate'] == 16000:
            raise ValueError('unsupported')
        return Mock()
    with patch('voice_flow.audio.sd.query_devices', return_value={'default_samplerate':48000,'max_input_channels':1}) as query, patch('voice_flow.audio.sd.InputStream', side_effect=create):
        recorder = AudioRecorder()
        assert recorder.start()
        recorder.close()
    query.assert_called_once_with(kind='input')
    assert all('device' not in call for call in calls)


def test_failed_start_closes_stream_retains_choice_and_recovers(monkeypatch):
    monkeypatch.setattr(config, 'selected_mic_device', 'Laptop')
    failed = Mock()
    failed.start.side_effect = ValueError('disconnected while opening')
    recovered = Mock()
    with patch('voice_flow.audio.sd.query_devices', return_value=catalog_rows()), patch('voice_flow.audio.sd.query_hostapis', return_value=[]), patch('voice_flow.audio.sd.InputStream', side_effect=[failed, recovered]):
        recorder = AudioRecorder()
        assert not recorder.start()
        assert not recorder.is_recording
        failed.close.assert_called_once()
        assert 'disconnected' in recorder.last_device_error
        assert config.selected_mic_device == 'Laptop'
        assert recorder.start()
        assert recorder.last_device_error is None
        recorder.close()


def test_selected_identity_start_routes_reordered_index(monkeypatch):
    rows = catalog_rows()
    apis = [{'name':'MME'}, {'name':'Windows WASAPI'}]
    identity = build_input_catalog(rows, apis)[1]['identity']
    monkeypatch.setattr(config, 'selected_mic_device', identity)
    with patch('voice_flow.audio.sd.query_devices', return_value=[rows[1], rows[0], rows[2]]), patch('voice_flow.audio.sd.query_hostapis', return_value=apis), patch('voice_flow.audio.sd.InputStream', return_value=Mock()) as stream:
        recorder = AudioRecorder()
        assert recorder.start()
        assert stream.call_args.kwargs['device'] == 0
        recorder.close()
    assert config.selected_mic_device == identity


def test_legacy_exact_name_aliases_choose_wasapi_and_refuse_best_api_duplicates():
    row = {'name': 'USB Headset', 'max_input_channels': 1, 'default_samplerate': 48000}
    apis = [{'name': 'MME'}, {'name': 'Windows DirectSound'}, {'name': 'Windows WASAPI'}]
    rows = [dict(row, hostapi=i) for i in range(3)]
    catalog = build_input_catalog(rows, apis)
    assert resolve_input_device('USB Headset', catalog)['index'] == 2
    rows.append(dict(row, hostapi=2))
    assert resolve_input_device('USB Headset', build_input_catalog(rows, apis)) is None
    assert resolve_input_device('USB', catalog) is None
    assert resolve_input_device(catalog[0]['identity'], catalog)['index'] == 0
    assert [r['index'] for r in display_input_catalog(catalog)] == [2]
    assert [r['index'] for r in display_input_catalog(catalog, catalog[0]['identity'])] == [0, 2]
    assert len(catalog) == 3
    assert len(display_input_catalog(build_input_catalog(rows, apis))) == 2


class FakeDeviceRegistry:
    def __init__(self):
        from types import SimpleNamespace
        self._initialized = 1
        self._last_callback = None
        self.default = SimpleNamespace(device=[0, -1])
        self.rows = catalog_rows()[:1]
        self._terminate = Mock(side_effect=self.terminate)
        self._initialize = Mock(side_effect=self.initialize)
    def terminate(self):
        self._initialized -= 1
    def initialize(self):
        self._initialized += 1
        self.rows = catalog_rows()[:2]
    def query_devices(self):
        return self.rows
    def query_hostapis(self):
        return [{'name': 'MME'}, {'name': 'Windows WASAPI'}]


def test_idle_refresh_refreshes_cached_snapshot_without_stream():
    from voice_flow.microphone_devices import query_input_catalog
    registry = FakeDeviceRegistry()
    assert len(query_input_catalog(registry)['devices']) == 1
    assert registry._terminate.call_count == 0
    result = query_input_catalog(registry, refresh=True)
    assert result['refreshed'] and not result['error']
    assert len(result['devices']) == 2
    registry._terminate.assert_called_once()
    registry._initialize.assert_called_once()


def test_refresh_declines_registered_active_and_convenience_streams():
    from voice_flow.microphone_devices import query_input_catalog
    from types import SimpleNamespace
    registry = FakeDeviceRegistry()
    recorder = AudioRecorder()
    recorder._stream = SimpleNamespace(closed=False)
    result = query_input_catalog(registry, refresh=True)
    assert result['busy'] and not result['refreshed']
    registry._terminate.assert_not_called()
    recorder._stream = None
    registry._last_callback = SimpleNamespace(stream=SimpleNamespace(closed=False))
    assert query_input_catalog(registry, refresh=True)['busy']
    registry._terminate.assert_not_called()
    registry._last_callback.stream.closed = True
    assert query_input_catalog(registry, refresh=True)['refreshed']


@pytest.mark.parametrize('count', [0, 2])
def test_refresh_declines_unexpected_initialization_ownership(count):
    from voice_flow.microphone_devices import query_input_catalog
    registry = FakeDeviceRegistry()
    registry._initialized = count
    result = query_input_catalog(registry, refresh=True)
    assert result['error'] and not result['refreshed']
    registry._terminate.assert_not_called()
    registry._initialize.assert_not_called()


def test_refresh_initialization_failure_does_not_repeat_reset():
    from voice_flow.microphone_devices import query_input_catalog
    registry = FakeDeviceRegistry()
    registry._initialize.side_effect = RuntimeError('driver initialization failed')
    result = query_input_catalog(registry, refresh=True)
    assert 'driver initialization failed' in result['error']
    assert not result['refreshed'] and registry._initialized == 0
    registry._terminate.assert_called_once()
    registry._initialize.assert_called_once()
    assert query_input_catalog(registry, refresh=True)['error']
    assert registry._terminate.call_count == 1
    registry._initialize.side_effect = registry.initialize
    recovered = query_input_catalog(registry, refresh=True)
    assert recovered['refreshed'] and len(recovered['devices']) == 2
    assert registry._terminate.call_count == 1


def test_failed_library_refresh_blocks_capture_without_changing_choice(monkeypatch):
    from voice_flow.microphone_devices import query_input_catalog
    registry = FakeDeviceRegistry()
    registry._initialize.side_effect = RuntimeError('init failed')
    query_input_catalog(registry, refresh=True)
    monkeypatch.setattr(config, 'selected_mic_device', 'USB Headset')
    with patch('voice_flow.audio.sd', registry):
        recorder = AudioRecorder()
        assert not recorder.start()
        assert 'Refresh devices' in recorder.last_device_error
    assert config.selected_mic_device == 'USB Headset'


def test_refresh_termination_failure_and_missing_hooks_are_truthful():
    from voice_flow.microphone_devices import query_input_catalog
    registry = FakeDeviceRegistry()
    registry._terminate.side_effect = RuntimeError('termination failed')
    result = query_input_catalog(registry, refresh=True)
    assert 'termination failed' in result['error'] and not result['refreshed']
    registry._initialize.assert_not_called()
    assert len(result['devices']) == 1
    registry._terminate = None
    assert 'does not support' in query_input_catalog(registry, refresh=True)['error']


def test_refresh_waits_for_stop_to_close_stream(monkeypatch):
    from voice_flow.microphone_devices import query_input_catalog
    import threading
    monkeypatch.setattr(config, 'selected_mic_device', None)
    registry = FakeDeviceRegistry()
    recorder = AudioRecorder()
    stopping = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    stream = Mock()
    stream.closed = False
    def stop():
        stopping.set()
        assert release.wait(2)
    stream.stop.side_effect = stop
    stream.close.side_effect = lambda: setattr(stream, 'closed', True)
    with patch('voice_flow.audio.sd.InputStream', return_value=stream):
        assert recorder.start()
    stopper = threading.Thread(target=recorder.stop)
    stopper.start()
    assert stopping.wait(1)
    result = []
    def refresh():
        result.append(query_input_catalog(registry, refresh=True))
        finished.set()
    refresher = threading.Thread(target=refresh)
    refresher.start()
    assert not finished.wait(.05)
    registry._terminate.assert_not_called()
    release.set()
    stopper.join(2)
    refresher.join(2)
    assert not stopper.is_alive() and not refresher.is_alive()
    assert result[0]['refreshed']


def test_failed_stream_close_keeps_refresh_busy_and_blocks_new_capture(monkeypatch):
    from voice_flow.microphone_devices import query_input_catalog
    monkeypatch.setattr(config, 'selected_mic_device', None)
    registry = FakeDeviceRegistry()
    recorder = AudioRecorder()
    stream = Mock()
    stream.closed = False
    stream.close.side_effect = RuntimeError('device refused close')
    with patch('voice_flow.audio.sd.InputStream', return_value=stream) as factory:
        assert recorder.start()
        recorder._audio_callback(np.full((8,1), .05, dtype=np.float32), 8, None, None)
        audio = recorder.stop()
        assert len(audio) == 8
        assert not recorder.is_recording
        assert query_input_catalog(registry, refresh=True)['busy']
        registry._terminate.assert_not_called()
        assert not recorder.start()
        assert not AudioRecorder().start()
        assert factory.call_count == 1
        stream.closed = True
        assert query_input_catalog(registry, refresh=True)['refreshed']


def test_stale_start_failed_close_does_not_open_another_stream(monkeypatch):
    monkeypatch.setattr(config, 'selected_mic_device', None)
    recorder = AudioRecorder()
    stale = Mock()
    stale.closed = False
    stale.close.side_effect = RuntimeError('close failed')
    recorder._stream = stale
    with patch('voice_flow.audio.sd.InputStream') as factory:
        assert not recorder.start()
        factory.assert_not_called()
        assert recorder.last_device_error
    stale.closed = True


def test_refresh_serializes_with_stream_construction_and_stop(monkeypatch):
    from voice_flow.microphone_devices import query_input_catalog
    import threading
    from types import SimpleNamespace
    monkeypatch.setattr(config, 'selected_mic_device', None)
    registry = FakeDeviceRegistry()
    constructing = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    recorder = AudioRecorder()
    stream = Mock()
    stream.closed = False
    stream.close.side_effect = lambda: setattr(stream, 'closed', True)
    def construct(**kwargs):
        constructing.set()
        assert release.wait(2)
        return stream
    result = []
    def refresh():
        result.append(query_input_catalog(registry, refresh=True))
        finished.set()
    with patch('voice_flow.audio.sd.InputStream', side_effect=construct):
        starter = threading.Thread(target=recorder.start)
        starter.start()
        assert constructing.wait(1)
        refresher = threading.Thread(target=refresh)
        refresher.start()
        assert not finished.wait(.05)
        release.set()
        starter.join(2)
        refresher.join(2)
        assert not starter.is_alive() and not refresher.is_alive()
        assert result[0]['busy']
        registry._terminate.assert_not_called()
        recorder.stop()
    assert query_input_catalog(registry, refresh=True)['refreshed']
