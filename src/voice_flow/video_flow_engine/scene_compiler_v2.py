"""Trusted Scene IR to Narova/HyperFrames compiler for Visual V2.

This is deliberately a one-way compiler.  Model-owned data enters only through
the already validated semantic plan and resolved layout; this module owns every
HTML tag, SVG path, style value, colour, and animation attribute it emits.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from html import escape
import re
from typing import Any, Mapping

from voice_flow.video_flow_contracts import validate_no_executable_code

from .layout_solver import LayoutV2Error, layout_video_plan
from .scene_ir import Box, SceneIR, SceneIRBeat, SceneIRObject, SceneIRRelationship, VideoSceneIR
from .style_engine_v2 import ResolvedDesignTokens, contrast_ratio, resolve_design_tokens
from .visual_plan_v2 import VideoVisualPlanV2


DEFAULT_VOICE = "edge/en-US-AvaNeural"
_SEMANTIC_3D_TYPES = frozenset({"particle_group", "mesh", "light", "camera_target"})
_MAX_3D_SCENES = 12
_THREE_PRIMITIVES = frozenset({"cube", "sphere", "cylinder", "plane", "torus", "cone", "icosahedron"})
_THREE_ANIMATION_PROPERTIES = frozenset({"position.x", "position.y", "position.z", "rotation.x", "rotation.y", "rotation.z", "scale.x", "scale.y", "scale.z", "scale", "opacity"})
_NUMBER = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*(%|x)?")


class SceneCompilerV2Error(ValueError):
    """Raised when a V2 plan cannot be compiled through the safe 2D surface."""


@dataclass(frozen=True)
class CompiledVisualV2:
    """A deterministic Narova production plus the typed artifacts that made it."""

    production: dict[str, Any]
    design_tokens: ResolvedDesignTokens
    scene_ir: VideoSceneIR

    def to_artifacts(self) -> dict[str, Any]:
        """Return JSON-serializable, job-relative artifacts without writing files."""

        artifacts: dict[str, Any] = {
            "resolved-design.json": self.design_tokens.to_dict(),
            "scene-ir/index.json": self.scene_ir.to_dict(),
        }
        for scene in self.scene_ir.scenes:
            artifacts[f"scene-ir/{scene.scene_id}.json"] = scene.to_dict()
        return artifacts


def compile_visual_plan_v2(
    storyboard: dict[str, Any],
    plan: VideoVisualPlanV2,
    *,
    title: str = "",
    mode: str = "summary",
    theme: Any = None,
    voice: Any = None,
) -> CompiledVisualV2:
    """Compile a semantic V2 plan into the existing HyperFrames production shape."""

    if not isinstance(plan, VideoVisualPlanV2):
        raise SceneCompilerV2Error("compile_visual_plan_v2 requires a VideoVisualPlanV2")
    try:
        validate_no_executable_code(plan.to_dict())
    except (TypeError, ValueError) as exc:
        raise SceneCompilerV2Error(f"Unsafe visual plan: {exc}") from exc
    _validate_3d_budget(plan)

    try:
        design_tokens = resolve_design_tokens(plan.design_bible, theme)
        scene_ir = layout_video_plan(plan)
    except (LayoutV2Error, ValueError, TypeError) as exc:
        raise SceneCompilerV2Error(str(exc)) from exc

    sections = _sections_by_id(storyboard)
    if len(sections) != len(scene_ir.scenes):
        raise SceneCompilerV2Error("V2 scenes must map one-to-one to storyboard sections")

    scenes = []
    for scene in scene_ir.scenes:
        section = sections.get(scene.storyboard_section_id)
        if section is None:
            raise SceneCompilerV2Error(
                f"No storyboard section exists for V2 scene {scene.storyboard_section_id!r}"
            )
        scenes.append(_compile_scene(scene, section, design_tokens))

    resolved_title = str(title or storyboard.get("topic") or "Video Flow Explanation")
    production = {
        "title": resolved_title,
        "size": "16:9",
        "renderer": "hyperframes",
        "voices": {"narrator": _narrator_voice(voice, design_tokens.accent)},
        "theme": {
            "mode": _theme_mode(design_tokens),
            "bg": design_tokens.background,
            "accent": design_tokens.accent,
            "css": "theme.css",
        },
        "safeLayout": True,
        "chrome": False,
        "captions": {"preset": "rise"},
        "timing": {
            "gapSentence": 0.22,
            "gapTurn": 0.35,
            "lead": 0.12,
            "tail": 0.45,
            "tempo": 1.05 if mode == "full" else 1.12,
        },
        "scenes": scenes,
        "_files": {"theme.css": _theme_css(design_tokens)},
    }
    return CompiledVisualV2(production=production, design_tokens=design_tokens, scene_ir=scene_ir)


def _validate_3d_budget(plan: VideoVisualPlanV2) -> None:
    three_scene_count = sum(
        any(item.type in _SEMANTIC_3D_TYPES for item in scene.objects)
        for scene in plan.scenes
    )
    if three_scene_count > _MAX_3D_SCENES:
        raise SceneCompilerV2Error(
            f"Visual V2 supports at most {_MAX_3D_SCENES} semantic 3D scenes per video"
        )

def _sections_by_id(storyboard: dict[str, Any]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(storyboard, Mapping):
        raise SceneCompilerV2Error("storyboard must be an object")
    raw_sections = storyboard.get("sections")
    if not isinstance(raw_sections, list) or not 1 <= len(raw_sections) <= 60:
        raise SceneCompilerV2Error("storyboard.sections must contain between 1 and 60 sections")
    sections: dict[str, Mapping[str, Any]] = {}
    for index, section in enumerate(raw_sections, start=1):
        if not isinstance(section, Mapping):
            raise SceneCompilerV2Error(f"storyboard.sections[{index - 1}] must be an object")
        raw_id = section.get("id")
        section_id = f"section_{index}" if raw_id is None or not str(raw_id).strip() else str(raw_id)
        if section_id in sections:
            raise SceneCompilerV2Error("storyboard contains duplicate section IDs")
        sections[section_id] = section
    return sections


def _narrator_voice(voice: Any, accent: str) -> dict[str, str]:
    if isinstance(voice, Mapping):
        raw_speaker = voice.get("speaker") or voice.get("id") or voice.get("voice")
    else:
        raw_speaker = voice
    speaker = str(raw_speaker or DEFAULT_VOICE).strip() or DEFAULT_VOICE
    return {"backend": "voiceflow", "speaker": speaker, "color": accent, "label": "Narrator"}


def _theme_mode(tokens: ResolvedDesignTokens) -> str:
    return "light" if contrast_ratio(tokens.foreground, "#FFFFFF") > contrast_ratio(tokens.foreground, "#000000") else "dark"


def _compile_scene(
    scene: SceneIR,
    section: Mapping[str, Any],
    tokens: ResolvedDesignTokens,
) -> dict[str, Any]:
    narration = _narration(section)
    three = _three_scene(scene, tokens) if _uses_semantic_3d(scene) else None
    compiled = {
        "id": scene.scene_id,
        "transition": scene.transition or "fade",
        "vo": [{"who": "narrator", "text": narration}],
        "body": _scene_body(scene, tokens, transparent=three is not None),
    }
    if three is not None:
        compiled["three"] = three
    return compiled

def _narration(section: Mapping[str, Any]) -> str:
    lines = section.get("lecture_lines")
    if not isinstance(lines, list) or not lines:
        raise SceneCompilerV2Error("storyboard section has no lecture_lines")
    return " ".join(str(line) for line in lines)


def _scene_body(scene: SceneIR, tokens: ResolvedDesignTokens, *, transparent: bool = False) -> str:
    beats = _beats_by_object(scene.beats)
    objects = {item.id: item for item in scene.objects}
    marker_id = f"v2-{scene.scene_id}-arrow"
    connections = "".join(
        _connection_markup(relationship, objects, marker_id, beats.get(relationship.target))
        for relationship in scene.relationships
    )
    object_markup = "".join(
        _object_markup(scene.scene_id, item, beats.get(item.id), tokens)
        for item in scene.objects
    )
    stage_classes = ["v2-stage"]
    if transparent:
        stage_classes.append("v2-clear")
    elif tokens.surface_mode == "clean_dot_grid" or tokens.background_character == "dot_grid":
        stage_classes.append("v2-dot-grid")
    stage_class = " ".join(stage_classes)
    return (
        f'<div class="{stage_class}">'
        '<svg class="v2-connections" viewBox="0 0 1920 1080" aria-hidden="true">'
        f'<defs><marker id="{escape(marker_id, quote=True)}" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>'
        f'{connections}</svg>'
        f'{object_markup}'
        '</div>'
    )


def _beats_by_object(beats: tuple[SceneIRBeat, ...]) -> dict[str, SceneIRBeat]:
    """Use the first semantic state change as the object's entrance anchor."""

    result: dict[str, SceneIRBeat] = {}
    for beat in beats:
        result.setdefault(beat.object_id, beat)
    return result


def _dock_points(source_box: Box, target_box: Box) -> tuple[int, int, int, int]:
    """Calculate clean edge-to-edge connection points so arrows never penetrate cards or overlap labels."""
    src_cx, src_cy = _center(source_box)
    tgt_cx, tgt_cy = _center(target_box)

    dx = tgt_cx - src_cx
    dy = tgt_cy - src_cy

    if abs(dx) >= abs(dy):
        if dx >= 0:
            start_x = source_box.x + source_box.width + 2
            start_y = src_cy
            end_x = max(start_x + 8, target_box.x - 10)
            end_y = tgt_cy
        else:
            start_x = source_box.x - 2
            start_y = src_cy
            end_x = min(start_x - 8, target_box.x + target_box.width + 10)
            end_y = tgt_cy
    else:
        if dy >= 0:
            start_x = src_cx
            start_y = source_box.y + source_box.height + 2
            end_x = tgt_cx
            end_y = max(start_y + 8, target_box.y - 10)
        else:
            start_x = src_cx
            start_y = source_box.y - 2
            end_x = tgt_cx
            end_y = min(start_y - 8, target_box.y + target_box.height + 10)

    return start_x, start_y, end_x, end_y


def _connection_markup(
    relationship: SceneIRRelationship,
    objects: dict[str, SceneIRObject],
    marker_id: str,
    beat: SceneIRBeat | None,
) -> str:
    source = objects.get(relationship.source)
    target = objects.get(relationship.target)
    if source is None or target is None:
        raise SceneCompilerV2Error("Scene IR relationship references an unavailable object")
    start_x, start_y, end_x, end_y = _dock_points(source.box, target.box)
    control = max(32, abs(end_x - start_x) // 3)
    direction = 1 if end_x >= start_x else -1
    path = f"M {start_x} {start_y} C {start_x + direction * control} {start_y}, {end_x - direction * control} {end_y}, {end_x} {end_y}"
    attrs = _animation_attrs(beat, drawable=True)
    return (
        f'<path class="v2-connection cue"{attrs} d="{path}" '
        f'marker-end="url(#{escape(marker_id, quote=True)})" data-relationship="{escape(relationship.kind, quote=True)}"/>'
    )


def _object_markup(
    scene_id: str,
    item: SceneIRObject,
    beat: SceneIRBeat | None,
    tokens: ResolvedDesignTokens,
) -> str:
    box_style = _box_style(item.box)
    label = escape(item.label, quote=True)
    attrs = _animation_attrs(beat, drawable=False)
    if item.type in _SEMANTIC_3D_TYPES:
        return f'<div class="v2-object v2-three-label v2-role-{item.role} cue"{attrs} style="{box_style}">{label}</div>'
    if item.type in {"shape", "node", "container"} and item.form not in {None, "auto"}:
        return _rich_form_markup(scene_id, item, attrs, label, tokens)
    if item.type == "node":
        return f'<div class="v2-object v2-node v2-role-{item.role} cue"{attrs} style="{box_style}"><span>{label}</span></div>'
    if item.type == "operator":
        return f'<div class="v2-object v2-operator v2-role-{item.role} cue"{attrs} style="{box_style}">{label}</div>'
    if item.type == "equation":
        return f'<div class="v2-object v2-equation v2-role-{item.role} cue"{attrs} style="{box_style}">{label}</div>'
    if item.type in {"text", "label"}:
        return f'<div class="v2-object v2-text v2-role-{item.role} cue"{attrs} style="{box_style}">{label}</div>'
    if item.type in {"shape", "container"}:
        return f'<div class="v2-object v2-shape v2-role-{item.role} cue"{attrs} style="{box_style}"><span>{label}</span></div>'
    if item.type == "chart":
        return _chart_markup(item, attrs, label)
    if item.type == "axis":
        return _axis_markup(item, attrs, label)
    if item.type == "wave":
        if item.form in {"line", "arc", "curve"}:
            return _line_markup(scene_id, item, attrs, label)
        return _wave_markup(item, attrs, label)
    if item.type in {"line", "arrow", "curve"}:
        return _line_markup(scene_id, item, attrs, label)
    raise SceneCompilerV2Error(f"Unsupported V2 object type {item.type!r}")


def _uses_semantic_3d(scene: SceneIR) -> bool:
    return any(item.type in _SEMANTIC_3D_TYPES for item in scene.objects)


def _three_scene(scene: SceneIR, tokens: ResolvedDesignTokens) -> dict[str, Any]:
    targets = [item for item in scene.objects if item.type == "camera_target"]
    look_at = _box_position(targets[0].box, targets[0].role) if targets else (0.0, 0.0, 0.0)
    lights = [
        {"type": "ambient", "color": "#FFFFFF", "intensity": 0.3},
        {"type": "directional", "color": "#FFFFFF", "intensity": 1.8, "position": [5.0, 8.0, 7.0]},
        {"type": "hemisphere", "color": tokens.foreground, "groundColor": tokens.surface, "intensity": 0.6},
        {"type": "directional", "color": tokens.accent, "intensity": 0.7, "position": [-4.0, 3.0, -5.0]},
    ]
    objects: list[dict[str, Any]] = []
    beat_by_object = _beats_by_object(scene.beats)
    for item in scene.objects:
        position = _box_position(item.box, item.role)
        if item.type == "light":
            lights.append(_semantic_light(position, item.role, tokens))
        elif item.type == "mesh":
            result = _mesh_object(scene.visual_mode, item, position, tokens, beat_by_object.get(item.id))
            if isinstance(result, list):
                objects.extend(result)
            else:
                objects.append(result)
        elif item.type == "particle_group":
            objects.append(_particle_object(item, position, tokens, beat_by_object.get(item.id)))
    if len(lights) == 1 and objects:
        lights.append({"type": "directional", "color": tokens.foreground, "intensity": 0.8, "position": [3.0, 4.0, 5.0]})
    return {
        "camera": _camera_preset(scene.camera_intent, look_at),
        "toneMapping": "aces",
        "background": tokens.background,
        "lights": lights,
        "objects": objects,
    }


def _box_position(box: Box, role: str) -> tuple[float, float, float]:
    center_x, center_y = _center(box)
    x = _bounded(((center_x / 1920) - 0.5) * 6.0, -3.0, 3.0)
    y = _bounded((0.5 - (center_y / 1080)) * 3.6, -1.8, 1.8)
    z_by_role = {"primary": -0.35, "secondary": 0.1, "support": 0.3, "container": 0.45, "background": 0.7, "annotation": -0.1}
    return (round(x, 3), round(y, 3), z_by_role.get(role, 0.0))


def _bounded(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _camera_preset(intent: str | None, look_at: tuple[float, float, float]) -> dict[str, Any]:
    presets = {
        "static": ([0.0, 0.0, 7.0], 48),
        "focus": ([0.0, 0.6, 6.2], 46),
        "zoom": ([0.0, 0.0, 5.6], 42),
        "pan": ([-2.2, 0.5, 6.8], 48),
        "orbit": ([3.2, 2.1, 6.6], 50),
        "dolly": ([0.0, 1.0, 7.8], 44),
        "follow": ([0.0, 1.2, 6.4], 47),
    }
    position, fov = presets.get(intent or "focus", presets["focus"])
    return {"position": position, "lookAt": list(look_at), "fov": fov, "near": 0.1, "far": 40.0}


def _semantic_light(position: tuple[float, float, float], role: str, tokens: ResolvedDesignTokens) -> dict[str, Any]:
    light_type = "directional" if role in {"primary", "background"} else "point"
    return {
        "type": light_type,
        "color": tokens.accent if role == "primary" else tokens.secondary,
        "intensity": 1.1 if role == "primary" else 0.8,
        "position": [position[0], position[1] + 1.2, 3.5],
    }


def _compound_mesh_object(
    visual_mode: str,
    item: SceneIRObject,
    position: tuple[float, float, float],
    tokens: ResolvedDesignTokens,
    beat: SceneIRBeat | None,
) -> list[dict[str, Any]] | None:
    """Create visually rich compound 3D objects from multiple primitives."""
    
    compounds = {
        "construction": [  # Architecture: base platform + tower + cap
            {"type": "cube", "size": [1.8, 0.15, 1.2], "position": [0, -0.5, 0], "color": tokens.surface},
            {"type": "cube", "size": [0.6, 1.2, 0.6], "position": [0, 0.2, 0], "color": tokens.accent},
            {"type": "cone", "size": [0.45, 0.3, 0.45], "position": [0, 0.95, 0], "color": tokens.secondary},
        ],
        "mechanism": [  # Machine: cylinder + sphere joints + connector
            {"type": "cylinder", "size": [0.3, 0.8, 0.3], "position": [-0.6, 0, 0], "color": tokens.accent},
            {"type": "sphere", "size": [0.2, 0.2, 0.2], "position": [0, 0, 0], "color": tokens.secondary},
            {"type": "cylinder", "size": [0.3, 0.8, 0.3], "position": [0.6, 0, 0], "color": tokens.accent},
            {"type": "cube", "size": [1.4, 0.1, 0.15], "position": [0, 0, 0], "color": tokens.edge},
        ],
        "spatial": [  # Planet system: large sphere + ring + small orbiting sphere
            {"type": "sphere", "size": [0.7, 0.7, 0.7], "position": [0, 0, 0], "color": tokens.accent},
            {"type": "torus", "size": [1.2, 1.2, 1.2], "position": [0, 0, 0], "color": tokens.edge},
            {"type": "sphere", "size": [0.18, 0.18, 0.18], "position": [1.1, 0, 0], "color": tokens.secondary},
        ],
        "diagram": [  # Layered card stack
            {"type": "cube", "size": [1.2, 0.08, 0.9], "position": [0.08, -0.2, 0.08], "color": tokens.edge},
            {"type": "cube", "size": [1.2, 0.08, 0.9], "position": [0.04, -0.05, 0.04], "color": tokens.surface},
            {"type": "cube", "size": [1.2, 0.08, 0.9], "position": [0, 0.1, 0], "color": tokens.accent},
        ],
        "narrative": [  # Book/scroll: open book shape
            {"type": "cube", "size": [0.6, 0.8, 0.06], "position": [-0.35, 0, 0], "color": tokens.accent},
            {"type": "cube", "size": [0.6, 0.8, 0.06], "position": [0.35, 0, 0], "color": tokens.accent},
            {"type": "cylinder", "size": [0.04, 0.8, 0.04], "position": [0, 0, 0], "color": tokens.edge},
        ],
    }
    
    parts = compounds.get(visual_mode)
    if not parts:
        return None  # Fallback to single primitive
    
    # Offset all positions relative to the object's world position
    children = []
    for part in parts:
        child = {
            "type": part["type"],
            "size": part["size"],
            "position": [
                position[0] + part["position"][0],
                position[1] + part["position"][1],
                position[2] + part["position"][2],
            ],
            "color": part["color"],
            **_material(tokens),
        }
        children.append(child)
    
    # Apply animation to the first (main) child
    animation = _three_animation(position, beat)
    if animation is not None:
        children[0]["animate"] = animation
    
    return children


def _mesh_object(
    visual_mode: str,
    item: SceneIRObject,
    position: tuple[float, float, float],
    tokens: ResolvedDesignTokens,
    beat: SceneIRBeat | None,
) -> dict[str, Any] | list[dict[str, Any]]:
    # For primary objects, try compound composition
    if item.role == "primary":
        compound = _compound_mesh_object(visual_mode, item, position, tokens, beat)
        if compound is not None:
            return compound

    form_primitives = {
        "circle": "sphere", "ellipse": "sphere", "rectangle": "cube", "square": "cube",
        "triangle": "cone", "marker": "icosahedron",
    }
    primitive = form_primitives.get(item.form or "") or {
        "construction": "cube",
        "mechanism": "cylinder",
        "spatial": "sphere",
        "narrative": "icosahedron",
        "chart": "cube",
        "data": "cube",
        "equation": "plane",
    }.get(visual_mode, "cube")
    if primitive not in _THREE_PRIMITIVES:
        raise SceneCompilerV2Error("Compiler selected an unsupported Three.js primitive")
    result: dict[str, Any] = {
        "type": primitive,
        "size": [1.2, 1.2, 1.2] if item.role == "primary" else [0.82, 0.82, 0.82],
        "position": list(position),
        "color": _object_colour(item.role, tokens),
        **_material(tokens),
    }
    animation = _three_animation(position, beat)
    if animation is not None:
        result["animate"] = animation
    return result


def _particle_object(
    item: SceneIRObject,
    position: tuple[float, float, float],
    tokens: ResolvedDesignTokens,
    beat: SceneIRBeat | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "particles",
        "count": 360 if item.role == "primary" else 180,
        "spread": [3.2, 2.4, 2.0],
        "position": list(position),
        "color": _object_colour(item.role, tokens),
        "size": 0.045,
        "animated": False,
    }
    animation = _three_animation(position, beat)
    if animation is not None:
        result["animate"] = animation
    return result


def _object_colour(role: str, tokens: ResolvedDesignTokens) -> str:
    return tokens.accent if role == "primary" else tokens.secondary if role in {"secondary", "support"} else tokens.emphasis


def _material(tokens: ResolvedDesignTokens) -> dict[str, Any]:
    if tokens.surface_mode == "metallic":
        return {"roughness": 0.24, "metalness": 0.72}
    if tokens.surface_mode == "emissive":
        return {"roughness": 0.38, "metalness": 0.1, "emissive": tokens.accent, "emissiveIntensity": 0.35}
    if tokens.surface_mode == "glass":
        return {"roughness": 0.18, "metalness": 0.08}
    return {"roughness": 0.52, "metalness": 0.0}


def _three_animation(position: tuple[float, float, float], beat: SceneIRBeat | None) -> dict[str, Any] | None:
    if beat is None:
        return None
    pos = position
    action_properties = {
        # MOTION GROUP - each moves differently
        "move": ("position.y", pos[1] - 0.6, pos[1]),
        "flow": ("position.x", pos[0] - 1.2, pos[0]),        # Horizontal flow, not vertical
        "propagate": ("position.z", pos[2] + 1.5, pos[2]),    # Come toward camera
        
        # ROTATION GROUP - different axes and amounts
        "rotate": ("rotation.y", 0.0, 3.14),                  # Half turn Y
        "orbit": ("rotation.y", 0.0, 6.28),                   # Full orbit Y  
        "tumble": ("rotation.x", 0.0, 6.28),                  # Full tumble X
        "roll": ("rotation.z", 0.0, 3.14),                    # Roll on Z
        
        # SCALE GROUP - different scale behaviors
        "scale": ("scale", 0.15, 1.0),                        # Small → full
        "morph": ("scale.y", 0.3, 1.0),                       # Stretch vertically
        "split": ("scale.x", 0.1, 1.0),                       # Widen horizontally
        "merge": ("scale", 1.2, 0.85),                        # Compress inward
        "grow": ("scale", 0.0, 1.0),                          # From nothing
        "shrink": ("scale", 1.0, 0.3),                        # Reduce
        "pulse": ("scale", 0.85, 1.1),                        # Breathing pulse
        
        # OPACITY GROUP - different fade behaviors
        "create": ("opacity", 0.0, 1.0),                      # Fade in
        "reveal": ("opacity", 0.0, 1.0),                      # Fade in
        "draw": ("opacity", 0.0, 1.0),                        # Fade in
        "trace": ("opacity", 0.0, 1.0),                       # Fade in
        "connect": ("opacity", 0.0, 1.0),                     # Fade in
        "disconnect": ("opacity", 1.0, 0.15),                 # Fade almost out
        "highlight": ("opacity", 0.4, 1.0),                   # Emphasize
        "dim": ("opacity", 1.0, 0.2),                         # Dim to background
        "replace": ("opacity", 0.0, 1.0),                     # Swap in
        
        # POSITION GROUP - varied entrances
        "focus": ("position.z", pos[2] + 2.0, pos[2]),        # Dolly toward camera
        "zoom": ("position.z", pos[2] - 2.0, pos[2]),         # Zoom from behind
        "pan": ("position.x", pos[0] + 1.8, pos[0]),          # Pan from right
        "measure": ("position.y", pos[1] + 0.8, pos[1]),      # Drop from above
    }
    property_name, start, end = action_properties.get(beat.action, ("opacity", 0.0, 1.0))
    if property_name not in _THREE_ANIMATION_PROPERTIES:
        raise SceneCompilerV2Error("Compiler selected an unsupported Three.js animation property")
        
    if beat.action in {"create", "reveal", "draw", "trace", "connect", "disconnect", "replace"}:
        duration = min(0.6, 0.4 + beat.order * 0.05)
    elif beat.action in {"orbit", "rotate", "tumble", "roll"}:
        duration = min(2.5, 1.5 + beat.order * 0.2)
    else:
        duration = min(1.2, 0.8 + beat.order * 0.1)
        
    if property_name.startswith("position"):
        ease = "power2.inOut"
    elif property_name.startswith("scale"):
        ease = "back.out"
    elif property_name.startswith("rotation"):
        ease = "sine.inOut"
    else:
        ease = "power3.out"

    return {
        "property": property_name,
        "from": round(start, 3),
        "to": round(end, 3),
        "duration": round(duration, 2),
        "ease": ease,
        "at": {"cue": 0, "offset": round(0.1 + (beat.order - 1) * 0.16, 2)},
    }

def _chart_markup(item: SceneIRObject, attrs: str, label: str) -> str:
    box = item.box
    bar_width = max(18, box.width // 7)
    plot_height = max(36, box.height - 56)
    bars = "".join(
        f'<rect class="v2-chart-bar" x="{32 + index * (bar_width + 18)}" y="{box.height - 28 - height}" '
        f'width="{bar_width}" height="{height}" rx="2" data-grow="true"/>'
        for index, height in enumerate(
            (max(18, plot_height * 35 // 100), max(18, plot_height * 55 // 100), max(18, plot_height * 75 // 100), plot_height)
        )
    )
    visual = (
        f'<path class="v2-chart-area" d="M 24 {box.height - 24} L {box.width * 28 // 100} {box.height * 60 // 100} L {box.width * 58 // 100} {box.height * 40 // 100} L {box.width - 20} 24 L {box.width - 20} {box.height - 24} Z" data-draw="true"/>'
        if item.form == "area"
        else bars
    )
    return (
        f'<div class="v2-object v2-chart v2-role-{item.role} cue"{attrs} style="{_box_style(box)}">'
        f'<svg viewBox="0 0 {box.width} {box.height}" aria-label="{label}">'
        f'<path class="v2-axis-path" d="M 24 {box.height - 24} V 24 M 24 {box.height - 24} H {box.width - 20}" data-draw="true"/>'
        f'{visual}</svg><span>{label}</span></div>'
    )


def _axis_markup(item: SceneIRObject, attrs: str, label: str) -> str:
    box = item.box
    return (
        f'<div class="v2-object v2-axis v2-role-{item.role} cue"{attrs} style="{_box_style(box)}">'
        f'<svg viewBox="0 0 {box.width} {box.height}" aria-label="{label}">'
        f'<path d="M 18 {box.height - 18} V 18 M 18 {box.height - 18} H {box.width - 18}" data-draw="true"/></svg>'
        f'<span>{label}</span></div>'
    )


def _wave_markup(item: SceneIRObject, attrs: str, label: str) -> str:
    box = item.box
    middle = box.height // 2
    path = f"M 0 {middle} C {box.width // 8} {middle - 56}, {box.width // 4} {middle + 56}, {box.width * 3 // 8} {middle} S {box.width * 5 // 8} {middle - 56}, {box.width * 3 // 4} {middle} S {box.width * 7 // 8} {middle + 56}, {box.width} {middle}"
    return (
        f'<div class="v2-object v2-wave v2-role-{item.role} cue"{attrs} style="{_box_style(box)}">'
        f'<svg viewBox="0 0 {box.width} {box.height}" aria-label="{label}"><path d="{path}" data-draw="true"/></svg>'
        f'<span>{label}</span></div>'
    )


def _line_markup(scene_id: str, item: SceneIRObject, attrs: str, label: str) -> str:
    box = item.box
    marker_id = f"v2-{scene_id}-{item.id}-arrow"
    end_marker = f' marker-end="url(#{marker_id})"' if item.type == "arrow" else ""
    marker = (
        f'<defs><marker id="{marker_id}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" '
        'markerHeight="8" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>'
        if item.type == "arrow"
        else ""
    )
    form = item.form or item.type
    curve = (
        f"M 4 {box.height // 2} Q {box.width // 2} 4 {box.width - 4} {box.height // 2}"
        if form in {"curve", "arc"}
        else f"M 4 {box.height // 2} H {box.width - 4}"
    )
    return (
        f'<div class="v2-object v2-line v2-role-{item.role} cue"{attrs} style="{_box_style(box)}">'
        f'<svg viewBox="0 0 {box.width} {box.height}" aria-label="{label}">{marker}'
        f'<path d="{curve}" data-draw="true"{end_marker}/></svg><span>{label}</span></div>'
    )


def _rich_form_markup(scene_id: str, item: SceneIRObject, attrs: str, label: str, tokens: ResolvedDesignTokens) -> str:
    box_style = _box_style(item.box)
    form = item.form or "rectangle"
    
    w = item.box.width
    h = item.box.height
    
    main_color = tokens.accent if item.role == "primary" else tokens.secondary if item.role == "secondary" else tokens.surface
    gradient_stop2 = tokens.secondary if item.role == "primary" else tokens.surface
    
    cx = w // 2
    cy = h // 2
    
    defs = (
        f'<defs>'
        f'<linearGradient id="grad_{scene_id}_{item.id}" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{main_color}" stop-opacity="0.9"/>'
        f'<stop offset="100%" stop-color="{gradient_stop2}" stop-opacity="0.7"/>'
        f'</linearGradient>'
        f'<radialGradient id="glow_{scene_id}_{item.id}" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{main_color}" stop-opacity="0.4"/>'
        f'<stop offset="100%" stop-color="{main_color}" stop-opacity="0"/>'
        f'</radialGradient>'
        f'</defs>'
    )
    
    glow_svg = f'<rect x="-20%" y="-20%" width="140%" height="140%" fill="url(#glow_{scene_id}_{item.id})" />' if item.role in {"primary", "secondary"} else ""
    
    shape_svg = ""
    inner_svg = ""
    
    is_primary = item.role == "primary"
    is_secondary = item.role == "secondary"
    
    if form in {"circle", "ellipse"}:
        r = min(w, h) // 2 - 4
        shape_svg = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#grad_{scene_id}_{item.id})" stroke="{tokens.edge}" stroke-width="2"/>'
        if is_primary or is_secondary:
            inner_svg += f'<circle cx="{cx}" cy="{cy}" r="{max(1, r - 8)}" fill="none" stroke="{tokens.edge}" stroke-width="1" stroke-dasharray="4 4" opacity="0.6"/>'
        if is_primary:
            inner_svg += f'<circle cx="{cx}" cy="{cy}" r="{max(1, r - 16)}" fill="none" stroke="{tokens.edge}" stroke-width="1" opacity="0.4"/>'
            
    elif form == "triangle":
        pt1 = f"{cx},{4}"
        pt2 = f"{w-4},{h-4}"
        pt3 = f"{4},{h-4}"
        shape_svg = f'<polygon points="{pt1} {pt2} {pt3}" fill="url(#grad_{scene_id}_{item.id})" stroke="{tokens.edge}" stroke-width="2" stroke-linejoin="round"/>'
        if is_primary or is_secondary:
            inner_svg += f'<polyline points="{cx},{16} {w-12},{h-10} {12},{h-10} {cx},{16}" fill="none" stroke="{tokens.edge}" stroke-width="1" stroke-dasharray="4 4" opacity="0.6"/>'
        if is_primary:
            inner_svg += f'<circle cx="{cx}" cy="{h - 16}" r="4" fill="{tokens.edge}" opacity="0.5"/>'
            
    elif form == "bar":
        shape_svg = f'<rect x="4" y="4" width="{w-8}" height="{h-8}" rx="8" fill="url(#grad_{scene_id}_{item.id})" stroke="{tokens.edge}" stroke-width="2"/>'
        if is_primary or is_secondary:
            inner_svg += f'<line x1="{w//3}" y1="4" x2="{w//3}" y2="{h-4}" stroke="{tokens.edge}" stroke-width="1" opacity="0.4"/>'
            inner_svg += f'<line x1="{w*2//3}" y1="4" x2="{w*2//3}" y2="{h-4}" stroke="{tokens.edge}" stroke-width="1" opacity="0.4"/>'
            
    elif form == "marker":
        r = min(w, h) // 2 - 4
        shape_svg = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#grad_{scene_id}_{item.id})" stroke="{tokens.edge}" stroke-width="2"/>'
        inner_svg += f'<circle cx="{cx}" cy="{cy}" r="{max(1, r//2)}" fill="{tokens.edge}" opacity="0.8"/>'
        if is_primary or is_secondary:
            inner_svg += f'<circle cx="{cx}" cy="{cy}" r="{max(1, r*3//4)}" fill="none" stroke="{tokens.edge}" stroke-width="1" stroke-dasharray="2 2" opacity="0.6"/>'
            
    elif form in {"line", "arc", "curve", "area"}:
        path = _form_path(form, w, h)
        shape_svg = f'<path d="{path}" fill="url(#grad_{scene_id}_{item.id})" stroke="{tokens.edge}" stroke-width="2"/>'
        
    else:
        rx = 16
        shape_svg = f'<rect x="4" y="4" width="{w-8}" height="{h-8}" rx="{rx}" fill="url(#grad_{scene_id}_{item.id})" stroke="{tokens.edge}" stroke-width="2"/>'
        if is_primary or is_secondary:
            inner_svg += f'<line x1="16" y1="20" x2="{w-16}" y2="20" stroke="{tokens.edge}" stroke-width="1" opacity="0.3"/>'
            inner_svg += f'<line x1="16" y1="{h-20}" x2="{w-16}" y2="{h-20}" stroke="{tokens.edge}" stroke-width="1" opacity="0.3"/>'
        if is_primary:
            inner_svg += f'<circle cx="24" cy="{cy}" r="3" fill="{tokens.edge}" opacity="0.4"/>'
            inner_svg += f'<circle cx="{w-24}" cy="{cy}" r="3" fill="{tokens.edge}" opacity="0.4"/>'

    if is_primary:
        label_markup = (
            f'<div style="position:absolute; inset:8px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; pointer-events:none;">'
            f'<div style="font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:{tokens.accent}; margin-bottom:4px;">★ CONCEPT</div>'
            f'<span style="font-size:clamp(14px, 1.4vw, 20px); font-weight:800; line-height:1.2; color:{tokens.foreground};">{label}</span>'
            f'</div>'
        )
    elif is_secondary:
        label_markup = (
            f'<div style="position:absolute; inset:8px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; pointer-events:none;">'
            f'<div style="font-size:10px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:{tokens.muted}; margin-bottom:2px;">COMPONENT</div>'
            f'<span style="font-size:clamp(13px, 1.2vw, 17px); font-weight:700; line-height:1.2; color:{tokens.foreground};">{label}</span>'
            f'</div>'
        )
    else:
        label_markup = (
            f'<div style="position:absolute; inset:4px; display:flex; align-items:center; justify-content:center; text-align:center; pointer-events:none;">'
            f'<span style="font-size:clamp(12px, 1.1vw, 16px); font-weight:600; line-height:1.2; color:{tokens.foreground};">{label}</span>'
            f'</div>'
        )
    
    return (
        f'<div class="v2-object v2-form v2-form-{form} v2-role-{item.role} cue"{attrs} style="{box_style}">'
        f'<svg viewBox="0 0 {w} {h}" style="position:absolute; top:0; left:0; width:100%; height:100%; overflow:visible;" aria-label="{label}">'
        f'{defs}{glow_svg}{shape_svg}{inner_svg}'
        f'</svg>'
        f'{label_markup}'
        f'</div>'
    )


def _form_path(form: str, width: int, height: int) -> str:
    if form == "triangle":
        return f"M {width // 2} 8 L {width - 8} {height - 8} L 8 {height - 8} Z"
    if form == "line":
        return f"M 8 {height // 2} H {width - 8}"
    if form == "arc":
        return f"M 8 {height - 8} A {max(12, width // 2 - 8)} {max(12, height - 8)} 0 0 1 {width - 8} {height - 8}"
    if form == "curve":
        return f"M 8 {height - 8} Q {width // 2} 8 {width - 8} {height // 2}"
    if form == "area":
        return f"M 8 {height - 8} L {width // 3} {height * 2 // 3} L {width * 2 // 3} {height // 3} L {width - 8} 8 L {width - 8} {height - 8} Z"
    return f"M 8 8 H {width - 8} V {height - 8} H 8 Z"

def _animation_attrs(beat: SceneIRBeat | None, *, drawable: bool, total_cues: int = 3, estimated_scene_duration: float = 10.0) -> str:
    if beat is None:
        return ' data-cue="0" data-delay="0.12"'
    
    cue_idx = 0
    has_anchor = hasattr(beat, "narration_anchor") and getattr(beat, "narration_anchor", None) is not None
    if has_anchor and hasattr(beat.narration_anchor, "cue_index"):
        cue_idx = int(beat.narration_anchor.cue_index)
    elif total_cues > 3 or has_anchor:
        cue_idx = (beat.order - 1) % max(1, total_cues)
    else:
        if beat.phase == "explain":
            cue_idx = 1
        elif beat.phase == "resolve":
            cue_idx = 2
        elif beat.order > 2:
            cue_idx = 1
            
    if cue_idx == 0:
        delay = min(0.3, 0.0 + ((beat.order - 1) % 4) * 0.1)
    elif not has_anchor and total_cues <= 3:
        delay = 0.12 + ((beat.order - 1) % 2) * 0.16
    else:
        delay = (cue_idx / max(1, total_cues)) * estimated_scene_duration
        
    attrs = f' data-cue="{cue_idx}" data-delay="{delay:.2f}"'
    
    if beat.action in {"flow", "propagate", "move"}:
        entrance = "slide-left" if beat.action == "flow" else "rise"
        attrs += f' data-enter="{entrance}"'
    elif beat.action in {"create", "scale", "split"}:
        attrs += ' data-enter="pop"'
    elif beat.action in {"focus", "zoom"}:
        attrs += ' data-enter="zoom"'
    elif beat.action in {"reveal", "draw", "trace"}:
        attrs += ' data-enter="rise"'
        
    if beat.action == "pulse":
        attrs += ' data-pulse="true"'
        
    if drawable and beat.action in {"draw", "trace", "connect", "flow", "propagate", "merge", "split"}:
        attrs += ' data-draw="true"'
    if beat.action == "highlight":
        attrs += ' data-mark="highlight"'
    elif beat.action == "measure":
        number = _measurement(beat.reason)
        if number is not None:
            value, suffix = number
            attrs += f' data-count="{value}" data-count-suffix="{suffix}"'
        else:
            attrs += ' data-mark="underline"'
    return attrs


def _measurement(text: str) -> tuple[str, str] | None:
    match = _NUMBER.search(text)
    if match is None:
        return None
    return match.group(1), match.group(2) or ""


def _box_style(box: Box) -> str:
    return f"left:{box.x}px;top:{box.y}px;width:{box.width}px;height:{box.height}px"


def _center(box: Box) -> tuple[int, int]:
    return box.x + box.width // 2, box.y + box.height // 2


def _surface_background(tokens: ResolvedDesignTokens) -> str:
    if tokens.surface_opacity >= 1:
        return tokens.surface
    red = int(tokens.surface[1:3], 16)
    green = int(tokens.surface[3:5], 16)
    blue = int(tokens.surface[5:7], 16)
    return f"rgba({red}, {green}, {blue}, {tokens.surface_opacity:.2f})"

def _theme_css(tokens: ResolvedDesignTokens) -> str:
    """Emit fixed, renderer-safe CSS from trusted resolved tokens only."""

    surface_background = _surface_background(tokens)
    return f"""
.v2-stage {{ position:absolute; inset:0; overflow:hidden; background:{tokens.background}; color:{tokens.foreground}; }}
.v2-stage.v2-clear {{ background:transparent; }}
.v2-stage, .v2-stage * {{ box-sizing:border-box; }}
.v2-stage.v2-dot-grid {{ background-image: radial-gradient(rgba(255,255,255,0.08) 1.5px, transparent 1.5px); background-size: 24px 24px; }}
.v2-scene-label {{ position:absolute; left:96px; top:58px; font:700 16px/1 {tokens.body_font_stack}; letter-spacing:.18em; color:{tokens.accent}; }}
.v2-title {{ position:absolute; left:96px; top:82px; max-width:72%; margin:0; font:800 {tokens.heading_size}px/1.04 {tokens.heading_font_stack}; letter-spacing:-.03em; color:{tokens.foreground}; }}
.v2-goal {{ position:absolute; left:96px; top:166px; max-width:56%; margin:0; font:500 {tokens.body_size}px/1.35 {tokens.body_font_stack}; color:{tokens.muted}; }}
.v2-connections {{ position:absolute; inset:0; width:100%; height:100%; overflow:visible; pointer-events:none; }}
.v2-connections path {{ fill:none; stroke:{tokens.edge}; stroke-width:{tokens.stroke_width}px; }}
.v2-connections marker path {{ fill:{tokens.edge}; stroke:none; }}
.v2-object {{ position:absolute; display:flex; align-items:center; justify-content:center; padding:{tokens.spacing // 2}px; color:{tokens.foreground}; font:600 {tokens.body_size}px/1.2 {tokens.body_font_stack}; text-align:center; }}
.v2-node {{ border:{tokens.stroke_width}px solid {tokens.accent}; border-radius:50%; background:{surface_background}; box-shadow:{tokens.shadow}; }}
.v2-operator {{ font:800 {tokens.heading_size}px/1 {tokens.heading_font_stack}; color:{tokens.accent}; padding:0; }}
.v2-equation {{ justify-content:flex-start; border-bottom:{tokens.stroke_width}px solid {tokens.accent}; font:700 {tokens.heading_size // 2}px/1.1 {tokens.heading_font_stack}; padding:0; }}
.v2-text {{ justify-content:flex-start; text-align:left; padding:0; }}
.v2-form {{ border:{tokens.stroke_width}px solid {tokens.accent}; background:{surface_background}; box-shadow:{tokens.shadow}; }}
.v2-form-frosted {{ border:1px solid rgba(255,255,255,0.15); box-shadow:0 20px 48px rgba(0,0,0,0.32); }}
.v2-form-circle, .v2-form-ellipse {{ border-radius:50%; }}
.v2-form-rectangle {{ border-radius:{tokens.radius}px; }}
.v2-form-square {{ aspect-ratio:1; align-self:center; }}
.v2-form-bar {{ height:22%; align-self:center; background:{tokens.accent}; color:{tokens.foreground}; }}
.v2-form-marker {{ width:28%; height:28%; border-radius:50%; align-self:center; background:{tokens.accent}; color:{tokens.foreground}; }}
.v2-form-svg {{ flex-direction:column; gap:8px; padding:0; }}
.v2-form-svg svg {{ width:100%; height:calc(100% - 30px); overflow:visible; }}
.v2-form-svg path {{ fill:none; stroke:{tokens.accent}; stroke-width:{tokens.stroke_width}px; }}
.v2-form-area path, .v2-chart-area {{ fill:{tokens.accent}; fill-opacity:.2; }}
.v2-role-primary {{ font-weight:750; }}
.v2-role-secondary, .v2-role-support, .v2-role-annotation {{ color:{tokens.muted}; }}
.v2-role-teaching_aid {{ font-weight:700; color:{tokens.accent}; }}
.v2-three-label {{ border:1px solid {tokens.edge}; border-radius:{tokens.radius}px; background:{surface_background}; box-shadow:{tokens.shadow}; font-size:18px; }}
.v2-shape {{ border:{tokens.stroke_width}px solid {tokens.edge}; border-radius:{tokens.radius}px; background:{surface_background}; box-shadow:{tokens.shadow}; }}
.v2-chart, .v2-axis, .v2-wave, .v2-line {{ flex-direction:column; gap:8px; padding:0; }}
.v2-chart svg, .v2-axis svg, .v2-wave svg, .v2-line svg {{ width:100%; height:calc(100% - 32px); overflow:visible; }}
.v2-chart span, .v2-axis span, .v2-wave span, .v2-line span {{ font:600 18px/1.2 {tokens.body_font_stack}; color:{tokens.muted}; }}
.v2-chart-bar {{ fill:{tokens.accent}; transform-origin:left center; }}
.v2-axis path, .v2-wave path, .v2-line path {{ fill:none; stroke:{tokens.accent}; stroke-width:{tokens.stroke_width}px; }}
.v21-stage {{ position:absolute; inset:0; overflow:hidden; }}
.v21-scene-svg {{ width:100%; height:100%; }}
.v21-label {{ font:700 20px/1.2 {tokens.body_font_stack}; fill:{tokens.foreground}; }}
.v21-relationship {{ stroke-linecap:round; stroke-linejoin:round; }}
""".strip()


# ---------------------------------------------------------------------------
# Trusted Visual Scene Program V2.1 compiler


@dataclass(frozen=True)
class CompiledVisualProgramV21(CompiledVisualV2):
    """V2.1 compilation result sharing the legacy renderer envelope."""

    program: Any = None
    motion_qa: tuple[Mapping[str, Any], ...] = ()
    render_plans: tuple[Mapping[str, Any], ...] = ()

    def to_artifacts(self) -> dict[str, Any]:
        artifacts = super().to_artifacts()
        if self.program is not None and callable(getattr(self.program, "to_dict", None)):
            artifacts["visual-program-v21.json"] = self.program.to_dict()
        artifacts["motion-qa-v21.json"] = {"events": [dict(item) for item in self.motion_qa]}
        artifacts["scene-space-v21.json"] = self.scene_ir.space.to_dict()
        return artifacts


CompiledVisualV21 = CompiledVisualProgramV21


def compile_visual_program_v21(
    storyboard: dict[str, Any],
    program: Any,
    *,
    title: str = "",
    mode: str = "summary",
    duration_seconds: float | None = None,
    theme: Any = None,
    visual_direction: str = "",
    voice: Any = None,
) -> CompiledVisualProgramV21:
    """Lower a validated V2.1 semantic program into the trusted production.

    The compiler owns all HTML/SVG, concrete styles, coordinates, Three
    primitives, animation properties, and camera data.  The model contributes
    only the already parsed semantic program.
    """

    from .layout_solver_v21 import layout_scene_v21
    from .representation_resolver import resolve_representation
    from .scene_ir_v21 import SceneIRV21, SceneObjectV21, SceneRelationshipV21, VideoSceneIRV21
    from .scene_space import SceneSpace
    from .scene_state import SceneState, event_qa_metrics
    from .visual_program_v21 import VideoVisualProgramV21

    if not isinstance(program, VideoVisualProgramV21):
        raise SceneCompilerV21Error("compile_visual_program_v21 requires a VideoVisualProgramV21")
    if not isinstance(storyboard, Mapping):
        raise SceneCompilerV21Error("V2.1 storyboard must be an object")
    try:
        validate_no_executable_code(program.to_dict())
    except (TypeError, ValueError) as exc:
        raise SceneCompilerV21Error(f"Unsafe V2.1 visual program: {exc}") from exc
    try:
        from .visual_validator import validate_visual_program_v21
        validate_visual_program_v21(program, storyboard=storyboard)
    except Exception as exc:
        if isinstance(exc, SceneCompilerV21Error):
            raise
        raise SceneCompilerV21Error(f"V2.1 capability validation failed: {exc}") from exc

    space = SceneSpace()
    try:
        design_tokens = resolve_design_tokens(
            program.design_bible,
            theme,
            visual_direction=visual_direction or program.design_bible.direction,
        )
    except (ValueError, TypeError, AssertionError) as exc:
        raise SceneCompilerV21Error(f"V2.1 style resolution failed: {exc}") from exc

    try:
        sections = _sections_by_id(storyboard)
    except SceneCompilerV2Error as exc:
        raise SceneCompilerV21Error(str(exc)) from exc
    if set(sections) != {scene.storyboard_section_id for scene in program.scenes}:
        raise SceneCompilerV21Error("V2.1 scenes must map one-to-one to storyboard sections")

    solved_scenes: list[Any] = []
    production_scenes: list[dict[str, Any]] = []
    motion_qa: list[Mapping[str, Any]] = []
    render_plans: list[Mapping[str, Any]] = []
    for scene_index, scene in enumerate(program.scenes):
        ir = _v21_scene_ir(scene, space)
        try:
            solved = layout_scene_v21(ir, space=space)
        except Exception as exc:
            # Dense semantic relation graphs can make every hard routing
            # candidate impossible. Keep the stable object composition and
            # record an explicit relation-router fallback instead of failing
            # the whole V2.1 attempt or silently dropping the program.
            try:
                fallback = layout_scene_v21(replace(ir, relationships=()), space=space)
                solved = replace(fallback, relationships=ir.relationships, metadata={**dict(fallback.metadata), "layout_fallback": "relation_constraints"})
            except Exception as fallback_exc:
                raise SceneCompilerV21Error(f"V2.1 layout failed for {scene.scene_id}: {exc}") from fallback_exc
        solved_scenes.append(solved)
        section = sections[scene.storyboard_section_id]
        scene_production, scene_plans, scene_metrics = _compile_v21_scene(
            scene,
            solved,
            section,
            design_tokens,
            space,
            scene_index=scene_index,
        )
        production_scenes.append(scene_production)
        render_plans.extend(scene_plans)
        motion_qa.extend(scene_metrics)

    resolved_duration = duration_seconds if duration_seconds is not None else program.duration_seconds
    if resolved_duration is not None:
        try:
            resolved_duration = float(resolved_duration)
        except (TypeError, ValueError) as exc:
            raise SceneCompilerV21Error("duration_seconds must be numeric") from exc
        if not 0.1 <= resolved_duration <= 600:
            raise SceneCompilerV21Error("duration_seconds is outside V2.1 bounds")
    scene_durations = _v21_scene_duration_targets(resolved_duration, len(production_scenes)) if resolved_duration is not None else ()
    for scene_production, scene_duration in zip(production_scenes, scene_durations):
        scene_production["dur"] = scene_duration
    resolved_title = str(title or storyboard.get("topic") or "Video Flow Explanation")
    production = {
        "title": resolved_title,
        "size": "16:9",
        "renderer": "hyperframes",
        "voices": {"narrator": _narrator_voice(voice, design_tokens.accent)},
        "theme": {
            "mode": _theme_mode(design_tokens),
            "bg": design_tokens.background,
            "accent": design_tokens.accent,
            "css": "theme.css",
        },
        "safeLayout": True,
        "chrome": False,
        "captions": {"preset": "rise"},
        "timing": {
            "gapSentence": 0.22,
            "gapTurn": 0.35,
            "lead": 0.12,
            "tail": 0.45,
            "tempo": _v21_tempo(mode, duration_seconds=resolved_duration, narration_words=_v21_narration_word_count(storyboard)),
            "duration_seconds": resolved_duration,
            "duration_is_target": resolved_duration is not None,
            "scene_durations": list(scene_durations),
            "scene_space": space.to_dict(),
        },
        "duration_seconds": resolved_duration,
        "duration_is_target": resolved_duration is not None,
        "scenes": production_scenes,
        "_files": {"theme.css": _theme_css_v21(design_tokens)},
    }
    compiled = CompiledVisualProgramV21(
        production=production,
        design_tokens=design_tokens,
        scene_ir=VideoSceneIRV21(scenes=tuple(solved_scenes), space=space),
        program=program,
        motion_qa=tuple(dict(item) for item in motion_qa),
        render_plans=tuple(dict(item) for item in render_plans),
    )
    return compiled


class SceneCompilerV21Error(SceneCompilerV2Error):
    """Typed V2.1 compiler failure used by the V1 fallback boundary."""


def _v21_scene_duration_targets(total: float, count: int) -> tuple[float, ...]:
    if count <= 0 or total <= 0:
        return ()
    if count == 1:
        return (float(total),)
    target = float(total) / count
    values = [target for _ in range(count - 1)]
    values.append(float(total) - sum(values))
    if any(value <= 0 for value in values):
        raise SceneCompilerV21Error("V2.1 scene duration target is not positive")
    return tuple(values)


def _v21_narration_word_count(storyboard: Mapping[str, Any]) -> int:
    """Estimate narration words without invoking TTS or reading model code."""

    total = 0
    sections = storyboard.get("sections") if isinstance(storyboard, Mapping) else ()
    if isinstance(sections, (list, tuple)):
        for section in sections[:60]:
            lines = section.get("lecture_lines") if isinstance(section, Mapping) else ()
            if isinstance(lines, (list, tuple)):
                for line in lines[:32]:
                    total += len(re.findall(r"\b[\w']+\b", str(line)))
    return max(1, min(5_000, total))


def _v21_tempo(mode: Any, *, duration_seconds: float | None = None, narration_words: int = 1) -> float:
    values = {"summary": 1.12, "lesson": 1.05, "full": 0.96, "demo": 1.0}
    base = values.get(str(mode or "summary").casefold(), 1.08)
    if duration_seconds is None:
        return base
    # Bound the natural narration estimate and map target duration to a safe
    # tempo multiplier. Narova may still retime narration to synthesized audio;
    # this is a deterministic pacing target, not a final-duration claim.
    natural_seconds = max(10.0, min(300.0, float(narration_words) / 2.5))
    ratio = ((natural_seconds + 30.0) / (float(duration_seconds) + 30.0)) ** 0.5
    return round(max(0.7, min(1.3, base * ratio)), 6)


def _v21_scene_ir(scene: Any, space: Any) -> Any:
    from .scene_ir_v21 import SceneIRV21, SceneObjectV21, SceneRelationshipV21

    subjects = tuple(scene.subjects)
    parent_map: dict[str, str] = {}
    for subject in subjects:
        for part in _v21_walk_parts(subject.parts):
            parent_map[part.id] = subject.id
    objects: list[Any] = []
    for index, subject in enumerate(subjects):
        render_strategy = str(subject.render_strategy or "procedural_2d")
        role = "primary" if index == 0 else "secondary"
        objects.append(
            SceneObjectV21(
                id=subject.id,
                type="subject",
                label=subject.semantic_name,
                role=role,
                region="auto",
                min_size=(0.12, 0.08) if role == "primary" else (0.09, 0.06),
                layer=index,
                depth=0.0 if role == "primary" else 0.15,
                metadata={
                    "semantic_name": subject.semantic_name,
                    "structural_family": subject.structural_family,
                    "render_strategy": render_strategy,
                    "state": dict(subject.state),
                    "parts": [part.to_dict() for part in subject.parts],
                    "events": [event.to_dict() for event in scene.events if event.subject == subject.id or event.carrier == subject.id],
                },
            )
        )
    subject_ids = {subject.id for subject in subjects}
    relationships: list[Any] = []
    for relation in scene.relationships:
        source = relation.source if relation.source in subject_ids else parent_map.get(relation.source)
        target = relation.target if relation.target in subject_ids else parent_map.get(relation.target)
        if not source or not target or source == target:
            continue
        relationships.append(
            SceneRelationshipV21(
                source=source,
                target=target,
                kind=relation.kind,
                importance=1.0,
                required=True,
                label=relation.kind,
            )
        )
    return SceneIRV21(
        scene_id=scene.scene_id,
        objects=tuple(objects),
        relationships=tuple(relationships),
        space=space,
        purpose=scene.purpose,
        representation_strategy="|".join(scene.representation_strategy),
        visual_mode=scene.shot.mode,
        camera_intent=scene.shot.mode,
        narration_anchors=tuple(anchor.to_dict() for anchor in scene.narration_anchors),
        metadata={"events": [event.to_dict() for event in scene.events], "shot": scene.shot.to_dict()},
    )


def _v21_walk_parts(parts: Any) -> Any:
    for part in parts or ():
        yield part
        yield from _v21_walk_parts(part.parts)


def _compile_v21_scene(scene: Any, ir_scene: Any, section: Mapping[str, Any], tokens: ResolvedDesignTokens, space: Any, *, scene_index: int) -> tuple[dict[str, Any], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    from .representation_resolver import resolve_representation
    from .scene_state import SceneState, event_qa_metrics

    object_map = {item.id: item for item in ir_scene.objects}
    anchor_map = {anchor.id: anchor for anchor in scene.narration_anchors}
    event_dicts = [_v21_event_dict(event, anchor_map, scene, object_map) for event in scene.events]
    state_objects: dict[str, dict[str, Any]] = {}
    for item in ir_scene.objects:
        position = list(space.three_position(item.box, depth=item.depth))
        state_values = dict(scene.initial_state.get(item.id, {}))
        state_values.setdefault("position", position)
        state_values.setdefault("geometry", {"width": item.box.width, "height": item.box.height, "radius": max(item.box.width, item.box.height) / 2.0})
        state_values.setdefault("semantic_state", str(state_values.get("state") or "initial"))
        state_objects[item.id] = state_values
    # Parts may be persistent event targets even when composition promotes
    # only their owning subject to a top-level box. Keep every declared state
    # ID in the evaluator so child transforms remain observable.
    for object_id, raw_state in scene.initial_state.objects.items():
        if object_id in state_objects:
            continue
        values = dict(raw_state)
        values.setdefault("position", [0.0, 0.0, 0.0])
        values.setdefault("geometry", {"radius": 0.08})
        values.setdefault("semantic_state", str(values.get("state") or "initial"))
        state_objects[object_id] = values
    base_state = SceneState(objects=state_objects)
    metrics: list[Mapping[str, Any]] = []
    for event in event_dicts:
        event_type = str(event.get("type") or "").upper()
        try:
            metric = event_qa_metrics(base_state, event, samples=5)
        except Exception as exc:
            raise SceneCompilerV21Error(f"V2.1 event lowering failed for {scene.scene_id}: {event_type}") from exc
        metric_dict = metric.to_dict()
        metric_dict["event_id"] = str(event.get("id") or "")
        metric_dict["scene_id"] = scene.scene_id
        metrics.append(metric_dict)
        if event_type in {"TRANSFER", "PATH_MOTION", "GROW", "TRANSFORM", "ASSEMBLE", "MERGE", "PROPAGATE", "CAMERA"} and not metric.valid:
            raise SceneCompilerV21Error(f"V2.1 event {event_type} has no observable deterministic behavior")

    plans: list[Mapping[str, Any]] = []
    svg_parts: list[str] = []
    three_objects: list[dict[str, Any]] = []
    camera_animations: list[dict[str, Any]] = []
    for item in ir_scene.objects:
        metadata = dict(item.metadata)
        subject = {
            "id": item.id,
            "semantic_name": item.label,
            "structural_family": metadata.get("structural_family", "rigid_assembly"),
            "parts": metadata.get("parts", []),
            "state": metadata.get("state", {}),
            "values": metadata.get("values", []),
        }
        subject_events = [event for event in event_dicts if _v21_event_subjects(event) & {item.id}]
        renderer = _v21_renderer_for(scene, subject)
        plan = resolve_representation(
            subject,
            family=_v21_resolver_family(subject["structural_family"]),
            representation_strategy="|".join(scene.representation_strategy),
            renderer=renderer,
            events=subject_events,
            state=metadata.get("state"),
        )
        plan_dict = plan.to_dict()
        plan_dict["scene_id"] = scene.scene_id
        plan_dict["object_id"] = item.id
        plans.append(plan_dict)
        cue = _v21_object_cue(item.id, scene, anchor_map, event_dicts)
        event_cues = [max(0, int(float(event.get("cue", 0.0)))) for event in subject_events]
        svg_parts.append(_v21_svg_subject(item, plan_dict, tokens, cue, event_cues, space=space))
        three = _v21_three_subject(item, plan_dict, tokens, space, scene, event_dicts, cue, object_map)
        if three is not None:
            three_objects.append(three)
        for animation in plan_dict.get("animations", ()):  # resolver camera descriptors are trusted data
            if isinstance(animation, Mapping) and animation.get("kind") == "camera":
                camera_animations.extend(_v21_camera_animation(animation, cue))

    three = None
    if three_objects or scene.shot.mode != "static":
        look_at = [0.0, 0.0, 0.0]
        target_item = object_map.get(scene.shot.subject or "")
        if target_item is not None:
            look_at = list(space.three_position(target_item.box, depth=target_item.depth))
        camera = _v21_camera(scene.shot.mode, look_at)
        lights = [
            {"type": "ambient", "intensity": 0.55, "color": tokens.foreground},
            {"type": "directional", "position": [4.0, 6.0, 5.0], "intensity": 1.2, "color": tokens.foreground, "shadow": True},
            {"type": "hemisphere", "color": tokens.foreground, "groundColor": tokens.background, "intensity": 0.45},
            {"type": "directional", "position": [-4.0, 3.0, -4.0], "intensity": 0.8, "color": tokens.accent},
        ]
        three = {
            "camera": camera,
            "toneMapping": "aces",
            "background": tokens.background,
            "lights": lights,
            "objects": three_objects,
            "cameraAnimate": camera_animations + _v21_shot_camera_animations(scene.shot, camera, cue),
        }
    narration = _v21_narration(section, scene.purpose)
    body = _v21_scene_body(scene, ir_scene, svg_parts, tokens, space, transparent=three is not None)
    compiled = {
        "id": scene.scene_id,
        "transition": "fade",
        "vo": [{"who": "narrator", "text": narration}],
        "body": body,
    }
    if three is not None:
        compiled["three"] = three
    return compiled, tuple(plans), tuple(metrics)


def _v21_resolver_family(family: Any) -> str:
    # The registry advertises particle_system as a semantic family while the
    # resolver intentionally reuses its atmospheric particle construction.
    return "atmospheric_system" if str(family) == "particle_system" else str(family)


def _v21_renderer_for(scene: Any, subject: Mapping[str, Any]) -> str:
    raw = str(subject.get("render_strategy") or "").casefold()
    if raw in {"semantic_3d", "three"}:
        return "three"
    if "DATA" in scene.representation_strategy:
        return "svg"
    if "MATHEMATICAL" in scene.representation_strategy:
        return "svg"
    if "SPATIAL" in scene.representation_strategy and subject.get("structural_family") == "celestial_body":
        return "hybrid"
    return "hybrid"


def _v21_event_subjects(event: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("subject", "source", "destination", "target", "carrier", "center"):
        if event.get(key):
            values.add(str(event[key]))
    for key in ("parts", "sources", "targets", "nodes"):
        raw = event.get(key) or []
        if isinstance(raw, (list, tuple)):
            values.update(str(item) for item in raw)
    return values


def _v21_event_dict(event: Any, anchors: Mapping[str, Any], scene: Any, object_map: Mapping[str, Any]) -> dict[str, Any]:
    data = event.to_dict()
    anchor = anchors.get(event.narration_anchor) if event.narration_anchor else None
    cue = anchor.cue_index if anchor is not None and anchor.cue_index is not None else (event.at if event.at is not None else 0.0)
    data["cue"] = max(0.0, float(cue))
    data["duration"] = float(event.duration)
    if event.event_type == "PROPAGATE":
        data["nodes"] = list(event.targets or event.parts)
    elif event.event_type == "ORBIT_AROUND":
        data["type"] = "PATH_MOTION"
        data["path"] = {"kind": "orbit", "center": event.center, "radius": event.radius, "sweep": 6.283185307179586}
    elif event.event_type == "PATH_MOTION":
        # Foundation PATH_MOTION is semantic: source/destination for a line,
        # or center/radius/mode for orbit. Do not pass coordinate arrays to
        # the renderer-facing contract. Legacy fixture points are converted
        # only to a bounded line descriptor for state QA.
        params = dict(data.get("parameters") or {})
        descriptor = params.get("orbit_descriptor") if isinstance(params.get("orbit_descriptor"), Mapping) else None
        raw_path = data.get("path")
        if descriptor is not None or str(params.get("mode", "")).casefold() == "orbit":
            orbit = dict(descriptor or {})
            data["path"] = {"kind": "orbit", "center": orbit.get("center", data.get("center")), "radius": orbit.get("radius", data.get("radius", 1.0)), "plane": orbit.get("plane", "xy"), "sweep": orbit.get("sweep", 6.283185307179586)}
        elif event.source is not None or event.destination is not None:
            data["path"] = {"kind": "line", "start": event.source, "end": event.destination or event.target}
        elif isinstance(raw_path, (list, tuple)) and raw_path:
            data["path"] = {"kind": "line", "start": raw_path[0], "end": raw_path[-1]}
    elif event.event_type == "CAMERA":
        data.setdefault("parameters", {})
        params = dict(data["parameters"])
        params.setdefault("camera", _v21_camera(event.mode or scene.shot.mode, [0.0, 0.0, 0.0]))
        params.setdefault("to", {"position": _v21_camera(event.mode or scene.shot.mode, [0.0, 0.0, 0.0])["position"]})
        data["parameters"] = params
    # State QA works in the top-level object space; parts remain trusted child
    # descriptors and are intentionally not promoted to independent scene boxes.
    return data


def _v21_object_cue(object_id: str, scene: Any, anchors: Mapping[str, Any], events: list[Mapping[str, Any]]) -> int:
    for event in events:
        if object_id in _v21_event_subjects(event):
            cue = event.get("cue", 0.0)
            return max(0, int(float(cue)))
    return 0


def _v21_svg_subject(item: Any, plan: Mapping[str, Any], tokens: ResolvedDesignTokens, cue: int, event_cues: list[int] | None = None, space: Any = None) -> str:
    from .scene_space import Rect
    if space is not None:
        box = space.denormalize(item.box)
    else:
        box = Rect(item.box.x * 1280.0, item.box.y * 720.0, item.box.width * 1280.0, item.box.height * 720.0)
    forms = plan.get("svg", {}).get("forms", []) if isinstance(plan.get("svg"), Mapping) else []
    result: list[str] = []
    for form in forms:
        if isinstance(form, Mapping):
            result.append(_v21_svg_form(form, box, tokens, cue))
    label = escape(item.label, quote=True)
    label_x = max(32.0, min(1248.0, box.center_x))
    label_y = max(32.0, min(680.0, box.bottom + 24.0))
    result.append(f'<text class="v21-label" x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="middle" dominant-baseline="hanging" data-cue="{cue}">{label}</text>')
    # Preserve every semantic event anchor in the trusted body. The empty
    # anchor groups are non-rendering metadata hooks consumed by Narova's cue
    # scheduler; all visible geometry remains compiler-owned above.
    for anchor_cue in sorted(set(event_cues or ())):
        result.append(f'<g class="v21-anchor" data-cue="{anchor_cue}" aria-hidden="true"></g>')
    return "".join(result)


def _v21_svg_form(form: Mapping[str, Any], box: Any, tokens: ResolvedDesignTokens, cue: int) -> str:
    geometry = form.get("geometry") if isinstance(form.get("geometry"), Mapping) else {}
    kind = str(form.get("kind") or "shape")
    role = str(form.get("palette_role") or "secondary")
    fill = tokens.accent if role == "accent" else tokens.emphasis if role == "emphasis" else tokens.secondary
    stroke = tokens.foreground if kind in {"polyline", "arc", "axes", "particles"} else tokens.edge
    attrs = f' class="v21-form v21-{kind}" data-cue="{cue}" data-delay="{0.12 + cue * 0.08:.2f}"'
    def px(value: Any, base: float) -> float:
        try:
            return base * float(value)
        except (TypeError, ValueError):
            return 0.0
    if kind == "circle":
        center = geometry.get("center", (0.5, 0.5))
        return f'<circle{attrs} cx="{box.x + px(center[0], box.width):.2f}" cy="{box.y + px(center[1], box.height):.2f}" r="{max(4.0, px(geometry.get("radius", 0.05), min(box.width, box.height))):.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    if kind == "ellipse":
        center = geometry.get("center", (0.5, 0.5))
        return f'<ellipse{attrs} cx="{box.x + px(center[0], box.width):.2f}" cy="{box.y + px(center[1], box.height):.2f}" rx="{max(6.0, px(geometry.get("radius_x", 0.12), box.width)):.2f}" ry="{max(6.0, px(geometry.get("radius_y", 0.07), box.height)):.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    if kind == "rect":
        origin = geometry.get("origin", (0.35, 0.4))
        return f'<rect{attrs} x="{box.x + px(origin[0], box.width):.2f}" y="{box.y + px(origin[1], box.height):.2f}" width="{max(8.0, px(geometry.get("width", 0.2), box.width)):.2f}" height="{max(8.0, px(geometry.get("height", 0.12), box.height)):.2f}" rx="8" ry="8" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    points = geometry.get("points", [])
    if isinstance(points, (list, tuple)) and points:
        pairs = []
        for point in points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                pairs.append(f"{box.x + px(point[0], box.width):.2f},{box.y + px(point[1], box.height):.2f}")
        if pairs:
            tag = "polygon" if kind == "polygon" else "polyline"
            return f'<{tag}{attrs} points="{" ".join(pairs)}" fill="{fill if tag == "polygon" else "none"}" stroke="{stroke}" stroke-width="2"/>'
    if kind == "grid":
        origin = geometry.get("origin", (0.2, 0.3))
        columns = max(1, min(8, int(geometry.get("columns", 3))))
        rows = max(1, min(8, int(geometry.get("rows", 2))))
        width = px(geometry.get("cell_width", 0.08), box.width)
        height = px(geometry.get("cell_height", 0.08), box.height)
        return "".join(f'<rect{attrs} x="{box.x + px(origin[0], box.width) + col * width:.2f}" y="{box.y + px(origin[1], box.height) + row * height:.2f}" width="{max(3.0, width - 2):.2f}" height="{max(3.0, height - 2):.2f}" fill="{fill}"/>' for row in range(rows) for col in range(columns))
    center = geometry.get("center", (0.5, 0.5))
    return f'<circle{attrs} cx="{box.x + px(center[0], box.width):.2f}" cy="{box.y + px(center[1], box.height):.2f}" r="{max(3.0, min(box.width, box.height) * 0.025):.2f}" fill="{fill}"/>'


def _v21_three_subject(item: Any, plan: Mapping[str, Any], tokens: ResolvedDesignTokens, space: Any, scene: Any, events: list[Mapping[str, Any]], cue: int, object_map: Mapping[str, Any]) -> dict[str, Any] | None:
    if str(plan.get("render_mode") or "").casefold() == "svg":
        return None
    three = plan.get("three") if isinstance(plan.get("three"), Mapping) else None
    if three is None:
        return None
    groups = three.get("groups") if isinstance(three.get("groups"), list) else []
    if not groups:
        return None
    group = dict(groups[0]) if isinstance(groups[0], Mapping) else None
    if group is None:
        return None
    group["id"] = f"v21-{item.id}-group"
    group["type"] = "group"
    group["position"] = list(space.three_position(item.box, depth=item.depth))
    group["children"] = [_v21_safe_three_child(child, tokens) for child in (group.get("children") or []) if isinstance(child, Mapping)]
    animations = [dict(item) for item in group.get("animations", []) if isinstance(item, Mapping)]
    if isinstance(group.get("animate"), Mapping):
        animations.append(dict(group["animate"]))
    animations.extend(_v21_event_animations(item.id, events, item, space, object_map))
    orbit_animation = next((animation for animation in animations if animation.pop("_semantic_orbit", False)), None)
    if orbit_animation is not None:
        orbit_radius = float(orbit_animation.get("radius", 0.28))
        center_id = next((str(event.get("path", {}).get("center")) for event in events if isinstance(event.get("path"), Mapping) and event.get("path", {}).get("kind") == "orbit" and event.get("path", {}).get("center")), "")
        center_item = object_map.get(center_id)
        center_position = list(space.three_position(center_item.box, depth=center_item.depth)) if center_item is not None else [0.0, 0.0, 0.0]
        # Keep one flat group: rotating this parent around its center moves
        # every primitive child at the declared radius without nested groups.
        for child in group["children"]:
            position = child.get("position", [0.0, 0.0, 0.0])
            if isinstance(position, list) and len(position) == 3:
                child["position"] = [float(position[0]) + orbit_radius, float(position[1]), float(position[2])]
        orbit_animation = _strip_animation_metadata(orbit_animation)
        return {
            "id": group["id"],
            "type": "group",
            "position": center_position,
            "children": group["children"],
            "animate": [orbit_animation],
        }
    if animations:
        group["animate"] = [_strip_animation_metadata(animation) for animation in animations]
    else:
        group.pop("animate", None)
    group.pop("animations", None)
    group.pop("semantic_motion", None)
    return group


def _v21_safe_three_child(child: Mapping[str, Any], tokens: ResolvedDesignTokens) -> dict[str, Any]:
    primitive = str(child.get("type") or "cube")
    # Narova group children are flat primitive descriptors.  Nested groups,
    # particles, models, and renderer-owned source are not valid children.
    allowed = {"cube", "sphere", "cylinder", "plane", "torus", "cone"}
    if primitive not in allowed:
        primitive = "sphere" if str(child.get("type") or "").casefold() in {"particles", "group"} else "cube"
    result: dict[str, Any] = {"id": str(child.get("id") or "child"), "type": primitive}
    if isinstance(child.get("position"), (list, tuple)) and len(child["position"]) == 3:
        result["position"] = [float(value) for value in child["position"]]
    if isinstance(child.get("size"), (list, tuple)) and len(child["size"]) == 3:
        result["size"] = [max(0.01, min(8.0, float(value))) for value in child["size"]]
    elif isinstance(child.get("size"), (int, float)):
        result["size"] = max(0.01, min(8.0, float(child["size"])))
    if isinstance(child.get("radius"), (int, float)):
        result["radius"] = max(0.01, min(5.0, float(child["radius"])))
    if primitive == "particles":
        result["count"] = max(1, min(2000, int(child.get("count", 24))))
        spread = child.get("spread", [0.25, 0.18, 0.08])
        result["spread"] = [max(0.01, min(8.0, float(value))) for value in spread] if isinstance(spread, (list, tuple)) and len(spread) == 3 else [0.25, 0.18, 0.08]
    result["color"] = tokens.accent
    result["roughness"] = 0.24
    result["metalness"] = 0.65
    result["clearcoat"] = 0.75
    result["clearcoatRoughness"] = 0.12
    return result


def _v21_reference_position(value: Any, object_map: Mapping[str, Any], space: Any, fallback: list[float]) -> list[float]:
    if isinstance(value, str):
        item = object_map.get(value)
        if item is not None:
            return list(space.three_position(item.box, depth=item.depth))
        return list(fallback)
    if isinstance(value, Mapping):
        reference = value.get("id", value.get("object_id"))
        if reference is not None:
            return _v21_reference_position(reference, object_map, space, fallback)
        position = value.get("position", value.get("point"))
        if position is not None:
            return _v21_reference_position(position, object_map, space, fallback)
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return [float(value[index]) for index in range(3)]
        except (TypeError, ValueError):
            return list(fallback)
    return list(fallback)


def _strip_animation_metadata(animation: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"property", "from", "to", "by", "duration", "ease", "at", "wait"}
    return {key: animation[key] for key in allowed if key in animation}


def _v21_event_animations(object_id: str, events: list[Mapping[str, Any]], item: Any, space: Any, object_map: Mapping[str, Any]) -> list[dict[str, Any]]:
    animations: list[dict[str, Any]] = []
    start_position = list(space.three_position(item.box, depth=item.depth))
    for event in events:
        if object_id not in _v21_event_subjects(event):
            continue
        kind = str(event.get("type") or "").upper()
        # A transfer moves only its carrier; source/destination are anchors,
        # not additional moving objects. PATH_MOTION likewise targets its
        # declared subject.
        if kind == "TRANSFER" and object_id != str(event.get("carrier") or ""):
            continue
        if kind == "PATH_MOTION" and object_id != str(event.get("subject") or event.get("carrier") or ""):
            continue
        cue_value = float(event.get("cue", 0.0) or 0.0)
        at = {"cue": max(0, int(cue_value)), "offset": round(cue_value % 1.0, 3)}
        duration = max(0.05, min(120.0, float(event.get("duration", 1.0))))
        if kind == "PATH_MOTION":
            path = event.get("path") if isinstance(event.get("path"), Mapping) else {}
            if str(path.get("kind", "")).casefold() in {"orbit", "arc", "circular"} or str(event.get("mode", "")).casefold() == "orbit":
                radius = max(0.05, min(8.0, float(path.get("radius") or event.get("radius") or 0.28)))
                animations.append({"property": "rotation.y", "from": 0.0, "to": 6.283185, "duration": duration, "ease": "linear", "at": at, "radius": radius, "_semantic_orbit": True})
                continue
            start = _v21_reference_position(path.get("start", event.get("source")), object_map, space, start_position)
            end = _v21_reference_position(path.get("end", event.get("destination", event.get("target"))), object_map, space, start_position)
            for axis, initial, final in zip(("x", "y", "z"), start, end):
                animations.append({"property": f"position.{axis}", "from": initial, "to": final, "duration": duration, "ease": "power2.inOut", "at": at})
        elif kind == "TRANSFER":
            source = _v21_reference_position(event.get("source"), object_map, space, start_position)
            destination = _v21_reference_position(event.get("destination", event.get("target")), object_map, space, start_position)
            for axis, initial, final in zip(("x", "y", "z"), source, destination):
                animations.append({"property": f"position.{axis}", "from": initial, "to": final, "duration": duration, "ease": "power2.inOut", "at": at})
        elif kind == "GROW":
            for axis in ("x", "y", "z"):
                animations.append({"property": f"scale.{axis}", "from": 0.35, "to": 1.0, "duration": duration, "ease": "power2.out", "at": at})
        elif kind in {"ASSEMBLE", "MERGE"}:
            target = _v21_reference_position(event.get("target"), object_map, space, [0.0, 0.0, 0.0])
            for axis, initial, final in zip(("x", "y", "z"), start_position, target):
                animations.append({"property": f"position.{axis}", "from": initial, "to": final, "duration": duration, "ease": "power2.inOut", "at": at})
            if kind == "MERGE":
                animations.append({"property": "opacity", "from": 1.0, "to": 0.0, "duration": duration, "ease": "power2.in", "at": at})
        elif kind == "PROPAGATE":
            animations.append({"property": "opacity", "from": 0.35, "to": 1.0, "duration": duration, "ease": "power2.out", "at": at})
        elif kind in {"CREATE", "EMPHASIZE"}:
            animations.append({"property": "opacity", "from": 0.0, "to": 1.0, "duration": duration, "ease": "power2.out", "at": at})
    return animations


def _v21_camera(mode: Any, look_at: list[float]) -> dict[str, Any]:
    presets = {"static": [0.0, 0.0, 4.8], "focus": [0.0, 0.2, 4.2], "zoom": [0.0, 0.0, 3.6], "pan": [-1.6, 0.2, 4.8], "orbit": [2.4, 1.4, 4.8], "dolly": [0.0, 0.8, 5.8], "follow": [0.0, 0.7, 4.5]}
    return {"position": presets.get(str(mode or "focus"), presets["focus"]), "lookAt": list(look_at), "fov": 48.0, "near": 0.1, "far": 40.0}


def _v21_camera_animation(animation: Mapping[str, Any], cue: int) -> list[dict[str, Any]]:
    start = animation.get("from") if isinstance(animation.get("from"), Mapping) else {}
    end = animation.get("to") if isinstance(animation.get("to"), Mapping) else {}
    duration = float(animation.get("duration", 1.0))
    at = {"cue": cue, "offset": float(animation.get("cue", 0.0)) % 1.0}
    return _v21_camera_tweens(start, end, duration=duration, at=at)


def _v21_camera_tweens(start: Mapping[str, Any], end: Mapping[str, Any], *, duration: float, at: Mapping[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    start_position = start.get("position", [0.0, 0.0, 6.0])
    end_position = end.get("position", start_position)
    start_target = start.get("target", start.get("lookAt", [0.0, 0.0, 0.0]))
    end_target = end.get("target", end.get("lookAt", start_target))
    for axis, initial, final in zip(("x", "y", "z"), start_position, end_position):
        specs.append({"property": f"position.{axis}", "from": float(initial), "to": float(final), "duration": duration, "ease": "power2.inOut", "at": dict(at)})
    for axis, initial, final in zip(("x", "y", "z"), start_target, end_target):
        specs.append({"property": f"lookAt.{axis}", "from": float(initial), "to": float(final), "duration": duration, "ease": "power2.inOut", "at": dict(at)})
    if "fov" in start or "fov" in end:
        specs.append({"property": "fov", "from": float(start.get("fov", 48.0)), "to": float(end.get("fov", start.get("fov", 48.0))), "duration": duration, "ease": "power2.inOut", "at": dict(at)})
    return specs


def _v21_shot_camera_animations(shot: Any, camera: Mapping[str, Any], cue: int) -> list[dict[str, Any]]:
    if shot.mode == "static":
        return []
    start = {"position": [0.0, 0.0, 6.0], "target": list(camera.get("lookAt", [0.0, 0.0, 0.0]))}
    end = {"position": list(camera.get("position", [0.0, 0.0, 4.8])), "target": list(camera.get("lookAt", [0.0, 0.0, 0.0]))}
    return _v21_camera_tweens(start, end, duration=float(shot.duration or 1.0), at={"cue": cue, "offset": 0.0})


def _v21_scene_body(scene: Any, ir_scene: Any, svg_parts: list[str], tokens: ResolvedDesignTokens, space: Any, *, transparent: bool) -> str:
    stage = "v21-stage v21-clear" if transparent else "v21-stage"
    title = escape(scene.purpose, quote=True)
    objects = {item.id: item for item in ir_scene.objects}
    relations = "".join(_v21_relationship_markup(relation, objects, scene, tokens, space) for relation in ir_scene.relationships)
    return f'<div class="{stage}"><svg class="v21-scene-svg" viewBox="{space.svg_viewbox}" aria-label="{title}"><g class="v21-connections">{relations}</g><g class="v21-visuals">{"".join(svg_parts)}</g></svg></div>'


def _v21_relationship_markup(relation: Any, objects: Mapping[str, Any], scene: Any, tokens: ResolvedDesignTokens, space: Any) -> str:
    source = objects.get(relation.source)
    target = objects.get(relation.target)
    if source is None or target is None:
        return ""
    start = (source.box.center_x * space.logical_width, source.box.center_y * space.logical_height)
    end = (target.box.center_x * space.logical_width, target.box.center_y * space.logical_height)
    midpoint = (start[0] + end[0]) / 2.0
    curve = 24.0 if relation.kind in {"bypasses", "orbits"} else 0.0
    path = f"M {start[0]:.2f} {start[1]:.2f} Q {midpoint:.2f} {min(start[1], end[1]) - curve:.2f} {end[0]:.2f} {end[1]:.2f}" if curve else f"M {start[0]:.2f} {start[1]:.2f} L {end[0]:.2f} {end[1]:.2f}"
    cue = None
    total_cues = len(scene.narration_anchors) if hasattr(scene, "narration_anchors") and scene.narration_anchors else 3
    for event in scene.events:
        if relation.source in _v21_event_subjects(event.to_dict()) or relation.target in _v21_event_subjects(event.to_dict()):
            anchor = next((item for item in getattr(scene, "narration_anchors", []) if item.id == event.narration_anchor), None)
            if anchor is not None and anchor.cue_index is not None:
                cue = int(anchor.cue_index)
            break
    if cue is None:
        try:
            rel_index = next(
                index
                for index, item in enumerate(scene.relationships)
                if item.source == relation.source and item.target == relation.target and item.kind == relation.kind
            )
        except StopIteration:
            rel_index = (len(relation.source) * 31 + len(relation.target) * 17 + len(relation.kind) * 7) % max(1, total_cues)
        cue = rel_index % max(1, total_cues)
        
    return f'<path class="v21-relationship" d="{path}" fill="none" stroke="{tokens.edge}" stroke-width="{2.0 + min(3.0, float(getattr(relation, "importance", 1.0))):.2f}" data-relationship="{escape(str(relation.kind), quote=True)}" data-cue="{cue}"/>'


def _v21_narration(section: Mapping[str, Any], fallback: str) -> str:
    lines = section.get("lecture_lines")
    if isinstance(lines, list) and lines:
        return " ".join(str(line) for line in lines)
    return str(fallback or section.get("title") or "")


def _theme_css_v21(tokens: ResolvedDesignTokens) -> str:
    return f""".v21-stage {{ position:absolute; inset:0; overflow:hidden; background:{tokens.background}; color:{tokens.foreground}; }} .v21-stage.v21-clear {{ background:transparent; }} .v21-scene-svg {{ width:100%; height:100%; overflow:visible; }} .v21-form {{ vector-effect:non-scaling-stroke; }} .v21-relationship {{ vector-effect:non-scaling-stroke; opacity:.82; }} .v21-label {{ fill:{tokens.foreground}; font:600 20px/1.2 {tokens.body_font_stack}; }}"""


__all__ = ["CompiledVisualV2", "CompiledVisualProgramV21", "CompiledVisualV21", "SceneCompilerV2Error", "SceneCompilerV21Error", "compile_visual_plan_v2", "compile_visual_program_v21"]
