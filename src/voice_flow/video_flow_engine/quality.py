"""Deterministic preview QA and targeted repair planning.

Preview QA is intentionally cheap and inspectable.  It runs before a final
render and checks the contracts a visual critic should never leave implicit:
truth references, one scene purpose, readable text, contrast, purposeful
motion, narration alignment, render cost, and repeated structures.  The
result is a mapping-shaped report so a multimodal critic or the canonical QA
dataclasses can be layered on later without changing the deterministic gate.
"""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .director import (
    ArtifactMap, _artifact, _list, _mapping, _normalise_duration, _normalise_render_class,
    _normalise_timing, _pick, _safe_float, _text,
)
from .diversity import CreativeFingerprint, DiversityLedger, structural_scene_fingerprint


def _camel(name: str) -> str:
    bits = name.split("_")
    return bits[0] + "".join(bit.title() for bit in bits[1:])


def _get(value: Any, *names: str, default: Any = None) -> Any:
    data = _mapping(value)
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
        camel = _camel(name)
        if camel in data and data[camel] is not None:
            return data[camel]
    return default


def _word_count(value: Any) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", _text(value)))


def _char_count(value: Any) -> int:
    return len(re.sub(r"\s+", " ", _text(value)).strip())


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _hex_rgb(value: Any) -> tuple[int, int, int] | None:
    text = _text(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return None
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _relative_luminance(value: Any) -> float | None:
    rgb = _hex_rgb(value)
    if rgb is None:
        return None
    channels = []
    for channel in rgb:
        normalized = channel / 255.0
        channels.append(normalized / 12.92 if normalized <= 0.03928 else ((normalized + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground: Any, background: Any) -> float | None:
    """Compute WCAG contrast when both colors are explicit hex/RGB values."""

    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    if first is None or second is None:
        return None
    light, dark = max(first, second), min(first, second)
    return round((light + 0.05) / (dark + 0.05), 3)


@dataclass(frozen=True)
class QualityConfig:
    normal_text_contrast: float = 4.5
    large_text_contrast: float = 3.0
    max_visible_words: int = 42
    max_visible_chars: int = 280
    max_elements: int = 180
    max_scene_cost: float = 90.0
    max_cost_by_class: Mapping[str, float] = field(
        default_factory=lambda: {
            "static-editorial": 24.0,
            "motion-island": 54.0,
            "continuous-2d": 90.0,
            "3d/webgl": 120.0,
            "existing-media": 100.0,
        }
    )
    repeated_structure_threshold: float = 0.78
    history_similarity_threshold: float = 0.72
    max_repairs: int = 20


class PreviewQA:
    """Run deterministic, scene-local checks over preview artifacts."""

    FORBIDDEN_MOTION = {
        "float", "floating", "bounce", "bouncing", "pulse", "pulsing", "parallax", "drift", "camera drift",
        "random", "wiggle", "idle", "decorative", "autonomous", "shader drift",
    }
    MOTION_PURPOSE_TERMS = {
        "cause", "change", "direction", "hierarchy", "focus", "compare", "comparison", "time", "relationship",
        "sequence", "quantity", "scale", "reveal", "trace", "connect", "transform", "resolve", "explain",
    }

    def __init__(self, config: QualityConfig | None = None, **overrides: Any) -> None:
        self.config = config or QualityConfig()
        if overrides:
            values = {field_name: getattr(self.config, field_name) for field_name in self.config.__dataclass_fields__}
            values.update({key: value for key, value in overrides.items() if key in values})
            self.config = QualityConfig(**values)

    def inspect(
        self,
        project: Any = None,
        previews: Any = None,
        *,
        evidence: Any = None,
        treatment: Any = None,
        history: Iterable[Any] | None = None,
        diversity_history: Iterable[Any] | None = None,
        request: Any = None,
        **kwargs: Any,
    ) -> ArtifactMap:
        """Inspect a project or direction package before final rendering.

        ``project`` may be a canonical ProjectSnapshot, a direction package,
        or a bare scene list.  ``previews`` may be a scene-id mapping, a list
        of preview artifacts, or a single preview carrying ``scene_id``.
        """

        package = ArtifactMap(_artifact(_mapping(project)))
        if isinstance(project, Sequence) and not isinstance(project, (str, bytes, bytearray, Mapping)):
            package = ArtifactMap({"scenes": [_artifact(item) for item in project]})
        scenes = [self._normalise_scene_for_qa(scene) for scene in self._scenes(package)]
        preview_map = self._preview_map(previews)
        treatment_data = _mapping(treatment) if treatment is not None else _mapping(_get(package, "treatment", "creative_treatment", "creativeTreatment", default={}))
        evidence_data = _mapping(evidence) if evidence is not None else _mapping(_get(package, "evidence_pack", "evidencePack", "evidence", default={}))
        claim_ids = self._claim_ids(evidence_data, package)
        all_history = diversity_history if diversity_history is not None else history
        issues: list[ArtifactMap] = []
        checks: list[ArtifactMap] = []
        for index, scene in enumerate(scenes):
            scene_data = scene
            scene_id = _text(_get(scene_data, "id", "scene_id", "sceneId", default=f"scene-{index + 1}")) or f"scene-{index + 1}"
            preview = preview_map.get(scene_id, ArtifactMap())
            scene_issues, scene_checks = self._inspect_scene(scene_data, preview, scene_id, claim_ids, evidence_data)
            issues.extend(scene_issues)
            checks.extend(scene_checks)

        issues.extend(self._check_repeated_scenes(scenes))
        spatial_required = bool(_get(package, "spatial_depth_required", "spatialDepthRequired", default=False))
        if spatial_required:
            if any(self._scene_has_spatial_depth(scene) for scene in scenes):
                checks.append(self._check("spatial-depth", "project", True, "At least one scene declares a webgl-3d render class or three node."))
            else:
                issues.append(
                    self._issue(
                        "spatial-depth-missing",
                        "error",
                        "project",
                        "The source and explicit user direction require a spatial-depth explanation, but no scene uses webgl-3d or a three node.",
                        "Re-author one scene as webgl-3d with a meaningful three node; preserve the grounded narration and evidence references.",
                    )
                )
        if all_history is not None:
            issues.extend(self._check_history(package, treatment_data, scenes, all_history))
        # A package with no scenes is not a valid storyboard, even though it
        # may have a perfectly valid treatment object.
        if not scenes:
            issues.append(self._issue("scene-purpose-missing", "error", "project", "No semantic scene briefs were supplied.", "Author at least one scene brief with a viewer question and intended understanding."))

        error_count = sum(1 for issue in issues if issue.get("severity") == "error")
        warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
        score = max(0.0, round(1.0 - error_count * 0.12 - warning_count * 0.035, 3))
        repair_instructions = [issue["repair"] for issue in issues if issue.get("repair")]
        report = ArtifactMap(
            {
                "version": "preview-qa.v1",
                "passed": error_count == 0,
                "quality_score": score,
                "issues": issues,
                "findings": issues,
                "checks": checks,
                "repair_instructions": repair_instructions[: self.config.max_repairs],
                "error_count": error_count,
                "warning_count": warning_count,
                "scene_count": len(scenes),
                "history_checked": all_history is not None,
                "deterministic": True,
                "multimodal_review_required": bool(kwargs.get("require_multimodal", False)),
            }
        )
        return report

    # Common aliases used by quality/runtime adapters.
    check = inspect
    run = inspect
    evaluate = inspect

    def repair_instructions(self, report: Any) -> list[ArtifactMap]:
        data = _mapping(report)
        return [ArtifactMap(_artifact(_mapping(item))) for item in _list(_get(data, "repair_instructions", "repairs", "instructions", default=[]))]

    def repair(self, project: Any, report: Any) -> ArtifactMap:
        """Attach targeted deterministic actions without rewriting scenes.

        This is intentionally an instruction pass, not an authoring pass.  A
        SceneStudio may consume ``repair_actions`` and regenerate only the
        affected scene; truth references and narration remain untouched here.
        """

        package = ArtifactMap(_artifact(_mapping(project)))
        instructions = self.repair_instructions(report)
        by_scene: dict[str, list[ArtifactMap]] = {}
        for instruction in instructions:
            scene_id = _text(_get(instruction, "scene_id", "sceneId", "id", default="project")) or "project"
            by_scene.setdefault(scene_id, []).append(instruction)
        scenes = [self._normalise_scene_for_qa(scene) for scene in self._scenes(package)]
        updated: list[ArtifactMap] = []
        targeted: list[str] = []
        for index, scene in enumerate(scenes):
            scene_data = scene
            scene_id = _text(_get(scene_data, "id", "scene_id", "sceneId", default=f"scene-{index + 1}")) or f"scene-{index + 1}"
            relevant = by_scene.get(scene_id, [])
            if relevant:
                targeted.append(scene_id)
                prior = [_text(item) for item in _list(_get(scene_data, "repair_actions", "repairActions", default=[])) if _text(item)]
                actions = [
                    _text(_get(item, "action", "instruction", "message", "repair", default=""))
                    for item in relevant
                ]
                scene_data["repair_actions"] = list(dict.fromkeys([*prior, *[action for action in actions if action]]))
                scene_data["repair_diagnostics"] = ArtifactMap(
                    {
                        "issue_codes": list(dict.fromkeys(_text(_get(item, "code", "issue_code", "issueCode", default="")) for item in relevant if _text(_get(item, "code", "issue_code", "issueCode", default="")))),
                        "preserve_truth_references": True,
                        "preserve_narration": True,
                        "full_video_regenerated": False,
                    }
                )
            updated.append(scene_data)
        package["scenes"] = updated
        package["scene_briefs"] = updated
        for key in ("storyboard", "semantic_storyboard", "semanticStoryboard"):
            if key in package:
                storyboard = ArtifactMap(_artifact(_mapping(package[key])))
                storyboard["scenes"] = updated
                package[key] = storyboard
        package["repair_plan"] = ArtifactMap(
            {
                "instructions": instructions[: self.config.max_repairs],
                "targeted_scene_ids": targeted,
                "preserve_unaffected_scenes": True,
                "full_video_regenerated": False,
            }
        )
        return package

    def _scenes(self, package: Mapping[str, Any]) -> list[Any]:
        scenes = _get(package, "scenes", "scene_briefs", "sceneBriefs", default=None)
        if scenes is None:
            storyboard = _get(package, "storyboard", "semantic_storyboard", "semanticStoryboard", default={})
            scenes = _get(storyboard, "scenes", "scene_briefs", "sceneBriefs", default=[])
        return _list(scenes)

    def _preview_map(self, previews: Any) -> dict[str, ArtifactMap]:
        if previews is None:
            return {}
        if isinstance(previews, Mapping):
            # A single preview has fields such as scene_id/frame; a mapping of
            # IDs has nested preview objects.
            if _get(previews, "scene_id", "sceneId", "id", default=None) is not None:
                scene_id = _text(_get(previews, "scene_id", "sceneId", "id", default=""))
                return {scene_id: ArtifactMap(_artifact(_mapping(previews)))} if scene_id else {}
            return {str(key): ArtifactMap(_artifact(_mapping(value))) for key, value in previews.items() if _mapping(value)}
        return {
            _text(_get(_mapping(item), "scene_id", "sceneId", "id", default=f"scene-{index + 1}")): ArtifactMap(_artifact(_mapping(item)))
            for index, item in enumerate(_list(previews))
        }

    def _claim_ids(self, evidence: Mapping[str, Any], package: Mapping[str, Any]) -> set[str]:
        claims = _get(evidence, "claims", "facts", "items", default=[])
        result: set[str] = set()
        for index, claim in enumerate(_list(claims)):
            result.add(_text(_get(claim, "id", "claim_id", "claimId", "key", default=f"claim-{index + 1}")))
        result.discard("")
        result.update(_text(item) for item in _list(_get(package, "source_claim_ids", "sourceClaimIds", default=[])) if _text(item))
        return result

    @staticmethod
    def _normalise_scene_for_qa(scene: Mapping[str, Any]) -> ArtifactMap:
        """Normalize harmless model aliases before running strict QA gates."""
        data = ArtifactMap(_artifact(_mapping(scene)))
        narration = _text(_get(data, "narration", "spoken_text", "voiceover", "body", "text", default=""))
        data["duration_seconds"] = _normalise_duration(data, narration)
        raw_timings = _get(data, "semantic_timings", "semanticTimings", "narration_anchors", "narrationAnchors", "narration_timing", "narrationTiming", "timings", "timing", "beats", default=None)
        if raw_timings is not None and _list(raw_timings):
            data["semantic_timings"] = _normalise_timing(raw_timings, data["duration_seconds"], narration, [])
        data["render_class"] = _normalise_render_class(_get(data, "render_class", "renderClass", "renderer", "render_mode", default="motion-island"))
        return data

    def _inspect_scene(
        self,
        scene: Mapping[str, Any],
        preview: Mapping[str, Any],
        scene_id: str,
        claim_ids: set[str],
        evidence: Mapping[str, Any],
    ) -> tuple[list[ArtifactMap], list[ArtifactMap]]:
        issues: list[ArtifactMap] = []
        checks: list[ArtifactMap] = []

        # Truth references -------------------------------------------------
        refs = [
            _text(item)
            for item in _list(_get(scene, "evidence_refs", "truth_references", "truthReferences", "claims", "claim_ids", "claimIds", default=[]))
            if _text(item)
        ]
        unknown_refs = [ref for ref in refs if claim_ids and ref not in claim_ids]
        if not refs:
            narration = _text(_get(scene, "narration", "spoken_text", "voiceover", default=""))
            if narration and (_word_count(narration) > 4 or _get(scene, "factual", "is_factual", "isFactual", default=True)):
                issues.append(self._issue("missing-truth-reference", "error", scene_id, "Scene narration/visuals have no evidence reference.", "Attach claim IDs or source spans to every factual scene element."))
            else:
                checks.append(self._check("truth-reference", scene_id, True, "No factual narration requiring a reference was detected."))
        elif unknown_refs:
            issues.append(self._issue("unknown-truth-reference", "error", scene_id, f"Unknown evidence references: {', '.join(unknown_refs)}.", "Replace each reference with an ID present in the EvidencePack."))
        else:
            checks.append(self._check("truth-reference", scene_id, True, f"{len(refs)} evidence reference(s) resolve."))

        # Scene purpose ----------------------------------------------------
        purpose = _text(_get(scene, "viewer_question", "purpose", "scene_purpose", "scenePurpose", "intended_understanding", "understanding", default=""))
        purpose_values = _list(_get(scene, "purposes", "scene_purposes", "scenePurposes", default=[]))
        if not purpose:
            issues.append(self._issue("scene-purpose-missing", "error", scene_id, "Scene has no viewer question or intended understanding.", "State one viewer question and one concrete change in the viewer's mental model."))
        elif len(purpose_values) > 1:
            issues.append(self._issue("scene-purpose-multiple", "warning", scene_id, "Scene declares multiple competing purposes.", "Keep one dominant visual question; move other purposes to neighboring scenes."))
        else:
            checks.append(self._check("scene-purpose", scene_id, True, "One dominant scene purpose is declared."))

        # Text density -----------------------------------------------------
        visible_text = self._visible_text(scene, preview)
        words = _word_count(visible_text)
        chars = _char_count(visible_text)
        explicit_density = _get(scene, "text_density", "textDensity", default=None)
        density_high = words > self.config.max_visible_words or chars > self.config.max_visible_chars
        if _finite(explicit_density):
            density_value = _safe_float(explicit_density, 0.0)
            # A normalized density (0..1) is accepted; larger values are
            # interpreted as average visible words for compatibility.
            density_high = density_high or (density_value > 1.0 and density_value > self.config.max_visible_words) or density_value > 0.92
        if density_high:
            issues.append(self._issue("text-density-high", "error", scene_id, f"Visible copy is {words} words/{chars} characters, above the preview budget.", "Remove decorative copy, shorten labels, and let the dominant visual carry the explanation."))
        else:
            checks.append(self._check("text-density", scene_id, True, f"Visible copy is {words} words/{chars} characters."))

        # Contrast ---------------------------------------------------------
        contrast_values = self._contrast_values(scene, preview)
        if contrast_values:
            failing = []
            for item in contrast_values:
                ratio = _safe_float(_get(item, "ratio", "contrast_ratio", "contrastRatio", default=0.0), 0.0)
                large = bool(_get(item, "large", "large_text", "largeText", default=False))
                required = self.config.large_text_contrast if large else self.config.normal_text_contrast
                if ratio < required:
                    failing.append((ratio, required))
            if failing:
                ratio, required = failing[0]
                issues.append(self._issue("contrast-fail", "error", scene_id, f"Contrast ratio {ratio:.2f}:1 is below the {required:.1f}:1 threshold.", "Change the foreground/background roles or increase type weight and size until WCAG contrast passes."))
            else:
                checks.append(self._check("contrast", scene_id, True, "All supplied text contrast ratios pass."))
        else:
            # If colors are explicit, calculate a ratio.  If a renderer has no
            # color metadata yet, preserve a warning rather than claiming QA.
            ratio = contrast_ratio(_get(scene, "foreground", "text_color", "textColor", default=None), _get(scene, "background", "background_color", "backgroundColor", default=None))
            if ratio is None:
                issues.append(self._issue("contrast-unmeasured", "warning", scene_id, "Preview supplied no measurable text contrast ratio.", "Emit foreground/background colors or contrast ratios in the preview probe."))
            elif ratio < self.config.normal_text_contrast:
                issues.append(self._issue("contrast-fail", "error", scene_id, f"Computed contrast ratio {ratio:.2f}:1 is below 4.5:1.", "Change the foreground/background roles or increase type weight and size."))
            else:
                checks.append(self._check("contrast", scene_id, True, f"Computed contrast ratio is {ratio:.2f}:1."))

        # Motion purpose ---------------------------------------------------
        motion = _list(_get(scene, "motion_events", "motion", "actions", "motionActions", default=[]))
        motion_purpose = _text(_get(scene, "motion_purpose", "motionPurpose", default=""))
        bad_motion: list[str] = []
        missing_purpose = []
        for event in motion:
            item = _mapping(event)
            action = _text(_get(item, "action", "verb", "name", default=event)).lower()
            purpose_text = _text(_get(item, "purpose", "why", "semantic_purpose", "semanticPurpose", default=""))
            if any(term in action for term in self.FORBIDDEN_MOTION):
                bad_motion.append(action)
            if not purpose_text and not any(term in motion_purpose.lower() for term in self.MOTION_PURPOSE_TERMS):
                missing_purpose.append(action or "unnamed motion")
        if motion and (bad_motion or missing_purpose):
            details = []
            if bad_motion:
                details.append(f"arbitrary motion: {', '.join(bad_motion)}")
            if missing_purpose:
                details.append(f"missing semantic purpose: {', '.join(missing_purpose)}")
            issues.append(self._issue("motion-purpose-missing", "error", scene_id, "; ".join(details), "Replace decorative motion with a named cause, change, direction, focus, comparison, time, or relationship event."))
        elif motion or motion_purpose:
            checks.append(self._check("motion-purpose", scene_id, True, "Motion events declare explanatory purpose."))
        else:
            issues.append(self._issue("motion-purpose-missing", "error", scene_id, "Scene has no declared explanatory motion purpose.", "Declare a meaningful visual change or mark the scene as an intentional resolved still."))

        # Narration timing -------------------------------------------------
        narration = _text(_get(scene, "narration", "spoken_text", "voiceover", default=""))
        timings = _list(_get(scene, "semantic_timings", "narration_anchors", "narrationAnchors", "timings", "timing", default=[]))
        duration = _safe_float(_get(scene, "duration_seconds", "durationSeconds", "duration", default=_get(preview, "duration_seconds", "durationSeconds", default=0.0)), 0.0)
        timing_failures = self._timing_failures(timings, duration, motion)
        if narration and not timings:
            issues.append(self._issue("narration-timing-missing", "error", scene_id, "Narration has no semantic timing anchors.", "Attach word/beat timing anchors to the visual events that explain them."))
        elif timing_failures:
            issues.append(self._issue("narration-timing-invalid", "error", scene_id, "; ".join(timing_failures), "Clamp anchors to the scene duration and connect every important narration beat to a visual event."))
        elif narration:
            checks.append(self._check("narration-timing", scene_id, True, f"{len(timings)} narration timing anchor(s) align to the scene."))
        else:
            checks.append(self._check("narration-timing", scene_id, True, "Scene has no spoken narration."))

        # Cost -------------------------------------------------------------
        cost = self._cost(scene, preview)
        render_class = _text(_get(scene, "render_class", "renderClass", default=""))
        budget = _safe_float(_get(scene, "cost_budget", "costBudget", "budget", default=self.config.max_cost_by_class.get(render_class, self.config.max_scene_cost)), self.config.max_scene_cost)
        element_count = self._element_count(scene, preview)
        cost_over = cost > budget or element_count > self.config.max_elements
        if cost_over:
            reason = f"estimated cost {cost:.1f} exceeds {budget:.1f}" if cost > budget else f"element count {element_count} exceeds {self.config.max_elements}"
            issues.append(self._issue("cost-over-budget", "error", scene_id, reason, "Reduce expensive effects/elements or choose a simpler equivalent representation; never substitute a generic card layout."))
        else:
            checks.append(self._check("render-cost", scene_id, True, f"Estimated cost {cost:.1f} is within {budget:.1f}; {element_count} elements."))

        # Asset/preview basics --------------------------------------------
        missing_assets = [
            _text(item)
            for item in _list(_get(scene, "missing_assets", "missingAssets", default=_get(preview, "missing_assets", "missingAssets", default=[])))
            if _text(item)
        ]
        if missing_assets:
            issues.append(self._issue("missing-preview-asset", "error", scene_id, f"Missing preview assets: {', '.join(missing_assets)}.", "Resolve the declared asset or mark the scene's approved fallback explicitly."))

        return issues, checks

    def _visible_text(self, scene: Mapping[str, Any], preview: Mapping[str, Any]) -> str:
        values: list[str] = []
        for source in (scene, preview):
            for key in ("visible_text", "visibleText", "labels", "text_blocks", "textBlocks", "on_screen_text", "onScreenText", "title", "body", "copy"):
                value = _get(source, key, default=None)
                if value is None:
                    continue
                if isinstance(value, Mapping):
                    values.extend(_text(item) for item in value.values())
                else:
                    values.extend(_text(item) for item in _list(value))
            elements = _list(_get(source, "elements", "nodes", "objects", default=[]))
            for element in elements:
                item = _mapping(element)
                values.extend(_text(_get(item, "text", "label", "content", "copy", default="")) for _ in [0])
        return " ".join(value for value in values if value)

    def _contrast_values(self, scene: Mapping[str, Any], preview: Mapping[str, Any]) -> list[ArtifactMap]:
        values: list[ArtifactMap] = []
        for source in (scene, preview):
            raw = _get(source, "contrast_ratios", "contrastRatios", "contrast_checks", "contrastChecks", default=None)
            if raw is not None:
                for item in _list(raw):
                    if isinstance(item, Mapping):
                        values.append(ArtifactMap(_artifact(_mapping(item))))
                    elif _finite(item):
                        values.append(ArtifactMap({"ratio": float(item), "large": False}))
            explicit = _get(source, "contrast_ratio", "contrastRatio", default=None)
            if explicit is not None and _finite(explicit):
                values.append(ArtifactMap({"ratio": float(explicit), "large": bool(_get(source, "large_text", "largeText", default=False))}))
        return values

    def _timing_failures(self, timings: Sequence[Any], duration: float, motion: Sequence[Any]) -> list[str]:
        failures: list[str] = []
        prior_end = -1e-6
        for index, timing in enumerate(timings):
            item = _mapping(timing)
            start = _safe_float(_get(item, "start", "start_seconds", "startSeconds", "from", default=-1.0), -1.0)
            end = _safe_float(_get(item, "end", "end_seconds", "endSeconds", "to", default=-1.0), -1.0)
            if start < 0 or end <= start:
                failures.append(f"beat {index + 1} has invalid start/end")
            if duration > 0 and end > duration + 0.05:
                failures.append(f"beat {index + 1} ends after scene duration")
            if start + 0.05 < prior_end:
                failures.append(f"beat {index + 1} overlaps the previous beat")
            prior_end = max(prior_end, end)
            if not _text(_get(item, "visual_event", "event", "visualEvent", "anchor", default="")) and motion:
                failures.append(f"beat {index + 1} has no visual event anchor")
        return list(dict.fromkeys(failures))

    def _cost(self, scene: Mapping[str, Any], preview: Mapping[str, Any]) -> float:
        raw = _get(scene, "estimated_cost", "estimatedCost", "render_cost", "renderCost", "cost", default=None)
        if isinstance(raw, Mapping):
            raw = _get(raw, "score", "units", "gpu_seconds", "gpuSeconds", "milliseconds", default=0.0)
        if raw is None:
            raw = _get(preview, "estimated_cost", "estimatedCost", "render_cost", "renderCost", "cost", default=0.0)
        return max(0.0, _safe_float(raw, 0.0))

    def _element_count(self, scene: Mapping[str, Any], preview: Mapping[str, Any]) -> int:
        for source in (preview, scene):
            raw = _get(source, "element_count", "elementCount", "visible_element_count", "visibleElementCount", default=None)
            if raw is not None and _finite(raw):
                return max(0, int(float(raw)))
            elements = _get(source, "elements", "nodes", "objects", default=None)
            if elements is not None:
                return len(_list(elements))
        return 0

    @classmethod
    def _scene_has_spatial_depth(cls, scene: Mapping[str, Any]) -> bool:
        render_class = _normalise_render_class(_get(scene, "render_class", "renderClass", default=""))
        if render_class == "webgl-3d":
            return True
        def contains_three(value: Any) -> bool:
            data = _mapping(value)
            if _text(_get(data, "type", default="")).lower() == "three" or _mapping(_get(data, "three", default={})):
                return True
            return any(contains_three(child) for child in _list(_get(data, "children", default=[])))
        return contains_three(_get(scene, "root", "scene_graph", "sceneGraph", default=scene))

    def _check_repeated_scenes(self, scenes: Sequence[Any]) -> list[ArtifactMap]:
        issues: list[ArtifactMap] = []
        fingerprints = [CreativeFingerprint.from_scene(scene) for scene in scenes]
        for left_index, left in enumerate(fingerprints):
            for right_index in range(left_index + 1, len(fingerprints)):
                comparison = left.compare(fingerprints[right_index], threshold=self.config.repeated_structure_threshold)
                if comparison.get("structural_similarity", 0.0) >= self.config.repeated_structure_threshold or (
                    comparison.get("similarity", 0.0) >= self.config.repeated_structure_threshold
                ):
                    left_id = _text(_get(scenes[left_index], "id", "scene_id", "sceneId", default=f"scene-{left_index + 1}"))
                    right_id = _text(_get(scenes[right_index], "id", "scene_id", "sceneId", default=f"scene-{right_index + 1}"))
                    issues.append(self._issue(
                        "repeated-structure",
                        "error",
                        right_id,
                        f"Scene {right_id} materially repeats {left_id} ({comparison.get('structural_similarity', 0.0):.2f} structural similarity).",
                        "Redesign the repeated scene's representation or relationship graph; palette substitution alone is insufficient.",
                        details={"reference_scene_id": left_id, "comparison": comparison},
                    ))
        return issues

    def _check_history(self, package: Mapping[str, Any], treatment: Mapping[str, Any], scenes: Sequence[Any], history: Iterable[Any]) -> list[ArtifactMap]:
        candidate = CreativeFingerprint.from_treatment(treatment, scenes=scenes)
        ledger = DiversityLedger(list(history), window=10, threshold=self.config.history_similarity_threshold)
        result = ledger.compare(candidate)
        if result.get("accepted", True):
            return []
        reference_index = result.get("reference_index", -1)
        return [self._issue(
            "repeated-history-structure",
            "error",
            "project",
            f"Creative treatment repeats recent visible structure (similarity {result.get('similarity', 0.0):.2f}).",
            "Redesign the material language, scene topology, metaphor family, or motion grammar; do not only swap colors.",
            details={"reference_index": reference_index, "comparison": result},
        )]

    @staticmethod
    def _check(code: str, scene_id: str, passed: bool, message: str) -> ArtifactMap:
        return ArtifactMap({"code": code, "scene_id": scene_id, "passed": passed, "message": message})

    @staticmethod
    def _issue(code: str, severity: str, scene_id: str, message: str, action: str, *, details: Any = None) -> ArtifactMap:
        repair = ArtifactMap({"scene_id": scene_id, "code": code, "severity": severity, "action": action, "preserve": ["truth_references", "narration", "unaffected_scenes"]})
        result = ArtifactMap({"code": code, "severity": severity, "scene_id": scene_id, "message": message, "repair": repair})
        if details is not None:
            result["details"] = _artifact(details)
        return result


class QualityGate:
    """Small orchestration facade for preview QA and targeted repairs."""

    def __init__(self, qa: PreviewQA | None = None, *, config: QualityConfig | None = None, **overrides: Any) -> None:
        self.qa = qa or PreviewQA(config, **overrides)

    def inspect(self, *args: Any, **kwargs: Any) -> ArtifactMap:
        return self.qa.inspect(*args, **kwargs)

    check = inspect
    run = inspect
    evaluate = inspect

    def repair(self, project: Any, report: Any) -> ArtifactMap:
        return self.qa.repair(project, report)

    def accepts(self, report: Any) -> bool:
        return bool(_get(report, "passed", "accepted", default=False))

    def gate(self, project: Any, previews: Any = None, **kwargs: Any) -> ArtifactMap:
        report = self.inspect(project, previews, **kwargs)
        report["accepted"] = report["passed"]
        return report


def inspect_preview(project: Any, previews: Any = None, **kwargs: Any) -> ArtifactMap:
    return PreviewQA(**{key: value for key, value in kwargs.pop("config", {}).items()}).inspect(project, previews, **kwargs)


__all__ = [
    "PreviewQA",
    "QualityConfig",
    "QualityGate",
    "contrast_ratio",
    "inspect_preview",
]
