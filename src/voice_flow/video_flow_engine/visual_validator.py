"""Pure deterministic validation for compiled Video Flow Visual V2 output."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .scene_compiler_v2 import CompiledVisualProgramV21, CompiledVisualV2
from .style_engine_v2 import contrast_ratio
from .visual_plan_v2 import TRANSITIONS


_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_PATH = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9 ,.\-+eE]*$")
_UNSAFE_MARKUP = re.compile(r'<\s*(?:script|iframe|object|embed|form|frame|frameset|meta|link|base|video|audio|source|track)\b|javascript:|\bon[a-z]+\s*=', re.IGNORECASE)
_ATTRIBUTE = re.compile(r"\b(?P<name>data-(?:delay|count))\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))", re.IGNORECASE)
_PATH_ATTRIBUTE = re.compile(r"\bd\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)')", re.IGNORECASE)
_THREE_TYPES = frozenset({"cube", "sphere", "cylinder", "plane", "torus", "cone", "ring", "icosahedron", "dodecahedron", "octahedron", "tetrahedron", "torusKnot", "model", "group", "particles"})
_LIGHT_TYPES = frozenset({"ambient", "directional", "point", "spot", "hemisphere"})
_ANIMATE_PROPERTIES = frozenset({"position.x", "position.y", "position.z", "rotation.x", "rotation.y", "rotation.z", "scale.x", "scale.y", "scale.z", "scale", "opacity"})
_THREE_EASES = frozenset({"none", "linear", "power1.in", "power1.out", "power1.inOut", "power2.in", "power2.out", "power2.inOut", "power3.in", "power3.out", "power3.inOut", "sine.in", "sine.out", "sine.inOut", "back.out", "expo.out", "expo.inOut", "elastic.out"})


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    scene_id: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "scene_id": self.scene_id, "message": self.message}


@dataclass(frozen=True)
class VisualValidationReport:
    valid: bool
    findings: tuple[ValidationFinding, ...]
    metrics: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "findings": [item.to_dict() for item in self.findings],
            "metrics": {key: self.metrics[key] for key in sorted(self.metrics)},
        }


class VisualValidationV2Error(ValueError):
    """Typed validation failure carrying the complete deterministic report."""

    def __init__(self, report: VisualValidationReport) -> None:
        super().__init__("Compiled Visual V2 failed deterministic validation")
        self.report = report


def validate_compiled_visual_v2(compiled: CompiledVisualV2) -> VisualValidationReport:
    """Validate a compiler-owned production without rendering or external I/O."""
    findings: list[ValidationFinding] = []
    if isinstance(compiled, CompiledVisualProgramV21):
        return validate_compiled_visual_program_v21(compiled)
    if not isinstance(compiled, CompiledVisualV2):
        report = _report(findings + [_finding("invalid_compiled_type", "", "Expected CompiledVisualV2")], 0, 0, 0, 0)
        raise VisualValidationV2Error(report)

    production = compiled.production
    scene_ir = compiled.scene_ir
    if not isinstance(production, Mapping):
        report = _report([_finding("invalid_production", "", "Production must be an object")], 0, 0, 0, 0)
        raise VisualValidationV2Error(report)
    _validate_envelope(production, findings)
    _validate_tokens(compiled, findings)

    production_scenes = production.get("scenes")
    scenes = production_scenes if isinstance(production_scenes, list) else []
    ir_scenes = tuple(getattr(scene_ir, "scenes", ()))
    if not ir_scenes:
        findings.append(_finding("empty_video", "", "Scene IR contains no scenes"))
    if len(scenes) != len(ir_scenes):
        findings.append(_finding("scene_count_mismatch", "", "Production and Scene IR scene counts differ"))

    local_objects = 0
    relationships = 0
    checked = min(len(scenes), len(ir_scenes))
    seen_ids: set[str] = set()
    for index in range(checked):
        scene = scenes[index]
        ir_scene = ir_scenes[index]
        scene_id = getattr(ir_scene, "scene_id", "")
        if not isinstance(scene, Mapping):
            findings.append(_finding("invalid_scene", scene_id, "Production scene must be an object"))
            continue
        _validate_scene(
            scene,
            ir_scene,
            getattr(scene_ir, "width", None),
            getattr(scene_ir, "height", None),
            getattr(scene_ir, "caption_safe_bottom", None),
            findings,
            seen_ids,
        )
        local_objects += sum(not item.carried for item in ir_scene.objects)
        relationships += len(ir_scene.relationships)

    for ir_scene in ir_scenes[checked:]:
        findings.append(_finding("missing_production_scene", ir_scene.scene_id, "Scene IR has no production scene"))
    for index in range(checked, len(scenes)):
        findings.append(_finding("extra_production_scene", "", f"Production has unexpected scene at index {index}"))

    report = _report(findings, len(ir_scenes), len(scenes), local_objects, relationships)
    if not report.valid:
        raise VisualValidationV2Error(report)
    return report


def _validate_envelope(production: Mapping[str, Any], findings: list[ValidationFinding]) -> None:
    if not isinstance(production.get("title"), str) or not production["title"].strip():
        findings.append(_finding("invalid_title", "", "Production title must be non-empty text"))
    if production.get("size") != "16:9":
        findings.append(_finding("invalid_size", "", "Production size must be 16:9"))
    if production.get("renderer") != "hyperframes":
        findings.append(_finding("invalid_renderer", "", "V2 production must use HyperFrames"))
    if production.get("safeLayout") is not True or production.get("chrome") is not False:
        findings.append(_finding("invalid_safety_envelope", "", "safeLayout and chrome production controls are invalid"))
    captions = production.get("captions")
    if not isinstance(captions, Mapping) or captions.get("preset") != "rise":
        findings.append(_finding("invalid_captions", "", "V2 captions must preserve the rise preset"))
    voices = production.get("voices")
    narrator = voices.get("narrator") if isinstance(voices, Mapping) else None
    if not isinstance(narrator, Mapping) or narrator.get("backend") != "voiceflow" or not str(narrator.get("speaker") or "").strip():
        findings.append(_finding("invalid_narrator", "", "V2 narration provider configuration is invalid"))
    theme = production.get("theme")
    if not isinstance(theme, Mapping) or not _is_hex(theme.get("bg")) or not _is_hex(theme.get("accent")):
        findings.append(_finding("invalid_theme", "", "V2 production theme requires valid concrete colours"))
    if not isinstance(production.get("timing"), Mapping):
        findings.append(_finding("invalid_timing", "", "V2 production timing must be an object"))
    if not isinstance(production.get("scenes"), list):
        findings.append(_finding("invalid_scenes", "", "V2 production scenes must be a list"))


def _validate_tokens(compiled: CompiledVisualV2, findings: list[ValidationFinding]) -> None:
    tokens = compiled.design_tokens
    values = {
        name: getattr(tokens, name, None)
        for name in ("background", "foreground", "muted", "accent", "secondary", "emphasis", "surface", "edge")
    }
    for name, value in values.items():
        if not _is_hex(value):
            findings.append(_finding("invalid_token_colour", "", f"Resolved {name} is not a #RRGGBB colour"))
    if not _is_hex(values["foreground"]) or not _is_hex(values["background"]) or not _is_hex(values["surface"]):
        return
    if contrast_ratio(values["foreground"], values["background"]) < 4.5:
        findings.append(_finding("low_background_contrast", "", "Foreground contrast against background is below 4.5"))
    if contrast_ratio(values["foreground"], values["surface"]) < 4.5:
        findings.append(_finding("low_surface_contrast", "", "Foreground contrast against surface is below 4.5"))


def _validate_scene(
    scene: Mapping[str, Any],
    ir_scene: Any,
    width: Any,
    height: Any,
    caption_safe_bottom: Any,
    findings: list[ValidationFinding],
    seen_ids: set[str],
) -> None:
    scene_id = str(getattr(ir_scene, "scene_id", ""))
    if scene.get("id") != scene_id or not scene_id:
        findings.append(_finding("scene_id_mismatch", scene_id, "Production scene ID does not match Scene IR"))
    if scene_id in seen_ids:
        findings.append(_finding("duplicate_scene_id", scene_id, "Scene ID appears more than once"))
    seen_ids.add(scene_id)
    transition = scene.get("transition")
    if transition not in TRANSITIONS:
        findings.append(_finding("invalid_transition", scene_id, "Scene transition is unsupported"))
    body = scene.get("body")
    if not isinstance(body, str) or not body.strip():
        findings.append(_finding("empty_body", scene_id, "Scene body is empty"))
    else:
        _validate_markup(body, scene_id, findings)
    narration = _narration(scene)
    if not narration:
        findings.append(_finding("empty_narration", scene_id, "Scene narration is empty"))

    objects = tuple(getattr(ir_scene, "objects", ()))
    if not objects:
        findings.append(_finding("empty_scene", scene_id, "Scene contains no visual objects"))
        return
    _validate_objects(objects, ir_scene, scene_id, width, height, caption_safe_bottom, findings)
    _validate_three(scene.get("three"), scene_id, findings)


def _validate_markup(body: str, scene_id: str, findings: list[ValidationFinding]) -> None:
    if _UNSAFE_MARKUP.search(body):
        findings.append(_finding("unsafe_markup", scene_id, "Scene contains unsafe markup, event handlers, or remote URLs"))
    for match in _PATH_ATTRIBUTE.finditer(body):
        path = match.group("double") if match.group("double") is not None else match.group("single")
        if not path or not _PATH.fullmatch(path):
            findings.append(_finding("invalid_svg_path", scene_id, "SVG path data is invalid"))
    for match in _ATTRIBUTE.finditer(body):
        value = next(group for group in (match.group("double"), match.group("single"), match.group("bare")) if group is not None)
        if not _finite_attribute_number(value):
            findings.append(_finding("invalid_animation_number", scene_id, f"{match.group('name')} must be finite"))


def _validate_objects(
    objects: tuple[Any, ...],
    ir_scene: Any,
    scene_id: str,
    width: Any,
    height: Any,
    caption_safe_bottom: Any,
    findings: list[ValidationFinding],
) -> None:
    object_ids: set[str] = set()
    local = []
    for item in objects:
        object_id = str(getattr(item, "id", ""))
        if not object_id or object_id in object_ids:
            findings.append(_finding("duplicate_object_id", scene_id, "Scene object IDs must be unique"))
        object_ids.add(object_id)
        box = getattr(item, "box", None)
        if not _valid_box(box, width, height, caption_safe_bottom):
            findings.append(_finding("invalid_box", scene_id, f"Object {object_id or '?'} is off-frame or overlaps captions"))
        else:
            _label_fit(item, scene_id, findings)
        if not getattr(item, "carried", False):
            local.append(item)
    for index, first in enumerate(local):
        for second in local[index + 1 :]:
            if _overlaps(first.box, second.box):
                findings.append(_finding("local_overlap", scene_id, "Local visual object boxes overlap"))
    for relationship in tuple(getattr(ir_scene, "relationships", ())):
        if getattr(relationship, "source", None) not in object_ids or getattr(relationship, "target", None) not in object_ids:
            findings.append(_finding("invalid_relationship_reference", scene_id, "Relationship references an unavailable object"))
    for beat in tuple(getattr(ir_scene, "beats", ())):
        if getattr(beat, "object_id", None) not in object_ids:
            findings.append(_finding("invalid_beat_reference", scene_id, "Animation beat references an unavailable object"))


def _validate_three(value: Any, scene_id: str, findings: list[ValidationFinding]) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping) or set(value) - {"camera", "objects", "lights", "background", "toneMapping", "cameraAnimate"}:
        findings.append(_finding("invalid_three", scene_id, "Three configuration uses unsupported keys"))
        return
    camera = value.get("camera")
    if (
        not isinstance(camera, Mapping)
        or set(camera) - {"position", "lookAt", "fov", "near", "far"}
        or not _vector(camera.get("position"), 3)
        or not _vector(camera.get("lookAt"), 3)
        or not all(_finite_number(camera.get(key)) for key in ("fov", "near", "far"))
        or float(camera.get("near")) <= 0
        or float(camera.get("far")) <= float(camera.get("near"))
    ):
        findings.append(_finding("invalid_three_camera", scene_id, "Three camera is not whitelisted"))
    objects = value.get("objects", [])
    if not isinstance(objects, list) or len(objects) > 12:
        findings.append(_finding("invalid_three_objects", scene_id, "Three objects must be a list of at most 12 items"))
    elif any(not _valid_three_object(item) for item in objects):
        findings.append(_finding("invalid_three_object", scene_id, "Three object configuration is not whitelisted"))
    camera_animations = value.get("cameraAnimate", [])
    if not isinstance(camera_animations, list) or len(camera_animations) > 24 or any(not _valid_camera_animate(item) for item in camera_animations):
        findings.append(_finding("invalid_three_camera_animation", scene_id, "Three camera animations are not whitelisted"))
    lights = value.get("lights", [])
    if not isinstance(lights, list) or any(not _valid_light(item) for item in lights):
        findings.append(_finding("invalid_three_lights", scene_id, "Three light configuration is not whitelisted"))


def _valid_three_object(value: Any) -> bool:
    allowed = {
        "id", "type", "radius", "size", "position", "color", "roughness", "metalness",
        "clearcoat", "clearcoatRoughness", "transmission", "ior", "thickness",
        "castShadow", "rotateDuration", "animate", "children", "count", "spread",
        "animated", "emissive", "emissiveIntensity",
    }
    if not isinstance(value, Mapping) or set(value) - allowed or value.get("type") not in _THREE_TYPES:
        return False
    for key in ("radius", "roughness", "metalness", "clearcoat", "clearcoatRoughness", "transmission", "ior", "thickness", "rotateDuration", "count"):
        if key in value and not _finite_number(value[key]):
            return False
    if "position" in value and not _vector(value["position"], 3):
        return False
    if "spread" in value and not _vector(value["spread"], 3):
        return False
    if "radius" in value and (not _finite_number(value["radius"]) or float(value["radius"]) <= 0):
        return False
    if "scale" in value and not (isinstance(value["scale"], (int, float)) or _vector(value["scale"], 3)):
        return False
    if "size" in value and not (_finite_number(value["size"]) or _vector(value["size"], 3)):
        return False
    if "animated" in value and type(value["animated"]) is not bool:
        return False
    children = value.get("children", [])
    if not isinstance(children, list) or len(children) > 64 or any(not _valid_three_object(item) for item in children):
        return False
    if "color" in value and not _is_hex(value["color"]):
        return False
    if "emissive" in value and not _is_hex(value["emissive"]):
        return False
    if "emissiveIntensity" in value and (not _finite_number(value["emissiveIntensity"]) or float(value["emissiveIntensity"]) < 0):
        return False
    if value.get("type") == "group":
        if any(str(child.get("type")) in {"group", "model", "particles"} for child in children if isinstance(child, Mapping)):
            return False
    animate = value.get("animate")
    if animate is None:
        return True
    if isinstance(animate, list):
        return len(animate) <= 64 and all(_valid_animate(item) for item in animate)
    return _valid_animate(animate)


def _valid_light(value: Any) -> bool:
    allowed = {"type", "position", "intensity", "shadow", "color", "groundColor"}
    if not isinstance(value, Mapping) or set(value) - allowed or value.get("type") not in _LIGHT_TYPES:
        return False
    if "position" in value and not _vector(value["position"], 3):
        return False
    if "intensity" in value and not _finite_number(value["intensity"]):
        return False
    if "shadow" in value and type(value["shadow"]) is not bool:
        return False
    for key in ("color", "groundColor"):
        if key in value and not _is_hex(value[key]):
            return False
    return True


def _valid_camera_animate(value: Any) -> bool:
    allowed_properties = frozenset({"position.x", "position.y", "position.z", "lookAt.x", "lookAt.y", "lookAt.z", "fov"})
    allowed = {"property", "from", "to", "by", "duration", "ease", "at", "wait"}
    if not isinstance(value, Mapping) or set(value) - allowed or value.get("property") not in allowed_properties:
        return False
    if not _finite_number(value.get("duration")) or float(value["duration"]) <= 0:
        return False
    for key in ("from", "to", "by"):
        if key in value and not _finite_number(value[key]):
            return False
    if "to" not in value and "by" not in value:
        return False
    if "ease" in value and value["ease"] not in _THREE_EASES:
        return False
    at = value.get("at")
    return at is None or (isinstance(at, Mapping) and set(at) <= {"cue", "offset"} and isinstance(at.get("cue"), int) and at["cue"] >= 0 and ("offset" not in at or _finite_number(at["offset"])))


def _valid_animate(value: Any) -> bool:
    allowed = {"property", "from", "to", "duration", "at", "ease", "semantic", "center", "radius", "loop"}
    if not isinstance(value, Mapping) or set(value) - allowed or value.get("property") not in _ANIMATE_PROPERTIES:
        return False
    if not all(_finite_number(value.get(key)) for key in ("from", "to", "duration")) or float(value["duration"]) <= 0:
        return False
    if "center" in value and not _vector(value["center"], 3):
        return False
    if "radius" in value and (not _finite_number(value["radius"]) or float(value["radius"]) <= 0):
        return False
    if "loop" in value and type(value["loop"]) is not bool:
        return False
    if "ease" in value and value["ease"] not in _THREE_EASES:
        return False
    at = value.get("at")
    return at is None or (
        isinstance(at, Mapping)
        and set(at) <= {"cue", "offset"}
        and "cue" in at
        and isinstance(at["cue"], int)
        and at["cue"] >= 0
        and ("offset" not in at or _finite_number(at["offset"]))
    )


def _narration(scene: Mapping[str, Any]) -> str:
    voice = scene.get("vo")
    if not isinstance(voice, list) or not voice or not isinstance(voice[0], Mapping):
        return ""
    return str(voice[0].get("text") or "").strip()


def _valid_box(box: Any, width: Any, height: Any, caption_safe_bottom: Any) -> bool:
    if not all(type(value) is int for value in (width, height, caption_safe_bottom)):
        return False
    if box is None or not all(type(getattr(box, name, None)) is int for name in ("x", "y", "width", "height")):
        return False
    return box.width > 0 and box.height > 0 and box.x >= 0 and box.y >= 0 and box.right <= width and box.bottom <= height - caption_safe_bottom


def _label_fit(item: Any, scene_id: str, findings: list[ValidationFinding]) -> None:
    label = str(getattr(item, "label", ""))
    box = item.box
    capacity = max(1, box.width // 14) * max(1, box.height // 36)
    if len(label) > capacity:
        findings.append(_finding("warning_label_may_overflow", scene_id, f"Label for {item.id!r} may not fit its box"))


def _overlaps(first: Any, second: Any) -> bool:
    return first.x < second.right and second.x < first.right and first.y < second.bottom and second.y < first.bottom


def _finite_attribute_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False

def _vector(value: Any, length: int) -> bool:
    return isinstance(value, list) and len(value) == length and all(_finite_number(item) for item in value)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_hex(value: Any) -> bool:
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _finding(code: str, scene_id: str, message: str) -> ValidationFinding:
    return ValidationFinding(code=code, scene_id=scene_id, message=message)


def _report(findings: list[ValidationFinding], scene_count: int, production_scene_count: int, local_objects: int, relationships: int) -> VisualValidationReport:
    ordered = tuple(sorted(findings, key=lambda item: (item.scene_id, item.code, item.message)))
    errors = sum(not item.code.startswith("warning_") for item in ordered)
    warnings = len(ordered) - errors
    return VisualValidationReport(
        valid=errors == 0,
        findings=ordered,
        metrics={
            "error_count": errors,
            "finding_count": len(ordered),
            "local_object_count": local_objects,
            "production_scene_count": production_scene_count,
            "relationship_count": relationships,
            "scene_count": scene_count,
            "warning_count": warnings,
        },
    )


# ---------------------------------------------------------------------------
# V2.1 Gate A/B validation


class VisualValidationV21Error(ValueError):
    """Typed failure for V2.1 capability or deterministic render QA."""

    def __init__(self, report: VisualValidationReport) -> None:
        super().__init__("Visual V2.1 failed deterministic validation")
        self.report = report


def validate_visual_program_v21(program: Any, storyboard: Any = None) -> VisualValidationReport:
    """Gate A: validate capability references before trusted compilation."""

    from .representation_resolver import resolve_representation
    from .visual_capabilities import VISUAL_CAPABILITIES
    from .visual_program_v21 import VideoVisualProgramV21, parse_video_visual_program_v21

    findings: list[ValidationFinding] = []
    try:
        parsed = program if isinstance(program, VideoVisualProgramV21) else parse_video_visual_program_v21(program, storyboard=storyboard)
        for scene in parsed.scenes:
            subject_ids = set(scene.all_subject_ids())
            for relation in scene.relationships:
                VISUAL_CAPABILITIES.require(relation.kind, kind="relationship")
                if relation.source not in subject_ids or relation.target not in subject_ids:
                    findings.append(_finding("invalid_relationship_reference", scene.scene_id, "Relationship references an unavailable subject"))
            for event in scene.events:
                VISUAL_CAPABILITIES.require(event.event_type, kind="event")
                refs = [event.subject, event.source, event.destination, event.target, event.carrier, event.center, *event.parts, *event.targets]
                if any(value is not None and value not in subject_ids for value in refs):
                    findings.append(_finding("invalid_event_reference", scene.scene_id, "Event references an unavailable subject"))
            for subject in scene.subjects:
                try:
                    family = "atmospheric_system" if subject.structural_family == "particle_system" else subject.structural_family
                    resolve_representation(subject.to_dict(), family=family, representation_strategy="|".join(scene.representation_strategy), renderer=subject.render_strategy, events=[event.to_dict() for event in scene.events])
                except Exception as exc:
                    findings.append(_finding("unsupported_representation", scene.scene_id, str(exc)[:200]))
        report = _report(findings, len(parsed.scenes), len(parsed.scenes), 0, sum(len(scene.relationships) for scene in parsed.scenes))
    except Exception as exc:
        report = _report([_finding("capability_validation", "", str(exc)[:240])], 0, 0, 0, 0)
    if not report.valid:
        raise VisualValidationV21Error(report)
    return report


def validate_compiled_visual_program_v21(compiled: Any) -> VisualValidationReport:
    """Gate B: deterministic geometry, contrast, safe markup, and motion QA."""

    findings: list[ValidationFinding] = []
    if not isinstance(compiled, CompiledVisualProgramV21):
        report = _report([_finding("invalid_compiled_type", "", "Expected CompiledVisualProgramV21")], 0, 0, 0, 0)
        raise VisualValidationV21Error(report)
    production = compiled.production
    if not isinstance(production, Mapping):
        report = _report([_finding("invalid_production", "", "Production must be an object")], 0, 0, 0, 0)
        raise VisualValidationV21Error(report)
    _validate_envelope(production, findings)
    tokens = compiled.design_tokens
    for foreground, background, code in (
        (getattr(tokens, "foreground", ""), getattr(tokens, "background", ""), "local_contrast"),
        (getattr(tokens, "foreground", ""), getattr(tokens, "surface", ""), "local_contrast"),
        (getattr(tokens, "accent", ""), getattr(tokens, "surface", ""), "local_contrast"),
        (getattr(tokens, "secondary", ""), getattr(tokens, "surface", ""), "local_contrast"),
    ):
        try:
            if contrast_ratio(foreground, background) < 4.5:
                findings.append(_finding(code, "", "Resolved local foreground/background contrast is below 4.5"))
        except (TypeError, ValueError):
            findings.append(_finding(code, "", "Resolved local contrast colours are invalid"))
    scenes = production.get("scenes") if isinstance(production.get("scenes"), list) else []
    ir_scenes = tuple(getattr(compiled.scene_ir, "scenes", ()))
    if len(scenes) != len(ir_scenes):
        findings.append(_finding("scene_count_mismatch", "", "Production and V2.1 SceneIR scene counts differ"))
    local_objects = 0
    relationships = 0
    for index, ir_scene in enumerate(ir_scenes):
        scene_id = str(getattr(ir_scene, "scene_id", ""))
        local_objects += len(getattr(ir_scene, "objects", ()))
        relationships += len(getattr(ir_scene, "relationships", ()))
        if index >= len(scenes) or not isinstance(scenes[index], Mapping):
            findings.append(_finding("missing_production_scene", scene_id, "V2.1 SceneIR scene has no production scene"))
            continue
        production_scene = scenes[index]
        body = production_scene.get("body")
        if not isinstance(body, str) or not body.strip():
            findings.append(_finding("empty_body", scene_id, "V2.1 scene body is empty"))
        else:
            _validate_markup(body, scene_id, findings)
            cues = {int(value) for value in re.findall(r'data-cue=["\'](\d+)', body)}
            motion_entries = compiled.motion_qa if isinstance(compiled.motion_qa, (list, tuple)) else ()
            motion_count = sum(isinstance(item, Mapping) and item.get("scene_id") == scene_id and item.get("event_type") in {"TRANSFER", "PATH_MOTION", "GROW", "TRANSFORM", "ASSEMBLE", "MERGE", "PROPAGATE", "CAMERA"} for item in motion_entries)
            if motion_count > 1 and len(cues) < 2:
                findings.append(_finding("cue_anchor_collapse", scene_id, "V2.1 scene motion has no varied narration cue anchors"))
        objects = tuple(getattr(ir_scene, "objects", ()))
        for item in objects:
            box = getattr(item, "box", None)
            space = getattr(ir_scene, "space", None)
            if space is None or box is None or not space.contains(box):
                findings.append(_finding("invalid_normalized_box", scene_id, f"Object {getattr(item, 'id', '?')} is outside canonical SceneSpace"))
            elif getattr(item, "label", "") and len(str(item.label)) > 240:
                findings.append(_finding("label_oversize", scene_id, "V2.1 label exceeds the bounded length"))
        _validate_three(production_scene.get("three"), scene_id, findings)
    required_motion = {"TRANSFER", "PATH_MOTION", "GROW", "TRANSFORM", "ASSEMBLE", "MERGE", "PROPAGATE", "CAMERA"}
    for metric in compiled.motion_qa if isinstance(compiled.motion_qa, (list, tuple)) else ():
        if not isinstance(metric, Mapping):
            findings.append(_finding("invalid_motion_qa", "", "V2.1 motion QA entry must be an object"))
            continue
        if str(metric.get("event_type") or "").upper() in required_motion:
            if not bool(metric.get("observed")):
                findings.append(_finding("motion_displacement", str(metric.get("scene_id") or ""), f"Event {metric.get('event_id') or '?'} has no observable displacement/state change"))
            try:
                radius_error = float(metric.get("path_radius_error", 0.0) or 0.0)
            except (TypeError, ValueError):
                findings.append(_finding("invalid_motion_qa", str(metric.get("scene_id") or ""), "V2.1 motion QA radius must be numeric"))
                continue
            if radius_error > 1e-4:
                findings.append(_finding("orbit_radius", str(metric.get("scene_id") or ""), "Orbit path does not preserve its declared radius"))
    report = _report(findings, len(ir_scenes), len(scenes), local_objects, relationships)
    if not report.valid:
        raise VisualValidationV21Error(report)
    return report


validate_compiled_visual_v21 = validate_compiled_visual_program_v21


def evaluate_visual_quality_v21(program: Any, compiled: Any) -> Any:
    """Gate C: Source grounding, cue distribution, and structural diversity."""
    import logging
    from .scene_evaluator_v21 import evaluate_video_v21

    logger = logging.getLogger(__name__)
    try:
        result = evaluate_video_v21(program, compiled)
        if result.verdict in ("WARN", "FAIL"):
            logger.warning("Gate C Visual Quality Evaluation %s: %s", result.verdict, result.findings)
            for scene_result in result.scene_results:
                if scene_result.verdict in ("WARN", "FAIL"):
                    logger.warning("  Scene %s %s: %s", scene_result.scene_id, scene_result.verdict, scene_result.findings)
        return result
    except Exception as exc:
        logger.error("Gate C evaluation failed: %s", exc)
        from .scene_evaluator_v21 import VideoEvaluationResult
        return VideoEvaluationResult(scene_results=(), structural_diversity_score=0.0, overall_cue_spread=0.0, overall_must_show_coverage=0.0, overall_relationship_coverage=0.0, distinct_families_used=0, distinct_strategies_used=0, verdict="WARN", findings=("Gate C crashed",))


__all__ = ["ValidationFinding", "VisualValidationReport", "VisualValidationV2Error", "VisualValidationV21Error", "validate_compiled_visual_v2", "validate_visual_program_v21", "validate_compiled_visual_program_v21", "validate_compiled_visual_v21", "evaluate_visual_quality_v21"]
