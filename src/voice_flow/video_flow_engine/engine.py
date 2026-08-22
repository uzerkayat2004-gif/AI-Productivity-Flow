"""Voice Flow-facing facade for the Code2Video -> Narova pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from .bridge import build_directed_production, build_narova_production
from .code2video_runner import Code2VideoRunner
from .narova_runner import NarovaRunner
from .process_manager import ProcessManager
from .sandbox import EngineError, prepare_job_directory

logger = logging.getLogger(__name__)

global_process_manager = ProcessManager()

_FALLBACK_RENDER_CODES = {"render_failed", "invalid_narova_config"}


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

    def run(self, video_id: str, **kwargs: Any) -> dict[str, Any]:
        callback: Callable[[dict[str, Any]], None] = kwargs.get("progress_callback") or (lambda _: None)
        report_context: dict[str, Path | None] = {"log_path": None}
        report = _reporter(callback, kwargs.get("job"), report_context)
        source_text = str(kwargs.get("source_text") or "").strip()

        try:
            project_dir = prepare_job_directory(
                video_id,
                projects_root=Path(kwargs["projects_root"]) if kwargs.get("projects_root") else None,
                project_dir=Path(kwargs["project_dir"]) if kwargs.get("project_dir") else None,
            )
            report_context["log_path"] = project_dir / "logs" / "job.log"
            if not source_text:
                raise EngineError("planning_failed", "source_text is required")
            self.process_manager.raise_if_cancelled(video_id)
            if len(source_text) > 100_000:
                raise EngineError("planning_failed", "source_text exceeds the 100000-character limit")
            (project_dir / "source.txt").write_text(source_text, encoding="utf-8")

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
                }
            )
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
                report(48, "Browser render unavailable — using portable renderer", "directing")
                logger.warning("HyperFrames render failed (%s); retrying with portable renderer", exc)
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
            report(98, "Finalizing", "buffering")
            report(100, "Ready", "complete")
            return {
                "video_id": video_id,
                "state": "complete",
                "message": "Ready",
                "video_path": str(video_path),
                "placeholder": False,
            }
        except Exception as exc:
            if isinstance(exc, EngineError):
                logger.warning("VideoFlowEngine.run failed for %s: %s", video_id, exc)
            else:
                logger.exception("VideoFlowEngine.run failed for %s", video_id)
            message = str(exc) or exc.__class__.__name__
            error_code = exc.code if isinstance(exc, EngineError) else _error_code(message)
            report(0, message, "cancelled" if error_code == "cancelled" else "failed")
            return {
                "video_id": video_id,
                "state": "cancelled" if error_code == "cancelled" else "failed",
                "message": message,
                "error_code": error_code,
                "placeholder": False,
            }

    def cancel(self, job_id: str) -> None:
        self.process_manager.cancel_job(job_id)

    def _build_production(
        self,
        storyboard: dict[str, Any],
        kwargs: dict[str, Any],
        project_dir: Path,
        report: Callable[[float, str, str], None],
    ) -> dict[str, Any]:
        """Creative Director (LLM or deterministic) → authored production.

        Falls back to the legacy portable production whenever the director or
        scene authoring fails, so generation never breaks.
        """
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
) -> Callable[[float, str, str], None]:
    def report(progress: float, message: str, state: str) -> None:
        event = {"progress": float(progress), "message": message, "state": state}
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










