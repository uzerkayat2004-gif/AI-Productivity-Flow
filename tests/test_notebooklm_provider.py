import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from voice_flow.video_flow_engine.notebooklm import (
    NotebookLMVideoError,
    NotebookLMVideoProvider,
    VideoRequest,
)


class FakeRunner:
    def __init__(self, responses, *, output_bytes: bytes = b"fake-mp4-stream"):
        self.responses = list(responses)
        self.commands: list[list[str]] = []
        self.output_bytes = output_bytes

    def __call__(self, command, timeout):
        command = list(command)
        self.commands.append(command)
        joined = " ".join(command)
        if "download video" in joined:
            force_index = command.index("--force")
            Path(command[force_index + 1]).write_bytes(self.output_bytes)
        if not self.responses:
            raise AssertionError(f"Unexpected command: {command}")
        response = self.responses.pop(0)
        return SimpleNamespace(
            returncode=response.get("returncode", 0),
            stdout=json.dumps(response.get("payload", {})),
            stderr=response.get("stderr", ""),
        )


def provider_with(
    fake: FakeRunner,
    root: Path,
    process_manager=None,
    write_dummy_auth: bool = True,
    profile: str = "video-flow-experiment",
) -> NotebookLMVideoProvider:
    cli = root / "notebooklm.exe"
    cli.write_bytes(b"stub")
    if write_dummy_auth:
        storage_file = root / "storage_state.json"
        storage_file.write_text(
            json.dumps({
                "cookies": [
                    {"name": "SID", "value": "dummy-sid"},
                    {"name": "HSID", "value": "dummy-hsid"},
                    {"name": "SSID", "value": "dummy-ssid"},
                    {"name": "__Secure-1PSID", "value": "dummy-1psid"},
                    {"name": "__Secure-1PSIDTS", "value": "dummy-1psidts", "expires": 2500000000},
                    {"name": "OSID", "value": "dummy-osid"},
                ],
                "notebooklm": {"account": {"email": "test@example.com"}},
            }),
            encoding="utf-8",
        )
    return NotebookLMVideoProvider(
        cli_path=cli,
        profile=profile,
        workdir=root,
        runner=fake,
        poll_interval_seconds=0.01,
        sleep=lambda _seconds: None,
        process_manager=process_manager,
    )


class NotebookLMProviderTests(unittest.TestCase):
    def test_auth_offline_validation_default_without_spawning_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root)
            result = provider.check_auth()
            self.assertEqual(result.status, "ok")
            self.assertTrue(result.authenticated)
            self.assertEqual(fake.commands, [])  # Zero CLI subprocesses spawned

    def test_auth_online_uses_profile_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([{"payload": {"status": "ok", "storage_path": "redacted"}}])
            provider = provider_with(fake, root)
            result = provider.check_auth(online=True)
            self.assertEqual(result.status, "ok")
            self.assertTrue(result.authenticated)
            self.assertEqual(
                fake.commands[0],
                [str(root / "notebooklm.exe"), "--profile", "video-flow-experiment", "auth", "check", "--json"],
            )

    def test_auth_test_network_uses_test_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([{"payload": {"status": "ok", "storage_path": "redacted"}}])
            provider = provider_with(fake, root)
            result = provider.check_auth(test_network=True)
            self.assertEqual(result.status, "ok")
            self.assertTrue(result.authenticated)
            self.assertEqual(
                fake.commands[0],
                [str(root / "notebooklm.exe"), "--profile", "video-flow-experiment", "auth", "check", "--test", "--json"],
            )

    def test_auth_offline_fails_when_storage_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root, write_dummy_auth=False)
            provider.profile = "missing-profile-xyz"
            with self.assertRaises(NotebookLMVideoError) as caught:
                provider.check_auth()
            self.assertTrue(caught.exception.code in ("AUTH", "auth_expired"))
            unauth = provider.check_auth(raise_on_error=False)
            self.assertFalse(unauth.authenticated)

    def test_add_source_waits_using_separate_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "article.txt"
            source_file.write_text("source", encoding="utf-8")
            fake = FakeRunner(
                [
                    {"payload": {"source": {"id": "source-1", "title": "Article"}}},
                    {"payload": {"source_id": "source-1", "title": "Article", "status": "ready"}},
                ]
            )
            provider = provider_with(fake, root)
            source = provider.add_source("notebook-1", source_file=source_file, title="Article")
            self.assertEqual(source.source_id, "source-1")
            self.assertIn("source add", " ".join(fake.commands[0]))
            self.assertIn("source wait", " ".join(fake.commands[1]))
            self.assertNotIn("--wait", fake.commands[0])

    def test_url_before_completion_is_not_treated_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner(
                [
                    {"payload": {"status": "in_progress", "url": "temporary-url"}},
                    {"payload": {"status": "completed", "url": "final-url"}},
                ]
            )
            clock_values = iter((0.0, 0.1))
            provider = provider_with(fake, root)
            provider.monotonic = lambda: next(clock_values)
            status, url = provider.wait_for_artifact("notebook-1", "task-1", timeout_seconds=60)
            self.assertEqual(status, "completed")
            self.assertEqual(url, "final-url")
            self.assertEqual(len(fake.commands), 2)

    def test_missing_source_file_is_typed_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root)
            with self.assertRaises(NotebookLMVideoError) as caught:
                provider.add_source("notebook-1", source_file=root / "missing.txt")
            self.assertEqual(caught.exception.code, "SOURCE_NOT_FOUND")
            self.assertEqual(fake.commands, [])

    def test_generate_downloads_mp4_and_writes_non_sensitive_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "article.txt"
            source_file.write_text("source", encoding="utf-8")
            output = root / "out" / "video.mp4"
            fake = FakeRunner(
                [
                    {"payload": {"notebook": {"id": "notebook-1", "title": "Test"}}},
                    {"payload": {"source": {"id": "source-1", "title": "Article"}}},
                    {"payload": {"source_id": "source-1", "title": "Article", "status": "ready"}},
                    {"payload": {"task_id": "task-1", "status": "pending"}},
                    {"payload": {"status": "completed", "url": "signed-url"}},
                    {"payload": {"path": str(output)}},
                ]
            )
            provider = provider_with(fake, root)
            artifact = provider.generate(
                VideoRequest(
                    title="Test",
                    prompt="Explain the article visually",
                    source_file=source_file,
                    output_path=output,
                    job_id="job-1",
                )
            )
            self.assertEqual(artifact.status, "completed")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)
            provenance = json.loads(Path(artifact.provenance_path).read_text(encoding="utf-8"))
            serialized = json.dumps(provenance)
            self.assertIn("task-1", serialized)
            self.assertIn("job-1", serialized)
            self.assertNotIn("cookie", serialized.lower())
            self.assertNotIn("bearer", serialized.lower())

    def test_cli_failure_is_preserved_with_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "payload": {"error": True, "code": "AUTH", "message": "login required"},
                    }
                ]
            )
            provider = provider_with(fake, root)
            with self.assertRaises(NotebookLMVideoError) as caught:
                provider.check_auth(online=True)
            self.assertEqual(caught.exception.code, "AUTH")

    def test_url_source_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner(
                [
                    {"payload": {"source": {"id": "src-url", "title": "URL Source"}}},
                    {"payload": {"source_id": "src-url", "title": "URL Source", "status": "ready"}},
                ]
            )
            provider = provider_with(fake, root)
            source = provider.add_source("notebook-1", source_url="https://example.com/article", title="URL Source")
            self.assertEqual(source.source_id, "src-url")
            self.assertIn("--type url", " ".join(fake.commands[0]))

    def test_text_source_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner(
                [
                    {"payload": {"source": {"id": "src-txt", "title": "Pasted Text"}}},
                    {"payload": {"source_id": "src-txt", "title": "Pasted Text", "status": "ready"}},
                ]
            )
            provider = provider_with(fake, root)
            source = provider.add_source("notebook-1", source_text="Exact selected text", title="Pasted Text")
            self.assertEqual(source.source_id, "src-txt")
            self.assertIn("--type file", " ".join(fake.commands[0]))

    def test_format_and_style_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root)
            with self.assertRaises(NotebookLMVideoError) as caught:
                req = VideoRequest(title="T", prompt="P", output_path=root / "out.mp4", source_text="Text", format="invalid_format")
                provider.start_video(req, "nb-1", "src-1")
            self.assertEqual(caught.exception.code, "VALIDATION")

    def test_custom_style_requires_style_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root)
            with self.assertRaises(NotebookLMVideoError) as caught:
                req = VideoRequest(title="T", prompt="P", output_path=root / "out.mp4", source_text="Text", style="custom", style_prompt="")
                provider.start_video(req, "nb-1", "src-1")
            self.assertEqual(caught.exception.code, "VALIDATION")

    def test_cinematic_format_omits_style(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([{"payload": {"task_id": "task-cinematic"}}])
            provider = provider_with(fake, root)
            req = VideoRequest(title="T", prompt="P", output_path=root / "out.mp4", source_text="Text", format="cinematic", style="retro-print")
            task_id, _ = provider.start_video(req, "nb-1", "src-1")
            self.assertEqual(task_id, "task-cinematic")
            cmd = " ".join(fake.commands[0])
            self.assertIn("--format cinematic", cmd)
            self.assertNotIn("--style", cmd)

    def test_language_forwarding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([{"payload": {"task_id": "task-lang"}}])
            provider = provider_with(fake, root)
            req = VideoRequest(title="T", prompt="P", output_path=root / "out.mp4", source_text="Text", language="es")
            provider.start_video(req, "nb-1", "src-1")
            cmd = " ".join(fake.commands[0])
            self.assertIn("--language es", cmd)

    def test_profile_resolution_fallback_to_canonical(self):
        from voice_flow.video_flow_engine.notebooklm.config import (
            DEFAULT_PROFILE,
            resolve_notebooklm_profile,
        )
        # 1. None profile falls back to canonical DEFAULT_PROFILE
        self.assertEqual(DEFAULT_PROFILE, "video-flow-experiment")
        resolved = resolve_notebooklm_profile(None)
        self.assertEqual(resolved, "video-flow-experiment")

    def test_profile_resolution_fallback_when_storage_missing(self):
        import os
        from voice_flow.video_flow_engine.notebooklm.config import resolve_notebooklm_profile
        with tempfile.TemporaryDirectory() as directory:
            profiles_dir = Path(directory)
            # Create valid storage_state.json in video-flow-experiment
            exp_dir = profiles_dir / "video-flow-experiment"
            exp_dir.mkdir(parents=True, exist_ok=True)
            (exp_dir / "storage_state.json").write_text(
                json.dumps({"cookies": [{"name": "SID", "value": "v"}]}),
                encoding="utf-8",
            )
            # empty profile directory without storage_state.json
            (profiles_dir / "custom-empty").mkdir(parents=True, exist_ok=True)

            old_env = os.environ.get("NOTEBOOKLM_PROFILES_DIR")
            try:
                os.environ["NOTEBOOKLM_PROFILES_DIR"] = str(profiles_dir)
                # Requesting "custom-empty" should seamlessly fallback to "video-flow-experiment"
                res = resolve_notebooklm_profile("custom-empty")
                self.assertEqual(res, "video-flow-experiment")
            finally:
                if old_env is not None:
                    os.environ["NOTEBOOKLM_PROFILES_DIR"] = old_env
                else:
                    os.environ.pop("NOTEBOOKLM_PROFILES_DIR", None)

    def test_cookie_inspection_missing_required_cookies(self):
        from voice_flow.video_flow_engine.notebooklm.provider import _inspect_cookies
        # Missing the core long-lived session cookies
        cookies = [{"name": "OTHER", "value": "val"}]
        valid, msg, details = _inspect_cookies(cookies)
        self.assertFalse(valid)
        self.assertIn("Missing required authentication cookies", msg)
        self.assertIn("__Secure-1PSID", details["missing_cookies"])
        self.assertIn("SID", details["missing_cookies"])

    def test_cookie_inspection_psidts_expired(self):
        from voice_flow.video_flow_engine.notebooklm.provider import _inspect_cookies
        # All required present, but __Secure-1PSIDTS is in the past
        cookies = [
            {"name": "SID", "value": "val"},
            {"name": "HSID", "value": "val"},
            {"name": "SSID", "value": "val"},
            {"name": "__Secure-1PSID", "value": "val"},
            {"name": "__Secure-1PSIDTS", "value": "val", "expires": 1000},
            {"name": "OSID", "value": "val"},
        ]
        valid, msg, details = _inspect_cookies(cookies, current_time=2000)
        # __Secure-1PSIDTS is a short-lived rotation cookie: its expiry must
        # NOT invalidate a session whose core cookies are still valid.
        self.assertTrue(valid)

    def test_auto_backup_and_recovery_from_corrupt_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            # Initialize provider with valid storage state
            provider = provider_with(fake, root, write_dummy_auth=True)
            storage_path = provider.get_storage_path()
            backup_path = provider.get_backup_path()

            # Verify backup was created automatically
            self.assertTrue(backup_path.is_file())
            self.assertGreater(backup_path.stat().st_size, 0)

            # Corrupt storage_state.json (e.g. laptop sleep / abrupt termination writes 0 bytes)
            storage_path.write_text("", encoding="utf-8")
            self.assertEqual(storage_path.stat().st_size, 0)

            # check_auth should automatically restore from backup and succeed
            auth = provider.check_auth()
            self.assertTrue(auth.authenticated)
            self.assertEqual(auth.status, "ok")
            self.assertGreater(storage_path.stat().st_size, 0)

    def test_inspect_session_method(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root, write_dummy_auth=True)
            info = provider.inspect_session()
            self.assertTrue(info["valid"])
            self.assertEqual(info["profile"], "video-flow-experiment")
            self.assertTrue(info["backup_exists"])
            self.assertIn("SID", info["cookies_found"])
            self.assertIn("OSID", info["cookies_found"])

    def test_wait_for_artifact_uses_cli_wait_primary_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([{"payload": {"status": "completed", "url": "https://signed-url.mp4"}}])
            provider = provider_with(fake, root)
            status, url = provider.wait_for_artifact("nb-abc", "task-xyz", timeout_seconds=120)
            self.assertEqual(status, "completed")
            self.assertEqual(url, "https://signed-url.mp4")
            self.assertEqual(len(fake.commands), 1)
            cmd = " ".join(fake.commands[0])
            self.assertIn("artifact wait task-xyz --notebook nb-abc --interval 3", cmd)
            self.assertIn("--json", cmd)

    def test_wait_for_artifact_fallback_to_adaptive_polling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # 1st command (artifact wait) fails with non-terminal error/status
            # 2nd command (artifact poll) succeeds with completed
            fake = FakeRunner(
                [
                    {"returncode": 1, "payload": {"error": "unsupported wait command"}},
                    {"payload": {"status": "completed", "url": "https://fallback-url.mp4"}},
                ]
            )
            provider = provider_with(fake, root)
            status, url = provider.wait_for_artifact("nb-abc", "task-xyz", timeout_seconds=60)
            self.assertEqual(status, "completed")
            self.assertEqual(url, "https://fallback-url.mp4")
            self.assertEqual(len(fake.commands), 2)
            cmd0 = " ".join(fake.commands[0])
            cmd1 = " ".join(fake.commands[1])
            self.assertIn("artifact wait task-xyz", cmd0)
            self.assertIn("artifact poll task-xyz", cmd1)

    def test_source_wait_uses_optimal_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([{"payload": {"source_id": "src-100", "title": "Article", "status": "ready"}}])
            provider = provider_with(fake, root)
            source_ref = provider.wait_for_source("nb-100", "src-100")
            self.assertEqual(source_ref.source_id, "src-100")
            self.assertEqual(source_ref.status, "ready")
            cmd = " ".join(fake.commands[0])
            self.assertIn("source wait src-100 --notebook nb-100 --timeout 120 --json", cmd)

    def test_generate_skips_create_notebook_when_notebook_id_provided(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "article.txt"
            source_file.write_text("content", encoding="utf-8")
            output = root / "video.mp4"
            fake = FakeRunner(
                [
                    {"payload": {"source": {"id": "src-reuse", "title": "Article"}}},
                    {"payload": {"source_id": "src-reuse", "title": "Article", "status": "ready"}},
                    {"payload": {"task_id": "task-reuse", "status": "pending"}},
                    {"payload": {"status": "completed", "url": "url"}},
                    {"payload": {"path": str(output)}},
                ]
            )
            provider = provider_with(fake, root)
            artifact = provider.generate(
                VideoRequest(
                    title="Reuse Test",
                    prompt="Test prompt",
                    source_file=source_file,
                    output_path=output,
                    notebook_id="existing-nb-999",
                )
            )
            self.assertEqual(artifact.notebook_id, "existing-nb-999")
            commands_joined = [" ".join(c) for c in fake.commands]
            self.assertFalse(any(" create " in f" {c} " for c in commands_joined))
            self.assertEqual(len(fake.commands), 5)

    def test_generate_skips_create_notebook_when_workspace_reuse_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "article.txt"
            source_file.write_text("content", encoding="utf-8")
            output = root / "video.mp4"

            # Pre-cache notebook_id in workspace .notebook_id
            (root / ".notebook_id").write_text("cached-nb-777", encoding="utf-8")

            fake = FakeRunner(
                [
                    {"payload": {"source": {"id": "src-cached", "title": "Article"}}},
                    {"payload": {"source_id": "src-cached", "title": "Article", "status": "ready"}},
                    {"payload": {"task_id": "task-cached", "status": "pending"}},
                    {"payload": {"status": "completed", "url": "url"}},
                    {"payload": {"path": str(output)}},
                ]
            )
            provider = provider_with(fake, root)
            provider.reuse_workspace = True
            artifact = provider.generate(
                VideoRequest(
                    title="Cached Workspace Test",
                    prompt="Test prompt",
                    source_file=source_file,
                    output_path=output,
                    reuse_workspace=True,
                )
            )
            self.assertEqual(artifact.notebook_id, "cached-nb-777")
            commands_joined = [" ".join(c) for c in fake.commands]
            self.assertFalse(any(" create " in f" {c} " for c in commands_joined))
            self.assertEqual(len(fake.commands), 5)

    def test_workspace_notebook_cache_methods(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root)
            self.assertIsNone(provider.get_cached_notebook_id())

            provider.save_cached_notebook_id("saved-nb-123")
            self.assertEqual(provider.get_cached_notebook_id(), "saved-nb-123")
            self.assertEqual((root / ".notebook_id").read_text(encoding="utf-8"), "saved-nb-123")

            provider.clear_cached_notebook_id()
            self.assertIsNone(provider.get_cached_notebook_id())
            self.assertFalse((root / ".notebook_id").exists())

    def test_run_command_process_flags(self):
        import subprocess
        from unittest.mock import patch
        from voice_flow.video_flow_engine.notebooklm.provider import _run_command

        with patch("subprocess.run") as mock_run:
            _run_command(["cmd", "arg"], timeout=10.0)
            self.assertTrue(mock_run.called)
            _, kwargs = mock_run.call_args
            self.assertTrue(kwargs.get("close_fds"))
            self.assertTrue(kwargs.get("text"))
            self.assertTrue(kwargs.get("capture_output"))
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                self.assertEqual(kwargs.get("creationflags"), subprocess.CREATE_NO_WINDOW)

    def test_auth_expired_error_code_and_friendly_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "stderr": (
                            "UNEXPECTED_ERROR: Unexpected error: Authentication expired or invalid. "
                            "Final URL: https://accounts.google.com/v3/signin\n"
                            "Run 'notebooklm login' to re-authenticate."
                        ),
                        "payload": {},
                    }
                ]
            )
            provider = provider_with(fake, root)
            with self.assertRaises(NotebookLMVideoError) as caught:
                provider.create_notebook("Test Title")
            self.assertEqual(caught.exception.code, "auth_expired")
            self.assertIn(
                "Google account login expired. Please sign in to NotebookLM in Video Flow settings.",
                str(caught.exception),
            )

    def test_auth_expired_psidts_offline_validation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            # Write expired PSIDTS cookie
            storage_file = root / "storage_state.json"
            storage_file.write_text(
                json.dumps({
                    "cookies": [
                        {"name": "SID", "value": "dummy-sid", "expires": 1000},
                        {"name": "__Secure-1PSID", "value": "dummy-1psid", "expires": 1000},
                    ],
                }),
                encoding="utf-8",
            )
            provider = NotebookLMVideoProvider(
                cli_path=root / "notebooklm.exe",
                profile="video-flow-experiment",
                workdir=root,
                runner=fake,
            )
            with self.assertRaises(NotebookLMVideoError) as caught:
                provider.check_auth()
            self.assertIn("AUTH", caught.exception.code.upper())
            self.assertIn(
                "Google account login expired. Please sign in to NotebookLM in Video Flow settings.",
                str(caught.exception),
            )

    def test_auth_expired_automatic_zero_failure_fallback_to_local(self):
        # Contract: auth_expired must NOT auto-fallback — it raises with a
        # clear message even when local fallback is enabled.
        from unittest.mock import MagicMock, patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "source.txt"
            source_file.write_text("Detailed test document for video creation.", encoding="utf-8")
            output_file = root / "out" / "video.mp4"

            # Fake runner returns auth expired error on create notebook
            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "stderr": "Authentication expired or invalid. Run 'notebooklm login' to re-authenticate.",
                        "payload": {},
                    }
                ]
            )
            provider = provider_with(fake, root)
            provider.allow_local_fallback = True

            mock_engine = MagicMock()
            mock_engine.run.return_value = {
                "state": "complete",
                "video_path": str(output_file),
            }

            with patch("voice_flow.video_flow_engine.engine.VideoFlowEngine", return_value=mock_engine):
                with self.assertRaises(NotebookLMVideoError) as caught:
                    provider.generate(
                        VideoRequest(
                            title="Fallback Test",
                            prompt="Explain visually",
                            source_file=source_file,
                            output_path=output_file,
                            allow_local_fallback=True,
                        )
                    )

            self.assertEqual(caught.exception.code, "auth_expired")
            mock_engine.run.assert_not_called()

    def test_has_valid_storage_state_active_cookies_validation(self):
        import time
        from voice_flow.video_flow_engine.notebooklm.config import (
            has_valid_storage_state,
        )
        with tempfile.TemporaryDirectory() as directory:
            profiles_dir = Path(directory)
            prof_dir = profiles_dir / "test-active"
            prof_dir.mkdir(parents=True, exist_ok=True)
            storage_file = prof_dir / "storage_state.json"

            # 1. Valid active cookies
            storage_file.write_text(
                json.dumps({
                    "cookies": [
                        {"name": "SID", "value": "valid_token"},
                        {"name": "__Secure-1PSIDTS", "value": "ts", "expires": time.time() + 3600},
                    ]
                }),
                encoding="utf-8",
            )
            import os
            old_env = os.environ.get("NOTEBOOKLM_PROFILES_DIR")
            try:
                os.environ["NOTEBOOKLM_PROFILES_DIR"] = str(profiles_dir)
                self.assertTrue(has_valid_storage_state("test-active"))

                # 2. Expired core session cookie
                storage_file.write_text(
                    json.dumps({
                        "cookies": [
                            {"name": "SID", "value": "valid_token", "expires": time.time() - 100},
                            {"name": "__Secure-1PSID", "value": "ts", "expires": time.time() - 100},
                        ]
                    }),
                    encoding="utf-8",
                )
                self.assertFalse(has_valid_storage_state("test-active"))

                # 3. Empty cookies list
                storage_file.write_text(json.dumps({"cookies": []}), encoding="utf-8")
                self.assertFalse(has_valid_storage_state("test-active"))
            finally:
                if old_env is not None:
                    os.environ["NOTEBOOKLM_PROFILES_DIR"] = old_env
                else:
                    os.environ.pop("NOTEBOOKLM_PROFILES_DIR", None)

    def test_auth_status_error_code_and_dict(self):
        from voice_flow.video_flow_engine.notebooklm.models import AuthStatus
        status_ok = AuthStatus(status="ok", profile="video-flow-experiment", authenticated=True)
        self.assertIsNone(status_ok.error_code)

        status_exp = AuthStatus(
            status="unauthenticated",
            profile="video-flow-experiment",
            authenticated=False,
            message="Google account login expired. Please sign in to NotebookLM in Video Flow settings.",
            details={"psidts_expired": True},
        )
        self.assertEqual(status_exp.error_code, "auth_expired")
        self.assertEqual(status_exp.to_dict()["error_code"], "auth_expired")

    def test_allow_local_fallback_on_general_cli_failure(self):
        from unittest.mock import MagicMock, patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "source.txt"
            source_file.write_text("Test document content", encoding="utf-8")
            output_file = root / "out" / "video.mp4"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"rendered-mp4")

            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "stderr": "Unknown CLI error occurred",
                        "payload": {},
                    }
                ]
            )
            provider = provider_with(fake, root)
            provider.allow_local_fallback = True

            mock_engine = MagicMock()
            mock_engine.run.return_value = {
                "state": "complete",
                "video_path": str(output_file),
            }

            with patch("voice_flow.video_flow_engine.engine.VideoFlowEngine", return_value=mock_engine):
                artifact = provider.generate(
                    VideoRequest(
                        title="General Failure Fallback Test",
                        prompt="Explain visually",
                        source_file=source_file,
                        output_path=output_file,
                        allow_local_fallback=True,
                    )
                )

            self.assertEqual(artifact.status, "completed")
            self.assertEqual(artifact.output_path, str(output_file))
            mock_engine.run.assert_called_once()

    def test_is_local_fallback_enabled_defaults_to_true_unless_explicitly_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner([])
            provider = provider_with(fake, root)

            # 1. Default with no arguments must be True
            self.assertTrue(provider.is_local_fallback_enabled())

            # 2. Default with normal VideoRequest must be True
            req_default = VideoRequest(
                title="Default Fallback",
                prompt="Explain visually",
                output_path=root / "out.mp4",
            )
            self.assertTrue(req_default.allow_local_fallback)
            self.assertTrue(provider.is_local_fallback_enabled(req_default))

            # 3. Explicitly disabled in request must be False
            req_disabled = VideoRequest(
                title="Disabled Fallback",
                prompt="Explain visually",
                output_path=root / "out.mp4",
                allow_local_fallback=False,
            )
            self.assertFalse(req_disabled.allow_local_fallback)
            self.assertFalse(provider.is_local_fallback_enabled(req_disabled))

            # 4. Explicitly disabled on provider must be False
            provider.allow_local_fallback = False
            self.assertFalse(provider.is_local_fallback_enabled())
            self.assertFalse(provider.is_local_fallback_enabled(req_default))

    def test_auth_expired_automatic_zero_failure_fallback_by_default(self):
        # Contract: auth_expired must NOT auto-fallback by default either —
        # it raises auth_expired even with allow_local_fallback=True.
        from unittest.mock import MagicMock, patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "source.txt"
            source_file.write_text("Detailed test document for zero-failure fallback.", encoding="utf-8")
            output_file = root / "out" / "video.mp4"

            # Fake runner returns auth expired error (__Secure-1PSIDTS expired or invalid)
            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "stderr": "Authentication expired (__Secure-1PSIDTS). Run 'notebooklm login' to re-authenticate.",
                        "payload": {},
                    }
                ]
            )
            # Provider is created with defaults (allow_local_fallback defaults to True)
            provider = provider_with(fake, root)
            self.assertTrue(provider.allow_local_fallback)

            mock_engine = MagicMock()
            mock_engine.run.return_value = {
                "state": "complete",
                "video_path": str(output_file),
            }

            # VideoRequest is created with defaults (allow_local_fallback defaults to True)
            req = VideoRequest(
                title="Zero Failure Test",
                prompt="Explain visually",
                source_file=source_file,
                output_path=output_file,
            )
            self.assertTrue(req.allow_local_fallback)

            with patch("voice_flow.video_flow_engine.engine.VideoFlowEngine", return_value=mock_engine):
                with self.assertRaises(NotebookLMVideoError) as caught:
                    provider.generate(req)

            self.assertEqual(caught.exception.code, "auth_expired")
            mock_engine.run.assert_not_called()

    def test_auth_failure_raises_when_fallback_explicitly_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "source.txt"
            source_file.write_text("Detailed test document.", encoding="utf-8")
            output_file = root / "out" / "video.mp4"

            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "stderr": "Authentication expired. Run 'notebooklm login'.",
                        "payload": {},
                    }
                ]
            )
            provider = provider_with(fake, root)

            req_disabled = VideoRequest(
                title="Disabled Fallback Test",
                prompt="Explain visually",
                source_file=source_file,
                output_path=output_file,
                allow_local_fallback=False,
            )

            with self.assertRaises(NotebookLMVideoError) as caught:
                provider.generate(req_disabled)

            self.assertEqual(caught.exception.code, "auth_expired")


    def test_timeout_error_falls_back_to_local_with_fallback_flag(self):
        # (a) A TIMEOUT error may fall back, and the fallback artifact carries fallback=True.
        from unittest.mock import MagicMock, patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = root / "source.txt"
            source_file.write_text("Detailed test document for timeout fallback.", encoding="utf-8")
            output_file = root / "out" / "video.mp4"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(b"local-rendered-mp4-data")

            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "payload": {"error": True, "code": "TIMEOUT", "message": "NotebookLM CLI command timed out"},
                    }
                ]
            )
            provider = provider_with(fake, root)

            mock_engine = MagicMock()
            mock_engine.run.return_value = {
                "state": "complete",
                "video_path": str(output_file),
            }

            with patch("voice_flow.video_flow_engine.engine.VideoFlowEngine", return_value=mock_engine):
                artifact = provider.generate(
                    VideoRequest(
                        title="Timeout Fallback Test",
                        prompt="Explain visually",
                        source_file=source_file,
                        output_path=output_file,
                        allow_local_fallback=True,
                    )
                )

            self.assertEqual(artifact.status, "completed")
            self.assertTrue(getattr(artifact, "fallback", False) is True)
            mock_engine.run.assert_called_once()

    def test_auth_expired_error_does_not_fallback(self):
        # (b) auth_expired never falls back — it raises even with fallback enabled.
        from unittest.mock import MagicMock, patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = FakeRunner(
                [
                    {
                        "returncode": 1,
                        "stderr": "Authentication expired or invalid. Run 'notebooklm login' to re-authenticate.",
                        "payload": {},
                    }
                ]
            )
            provider = provider_with(fake, root)
            mock_engine = MagicMock()
            with patch("voice_flow.video_flow_engine.engine.VideoFlowEngine", return_value=mock_engine):
                with self.assertRaises(NotebookLMVideoError) as caught:
                    provider.generate(
                        VideoRequest(
                            title="Auth No Fallback",
                            prompt="Explain visually",
                            source_text="Some source text for auth failure.",
                            output_path=root / "out.mp4",
                            allow_local_fallback=True,
                        )
                    )
            self.assertEqual(caught.exception.code, "auth_expired")
            mock_engine.run.assert_not_called()

    def test_prompt_rebuild_is_idempotent(self):
        # (c) Directive assembly run twice keeps each marker exactly once.
        from voice_flow.video_flow_engine.notebooklm.provider import _assemble_prompt
        sections = [
            {"title": "Alpha", "key_point": "First point"},
            {"title": "Beta", "key_point": "Second point"},
        ]
        doc_profile = {"density_score": 1.0, "substantive_concepts": []}
        once = _assemble_prompt(
            "Explain the report",
            directive="Cover everything briskly.",
            format_name="cinematic",
            style="retro-print",
            sections=sections,
            doc_profile=doc_profile,
        )
        twice = _assemble_prompt(
            once,
            directive="Cover everything briskly.",
            format_name="cinematic",
            style="retro-print",
            sections=sections,
            doc_profile=doc_profile,
        )
        self.assertEqual(once, twice)
        for marker in ("[Adaptive Video Directives]", "[Visual Style]", "[Content Depth & Key Points]"):
            self.assertEqual(twice.count(marker), 1, f"marker {marker} must appear exactly once")

    def test_duration_undershoot_flags_below_half_target(self):
        # (d) Pure undershoot logic: actual < 50% of target flags True.
        from voice_flow.video_flow_engine.notebooklm.provider import _duration_undershoot
        self.assertTrue(_duration_undershoot(120.0, 30.0))
        self.assertTrue(_duration_undershoot(100, 49.0))
        self.assertFalse(_duration_undershoot(100, 50.0))
        self.assertFalse(_duration_undershoot(100, 90.0))
        self.assertFalse(_duration_undershoot(None, 30.0))
        self.assertFalse(_duration_undershoot(0, 10.0))

    def test_verify_duration_emits_and_marks_profile(self):
        # Duration verification is additive: warning + emit + dict keys.
        from voice_flow.video_flow_engine.notebooklm.provider import NotebookLMVideoProvider
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = provider_with(FakeRunner([]), root)
            events: list[dict] = []
            provider.progress = lambda event: events.append(dict(event))
            profile = {"target_duration_seconds": 120.0}
            flagged = provider._verify_duration(profile, 30.0, job_id="job-under")
            self.assertTrue(flagged)
            self.assertTrue(profile.get("duration_undershoot") is True)
            self.assertEqual(profile.get("duration_actual_seconds"), 30.0)
            self.assertTrue(any(e.get("state") == "duration_undershoot" for e in events))

            profile_ok = {"target_duration_seconds": 120.0}
            self.assertFalse(provider._verify_duration(profile_ok, 90.0, job_id="job-ok"))
            self.assertNotIn("duration_undershoot", profile_ok)


if __name__ == "__main__":
    unittest.main()
