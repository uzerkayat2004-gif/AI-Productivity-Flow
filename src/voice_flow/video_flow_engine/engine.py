"""Agentic visual explanation engine.

This module owns the planning-to-render seam. It gives the selected model
creative authorship over executable scene graphs while keeping truth,
legibility, diversity, and render cost as hard contracts.
"""

from __future__ import annotations

import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from voice_flow.video_flow_engine.contracts import SourceInput, as_json_dict
from voice_flow.video_flow_engine.adapters import SafeHttpRetrievalAdapter
from voice_flow.video_flow_engine.director import (
    DirectorConfig, VisualDirector, _normalise_duration, _normalise_render_class,
    _normalise_timing, _spatial_depth_terms,
)
from voice_flow.video_flow_engine.diversity import CreativeFingerprint, DiversityLedger
from voice_flow.video_flow_engine.evidence import EvidenceBuilder
from voice_flow.video_flow_engine.quality import PreviewQA
from voice_flow.video_flow_engine.scheduler import normalize_manifest


ENGINE_VERSION = "agentic-visual.v1"
ALLOWED_NODE_TYPES = {
    "group", "rect", "roundRect", "ellipse", "circle", "line", "path",
    "text", "image", "chart", "network", "timeline", "media", "three",
}
ALLOWED_RENDER_CLASSES = {"static", "motion-island", "continuous-2d", "webgl-3d", "media"}


class AgenticVisualEngineError(RuntimeError):
    """Raised when authorship cannot produce a safe executable scene program."""


@dataclass(frozen=True)
class VideoIntent:
    title: str
    mode: str = "summary"
    visual_direction: str = ""
    source_name: str = ""
    requested_format: str = "explainer"
    audience: str = "general"

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "mode": self.mode,
            "visual_direction": self.visual_direction,
            "source_name": self.source_name,
            "requested_format": self.requested_format,
            "audience": self.audience,
        }


class AgenticVisualEngine:
    """Build canonical evidence, direction, QA, and executable ScenePrograms."""

    def __init__(self, model_gateway: Any, *, evidence_builder: EvidenceBuilder | None = None) -> None:
        self.model_gateway = model_gateway
        self.evidence_builder = evidence_builder or EvidenceBuilder(retrieval_adapter=SafeHttpRetrievalAdapter())
        self.qa = PreviewQA()

    def build(
        self,
        source: Any,
        *,
        intent: VideoIntent,
        model_ref: str,
        allow_external_ai: bool,
        diversity_history: Iterable[Any] | None = None,
        source_kind: str | None = None,
        source_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        history = self._history(diversity_history or [])
        metadata = dict(source_metadata or {})
        source_name = str(metadata.pop("name", "") or intent.source_name)
        source_input = SourceInput.from_any(
            source,
            kind=source_kind,
            **metadata,
        )
        if source_name:
            source_input.name = source_name
        evidence = self.evidence_builder.build(
            source_input,
            query=intent.title,
            include_source_text=True,
            strict=False,
        )
        sufficiency = dict(evidence.get("context_sufficiency") or {})
        if str(sufficiency.get("status") or "").lower() == "insufficient":
            questions = "; ".join(str(item) for item in sufficiency.get("questions") or [])
            raise AgenticVisualEngineError(
                "The source does not contain enough grounded context to author an explanation."
                + (f" Needed: {questions}" if questions else "")
            )

        intent_data = intent.to_dict()
        explicit_spatial = _spatial_depth_terms(intent.visual_direction)
        source_text = json.dumps(evidence, ensure_ascii=False, default=str)
        spatial_required = bool(explicit_spatial and _spatial_depth_terms(source_text))
        intent_data["spatial_depth_requested"] = explicit_spatial
        intent_data["spatial_depth_required"] = spatial_required

        generate = self._generator(model_ref, allow_external_ai)
        director = VisualDirector(
            model_generate=generate,
            config=DirectorConfig(minimum_scenes=2, maximum_scenes=48, diversity_window=10),
        )
        direction = director.create(
            evidence,
            source={
                "kind": source_input.kind,
                "name": source_input.name,
                "mime_type": source_input.mime_type,
                "uri": source_input.uri,
                "metadata": as_json_dict(source_input.metadata),
                "raw_value_redacted": True,
            },
            request=intent_data,
            diversity_history=history,
            user_direction=intent.visual_direction,
        )
        qa_report = self.qa.inspect(direction, evidence=evidence, history=history)
        if not qa_report.get("passed") and qa_report.get("repair_instructions"):
            direction = director.repair(
                direction,
                qa_report,
                model_generate=generate,
                max_scenes=min(6, len(qa_report.get("repair_instructions") or [])),
            )
            qa_report = self.qa.inspect(direction, evidence=evidence, history=history)
        if not qa_report.get("passed"):
            issue_codes = ", ".join(
                str(item.get("code") or "quality-error")
                for item in qa_report.get("issues") or []
                if isinstance(item, Mapping) and item.get("severity") == "error"
            )
            raise AgenticVisualEngineError(
                "The visual direction did not pass the quality constitution after targeted repair"
                + (f": {issue_codes}" if issue_codes else ".")
            )

        fingerprint = CreativeFingerprint.from_artifacts(direction)
        diversity = DiversityLedger(history=history).review(fingerprint)
        if not diversity.get("accepted", not diversity.get("is_repeat", False)):
            direction = director.repair(
                direction,
                {
                    "repair_instructions": [
                        {
                            "scene_id": str(scene.get("id") or ""),
                            "action": (
                                "Re-author the scene's visual construction, spatial reading path, mark vocabulary, "
                                "and choreography. Preserve narration and evidence; do not merely recolor."
                            ),
                        }
                        for scene in list(direction.get("scenes") or [])[:6]
                    ]
                },
                model_generate=generate,
                max_scenes=6,
            )
            fingerprint = CreativeFingerprint.from_artifacts(direction)
            diversity = DiversityLedger(history=history).review(fingerprint)

        manifest = self._compile_scene_programs(
            evidence=evidence,
            direction=direction,
            intent=intent,
            generate=generate,
            diversity=diversity,
        )
        manifest = self._validate_manifest(manifest)
        manifest["evidencePack"] = evidence
        compiled_qa = self.qa.inspect(manifest, evidence=evidence, history=history)
        if not compiled_qa.get("passed"):
            codes = ", ".join(
                str(item.get("code") or "compiled-quality-error")
                for item in compiled_qa.get("issues") or []
                if isinstance(item, Mapping) and item.get("severity") == "error"
            )
            raise AgenticVisualEngineError(
                "Compiled Scene Programs failed quality review" + (f": {codes}" if codes else ".")
            )
        compiled_artifacts = {
            "treatment": direction.get("treatment") or {},
            "scenes": manifest.get("scenes") or [],
        }
        fingerprint = CreativeFingerprint.from_artifacts(compiled_artifacts)
        diversity = DiversityLedger(history=history).review(fingerprint)
        if not diversity.get("accepted", True):
            repaired_direction = copy.deepcopy(dict(direction))
            for scene in repaired_direction.get("scenes") or []:
                if isinstance(scene, dict):
                    scene["anti_repeat_instruction"] = (
                        "The first executable construction matched recent videos. Change hierarchy, topology, "
                        "dominant geometry, spatial reading path, mark vocabulary, camera, and choreography. "
                        "Preserve narration and evidence. Recoloring alone is forbidden."
                    )
                    scene["repeated_dimensions"] = list(diversity.get("repeated_dimensions") or [])
            manifest = self._compile_scene_programs(
                evidence=evidence,
                direction=repaired_direction,
                intent=intent,
                generate=generate,
                diversity=diversity,
            )
            manifest = self._validate_manifest(manifest)
            fingerprint = CreativeFingerprint.from_artifacts(
                {
                    "treatment": repaired_direction.get("treatment") or {},
                    "scenes": manifest.get("scenes") or [],
                }
            )
            diversity = DiversityLedger(history=history).review(fingerprint)
            if not diversity.get("accepted", True):
                raise AgenticVisualEngineError(
                    "The visual author repeated a recent structural fingerprint after targeted re-authoring."
                )
            direction = repaired_direction
        manifest["evidencePack"] = evidence
        compiled_qa = self.qa.inspect(manifest, evidence=evidence, history=history)
        if not compiled_qa.get("passed"):
            codes = ", ".join(
                str(item.get("code") or "compiled-quality-error")
                for item in compiled_qa.get("issues") or []
                if isinstance(item, Mapping) and item.get("severity") == "error"
            )
            raise AgenticVisualEngineError(
                "Final Scene Programs failed quality review" + (f": {codes}" if codes else ".")
            )
        manifest["creativeTreatment"] = direction.get("treatment") or direction.get("creative_treatment") or {}
        manifest["semanticStoryboard"] = direction.get("storyboard") or direction.get("semantic_storyboard") or {}
        compiled_qa["direction_qa"] = qa_report
        manifest["qaReport"] = compiled_qa
        manifest["creativeFingerprint"] = fingerprint.to_mapping(include_signature=True, aliases=True)
        manifest["diversityReport"] = diversity
        manifest["planningModel"] = manifest.pop("planning_model", model_ref)
        manifest["requestedModel"] = model_ref
        return normalize_manifest(manifest)

    def _generator(self, model_ref: str, allow_external_ai: bool) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
        def generate(context: Mapping[str, Any]) -> dict[str, Any]:
            prompt = str(context.get("raw_prompt") or "") or self._direction_prompt(context)
            return self.model_gateway.generate_structured(
                prompt,
                model_ref,
                allow_external_ai=allow_external_ai,
            )
        return generate

    @staticmethod
    def _history(history: Iterable[Any]) -> list[Any]:
        result: list[Any] = []
        for item in history:
            if isinstance(item, Mapping):
                candidate = item.get("creative_fingerprint") or item.get("creativeFingerprint") or item.get("video_signature") or item
                if isinstance(candidate, str):
                    try:
                        candidate = json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
                if isinstance(candidate, Mapping):
                    result.append(candidate)
            else:
                result.append(item)
        return result[-10:]

    @staticmethod
    def _direction_prompt(context: Mapping[str, Any]) -> str:
        compact = copy.deepcopy(dict(context))
        evidence = dict(compact.get("evidence_pack") or {})
        normalized = dict(evidence.get("normalized_source") or {})
        if len(str(normalized.get("text") or "")) > 100_000:
            normalized["text"] = str(normalized["text"])[:100_000]
        evidence["normalized_source"] = normalized
        compact["evidence_pack"] = evidence
        return """You are the lead visual director for a world-class explanatory video.
Return JSON only. You are authoring meaning, not selecting a template.

OUTPUT:
{
  "treatment": {
    "genre": "content-specific genre",
    "emotional_register": "...",
    "visual_world": "a concrete world unique to this source",
    "material_language": "...",
    "palette_roles": {"background":"#...","primary_text":"#...","secondary_text":"#...","accent":["#..."],"semantic_roles":{}},
    "typography": {"category":"...","hierarchy":["..."],"character":"..."},
    "illustration_strategy": "...",
    "motion_personality": "...",
    "camera_grammar": "...",
    "transition_logic": "...",
    "anti_patterns": ["specific things this video must not repeat"]
  },
  "scenes": [{
    "id":"scene-1",
    "viewer_question":"one question",
    "purpose":"one purpose",
    "intended_understanding":"one mental-model change",
    "evidence_refs":["exact claim ids"],
    "narration":"spoken explanation",
    "duration_seconds":8,
    "visible_entities":["concrete source-grounded objects"],
    "composition_intent":{"dominant_idea":"...","reading_path":"...","spatial_relationships":"..."},
    "motion_purpose":"what change/direction/cause/relationship motion explains",
    "motion_events":[{"action":"...","purpose":"..."}],
    "semantic_timings":[{"label":"...","start_ratio":0.0,"end_ratio":0.3}],
    "render_class":"static|motion-island|continuous-2d|webgl-3d|media",
    "estimated_cost":12
  }]
}

Rules:
- Derive a different genre, visual world, palette, spatial logic, and motion personality from this exact source.
- Never output a dashboard, card grid, fixed slide family, notebook imitation, or reusable completed layout.
- One dominant visual explanation per scene. Show relationships and changes instead of paragraphs.
- Motion must explain cause, change, direction, hierarchy, focus, comparison, time, quantity, or relationship.
- Every factual narration and visual maps to evidence_refs. Mark uncertainty; never invent missing context.
- Keep on-screen words sparse. Narration carries detail.
- 3D is allowed only when depth, assembly, spatial mechanism, or scale materially improves understanding.
- Recent fingerprints are negative constraints: change structure and choreography, not just colors.

CONTEXT:
""" + json.dumps(compact, ensure_ascii=False, separators=(",", ":"), default=str)

    def _compile_scene_programs(
        self,
        *,
        evidence: Mapping[str, Any],
        direction: Mapping[str, Any],
        intent: VideoIntent,
        generate: Callable[[Mapping[str, Any]], dict[str, Any]],
        diversity: Mapping[str, Any],
    ) -> dict[str, Any]:

        briefs = list(direction.get("scenes") or [])
        if not briefs:
            raise AgenticVisualEngineError("The director returned no semantic scene briefs.")
        spatial_requested = bool(direction.get("spatial_depth_requested", False)) or _spatial_depth_terms(intent.visual_direction)
        spatial_required = bool(direction.get("spatial_depth_required", False))
        intent_payload = intent.to_dict()
        intent_payload["spatial_depth_requested"] = spatial_requested
        intent_payload["spatial_depth_required"] = spatial_required
        shared = {
            "phase": "scene-program-compiler",
            "intent": intent_payload,
            "spatial_depth_requested": spatial_requested,
            "spatial_depth_required": spatial_required,
            "required_spatial_contract": (
                {"at_least_one_scene": True, "render_class": "webgl-3d", "node_type": "three"}
                if spatial_required
                else {}
            ),
            "treatment": direction.get("treatment") or {},
            "claim_ids": [item.get("id") for item in evidence.get("claims") or []],
            "entities": evidence.get("entities") or [],
            "relationships": evidence.get("relationships") or [],
            "diversity_report": diversity,
        }
        batches = [(index, briefs[index:index + 2]) for index in range(0, len(briefs), 2)]
        compiled: dict[int, list[dict[str, Any]]] = {}
        planning_model = ""

        def author(batch_index: int, batch: list[Any]) -> tuple[int, dict[str, Any]]:
            payload = {**shared, "scene_index_start": batch_index, "scenes": batch}
            response = generate({"raw_prompt": self._compiler_prompt(payload)})
            for key in ("manifest", "scene_program", "sceneProgram", "result"):
                if isinstance(response.get(key), Mapping) and response[key].get("scenes"):
                    response = dict(response[key])
                    break
            return batch_index, response

        workers = min(4, len(batches))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="video-flow-scenes") as executor:
            futures = {
                executor.submit(author, batch_index, batch): (batch_index, len(batch))
                for batch_index, batch in batches
            }
            for future in as_completed(futures):
                batch_index, expected = futures[future]
                _, response = future.result()
                batch = briefs[batch_index:batch_index + expected]
                scenes = [dict(item) for item in response.get("scenes") or [] if isinstance(item, Mapping)]
                if len(scenes) != expected:
                    raise AgenticVisualEngineError(
                        f"Scene author returned {len(scenes)} programs for {expected} briefs at index {batch_index}."
                    )
                for offset, (scene, brief_value) in enumerate(zip(scenes, batch)):
                    brief = dict(brief_value) if isinstance(brief_value, Mapping) else {}
                    narration = str(brief.get("narration") or brief.get("spoken_text") or scene.get("narration") or scene.get("voiceover") or "").strip()
                    if not narration:
                        raise AgenticVisualEngineError(
                            f"Semantic brief {batch_index + offset + 1} has no grounded narration."
                        )
                    scene = self._normalise_compiled_scene(scene, brief, batch_index + offset)
                    scene["id"] = str(brief.get("id") or brief.get("scene_id") or scene.get("id") or f"scene-{batch_index + offset + 1}")
                    scene["narration"] = narration
                    scene["evidence_refs"] = [str(item) for item in brief.get("evidence_refs") or brief.get("truth_references") or [] if str(item)]
                    scene["viewer_question"] = str(brief.get("viewer_question") or brief.get("question") or scene.get("viewer_question") or "")
                    scene["purpose"] = str(brief.get("purpose") or scene.get("purpose") or "")
                    scene["intended_understanding"] = str(brief.get("intended_understanding") or scene.get("intended_understanding") or "")
                    scene["motion_purpose"] = str(brief.get("motion_purpose") or brief.get("motionPurpose") or scene.get("motion_purpose") or "")
                    scene["motion_events"] = list(brief.get("motion_events") or brief.get("motionEvents") or scene.get("motion_events") or [])
                    scene["estimated_cost"] = float(brief.get("estimated_cost") or brief.get("estimatedCost") or scene.get("estimated_cost") or 0.0)
                    metadata = dict(scene.get("metadata") or {})
                    metadata["purpose"] = str(brief.get("purpose") or brief.get("intended_understanding") or metadata.get("purpose") or "")
                    metadata["evidenceRefs"] = list(scene["evidence_refs"])
                    scene["metadata"] = metadata
                    scenes[offset] = scene
                compiled[batch_index] = scenes
                planning_model = planning_model or str(response.get("planning_model") or "")
        ordered = [scene for batch_index, _ in batches for scene in compiled[batch_index]]
        if spatial_required and not any(self._scene_has_spatial_depth(scene) for scene in ordered):
            raise AgenticVisualEngineError(
                "Compiler contract violation: explicit 3D direction and source-grounded spatial depth require at least one webgl-3d/three scene."
            )
        return {
            "engineVersion": ENGINE_VERSION,
            "title": intent.title,
            "fps": 24,
            "width": 1920,
            "height": 1080,
            "scenes": ordered,
            "planning_model": planning_model,
        }
    @staticmethod
    def _normalise_node(value: Mapping[str, Any]) -> dict[str, Any]:
        data = copy.deepcopy(dict(value))
        raw_type = str(data.get("type") or data.get("node_type") or data.get("nodeType") or data.get("kind") or "")
        node_aliases = {"3d": "three", "webgl": "three", "threejs": "three", "round_rect": "roundRect", "rounded_rect": "roundRect"}
        data["type"] = node_aliases.get(raw_type.lower(), raw_type)
        children = data.get("children")
        if children is None:
            children = data.get("nodes") or data.get("items") or []
        data["children"] = [
            AgenticVisualEngine._normalise_node(child)
            for child in children
            if isinstance(child, Mapping)
        ]
        return data

    @staticmethod
    def _normalise_compiled_scene(value: Mapping[str, Any], brief: Mapping[str, Any], index: int) -> dict[str, Any]:
        scene = copy.deepcopy(dict(value))
        narration = str(brief.get("narration") or brief.get("spoken_text") or scene.get("narration") or scene.get("voiceover") or "")
        duration_source = brief if any(key in brief for key in ("duration_seconds", "durationSeconds", "duration", "duration_in_seconds", "durationInSeconds", "length", "seconds")) else scene
        duration = _normalise_duration(duration_source, narration, minimum=2.5, maximum=24.0)
        scene["durationSeconds"] = duration
        raw_frames = brief.get("duration_in_frames") or brief.get("durationInFrames") or scene.get("durationInFrames") or scene.get("duration_in_frames") or scene.get("frames")
        try:
            scene["durationInFrames"] = max(1, int(round(float(raw_frames)))) if raw_frames else max(1, int(round(duration * 24)))
        except (TypeError, ValueError):
            scene["durationInFrames"] = max(1, int(round(duration * 24)))
        scene["id"] = str(brief.get("id") or brief.get("scene_id") or brief.get("sceneId") or scene.get("id") or f"scene-{index + 1}")
        scene["renderClass"] = _normalise_render_class(
            brief.get("render_class") or brief.get("renderClass") or scene.get("renderClass") or scene.get("render_class") or "motion-island"
        )
        root = scene.get("root") or scene.get("scene_graph") or scene.get("sceneGraph") or scene.get("graph") or scene.get("node")
        if isinstance(root, Mapping):
            scene["root"] = AgenticVisualEngine._normalise_node(root)
        raw_timings = brief.get("semantic_timings") or brief.get("semanticTimings") or brief.get("narration_anchors") or brief.get("narrationAnchors") or brief.get("narration_timing") or brief.get("narrationTiming") or scene.get("semantic_timings") or scene.get("semanticTimings") or scene.get("narrationAnchors")
        if raw_timings is not None and list(raw_timings if isinstance(raw_timings, (list, tuple)) else [raw_timings]):
            scene["semantic_timings"] = _normalise_timing(raw_timings, duration, narration, [])
        return scene

    @staticmethod
    def _scene_has_spatial_depth(scene: Mapping[str, Any]) -> bool:
        if _normalise_render_class(scene.get("renderClass") or scene.get("render_class")) == "webgl-3d":
            return True
        def contains_three(value: Any) -> bool:
            if not isinstance(value, Mapping):
                return False
            if str(value.get("type") or "").lower() == "three":
                return True
            return any(contains_three(child) for child in value.get("children") or [])
        return contains_three(scene.get("root") or {})

    @staticmethod
    def _compiler_prompt(payload: Mapping[str, Any]) -> str:
        return """You are Scene Studio, an expert Remotion scene author.
Return one JSON object only. Compile every semantic brief into an ORIGINAL executable scene graph.
Do not choose from layouts or copy one scene graph across scenes. The semantic brief controls composition.

TOP LEVEL:
{"engineVersion":"agentic-visual.v1","title":"...","fps":24,"width":1920,"height":1080,"scenes":[SCENE...]}

SCENE:
{"id":"scene-1","title":"...","fps":24,"width":1920,"height":1080,
"durationInFrames":192,"durationSeconds":8,"narration":"exact brief narration",
"renderClass":"static|motion-island|continuous-2d|webgl-3d|media","background":"#hex",
"root":NODE,"anchors":[{"id":"concept-id","start":0,"end":48,"tags":["meaning"]}],
"camera":{"x":0,"y":0,"zoom":1},"assets":[],"metadata":{"purpose":"...","evidenceRefs":["..."]},
"motionPlan":{"renderWindows":[{"startFrame":0,"endFrame":72,"mode":"motion-island"}],
"transition":{"type":"fade|wipe|slide|match|cut","kind":"same value","durationInFrames":6}}}

NODE is recursive:
{"id":"unique","type":"group|rect|roundRect|ellipse|circle|line|path|text|image|chart|network|timeline|media|three",
"layout":{"mode":"absolute|flow","position":"absolute|relative","x":0,"y":0,"width":100,"height":100,
"direction":"row|column","gap":10,"padding":10,"align":"start|center|end|stretch","justify":"start|center|end|space-between"},
"transform":{"x":0,"y":0,"scale":1,"rotate":0,"perspective":900},
"style":{"fill":"#hex","opacity":1,"borderRadius":20,"fontFamily":"Arial","fontSize":48,"fontWeight":600,"color":"#hex"},
"motion":{"enter":{"from":0,"to":1,"start":0,"end":18,"easing":"easeOut"},
"keyframes":{"opacity":[{"at":0,"value":0},{"at":18,"value":1}],"left":[{"at":0,"value":-100},{"at":36,"value":0}]}},
"anchors":["concept-id"],"children":[NODE...]}

Payloads: text={"text":{"text":"short label","role":"title|heading|body|label|caption","maxLines":2,"fit":"shrink"}};
path={"path":{"d":"SVG path","progress":{"op":"anchor","id":"concept-id","field":"progress"},"markerEnd":"arrow"}};
chart={"chart":{"kind":"bar|line|area|pie|donut","data":[{"label":"A","value":10,"color":"#hex"}],"animate":"frame/40"}};
network={"network":{"nodes":[{"id":"a","label":"A","x":100,"y":100}],"edges":[{"from":"a","to":"b","directed":true,"progress":"frame/40"}]}};
timeline={"timeline":{"items":[{"id":"a","label":"A","start":0,"end":10}],"now":"frame/24"}};
three={"three":{"primitive":"box|sphere|cylinder|torus|plane","dimensions":[1,1,1],"color":"#hex","roughness":0.7,
"rotation":[0,"frame/90",0],"position":[0,0,0],"illustrative":false}}.

Frame expressions may be numbers; strings using frame,fps,duration and arithmetic; or objects:
{"op":"interpolate","input":"frame","inputRange":[0,24],"outputRange":[0,1]},
{"op":"spring","frame":"frame","from":0,"to":1,"duration":30},
{"op":"anchor","id":"concept-id","field":"progress"}.
All animation must be frame-driven and deterministic. Never use CSS animation or transition.

Quality constitution:
- Preserve exact narration and evidence refs. Never invent facts, numbers, logos, quotes, or unavailable assets.
- Use strong hierarchy, safe margins, rich intentional color, readable contrast, and at most 36 visible words at once.
- Create concrete explanatory mechanisms: spatial causality, transformations, flows, comparisons, maps, cutaways,
  diagrams, physical metaphors, data, scale, or 3D mechanisms when justified.
- No generic UI cards, glass dashboards, cartoon decorations, arbitrary floating/pulsing, or identical scene shells.
- Each scene must have a visibly distinct construction while the treatment gives video-wide coherence.
- renderWindows include every frame interval with meaningful motion; holds outside them are assembled cheaply.
- Keep element count proportional to meaning. Prefer vectors and primitives; use 3D only for spatial explanation.
- When spatial_depth_required is true in INPUT, compile at least one scene with renderClass webgl-3d and a meaningful root node of type three (or a nested three node). When false, do not add ornamental 3D.

INPUT:
""" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
        manifest = copy.deepcopy(dict(value))
        scenes = manifest.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise AgenticVisualEngineError("The scene author returned no executable scenes.")
        manifest.update({"engineVersion": ENGINE_VERSION, "fps": 24, "width": 1920, "height": 1080})
        seen: set[str] = set()
        for index, raw in enumerate(scenes):
            if not isinstance(raw, Mapping):
                raise AgenticVisualEngineError(f"Scene {index + 1} is not a scene program.")
            scene = AgenticVisualEngine._normalise_compiled_scene(raw, raw, index)
            scene_id = str(scene.get("id") or f"scene-{index + 1}")
            if scene_id in seen:
                raise AgenticVisualEngineError(f"Duplicate scene id: {scene_id}")
            seen.add(scene_id)
            scene["id"] = scene_id
            if not str(scene.get("narration") or "").strip():
                raise AgenticVisualEngineError(f"{scene_id} has no narration.")
            render_class = str(scene.get("renderClass") or "motion-island")
            if render_class not in ALLOWED_RENDER_CLASSES:
                raise AgenticVisualEngineError(f"{scene_id} has unsupported render class {render_class}.")
            scene["renderClass"] = render_class
            root = scene.get("root")
            if not isinstance(root, Mapping):
                raise AgenticVisualEngineError(f"{scene_id} has no executable root scene graph.")
            count, depth = AgenticVisualEngine._validate_node(root, path=f"{scene_id}.root")
            if count > 450 or depth > 18:
                raise AgenticVisualEngineError(f"{scene_id} exceeds the safe scene-graph budget ({count} nodes, depth {depth}).")
            scene.setdefault("durationSeconds", max(2.5, min(24.0, len(str(scene["narration"]).split()) * 0.36)))
            scene.setdefault("durationInFrames", int(float(scene["durationSeconds"]) * 24))
            scene.setdefault("fps", 24)
            scene.setdefault("width", 1920)
            scene.setdefault("height", 1080)
            scenes[index] = scene
        manifest["scenes"] = scenes
        return manifest

    @staticmethod
    def _validate_node(node: Mapping[str, Any], *, path: str, depth: int = 1) -> tuple[int, int]:
        node_type = str(node.get("type") or "")
        if node_type not in ALLOWED_NODE_TYPES:
            raise AgenticVisualEngineError(f"{path} has unsupported node type '{node_type}'.")
        if not str(node.get("id") or ""):
            raise AgenticVisualEngineError(f"{path} has no stable id.")
        source = node.get("src")
        if isinstance(source, str) and re.match(r"^(?:https?|blob):", source, re.I):
            raise AgenticVisualEngineError(f"{path}.src must reference a declared local asset, not a remote URL.")
        media = node.get("media")
        if isinstance(media, Mapping):
            source = media.get("src")
            if isinstance(source, str) and re.match(r"^(?:https?|blob):", source, re.I):
                raise AgenticVisualEngineError(f"{path}.media.src must reference a declared local asset, not a remote URL.")
        total = 1
        maximum = depth
        children = node.get("children") or []
        if not isinstance(children, list):
            raise AgenticVisualEngineError(f"{path}.children must be an array.")
        for index, child in enumerate(children):
            if not isinstance(child, Mapping):
                raise AgenticVisualEngineError(f"{path}.children[{index}] is not a node.")
            child_total, child_depth = AgenticVisualEngine._validate_node(child, path=f"{path}.children[{index}]", depth=depth + 1)
            total += child_total
            maximum = max(maximum, child_depth)
        return total, maximum
