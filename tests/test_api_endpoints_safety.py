
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


@pytest.fixture
def test_server(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'voice_flow_api_safety_test.db')
    test_storage = StorageEngine(db_path)
    monkeypatch.setattr(api_server, 'storage', test_storage)
    monkeypatch.setattr('voice_flow.storage.storage', test_storage)

    server = ThreadingHTTPServer(('127.0.0.1', 0), api_server.VoiceFlowApiHandler)
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.15)
    port = server.server_address[1]
    base_url = f'http://127.0.0.1:{port}'

    yield {'base_url': base_url, 'storage': test_storage, 'server': server}

    server.shutdown()
    server.server_close()


def _get(url: str) -> tuple[int, dict, dict]:
    req = urllib.request.Request(url, headers={'Connection': 'close'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode('utf-8'))
            return resp.status, headers, body
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        body = json.loads(e.read().decode('utf-8'))
        return e.code, headers, body


def test_invalid_api_endpoints_return_json_404(test_server):
    base_url = test_server['base_url']

    # 1. GET /api/invalid-endpoint
    status, headers, body = _get(f'{base_url}/api/invalid-endpoint')
    assert status == 404
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is False
    assert 'not found' in body.get('error', '').lower()

    # 2. GET /api/providers/does-not-exist
    status, headers, body = _get(f'{base_url}/api/providers/does-not-exist')
    assert status == 404
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is False

    # 3. POST /api/invalid-endpoint
    status, headers, body = _post(f'{base_url}/api/invalid-endpoint', {'foo': 'bar'})
    assert status == 404
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is False
    assert 'not found' in body.get('error', '').lower()

    # 4. POST /api/models/non-existent-action
    status, headers, body = _post(f'{base_url}/api/models/non-existent-action', {})
    assert status == 404
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is False


def test_provider_endpoints_respond_with_json(test_server):
    base_url = test_server['base_url']

    # 1. GET /api/providers/catalog
    status, headers, body = _get(f'{base_url}/api/providers/catalog')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert 'providers' in body
    assert isinstance(body['providers'], list)

    # 2. GET /api/providers/connections
    status, headers, body = _get(f'{base_url}/api/providers/connections')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert 'connections' in body

    # 3. GET /api/providers/overview
    status, headers, body = _get(f'{base_url}/api/providers/overview')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert 'connections' in body

    # 4. GET /api/providers/details?provider=gemini
    status, headers, body = _get(f'{base_url}/api/providers/details?provider=gemini')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['provider'] == 'gemini'
    assert 'connections' in body
    assert 'models' in body

    # 5. POST /api/providers/all
    status, headers, body = _post(f'{base_url}/api/providers/all', {})
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True
    assert 'connections' in body

    # 6. POST /api/providers/mode/save
    status, headers, body = _post(f'{base_url}/api/providers/mode/save', {'provider': 'gemini', 'mode': 'round_robin'})
    assert status == 200
    assert body['success'] is True


def test_model_crud_and_toggle_and_test_endpoints(test_server):
    base_url = test_server['base_url']
    storage = test_server['storage']

    # 1. POST /api/providers/models/add
    status, headers, body = _post(
        f'{base_url}/api/providers/models/add',
        {'provider': 'gemini', 'model_id': 'gemini-2.5-flash-test', 'display_name': 'Gemini 2.5 Flash Test'},
    )
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True
    models = body['models']
    added = next((m for m in models if m['model_id'] == 'gemini-2.5-flash-test'), None)
    assert added is not None
    mid = added['id']

    # 2. POST /api/models/add (alias)
    status, headers, body = _post(
        f'{base_url}/api/models/add',
        {'provider': 'openai', 'model_id': 'gpt-4o-custom-test', 'display_name': 'GPT 4o Custom'},
    )
    assert status == 200
    assert body['success'] is True

    # 3. POST /api/providers/models/toggle (disable)
    status, headers, body = _post(f'{base_url}/api/providers/models/toggle', {'id': mid, 'is_active': False})
    assert status == 200
    assert body['success'] is True
    models_now = storage.get_provider_models('gemini')
    target = next((m for m in models_now if m['id'] == mid), None)
    assert target['is_active'] == 0

    # 4. POST /api/models/toggle (enable)
    status, headers, body = _post(f'{base_url}/api/models/toggle', {'id': mid, 'is_active': True})
    assert status == 200
    assert body['success'] is True
    models_now = storage.get_provider_models('gemini')
    target = next((m for m in models_now if m['id'] == mid), None)
    assert target['is_active'] == 1

    # 5. POST /api/models/save and /api/video-flow/settings/model
    status, headers, body = _post(f'{base_url}/api/video-flow/settings/model', {'model': 'gemini/gemini-2.5-flash-test'})
    assert status == 200
    assert body['success'] is True
    assert body['model'] == 'gemini/gemini-2.5-flash-test'

    status, headers, body = _post(f'{base_url}/api/models/save', {'model': 'openai/gpt-4o-custom-test'})
    assert status == 200
    assert body['success'] is True

    # 6. POST /api/providers/models/test for local/deterministic model
    status, headers, body = _post(
        f'{base_url}/api/providers/models/test',
        {'provider': 'local', 'model_id': 'deterministic', 'kind': 'llm'},
    )
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True

    # 7. POST /api/models/test (alias)
    status, headers, body = _post(
        f'{base_url}/api/models/test',
        {'provider': 'local', 'model_id': 'deterministic', 'kind': 'stt'},
    )
    assert status == 200
    assert body['success'] is True


def test_video_flow_endpoints_respond_with_json(test_server):
    base_url = test_server['base_url']

    # 1. GET /api/video-flow/catalog
    status, headers, body = _get(f'{base_url}/api/video-flow/catalog')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert 'providers' in body
    assert 'models' in body

    # 2. GET /api/video-flow/providers
    status, headers, body = _get(f'{base_url}/api/video-flow/providers')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')

    # 3. GET /api/video-flow/voice
    status, headers, body = _get(f'{base_url}/api/video-flow/voice')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True
    assert 'active_voice' in body

    # 4. POST /api/video-flow/voice
    status, headers, body = _post(f'{base_url}/api/video-flow/voice', {'voice': 'edge/en-US-GuyNeural'})
    assert status == 200
    assert body['success'] is True
    assert body['active_voice'] == 'edge/en-US-GuyNeural'

    # 5. GET /api/video-flow/history
    status, headers, body = _get(f'{base_url}/api/video-flow/history')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert 'videos' in body

    # 6. GET /api/video-flow/custom-providers/list
    status, headers, body = _get(f'{base_url}/api/video-flow/custom-providers/list')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True

    # 7. POST /api/video-flow/custom-providers/add and delete
    custom_entry = {
        'name': 'Local LMStudio',
        'base_url': 'http://127.0.0.1:1234/v1',
        'api_key': 'lm-studio',
        'models': [{'model_id': 'qwen2.5-7b', 'display_name': 'Qwen 2.5 7B'}],
    }
    status, headers, body = _post(f'{base_url}/api/video-flow/custom-providers/add', custom_entry)
    assert status == 200
    assert body['success'] is True

    status, headers, body = _post(f'{base_url}/api/video-flow/custom-providers/delete', {'id': 'custom-local-lmstudio'})
    assert status == 200
    assert body['success'] is True

    # 8. GET /api/video-flow/notebooklm/status
    status, headers, body = _get(f'{base_url}/api/video-flow/notebooklm/status')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True


def test_audio_summary_endpoints_respond_with_json(test_server):
    base_url = test_server['base_url']

    # 1. GET /api/audio-summary/settings/get
    status, headers, body = _get(f'{base_url}/api/audio-summary/settings/get')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True
    assert 'model' in body
    assert 'consent' in body

    # 2. GET /api/audio-summary/test with deterministic model query
    query = urllib.parse.urlencode({
        'text': 'Antigravity provides automated verification tests for Voice Flow.',
        'depth': 'quick',
        'model': 'local/deterministic',
    })
    status, headers, body = _get(f'{base_url}/api/audio-summary/test?{query}')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True
    assert body['depth'] == 'quick'
    assert len(body['summary']) > 0

    # 3. POST /api/audio-summary/test
    status, headers, body = _post(
        f'{base_url}/api/audio-summary/test',
        {
            'text': 'Voice Flow enables rapid speech dictation and audio intelligence on Windows.',
            'depth': 'standard',
            'model': 'local/deterministic',
        },
    )
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True
    assert len(body['summary']) > 0

    # 4. POST /api/audio-summary/settings/model
    status, headers, body = _post(
        f'{base_url}/api/audio-summary/settings/model',
        {'model': 'local/deterministic'},
    )
    assert status == 200
    assert body['success'] is True

    # 5. POST /api/audio-summary/settings/consent
    status, headers, body = _post(
        f'{base_url}/api/audio-summary/settings/consent',
        {'consent': True},
    )
    assert status == 200
    assert body['success'] is True
    assert body['consent'] is True


def test_provider_connection_crud_and_test(test_server):
    base_url = test_server['base_url']
    storage = test_server['storage']

    with patch.object(api_server.VoiceFlowApiHandler, 'verify_api_key') as mock_verify:
        mock_verify.return_value = {'success': True, 'message': 'Verified!'}

        # 1. Add connection
        status, headers, body = _post(
            f'{base_url}/api/providers/connections/add',
            {'provider': 'gemini', 'name': 'Key A', 'key': 'AIzaSyFakeTestKey1234567890', 'priority': 1},
        )
        assert status == 200
        assert 'application/json' in headers.get('Content-Type', '')
        assert body['success'] is True
        conn = body['connection']
        cid = conn['id']

        # 2. Test connection
        status, headers, body = _post(
            f'{base_url}/api/providers/connections/test',
            {'id': cid, 'provider': 'gemini', 'key': 'AIzaSyFakeTestKey1234567890'},
        )
        assert status == 200
        assert body['success'] is True

        # 3. Toggle connection
        status, headers, body = _post(
            f'{base_url}/api/providers/connections/toggle',
            {'id': cid, 'is_active': False},
        )
        assert status == 200
        assert body['success'] is True
        conns = storage.get_provider_connections('gemini')
        assert conns[0]['is_active'] == 0

        # 4. Update connection
        status, headers, body = _post(
            f'{base_url}/api/providers/connections/update',
            {'id': cid, 'name': 'Key A Renamed', 'key': 'AIzaSyFakeTestKey1234567890', 'priority': 2},
        )
        assert status == 200
        assert body['success'] is True
        conns = storage.get_provider_connections('gemini')
        assert conns[0]['name'] == 'Key A Renamed'

        # 5. Delete connection
        status, headers, body = _post(
            f'{base_url}/api/providers/connections/delete',
            {'id': cid},
        )
        assert status == 200
        assert body['success'] is True
        conns = storage.get_provider_connections('gemini')
        assert len(conns) == 0


def test_oauth_start_and_complete_endpoints(test_server):
    base_url = test_server['base_url']
    storage = test_server['storage']

    # 1. GET /api/providers/oauth/start?provider=antigravity
    status, headers, body = _get(f'{base_url}/api/providers/oauth/start?provider=antigravity')
    assert status == 200
    assert 'application/json' in headers.get('Content-Type', '')
    assert body['success'] is True
    assert 'auth_url' in body
    assert 'accounts.google.com' in body['auth_url']
    state = body['state']

    # 2. POST /api/providers/oauth/complete with mock token exchange
    with patch('voice_flow.video_flow_oauth._http_json') as mock_http, \
            patch('voice_flow.video_flow_oauth.load_code_assist_project', return_value=''):
        mock_http.return_value = {
            'access_token': 'ya29.live_user_access_token_safety',
            'refresh_token': '1//refresh_token_safety_xyz',
            'expires_in': 3600,
            'id_token': 'eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6InNhZmV0eS50ZXN0QGdtYWlsLmNvbSJ9.sig',
        }

        status, headers, body = _post(
            f'{base_url}/api/providers/oauth/complete',
            {'provider': 'antigravity', 'code': '4/safety_code_123', 'state': state},
        )
        assert status == 200
        assert 'application/json' in headers.get('Content-Type', '')
        assert body['success'] is True
        assert body['email'] == 'safety.test@gmail.com'

        conns = storage.get_provider_connections('antigravity')
        assert len(conns) == 1
        assert conns[0]['email'] == 'safety.test@gmail.com'


def test_gemini_model_test_routing_and_no_openai_leak(test_server):
    base_url = test_server['base_url']
    storage = test_server['storage']
    with patch.object(api_server.VoiceFlowApiHandler, 'verify_api_key', return_value={'success': True}):
        _post(
            f'{base_url}/api/providers/connections/add',
            {'provider': 'gemini', 'name': 'Test Gemini', 'key': 'AIzaSyFakeGeminiKeyForTest123', 'priority': 1},
        )

    real_urlopen = urllib.request.urlopen
    captured_urls = []
    def fake_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        if '127.0.0.1' in url or 'localhost' in url:
            return real_urlopen(req, *args, **kwargs)
        captured_urls.append(url)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "name": "models/gemini-3.5-transcribe",
            "supportedGenerationMethods": ["generateContent"]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch('urllib.request.urlopen', side_effect=fake_urlopen):
        status, headers, body = _post(
            f'{base_url}/api/providers/models/test',
            {'provider': 'gemini', 'model_id': 'gemini-3.5-transcribe', 'kind': 'stt'},
        )
        assert status == 200
        assert body['success'] is True
        assert len(captured_urls) > 0
        for u in captured_urls:
            assert 'api.openai.com' not in u
            assert 'generativelanguage.googleapis.com' in u

