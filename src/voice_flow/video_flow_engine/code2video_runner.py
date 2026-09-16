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

from voice_flow.video_flow_contracts import validate_no_executable_code

from .process_manager import ProcessManager, hidden_window_kwargs
from .sandbox import EngineError

# Planning prompts ride a model gateway whose provider may enforce a tight
# tokens-per-minute ceiling (groq free tier rejects ~8k-token requests with
# HTTP 413). Cap the planning input independently of the full source text.
_PLANNING_SOURCE_MAX_CHARS = 20_000


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
        fmt = str(options.get("format") or "").strip().lower()
        req_fmt = str(options.get("requested_format") or "").strip().lower()
        if fmt in {"short", "brief", "explainer", "cinematic"}:
            resolved_fmt = fmt
        elif req_fmt in {"short", "brief", "explainer", "cinematic"}:
            resolved_fmt = req_fmt
        else:
            from .notebooklm.document_profiler import analyze_document_source
            task_context = str(options.get("task") or options.get("focus") or options.get("visual_direction") or "")
            title_context = str(options.get("title") or "")
            mode_context = str(options.get("mode") or "")
            profile = analyze_document_source(
                source_text,
                requested_format="auto",
                task=task_context,
                title=title_context,
                mode=mode_context,
                focus=task_context,
            )
            resolved_fmt = profile.recommended_format

        options["format"] = resolved_fmt
        default_dur = 45.0
        if not options.get("duration_seconds"):
            try:
                from .notebooklm.document_profiler import analyze_document_source
                prof = analyze_document_source(source_text, requested_format=resolved_fmt)
                default_dur = float(prof.target_duration_seconds)
            except Exception:
                if resolved_fmt == "short":
                    default_dur = 45.0
                elif resolved_fmt == "brief":
                    default_dur = 75.0
                elif resolved_fmt == "explainer":
                    default_dur = 150.0
                elif resolved_fmt == "cinematic":
                    default_dur = 240.0
        else:
            default_dur = float(options["duration_seconds"])
        duration_seconds = min(300.0, max(10.0, default_dur))
        planning_source = _cap_planning_source(source_text)
        try:
            outline_prompt = self._outline_prompt(
                knowledge_point=planning_source,
                duration=round(duration_seconds / 60.0, 2),
                reference_image_path=None,
            )
            outline_prompt += _request_context(options)
            outline = self._request_json(outline_prompt, project_dir, options)
            _validate_outline(outline)
            _write_json(project_dir / "plan" / "outline.json", outline)

            storyboard_prompt = self._storyboard_prompt(
                outline=_compact_outline_json(outline),
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
        except EngineError:
            if not bool(options.get("allow_fallback") or options.get("allow_local_fallback")):
                raise
            import logging
            logging.getLogger(__name__).warning("Model planning failed; using deterministic storyboard")
            result = _deterministic_storyboard(source_text, duration_seconds, options)
            outline = {
                "topic": result["topic"],
                "target_audience": result["target_audience"],
                "sections": [{"id": s["id"], "title": s["title"], "content": " ".join(s.get("lecture_lines", []))} for s in result["sections"]],
            }
            _write_json(project_dir / "plan" / "outline.json", outline)
        except Exception as exc:
            if not bool(options.get("allow_fallback") or options.get("allow_local_fallback")):
                raise
            import logging
            logging.getLogger(__name__).warning("Model planning unavailable or failed (%s); using deterministic storyboard", exc)
            result = _deterministic_storyboard(source_text, duration_seconds, options)
            outline = {
                "topic": result["topic"],
                "target_audience": result["target_audience"],
                "sections": [{"id": s["id"], "title": s["title"], "content": " ".join(s.get("lecture_lines", []))} for s in result["sections"]],
            }
            _write_json(project_dir / "plan" / "outline.json", outline)

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
        try:
            prompt_path.write_text(prompt, encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise EngineError("planning_failed", "Code2Video could not stage its planning prompt") from exc
        process: subprocess.Popen[str] | None = None
        try:
            worker = Path(__file__).with_name("code2video_worker.py")
            if not worker.is_file():
                raise EngineError("dependency_missing", f"Code2Video worker is missing: {worker}")
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
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP | hidden_window_kwargs().get("creationflags", 0)
                    if os.name == "nt"
                    else 0
                ),
                startupinfo=hidden_window_kwargs().get("startupinfo"),
            )
            manager.register(job_id, process)
            try:
                output, _ = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                manager.terminate_job(job_id)
                try:
                    process.communicate(timeout=10)
                except Exception:
                    pass
                raise EngineError("timeout", "Code2Video planning timed out") from exc
            log_path = project_dir / "logs" / "code2video.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(output)
            manager.raise_if_cancelled(job_id)
            if process.returncode != 0 or not response_path.is_file():
                raise EngineError("provider_error", "Code2Video model provider failed; see logs/code2video.log")
            try:
                return response_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise EngineError("provider_error", "Code2Video model provider returned an unreadable response") from exc
        finally:
            if process is not None:
                manager.unregister(job_id, process)
            prompt_path.unlink(missing_ok=True)
            response_path.unlink(missing_ok=True)


def _cap_planning_source(source_text: str) -> str:
    """Trim planning input so the prompt stays within budget while preserving all sections."""
    text = str(source_text or "")
    if len(text) <= _PLANNING_SOURCE_MAX_CHARS:
        return text
    import logging

    logging.getLogger(__name__).info(
        "Planning source capped from %d to %d chars to fit provider token budget",
        len(text), _PLANNING_SOURCE_MAX_CHARS,
    )
    from .notebooklm.document_profiler import extract_document_sections
    sections = extract_document_sections(text)
    if sections and len(sections) > 1:
        budget_per_sec = max(250, int((_PLANNING_SOURCE_MAX_CHARS - 1000) / len(sections)))
        condensed_parts = []
        for s in sections:
            s_title = s.get("title", "")
            s_content = s.get("content", "")
            if len(s_content) > budget_per_sec:
                s_content = s_content[:budget_per_sec].rsplit(" ", 1)[0] + "..."
            condensed_parts.append(f"## {s_title}\n{s_content}")
        return "\n\n".join(condensed_parts)
    head_len = _PLANNING_SOURCE_MAX_CHARS // 2
    tail_len = _PLANNING_SOURCE_MAX_CHARS - head_len
    return f"{text[:head_len]}\n\n[... middle truncated for planning ...]\n\n{text[-tail_len:]}"


def _compact_outline_json(outline: dict[str, Any]) -> str:
    """Serialize the outline without indentation to keep stage-2 prompts small."""
    return json.dumps(outline, ensure_ascii=False, separators=(",", ":"))


def _request_context(options: dict[str, Any]) -> str:
    mode = str(options.get("mode") or "summary")
    visual_direction = str(options.get("visual_direction") or "").strip()
    duration_seconds = options.get("duration_seconds")
    context = f"\n\nVoice Flow mode: {mode}."
    dur = float(duration_seconds or 90.0)
    if duration_seconds:
        context += f"\nTarget duration: {dur:.1f} seconds. Adjust storyboard pacing and section counts proportionally."
    fmt = str(options.get("format") or "").strip().lower()
    target_scenes = max(2, min(24, int(round(dur / 20.0))))
    if fmt == "short":
        context += f"\nFormat: Short (vertical 9:16 aspect ratio, fast-paced high energy, covering all core points across {min(target_scenes, 6)} focused sections with substantive takeaways)."
    elif fmt == "brief":
        context += f"\nFormat: Brief (concise executive overview, covering key sections across {min(target_scenes, 8)} focused sections with critical takeaways)."
    elif fmt == "explainer":
        context += f"\nFormat: Explainer (structured visual explanation, balanced depth across {min(target_scenes, 16)} comprehensive sections explaining mechanisms and data)."
    elif fmt == "cinematic":
        context += f"\nFormat: Cinematic (documentary style, deep-dive narrative immersion across {min(target_scenes, 24)} cinematic sections exploring context and implications)."
    context += "\nContent Requirement: Preserve substantive explanations, inner data, and key context from each section; do not merely list or display surface titles."
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
    fences or surrounding prose, some wrap keys/values in bold/italic formatting,
    and some emit relaxed JSON or several objects. Prefer the largest balanced
    JSON object found with comprehensive repair.
    """
    import re as _re
    import ast as _ast

    def _clean_json_candidate(raw: str) -> str:
        s = str(raw).strip()
        # 1. Strip outer code fences if candidate still has them
        s = _re.sub(r"^(?:```+|~~~+)[a-zA-Z0-9_-]*\s*", "", s)
        s = _re.sub(r"\s*(?:```+|~~~+)$", "", s)
        # 2. Strip single-line comments // ... or # ... outside strings (line-anchored)
        s = _re.sub(r"(?m)^\s*(?://|#)[^\n]*$", "", s)
        # 3. Strip markdown bold / italics across entire lines:
        # e.g. **"key": "val"**, or **"key": "val"**
        s = _re.sub(r"(?m)^\s*\*\*(.*?)\*\*\s*(,?)$", r"\1\2", s)
        s = _re.sub(r"(?m)^\s*__(.*?)__\s*(,?)$", r"\1\2", s)
        # 4. Strip markdown bold or italics around keys (quoted and unquoted):
        # e.g. **"key"**: -> "key":  and  **key**: -> "key":
        s = _re.sub(r'\*\*"([^"]+)"\*\*\s*:', r'"\1":', s)
        s = _re.sub(r'\*\*([a-zA-Z_][a-zA-Z0-9_-]*)\*\*\s*:', r'"\1":', s)
        s = _re.sub(r'__"([^"]+)"__\s*:', r'"\1":', s)
        s = _re.sub(r'__([a-zA-Z_][a-zA-Z0-9_-]*)__\s*:', r'"\1":', s)
        # 5. Strip markdown italics around keys:
        # e.g. *"key"*: or *key*: or _"key"_:
        s = _re.sub(r'\*"([^"]+)"\*\s*:', r'"\1":', s)
        s = _re.sub(r'\*([a-zA-Z_][a-zA-Z0-9_-]*)\*\s*:', r'"\1":', s)
        s = _re.sub(r'_"([^"]+)"_\s*:', r'"\1":', s)
        s = _re.sub(r'_([a-zA-Z_][a-zA-Z0-9_-]*)_\s*:', r'"\1":', s)
        # 6. Strip bold around values:
        s = _re.sub(r':\s*\*\*([^*]+)\*\*', r': \1', s)
        s = _re.sub(r':\s*__([^_]+)__', r': \1', s)
        # 7. General non-greedy bold/italic cleanup:
        s = _re.sub(r'\*\*(.+?)\*\*', r'\1', s)
        s = _re.sub(r'__(.+?)__', r'\1', s)
        # 8. Strip markdown list bullets preceding keys or object items:
        s = _re.sub(r'(?m)^\s*[\*\-]\s*(["{])', r'\1', s)
        # 9. Strip trailing commas before closing braces/brackets (repeatedly)
        for _ in range(3):
            s = _re.sub(r",\s*([\]}])", r"\1", s)
        # 10. Fix unquoted keys in objects: e.g. { topic: "foo" } -> { "topic": "foo" }
        s = _re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*:', r' "\1":', s)
        # 11. Fix single-quoted keys in objects: e.g. { 'topic': "foo" } -> { "topic": "foo" }
        s = _re.sub(r"(?<=[{,])\s*'([^']+)'\s*:", r' "\1":', s)
        return s.strip()

    def _try_parse_json(candidate: str) -> dict | None:
        if not candidate or not candidate.strip():
            return None
        # 1. Direct json.loads with strict=False (allows unescaped control chars)
        try:
            obj = json.loads(candidate, strict=False)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        # 2. Clean candidate and retry json.loads
        cleaned = _clean_json_candidate(candidate)
        try:
            obj = json.loads(cleaned, strict=False)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        # 3. Python literal eval fallback for dicts emitted with single quotes or python booleans
        try:
            py_cand = cleaned
            py_cand = _re.sub(r':\s*true\b', ': True', py_cand)
            py_cand = _re.sub(r':\s*false\b', ': False', py_cand)
            py_cand = _re.sub(r':\s*null\b', ': None', py_cand)
            obj = _ast.literal_eval(py_cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        return None

    text = str(content).strip()
    fence = _re.search(r"(?:```+|~~~+)[a-zA-Z0-9_-]*\s*(.*?)(?:```+|~~~+)", text, _re.DOTALL)
    if fence:
        parsed = _try_parse_json(fence.group(1))
        if parsed is not None:
            return parsed

    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed

    best_text: str | None = None
    best_obj: dict | None = None

    # Scan for balanced JSON objects on both raw and cleaned text
    for scan_text in (text, _clean_json_candidate(text)):
        depth = 0
        start = -1
        in_string = False
        escaped = False
        for index, char in enumerate(scan_text):
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
                        candidate = scan_text[start : index + 1]
                        obj = _try_parse_json(candidate)
                        if obj is not None and (best_text is None or len(candidate) > len(best_text)):
                            best_text, best_obj = candidate, obj
        if best_obj is not None:
            return best_obj

    # Global first '{' to last '}' fallback
    for target in (_clean_json_candidate(text), text):
        first_b = target.find("{")
        last_b = target.rfind("}")
        if first_b >= 0 and last_b > first_b:
            obj = _try_parse_json(target[first_b : last_b + 1])
            if obj is not None:
                return obj

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


def _deterministic_storyboard(source_text: str, duration_seconds: float, options: dict[str, Any]) -> dict[str, Any]:
    title = str(options.get("title") or "").strip()
    raw_lines = [p.strip() for p in source_text.replace("\r\n", "\n").split("\n") if p.strip()]
    if len(raw_lines) <= 1 and raw_lines:
        import re
        raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw_lines[0]) if s.strip()]
        lines = raw_sentences if raw_sentences else raw_lines
    else:
        lines = raw_lines if raw_lines else ["Video Flow Explanation"]

    topic = title or (lines[0][:60] if lines else "Video Flow Explanation")

    fmt = str(options.get("format") or "").strip().lower()
    if fmt == "short":
        target_count = max(2, min(4, int(duration_seconds / 15.0) or 2))
    elif fmt == "brief":
        target_count = max(2, min(5, int(duration_seconds / 20.0) or 3))
    elif fmt == "cinematic":
        target_count = max(4, min(10, int(duration_seconds / 25.0) or 5))
    elif fmt == "explainer":
        target_count = max(3, min(8, int(duration_seconds / 25.0) or 4))
    else:
        target_count = max(2, min(12, int(duration_seconds / 15.0)))
    target_count = min(target_count, max(2, len(lines)))
    target_count = min(target_count, 12)
    chunk_size = max(1, min(4, len(lines) // target_count or 1))

    sections: list[dict[str, Any]] = []
    for i in range(0, len(lines), chunk_size):
        chunk = [line[:250] for line in lines[i:i + chunk_size][:4]]
        if not chunk:
            continue
        sec_num = len(sections) + 1
        sec_title = chunk[0][:50] if len(chunk[0]) <= 50 else f"Concept {sec_num}"
        sections.append({
            "id": f"section_{sec_num}",
            "title": sec_title,
            "lecture_lines": chunk,
            "animations": [f"Illustrate {sec_title}"],
        })
        if len(sections) >= target_count:
            break

    if not sections:
        sections = [{
            "id": "section_1",
            "title": topic[:50],
            "lecture_lines": [lines[0][:250] if lines else "Core concept overview."],
            "animations": ["Illustrate key concept"],
        }]

    for s in sections:
        if len(s["lecture_lines"]) > 6:
            s["lecture_lines"] = s["lecture_lines"][:6]
        if not s["lecture_lines"]:
            s["lecture_lines"] = [s["title"]]

    return {
        "topic": topic,
        "target_audience": "general learners",
        "learning_objectives": [str(s["title"]) for s in sections],
        "sections": sections,
    }











