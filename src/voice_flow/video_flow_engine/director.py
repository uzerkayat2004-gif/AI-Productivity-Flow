"""Open-ended creative direction for Video Flow.

The visual director deliberately stops one level above rendering.  It turns
evidence and a viewer request into a treatment and semantic storyboard, but it
does not pick a completed scene layout.  A scene brief describes what the
viewer should see change and why; the scene runtime remains free to compose
that material with its typed scene graph.

The module is intentionally independent from ``contracts.py``.  During the
engine migration the canonical artifacts may be dataclasses, pydantic models,
or dictionaries.  The small coercion layer below accepts all three and emits
``ArtifactMap`` objects, which behave as both mappings and attribute objects.
That gives callers a stable seam without imposing a second canonical schema.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any, Protocol, runtime_checkable


class StructuredGenerationError(RuntimeError):
    """Raised when an injected structured generator returns unusable output."""


@runtime_checkable
class StructuredGenerator(Protocol):
    """Protocol for an optional model adapter.

    Implementations may accept the complete context mapping, or the more
    explicit ``(evidence, request, history)`` arguments.  ``VisualDirector``
    supports both forms to keep provider adapters out of this module.
    """

    def __call__(self, context: Mapping[str, Any]) -> Mapping[str, Any] | str: ...


class ArtifactMap(dict[str, Any]):
    """A dict with light attribute access for canonical-artifact bridges."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - normal Python semantics
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def copy(self) -> "ArtifactMap":
        return ArtifactMap(super().copy())


def _mapping(value: Any) -> dict[str, Any]:
    """Coerce a mapping, dataclass, pydantic model, or plain object."""

    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        except Exception:
            pass
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        try:
            mapped = to_mapping()
            if isinstance(mapped, Mapping):
                return dict(mapped)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return {
            str(key): item
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return {}


def _artifact(value: Any) -> Any:
    """Recursively preserve flexible artifact mappings."""

    if isinstance(value, ArtifactMap):
        return ArtifactMap({key: _artifact(item) for key, item in value.items()})
    if isinstance(value, Mapping) or is_dataclass(value) or hasattr(value, "model_dump"):
        return ArtifactMap({key: _artifact(item) for key, item in _mapping(value).items()})
    if isinstance(value, (list, tuple)):
        return [_artifact(item) for item in value]
    if isinstance(value, set):
        return [_artifact(item) for item in sorted(value, key=str)]
    return value


def _pick(value: Any, *names: str, default: Any = None) -> Any:
    data = _mapping(value)
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
        camel = _camel(name)
        if camel in data and data[camel] is not None:
            return data[camel]
    return default


def _camel(name: str) -> str:
    bits = name.split("_")
    return bits[0] + "".join(bit.title() for bit in bits[1:])


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return ", ".join(_text(item) for item in value if _text(item))
    return re.sub(r"\s+", " ", str(value)).strip()


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)):
        return [value] if _text(value) else []
    if isinstance(value, Mapping):
        return list(value.values())
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def _words(value: Any) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", _text(value))


def _slug(value: Any, fallback: str = "scene") -> str:
    result = re.sub(r"[^a-z0-9]+", "-", _text(value).lower()).strip("-")
    return result or fallback


def _digest(value: Any, length: int = 16) -> str:
    try:
        payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        payload = repr(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _spatial_depth_terms(value: Any) -> bool:
    """Return whether text explicitly calls for a spatial/depth treatment.

    This deliberately uses a small, high-signal vocabulary. A source merely
    mentioning the depth of a statistic should not force a WebGL scene, while
    phrases such as 3D assembly or cross-section should survive the
    director/compiler seam as an explicit requirement.
    """

    text = _text(value).lower()
    if not text:
        return False
    patterns = (
        r"\b3\s*d\b", r"\b3d\b", r"three[- ]dimensional", r"three\.js",
        r"\bwebgl\b", r"volumetric", r"spatial depth", r"depth perspective",
        r"cross[- ]section", r"cutaway", r"inside the", r"layered assembly",
        r"rotate around", r"orbit(?:al|ing)?", r"solid geometry", r"topology",
        r"physical mechanism", r"in three dimensions",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _normalise_render_class(value: Any, default: str = "motion-island") -> str:
    """Canonicalize model render-class spellings without relaxing the contract."""

    raw = _text(value).lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "3d": "webgl-3d",
        "webgl": "webgl-3d",
        "webgl3d": "webgl-3d",
        "webgl-3d": "webgl-3d",
        "three": "webgl-3d",
        "three-js": "webgl-3d",
        "motion": "motion-island",
        "motion-island": "motion-island",
        "continuous": "continuous-2d",
        "continuous-2d": "continuous-2d",
        "static-editorial": "static",
        "static": "static",
        "media": "media",
        "existing-media": "media",
    }
    return aliases.get(raw, default)


def _normalise_duration(
    data: Mapping[str, Any],
    narration: str = "",
    *,
    minimum: float = 2.5,
    maximum: float = 24.0,
) -> float:
    """Read common model duration aliases and clamp to a safe scene range."""

    raw = _pick(
        data,
        "duration_seconds", "durationSeconds", "duration_in_seconds", "durationInSeconds",
        "scene_duration_seconds", "sceneDurationSeconds", "duration", "length_seconds",
        "lengthSeconds", "length", "seconds",
        default=0.0,
    )
    duration = _safe_float(raw, 0.0)
    if duration <= 0:
        duration = 0.36 * max(8, len(_words(narration)))
    return round(max(minimum, min(maximum, duration)), 3)
def _first_sentence(value: Any, maximum: int = 92) -> str:
    text = _text(value)
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    words = sentence.split()
    if len(words) > 13:
        sentence = " ".join(words[:13]) + "…"
    return sentence[:maximum].rstrip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _normalise_claims(evidence: Mapping[str, Any]) -> list[ArtifactMap]:
    raw = _pick(evidence, "claims", "facts", "evidence_items", "items", default=[])
    claims: list[ArtifactMap] = []
    for index, item in enumerate(_list(raw)):
        data = _mapping(item)
        statement = _text(
            _pick(data, "statement", "claim", "text", "content", "description", default=item)
        )
        if not statement:
            continue
        claim_id = _text(_pick(data, "id", "claim_id", "claimId", "key", default=f"claim-{index + 1}"))
        source_refs = _list(_pick(data, "source_refs", "source_references", "sourceRefs", "refs", default=[]))
        claims.append(
            ArtifactMap(
                {
                    "id": claim_id or f"claim-{index + 1}",
                    "statement": statement,
                    "kind": _text(_pick(data, "claim_type", "claimType", "kind", "classification", "type", default="source_fact")) or "source_fact",
                    "source_refs": [_text(ref) for ref in source_refs if _text(ref)],
                    "confidence": _safe_float(_pick(data, "confidence", default=1.0), 1.0),
                    "source_span": _pick(data, "source_span", "span", "sourceSpan", default=None),
                    "raw": _artifact(data),
                }
            )
        )
    if claims:
        return claims

    # Some evidence adapters expose a flat ``text`` and no claims.  Retaining
    # one explicitly marked claim keeps truth references visible in the brief
    # without pretending the source contained a finer-grained claim graph.
    text = _text(_pick(evidence, "text", "source_text", "content", default=""))
    if text:
        return [ArtifactMap({"id": "claim-1", "statement": text, "kind": "source_fact", "source_refs": []})]
    return []


def _normalise_entities(evidence: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]) -> list[str]:
    raw = _pick(evidence, "entities", "topics", "subjects", default=[])
    entities = [
        _text(_pick(_mapping(item), "label", "name", "text", default=item))
        for item in _list(raw)
        if _text(_pick(_mapping(item), "label", "name", "text", default=item))
    ]
    if entities:
        return list(dict.fromkeys(entities))[:24]
    candidates: list[str] = []
    stop = {
        "about", "after", "again", "because", "being", "could", "first", "have", "into",
        "more", "most", "other", "over", "their", "there", "these", "those", "through",
        "under", "which", "where", "while", "would", "your", "that", "this", "with",
    }
    for claim in claims:
        for word in _words(claim.get("statement")):
            if len(word) > 4 and word.lower() not in stop:
                candidates.append(word.lower())
    return list(dict.fromkeys(candidates))[:12]


def _request_map(request: Any, source: Any) -> ArtifactMap:
    if isinstance(request, str):
        return ArtifactMap({"instruction": _text(request)})
    result = ArtifactMap(_artifact(_mapping(request)))
    if not result:
        if isinstance(source, str):
            result["instruction"] = _text(source)
        else:
            source_data = _mapping(source)
            instruction = _pick(source_data, "instruction", "request", "question", "prompt", default="")
            if instruction:
                result["instruction"] = _text(instruction)
    return result


def _history_list(history: Any) -> list[ArtifactMap]:
    if history is None:
        return []
    if isinstance(history, Mapping):
        history = _pick(history, "items", "videos", "history", "entries", default=[history])
    return [ArtifactMap(_artifact(_mapping(item))) for item in _list(history) if _mapping(item)]


def _colour(seed: str, offset: int) -> str:
    digest = hashlib.sha256(f"{seed}:{offset}".encode("utf-8")).hexdigest()
    # Keep deterministic fallback colors away from the very light and very
    # dark extremes so treatment roles remain visible on a neutral field.
    r = 52 + int(digest[0:2], 16) % 164
    g = 52 + int(digest[2:4], 16) % 164
    b = 52 + int(digest[4:6], 16) % 164
    return f"#{r:02x}{g:02x}{b:02x}"


def _contains(value: Any, *needles: str) -> bool:
    haystack = _text(value).lower()
    return any(needle in haystack for needle in needles)


def _domain(evidence: Mapping[str, Any], request: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]) -> str:
    explicit = _text(_pick(evidence, "domain", "subject_domain", default="")) or _text(
        _pick(request, "domain", "subject_domain", default="")
    )
    if explicit:
        return explicit.lower()
    text = " ".join(
        [_text(_pick(evidence, "title", "source_title", default=""))]
        + [_text(c.get("statement")) for c in claims]
    )
    hints = (
        ("security", ("attack", "credential", "breach", "malware", "threat")),
        ("science", ("molecule", "experiment", "cell", "orbit", "physics")),
        ("technology", ("software", "api", "database", "model", "code", "system")),
        ("health", ("patient", "disease", "heart", "treatment", "health")),
        ("finance", ("market", "revenue", "price", "investment", "cost")),
        ("history", ("century", "war", "empire", "historical", "archive")),
    )
    for name, words in hints:
        if any(word in text.lower() for word in words):
            return name
    return "general"


def _semantic_shape(statement: str, evidence: Mapping[str, Any]) -> str:
    explicit = _text(_pick(evidence, "data_shape", "shape", default=""))
    if explicit:
        return explicit
    lower = statement.lower()
    if any(word in lower for word in ("first", "then", "next", "finally", "before", "after")):
        return "sequence"
    if any(word in lower for word in ("compared", "versus", "than", "difference", "both", "unlike")):
        return "comparison"
    if any(word in lower for word in ("%", "percent", "million", "billion", "increase", "decrease", "times")):
        return "quantity"
    if any(word in lower for word in ("causes", "leads", "depends", "connects", "between", "relationship")):
        return "causal"
    return "concept"


def _normalise_timing(raw: Any, duration: float, narration: str, actions: Sequence[str]) -> list[ArtifactMap]:
    """Normalize timing aliases to bounded, QA-readable second intervals.

    Ratio aliases are converted using the canonical scene duration; genuinely
    overlapping/contradictory beats are left visible for QA to reject.
    """

    timings: list[ArtifactMap] = []
    raw_items = _list(raw)
    safe_duration = max(0.01, _safe_float(duration, 0.0))
    for index, item in enumerate(raw_items):
        data = _mapping(item)
        start_ratio = _pick(data, "start_ratio", "startRatio", "from_ratio", "fromRatio", default=None)
        end_ratio = _pick(data, "end_ratio", "endRatio", "to_ratio", "toRatio", default=None)
        if start_ratio is not None:
            start = _safe_float(start_ratio, 0.0) * safe_duration
        else:
            start = _safe_float(
                _pick(data, "start", "start_seconds", "startSeconds", "from", "start_time", "startTime", default=0.0),
                0.0,
            )
        if end_ratio is not None:
            end = _safe_float(end_ratio, 1.0) * safe_duration
        else:
            end = _safe_float(
                _pick(data, "end", "end_seconds", "endSeconds", "to", "end_time", "endTime", default=0.0),
                0.0,
            )
        if end <= start:
            end = start + max(0.35, safe_duration / max(1, len(raw_items)))
        start = max(0.0, min(safe_duration, start))
        end = max(start + 0.01, min(safe_duration, end))
        if end > safe_duration:
            end = safe_duration
            start = max(0.0, min(start, max(0.0, safe_duration - 0.01)))
        label = _text(_pick(data, "label", "name", "title", default=""))
        visual_event = _text(_pick(data, "visual_event", "event", "visualEvent", "anchor", default=label))
        timings.append(
            ArtifactMap(
                {
                    "id": _text(_pick(data, "id", "anchor_id", "anchorId", default=f"beat-{index + 1}")),
                    "start_seconds": round(start, 3),
                    "end_seconds": round(end, 3),
                    "start_ratio": round(start / safe_duration, 6),
                    "end_ratio": round(end / safe_duration, 6),
                    "words": _text(_pick(data, "words", "text", "narration", "spoken_text", default="")),
                    "label": label,
                    "visual_event": visual_event or "semantic reveal",
                }
            )
        )
    if timings:
        return timings
    if not narration:
        return []
    count = max(1, min(len(actions) or 1, math.ceil(len(_words(narration)) / 8)))
    step = safe_duration / count
    words = _words(narration)
    for index in range(count):
        start = index * step
        end = safe_duration if index == count - 1 else (index + 1) * step
        start_word = round(index * len(words) / count)
        end_word = round((index + 1) * len(words) / count)
        timings.append(
            ArtifactMap(
                {
                    "id": f"beat-{index + 1}",
                    "start_seconds": round(start, 3),
                    "end_seconds": round(end, 3),
                    "start_ratio": round(start / safe_duration, 6),
                    "end_ratio": round(end / safe_duration, 6),
                    "words": " ".join(words[start_word:end_word]),
                    "visual_event": _text(actions[index] if index < len(actions) else "reveal"),
                }
            )
        )
    return timings

def _forbidden_layout_fields(data: Mapping[str, Any]) -> dict[str, Any]:
    """Remove completed-layout selectors while retaining diagnostics.

    A model may still return ``template`` or ``layout_id`` because it was
    trained on the old planner.  Keeping those selectors in a direction
    package would make the runtime silently converge on a finite catalog.
    The value is retained only in diagnostics so a provider can improve its
    prompt, never as a renderer instruction.
    """

    forbidden: dict[str, Any] = {}
    keys = {
        "template", "template_id", "templateId", "layout_id", "layoutId", "layout_name",
        "layoutName", "preset", "recipe", "scene_template", "sceneTemplate",
    }
    for key in keys:
        if key in data and data[key] not in (None, "", [], {}):
            forbidden[key] = data[key]
    return forbidden


@dataclass(frozen=True)
class DirectorConfig:
    """Conservative defaults for deterministic planning."""

    minimum_scenes: int = 2
    maximum_scenes: int = 8
    max_visible_words: int = 36
    max_visible_chars: int = 240
    diversity_window: int = 10


class VisualDirector:
    """Create open-ended creative treatments and semantic storyboards.

    ``structured_generator`` is optional.  If supplied, it receives a
    serializable context and may return a mapping or JSON object.  Any
    malformed/failed response falls back to the deterministic planner, so a
    provider outage cannot accidentally choose a primitive compatibility
    layout.
    """

    def __init__(
        self,
        structured_generator: Callable[..., Any] | None = None,
        *,
        model_generate: Callable[..., Any] | None = None,
        config: DirectorConfig | None = None,
    ) -> None:
        self.structured_generator = structured_generator or model_generate
        self.config = config or DirectorConfig()

    def create(
        self,
        evidence_pack: Any,
        source: Any = None,
        model_generate: Callable[..., Any] | None = None,
        diversity_history: Any = None,
        user_direction: str = "",
        *,
        request: Any = None,
        history: Any = None,
        generator: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> ArtifactMap:
        """Direct one video from evidence, intent, and recent creative history.

        Positional arguments intentionally mirror the migration brief while
        keyword aliases (``request``, ``history``, ``generator``) make it easy
        for the final canonical engine to bridge in its own names.
        """

        evidence = ArtifactMap(_artifact(_mapping(evidence_pack)))
        source_value = source
        if request is None:
            request = kwargs.get("intent") or kwargs.get("user_request")
        request_data = _request_map(request, source_value)
        if user_direction:
            request_data["user_direction"] = _text(user_direction)
        recent = _history_list(history if history is not None else diversity_history)
        claims = _normalise_claims(evidence)
        entities = _normalise_entities(evidence, claims)
        domain = _domain(evidence, request_data, claims)
        explicit_spatial = bool(_pick(request_data, "spatial_depth_requested", "spatialDepthRequested", default=False))
        explicit_spatial = explicit_spatial or _spatial_depth_terms(
            _pick(request_data, "visual_direction", "visualDirection", "user_direction", "instruction", "style", default="")
        )
        source_text = json.dumps(evidence, ensure_ascii=False, default=str)
        spatial_required = bool(explicit_spatial and _spatial_depth_terms(source_text))
        request_data["spatial_depth_requested"] = explicit_spatial
        request_data["spatial_depth_required"] = spatial_required

        context = ArtifactMap(
            {
                "evidence_pack": evidence,
                "source": _artifact(source_value) if not isinstance(source_value, str) else source_value,
                "request": request_data,
                "history": recent[-self.config.diversity_window :],
                "user_direction": _text(user_direction),
                "spatial_depth_requested": explicit_spatial,
                "spatial_depth_required": spatial_required,
                "constraints": self.design_constitution(),
                "instruction": (
                    "Author an original creative treatment and semantic storyboard. "
                    "Describe scene purpose, visible relationships, and meaningful changes; "
                    "never select a completed template or fixed layout."
                ),
            }
        )

        generation_error = ""
        generated: Mapping[str, Any] | None = None
        active_generator = generator or model_generate or self.structured_generator
        if active_generator is not None:
            try:
                generated = self._call_generator(active_generator, context, evidence, request_data, recent)
            except Exception as exc:
                generation_error = f"{type(exc).__name__}: {exc}"[:500]

        fallback = self._fallback(evidence, request_data, claims, entities, domain, recent)
        if generated:
            package = self._merge_generated(generated, fallback, evidence, request_data, claims, entities, domain)
            generation_mode = "structured"
        else:
            raise RuntimeError(
                "The selected visual-director model did not return a structured creative treatment"
                + (f": {generation_error}" if generation_error else ".")
            )

        diagnostics = ArtifactMap(_artifact(_mapping(package.get("diagnostics", {}))))
        diagnostics.update(
            {
                "generation_mode": generation_mode,
                "generator_error": generation_error,
                "used_completed_layout_selector": bool(diagnostics.get("forbidden_layout_fields")),
                "history_count": len(recent),
                "spatial_depth_requested": bool(package.get("spatial_depth_requested", explicit_spatial)),
                "spatial_depth_required": bool(package.get("spatial_depth_required", spatial_required)),
            }
        )
        package["diagnostics"] = diagnostics
        return _artifact(package)

    # The old planner calls the operation ``direct``; keeping an explicit
    # method (rather than a simple alias) gives introspection tools a useful
    # canonical entry point.
    def direct(self, *args: Any, **kwargs: Any) -> ArtifactMap:
        return self.create(*args, **kwargs)

    def build(self, *args: Any, **kwargs: Any) -> ArtifactMap:
        return self.create(*args, **kwargs)

    def repair(
        self,
        direction_package: Any,
        qa_report: Any,
        model_generate: Callable[..., Any] | None = None,
        *,
        generator: Callable[..., Any] | None = None,
        max_scenes: int | None = None,
    ) -> ArtifactMap:
        """Apply deterministic, scene-local repair directives.

        The returned package preserves narration, evidence, and unaffected
        scene briefs.  An injected generator may refine a single scene, but
        it receives only that scene and its diagnostics; it cannot regenerate
        the whole project by accident.
        """

        package = _artifact(_mapping(direction_package))
        report = _mapping(qa_report)
        instructions = _list(_pick(report, "repair_instructions", "repairs", "instructions", default=[]))
        if not instructions:
            issues = _list(_pick(report, "issues", "findings", default=[]))
            instructions = [
                _mapping(issue).get("repair", _mapping(issue))
                for issue in issues
                if _mapping(issue).get("repair") or _mapping(issue).get("scene_id")
            ]
        limit = max_scenes if max_scenes is not None else len(instructions)
        target_ids: set[str] = set()
        for item in instructions[: max(0, limit)]:
            target = _mapping(item)
            scene_id = _text(_pick(target, "scene_id", "sceneId", "id", default=""))
            if scene_id and scene_id.lower() != "project":
                target_ids.add(scene_id)
        global_instructions = [
            ArtifactMap(_artifact(_mapping(item)))
            for item in instructions
            if _text(_pick(_mapping(item), "scene_id", "sceneId", "id", default="")).lower() in {"", "project"}
        ]

        scenes = _list(_pick(package, "scenes", "scene_briefs", "sceneBriefs", default=[]))
        repaired: list[Any] = []
        failure_details: list[ArtifactMap] = []
        active_generator = generator or model_generate or self.structured_generator
        for index, scene in enumerate(scenes):
            scene_map = ArtifactMap(_artifact(_mapping(scene)))
            scene_id = _text(_pick(scene_map, "id", "scene_id", "sceneId", default=f"scene-{index + 1}"))
            relevant = [
                ArtifactMap(_artifact(_mapping(item)))
                for item in instructions
                if _text(_pick(_mapping(item), "scene_id", "sceneId", "id", default="")).lower() in {scene_id.lower(), str(index), str(index + 1)}
            ]
            if global_instructions:
                relevant = [*global_instructions, *relevant]
                target_ids.add(scene_id)
            if not relevant and target_ids and scene_id not in target_ids:
                repaired.append(scene_map)
                continue
            if not relevant and not target_ids:
                repaired.append(scene_map)
                continue
            actions: list[str] = []
            for item in relevant:
                action = _text(_pick(item, "action", "instruction", "message", "repair", default=""))
                if action:
                    actions.append(action)
            if actions:
                prior = _list(_pick(scene_map, "repair_actions", "repairActions", default=[]))
                scene_map["repair_actions"] = list(dict.fromkeys([*_map_text(prior), *actions]))
                scene_map["repair_version"] = int(_safe_float(_pick(scene_map, "repair_version", "repairVersion", default=0))) + 1
            if active_generator is not None:
                repair_context = ArtifactMap(
                    {
                        "operation": "repair_scene",
                        "scene": scene_map,
                        "instructions": relevant,
                        "qa_report": report,
                        "guard": "Return only this scene brief. Preserve truth references and narration.",
                    }
                )
                try:
                    proposed = self._call_generator(active_generator, repair_context, scene_map, relevant, [])
                    proposed_scene = _pick(proposed, "scene", "scene_brief", "brief", default=proposed)
                    if _mapping(proposed_scene):
                        merged = ArtifactMap(scene_map)
                        merged.update(_artifact(_mapping(proposed_scene)))
                        merged["id"] = scene_id
                        merged["repair_actions"] = scene_map.get("repair_actions", [])
                        scene_map = merged
                    else:
                        reason = "repair generator returned no scene mapping"
                        scene_map["repair_generator_failed"] = True
                        scene_map["repair_failure_reason"] = reason
                        failure_details.append(
                            ArtifactMap({"scene_id": scene_id, "reason": reason, "deterministic_fallback": True})
                        )
                except Exception as exc:
                    # A failed optional repair remains diagnosable and the
                    # deterministic instruction still reaches the caller.
                    reason = f"{type(exc).__name__}: {exc}"[:500]
                    scene_map["repair_generator_failed"] = True
                    scene_map["repair_failure_reason"] = reason
                    failure_details.append(
                        ArtifactMap({"scene_id": scene_id, "reason": reason, "deterministic_fallback": True})
                    )
            repaired.append(scene_map)

        package["scenes"] = repaired
        package["scene_briefs"] = repaired
        if _pick(package, "storyboard", "semantic_storyboard", "semanticStoryboard", default=None) is not None:
            storyboard_key = "semantic_storyboard" if "semantic_storyboard" in package else "storyboard"
            storyboard = ArtifactMap(_artifact(_mapping(package[storyboard_key])))
            storyboard["scenes"] = repaired
            package[storyboard_key] = storyboard
            package["semantic_storyboard"] = storyboard
            package["storyboard"] = storyboard
        package["repair_diagnostics"] = ArtifactMap(
            {
                "targeted_scene_ids": sorted(target_ids),
                "instruction_count": len(instructions),
                "full_video_regenerated": False,
                "failed_scene_ids": [str(item.get("scene_id")) for item in failure_details],
                "failures": failure_details,
                "deterministic_fallback": True,
                "actionable_message": (
                    "Repair output was not accepted for the listed scenes; preserve narration/evidence and "
                    "re-author only the failed scene contracts."
                    if failure_details
                    else ""
                ),
            }
        )
        return _artifact(package)

    @staticmethod
    def design_constitution() -> ArtifactMap:
        return ArtifactMap(
            {
                "truth": [
                    "Every factual visual and spoken claim traces to an evidence reference.",
                    "Inferences and analogies are visibly distinguishable from source facts.",
                    "Do not invent missing details to improve an image.",
                ],
                "explanation": [
                    "Each scene answers one visual question and produces one meaningful change.",
                    "The dominant visual carries the explanation; text is subordinate.",
                    "Labels remain spatially close to their referents.",
                ],
                "color_and_type": {
                    "normal_text_contrast": 4.5,
                    "large_text_contrast": 3.0,
                    "color_is_not_the_only_encoding": True,
                },
                "motion": [
                    "Motion communicates cause, change, direction, hierarchy, focus, comparison, time, or relationship.",
                    "No arbitrary floating, bouncing, pulsing, parallax, or camera drift.",
                    "Important states hold long enough to be understood.",
                ],
                "composition": [
                    "One dominant visual idea per scene.",
                    "Strong safe margins and a clear reading path.",
                    "No universal dashboard shell or repeated complete layout.",
                ],
                "performance": {
                    "declared_render_class": True,
                    "declared_estimated_cost": True,
                    "heavy_3d_requires_explanatory_justification": True,
                },
            }
        )

    def _call_generator(
        self,
        generator: Callable[..., Any],
        context: Mapping[str, Any],
        evidence: Mapping[str, Any],
        request: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        """Call a structured adapter without prescribing an SDK."""

        calls: list[Callable[[], Any]] = []
        try:
            signature = inspect.signature(generator)
            parameters = list(signature.parameters.values())
            names = {parameter.name for parameter in parameters}
            if {"evidence_pack", "request", "history"} & names:
                calls.append(lambda: generator(evidence_pack=evidence, request=request, history=history, context=context))
            elif len(parameters) >= 3:
                calls.append(lambda: generator(evidence, request, history))
            elif len(parameters) == 2:
                calls.append(lambda: generator(evidence, request))
            else:
                calls.append(lambda: generator(context))
        except (TypeError, ValueError):
            calls.append(lambda: generator(context))
        # A few adapters expose keyword-only ``payload`` or ``prompt`` forms.
        calls.extend(
            [
                lambda: generator(context=context),
                lambda: generator(payload=context),
                lambda: generator(context),
            ]
        )
        errors: list[str] = []
        seen: set[str] = set()
        for call in calls:
            try:
                result = call()
                parsed = self._parse_generation(result)
                if parsed:
                    return parsed
                errors.append("empty structured response")
            except TypeError as exc:
                signature = str(exc)
                if signature not in seen:
                    errors.append(signature[:160])
                    seen.add(signature)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                break
        raise StructuredGenerationError("; ".join(errors[-3:]) or "structured generator failed")

    @staticmethod
    def _parse_generation(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                return {}
        data = _mapping(value)
        return data if isinstance(data, Mapping) else {}

    def _fallback(
        self,
        evidence: Mapping[str, Any],
        request: Mapping[str, Any],
        claims: Sequence[Mapping[str, Any]],
        entities: Sequence[str],
        domain: str,
        history: Sequence[Mapping[str, Any]],
    ) -> ArtifactMap:
        title = _text(_pick(evidence, "title", "source_title", default="")) or _text(
            _pick(request, "title", "question", "goal", default="")
        ) or "An evidence-led explanation"
        source_seed = "|".join([title, domain, *[_text(c.get("statement")) for c in claims]])
        seed = _digest(source_seed, 24)
        used_worlds = {
            _text(_pick(item, "visual_world", "visualWorld", default=""))
            for item in history
            if _text(_pick(item, "visual_world", "visualWorld", default=""))
        }
        world_words = entities[:3] or [domain, "evidence", "change"]
        world_variants = [
            f"A {domain} field where {' / '.join(world_words)} can be observed in motion",
            f"An evidence studio that turns {' / '.join(world_words)} into visible relationships",
            f"A material landscape built from {' / '.join(world_words)} and their consequences",
        ]
        variant = int(seed[:4], 16) % len(world_variants)
        world = world_variants[variant]
        if world in used_worlds:
            world = world_variants[(variant + 1) % len(world_variants)] + "; a new vantage"
        palette = ArtifactMap(
            {
                "background": _colour(seed, 0),
                "primary_text": _colour(seed, 1),
                "secondary_text": _colour(seed, 2),
                "accent": [_colour(seed, 3), _colour(seed, 4)],
                "semantic_roles": {
                    "source_fact": _colour(seed, 5),
                    "inference": _colour(seed, 6),
                    "uncertainty": _colour(seed, 7),
                },
            }
        )
        treatment = ArtifactMap(
            {
                "id": f"treatment-{seed[:12]}",
                "genre": self._genre(domain, request, claims),
                "emotional_register": self._register(request, claims),
                "visual_world": world,
                "material_language": self._material(domain, claims),
                "palette_roles": palette,
                "typography": {
                    "category": "restrained editorial sans",
                    "hierarchy": ["question", "proof", "annotation"],
                    "character": "clear, human, and measured",
                },
                "illustration_strategy": self._illustration_strategy(domain, claims, entities),
                "motion_personality": self._motion_personality(claims),
                "camera_grammar": "purposeful reframing between evidence and consequence",
                "media_balance": {"2d": 0.72, "2_5d": 0.22, "3d_or_media": 0.06},
                "transition_logic": "carry one semantic material or directional cue into the next question",
                "anti_patterns": [
                    "completed template layouts",
                    "dashboard shells and decorative card grids",
                    "paragraphs used as the dominant visual",
                    "arbitrary floating or camera drift",
                ],
                "variation_cues": [
                    f"material cue {seed[0:3]}",
                    f"camera cue {seed[3:6]}",
                    f"rhythm cue {seed[6:9]}",
                ],
                "design_constitution": self.design_constitution(),
            }
        )

        scene_briefs: list[ArtifactMap] = []
        selected_claims = list(claims)[: self.config.maximum_scenes]
        if not selected_claims:
            selected_claims = [ArtifactMap({"id": "claim-1", "statement": title, "kind": "unknown", "source_refs": []})]
        scene_count = max(self.config.minimum_scenes, min(self.config.maximum_scenes, len(selected_claims)))
        # A single claim can still support an opening and a resolved view.  The
        # second brief asks a different viewer question without introducing a
        # canned scene layout.
        while len(selected_claims) < scene_count:
            selected_claims.append(selected_claims[-1])
        for index, claim in enumerate(selected_claims[:scene_count]):
            statement = _text(claim.get("statement"))
            shape = _semantic_shape(statement, evidence)
            scene_briefs.append(self._fallback_scene(index, claim, statement, shape, entities, domain, treatment, claims))
        storyboard = ArtifactMap(
            {
                "id": f"storyboard-{seed[:12]}",
                "central_question": _text(_pick(request, "question", "goal", "instruction", default="What should the viewer understand?")),
                "learning_outcome": _text(_pick(request, "learning_outcome", "outcome", default="Understand the source's governing relationships.")),
                "viewer_assumptions": _list(_pick(request, "viewer_assumptions", "assumptions", default=[])),
                "explanation_order": [scene["id"] for scene in scene_briefs],
                "scenes": scene_briefs,
                "continuity": "Reuse semantic entities only when their meaning continues; change construction when the question changes.",
            }
        )
        return ArtifactMap(
            {
                "version": "creative-director.v1",
                "treatment": treatment,
                "creative_treatment": treatment,
                "storyboard": storyboard,
                "semantic_storyboard": storyboard,
                "scenes": scene_briefs,
                "scene_briefs": scene_briefs,
                "source_claim_ids": [str(claim.get("id")) for claim in claims],
                "diagnostics": ArtifactMap({"fallback_seed": seed, "forbidden_layout_fields": {}}),
            }
        )

    def _fallback_scene(
        self,
        index: int,
        claim: Mapping[str, Any],
        statement: str,
        shape: str,
        entities: Sequence[str],
        domain: str,
        treatment: Mapping[str, Any],
        claims: Sequence[Mapping[str, Any]],
    ) -> ArtifactMap:
        claim_id = _text(claim.get("id"), f"claim-{index + 1}")
        scene_id = f"scene-{index + 1}-{_slug(claim_id, 'claim')}"
        words = _words(statement)
        hero = entities[index % len(entities)] if entities else domain
        supporting = [item for item in entities if item != hero][:4]
        if not supporting:
            supporting = ["evidence", "consequence"]
        if shape == "sequence":
            visual_question = f"What changes first, and what follows for {hero}?"
            change = "Reveal the causal order, then carry the consequence into the next state."
            representation = "a staged causal transformation with visible intermediate states"
            actions = ["stage", "connect", "transform"]
        elif shape == "comparison":
            visual_question = f"What materially differs around {hero}?"
            change = "Place the governing difference in view, then make its consequence legible."
            representation = "a parallel state contrast with a shared semantic anchor"
            actions = ["separate", "measure", "reframe"]
        elif shape == "quantity":
            visual_question = f"How much does the evidence change the picture of {hero}?"
            change = "Make the quantity's scale visible and connect it to the stated meaning."
            representation = "a proportional measurement whose scale is read before its label"
            actions = ["count", "grow", "highlight"]
        elif shape == "causal":
            visual_question = f"Which relationship makes {hero} matter?"
            change = "Trace one governing relationship from cause to visible result."
            representation = "an object-led relationship field with explicit directional anchors"
            actions = ["trace", "link", "resolve"]
        else:
            visual_question = f"What should a beginner notice about {hero}?"
            change = "Move from the concrete subject to the implication the narration names."
            representation = "a content-specific physical metaphor with labeled semantic anchors"
            actions = ["introduce", "focus", "reveal"]
        duration = max(2.6, min(14.0, 0.36 * max(8, len(words))))
        visible_text = _first_sentence(statement, 92)
        return ArtifactMap(
            {
                "id": scene_id,
                "index": index,
                "viewer_question": visual_question,
                "purpose": visual_question,
                "intended_understanding": _first_sentence(statement, 180),
                "claims": [claim_id],
                "evidence_refs": [claim_id],
                "truth_references": [claim_id],
                "narration": statement,
                "semantic_timings": _normalise_timing([], duration, statement, actions),
                "duration_seconds": round(duration, 3),
                "visible_entities": [hero, *supporting],
                "visible_relationships": [
                    f"{hero} is grounded in the source claim",
                    f"the stated {shape} changes the viewer's model",
                ],
                "required_change": change,
                "representation": representation,
                "why_representation": "It shows the claim's governing relationship without relying on a paragraph of text.",
                "composition_intent": {
                    "dominant_idea": hero,
                    "reading_path": "hero → evidence cue → consequence",
                    "safe_margin": "open margins around the explanatory field",
                    "hierarchy": ["dominant visual", "semantic relation", "short annotation"],
                    "spatial_relationships": "derive positions from the relationship, not a reusable layout",
                },
                "visual_anchors": [
                    {"id": f"anchor-{index + 1}-hero", "role": "hero", "meaning": hero},
                    {"id": f"anchor-{index + 1}-evidence", "role": "evidence", "meaning": "source-grounded claim"},
                ],
                "motion_events": [
                    {"id": f"motion-{index + 1}-1", "action": action, "purpose": f"Make {shape} legible", "anchor": f"anchor-{index + 1}-hero"}
                    for action in actions
                ],
                "motion_purpose": f"Use {', '.join(actions)} to communicate the claim's {shape} relationship.",
                "text_budget": {"visible_words": min(18, len(_words(visible_text))), "visible_chars": min(120, len(visible_text))},
                "visible_text": visible_text,
                "render_class": "motion-island" if len(actions) > 1 else "static-editorial",
                "estimated_cost": round(8.0 + 1.5 * len(actions) + 0.4 * len(supporting), 2),
                "continuity": {"from_previous": "carry only entities whose meaning persists", "to_next": "leave a semantic cue, not a repeated layout"},
                "anti_patterns": list(_list(_pick(treatment, "anti_patterns", default=[]))),
            }
        )

    def _merge_generated(
        self,
        generated: Mapping[str, Any],
        fallback: Mapping[str, Any],
        evidence: Mapping[str, Any],
        request: Mapping[str, Any],
        claims: Sequence[Mapping[str, Any]],
        entities: Sequence[str],
        domain: str,
    ) -> ArtifactMap:
        generated_data = _mapping(generated)
        fallback_treatment = ArtifactMap(_artifact(_mapping(_pick(fallback, "treatment", "creative_treatment", default={}))))
        raw_treatment = _pick(generated_data, "treatment", "creative_treatment", "creativeTreatment", "direction", default={})
        treatment = ArtifactMap(fallback_treatment)
        if _mapping(raw_treatment):
            treatment.update(_artifact(_mapping(raw_treatment)))
        forbidden_treatment = _forbidden_layout_fields(_mapping(raw_treatment))
        if forbidden_treatment:
            treatment.pop("template", None)
            treatment.pop("template_id", None)
            treatment.pop("layout", None)
            treatment["rejected_layout_fields"] = sorted(forbidden_treatment)

        explicit_spatial = bool(_pick(request, "spatial_depth_requested", "spatialDepthRequested", default=False))
        source_text = json.dumps(evidence, ensure_ascii=False, default=str)
        spatial_required = bool(_pick(request, "spatial_depth_required", "spatialDepthRequired", default=False)) or bool(explicit_spatial and _spatial_depth_terms(source_text))
        raw_scenes = _pick(generated_data, "scenes", "scene_briefs", "sceneBriefs", default=None)
        raw_storyboard = _pick(generated_data, "storyboard", "semantic_storyboard", "semanticStoryboard", default={})
        if raw_scenes is None:
            raw_scenes = _pick(_mapping(raw_storyboard), "scenes", "scene_briefs", "sceneBriefs", default=[])
        fallback_scenes = _list(_pick(fallback, "scenes", "scene_briefs", default=[]))
        scenes: list[ArtifactMap] = []
        for index, raw_scene in enumerate(_list(raw_scenes)):
            base = ArtifactMap(_artifact(_mapping(fallback_scenes[index] if index < len(fallback_scenes) else {})))
            raw_data = _mapping(raw_scene)
            if raw_data:
                base.update(_artifact(raw_data))
                # A generated alias must override a fallback canonical key.
                alias_groups = {
                    "duration_seconds": {"duration_seconds", "durationSeconds", "duration_in_seconds", "durationInSeconds", "duration", "length", "seconds"},
                    "semantic_timings": {"semantic_timings", "semanticTimings", "narration_anchors", "narrationAnchors", "narration_timing", "narrationTiming", "timings", "timing", "beats"},
                    "render_class": {"render_class", "renderClass", "renderer", "render_mode"},
                }
                for canonical, aliases in alias_groups.items():
                    if any(key in raw_data for key in aliases):
                        base.pop(canonical, None)
            scenes.append(self._normalise_generated_scene(base, index, claims, entities, domain, treatment))
        if not scenes:
            scenes = [ArtifactMap(_artifact(_mapping(scene))) for scene in fallback_scenes]
        if len(scenes) > self.config.maximum_scenes:
            scenes = scenes[: self.config.maximum_scenes]
        storyboard = ArtifactMap(_artifact(_mapping(_pick(fallback, "storyboard", "semantic_storyboard", default={}))))
        if _mapping(raw_storyboard):
            storyboard.update(_artifact(_mapping(raw_storyboard)))
        storyboard["scenes"] = scenes
        storyboard.setdefault("explanation_order", [scene.get("id") for scene in scenes])
        seed = _digest([treatment, [scene.get("id") for scene in scenes]], 24)
        diagnostics = ArtifactMap(
            {
                "fallback_seed": _pick(_mapping(_pick(fallback, "diagnostics", default={})), "fallback_seed", default=""),
                "forbidden_layout_fields": {**forbidden_treatment, **{str(key): value for key, value in _forbidden_layout_fields(generated_data).items()}},
                "generated_keys": sorted(str(key) for key in generated_data),
                "package_seed": seed,
                "spatial_depth_requested": explicit_spatial,
                "spatial_depth_required": spatial_required,
            }
        )
        return ArtifactMap(
            {
                "version": "creative-director.v1",
                "treatment": treatment,
                "creative_treatment": treatment,
                "storyboard": storyboard,
                "semantic_storyboard": storyboard,
                "scenes": scenes,
                "scene_briefs": scenes,
                "source_claim_ids": [str(claim.get("id")) for claim in claims],
                "spatial_depth_requested": explicit_spatial,
                "spatial_depth_required": spatial_required,
                "diagnostics": diagnostics,
            }
        )

    def _normalise_generated_scene(
        self,
        scene: Mapping[str, Any],
        index: int,
        claims: Sequence[Mapping[str, Any]],
        entities: Sequence[str],
        domain: str,
        treatment: Mapping[str, Any],
    ) -> ArtifactMap:
        data = ArtifactMap(_artifact(scene))
        claim_ids = [str(claim.get("id")) for claim in claims]
        scene_id = _text(_pick(data, "id", "scene_id", "sceneId", default=f"scene-{index + 1}")) or f"scene-{index + 1}"
        statement = _text(_pick(data, "narration", "spoken_text", "voiceover", "body", "text", default=""))
        if not statement and claims:
            statement = _text(claims[index % len(claims)].get("statement"))
        actions = [_text(item) for item in _list(_pick(data, "motion_events", "actions", "motionActions", default=[])) if _text(item)]
        action_names: list[str] = []
        for action in actions:
            action_data = _mapping(action)
            action_names.append(_text(_pick(action_data, "action", "verb", "name", default=action)) or "reveal")
        if not action_names:
            action_names = ["reveal"]
        duration = _normalise_duration(data, statement, minimum=2.5, maximum=24.0)
        refs = [_text(item) for item in _list(_pick(data, "evidence_refs", "truth_references", "claims", "claim_ids", "claimIds", default=[])) if _text(item)]
        refs = list(dict.fromkeys(refs)) or claim_ids[:1]
        visible_entities = [_text(item) for item in _list(_pick(data, "visible_entities", "entities", "visual_entities", default=[])) if _text(item)]
        visible_entities = list(dict.fromkeys(visible_entities or list(entities)[:4] or [domain]))
        forbidden = _forbidden_layout_fields(data)
        for key in forbidden:
            data.pop(key, None)
        data.update(
            {
                "id": scene_id,
                "index": index,
                "viewer_question": _text(_pick(data, "viewer_question", "question", "purpose", default=f"What should the viewer understand about {visible_entities[0]}?")),
                "purpose": _text(_pick(data, "purpose", "viewer_question", "question", default="Understand the source-grounded change.")),
                "intended_understanding": _text(_pick(data, "intended_understanding", "understanding", "takeaway", default=_first_sentence(statement, 180))),
                "evidence_refs": refs,
                "truth_references": refs,
                "narration": statement,
                "duration_seconds": round(duration, 3),
                "semantic_timings": _normalise_timing(
                    _pick(data, "semantic_timings", "semanticTimings", "narration_anchors", "narrationAnchors", "narration_timing", "narrationTiming", "timings", "timing", "beats", default=[]),
                    duration,
                    statement,
                    action_names,
                ),
                "visible_entities": visible_entities,
                "motion_purpose": _text(_pick(data, "motion_purpose", "motionPurpose", default=f"Make the scene's governing relationship visible through {', '.join(action_names)}.")),
                "motion_events": [
                    _artifact(action) if _mapping(action) else ArtifactMap({"action": _text(action), "purpose": "Support the stated scene change."})
                    for action in _list(_pick(data, "motion_events", "actions", "motionActions", default=action_names))
                ],
                "render_class": _normalise_render_class(_pick(data, "render_class", "renderClass", "renderer", "render_mode", default="motion-island")),
                "estimated_cost": _safe_float(_pick(data, "estimated_cost", "estimatedCost", "cost", default=10.0), 10.0),
                "anti_patterns": list(_list(_pick(treatment, "anti_patterns", default=[]))),
            }
        )
        data["composition_intent"] = ArtifactMap(
            _mapping(_pick(data, "composition_intent", "composition", "spatial_intent", default={}))
            or {
                "dominant_idea": visible_entities[0],
                "reading_path": "semantic anchor → relationship → consequence",
                "spatial_relationships": "author from meaning; no fixed layout selector",
            }
        )
        if forbidden:
            data["rejected_layout_fields"] = sorted(forbidden)
        return data

    @staticmethod
    def _genre(domain: str, request: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]) -> str:
        explicit = _text(_pick(request, "genre", "visual_genre", "style", default=""))
        if explicit:
            return explicit
        if domain in {"security", "history"}:
            return "forensic visual essay"
        if domain in {"science", "health"}:
            return "observational field guide"
        if any(_contains(claim.get("statement"), "compare", "versus", "difference") for claim in claims):
            return "comparative visual argument"
        return "evidence-led explanatory film"

    @staticmethod
    def _register(request: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]) -> str:
        tone = _text(_pick(request, "tone", "mood", "emotional_register", default=""))
        if tone:
            return tone
        if any(_contains(claim.get("statement"), "risk", "failure", "warning", "danger") for claim in claims):
            return "alert but composed"
        return "curious, clear, and grounded"

    @staticmethod
    def _material(domain: str, claims: Sequence[Mapping[str, Any]]) -> str:
        if domain == "science":
            return "measured marks, translucent layers, and instrument-like annotation"
        if domain == "technology":
            return "signal traces, modular surfaces, and deliberate connection lines"
        if domain == "security":
            return "paper evidence, redaction marks, and directional route traces"
        if domain == "history":
            return "archival fibers, dated marks, and tactile document edges"
        if any(_contains(claim.get("statement"), "people", "community", "story") for claim in claims):
            return "human-scale objects, warm fields, and hand-placed markers"
        return "solid material fields with one restrained accent and visible provenance marks"

    @staticmethod
    def _illustration_strategy(domain: str, claims: Sequence[Mapping[str, Any]], entities: Sequence[str]) -> str:
        if domain in {"science", "health"}:
            return "show the system as a simplified explanatory cutaway; label uncertainty rather than inventing detail"
        if domain in {"technology", "security"}:
            return "turn entities into tangible modules and traces; make boundaries and direction explicit"
        if any(_contains(claim.get("statement"), "number", "%", "percent", "rate") for claim in claims):
            return "translate quantities into proportional marks with a visible reference scale"
        return f"use concrete forms for {', '.join(entities[:3]) or 'the governing subject'} and let relationships determine composition"

    @staticmethod
    def _motion_personality(claims: Sequence[Mapping[str, Any]]) -> str:
        if any(_contains(claim.get("statement"), "process", "then", "next", "step") for claim in claims):
            return "staged cause-and-effect with clear holds between states"
        if any(_contains(claim.get("statement"), "compare", "versus", "difference") for claim in claims):
            return "measured separation and convergence for comparison"
        return "quiet reveal, focus shift, and consequence carried forward"


def _map_text(values: Sequence[Any]) -> list[str]:
    return [_text(value) for value in values if _text(value)]


__all__ = [
    "ArtifactMap",
    "DirectorConfig",
    "StructuredGenerationError",
    "StructuredGenerator",
    "VisualDirector",
]


