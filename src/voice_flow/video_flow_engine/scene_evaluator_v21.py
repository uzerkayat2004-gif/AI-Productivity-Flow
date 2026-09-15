"""V2.1 Scene Evaluation — Source grounding, cue spread, and diversity checks."""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class SceneEvaluationResult:
    scene_id: str
    must_show_coverage: float  # 0.0 to 1.0
    relationship_coverage: float  # 0.0 to 1.0 
    cue_spread: float  # 0.0 to 1.0 — fraction of duration with active reveals
    max_cue_index: int  # highest cue index used
    distinct_cue_count: int  # number of distinct cue values
    has_front_loaded_animation: bool  # True if >80% of elements at cue 0
    findings: tuple[str, ...] = ()
    verdict: str = "PASS"  # PASS, WARN, FAIL

@dataclass(frozen=True)
class VideoEvaluationResult:
    scene_results: tuple[SceneEvaluationResult, ...]
    structural_diversity_score: float  # 0.0 to 1.0
    overall_cue_spread: float
    overall_must_show_coverage: float
    overall_relationship_coverage: float
    distinct_families_used: int
    distinct_strategies_used: int
    findings: tuple[str, ...] = ()
    verdict: str = "PASS"


def check_cue_spread(compiled_html: str) -> tuple[float, int, int, bool]:
    if not isinstance(compiled_html, str):
        return 0.0, 0, 0, False
    matches = re.findall(r'data-cue=["\'](\d+)["\']', compiled_html)
    if not matches:
        return 0.0, 0, 0, False
        
    cues = [int(c) for c in matches]
    max_cue = max(cues)
    distinct_cues = len(set(cues))
    
    count_zero = cues.count(0)
    is_front_loaded = (count_zero / len(cues)) > 0.8 if cues else False
    
    expected_cues = max_cue + 1
    spread = distinct_cues / max(expected_cues, 1)
    
    return float(spread), max_cue, distinct_cues, is_front_loaded


def evaluate_scene_v21(scene_program: Any, compiled_scene: Mapping[str, Any]) -> SceneEvaluationResult:
    html = compiled_scene.get("body", "") if isinstance(compiled_scene, Mapping) else ""
    if not isinstance(html, str):
        html = ""
    spread, max_cue, distinct, front_loaded = check_cue_spread(html)
    
    declared_subjects = getattr(scene_program, "subjects", [])
    declared_rels = getattr(scene_program, "relationships", [])
    
    must_show_count = 0
    for s in declared_subjects:
        sid = getattr(s, "subject_id", getattr(s, "id", ""))
        if f'id="{sid}"' in html or f"id='{sid}'" in html:
            must_show_count += 1
            
    must_show_cov = must_show_count / len(declared_subjects) if declared_subjects else 1.0
    
    rel_rendered = len(re.findall(r'class="[^"]*v21-relationship[^"]*"', html))
    rel_cov = rel_rendered / len(declared_rels) if declared_rels else 1.0
    
    findings = []
    verdict = "PASS"
    if must_show_cov < 1.0:
        findings.append(f"Missing {len(declared_subjects) - must_show_count} declared subjects")
        verdict = "WARN"
    if rel_cov < 1.0:
        findings.append(f"Missing {len(declared_rels) - rel_rendered} relationships")
        verdict = "WARN"
    if front_loaded:
        findings.append("Animation is front-loaded (>80% at cue 0)")
        verdict = "WARN" if verdict == "PASS" else verdict
        
    return SceneEvaluationResult(
        scene_id=str(getattr(scene_program, "scene_id", "")),
        must_show_coverage=float(must_show_cov),
        relationship_coverage=float(rel_cov),
        cue_spread=spread,
        max_cue_index=max_cue,
        distinct_cue_count=distinct,
        has_front_loaded_animation=front_loaded,
        findings=tuple(findings),
        verdict=verdict
    )


def evaluate_video_v21(program: Any, compiled: Any) -> VideoEvaluationResult:
    scene_results = []
    distinct_families = set()
    distinct_strategies = set()
    total_subjects = 0
    
    scenes = getattr(program, "scenes", [])
    try:
        compiled_scenes = compiled.production.get("scenes", [])
    except AttributeError:
        compiled_scenes = getattr(compiled, "scenes", [])
    
    for i, scene_program in enumerate(scenes):
        if i < len(compiled_scenes):
            compiled_scene = compiled_scenes[i]
            res = evaluate_scene_v21(scene_program, compiled_scene)
            scene_results.append(res)
            
        for s in getattr(scene_program, "subjects", []):
            family = getattr(s, "structural_family", "")
            if family:
                distinct_families.add(family)
            total_subjects += 1
            
        strategies = getattr(scene_program, "representation_strategy", [])
        if isinstance(strategies, str):
            distinct_strategies.add(strategies)
        else:
            for strategy in strategies:
                distinct_strategies.add(strategy)
            
    struct_diversity = len(distinct_families) / total_subjects if total_subjects else 1.0
    
    overall_must_show = sum(r.must_show_coverage for r in scene_results) / len(scene_results) if scene_results else 1.0
    overall_rel = sum(r.relationship_coverage for r in scene_results) / len(scene_results) if scene_results else 1.0
    overall_cue_spread = sum(r.cue_spread for r in scene_results) / len(scene_results) if scene_results else 1.0
    
    findings = []
    verdict = "PASS"
    if struct_diversity < 0.5:
        findings.append("Low structural diversity across video")
        verdict = "WARN"
        
    for r in scene_results:
        if r.verdict != "PASS":
            verdict = "WARN"
            
    return VideoEvaluationResult(
        scene_results=tuple(scene_results),
        structural_diversity_score=float(struct_diversity),
        overall_cue_spread=overall_cue_spread,
        overall_must_show_coverage=overall_must_show,
        overall_relationship_coverage=overall_rel,
        distinct_families_used=len(distinct_families),
        distinct_strategies_used=len(distinct_strategies),
        findings=tuple(findings),
        verdict=verdict
    )
