from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_flow.video_flow_engine.notebooklm.mcp_client import NotebookLMMcpClient
from voice_flow.video_flow_engine.notebooklm.models import NotebookLMVideoError
from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoProvider


TOKEN_ERROR = (
    "Token fetch failed: CSRF token not found in HTML. Final URL: "
    "https://notebook.google.com/ This may indicate the page structure has changed."
)
TOKEN_ERROR_WITH_SECRET = TOKEN_ERROR.replace(
    "https://notebook.google.com/", "https://notebook.google.com/entry?token=secret-value#frag"
)


class _Runner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.commands = []

    def __call__(self, command, timeout):
        self.commands.append(list(command))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _result(code: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def _token_failure_payload() -> str:
    # CLI versions have returned the useful message in details.error while
    # keeping a less useful wrapper in the top-level message.
    return json.dumps({
        "code": "CLI_ERROR",
        "message": "NotebookLM command failed",
        "details": {"error": TOKEN_ERROR},
    })


def _token_failure_payload_with_secret() -> str:
    return json.dumps({
        "code": "CLI_ERROR",
        "message": "NotebookLM command failed",
        "details": {"error": TOKEN_ERROR_WITH_SECRET},
    })


def _provider(tmp_path: Path, runner: _Runner) -> NotebookLMVideoProvider:
    cli = tmp_path / "notebooklm.exe"
    cli.write_bytes(b"stub")
    provider = NotebookLMVideoProvider(
        cli_path=cli,
        profile="recovery-test",
        workdir=tmp_path,
        runner=runner,
    )
    provider.sync_storage_state = lambda **_kwargs: {}  # type: ignore[method-assign]
    return provider


def _client(tmp_path: Path, runner: _Runner) -> NotebookLMMcpClient:
    cli = tmp_path / "notebooklm.exe"
    cli.write_bytes(b"stub")
    return NotebookLMMcpClient(profile="recovery-test", cli_path=cli, runner=runner)


def test_provider_recovers_token_extraction_failure_then_retries_job_once(monkeypatch, tmp_path):
    runner = _Runner([
        _result(1, stdout=_token_failure_payload()),
        _result(0, stdout=json.dumps({"task_id": "task-recovered"})),
    ])
    heals = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )
    provider = _provider(tmp_path, runner)

    assert provider._invoke(("video", "create"), timeout=3) == {"task_id": "task-recovered"}
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_provider_unresolved_token_error_is_retryable_and_never_claims_expired(monkeypatch, tmp_path):
    runner = _Runner([_result(1, stdout=_token_failure_payload_with_secret())])
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: {"ok": False, "classification": "transient_error"},
    )
    provider = _provider(tmp_path, runner)

    with pytest.raises(NotebookLMVideoError) as caught:
        provider._invoke(("video", "create"), timeout=3)
    assert caught.value.code == "auth_unavailable"
    assert caught.value.code != "auth_expired"
    assert caught.value.payload["retryable"] is True
    assert "secret-value" not in repr(caught.value.payload)
    assert "notebook.google.com" in caught.value.payload["details_message"]
    assert len(runner.commands) == 1


def test_provider_does_not_repeat_heal_when_token_error_persists_after_recovery(monkeypatch, tmp_path):
    runner = _Runner([
        _result(1, stdout=_token_failure_payload()),
        _result(1, stdout=_token_failure_payload()),
    ])
    heals = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )
    provider = _provider(tmp_path, runner)

    with pytest.raises(NotebookLMVideoError) as caught:
        provider._invoke(("video", "create"), timeout=3)
    assert caught.value.code == "auth_unavailable"
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_provider_shared_retry_guard_covers_auth_then_token_failure(monkeypatch, tmp_path):
    runner = _Runner([
        _result(1, stderr="Google account login expired."),
        _result(1, stdout=_token_failure_payload()),
    ])
    heals = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )
    provider = _provider(tmp_path, runner)

    with pytest.raises(NotebookLMVideoError) as caught:
        provider._invoke(("video", "create"), timeout=3)
    assert caught.value.code == "auth_unavailable"
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_provider_shared_retry_guard_covers_token_then_auth_failure(monkeypatch, tmp_path):
    runner = _Runner([
        _result(1, stdout=_token_failure_payload()),
        _result(1, stderr="Google account login expired."),
    ])
    heals = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )
    provider = _provider(tmp_path, runner)

    with pytest.raises(NotebookLMVideoError) as caught:
        provider._invoke(("video", "create"), timeout=3)
    assert caught.value.code == "auth_expired"
    assert len(heals) == 1
    assert len(runner.commands) == 2


@pytest.mark.parametrize("surface", ["provider", "mcp"])
@pytest.mark.parametrize("message", [
    "Network connection timed out while contacting NotebookLM.",
    "Quota exceeded. Try again later.",
    "Invalid JSON response from CLI.",
])
def test_unrelated_failure_does_not_start_browser_recovery(monkeypatch, tmp_path, surface, message):
    runner = _Runner([_result(1, stderr=message)])
    heal_calls = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heal_calls.append(kwargs) or {"ok": True},
    )

    with pytest.raises(NotebookLMVideoError):
        if surface == "provider":
            _provider(tmp_path, runner)._invoke(("video", "create"), timeout=3)
        else:
            _client(tmp_path, runner)._invoke_cli(("list",), timeout=3)
    assert heal_calls == []
    assert len(runner.commands) == 1


@pytest.mark.parametrize("surface", ["provider", "mcp"])
def test_cli_timeout_does_not_start_browser_recovery(monkeypatch, tmp_path, surface):
    runner = _Runner([subprocess.TimeoutExpired("notebooklm", 3)])
    heal_calls = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heal_calls.append(kwargs) or {"ok": True},
    )

    with pytest.raises(NotebookLMVideoError):
        if surface == "provider":
            _provider(tmp_path, runner)._invoke(("video", "create"), timeout=3)
        else:
            _client(tmp_path, runner)._invoke_cli(("list",), timeout=3)
    assert heal_calls == []
    assert len(runner.commands) == 1


def test_provider_cancellation_after_recovery_prevents_retry(monkeypatch, tmp_path):
    runner = _Runner([
        _result(1, stdout=_token_failure_payload()),
        _result(0, stdout=json.dumps({"task_id": "must-not-run"})),
    ])
    heal_calls = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heal_calls.append(kwargs) or {"ok": True},
    )

    class _CancelAfterFirstCheck:
        checks = 0

        def is_cancelled(self, _job_id):
            self.checks += 1
            return self.checks > 2

    provider = _provider(tmp_path, runner)
    provider._active_job_id = "cancel-after-recovery"
    provider.process_manager = _CancelAfterFirstCheck()

    with pytest.raises(NotebookLMVideoError) as caught:
        provider._invoke(("video", "create"), timeout=3)
    assert caught.value.code == "cancelled"
    assert len(heal_calls) == 1
    assert len(runner.commands) == 1


def test_mcp_client_recovers_token_extraction_failure_and_retries_once(monkeypatch, tmp_path):
    runner = _Runner([
        _result(1, stdout=_token_failure_payload()),
        _result(0, stdout=json.dumps({"notebooks": [{"id": "nb-ok"}]})),
    ])
    heals = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )
    client = _client(tmp_path, runner)

    assert client._invoke_cli(("list",), timeout=3) == {"notebooks": [{"id": "nb-ok"}]}
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_mcp_client_unresolved_token_error_is_retryable_not_expired(monkeypatch, tmp_path):
    runner = _Runner([_result(1, stdout=_token_failure_payload_with_secret())])
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: {"ok": False, "classification": "authenticated"},
    )
    client = _client(tmp_path, runner)

    with pytest.raises(NotebookLMVideoError) as caught:
        client._invoke_cli(("list",), timeout=3)
    assert caught.value.code == "auth_unavailable"
    assert caught.value.code != "auth_expired"
    assert caught.value.payload["retryable"] is True
    assert "secret-value" not in repr(caught.value.payload)
    assert len(runner.commands) == 1


def test_mcp_client_does_not_repeat_heal_when_token_error_persists(monkeypatch, tmp_path):
    runner = _Runner([
        _result(1, stdout=_token_failure_payload()),
        _result(1, stdout=_token_failure_payload()),
    ])
    heals = []
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )
    client = _client(tmp_path, runner)

    with pytest.raises(NotebookLMVideoError) as caught:
        client._invoke_cli(("list",), timeout=3)
    assert caught.value.code == "auth_unavailable"
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_provider_auth_check_retries_nested_token_failure_after_heal(monkeypatch, tmp_path):
    runner = _Runner([
        _result(0, stdout=json.dumps({
            "status": "error", "message": "Authentication check failed",
            "details": {"error": TOKEN_ERROR},
        })),
        _result(0, stdout=json.dumps({"status": "ok", "storage_path": "safe-test-state.json"})),
    ])
    heals = []
    provider = _provider(tmp_path, runner)
    monkeypatch.setattr(provider, "backup_storage_state", lambda: None)
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )

    status = provider.check_auth(online=True)

    assert status.authenticated is True
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_provider_auth_check_does_not_heal_twice_when_code_zero_error_persists(monkeypatch, tmp_path):
    failure = json.dumps({
        "status": "error", "message": "Authentication check failed",
        "details": {"error": TOKEN_ERROR},
    })
    runner = _Runner([_result(0, stdout=failure), _result(0, stdout=failure)])
    heals = []
    provider = _provider(tmp_path, runner)
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )

    with pytest.raises(NotebookLMVideoError) as caught:
        provider.check_auth(online=True)
    assert caught.value.code == "auth_unavailable"
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_provider_auth_check_shares_recovery_budget_across_cli_error_then_status_error(monkeypatch, tmp_path):
    status_failure = json.dumps({
        "status": "error", "message": "Authentication check failed",
        "details": {"error": TOKEN_ERROR},
    })
    runner = _Runner([
        _result(1, stdout=_token_failure_payload()),
        _result(0, stdout=status_failure),
    ])
    heals = []
    provider = _provider(tmp_path, runner)
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: heals.append(kwargs) or {"ok": True},
    )

    with pytest.raises(NotebookLMVideoError) as caught:
        provider.check_auth(online=True)
    assert caught.value.code == "auth_unavailable"
    assert caught.value.payload["retryable"] is True
    assert len(heals) == 1
    assert len(runner.commands) == 2


def test_provider_check_auth_unavailable_has_auth_status_when_not_raising(monkeypatch, tmp_path):
    runner = _Runner([_result(1, stdout=_token_failure_payload())])
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: {"ok": False, "classification": "transient_error"},
    )
    provider = _provider(tmp_path, runner)

    status = provider.check_auth(online=True, raise_on_error=False)

    assert status.status == "error"
    assert status.authenticated is False
    assert "temporarily unavailable" in status.message
    assert status.details["retryable"] is True
    assert len(runner.commands) == 1


def test_provider_code_zero_token_payload_drops_raw_url_query(monkeypatch, tmp_path):
    runner = _Runner([_result(0, stdout=json.dumps({
        "status": "error",
        "message": "Authentication check failed",
        "details": {"error": TOKEN_ERROR_WITH_SECRET},
    }))])
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: {"ok": False, "classification": "transient_error"},
    )
    provider = _provider(tmp_path, runner)

    with pytest.raises(NotebookLMVideoError) as caught:
        provider.check_auth(online=True)
    assert caught.value.code == "auth_unavailable"
    assert "secret-value" not in repr(caught.value.payload)
    assert "notebook.google.com/entry" in repr(caught.value.payload)


@pytest.mark.parametrize("raise_on_error", [True, False])
def test_provider_check_auth_preserves_transient_heal_result(monkeypatch, tmp_path, raise_on_error):
    runner = _Runner([_result(1, stderr="Google account login expired.")])
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: {"ok": False, "classification": "transient_error"},
    )
    provider = _provider(tmp_path, runner)

    if raise_on_error:
        with pytest.raises(NotebookLMVideoError) as caught:
            provider.check_auth(online=True, raise_on_error=True)
        assert caught.value.code == "auth_unavailable"
        assert caught.value.payload["retryable"] is True
    else:
        status = provider.check_auth(online=True, raise_on_error=False)
        assert status.status == "error"
        assert "temporarily unavailable" in status.message
        assert status.details["retryable"] is True
    assert len(runner.commands) == 1


def test_provider_auth_check_surfaces_nested_token_extraction_failure(monkeypatch, tmp_path):
    # A successful CLI transport can still return an auth-check failure payload.
    runner = _Runner([_result(0, stdout=json.dumps({
        "status": "error",
        "message": "Authentication check failed",
        "details": {"error": TOKEN_ERROR},
    }))])
    provider = _provider(tmp_path, runner)
    monkeypatch.setattr(provider, "backup_storage_state", lambda: None)
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **kwargs: {"ok": False, "classification": "transient_error"},
    )

    with pytest.raises(NotebookLMVideoError) as caught:
        provider.check_auth(online=True)
    assert caught.value.code == "auth_unavailable"
    assert caught.value.payload["retryable"] is True
