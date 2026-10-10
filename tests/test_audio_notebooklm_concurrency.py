from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice_flow.audio_notebooklm import NotebookLMAudioSummaryError, NotebookLMAudioSummaryService
from tests.test_audio_notebooklm import _Bridge


def test_generation_admits_two_jobs_then_queues_and_isolates_outputs(tmp_path: Path) -> None:
    entered = threading.Condition()
    release = threading.Event()
    queued = threading.Event()
    factories: list[dict] = []
    results: dict[str, dict] = {}
    failures: list[BaseException] = []

    class HeldBridge(_Bridge):
        def check_auth(self, **kwargs):
            with entered:
                entered.notify_all()
            assert release.wait(3.0)
            return super().check_auth(**kwargs)

    def factory(**kwargs):
        bridge = HeldBridge(**kwargs)
        with entered:
            factories.append({"bridge": bridge, "workdir": kwargs["workdir"]})
            entered.notify_all()
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory, sleep=lambda _s: None)

    def run(name: str, *, on_progress=None):
        try:
            results[name] = service.generate(f"Independent source {name}.", on_progress=on_progress)
        except BaseException as exc:
            failures.append(exc)

    def on_queued(event):
        if event["state"] == "queued":
            queued.set()

    workers = [threading.Thread(target=run, args=(str(i),)) for i in range(2)]
    for worker in workers:
        worker.start()
    with entered:
        assert entered.wait_for(lambda: len(factories) == 2, timeout=2.0)

    third = threading.Thread(target=run, args=("third",), kwargs={"on_progress": on_queued})
    third.start()
    assert queued.wait(2.0)
    assert len(factories) == 2, "queued work must not construct another NotebookLM bridge"

    release.set()
    for worker in [*workers, third]:
        worker.join(timeout=4.0)
        assert not worker.is_alive()
    assert not failures
    assert len(factories) == 3
    assert len({str(item["workdir"]) for item in factories}) == 3
    assert len({result["audio_path"] for result in results.values()}) == 3
    assert all(Path(result["audio_path"]).is_file() for result in results.values())


def test_cancelling_a_queued_request_does_not_cancel_active_requests(tmp_path: Path) -> None:
    entered = threading.Condition()
    release = threading.Event()
    queued = threading.Event()
    cancelled = threading.Event()
    factory_count = 0
    errors: dict[str, str] = {}

    class HeldBridge(_Bridge):
        def check_auth(self, **kwargs):
            with entered:
                entered.notify_all()
            assert release.wait(3.0)
            return super().check_auth(**kwargs)

    def factory(**kwargs):
        nonlocal factory_count
        with entered:
            factory_count += 1
            entered.notify_all()
        return HeldBridge(**kwargs)

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory, sleep=lambda _s: None)

    def run(name: str, token=None, *, on_progress=None):
        try:
            service.generate(name, cancelled=token, on_progress=on_progress)
        except NotebookLMAudioSummaryError as exc:
            errors[name] = exc.code

    active = [threading.Thread(target=run, args=(f"active-{i}",)) for i in range(2)]
    for worker in active:
        worker.start()
    with entered:
        assert entered.wait_for(lambda: factory_count == 2, timeout=2.0)

    def observe(event):
        if event["state"] == "queued":
            queued.set()

    waiting = threading.Thread(target=run, args=("waiting", cancelled), kwargs={"on_progress": observe})
    waiting.start()
    assert queued.wait(2.0)
    cancelled.set()
    waiting.join(timeout=1.0)
    assert not waiting.is_alive()
    assert errors["waiting"] == "cancelled"
    assert factory_count == 2
    assert all(worker.is_alive() for worker in active)

    release.set()
    for worker in active:
        worker.join(timeout=4.0)
        assert not worker.is_alive()
    assert not errors.keys() - {"waiting"}


def test_callback_failure_releases_generation_capacity(tmp_path: Path) -> None:
    constructions = 0

    def factory(**kwargs):
        nonlocal constructions
        constructions += 1
        return _Bridge(**kwargs)

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory, sleep=lambda _s: None)

    def fail_progress(event):
        if event["state"] == "notebook_create":
            raise RuntimeError("offline callback failure")

    with pytest.raises(NotebookLMAudioSummaryError) as error:
        service.generate("first request", on_progress=fail_progress)
    assert error.value.code == "CALLBACK_FAILED"

    result = service.generate("second request")
    assert Path(result["audio_path"]).is_file()
    assert constructions == 2


@pytest.mark.parametrize("blocked_stage", ["submit", "download"])
def test_cancel_terminates_only_its_provider_and_removes_partial_audio(tmp_path: Path, blocked_stage: str) -> None:
    entered = threading.Condition()
    operation_blocked = threading.Event()
    cancel_token = threading.Event()
    survivor_done = threading.Event()
    bridges: list[dict] = []
    outcomes: dict[str, object] = {}

    class BlockingBridge:
        def __init__(self, **kwargs):
            self.workdir = Path(kwargs["workdir"])
            self.source_text = ""
            self.cancelled = threading.Event()
            self.cancel_calls = 0
            self.output_path: Path | None = None

        def check_auth(self, **_kwargs):
            return SimpleNamespace(authenticated=True)

        def create_notebook(self, title):
            return SimpleNamespace(notebook_id=title)

        def add_source(self, notebook_id, *, source_text, title):
            self.source_text = source_text
            return SimpleNamespace(source_id=title, status="ready")

        def _invoke(self, args, *, timeout):
            command = tuple(args)
            if command[:2] == ("generate", "audio"):
                if self.source_text == "cancel source" and blocked_stage == "submit":
                    operation_blocked.set()
                    assert self.cancelled.wait(2.0)
                return {"task_id": f"task-{self.source_text}"}
            if command[:2] == ("artifact", "poll"):
                return {"status": "completed", "artifact_id": f"artifact-{self.source_text}"}
            if command[:2] == ("download", "audio"):
                self.output_path = Path(command[2])
                if self.source_text == "cancel source" and blocked_stage == "download":
                    operation_blocked.set()
                    assert self.cancelled.wait(2.0)
                    # Simulate a downloader that leaves a partial file as it
                    # exits after the owned provider process is terminated.
                    self.output_path.write_bytes(b"partial download")
                else:
                    self.output_path.write_bytes(b"complete survivor audio")
                return {"status": "ok"}
            raise AssertionError(command)

        def cancel(self):
            self.cancel_calls += 1
            self.cancelled.set()

    def factory(**kwargs):
        bridge = BlockingBridge(**kwargs)
        with entered:
            bridges.append({"bridge": bridge, "workdir": bridge.workdir})
            entered.notify_all()
        return bridge

    service = NotebookLMAudioSummaryService(root_dir=tmp_path, provider_factory=factory)
    sentinel = tmp_path / "unrelated.m4a"
    sentinel.write_bytes(b"preserve this")

    def run(name: str, token=None):
        try:
            outcomes[name] = service.generate(name, cancelled=token)
        except NotebookLMAudioSummaryError as exc:
            outcomes[name] = exc.code
        finally:
            if name == "survivor source":
                survivor_done.set()

    canceled_worker = threading.Thread(target=run, args=("cancel source", cancel_token))
    survivor_worker = threading.Thread(target=run, args=("survivor source",))
    canceled_worker.start()
    survivor_worker.start()
    with entered:
        assert entered.wait_for(lambda: len(bridges) == 2, timeout=2.0)
    assert operation_blocked.wait(2.0)
    assert survivor_done.wait(2.0)
    survivor_result = outcomes["survivor source"]
    assert isinstance(survivor_result, dict)
    survivor_path = Path(survivor_result["audio_path"])
    assert survivor_path.is_file()

    cancel_token.set()
    canceled_worker.join(timeout=2.0)
    survivor_worker.join(timeout=2.0)
    assert not canceled_worker.is_alive()
    assert not survivor_worker.is_alive()

    canceled_bridge = next(item["bridge"] for item in bridges if item["bridge"].source_text == "cancel source")
    survivor_bridge = next(item["bridge"] for item in bridges if item["bridge"].source_text == "survivor source")
    assert outcomes["cancel source"] == "cancelled"
    assert canceled_bridge.cancel_calls >= 1
    assert survivor_bridge.cancel_calls == 0
    if canceled_bridge.output_path is not None:
        assert not canceled_bridge.output_path.exists()
    assert survivor_path.is_file()
    assert sentinel.read_bytes() == b"preserve this"
    assert not list(tmp_path.glob("*-prompt.txt"))
    assert all(not item["workdir"].exists() for item in bridges)
    guard_prefixes = {f"NotebookLMAudioCancel-{item['workdir'].name[:12]}" for item in bridges}
    assert not any(thread.name in guard_prefixes for thread in threading.enumerate())


def test_failed_download_removes_only_its_partial_output(tmp_path: Path) -> None:
    class FailingDownloadBridge(_Bridge):
        def _invoke(self, args, *, timeout):
            command = tuple(args)
            if command[:2] == ("download", "audio"):
                Path(command[2]).write_bytes(b"partial failed download")
                raise OSError("offline fake download failure")
            return super()._invoke(command, timeout=timeout)

    service = NotebookLMAudioSummaryService(
        root_dir=tmp_path,
        provider_factory=lambda **kwargs: FailingDownloadBridge(**kwargs),
        sleep=lambda _seconds: None,
    )
    unrelated = tmp_path / "keep.m4a"
    unrelated.write_bytes(b"other job output")

    with pytest.raises(NotebookLMAudioSummaryError):
        service.generate("failed download source")

    assert sorted(path.name for path in tmp_path.glob("*.m4a")) == ["keep.m4a"]
    assert unrelated.read_bytes() == b"other job output"
    assert not list(tmp_path.glob("*-prompt.txt"))
    assert not list((tmp_path / ".audio-flow-jobs").iterdir())
