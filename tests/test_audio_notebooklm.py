"""Tests for the isolated NotebookLM Audio Flow backend."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_flow.audio_notebooklm import (
    NotebookLMAudioSummaryError,
    NotebookLMAudioSummaryService,
    m4a_duration_seconds,
    normalize_audio_depth,
    podcast_duration_budget,
    podcast_audio_length,
    podcast_audio_target_words,
)


def _m4a_with_duration(seconds: float, *, version: int = 0, timescale: int = 1_000) -> bytes:
    duration = round(seconds * timescale)
    if version == 0:
        payload = bytes([0, 0, 0, 0]) + (0).to_bytes(4, "big") * 2 + timescale.to_bytes(4, "big") + duration.to_bytes(4, "big")
    else:
        payload = bytes([1, 0, 0, 0]) + (0).to_bytes(8, "big") * 2 + timescale.to_bytes(4, "big") + duration.to_bytes(8, "big")
    mvhd = (8 + len(payload)).to_bytes(4, "big") + b"mvhd" + payload
    moov = (8 + len(mvhd)).to_bytes(4, "big") + b"moov" + mvhd
    return (16).to_bytes(4, "big") + b"ftypM4A " + b"isom" + moov


class _Bridge:
    def __init__(
        self,
        *,
        terminal: str = "completed",
        task_id: str | None = "task-audio",
        source_status: str = "ready",
        write_download: bool = True,
        download_durations: list[float] | None = None,
        **_kwargs,
    ) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.prompts: list[str] = []
        self.terminal = terminal
        self.task_id = task_id
        self.source_status = source_status
        self.write_download = write_download
        self.poll_count = 0
        self.fast_auth_requests: list[bool] = []
        self.download_durations = list(download_durations or [30.0])

    def check_auth(self, *, raise_on_error: bool, fast_valid_session: bool = False):
        assert raise_on_error is True
        self.fast_auth_requests.append(fast_valid_session)
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
            self.prompts.append(Path(command[command.index("--prompt-file") + 1]).read_text(encoding="utf-8"))
            return {"task_id": self.task_id} if self.task_id else {}
        if command[:2] == ("artifact", "poll"):
            self.poll_count += 1
            if self.poll_count == 1:
                return {"status": "generating"}
            return {"status": self.terminal, "artifact_id": "artifact-audio", "message": "remote failed"}
        if command[:2] == ("download", "audio"):
            if self.write_download:
                duration = self.download_durations.pop(0) if self.download_durations else 30.0
                Path(command[2]).write_bytes(_m4a_with_duration(duration))
            return {"status": "ok"}
        raise AssertionError(command)


def test_podcast_duration_plan_is_source_bounded_and_selects_coarse_native_lengths() -> None:
    assert podcast_audio_target_words("short", 1_000) == 180
    assert podcast_audio_target_words("balanced", 1_000) == 550
    assert podcast_audio_target_words("deep", 4_000) == 2_000
    assert podcast_audio_target_words("deep", 12) == 12
    assert podcast_audio_length("deep", 400) == "short"
    assert podcast_audio_length("balanced", 2_000) == "default"
    assert podcast_audio_length("deep", 4_000) == "long"


def test_generation_returns_monotonic_stage_timings_and_uses_fast_auth(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    clock = {"now": 0.0}

    def advance(seconds: float) -> None:
        clock["now"] += seconds

    class TimedBridge(_Bridge):
        def check_auth(self, **kwargs):
            advance(1.5)
            return super().check_auth(**kwargs)

        def create_notebook(self, *args, **kwargs):
            advance(2.0)
            return super().create_notebook(*args, **kwargs)

        def add_source(self, *args, **kwargs):
            advance(3.0)
            return super().add_source(*args, **kwargs)

        def _invoke(self, args, **kwargs):
            if tuple(args)[:2] == ("generate", "audio"):
                advance(4.0)
            elif tuple(args)[:2] == ("artifact", "poll"):
                advance(5.0)
            elif tuple(args)[:2] == ("download", "audio"):
                advance(6.0)
            return super()._invoke(args, **kwargs)

    def factory(**kwargs):
        bridge = TimedBridge(**kwargs)
        holder["bridge"] = bridge
        return bridge

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=factory,
        sleep=lambda _s: None,
        monotonic=lambda: clock["now"],
    )

    result = service.generate("A source with enough content to summarize.")

    timings = result["timings_seconds"]
    assert set(timings) == {
        "auth", "notebook_setup", "source_indexing", "generation_submit", "cloud_wait", "download", "total"
    }
    assert timings == {
        "auth": 1.5,
        "notebook_setup": 2.0,
        "source_indexing": 3.0,
        "generation_submit": 4.0,
        "cloud_wait": 10.0,
        "download": 6.0,
        "total": 26.5,
    }
    assert holder["bridge"].fast_auth_requests == [True]


@pytest.mark.parametrize(("style", "expected_format"), [("single", "brief"), ("podcast", "deep-dive")])
@pytest.mark.parametrize("depth", ["short", "balanced", "deep"])
def test_native_summary_styles_use_source_scoped_audio_and_distinct_depth_prompts(tmp_path: Path, style: str, expected_format: str, depth: str) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=lambda **kwargs: _factory(holder, **kwargs), sleep=lambda _s: None)
    result = service.generate("A source with claims, evidence, examples, and limitations. " * 30, depth, style=style)
    generated = next(command for command in holder["bridge"].commands if command[:2] == ("generate", "audio"))
    assert result["style"] == style
    assert generated[generated.index("--format") + 1] == expected_format
    assert generated[generated.index("--source") + 1] == "src-audio"
    assert not any(command[:1] == ("ask",) for command in holder["bridge"].commands)
    prompt = holder["bridge"].prompts[0]
    assert {"short": "practical takeaway", "balanced": "supporting details", "deep": "relationships"}[depth] in prompt
    if style == "single":
        assert "about" not in prompt
        if depth in {"balanced", "deep"}:
            assert "available native Brief time appropriate for this source and selected depth" in prompt
    else:
        assert "Across both hosts" in prompt
        assert "No greetings, chitchat" in prompt


@pytest.mark.parametrize(
    ("style", "depth", "source_words", "expected_length"),
    [
        ("single", "short", 12, "short"),
        ("single", "short", 200, "short"),
        ("single", "short", 650, "short"),
        ("single", "short", 1_000, "short"),
        ("single", "balanced", 12, "short"),
        ("single", "balanced", 200, "short"),
        ("single", "balanced", 650, "default"),
        ("single", "balanced", 1_000, "default"),
        ("single", "deep", 12, "short"),
        ("single", "deep", 200, "default"),
        ("single", "deep", 650, "long"),
        ("single", "deep", 1_000, "long"),
        ("podcast", "short", 12, "short"),
        ("podcast", "short", 1_000, "short"),
        ("podcast", "balanced", 12, "short"),
        ("podcast", "balanced", 650, "short"),
        ("podcast", "balanced", 2_000, "default"),
        ("podcast", "deep", 12, "short"),
        ("podcast", "deep", 200, "short"),
        ("podcast", "deep", 650, "short"),
        ("podcast", "deep", 1_000, "default"),
        ("podcast", "deep", 4_000, "long"),
    ],
)
def test_native_length_flags_cover_one_page_multi_page_and_tiny_sources(
    tmp_path: Path, style: str, depth: str, source_words: int, expected_length: str
) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=lambda **kwargs: _factory(holder, **kwargs), sleep=lambda _s: None)
    service.generate("source " * source_words, depth, style=style)
    generated = next(command for command in holder["bridge"].commands if command[:2] == ("generate", "audio"))
    assert generated[generated.index("--length") + 1] == expected_length
    prompt = holder["bridge"].prompts[0]
    if style == "single" and source_words <= 35:
        assert "brief and proportionate to this small source" in prompt
    elif style == "single":
        assert "proportionate to the selected source" in prompt or "appropriate for this source and selected depth" in prompt


def test_tiny_podcast_source_has_a_bounded_no_padding_instruction(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=lambda **kwargs: _factory(holder, **kwargs), sleep=lambda _s: None)
    service.generate("A tiny source.", "deep", style="podcast")
    prompt = holder["bridge"].prompts[0]
    assert "Across both hosts" in prompt
    assert "no more than 3 words" in prompt
    assert "never pad to fill time" in prompt


def _factory(holder: dict[str, _Bridge], **kwargs):
    bridge = _Bridge(**kwargs)
    holder["bridge"] = bridge
    return bridge


@pytest.mark.parametrize(
    ("requested", "canonical", "audio_format", "audio_length"),
    [
        ("short", "short", "deep-dive", "short"),
        ("brief", "short", "deep-dive", "short"),
        ("quick", "short", "deep-dive", "short"),
        ("balanced", "balanced", "deep-dive", "short"),
        ("standard", "balanced", "deep-dive", "short"),
        ("deep", "deep", "deep-dive", "short"),
        ("detailed", "deep", "deep-dive", "short"),
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

    result = service.generate("Evaporation turns water into vapour.", requested, style="podcast")

    assert result["depth"] == canonical
    assert Path(result["audio_path"]).is_absolute()
    assert m4a_duration_seconds(result["audio_path"]) == 30.0
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
        service.generate("A small source.", style="podcast", cancelled=cancelled, on_progress=progress.append)

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
        service.generate("A source that will fail.", style="podcast")

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
        NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory).generate("Source text", style="podcast")

    assert error.value.code == "SOURCE_NOT_READY"
    assert not holder["bridge"].commands


def test_missing_task_id_and_download_file_are_typed_failures(tmp_path: Path) -> None:
    for name, factory in {
        "task": lambda **kwargs: _Bridge(task_id=None, **kwargs),
        "download": lambda **kwargs: _Bridge(write_download=False, **kwargs),
    }.items():
        service = NotebookLMAudioSummaryService(root_dir=tmp_path / name, provider_factory=factory, sleep=lambda _s: None)
        with pytest.raises(NotebookLMAudioSummaryError) as error:
            service.generate("Source text", style="podcast")
        assert error.value.code == ("INVALID_RESPONSE" if name == "task" else "DOWNLOAD_FAILED")


def test_poll_timeout_is_bounded(tmp_path: Path) -> None:
    timestamps = iter((0.0, 2.0, 2.0))
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        poll_timeout_seconds=1,
        sleep=lambda _s: None,
        monotonic=lambda: next(timestamps),
    )
    bridge = _Bridge(terminal="generating")

    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service._poll(
            bridge,
            "notebook-id",
            "task-id",
            cancelled=None,
            on_progress=None,
        )

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
        service.generate("Source text", style="podcast", cancelled=lambda: downloaded["value"])

    assert error.value.code == "cancelled"


def test_callback_failure_fails_closed_before_cloud_submission(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: _factory(holder, **kwargs),
    )

    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("Source text", style="podcast", on_progress=lambda _event: (_ for _ in ()).throw(RuntimeError("cancelled UI")))

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

    result = service.generate("Source text to summarize.", style="podcast")
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
        service.generate("Source text", style="podcast")

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

    result = service.generate("Source text", style="podcast")
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

    result = service.generate("Source text to test create auto-heal.", style="podcast")
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

    result = service.generate("Source text to test invoke auto-heal.", style="podcast")
    assert healed["called"] is True
    assert invoke_calls == 2
    assert Path(result["audio_path"]).is_file()


def test_non_auth_cli_error_does_not_trigger_slow_session_heal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    monkeypatch.setattr(
        "voice_flow.video_flow_engine.notebooklm.login_flow.self_heal",
        lambda **_kwargs: pytest.fail("network errors must not trigger auth recovery"),
    )

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        bridge._invoke = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            NotebookLMVideoError("CLI_ERROR", "network unavailable")
        )
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory, sleep=lambda _s: None)
    with pytest.raises(NotebookLMAudioSummaryError) as exc_info:
        service.generate("Source text")

    assert exc_info.value.code == "CLI_ERROR"


def test_authenticated_generation_skips_near_expiry_preflight_heal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(**_kwargs):
        pytest.fail("authenticated summary generation must not block on proactive self-heal")

    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", fail_if_called)
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.config.is_session_near_expiry", lambda *a, **k: True)

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "audio_summaries",
        provider_factory=lambda **kw: _Bridge(**kw),
        sleep=lambda _s: None,
    )

    result = service.generate("Source text with a valid authenticated session.", style="podcast")
    assert Path(result["audio_path"]).is_file()


def test_auto_sync_from_browser_success_requires_verified_check_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoError

    monkeypatch.setenv("VOICE_FLOW_TEST_AUTO_HEAL", "1")
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.login_flow.self_heal", lambda **k: {"ok": False})
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser", lambda **k: {"success": False})
    monkeypatch.setattr("voice_flow.video_flow_engine.notebooklm.browser_sync.auto_sync_from_browser", lambda **k: {"success": True})

    def factory(**kwargs):
        bridge = _Bridge(**kwargs)
        bridge.check_auth = lambda *, raise_on_error: (_ for _ in ()).throw(
            NotebookLMVideoError("auth_expired", "Expired")
        )
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path / "audio_summaries", provider_factory=factory, sleep=lambda _s: None)

    with pytest.raises(NotebookLMAudioSummaryError) as exc_info:
        service.generate("Source text", style="podcast")

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
    result = service.generate("Source text", style="podcast")
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
        service.generate("Source text", style="podcast")

    assert exc_info.value.code == "auth_expired"
    assert exc_info.value.message == "Google account login expired. Please sign in to NotebookLM in Video Flow settings."


@pytest.mark.parametrize(("version", "seconds"), [(0, 50.25), (1, 123.75)])
def test_m4a_duration_reader_supports_mvhd_versions(tmp_path: Path, version: int, seconds: float) -> None:
    audio = tmp_path / f"version-{version}.m4a"
    audio.write_bytes(_m4a_with_duration(seconds, version=version))
    assert m4a_duration_seconds(audio) == seconds


def test_m4a_duration_reader_rejects_malformed_metadata(tmp_path: Path) -> None:
    audio = tmp_path / "broken.m4a"
    audio.write_bytes(b"\x00\x00\x00\x20moov\x00")
    with pytest.raises(NotebookLMAudioSummaryError) as error:
        m4a_duration_seconds(audio)
    assert error.value.code == "AUDIO_METADATA_INVALID"


def test_podcast_with_unreadable_metadata_fails_without_a_second_submit(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: _factory(holder, write_download=False, **kwargs),
        sleep=lambda _s: None,
    )

    # The bridge still produces a nonempty artifact, but it is not ISO-BMFF.
    bridge = service._bridge()
    original_invoke = bridge._invoke

    def invalid_download(args, *, timeout: float):
        if tuple(args)[:2] == ("download", "audio"):
            Path(args[2]).write_bytes(b"not an m4a")
            bridge.commands.append(tuple(args))
            return {"status": "ok"}
        return original_invoke(args, timeout=timeout)

    bridge._invoke = invalid_download
    service._bridge = lambda **_kwargs: bridge  # type: ignore[method-assign]
    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("source " * 84, "short", style="podcast")
    assert error.value.code == "AUDIO_METADATA_INVALID"
    assert len([command for command in bridge.commands if command[:2] == ("generate", "audio")]) == 1


def test_m4a_duration_reader_handles_extended_and_size_zero_boxes(tmp_path: Path) -> None:
    payload = bytes([0, 0, 0, 0]) + (0).to_bytes(4, "big") * 2 + (1_000).to_bytes(4, "big") + (50_000).to_bytes(4, "big")
    mvhd_to_end = (0).to_bytes(4, "big") + b"mvhd" + payload
    moov_size = 16 + len(mvhd_to_end)
    audio = tmp_path / "extended.m4a"
    audio.write_bytes(
        (16).to_bytes(4, "big") + b"ftypM4A " + b"isom"
        + (1).to_bytes(4, "big") + b"moov" + moov_size.to_bytes(8, "big") + mvhd_to_end
    )
    assert m4a_duration_seconds(audio) == 50.0


def test_overlong_podcast_reuses_notebook_and_source_once_then_returns_verified_duration(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}

    def factory(**kwargs):
        bridge = _Bridge(download_durations=[268.49, 50.0], **kwargs)
        holder["bridge"] = bridge
        return bridge

    progress: list[dict] = []
    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory, sleep=lambda _s: None)
    result = service.generate("source " * 84, "short", style="podcast", on_progress=progress.append)

    bridge = holder["bridge"]
    generated = [command for command in bridge.commands if command[:2] == ("generate", "audio")]
    assert len(generated) == 2
    assert len([command for command in bridge.commands if command[:2] == ("download", "audio")]) == 2
    assert generated[0][generated[0].index("--notebook") + 1] == generated[1][generated[1].index("--notebook") + 1] == "nb-audio"
    assert generated[0][generated[0].index("--source") + 1] == generated[1][generated[1].index("--source") + 1] == "src-audio"
    assert len(bridge.prompts) == 2
    assert "prior attempt ran for 268.5 seconds" in bridge.prompts[1]
    assert any(event["state"] == "audio_retry" for event in progress)
    assert result["duration_sec"] == 50.0
    assert result["duration_budget"]["maximum_seconds"] == 60


def test_twice_overlong_podcast_raises_typed_error_without_playable_result(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: _factory(holder, download_durations=[268.0, 268.0], **kwargs),
        sleep=lambda _s: None,
    )
    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("source " * 84, "short", style="podcast")
    assert error.value.code == "PODCAST_TOO_LONG"
    assert len([command for command in holder["bridge"].commands if command[:2] == ("generate", "audio")]) == 2


def test_cancellation_before_second_podcast_submit_stops_retry(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    cancelled = {"value": False}

    def progress(event: dict) -> None:
        if event["state"] == "audio_retry":
            cancelled["value"] = True

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: _factory(holder, download_durations=[268.0], **kwargs),
        sleep=lambda _s: None,
    )
    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("source " * 84, "short", style="podcast", cancelled=lambda: cancelled["value"], on_progress=progress)
    assert error.value.code == "cancelled"
    assert len([command for command in holder["bridge"].commands if command[:2] == ("generate", "audio")]) == 1


def test_exhausted_cloud_wait_prevents_second_podcast_submission(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    clock = {"now": 0.0}

    class SlowCompletedBridge(_Bridge):
        def _invoke(self, args, *, timeout: float):
            if tuple(args)[:2] == ("artifact", "poll"):
                self.commands.append(tuple(args))
                clock["now"] += 60.0
                return {"status": "completed", "artifact_id": "artifact-audio"}
            return super()._invoke(args, timeout=timeout)

    def factory(**kwargs):
        bridge = SlowCompletedBridge(download_durations=[268.0], **kwargs)
        holder["bridge"] = bridge
        return bridge

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path, provider_factory=factory, poll_timeout_seconds=60,
        sleep=lambda _s: None, monotonic=lambda: clock["now"],
    )
    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("source " * 84, "short", style="podcast")
    assert error.value.code == "TIMEOUT"
    assert len([command for command in holder["bridge"].commands if command[:2] == ("generate", "audio")]) == 1


def test_single_and_in_budget_podcast_do_not_retry(tmp_path: Path) -> None:
    holder: dict[str, _Bridge] = {}
    podcast = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "podcast",
        provider_factory=lambda **kwargs: _factory(holder, download_durations=[50.0], **kwargs), sleep=lambda _s: None,
    )
    podcast.generate("source " * 84, "short", style="podcast")
    assert len([command for command in holder["bridge"].commands if command[:2] == ("generate", "audio")]) == 1
    single_holder: dict[str, _Bridge] = {}
    single = NotebookLMAudioSummaryService(
        root_dir=tmp_path / "single",
        provider_factory=lambda **kwargs: _factory(single_holder, download_durations=[268.0], **kwargs), sleep=lambda _s: None,
    )
    single.generate("source " * 84, "short", style="single")
    assert len([command for command in single_holder["bridge"].commands if command[:2] == ("generate", "audio")]) == 1


def test_podcast_budget_grows_with_depth_and_source_size() -> None:
    small = podcast_duration_budget("short", 84)
    balanced = podcast_duration_budget("balanced", 1_000)
    deep = podcast_duration_budget("deep", 4_000)
    assert small["target_seconds"] < balanced["target_seconds"] < deep["target_seconds"]
    assert small["maximum_seconds"] < balanced["maximum_seconds"] < deep["maximum_seconds"]
