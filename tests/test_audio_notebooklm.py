"""Tests for the isolated NotebookLM Audio Flow backend."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_flow.audio_notebooklm import (
    NotebookLMAudioSummaryError,
    NotebookLMAudioSummaryService,
    normalize_audio_depth,
)


class _Bridge:
    def __init__(
        self,
        *,
        terminal: str = "completed",
        task_id: str | None = "task-audio",
        source_status: str = "ready",
        write_download: bool = True,
        **_kwargs,
    ) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.terminal = terminal
        self.task_id = task_id
        self.source_status = source_status
        self.write_download = write_download
        self.poll_count = 0

    def check_auth(self, *, raise_on_error: bool):
        assert raise_on_error is True
        return SimpleNamespace(authenticated=True)

    def create_notebook(self, _title: str):
        return SimpleNamespace(notebook_id="nb-audio")

    def add_source(self, notebook_id: str, *, source_text: str, title: str):
        assert notebook_id == "nb-audio"
        assert source_text
        assert title
        return SimpleNamespace(source_id="src-audio", status=self.source_status)

    def _invoke(self, args, *, timeout: float):
        command = tuple(args)
        self.commands.append(command)
        if command[:2] == ("generate", "audio"):
            return {"task_id": self.task_id} if self.task_id else {}
        if command[:2] == ("artifact", "poll"):
            self.poll_count += 1
            if self.poll_count == 1:
                return {"status": "generating"}
            return {"status": self.terminal, "artifact_id": "artifact-audio", "message": "remote failed"}
        if command[:2] == ("download", "audio"):
            if self.write_download:
                Path(command[2]).write_bytes(b"m4a bytes")
            return {"status": "ok"}
        raise AssertionError(command)


def _factory(holder: dict[str, _Bridge], **kwargs):
    bridge = _Bridge(**kwargs)
    holder["bridge"] = bridge
    return bridge


@pytest.mark.parametrize(
    ("requested", "canonical", "audio_format", "audio_length"),
    [
        ("short", "short", "brief", "short"),
        ("brief", "short", "brief", "short"),
        ("quick", "short", "brief", "short"),
        ("balanced", "balanced", "deep-dive", "default"),
        ("standard", "balanced", "deep-dive", "default"),
        ("deep", "deep", "deep-dive", "long"),
        ("detailed", "deep", "deep-dive", "long"),
    ],
)
def test_generate_maps_depth_to_explicit_notebooklm_audio_options(
    tmp_path: Path, requested: str, canonical: str, audio_format: str, audio_length: str
) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=lambda **kwargs: _factory(holder, **kwargs),
        sleep=lambda _seconds: None,
    )

    result = service.generate("Evaporation turns water into vapour.", requested)

    assert result["depth"] == canonical
    assert Path(result["audio_path"]).is_absolute()
    assert Path(result["audio_path"]).read_bytes() == b"m4a bytes"
    generated = next(c for c in holder["bridge"].commands if c[:2] == ("generate", "audio"))
    assert ("--format", audio_format) == generated[generated.index("--format") : generated.index("--format") + 2]
    assert ("--length", audio_length) == generated[generated.index("--length") : generated.index("--length") + 2]
    assert any(c[:2] == ("artifact", "poll") for c in holder["bridge"].commands)
    downloaded = next(c for c in holder["bridge"].commands if c[:2] == ("download", "audio"))
    assert downloaded[2] == result["audio_path"]
    assert ("--artifact", "artifact-audio") == downloaded[downloaded.index("--artifact") : downloaded.index("--artifact") + 2]


def test_generate_emits_progress_and_checks_cancellation_between_polling(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    progress: list[dict] = []
    cancelled_calls = 0

    def cancelled() -> bool:
        nonlocal cancelled_calls
        cancelled_calls += 1
        return cancelled_calls >= 6

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: _factory(holder, **kwargs),
        sleep=lambda _seconds: None,
    )

    with pytest.raises(NotebookLMAudioSummaryError, match="cancelled") as error:
        service.generate("A small source.", cancelled=cancelled, on_progress=progress.append)

    assert error.value.code == "cancelled"
    assert any(event["state"] == "audio_start" for event in progress)
    assert not any(command[:2] == ("download", "audio") for command in holder["bridge"].commands)


def test_artifact_failure_is_typed_and_never_falls_back_to_local_audio(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}

    def failed_factory(**kwargs):
        bridge = _Bridge(terminal="failed", **kwargs)
        holder["bridge"] = bridge
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=failed_factory, sleep=lambda _seconds: None)

    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("A source that will fail.")

    assert error.value.code == "ARTIFACT_FAILED"
    assert not list(tmp_path.glob("*.m4a"))
    assert not any(command[:2] == ("download", "audio") for command in holder["bridge"].commands)


def test_depth_validation_is_safe() -> None:
    assert normalize_audio_depth("deep dive") == "deep"
    with pytest.raises(NotebookLMAudioSummaryError, match="Summary depth"):
        normalize_audio_depth("novel")


def test_source_must_be_ready_before_cloud_audio_is_submitted(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}

    def factory(**kwargs):
        bridge = _Bridge(source_status="processing", **kwargs)
        holder["bridge"] = bridge
        return bridge

    with pytest.raises(NotebookLMAudioSummaryError) as error:
        NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory).generate("Source text")

    assert error.value.code == "SOURCE_NOT_READY"
    assert not holder["bridge"].commands


def test_missing_task_id_and_download_file_are_typed_failures(tmp_path: Path) -> None:
    for name, factory in {
        "task": lambda **kwargs: _Bridge(task_id=None, **kwargs),
        "download": lambda **kwargs: _Bridge(write_download=False, **kwargs),
    }.items():
        service = NotebookLMAudioSummaryService(root_dir=tmp_path / name, provider_factory=factory, sleep=lambda _s: None)
        with pytest.raises(NotebookLMAudioSummaryError) as error:
            service.generate("Source text")
        assert error.value.code == ("INVALID_RESPONSE" if name == "task" else "DOWNLOAD_FAILED")


def test_poll_timeout_is_bounded(tmp_path: Path) -> None:
    timestamps = iter((0.0, 2.0, 2.0))
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: _Bridge(terminal="generating", **kwargs),
        poll_timeout_seconds=1,
        sleep=lambda _s: None,
        monotonic=lambda: next(timestamps),
    )

    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("Source text")

    assert error.value.code == "TIMEOUT"


def test_cancellation_after_download_does_not_return_audio(tmp_path: Path) -> None:
    downloaded = {"value": False}

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        invoke = bridge._invoke

        def wrapped(args, *, timeout):
            result = invoke(args, timeout=timeout)
            if tuple(args[:2]) == ("download", "audio"):
                downloaded["value"] = True
            return result

        bridge._invoke = wrapped
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory, sleep=lambda _s: None)
    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("Source text", cancelled=lambda: downloaded["value"])

    assert error.value.code == "cancelled"


def test_callback_failure_fails_closed_before_cloud_submission(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: _factory(holder, **kwargs),
    )

    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("Source text", on_progress=lambda _event: (_ for _ in ()).throw(RuntimeError("cancelled UI")))

    assert error.value.code == "CALLBACK_FAILED"
    assert not holder["bridge"].commands


def test_source_limit_and_secret_redaction_are_safe(tmp_path: Path) -> None:
    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=lambda **_kwargs: pytest.fail("bridge not needed"))
    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("x" * 100_001)
    assert error.value.code == "VALIDATION"

    exc = NotebookLMAudioSummaryError("CLI_ERROR", "Bearer secret-value token=abc123 cookie: SIDVALUE")
    assert "secret-value" not in exc.message
    assert "abc123" not in exc.message
    assert "SIDVALUE" not in exc.message


def test_generate_auto_heals_on_auth_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    healed = {"called": False}

    def fake_self_heal(*, profile=None, timeout=240):
        healed["called"] = True
        return {"ok": True, "error": None}

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", fake_self_heal)

    holder: dict[str, _Bridge] = {}
    auth_calls = 0

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        orig_check = bridge.check_auth

        def flaky_check_auth(*, raise_on_error: bool):
            nonlocal auth_calls
            auth_calls += 1
            if auth_calls == 1:
                raise NotebookLMVideoError("auth_expired", "Google account login expired.")
            return orig_check(raise_on_error=raise_on_error)

        bridge.check_auth = flaky_check_auth
        bridge.sync_storage_state = lambda force=False: None
        holder["bridge"] = bridge
        return bridge

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=factory,
        sleep=lambda _s: None,
    )

    result = service.generate("Source text to summarize.")
    assert healed["called"] is True
    assert auth_calls == 2
    assert Path(result["audio_path"]).is_file()


def test_generate_raises_auth_expired_when_auto_heal_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")

    def failing_self_heal(*, profile=None, timeout=240):
        return {"ok": False, "error": "refresh failed"}

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", failing_self_heal)

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        bridge.check_auth = lambda *, raise_on_error: (_ for _ in ()).throw(
            NotebookLMVideoError("auth_expired", "Google account login expired.")
        )
        return bridge

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=factory,
        sleep=lambda _s: None,
    )

    with pytest.raises(NotebookLMAudioSummaryError) as exc_info:
        service.generate("Source text")

    assert exc_info.value.code == "auth_expired"


def test_generate_auto_heals_when_auth_object_not_authenticated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    healed = {"called": False}

    def fake_self_heal(*, profile=None, timeout=240):
        healed["called"] = True
        return {"ok": True, "error": None}

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", fake_self_heal)

    auth_calls = 0

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)

        def check_auth_sequence(*, raise_on_error: bool):
            nonlocal auth_calls
            auth_calls += 1
            if auth_calls == 1:
                return SimpleNamespace(authenticated=False)
            return SimpleNamespace(authenticated=True)

        bridge.check_auth = check_auth_sequence
        bridge.sync_storage_state = lambda force=False: None
        return bridge

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=factory,
        sleep=lambda _s: None,
    )

    result = service.generate("Source text")
    assert healed["called"] is True
    assert auth_calls == 2
    assert Path(result["audio_path"]).is_file()


def test_generate_auto_heals_on_create_notebook_auth_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    healed = {"called": False}

    def fake_self_heal(*, profile=None, timeout=240):
        healed["called"] = True
        return {"ok": True, "error": None}

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", fake_self_heal)

    create_calls = 0

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        orig_create = bridge.create_notebook

        def flaky_create_notebook(title: str):
            nonlocal create_calls
            create_calls += 1
            if create_calls == 1:
                raise NotebookLMVideoError("auth_expired", "Google account login expired.")
            return orig_create(title)

        bridge.create_notebook = flaky_create_notebook
        bridge.sync_storage_state = lambda force=False: None
        return bridge

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=factory,
        sleep=lambda _s: None,
    )

    result = service.generate("Source text to test create auto-heal.")
    assert healed["called"] is True
    assert create_calls == 2
    assert Path(result["audio_path"]).is_file()


def test_generate_auto_heals_on_invoke_auth_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    healed = {"called": False}

    def fake_self_heal(*, profile=None, timeout=240):
        healed["called"] = True
        return {"ok": True, "error": None}

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", fake_self_heal)

    invoke_calls = 0

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        orig_invoke = bridge._invoke

        def flaky_invoke(args, **kw):
            nonlocal invoke_calls
            if args and args[0] == "generate" and args[1] == "audio":
                invoke_calls += 1
                if invoke_calls == 1:
                    raise NotebookLMVideoError("auth_expired", "Google account login expired.")
            return orig_invoke(args, **kw)

        bridge._invoke = flaky_invoke
        bridge.sync_storage_state = lambda force=False: None
        return bridge

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=factory,
        sleep=lambda _s: None,
    )

    result = service.generate("Source text to test invoke auto-heal.")
    assert healed["called"] is True
    assert invoke_calls == 2
    assert Path(result["audio_path"]).is_file()


def test_generate_proactively_refreshes_when_session_near_expiry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    healed = {"called": False}

    def fake_self_heal(*, profile=None, timeout=240):
        healed["called"] = True
        return {"ok": True, "error": None}

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", fake_self_heal)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.is_session_near_expiry", lambda *a, **k: True)

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=lambda **kw: _Bridge(**kw),
        sleep=lambda _s: None,
    )

    result = service.generate("Source text to test proactive refresh.")
    assert healed["called"] is True
    assert Path(result["audio_path"]).is_file()


def test_auto_sync_from_browser_success_requires_verified_check_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", lambda **k: {"ok": False})
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser", lambda **k: {"success": True})

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        bridge.check_auth = lambda *, raise_on_error: (_ for _ in ()).throw(
            NotebookLMVideoError("auth_expired", "Expired")
        )
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path / "audio_summaries", provider_factory=factory, sleep=lambda _s: None)

    with pytest.raises(NotebookLMAudioSummaryError) as exc_info:
        service.generate("Source text")

    assert exc_info.value.code == "auth_expired"
    assert exc_info.value.message == "Google account login expired. Please sign in to NotebookLM in Video Flow settings."


def test_auto_sync_from_browser_succeeds_when_verified_auth_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", lambda **k: {"ok": False})
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser", lambda **k: {"success": True})

    calls = 0

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        orig_check = bridge.check_auth

        def flaky_check(*, raise_on_error: bool):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise NotebookLMVideoError("auth_expired", "Session expired")
            return orig_check(raise_on_error=raise_on_error)

        bridge.check_auth = flaky_check
        bridge.sync_storage_state = lambda force=False: None
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path / "audio_summaries", provider_factory=factory, sleep=lambda _s: None)
    result = service.generate("Source text")
    assert Path(result["audio_path"]).is_file()
    assert calls >= 2


def test_unhandled_raw_auth_error_does_not_crash_audio_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", lambda **k: {"ok": False})
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser", lambda **k: {"success": False})

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        # Raw generic RuntimeError with auth indicator in message
        bridge.check_auth = lambda *, raise_on_error: (_ for _ in ()).throw(
            RuntimeError("accounts.google.com token expired; please re-authenticate")
        )
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path / "audio_summaries", provider_factory=factory, sleep=lambda _s: None)

    with pytest.raises(NotebookLMAudioSummaryError) as exc_info:
        service.generate("Source text")

    assert exc_info.value.code == "auth_expired"
    assert exc_info.value.message == "Google account login expired. Please sign in to NotebookLM in Video Flow settings."


