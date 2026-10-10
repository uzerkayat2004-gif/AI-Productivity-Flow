import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from voice_flow.video_flow_engine.engine import VideoFlowEngine
from voice_flow.video_flow_engine.notebooklm import NotebookLMVideoProvider, VideoRequest
from voice_flow.video_flow_service import VideoFlowService, VideoFlowStore


class FakeRunner:
    def __init__(self, responses, *, output_bytes: bytes = b"mock-mp4-data"):
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


class VideoFlowNotebookLMIntegrationTests(unittest.TestCase):
    def test_engine_run_with_notebooklm_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cli = root / "notebooklm.exe"
            cli.write_bytes(b"stub")
            job_dir = root / "vf-test-nlm"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "storage_state.json").write_text(
                json.dumps({
                    "cookies": [{"name": k, "value": f"dummy-{k}"} for k in ["SID", "HSID", "SSID", "__Secure-1PSID", "__Secure-1PSIDTS", "OSID"]],
                    "notebooklm": {"account": {"email": "test@example.com"}},
                }),
                encoding="utf-8",
            )
            fake = FakeRunner(
                [
                    {"payload": {"notebook": {"id": "nb-99", "title": "AI Overview"}}},
                    {"payload": {"source": {"id": "src-99", "title": "Article"}}},
                    {"payload": {"source_id": "src-99", "title": "Article", "status": "ready"}},
                    {"payload": {"task_id": "task-99", "status": "pending"}},
                    {"payload": {"status": "completed", "url": "https://signed.url"}},
                    {"payload": {"status": "ok"}},
                ]
            )

            progress_events = []
            def progress_cb(event):
                progress_events.append(dict(event))

            engine = VideoFlowEngine()
            # Patch NotebookLMVideoProvider to use our fake runner
            import voice_flow.video_flow_engine.notebooklm.provider as prov_mod
            original_runner = prov_mod._run_command
            prov_mod._run_command = fake
            try:
                result = engine.run(
                    video_id="vf-test-nlm",
                    provider="notebooklm",
                    source_text="This is a deep dive into neural transformers.",
                    title="AI Overview",
                    format="explainer",
                    style="classic",
                    cli_path=cli,
                    projects_root=root,
                    project_dir=root / "vf-test-nlm",
                    progress_callback=progress_cb,
                )
                self.assertEqual(result["state"], "ready")
                self.assertEqual(result["provider"], "notebooklm")
                self.assertTrue(Path(result["video_path"]).is_file())
                self.assertEqual(result["artifact"]["notebook_id"], "nb-99")
                self.assertEqual(result["artifact"]["task_id"], "task-99")
                self.assertTrue(any(e.get("state") == "video_poll" for e in progress_events))

                # Verify timings in engine result and artifact
                self.assertIn("timings", result)
                self.assertIn("timings", result["artifact"])
                expected_keys = [
                    "auth", "t_auth",
                    "notebook_setup", "t_notebook",
                    "source_ingest", "t_source",
                    "cloud_synthesis", "t_cloud",
                    "download", "t_download",
                    "probe", "t_probe",
                    "total", "t_total",
                ]
                for key in expected_keys:
                    self.assertIn(key, result["timings"])
                    self.assertIsInstance(result["timings"][key], (int, float))
                    self.assertIn(key, result["artifact"]["timings"])

                # Verify progress events emit phase and elapsed telemetry
                phases_emitted = {e.get("phase") for e in progress_events if e.get("phase")}
                self.assertTrue({"auth", "notebook_setup", "source_ingest", "cloud_synthesis", "download", "probe", "total"}.issubset(phases_emitted))
                self.assertTrue(any("elapsed" in e for e in progress_events))

                # Verify provenance.json and production-provenance.json contain timings
                prov_file = root / "vf-test-nlm" / "provenance" / "provenance.json"
                prod_prov_file = root / "vf-test-nlm" / "provenance" / "production-provenance.json"
                self.assertTrue(prov_file.is_file())
                self.assertTrue(prod_prov_file.is_file())
                prov_data = json.loads(prov_file.read_text(encoding="utf-8"))
                self.assertIn("timings", prov_data)
                for key in expected_keys:
                    self.assertIn(key, prov_data["timings"])
            finally:
                prov_mod._run_command = original_runner

    def test_models_timings_field(self):
        from voice_flow.video_flow_engine.notebooklm.models import VideoArtifact, VideoRequest

        req = VideoRequest(
            title="Timing test",
            prompt="Explain things",
            output_path=Path("out.mp4"),
            timings={"auth": 0.12, "t_auth": 0.12, "total": 1.5, "t_total": 1.5},
        )
        self.assertEqual(req.timings["auth"], 0.12)

        req_default = VideoRequest(
            title="Timing test default",
            prompt="Explain things",
            output_path=Path("out.mp4"),
        )
        self.assertEqual(req_default.timings, {})

        artifact = VideoArtifact(
            notebook_id="nb-1",
            task_id="t-1",
            artifact_id="a-1",
            status="completed",
            timings={"t_cloud": 12.34, "cloud_synthesis": 12.34, "total": 15.0},
        )
        self.assertEqual(artifact.timings["t_cloud"], 12.34)
        d = artifact.to_dict()
        self.assertIn("timings", d)
        self.assertEqual(d["timings"]["t_cloud"], 12.34)

    def test_provenance_json_records_timings(self):
        from voice_flow.video_flow_engine.notebooklm.models import VideoArtifact, VideoRequest
        from voice_flow.video_flow_engine.notebooklm.provenance import write_notebooklm_provenance

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir)
            req = VideoRequest(
                title="Prov test",
                prompt="Prompt",
                output_path=proj / "video.mp4",
                job_id="vf-prov-test",
            )
            artifact = VideoArtifact(
                notebook_id="nb-1",
                task_id="task-1",
                artifact_id="task-1",
                status="completed",
                timings={"t_auth": 0.05, "t_cloud": 4.5, "t_total": 5.0, "total": 5.0},
            )
            prov_path = write_notebooklm_provenance(
                project_dir=proj,
                request=req,
                artifact=artifact,
                started_at="2026-08-28T00:00:00Z",
                timings=artifact.timings,
            )
            self.assertTrue(prov_path.is_file())
            prov_json = proj / "provenance" / "provenance.json"
            self.assertTrue(prov_json.is_file())
            data = json.loads(prov_json.read_text(encoding="utf-8"))
            self.assertIn("timings", data)
            self.assertEqual(data["timings"]["t_cloud"], 4.5)
            self.assertEqual(data["timings"]["total"], 5.0)

    def test_service_saves_job_meta_timings_and_accessible(self):
        root_dir = tempfile.mkdtemp()
        try:
            root = Path(root_dir)
            store = VideoFlowStore(root / "jobs.db")
            service = VideoFlowService(store=store, projects_root=root / "projects")

            video_file = root / "projects" / "vf-telemetry" / "video.mp4"
            video_file.parent.mkdir(parents=True, exist_ok=True)
            video_file.write_bytes(b"dummy mp4")

            from voice_flow.video_flow_contracts import JobV3
            job = JobV3(job_id="vf-telemetry", message="Queued", meta={"output_path": str(video_file)})
            store.create(job)

            timings_payload = {
                "auth": 0.05,
                "t_auth": 0.05,
                "notebook_setup": 0.3,
                "t_notebook": 0.3,
                "source_ingest": 1.2,
                "t_source": 1.2,
                "cloud_synthesis": 25.4,
                "t_cloud": 25.4,
                "download": 1.1,
                "t_download": 1.1,
                "probe": 0.08,
                "t_probe": 0.08,
                "total": 28.13,
                "t_total": 28.13,
            }

            service._complete(
                "vf-telemetry",
                {
                    "state": "complete",
                    "video_path": str(video_file),
                    "timings": timings_payload,
                },
            )

            finished_job = service.get("vf-telemetry")
            self.assertIsNotNone(finished_job)
            self.assertEqual(finished_job.state, "complete")
            self.assertIn("timings", finished_job.meta)
            self.assertEqual(finished_job.meta["timings"]["t_cloud"], 25.4)
            self.assertEqual(finished_job.meta["timings"]["total"], 28.13)

            # Also check list()
            all_jobs = service.list()
            matched = next((j for j in all_jobs if j.job_id == "vf-telemetry"), None)
            self.assertIsNotNone(matched)
            self.assertIn("timings", matched.meta)
            self.assertEqual(matched.meta["timings"]["t_auth"], 0.05)
        finally:
            import shutil
            shutil.rmtree(root_dir, ignore_errors=True)

    def test_service_queue_with_notebooklm_engine(self):
        root_dir = tempfile.mkdtemp()
        try:
            root = Path(root_dir)
            store = VideoFlowStore(root / "jobs.db")
            service = VideoFlowService(store=store, projects_root=root / "projects")
            job = service.queue(
                source_text="Quantum computing fundamentals.",
                title="Quantum Intro",
                provider="notebooklm",
                format="cinematic",
            )
            self.assertEqual(job.meta.get("video_engine"), "notebooklm")
            self.assertEqual(job.meta.get("format"), "cinematic")
            persisted = store.get(job.job_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.meta.get("video_engine"), "notebooklm")
            self.assertEqual(persisted.meta.get("format"), "cinematic")
        finally:
            if "service" in locals() and "job" in locals() and job:
                try:
                    service.cancel(job.job_id)
                except Exception:
                    pass
            import shutil
            shutil.rmtree(root_dir, ignore_errors=True)

    def test_service_queue_defaults_to_notebooklm_when_omitted_or_default(self):
        root_dir = tempfile.mkdtemp()
        try:
            root = Path(root_dir)
            store = VideoFlowStore(root / "jobs.db")
            service = VideoFlowService(store=store, projects_root=root / "projects")

            # Omitted provider/video_engine
            job1 = service.queue(
                source_text="Default routing test.",
                title="Default Provider",
                format="explainer",
                style="chalkboard",
                style_prompt="vibrant colors",
                language="en",
                focus="key concepts",
                source_url="https://example.com",
                profile="custom-profile",
            )
            self.assertEqual(job1.meta.get("video_engine"), "notebooklm")
            self.assertEqual(job1.meta.get("provider"), "notebooklm")
            self.assertEqual(job1.meta.get("format"), "explainer")
            self.assertEqual(job1.meta.get("style"), "chalkboard")
            self.assertEqual(job1.meta.get("style_prompt"), "vibrant colors")
            self.assertEqual(job1.meta.get("language"), "en")
            self.assertEqual(job1.meta.get("focus"), "key concepts")
            self.assertEqual(job1.meta.get("source_url"), "https://example.com")
            self.assertEqual(job1.meta.get("profile"), "custom-profile")

            # Explicit "default"
            job2 = service.queue(
                source_text="Default explicit test.",
                video_engine="default",
            )
            self.assertEqual(job2.meta.get("video_engine"), "notebooklm")
            self.assertEqual(job2.meta.get("provider"), "notebooklm")
        finally:
            if "service" in locals():
                for j in (locals().get("job1"), locals().get("job2")):
                    if j:
                        try:
                            service.cancel(j.job_id)
                        except Exception:
                            pass
            import shutil
            shutil.rmtree(root_dir, ignore_errors=True)

    def test_service_queue_explicit_native_and_visual_v21(self):
        root_dir = tempfile.mkdtemp()
        try:
            root = Path(root_dir)
            store = VideoFlowStore(root / "jobs.db")
            service = VideoFlowService(store=store, projects_root=root / "projects")

            job_native = service.queue(
                source_text="Native engine test.",
                video_engine="native",
            )
            self.assertEqual(job_native.meta.get("video_engine"), "visual-v2.1")

            job_v21 = service.queue(
                source_text="Visual V2.1 engine test.",
                video_engine="visual-v2.1",
            )
            self.assertEqual(job_v21.meta.get("video_engine"), "visual-v2.1")
        finally:
            if "service" in locals():
                for j in (locals().get("job_native"), locals().get("job_v21")):
                    if j:
                        try:
                            service.cancel(j.job_id)
                        except Exception:
                            pass
            import shutil
            shutil.rmtree(root_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
