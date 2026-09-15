from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch, MagicMock

import pytest

from voice_flow.gui import api_server
from voice_flow.storage import StorageEngine
import voice_flow.video_flow_providers as vf_providers


@pytest.fixture
def custom_test_server(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'voice_flow_custom_test.db')
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, 'storage', test_storage)

    # Initialize VideoFlowProviderService with test db as well
    vf_service = vf_providers.VideoFlowProviderService(db_path)
    monkeypatch.setattr(api_server, 'video_flow_provider_service', vf_service)

    server = ThreadingHTTPServer(('127.0.0.1', 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f'http://127.0.0.1:{port}'

    yield {
        'base_url': base_url,
        'storage': test_storage,
        'vf_service': vf_service,
        'server': server,
    }

    server.shutdown()
    server.server_close()


def _get(url: str) -> tuple[int, dict, dict]:
    req = urllib.request.Request(url, headers={'Connection': 'close'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode('utf-8'))
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        body = json.loads(e.read().decode('utf-8'))
        return e.code, headers, body


def _post(url: str, payload: dict) -> tuple[int, dict, dict]:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json', 'Connection': 'close'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode('utf-8'))
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        body = json.loads(e.read().decode('utf-8'))
        return e.code, headers, body


# ==============================================================================
# 1. VOICE FLOW CUSTOM PROVIDERS TESTS
# ==============================================================================

def test_voice_flow_custom_provider_full_lifecycle(custom_test_server):
    base = custom_test_server['base_url']

    # 1. Add custom provider
    status, _, data = _post(f'{base}/api/voice-flow/custom-providers/add', {
        'name': 'Local Llama Voice',
        'base_url': 'http://localhost:11434/v1',
        'api_key': 'secret-voice-key',
        'api_format': 'openai',
        'headers': {'X-Custom-Test': 'voice-1'},
        'models': [
            {'model_id': 'llama-3.2-3b', 'display_name': 'Llama 3.2 3B', 'is_active': True},
            {'model_id': 'qwen-2.5-7b', 'display_name': 'Qwen 2.5 7B', 'is_active': True},
        ],
    })
    assert status == 200
    assert data.get('success') is True
    providers = data.get('providers', [])
    created = next((p for p in providers if p['name'] == 'Local Llama Voice'), None)
    assert created is not None
    prov_id = created['id']
    assert prov_id.startswith('custom-')
    assert len(created['models']) == 2
    assert created.get('headers') == {'X-Custom-Test': 'voice-1'}

    # 2. List custom providers
    status, _, list_data = _get(f'{base}/api/voice-flow/custom-providers/list')
    assert status == 200
    assert any(p['id'] == prov_id for p in list_data.get('providers', []))

    # 3. Update custom provider (change name, models, base_url, omit api_key to preserve it)
    status, _, upd_data = _post(f'{base}/api/voice-flow/custom-providers/update', {
        'id': prov_id,
        'name': 'Local Llama Voice Renamed',
        'base_url': 'http://localhost:11434/v2',
        'api_format': 'anthropic',
        'headers': {'X-Custom-Test': 'voice-updated'},
        'models': [
            {'model_id': 'llama-3.2-3b', 'display_name': 'Llama 3.2 3B', 'is_active': True},
        ],
    })
    assert status == 200
    assert upd_data.get('success') is True
    updated = next((p for p in upd_data.get('providers', []) if p['id'] == prov_id), None)
    assert updated is not None
    assert updated['name'] == 'Local Llama Voice Renamed'
    assert updated['base_url'] == 'http://localhost:11434/v2'
    assert updated['api_format'] == 'anthropic'
    assert updated['headers'] == {'X-Custom-Test': 'voice-updated'}
    assert len(updated['models']) == 1

    # Verify existing API key was preserved in database
    db_p = next((p for p in custom_test_server['storage'].get_voice_flow_custom_providers() if p['id'] == prov_id), None)
    assert db_p is not None
    assert db_p['api_key'] == 'secret-voice-key'

    # 4. Delete custom model from provider
    model_id_to_del = 'llama-3.2-3b'
    status, _, del_m_data = _post(f'{base}/api/providers/models/delete', {
        'provider': prov_id,
        'id': model_id_to_del,
    })
    assert status == 200
    assert del_m_data.get('success') is True
    db_p_after_model_del = next((p for p in custom_test_server['storage'].get_voice_flow_custom_providers() if p['id'] == prov_id), None)
    assert len(db_p_after_model_del['models']) == 0

    # 5. Delete custom provider
    status, _, del_data = _post(f'{base}/api/voice-flow/custom-providers/delete', {'id': prov_id})
    assert status == 200
    assert del_data.get('success') is True
    assert not any(p['id'] == prov_id for p in del_data.get('providers', []))


# ==============================================================================
# 2. AUDIO FLOW CUSTOM PROVIDERS TESTS
# ==============================================================================

def test_audio_flow_custom_provider_full_lifecycle(custom_test_server):
    base = custom_test_server['base_url']

    # 1. Add custom audio provider
    status, _, data = _post(f'{base}/api/audio-flow/custom-providers/add', {
        'name': 'Local Piper TTS',
        'base_url': 'http://localhost:5000/v1',
        'api_key': 'piper-secret-key',
        'api_format': 'openai',
        'headers': {'Authorization': 'Bearer piper-secret-key'},
        'models': [
            {'model_id': 'en_US-lessac-medium', 'display_name': 'Lessac Medium', 'is_active': True},
            {'model_id': 'en_US-ryan-medium', 'display_name': 'Ryan Medium', 'is_active': True},
        ],
    })
    assert status == 200
    assert data.get('success') is True
    providers = data.get('providers', [])
    created = next((p for p in providers if p['name'] == 'Local Piper TTS'), None)
    assert created is not None
    prov_id = created['id']
    assert prov_id.startswith('custom-')
    assert len(created['models']) == 2
    assert created.get('headers') == {'Authorization': 'Bearer piper-secret-key'}

    # 2. List custom audio providers
    status, _, list_data = _get(f'{base}/api/audio-flow/custom-providers/list')
    assert status == 200
    assert any(p['id'] == prov_id for p in list_data.get('providers', []))

    # 3. Update custom audio provider (change base_url, format to elevenlabs, omit key to preserve)
    status, _, upd_data = _post(f'{base}/api/audio-flow/custom-providers/update', {
        'id': prov_id,
        'name': 'Local Piper TTS Updated',
        'base_url': 'http://localhost:5000/v2',
        'api_format': 'elevenlabs',
        'models': [
            {'model_id': 'en_US-lessac-medium', 'display_name': 'Lessac Medium', 'is_active': True},
        ],
    })
    assert status == 200
    assert upd_data.get('success') is True
    updated = next((p for p in upd_data.get('providers', []) if p['id'] == prov_id), None)
    assert updated is not None
    assert updated['name'] == 'Local Piper TTS Updated'
    assert updated['base_url'] == 'http://localhost:5000/v2'
    assert updated['api_format'] == 'elevenlabs'
    assert len(updated['models']) == 1

    # Verify key preserved in database
    db_p = next((p for p in custom_test_server['storage'].get_audio_flow_custom_providers() if p['id'] == prov_id), None)
    assert db_p is not None
    assert db_p['api_key'] == 'piper-secret-key'

    # 4. Delete custom voice model from provider
    model_id_to_del = 'en_US-lessac-medium'
    status, _, del_m_data = _post(f'{base}/api/audio-providers/models/delete', {
        'provider': prov_id,
        'id': model_id_to_del,
    })
    assert status == 200
    assert del_m_data.get('success') is True
    db_p_after_del = next((p for p in custom_test_server['storage'].get_audio_flow_custom_providers() if p['id'] == prov_id), None)
    assert len(db_p_after_del['models']) == 0

    # 5. Delete custom audio provider
    status, _, del_data = _post(f'{base}/api/audio-flow/custom-providers/delete', {'id': prov_id})
    assert status == 200
    assert del_data.get('success') is True
    assert not any(p['id'] == prov_id for p in del_data.get('providers', []))


# ==============================================================================
# 3. VIDEO FLOW CUSTOM PROVIDERS TESTS
# ==============================================================================

def test_video_flow_custom_provider_full_lifecycle(custom_test_server):
    base = custom_test_server['base_url']

    # 1. Add custom provider
    status, _, data = _post(f'{base}/api/video-flow/custom-providers/add', {
        'name': 'DeepSeek Video Engine',
        'base_url': 'https://api.deepseek.com/v1',
        'api_key': 'deepseek-key-123',
        'api_format': 'openai',
        'headers': {'X-Org': 'TestCorp'},
        'models': [
            {'model_id': 'deepseek-chat', 'display_name': 'DeepSeek Chat'},
            {'model_id': 'deepseek-coder', 'display_name': 'DeepSeek Coder'},
        ],
    })
    assert status == 200
    assert data.get('success') is True
    providers = data.get('providers', [])
    created = next((p for p in providers if p['name'] == 'DeepSeek Video Engine'), None)
    assert created is not None
    prov_id = created['id']

    # 2. Update custom provider
    status, _, upd_data = _post(f'{base}/api/video-flow/custom-providers/update', {
        'id': prov_id,
        'name': 'DeepSeek Video Engine Updated',
        'base_url': 'https://api.deepseek.com/v1beta',
        'api_format': 'openai',
        'headers': {'X-Org': 'TestCorp2'},
        'models': [
            {'model_id': 'deepseek-chat', 'display_name': 'DeepSeek Chat'},
        ],
    })
    assert status == 200
    assert upd_data.get('success') is True
    updated = next((p for p in upd_data.get('providers', []) if p['id'] == prov_id), None)
    assert updated['name'] == 'DeepSeek Video Engine Updated'
    assert updated['base_url'] == 'https://api.deepseek.com/v1beta'
    assert updated['headers'] == {'X-Org': 'TestCorp2'}

    # Verify key preserved in database
    db_p = next((p for p in custom_test_server['storage'].get_video_flow_custom_providers() if p['id'] == prov_id), None)
    assert db_p['api_key'] == 'deepseek-key-123'

    # 3. Delete custom model via m-0 index
    status, _, del_m_data = _post(f'{base}/api/video-flow/providers/models/delete', {
        'provider': prov_id,
        'id': 'm-0',
    })
    assert status == 200
    assert del_m_data.get('success') is True

    # 4. Delete provider
    status, _, del_data = _post(f'{base}/api/video-flow/custom-providers/delete', {'id': prov_id})
    assert status == 200
    assert del_data.get('success') is True
    assert not any(p['id'] == prov_id for p in del_data.get('providers', []))


# ==============================================================================
# 4. DIRECT PROBE / TEST ENDPOINT ON CUSTOM PROVIDERS
# ==============================================================================

def test_custom_provider_test_endpoint_with_mock_probe(custom_test_server):
    base = custom_test_server['base_url']

    with patch('voice_flow.gui.api_server.VoiceFlowApiHandler._probe_custom_endpoint_direct', return_value={'success': True, 'latency_ms': 42, 'message': 'OK'}):
        # Voice Flow test
        status, _, data_vf = _post(f'{base}/api/voice-flow/custom-providers/test', {
            'base_url': 'https://custom.llm.example.com',
            'api_key': 'test-key',
            'api_format': 'openai',
            'model_id': 'test-model',
        })
        assert status == 200
        assert data_vf.get('ok') is True
        assert data_vf.get('latency_ms') == 42

        # Audio Flow test
        status, _, data_af = _post(f'{base}/api/audio-flow/custom-providers/test', {
            'base_url': 'https://custom.tts.example.com',
            'api_key': 'test-key',
            'api_format': 'elevenlabs',
            'model_id': 'test-voice',
        })
        assert status == 200
        assert data_af.get('ok') is True
        assert data_af.get('latency_ms') == 42

        # Video Flow test
        status, _, data_vdf = _post(f'{base}/api/video-flow/custom-providers/test', {
            'base_url': 'https://custom.video.example.com',
            'api_key': 'test-key',
            'api_format': 'gemini',
            'model_id': 'gemini-1.5-flash',
        })
        assert status == 200
        assert data_vdf.get('ok') is True
        assert data_vdf.get('latency_ms') == 42


# ==============================================================================
# 5. ROUND-ROBIN PERSISTENCE (AUDIO FLOW & VOICE FLOW)
# ==============================================================================

def test_audio_flow_and_voice_flow_round_robin_persistence(custom_test_server):
    base = custom_test_server['base_url']

    # --- AUDIO FLOW ROUND-ROBIN ---
    # 1. Default check
    status, _, data = _get(f'{base}/api/audio-providers/details?provider=elevenlabs')
    assert status == 200
    assert data.get('load_balance_mode') in ('priority', 'round_robin', None)

    # 2. Set to round_robin
    status, _, save_data = _post(f'{base}/api/audio-providers/mode/save', {
        'provider': 'elevenlabs',
        'mode': 'round_robin',
    })
    assert status == 200
    assert save_data.get('success') is True
    assert save_data.get('mode') == 'round_robin'

    # Verify persistence via GET /details
    status, _, details_after = _get(f'{base}/api/audio-providers/details?provider=elevenlabs')
    assert status == 200
    assert details_after.get('load_balance_mode') == 'round_robin'
    assert details_after.get('mode') == 'round_robin'

    # Switch back to priority
    status, _, save_prio = _post(f'{base}/api/audio-providers/mode/save', {
        'provider': 'elevenlabs',
        'mode': 'priority',
    })
    assert status == 200
    assert save_prio.get('success') is True
    assert save_prio.get('mode') == 'priority'

    status, _, details_prio = _get(f'{base}/api/audio-providers/details?provider=elevenlabs')
    assert status == 200
    assert details_prio.get('load_balance_mode') == 'priority'

    # --- VOICE FLOW ROUND-ROBIN ---
    # Set to round_robin
    status, _, vf_save = _post(f'{base}/api/providers/mode/save', {
        'provider': 'openai',
        'mode': 'round_robin',
    })
    assert status == 200
    assert vf_save.get('success') is True
    assert vf_save.get('mode') == 'round_robin'

    status, _, vf_details = _get(f'{base}/api/providers/details?provider=openai')
    assert status == 200
    assert vf_details.get('load_balance_mode') == 'round_robin'


# ==============================================================================
# 6. SINGLE MODEL TESTING (TTS & LLM)
# ==============================================================================

def test_custom_provider_single_model_testing(custom_test_server):
    base = custom_test_server['base_url']

    with patch.object(api_server.VoiceFlowApiHandler, 'verify_model_by_kind', return_value={'success': True, 'latency_ms': 38}):
        # TTS model test
        status, _, data_tts = _post(f'{base}/api/providers/models/test', {
            'provider': 'custom-local-tts',
            'model_id': 'alloy',
            'kind': 'tts',
        })
        assert status == 200
        assert data_tts.get('success') is True
        assert data_tts.get('ok') is True
        assert data_tts.get('latency_ms') is not None

        # LLM model test
        status, _, data_llm = _post(f'{base}/api/providers/models/test', {
            'provider': 'custom-local-llm',
            'model_id': 'llama-3',
            'kind': 'llm',
        })
        assert status == 200
        assert data_llm.get('success') is True
        assert data_llm.get('ok') is True


# ==============================================================================
# 7. EDGE CASES & ERROR PATHS
# ==============================================================================

def test_custom_provider_edge_cases(custom_test_server):
    base = custom_test_server['base_url']

    # 1. Missing name
    status, _, err1 = _post(f'{base}/api/voice-flow/custom-providers/add', {
        'name': '',
        'base_url': 'http://localhost:8000',
        'models': ['m1'],
    })
    assert status == 400
    assert err1.get('success') is False

    # 2. Missing base_url
    status, _, err2 = _post(f'{base}/api/audio-flow/custom-providers/add', {
        'name': 'Test Voice',
        'base_url': '',
        'models': ['m1'],
    })
    assert status == 400
    assert err2.get('success') is False

    # 3. Update without id
    status, _, err3 = _post(f'{base}/api/voice-flow/custom-providers/update', {
        'name': 'No ID Voice',
    })
    assert status == 400
    assert err3.get('success') is False

    # 4. Update non-existent id
    status, _, err4 = _post(f'{base}/api/voice-flow/custom-providers/update', {
        'id': 'custom-does-not-exist',
        'name': 'Does Not Exist',
    })
    assert status == 400
    assert err4.get('success') is False

    # 5. Test without base_url
    status, _, err5 = _post(f'{base}/api/voice-flow/custom-providers/test', {
        'base_url': '',
    })
    assert status == 400
    assert err5.get('success') is False


# ==============================================================================
# 8. OUT-OF-ORDER CONNECTION DELETION & FIND-BY-ID AUDIT TESTS
# ==============================================================================

def test_connection_id_lookup_and_out_of_order_deletion(custom_test_server):
    base = custom_test_server['base_url']

    # Add custom voice provider with 1 primary key
    status, _, add_res = _post(f'{base}/api/voice-flow/custom-providers/add', {
        'name': 'Multi-Conn Provider',
        'base_url': 'http://localhost:8000',
        'api_key': 'key-primary',
        'models': ['m1'],
    })
    assert status == 200
    prov_id = add_res['providers'][-1]['id']

    # Add a second connection
    status, _, conn_add = _post(f'{base}/api/providers/connections/add', {
        'provider': prov_id,
        'name': 'Second Key',
        'key': 'key-secondary',
        'priority': 2,
    })
    assert status == 200

    # Delete connection c-0 (the first connection)
    status, _, del_res = _post(f'{base}/api/providers/connections/delete', {
        'provider': prov_id,
        'id': 'c-0',
    })
    assert status == 200
    assert del_res.get('success') is True

    # Now only 1 connection remains (the second key).
    # Operating on c-1 must NOT fail with 404 (the prior len(conns) index bug).
    status, _, upd_res = _post(f'{base}/api/providers/connections/update', {
        'provider': prov_id,
        'id': 'c-1',
        'name': 'Second Key Renamed',
    })
    assert status == 200
    assert upd_res.get('success') is True

    # Toggling c-1 must also succeed
    status, _, tog_res = _post(f'{base}/api/providers/connections/toggle', {
        'provider': prov_id,
        'id': 'c-1',
        'is_active': False,
    })
    assert status == 200
    assert tog_res.get('success') is True

    # Deleting c-1 must also succeed
    status, _, del2_res = _post(f'{base}/api/providers/connections/delete', {
        'provider': prov_id,
        'id': 'c-1',
    })
    assert status == 200
    assert del2_res.get('success') is True


# ==============================================================================
# 9. VIDEO FLOW PARITY & ADVANCED AUDIT TESTS
# ==============================================================================

def test_video_flow_custom_model_operations_and_settings(custom_test_server):
    base = custom_test_server['base_url']

    # Add a custom video flow provider
    status, _, add_res = _post(f'{base}/api/video-flow/custom-providers/add', {
        'name': 'Video Test Custom',
        'base_url': 'http://localhost:8000',
        'api_key': 'video-key-1',
        'models': [
            {'model_id': 'model-vid-alpha', 'display_name': 'Alpha Vid', 'is_active': True},
            {'model_id': 'model-vid-beta', 'display_name': 'Beta Vid', 'is_active': True},
        ],
    })
    assert status == 200
    v_id = add_res['providers'][-1]['id']

    # 1. Toggle model by string model_id
    status, _, tog_res = _post(f'{base}/api/video-flow/providers/models/toggle', {
        'provider': v_id,
        'id': 'model-vid-alpha',
        'is_active': False,
    })
    assert status == 200
    assert tog_res.get('success') is True

    # 2. Delete model by string model_id
    status, _, del_res = _post(f'{base}/api/video-flow/providers/models/delete', {
        'provider': v_id,
        'id': 'model-vid-beta',
    })
    assert status == 200
    assert del_res.get('success') is True

    # 3. Add 2 connections for video custom provider
    status, _, conn1 = _post(f'{base}/api/video-flow/providers/connections/add', {
        'provider': v_id,
        'name': 'Vid Key 2',
        'secret': 'video-key-2',
        'priority': 2,
    })
    assert status == 200

    # 4. Reorder connections without provider field (as video-flow.js did)
    status, _, reorder_res = _post(f'{base}/api/video-flow/providers/connections/reorder', {
        'connection_ids': ['c-1', 'c-0'],
    })
    assert status == 200
    assert reorder_res.get('success') is True

    # 5. Load balance settings update & persistence in details
    status, _, set_res = _post(f'{base}/api/video-flow/providers/settings', {
        'provider': v_id,
        'load_balance_mode': 'round_robin',
    })
    assert status == 200
    assert set_res.get('load_balance_mode') == 'round_robin'

    status, _, det_res = _get(f'{base}/api/video-flow/providers/details?provider={v_id}')
    assert status == 200
    assert det_res.get('load_balance_mode') == 'round_robin'


# ==============================================================================
# 10. VERIFY MODEL BY KIND: GEMINI & CUSTOM HEADERS
# ==============================================================================

def test_verify_model_by_kind_gemini_and_headers(custom_test_server):
    handler = api_server.VoiceFlowApiHandler
    mock_instance = MagicMock()

    # Test gemini format
    custom_gemini = {
        'id': 'custom-gemini-test',
        'name': 'Custom Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta',
        'api_format': 'gemini',
        'api_key': 'gemini-test-key',
        'headers': {'X-Test-Hdr': 'gemini-val'},
        'models': [{'model_id': 'gemini-1.5-flash'}],
    }
    custom_test_server['storage'].add_voice_flow_custom_provider(custom_gemini)

    with patch('urllib.request.urlopen') as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"candidates": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = handler.verify_model_by_kind(
            mock_instance,
            provider='custom-gemini-test',
            model_id='gemini-1.5-flash',
            kind='llm',
        )
        assert result.get('success') is True
        # Verify request details
        req_sent = mock_urlopen.call_args[0][0]
        assert 'gemini-1.5-flash:generateContent' in req_sent.full_url
        headers_lower = {k.lower(): v for k, v in req_sent.headers.items()}
        assert headers_lower.get('x-test-hdr') == 'gemini-val'


# ==============================================================================
# 11. VERIFY TTS API KEY FOR CUSTOM AUDIO PROVIDER
# ==============================================================================

def test_verify_tts_api_key_custom_provider(custom_test_server):
    handler = api_server.VoiceFlowApiHandler
    mock_instance = MagicMock()

    custom_audio = {
        'id': 'custom-tts-test',
        'name': 'Custom TTS',
        'base_url': 'http://localhost:8000/v1',
        'api_format': 'openai',
        'api_key': 'tts-secret-key',
        'models': [{'model_id': 'tts-1'}],
    }
    custom_test_server['storage'].add_audio_flow_custom_provider(custom_audio)

    with patch.object(handler, '_probe_custom_endpoint_direct', return_value={'success': True, 'message': 'TTS ok'}):
        res = handler.verify_tts_api_key(mock_instance, 'custom-tts-test', 'tts-secret-key')
        assert res.get('valid') is True
        assert 'Connected' in res.get('status', '')


