"""Adapter for Code2Video's educational outline and storyboard stages."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from voice_flow.video_flow_v3.contracts import validate_no_executable_code

from .process_manager import ProcessManager
from .sandbox import EngineError


class Code2VideoRunner:
    """Use Code2Video's real planning prompts without entering its Manim stages."""

    def __init__(
        self,
        *,
        gateway: Any = None,
        vendor_root: Path | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.gateway = gateway
        from .. import runtime_env as _runtime_env

        self.vendor_root = Path(vendor_root or _runtime_env.code2video_root()
                                or Path(__file__).resolve().parents[3] / "third_party" / "code2video")
        self.timeout_seconds = timeout_seconds
        self._outline_prompt = _load_function(self.vendor_root / "prompts" / "stage1.py", "get_prompt1_outline")
        self._storyboard_prompt = _load_function(self.vendor_root / "prompts" / "stage2.py", "get_prompt2_storyboard")

    def plan(self, source_text: str, **options: Any) -> dict[str, Any]:
        project_dir = Path(options.get("project_dir") or Path.cwd())
        duration_seconds = min(300.0, max(10.0, float(options.get("duration_seconds") or 45.0)))
        outline_prompt = self._outline_prompt(
            knowledge_point=source_text,
            duration=round(duration_seconds / 60.0, 2),
            reference_image_path=None,
        )
        outline_prompt += _request_context(options)
        outline = self._request_json(outline_prompt, project_dir, options)
        _validate_outline(outline)
        _write_json(project_dir / "plan" / "outline.json", outline)

        storyboard_prompt = self._storyboard_prompt(
            outline=json.dumps(outline, ensure_ascii=False, indent=2),
            reference_image_path=None,
        )
        storyboard_prompt += _request_context(options)
        storyboard = self._request_json(storyboard_prompt, project_dir, options)
        _validate_storyboard(storyboard)
        result = {
            "topic": str(outline.get("topic") or options.get("title") or "Video Flow Explanation"),
            "target_audience": str(outline.get("target_audience") or "general learners"),
            "learning_objectives": [
                str(section.get("content") or section.get("title") or "")
                for section in outline["sections"]
            ],
            "sections": storyboard["sections"],
        }
        validate_no_executable_code(result)
        _write_json(project_dir / "storyboard" / "storyboard.json", result)
        return result

    def _request_json(self, prompt: str, project_dir: Path, options: dict[str, Any]) -> dict[str, Any]:
        if self.gateway is not None:
            is_local = bool(getattr(self.gateway, "is_local", False))
            isolated_request = getattr(self.gateway, "request_isolated", None)
            if not is_local:
                if not bool(options.get("allow_external_ai", False)):
                    raise EngineError("provider_error", "External AI planning is not permitted for this request")
                if not callable(isolated_request):
                    raise EngineError("provider_error", "External injected gateways must provide request_isolated")
            try:
                if is_local:
                    response = _call_gateway(
                        self.gateway,
                        prompt,
                        model_ref=options.get("model_ref"),
                        max_tokens=min(16_000, max(512, int(options.get("max_tokens") or 8000))),
                    )
                else:
                    response = isolated_request(
                        prompt=prompt,
                        model_ref=options.get("model_ref"),
                        max_tokens=min(16_000, max(512, int(options.get("max_tokens") or 8000))),
                        timeout_seconds=self.timeout_seconds,
                        job_id=str(options.get("job_id") or "code2video"),
                        process_manager=options.get("process_manager"),
                    )
            except EngineError:
                raise
            except Exception as exc:
                raise EngineError("provider_error", "Configured model gateway failed") from exc
            content = _response_text(response)
            _dump_planner_response(project_dir, content)
        else:
            if not bool(options.get("allow_external_ai", False)):
                raise EngineError("dependency_missing", "Code2Video planning requires a configured model gateway")
            content = self._request_with_vendor_provider(prompt, project_dir, options)
        try:
            payload = _extract_json_object(content)
        except (ValueError, json.JSONDecodeError) as exc:
            raise EngineError("planning_failed", "Code2Video returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EngineError("planning_failed", "Code2Video response must be a JSON object")
        validate_no_executable_code(payload)
        return payload

    def _request_with_vendor_provider(self, prompt: str, project_dir: Path, options: dict[str, Any]) -> str:
        manager = options.get("process_manager")
        if not isinstance(manager, ProcessManager):
            manager = ProcessManager()
        job_id = str(options.get("job_id") or "code2video")
        model = str(options.get("model_ref") or "gpt-41")
        if model not in {"gpt-41", "claude", "gpt-5", "gpt-4o", "gpt-o4mini", "Gemini"}:
            raise EngineError("provider_error", f"Unknown Code2Video model reference: {model}")
        token = uuid.uuid4().hex
        temp_dir = project_dir / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = temp_dir / f"code2video-{token}.prompt.txt"
        response_path = temp_dir / f"code2video-{token}.response.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        process: subprocess.Popen[str] | None = None
        try:
            worker = Path(__file__).with_name("code2video_worker.py")
            command = [
                sys.executable,
                str(worker),
                "--vendor-root",
                str(self.vendor_root),
                "--model",
                model,
                "--prompt-file",
                str(prompt_path),
                "--response-file",
                str(response_path),
                "--max-tokens",
                str(min(16_000, max(512, int(options.get("max_tokens") or 8000)))),
            ]
            process = subprocess.Popen(
                command,
                cwd=str(project_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_safe_environment(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            manager.register(job_id, process)
            try:
                output, _ = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                manager.cancel_job(job_id)
                raise EngineError("timeout", "Code2Video planning timed out") from exc
            log_path = project_dir / "logs" / "code2video.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(output)
            if process.returncode != 0 or not response_path.is_file():
                raise EngineError("provider_error", "Code2Video model provider failed; see logs/code2video.log")
            return response_path.read_text(encoding="utf-8")
        finally:
            if process is not None:
                manager.unregister(job_id, process)
            prompt_path.unlink(missing_ok=True)
            response_path.unlink(missing_ok=True)


def _request_context(options: dict[str, Any]) -> str:
    mode = str(options.get("mode") or "summary")
    visual_direction = str(options.get("visual_direction") or "").strip()
    context = f"\n\nVoice Flow mode: {mode}."
    if visual_direction:
        context += f"\nVisual direction: {visual_direction}."
    return context


def _load_function(path: Path, name: str) -> Callable[..., str]:
    if not path.is_file():
        raise EngineError("dependency_missing", f"Code2Video prompt file is missing: {path}")
    spec = importlib.util.spec_from_file_location(f"video_flow_{path.stem}_{name}", path)
    if spec is None or spec.loader is None:
        raise EngineError("dependency_missing", f"Cannot load Code2Video prompt file: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, name, None)
    if not callable(function):
        raise EngineError("dependency_missing", f"Code2Video prompt function is missing: {name}")
    return function


def _call_gateway(gateway: Any, prompt: str, **kwargs: Any) -> Any:
    if callable(gateway):
        return gateway(prompt, **kwargs)
    for method_name in ("generate", "complete", "request"):
        method = getattr(gateway, method_name, None)
        if callable(method):
            return method(prompt=prompt, **kwargs)
    raise EngineError("dependency_missing", "Configured model gateway has no supported generation method")


def _extract_json_object(content: str) -> dict:
    """Extract the storyboard JSON object from a planner response.

    Planners differ: some return bare JSON, others wrap it in markdown
    fences or surrounding prose, and some emit several objects. Prefer the
    largest balanced JSON object found.
    """
    import re as _re

    text = str(content).strip()
    fence = _re.search(r"```(?:json)?\s*(.*?)```", text, _re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    best_text: str | None = None
    best_obj: dict | None = None
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start : index + 1]
                    if best_text is None or len(candidate) > len(best_text):
                        try:
                            obj = json.loads(candidate)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(obj, dict):
                            best_text, best_obj = candidate, obj
    if best_obj is not None:
        return best_obj
    raise ValueError("No JSON object found in planner response")


def _dump_planner_response(project_dir: Path, content: str) -> None:
    """Persist raw planner responses for offline diagnosis of parse failures."""
    try:
        log_dir = project_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "planner_raw.log", "a", encoding="utf-8") as handle:
            handle.write("\n===== PLANNER RESPONSE =====\n")
            handle.write(str(content))
            handle.write("\n")
    except Exception:
        pass


def _response_text(response: Any) -> str:
    if isinstance(response, tuple) and response:
        response = response[0]
    if isinstance(response, str):
        return response
    try:
        return str(response.choices[0].message.content)
    except (AttributeError, IndexError, TypeError):
        pass
    try:
        return str(response.candidates[0].content.parts[0].text)
    except (AttributeError, IndexError, TypeError):
        return str(response)


def _validate_outline(payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("sections"), list) or not payload["sections"]:
        raise EngineError("planning_failed", "Code2Video outline has no sections")


def _validate_storyboard(payload: dict[str, Any]) -> None:
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise EngineError("planning_failed", "Code2Video storyboard has no sections")
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("lecture_lines"), list):
            raise EngineError("planning_failed", "Code2Video storyboard section is malformed")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA")
    return {name: os.environ[name] for name in allowed if name in os.environ}










