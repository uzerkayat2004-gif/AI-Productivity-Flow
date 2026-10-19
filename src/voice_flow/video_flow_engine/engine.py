"""Voice Flow-facing facade for the Code2Video -> Narova pipeline."""

from __future__ import annotations

import dataclasses

import json
import logging
from pathlib import Path
from typing import Any, Callable, Mapping

from .bridge import build_directed_production, build_narova_production
from .code2video_runner import Code2VideoRunner
from .narova_runner import NarovaRunner
from .process_manager import ProcessManager
from .sandbox import EngineError, prepare_job_directory

logger = logging.getLogger(__name__)

global_process_manager = ProcessManager()

_FALLBACK_RENDER_CODES = {"render_failed", "invalid_narova_config"}

# Mirrors video_flow_service._SECRET so auth diagnostics never persist raw
# credentials in job history. Kept local to avoid an import cycle.
_SECRET = None
try:
    import re as _re

    _SECRET = _re.compile(r"(?i)(?:bearer\s+|api[_ -]?key[=:]\s*|[a-z]{0,3}sk[-_][a-z0-9_-]{8,})[^\s,;]+")
except Exception:
    _SECRET = None


def _redact_secret(value: Any) -> str:
    text = str(value or "").strip()
    if _SECRET is not None:
        text = _SECRET.sub("[redacted]", text)
    return text[:300]


class VideoFlowEngine:
    """Deep module hiding planning, validation, rendering, and error mapping."""

    def __init__(
        self,
        process_manager: ProcessManager | None = None,
        *,
        planner: Any = None,
        renderer: Any = None,
        model_gateway: Any = None,
    ) -> None:
        self.process_manager = process_manager or global_process_manager
        self.planner = planner
        self.renderer = renderer
        self.model_gateway = model_gateway

    @staticmethod
    def _gather_research_sources(
        source_text: str,
        kwargs: dict[str, Any],
        project_dir: Path,
        report: Callable[..., Any],
    ) -> list[dict[str, Any]]:
        """Optional Tavily web research ("Research with web sources").

        Runs only when the user ticked the box *and* allowed external AI
        planning for this video; without a Tavily key it is a no-op. Any
        failure leaves planning exactly as it was without research.
        """
        try:
            from voice_flow import tavily_research

            if not (tavily_research.research_requested(kwargs) and kwargs.get("allow_external_ai") is True):
                return []
            report(12, "Researching web sources", "understanding")
            sources = tavily_research.gather_sources(source_text, kwargs)
            if sources:
                path = project_dir / "plan" / "research_sources.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"provider": "tavily", "sources": tavily_research.public_sources(sources)}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            return sources
        except Exception as exc:
            logger.warning("Video Flow web research skipped (%s)", exc.__class__.__name__)
            return []

    def run(self, video_id: str, **kwargs: Any) -> dict[str, Any]:
        callback: Callable[[dict[str, Any]], None] = kwargs.get("progress_callback") or (lambda _: None)
        report_context: dict[str, Path | None] = {"log_path": None}
        report = _reporter(callback, kwargs.get("job"), report_context)
        source_text = str(kwargs.get("source_text") or "").strip()
        visual_context: dict[str, Any] = {}

        try:
            project_dir = prepare_job_directory(
                video_id,
                projects_root=Path(kwargs["projects_root"]) if kwargs.get("projects_root") else None,
                project_dir=Path(kwargs["project_dir"]) if kwargs.get("project_dir") else None,
            )
            report_context["log_path"] = project_dir / "logs" / "job.log"
            provider_req = str(kwargs.get("provider") or kwargs.get("video_engine") or "").strip().lower().replace("_", "-")
            format_name = self._resolve_auto_format(kwargs)
            kwargs["format"] = format_name

            if provider_req in {"default", "notebooklm", "notebook-lm", "nlm"}:
                return self._run_notebooklm(video_id, project_dir, report, kwargs)

            if not source_text:
                raise EngineError("planning_failed", "source_text is required")
            self.process_manager.raise_if_cancelled(video_id)
            if len(source_text) > 100_000:
                raise EngineError("planning_failed", "source_text exceeds the 100000-character limit")
            (project_dir / "source.txt").write_text(source_text, encoding="utf-8")

            # Resolve format-specific duration if duration_seconds not explicitly provided
            duration_sec = kwargs.get("duration_seconds")
            if duration_sec is None:
                profile_meta = kwargs.get("document_profile")
                if isinstance(profile_meta, Mapping) and profile_meta.get("target_duration_seconds"):
                    duration_sec = profile_meta["target_duration_seconds"]
                else:
                    from .notebooklm.document_profiler import analyze_document_source
                    duration_sec = analyze_document_source(
                        source_text,
                        requested_format=format_name,
                        task=kwargs.get("task") or kwargs.get("focus") or kwargs.get("visual_direction") or kwargs.get("prompt"),
                        title=kwargs.get("title"),
                        mode=kwargs.get("mode"),
                    ).target_duration_seconds
                kwargs["duration_seconds"] = duration_sec

            report(5, "Preparing", "queued")
            report(10, "Understanding text", "understanding")
            planner_options = {
                key: value
                for key, value in kwargs.items()
                if key not in {"source_text", "project_dir", "projects_root", "progress_callback", "job", "voice"}
            }
            planner_options.update(
                {
                    "project_dir": project_dir,
                    "job_id": video_id,
                    "process_manager": self.process_manager,
                    "format": format_name,
                    "duration_seconds": duration_sec,
                }
            )
            research_sources = self._gather_research_sources(source_text, kwargs, project_dir, report)
            if research_sources:
                planner_options["research_sources"] = research_sources
            planner = self.planner or Code2VideoRunner(gateway=self.model_gateway)
            renderer = self.renderer or NarovaRunner()
            storyboard = planner.plan(source_text, **planner_options)
            self.process_manager.raise_if_cancelled(video_id)
            report(35, "Creating storyboard", "directing")

            production = self._build_production(
                storyboard,
                kwargs,
                project_dir,
                report,
                video_id=video_id,
                visual_context=visual_context,
            )
            report(45, "Translating visual plan", "directing")
            try:
                video_path = Path(
                    renderer.render(
                        production,
                        project_dir,
                        job_id=video_id,
                        process_manager=self.process_manager,
                        progress_callback=lambda event: report(
                            float(event["progress"]),
                            str(event["message"]),
                            str(event["state"]),
                        ),
                    )
                )
            except EngineError as exc:
                # Full-fidelity browser rendering must never take Video Flow
                # down with it: fall back once to the portable renderer.
                if str(production.get("renderer")) != "hyperframes" or exc.code not in _FALLBACK_RENDER_CODES:
                    raise
                if self.process_manager.is_cancelled(video_id):
                    raise
                report(48, "Browser render unavailable — using portable renderer", "directing")
                logger.warning("HyperFrames render failed (%s); retrying with portable renderer", exc)
                visual_context.pop("pending_signature", None)
                visual_context.pop("signature_store", None)
                provenance = visual_context.get("provenance")
                if provenance is not None and getattr(provenance, "requested_engine", None) == "visual-v2.1":
                    from .production_provenance import ENGINE_PORTABLE
                    try:
                        visual_context["provenance"] = provenance.fallback(final_engine=ENGINE_PORTABLE, stage="browser", reason=str(exc.code or "browser_render_failed"))
                    except Exception:
                        visual_context["provenance"] = provenance
                legacy = self._legacy_production(storyboard, kwargs)
                video_path = Path(
                    renderer.render(
                        legacy,
                        project_dir,
                        job_id=video_id,
                        process_manager=self.process_manager,
                        progress_callback=lambda event: report(
                            float(event["progress"]),
                            str(event["message"]),
                            str(event["state"]),
                        ),
                    )
                )
            if not video_path.is_file() or video_path.stat().st_size == 0:
                raise EngineError("render_failed", "renderer did not produce video.mp4")
            pending_signature = visual_context.get("pending_signature")
            signature_store = visual_context.get("signature_store")
            if pending_signature is not None and signature_store is not None:
                try:
                    self.process_manager.raise_if_cancelled(video_id)
                    signature_store.append(pending_signature)
                except RuntimeError:
                    raise
                except Exception as exc:
                    logger.warning("Video Flow V2 signature persistence failed (%s)", exc.__class__.__name__)
            provenance = visual_context.get("provenance")
            if provenance is not None:
                from .production_provenance import write_provenance_json
                try:
                    if not provenance.final:
                        provenance = provenance.complete()
                    provenance = provenance.with_final_artifact("video.mp4", kind="video")
                    write_provenance_json(project_dir, provenance)
                    visual_context["provenance"] = provenance
                except Exception as exc:
                    logger.warning("Video Flow provenance persistence failed (%s)", exc.__class__.__name__)
            report(98, "Finalizing", "buffering")
            report(100, "Ready", "complete")
            result = {
                "video_id": video_id,
                "state": "complete",
                "message": "Ready",
                "video_path": str(video_path),
                "placeholder": False,
                "duration_seconds": kwargs.get("duration_seconds"),
            }
            # Honest-fallback context so the job/UI can show that the
            # requested engine (e.g. NotebookLM) could not be used.
            for _fb_key in ("fallback_reason", "fallback_requested_engine", "fallback_error"):
                if kwargs.get(_fb_key):
                    result[_fb_key] = _redact_secret(kwargs[_fb_key]) if _fb_key == "fallback_error" else kwargs[_fb_key]
            if visual_context.get("provenance") is not None:
                result["provenance"] = visual_context["provenance"].to_dict()
            return result
        except Exception as exc:
            if isinstance(exc, EngineError):
                logger.warning("VideoFlowEngine.run failed for %s: %s", video_id, exc)
            else:
                logger.exception("VideoFlowEngine.run failed for %s", video_id)
            is_cancelled_job = (
                self.process_manager.is_cancelled(video_id)
                or getattr(exc, "code", None) == "cancelled"
                or str(exc).lower().startswith("cancelled")
            )
            if is_cancelled_job:
                error_code = "cancelled"
                message = "Cancelled"
            else:
                message = str(exc) or exc.__class__.__name__
                error_code = exc.code if isinstance(exc, EngineError) else _error_code(message)
                if hasattr(exc, "code") and exc.code:
                    error_code = exc.code
                    if ": " in message and message.startswith(f"{exc.code}: "):
                        message = message[len(f"{exc.code}: "):]
                elif "auth_expired" in str(error_code).lower() or "authentication expired" in message.lower() or "expired or invalid" in message.lower():
                    error_code = "auth_expired"
                    message = "Google account login expired. Please sign in to NotebookLM in Video Flow settings."

            provenance = visual_context.get("provenance")
            if provenance is not None:
                from dataclasses import replace
                from .production_provenance import write_provenance_json
                try:
                    if error_code == "cancelled":
                        provenance = provenance.cancel()
                    else:
                        # A render/portable failure is terminal but must not
                        # retain a prior final-engine success marker.
                        provenance = replace(
                            provenance,
                            final_engine=None,
                            fallback_used=False,
                            fallback_stage=None,
                            fallback_reason=None,
                            attempt_status="failed",
                            final_status="failed",
                            final_artifacts=(),
                        )
                    visual_context["provenance"] = provenance
                    write_provenance_json(project_dir, provenance)
                except Exception as provenance_exc:
                    logger.warning("Video Flow terminal provenance persistence failed (%s)", provenance_exc.__class__.__name__)
            report(0, message, "cancelled" if error_code == "cancelled" else "failed")
            result = {
                "video_id": video_id,
                "state": "cancelled" if error_code == "cancelled" else "failed",
                "message": message,
                "error_code": error_code,
                "error_message": message,
                "placeholder": False,
                "duration_seconds": kwargs.get("duration_seconds"),
            }
            if visual_context.get("provenance") is not None:
                result["provenance"] = visual_context["provenance"].to_dict()
            return result


    @staticmethod
    def _cinematic_allowed(profile: Any) -> bool:
        try:
            from voice_flow.video_flow_engine.notebooklm.account_plan import cinematic_allowed

            return cinematic_allowed(str(profile) if profile else None)
        except Exception:
            return False

    @staticmethod
    def _resolve_auto_format(kwargs: Mapping[str, Any]) -> str:
        """Resolve the Auto-Adaptive format to a concrete NotebookLM format.

        The floating-bar composer sends format='auto'; the desktop page resolves
        it client-side. Resolving here (from the document profile's target
        duration) makes every entry point behave identically instead of failing
        NotebookLM validation with "Unsupported format 'auto'".
        """
        from .notebooklm import VIDEO_FORMATS

        fmt = str(kwargs.get("format") or "").strip().lower()
        if fmt in VIDEO_FORMATS:
            return fmt
        req_fmt = str(kwargs.get("requested_format") or "").strip().lower()
        if req_fmt in VIDEO_FORMATS:
            return req_fmt

        profile_meta = kwargs.get("document_profile")
        if isinstance(profile_meta, Mapping):
            rec_format = str(profile_meta.get("recommended_format") or profile_meta.get("resolved_format") or "").strip().lower()
            if rec_format in VIDEO_FORMATS:
                return rec_format

        # First, try resolving via source document and task context
        source_text = str(kwargs.get("source_text") or "").strip()
        source_file = kwargs.get("source_file")
        if not source_text and source_file:
            try:
                sf = Path(source_file)
                if sf.is_file():
                    source_text = sf.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                pass
        if source_text or source_file:
            from .notebooklm.document_profiler import analyze_document_source
            task_context = str(kwargs.get("task") or kwargs.get("focus") or kwargs.get("visual_direction") or kwargs.get("prompt") or "")
            title_context = str(kwargs.get("title") or "")
            mode_context = str(kwargs.get("mode") or "")
            profile = analyze_document_source(
                source_text,
                source_path=source_file,
                requested_format="auto",
                task=task_context,
                title=title_context,
                mode=mode_context,
                focus=task_context,
            )
            return profile.recommended_format

        # Otherwise, fall back to target duration tiers if duration was provided
        target: float | None = None
        if isinstance(profile_meta, Mapping):
            raw = profile_meta.get("target_duration_seconds")
            try:
                target = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                target = None
        if target is None and kwargs.get("duration_seconds") is not None:
            try:
                target = float(kwargs["duration_seconds"])
            except (TypeError, ValueError):
                target = None

        if target is not None:
            if target <= 45:
                return "short"
            if target <= 120:
                return "brief"
            if target <= 240:
                return "explainer"
            return "cinematic"

        return "explainer"

    def cancel(self, job_id: str) -> None:
        self.process_manager.cancel_job(job_id)

    def _run_notebooklm(
        self,
        video_id: str,
        project_dir: Path,
        report: Callable[[float, str, str], None],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the NotebookLM video generation pipeline."""
        from .notebooklm import DEFAULT_FORMAT, VIDEO_FORMATS, VIDEO_STYLES, NotebookLMVideoError, NotebookLMVideoProvider, VideoRequest

        report(5, "Checking NotebookLM authentication", "auth_check")
        self.process_manager.raise_if_cancelled(video_id)

        source_file = Path(kwargs["source_file"]) if kwargs.get("source_file") else None
        source_url = str(kwargs.get("source_url") or "") or None
        source_text = str(kwargs.get("source_text") or "").strip() or None

        title = str(kwargs.get("title") or "Video Overview").strip()
        prompt = str(kwargs.get("focus") or kwargs.get("visual_direction") or kwargs.get("prompt") or "Explain the content clearly with visual illustrations.").strip()

        output_path = project_dir / "video.mp4"
        format_name = self._resolve_auto_format(kwargs)
        # Cinematic (Veo) videos need a Google AI Ultra plan. On Free/Pro,
        # NotebookLM rejects the request and the job died with a bare
        # "generation_failed". Auto-Adaptive must never pick it: only a user
        # who explicitly chose Cinematic gets it.
        explicit_cinematic = str(kwargs.get("requested_format") or "").strip().lower() == "cinematic"
        if format_name == "cinematic" and not explicit_cinematic:
            logger.info("Auto-Adaptive resolved to cinematic; using explainer (cinematic needs AI Ultra)")
            format_name = "explainer"
        if format_name == "cinematic" and not self._cinematic_allowed(kwargs.get("profile")):
            # Only a confirmed Google AI Ultra account can make Cinematic. The
            # UI no longer offers it to anyone else; this guards old retries
            # and the floating bar.
            logger.info("Cinematic requested without a confirmed AI Ultra plan; using explainer")
            format_name = "explainer"
        style_name = str(kwargs.get("style") or "auto").strip().lower()
        if style_name not in VIDEO_STYLES:
            style_name = "auto"
        style_prompt = str(kwargs.get("style_prompt") or "") if kwargs.get("style_prompt") else None
        language = str(kwargs.get("language") or "") if kwargs.get("language") else None
        profile = kwargs.get("profile")
        timeout_seconds = int(kwargs.get("timeout_seconds") or 1800)
        # An unbounded or non-positive planning timeout would hang a worker
        # thread forever; clamp to the CEO-approved finite 10m–2h window so
        # long cloud renders still complete but runaways always fail.
        try:
            timeout_seconds = int(timeout_seconds)
        except (TypeError, ValueError):
            timeout_seconds = 1800
        timeout_seconds = max(600, min(7200, timeout_seconds))
        notebook_id = kwargs.get("notebook_id")
        source_id = kwargs.get("source_id")
        task_id = kwargs.get("task_id")

        # Thread the requested duration through to NotebookLM: explicit
        # per-job duration first (clamped to the supported 10–300s window),
        # then the document profile's own target, so the provider never
        # silently drops back to an auto-derived default.
        request_target: float | None = None
        for candidate in (
            kwargs.get("target_duration_seconds"),
            kwargs.get("duration_seconds"),
        ):
            try:
                value = float(candidate) if candidate is not None else None
            except (TypeError, ValueError):
                value = None
            if value is not None and 10.0 <= value <= 300.0:
                request_target = value
                break
        profile_meta = kwargs.get("document_profile")
        if request_target is None and isinstance(profile_meta, Mapping):
            try:
                value = float(profile_meta.get("target_duration_seconds")) if profile_meta.get("target_duration_seconds") is not None else None
            except (TypeError, ValueError):
                value = None
            if value is not None and 10.0 <= value <= 300.0:
                request_target = value

        def _progress_bridge(event: Mapping[str, Any]) -> None:
            st = str(event.get("state") or "")
            phase = str(event.get("phase") or "")
            elapsed = event.get("elapsed")
            timings = event.get("timings")
            extra: dict[str, Any] = {}
            if phase:
                extra["phase"] = phase
            if elapsed is not None:
                extra["elapsed"] = elapsed
            if timings:
                extra["timings"] = timings

            if st in ("auth_check", "auth_complete"):
                report(10, "Verifying Google authentication", "auth_check", **extra)
            elif st in ("notebook_create", "notebook_setup_start", "notebook_setup_complete"):
                report(20, "Creating NotebookLM notebook", "notebook_create", **extra)
            elif st in ("source_add", "source_ingest_start", "source_ingest_complete"):
                report(30, "Uploading source to NotebookLM", "source_add", **extra)
            elif st == "source_wait":
                report(40, "Waiting for source indexing", "source_wait", **extra)
            elif st in ("video_start", "cloud_synthesis_start"):
                report(50, "Requesting Video Overview generation", "video_start", **extra)
            elif st == "video_poll":
                report(65, "Generating video overview in cloud...", "video_poll", **extra)
            elif st in ("video_download", "download_start", "download_complete"):
                report(85, "Downloading completed MP4 artifact", "video_download", **extra)
            elif st in ("probe_start", "probe_complete", "normalizing"):
                report(95, "Normalizing media format", "normalizing", **extra)
            else:
                report(50, f"Processing {st}", st, **extra)

        allow_fallback = bool(kwargs.get("allow_local_fallback", True))

        provider = NotebookLMVideoProvider(
            cli_path=kwargs.get("cli_path"),
            profile=profile,
            workdir=project_dir,
            progress_callback=_progress_bridge,
            process_manager=self.process_manager,
            reuse_workspace=bool(kwargs.get("reuse_workspace", False)),
            allow_local_fallback=False,  # the engine owns the local fallback (it has the model gateway)
        )

        request = VideoRequest(
            title=title,
            prompt=prompt,
            output_path=output_path,
            source_file=source_file,
            source_url=source_url,
            source_text=source_text,
            notebook_id=notebook_id,
            source_id=source_id,
            task_id=task_id,
            format=format_name,
            style=style_name,
            style_prompt=style_prompt,
            language=language,
            job_id=video_id,
            timeout_seconds=timeout_seconds,
            profile=provider.profile,
            retain_notebook=bool(kwargs.get("retain_notebook", True)),
            reuse_workspace=bool(kwargs.get("reuse_workspace", False)),
            allow_local_fallback=False,  # the engine owns the local fallback (it has the model gateway)
            document_profile=kwargs.get("document_profile"),
            target_duration_seconds=request_target,
        )

        try:
            try:
                artifact = provider.generate(request)
            except Exception as first_exc:
                first_code = str(getattr(first_exc, "code", "") or "")
                first_msg = str(first_exc).lower()
                retry_as_explainer = (
                    not self.process_manager.is_cancelled(video_id)
                    and first_code not in {"cancelled", "auth_expired", "AUTH", "auth_unavailable", "RATE_LIMITED", "rate_limited", "TIMEOUT"}
                    and not any(k in first_msg for k in ("expired", "re-authenticate", "not authenticated", "rate limit", "cancelled"))
                )
                if not retry_as_explainer:
                    raise
                # NotebookLM refused this generation (Cinematic needs Google AI
                # Ultra; other refusals are often transient). Try once more as a
                # plain Explainer with a fresh notebook before giving up.
                logger.warning("NotebookLM generation failed (%s); retrying once as explainer", first_exc)
                if request.format == "cinematic":
                    report(50, "Cinematic needs Google AI Ultra, making an Explainer video instead", "video_start")
                else:
                    report(50, "NotebookLM had a problem, trying once more", "video_start")
                request = dataclasses.replace(
                    request,
                    format="explainer",
                    style=style_name if style_name != "custom" else "auto",
                    style_prompt=None if style_name == "custom" else request.style_prompt,
                    notebook_id=None,
                    source_id=None,
                    task_id=None,
                )
                try:
                    artifact = provider.generate(request)
                except Exception as second_exc:
                    setattr(second_exc, "_voice_flow_generation_retried", True)
                    raise second_exc from first_exc
        except Exception as exc:
            if (
                self.process_manager.is_cancelled(video_id)
                or getattr(exc, "code", None) == "cancelled"
                or str(exc).lower().startswith("cancelled")
            ):
                raise NotebookLMVideoError("cancelled", f"Job {video_id} was cancelled") from exc
            is_auth = (getattr(exc, "code", "") in {"auth_expired", "AUTH"}) or "authentication expired" in str(exc).lower() or "expired or invalid" in str(exc).lower() or "login expired" in str(exc).lower() or "psidts" in str(exc).lower() or "re-authenticate" in str(exc).lower() or "not authenticated" in str(exc).lower()
            if is_auth and not getattr(exc, "_voice_flow_retried_after_reauth", False):
                # Self-heal: if the durable master token exists, mint fresh
                # web cookies headlessly (no browser) and retry once. This is
                # the "sign in once, keeps working" path.
                heal = self._recover_notebooklm_auth(profile or provider.profile, provider)
                if heal.get("ok"):
                    logger.info("NotebookLM auth recovered via master-token remint; retrying")
                    report(12, "Login refreshed automatically — retrying NotebookLM", "auth_check")
                    try:
                        artifact = provider.generate(request)
                    except Exception as retry_exc:
                        setattr(retry_exc, "_voice_flow_retried_after_reauth", True)
                        if allow_fallback:
                            logger.warning("NotebookLM retry after remint failed (%s); falling back to local Visual V2.1 engine", retry_exc)
                            report(15, "NotebookLM login expired — rendering with local engine", "directing")
                            return self._auth_fallback_to_local(video_id, kwargs, source_text, source_file, source_url, title, retry_exc)
                        raise
                    # Retry succeeded — skip the except-path entirely.
                    self.process_manager.raise_if_cancelled(video_id)
                    if not output_path.is_file() or output_path.stat().st_size <= 0:
                        raise EngineError("download_failed", "NotebookLM video generation produced no local MP4")
                    report(98, "Finalizing", "normalizing")
                    report(100, "Ready", "ready")
                    return {
                        "video_id": video_id,
                        "state": "ready",
                        "message": "Video generated successfully with NotebookLM",
                        "video_path": str(output_path),
                        "output_path": str(output_path),
                        "job_id": video_id,
                        "provider": "notebooklm",
                        "artifact": artifact.to_dict(),
                        "provenance_path": artifact.provenance_path,
                        "duration_seconds": artifact.duration_seconds,
                        "timings": dict(artifact.timings),
                        "document_profile": artifact.document_profile,
                    }
                logger.info("NotebookLM self-heal unavailable (%s); continuing to fallback logic", heal.get("error"))
            if is_auth and allow_fallback:
                logger.warning("NotebookLM auth expired (%s); falling back to local Visual V2.1 engine", exc)
                report(15, "NotebookLM login expired — rendering with local engine", "directing")
                return self._auth_fallback_to_local(video_id, kwargs, source_text, source_file, source_url, title, exc)
            is_rate_limited = "rate" in str(getattr(exc, "code", "") or "").lower() or "rate limit" in str(exc).lower() or "usage limit" in str(exc).lower()
            if (
                not is_auth
                and not is_rate_limited
                and (getattr(exc, "_voice_flow_generation_retried", False) or str(getattr(exc, "code", "")) == "TIMEOUT")
                and allow_fallback
            ):
                # NotebookLM refused the video twice. Make it with the local
                # engine instead of leaving the user with a dead card.
                logger.warning("NotebookLM generation failed twice (%s); falling back to local engine", exc)
                report(15, "NotebookLM couldn't make this video — rendering with local engine", "directing")
                return self._auth_fallback_to_local(
                    video_id, kwargs, source_text, source_file, source_url, title, exc,
                    reason="notebooklm_generation_failed",
                )
            raise

        self.process_manager.raise_if_cancelled(video_id)

        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise EngineError("download_failed", "NotebookLM video generation produced no local MP4")

        report(98, "Finalizing", "normalizing")
        report(100, "Ready", "ready")

        return {
            "video_id": video_id,
            "state": "ready",
            "message": "Video generated successfully with NotebookLM",
            "video_path": str(output_path),
            "output_path": str(output_path),
            "job_id": video_id,
            "provider": "notebooklm",
            "artifact": artifact.to_dict(),
            "provenance_path": artifact.provenance_path,
            "duration_seconds": artifact.duration_seconds,
            "timings": dict(artifact.timings),
            "document_profile": artifact.document_profile,
        }

    @staticmethod
    def _recover_notebooklm_auth(profile: Any, provider: Any) -> dict[str, Any]:
        """Same sign-in recovery Audio Flow uses, so Video does not fail where Audio works.

        1. Master-token remint (no browser). 2. Copy cookies from the user's
        browser. 3. Headless Playwright cookie sync. Each step is verified.
        """
        from .notebooklm import login_flow

        last_error: Any = None
        try:
            heal = login_flow.self_heal(profile=profile)
            if heal.get("ok"):
                return heal
            last_error = heal.get("error")
        except Exception as exc:  # pragma: no cover - defensive
            last_error = str(exc)

        def _verified() -> bool:
            try:
                if hasattr(provider, "sync_storage_state"):
                    provider.sync_storage_state(force=True)
                status = provider.check_auth(raise_on_error=False)
                return bool(getattr(status, "authenticated", False))
            except Exception:
                return False

        import os as _os
        in_tests = bool(_os.environ.get("PYTEST_CURRENT_TEST"))
        if not in_tests or _os.environ.get("VOICE_FLOW_TEST_AUTO_HEAL"):
            try:
                from .notebooklm.browser_sync import auto_sync_from_browser

                res = auto_sync_from_browser(profile=profile)
                if res.get("success") and _verified():
                    logger.info("NotebookLM auth recovered from the browser session")
                    return {"ok": True, "method": "browser_sync"}
            except Exception as exc:
                last_error = last_error or str(exc)
        if not in_tests or _os.environ.get("VOICE_FLOW_TEST_PLAYWRIGHT_HEAL"):
            try:
                from .notebooklm.browser_sync import sync_cookies_with_playwright

                res = sync_cookies_with_playwright(profile=profile, headless=True, timeout_seconds=35)
                if res.get("success") and _verified():
                    logger.info("NotebookLM auth recovered with a headless cookie sync")
                    return {"ok": True, "method": "playwright_sync"}
            except Exception as exc:
                last_error = last_error or str(exc)
        return {"ok": False, "error": last_error}

    def _auth_fallback_to_local(
        self,
        video_id: str,
        kwargs: Mapping[str, Any],
        source_text: str | None,
        source_file: Path | None,
        source_url: str | None,
        title: str,
        exc: Exception,
        reason: str = "notebooklm_auth_expired",
    ) -> dict[str, Any]:
        """Re-run the job on the local engine after NotebookLM could not make it."""
        local_kwargs = dict(kwargs)
        local_kwargs["provider"] = "visual-v2.1"
        local_kwargs["video_engine"] = "visual-v2.1"
        local_kwargs["source_text"] = source_text or (source_file.read_text(encoding="utf-8") if source_file and source_file.is_file() else "") or source_url or title
        # Honest-fallback metadata: the job records that the user asked
        # for NotebookLM and why the local engine took over, so the UI
        # can show a badge instead of pretending the request succeeded.
        # Redact first: provider diagnostics can echo key material.
        local_kwargs["fallback_reason"] = reason
        local_kwargs["fallback_requested_engine"] = "notebooklm"
        local_kwargs["fallback_error"] = _redact_secret(str(exc))[:300]
        result = self.run(video_id, **local_kwargs)
        if isinstance(result, dict) and result.get("state") == "failed":
            # The local engine could not stand in either. Tell the user the
            # real, fixable reason (NotebookLM sign-in), not a generic
            # "generation_failed" from the fallback.
            local_error = str(result.get("error_message") or result.get("message") or "")
            if reason == "notebooklm_generation_failed":
                nlm_reason = str(getattr(exc, "message", "") or str(exc) or "").strip()
                message = (
                    "NotebookLM couldn't make this video"
                    + (f" ({_redact_secret(nlm_reason)[:160]})" if nlm_reason else "")
                    + ". Wait a few minutes and tap Retry, or try a shorter document."
                )
                result.update(
                    {
                        "error_code": str(getattr(exc, "code", "") or "notebooklm_generation_failed"),
                        "error_message": message,
                        "message": message,
                        "fallback_error": _redact_secret(local_error)[:300],
                    }
                )
                return result
            message = (
                "NotebookLM sign-in expired. Open Video Flow settings, sign in to "
                "NotebookLM again, then tap Retry."
            )
            result.update(
                {
                    "error_code": "auth_expired",
                    "error_message": message,
                    "message": message,
                    "fallback_error": _redact_secret(local_error)[:300],
                }
            )
        return result

    def _build_production(
        self,
        storyboard: dict[str, Any],
        kwargs: dict[str, Any],
        project_dir: Path,
        report: Callable[[float, str, str], None],
        *,
        video_id: str,
        visual_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Creative Director (LLM or deterministic) → authored production.

        Falls back to the legacy portable production whenever the director or
        scene authoring fails, so generation never breaks.
        """
        if _visual_v21_enabled(kwargs):
            try:
                return self._build_visual_v21(
                    storyboard,
                    kwargs,
                    project_dir,
                    report,
                    video_id=video_id,
                    visual_context=visual_context,
                )
            except Exception as exc:
                if _v2_cancelled(exc, self.process_manager, video_id):
                    raise
                provenance = visual_context.get("provenance")
                if provenance is None:
                    from .production_provenance import new_provenance
                    provenance = new_provenance()
                try:
                    visual_context["provenance"] = provenance.fallback(
                        final_engine="visual-v1",
                        stage=_v21_failure_stage(exc),
                        reason=_v21_failure_reason(exc),
                    )
                except Exception:
                    visual_context["provenance"] = provenance
                visual_context.pop("pending_signature", None)
                visual_context.pop("signature_store", None)
                logger.warning("Video Flow V2.1 failed; using V1 fallback (%s)", _v2_failure_type(exc))

        elif _visual_v2_enabled(kwargs):
            try:
                from .scene_compiler_v2 import compile_visual_plan_v2
                from .visual_director_v2 import direct_visual_plan_v2
                from .visual_signature import VisualSignatureStore, signature_from
                from .visual_validator import validate_compiled_visual_v2
                from voice_flow.paths import data_dir

                report(36, "Visual Director V2 selected", "directing")
                logger.info("Video Flow V2 selected")
                signature_store = VisualSignatureStore(data_dir() / "video_flow" / "visual-signatures.json")
                visual_plan = direct_visual_plan_v2(
                    storyboard,
                    self.model_gateway,
                    model_ref=kwargs.get("model_ref"),
                    allow_external_ai=kwargs.get("allow_external_ai") is True,
                    visual_direction=str(kwargs.get("visual_direction") or ""),
                    theme=kwargs.get("theme"),
                    job_id=video_id,
                    process_manager=self.process_manager,
                    project_dir=project_dir,
                    recent_signatures=[signature.to_dict() for signature in signature_store.recent()],
                )
                report(39, "Visual plan validated", "directing")
                logger.info("Video Flow V2 visual plan validated")
                compiled = compile_visual_plan_v2(
                    storyboard,
                    visual_plan,
                    title=str(kwargs.get("title") or ""),
                    mode=str(kwargs.get("mode") or "summary"),
                    theme=kwargs.get("theme"),
                    voice=kwargs.get("voice"),
                )
                validation = validate_compiled_visual_v2(compiled)
                signature = signature_from(visual_plan, compiled)
                artifacts = compiled.to_artifacts()
                artifacts["validation.json"] = validation.to_dict()
                artifacts["visual-signature.json"] = signature.to_dict()
                _write_visual_v2_artifacts(project_dir, artifacts)
                visual_context["pending_signature"] = signature
                visual_context["signature_store"] = signature_store
                report(42, "Style, layout, and V2 scenes compiled", "directing")
                logger.info("Video Flow V2 style/layout/scene compilation complete")
                return compiled.production
            except Exception as exc:
                if _v2_cancelled(exc, self.process_manager, video_id):
                    raise
                logger.warning("Video Flow V2 failed; using V1 fallback (%s)", _v2_failure_type(exc))
        direction = None
        if kwargs.get("allow_external_ai") or self.model_gateway is None:
            try:
                from .creative_director import DirectorError, direct

                direction = direct(
                    storyboard,
                    self.model_gateway,
                    theme=kwargs.get("theme"),
                    visual_direction=str(kwargs.get("visual_direction") or ""),
                )
                (project_dir / "creative-direction.json").write_text(
                    __import__("json").dumps(direction, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:
                if isinstance(exc, DirectorError):
                    logger.info("Creative Director unavailable: %s", exc)
                else:
                    logger.warning("Creative Director failed; using deterministic direction", exc_info=True)
                direction = None
        if direction is not None:
            try:
                return build_directed_production(
                    storyboard,
                    direction,
                    title=str(kwargs.get("title") or ""),
                    mode=str(kwargs.get("mode") or "summary"),
                    theme=kwargs.get("theme"),
                    voice=kwargs.get("voice"),
                )
            except Exception as exc:
                logger.warning("Directed production failed; using legacy bridge: %s", exc)
        return self._legacy_production(storyboard, kwargs)

    def _build_visual_v21(
        self,
        storyboard: dict[str, Any],
        kwargs: dict[str, Any],
        project_dir: Path,
        report: Callable[[float, str, str], None],
        *,
        video_id: str,
        visual_context: dict[str, Any],
    ) -> dict[str, Any]:
        from .production_provenance import new_provenance, record_attempt_artifact
        from .scene_compiler_v2 import compile_visual_program_v21
        from .visual_director_v2 import direct_visual_program_v21
        from .visual_validator import validate_compiled_visual_program_v21, validate_visual_program_v21
        from .visual_signature import VisualSignatureStore
        from voice_flow.paths import data_dir

        provenance = new_provenance()
        visual_context["provenance"] = provenance
        report(36, "Visual Director V2.1 selected", "directing")
        signature_store = VisualSignatureStore(data_dir() / "video_flow" / "visual-signatures.json")
        program = direct_visual_program_v21(
            storyboard,
            self.model_gateway,
            model_ref=kwargs.get("model_ref"),
            allow_external_ai=kwargs.get("allow_external_ai") is True,
            mode=str(kwargs.get("mode") or "summary"),
            duration_seconds=kwargs.get("duration_seconds"),
            visual_direction=str(kwargs.get("visual_direction") or ""),
            theme=kwargs.get("theme"),
            job_id=video_id,
            process_manager=self.process_manager,
            project_dir=project_dir,
            recent_signatures=[signature.to_dict() for signature in signature_store.recent()],
        )
        provenance = record_attempt_artifact(provenance, "visual/visual-program-v21.json")
        visual_context["provenance"] = provenance
        report(39, "Visual program validated", "directing")
        validate_visual_program_v21(program, storyboard=storyboard)
        compiled = compile_visual_program_v21(
            storyboard,
            program,
            title=str(kwargs.get("title") or ""),
            mode=str(kwargs.get("mode") or "summary"),
            duration_seconds=kwargs.get("duration_seconds"),
            theme=kwargs.get("theme"),
            visual_direction=str(kwargs.get("visual_direction") or ""),
            voice=kwargs.get("voice"),
        )
        validation = validate_compiled_visual_program_v21(compiled)
        
        from .visual_validator import validate_compiled_visual_program_v21, validate_visual_program_v21, evaluate_visual_quality_v21
        from dataclasses import asdict, replace
        evaluation = evaluate_visual_quality_v21(program, compiled)
        provenance = replace(provenance, evaluation=asdict(evaluation))
            
        artifacts = compiled.to_artifacts()
        artifacts["validation-v21.json"] = validation.to_dict()
        artifacts["evaluation-v21.json"] = asdict(evaluation)
        _write_visual_v21_artifacts(project_dir, artifacts)
        for relative in artifacts:
            provenance = record_attempt_artifact(provenance, f"visual/{relative}")
        visual_context["provenance"] = provenance
        visual_context["pending_signature"] = _signature_from_v21(program)
        visual_context["signature_store"] = signature_store
        report(42, "V2.1 style, layout, motion, and scenes compiled", "directing")
        return compiled.production

    def _legacy_production(self, storyboard: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
        try:
            return build_narova_production(
                storyboard,
                title=str(kwargs.get("title") or ""),
                mode=str(kwargs.get("mode") or "summary"),
                theme=kwargs.get("theme"),
                visual_direction=str(kwargs.get("visual_direction") or ""),
                voice=kwargs.get("voice"),
            )
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError("bridge_failed", f"Bridge validation failed: {exc}") from exc


def _reporter(
    callback: Callable[[dict[str, Any]], None],
    job: Any,
    context: dict[str, Path | None],
) -> Callable[..., None]:
    def report(progress: float, message: str, state: str, **extra: Any) -> None:
        event = {"progress": float(progress), "message": _redact_secret(message), "state": state, **extra}
        log_path = context.get("log_path")
        if log_path is not None:
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            except Exception:
                logger.warning("Video Flow job log update failed", exc_info=True)
        try:
            if job is not None:
                if isinstance(job, dict):
                    job.update(event)
                else:
                    for key, value in event.items():
                        if hasattr(job, key):
                            setattr(job, key, value)
        except Exception:
            logger.warning("Video Flow job progress update failed", exc_info=True)
        try:
            callback(event)
        except Exception:
            logger.warning("Video Flow progress callback failed", exc_info=True)

    return report


def _error_code(message: str) -> str:
    prefix = message.split(":", 1)[0]
    known = {
        "dependency_missing",
        "planning_failed",
        "bridge_failed",
        "invalid_narova_config",
        "tts_failed",
        "render_failed",
        "ffmpeg_failed",
        "timeout",
        "cancelled",
        "provider_error",
    }
    return prefix if prefix in known else "generation_failed"












def _visual_v21_enabled(kwargs: dict[str, Any]) -> bool:
    if "visual_v21_enabled" in kwargs:
        return bool(kwargs.get("visual_v21_enabled"))
    if kwargs.get("visual_v2_enabled") is True:
        return False
    import os
    if os.environ.get("VIDEO_FLOW_VISUAL_V2", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    raw = os.environ.get("VIDEO_FLOW_VISUAL_V21", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _v21_failure_stage(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "").casefold()
    if "storyboard" in code or "provider" in code or "response" in code or "duration" in code:
        return "planning"
    if "program" in code or "capability" in code or "reference" in code:
        return "capability_validation"
    if "render" in code or "browser" in code:
        return "render"
    return "compile"


def _v21_failure_reason(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "").strip()
    reason = code or exc.__class__.__name__
    return " ".join(reason.replace("_", " ").split())[:240]


def _signature_from_v21(program: Any) -> Any:
    from .visual_signature import VisualSignature
    bible = program.design_bible
    surface = str(bible.surface_mode)
    palette = str(bible.palette_intent.accent_family)
    background = str(bible.background_character).replace("_", "-")
    camera = str(program.scenes[0].shot.mode if program.scenes else "focus")
    structural_3d = any(str(subject.render_strategy) == "semantic_3d" or subject.structural_family == "celestial_body" for scene in program.scenes for subject in scene.subjects)
    layered = any(len(scene.subjects) > 1 for scene in program.scenes)
    density = max(1, min(16, round(sum(len(scene.subjects) for scene in program.scenes) / max(1, len(program.scenes)))))
    allowed_palette = {"none", "signal-red", "red", "orange", "amber", "yellow", "green", "blue", "violet", "purple", "pink", "teal", "earth", "hard-white", "black", "white", "gray", "mono"}
    allowed_background = {"solid", "gradient", "grid", "texture", "negative-space", "paper"}
    return VisualSignature(
        surface_mode=surface if surface in {"solid", "flat", "paper", "ink", "technical", "glass", "metallic", "emissive", "textured"} else "solid",
        palette_family=palette if palette in allowed_palette else "gray",
        background_family=background if background in allowed_background else "solid",
        typography_family=str(bible.typography_character) if str(bible.typography_character) in {"technical", "editorial", "geometric", "humanist", "display", "monospace"} else "geometric",
        motion_profile=str(bible.motion_character) if str(bible.motion_character) in {"crisp", "flowing", "technical", "measured", "playful", "cinematic"} else "crisp",
        camera_profile=camera if camera in {"static", "focus", "zoom", "pan", "orbit", "dolly", "follow"} else "focus",
        depth_profile="spatial" if structural_3d else "layered" if layered else "flat",
        scene_density=density,
        usage_3d=structural_3d,
    )


def _write_visual_v21_artifacts(project_dir: Path, artifacts: Any) -> None:
    if not isinstance(artifacts, dict):
        raise ValueError("V2.1 compiler artifacts must be a mapping")
    for relative, content in artifacts.items():
        raw = str(relative).replace("\\", "/")
        parts = Path(raw).parts
        valid_scene = len(parts) == 2 and parts[0] == "scene-ir" and parts[1].endswith(".json") and parts[1][:-5]
        valid_fixed = raw in {"resolved-design.json", "scene-ir/index.json", "visual-program-v21.json", "motion-qa-v21.json", "scene-space-v21.json", "validation-v21.json", "evaluation-v21.json"}
        if not raw or raw.startswith("/") or Path(raw).is_absolute() or ".." in parts or ":" in raw or not (valid_scene or valid_fixed):
            raise ValueError("V2.1 compiler artifact path is unsafe")
        target = project_dir / "visual" / Path(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")



def _visual_v2_enabled(kwargs: dict[str, Any]) -> bool:
    if "visual_v2_enabled" in kwargs:
        return kwargs.get("visual_v2_enabled") is True
    import os

    return os.environ.get("VIDEO_FLOW_VISUAL_V2", "").strip().lower() in {"1", "true", "yes", "on"}


def _v2_cancelled(exc: Exception, process_manager: ProcessManager, video_id: str) -> bool:
    if str(getattr(exc, "code", "")).casefold() == "cancelled":
        return True
    if str(exc).startswith("cancelled:"):
        return True
    try:
        return process_manager.is_cancelled(video_id)
    except Exception:
        return False


def _v2_failure_type(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return str(code) if isinstance(code, str) and code else exc.__class__.__name__


def _write_visual_v2_artifacts(project_dir: Path, artifacts: Any) -> None:
    if not isinstance(artifacts, dict):
        raise ValueError("V2 compiler artifacts must be a mapping")
    targets: list[tuple[Path, Any]] = []
    visual_dir = project_dir / "visual"
    for relative, content in artifacts.items():
        raw = str(relative).replace("\\", "/")
        parts = Path(raw).parts
        scene_artifact = (
            len(parts) == 2
            and parts[0] == "scene-ir"
            and parts[1].endswith(".json")
            and parts[1][:-5]
            and parts[1][:-5][0].isalpha()
            and all(char.isalnum() or char in "_-" for char in parts[1][:-5])
        )
        fixed_artifact = raw in {"resolved-design.json", "validation.json", "visual-signature.json", "scene-ir/index.json"}
        if (
            not raw
            or raw.startswith("/")
            or Path(raw).is_absolute()
            or ".." in parts
            or ":" in raw
            or not (fixed_artifact or scene_artifact)
        ):
            raise ValueError("V2 compiler artifact path is unsafe")
        targets.append((visual_dir.joinpath(*parts), content))
    for target, content in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
