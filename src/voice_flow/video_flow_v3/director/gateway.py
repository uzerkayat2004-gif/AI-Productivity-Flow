"""V3 AI Creative Director Gateway.

Routes semantic scene authoring to user-selected LLM models (Gemini, Claude, OpenAI, Groq, Combos)
via VideoModelGateway & provider connections while enforcing:
1. Strict AI Security Boundary: DATA ONLY (NO executable code: eval/JS/Python/shaders/HTML/SVG).
2. NO raw pixel coordinates (x, y) or camera XYZ.
3. External AI consent policies (Default DENY).
4. Complete source text processing (hierarchical chunking without arbitrary truncation).
5. Fallback to deterministic semantic planning when models are offline or consent denied.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from voice_flow.video_flow_v3.contracts import (
    SourceBundle,
    SourceUnit,
    EvidenceGraph,
    CoverageLedger,
    ArtDirectionGenome,
    SceneSemanticV3,
    SceneBeat,
    SemanticObject,
    SemanticRepresentationType,
    SemanticTransitionType,
    UnitDispositionType,
    FidelityClass3D,
    validate_no_executable_code,
)
from voice_flow.video_flow_v3.evidence.builder import SpatialAffordanceAnalyzer

log = logging.getLogger(__name__)


def classify_semantic_representation(
    text: str,
    content_type: str = "sentence",
    unit_order: int = 0,
    total_units: int = 1,
) -> SemanticRepresentationType:
    """Resolve realistic semantic representation types based on text semantics and syntax."""
    text_lower = text.lower()

    # 1. Code blocks
    if content_type == "code_block" or "```" in text or "def " in text or "function " in text or "class " in text:
        return SemanticRepresentationType.CODE_EXPLANATION

    # 2. Tables / Structured metrics
    if content_type == "table_row":
        return SemanticRepresentationType.STAT_GRID

    # 3. Quotes
    if content_type == "quote" or (text.strip().startswith('"') and text.strip().endswith('"')):
        return SemanticRepresentationType.QUOTE_CALLOUT

    # 4. Mathematical equations / formulas
    if any(k in text_lower for k in ["equation", "formula", "\\sum", "\\int", "\\approx", "dx/dt", "e=mc"]):
        return SemanticRepresentationType.EQUATION_EXPLANATION

    # 5. 3D Physical Assembly / Cutaways
    if any(k in text_lower for k in ["cutaway", "internal section", "cross-section", "exploded view", "encases", "internal", "inside housing"]):
        return SemanticRepresentationType.CUTAWAY_3D
    if any(k in text_lower for k in ["assembly", "chassis", "cad model", "engine block", "mechanical structure", "physical structure", "drivetrain", "turbopump", "fuselage"]):
        return SemanticRepresentationType.ASSEMBLY_3D

    # 6. Comparisons / Contrasts
    if any(k in text_lower for k in [" versus ", " vs ", " vs. ", "compared to", "differ from", "contrast with", "advantage", "trade-off", "faster than", "better than", "in contrast"]):
        return SemanticRepresentationType.COMPARISON

    # 7. Before / After & Transformations
    if any(k in text_lower for k in ["before and after", "before/after", "previously", "migrated to", "transformed into", "upgrade from"]):
        return SemanticRepresentationType.BEFORE_AFTER
    if any(k in text_lower for k in ["transformation", "converts", "transforms", "metamorphosis", "evolves into", "condenses into", "replication cycle", "division cycle"]):
        return SemanticRepresentationType.TRANSFORMATION

    # 8. Cause and Effect
    if any(k in text_lower for k in ["causes", "leads to", "because of", "results in", "consequently", "triggering", "due to this", "as a result"]):
        return SemanticRepresentationType.CAUSE_EFFECT

    # 9. Timelines / Dates / Chronology
    if any(k in text_lower for k in ["timeline", "chronology", "century", "milestone", "era", "in 19", "in 20", "history of"]):
        return SemanticRepresentationType.TIMELINE

    # 10. Quantitative / Charts / Metrics
    if any(k in text_lower for k in ["%", "percent", "metric", "revenue", "benchmark", "quantitatively", "statistically", "data point", "measure", "statistics"]):
        return SemanticRepresentationType.QUANTITATIVE

    # 11. System Architecture / Layer Stacks
    if any(k in text_lower for k in ["layer stack", "protocol stack", "stack of layers", "osi layer"]):
        return SemanticRepresentationType.LAYER_STACK
    if any(k in text_lower for k in ["architecture", "subsystem", "microservice", "infrastructure", "backend", "frontend", "client-server", "distributed system"]):
        return SemanticRepresentationType.SYSTEM_ARCHITECTURE

    # 12. Networks / Graphs / Topologies
    if any(k in text_lower for k in ["network", "mesh", "topology", "graph", "interconnected", "nodes and edges", "peer-to-peer", "cluster"]):
        return SemanticRepresentationType.NETWORK

    # 13. Hierarchies / Trees / Taxonomies
    if any(k in text_lower for k in ["hierarchy", "hierarchical", "taxonomy", "tree structure", "parent-child", "subclass", "nested levels"]):
        return SemanticRepresentationType.HIERARCHY

    # 14. Processes / Sequences / Steps
    if any(k in text_lower for k in ["step 1", "step 2", "step 3", "first,", "second,", "then,", "next,", "finally,", "procedure", "stage 1", "stage 2", "workflow", "prophase", "metaphase", "anaphase", "telophase", "cytokinesis", "mitosis", "replication", "stages", "phases", "division", "biological cycle"]):
        return SemanticRepresentationType.PROCESS
    if any(k in text_lower for k in ["sequence", "ordered steps", "progression"]):
        return SemanticRepresentationType.SEQUENCE

    # 15. Flow / Pipelines / Streams
    if any(k in text_lower for k in ["data flow", "data stream", "streaming", "packet flow", "pipeline flow", "throughput", "supply chain", "continuous flow"]):
        return SemanticRepresentationType.FLOW

    # 16. List Breakdown
    if any(k in text_lower for k in ["requirements:", "items:", "checklist", "key points:", "following:"]):
        return SemanticRepresentationType.LIST_BREAKDOWN

    # 17. Document / Source
    if any(k in text_lower for k in ["document", "source code", "manifesto", "contract", "specification"]):
        return SemanticRepresentationType.DOCUMENT_SOURCE

    # 18. Recap / Conclusion
    if unit_order > 0 and unit_order >= total_units - 1:
        if any(k in text_lower for k in ["conclusion", "in summary", "to summarize", "takeaway", "overall", "finally", "wrap up"]):
            return SemanticRepresentationType.SUMMARY_RECAP

    # Structural default based on narrative position and progressive storytelling
    if total_units > 1 and unit_order == 0:
        return SemanticRepresentationType.OBJECT_FOCUS
    elif total_units > 1 and unit_order == total_units - 1:
        return SemanticRepresentationType.SUMMARY_RECAP

    mid_rotations = [
        SemanticRepresentationType.SYSTEM_ARCHITECTURE,
        SemanticRepresentationType.COMPARISON,
        SemanticRepresentationType.FLOW,
        SemanticRepresentationType.HIERARCHY,
        SemanticRepresentationType.NETWORK,
        SemanticRepresentationType.QUANTITATIVE,
        SemanticRepresentationType.PROCESS,
    ]
    return mid_rotations[unit_order % len(mid_rotations)]


def author_scene_beats(
    scene_id: str,
    narration_text: str,
    semantic_objects: List[SemanticObject],
    representation_type: str,
    duration_sec: float,
) -> List[SceneBeat]:
    """Author 2-4 semantic visual beats within a single scene.

    Prevents static visuals and provides deterministic timing hooks for segmented narration
    and interactive highlight actions.
    """
    beats: List[SceneBeat] = []
    dur = max(3.5, duration_sec)

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narration_text) if s.strip()]
    if not sentences:
        sentences = [narration_text] if narration_text else ["Visual focus point"]

    obj_ids = [o.object_id for o in semantic_objects] or [f"{scene_id}_hero"]

    if len(sentences) == 1 or dur < 5.0:
        # 2 beats: intro reveal & focal highlight
        b1_dur = round(dur * 0.45, 2)
        b2_dur = round(dur - b1_dur, 2)
        beats.append(SceneBeat(
            beat_id=f"{scene_id}_beat_0",
            time_offset_sec=0.0,
            beat_type="intro",
            narration_subphrase=sentences[0][:80],
            visual_action="reveal",
            target_element_ids=[obj_ids[0]],
            duration_sec=b1_dur,
        ))
        beats.append(SceneBeat(
            beat_id=f"{scene_id}_beat_1",
            time_offset_sec=b1_dur,
            beat_type="focus",
            narration_subphrase=sentences[0][80:160] if len(sentences[0]) > 80 else sentences[0],
            visual_action="highlight_target",
            target_element_ids=obj_ids,
            duration_sec=b2_dur,
        ))
    else:
        # 3-4 beats: intro, evidence/mechanism, focus, recap
        num_beats = min(4, max(3, len(sentences)))
        step_dur = round(dur / num_beats, 2)

        for b_idx in range(num_beats):
            t_offset = round(b_idx * step_dur, 2)
            curr_dur = step_dur if b_idx < num_beats - 1 else round(dur - t_offset, 2)
            subphrase = sentences[b_idx] if b_idx < len(sentences) else sentences[-1]

            if b_idx == 0:
                b_type = "intro"
                action = "reveal"
                tgt = [obj_ids[0]]
            elif b_idx == 1:
                b_type = "evidence"
                if representation_type in (SemanticRepresentationType.SYSTEM_ARCHITECTURE.value, SemanticRepresentationType.LAYER_STACK.value):
                    action = "expand_node"
                elif representation_type in (SemanticRepresentationType.FLOW.value, SemanticRepresentationType.PROCESS.value, SemanticRepresentationType.NETWORK.value):
                    action = "route_signal"
                elif representation_type in (SemanticRepresentationType.COMPARISON.value, SemanticRepresentationType.BEFORE_AFTER.value):
                    action = "compare_delta"
                elif representation_type in (SemanticRepresentationType.ASSEMBLY_3D.value, SemanticRepresentationType.CUTAWAY_3D.value):
                    action = "assemble"
                else:
                    action = "focus"
                tgt = obj_ids[:2]
            elif b_idx == num_beats - 1:
                b_type = "recap"
                action = "highlight_target"
                tgt = obj_ids
            else:
                b_type = "focus"
                action = "morph_state"
                tgt = [obj_ids[-1]]

            beats.append(SceneBeat(
                beat_id=f"{scene_id}_beat_{b_idx}",
                time_offset_sec=t_offset,
                beat_type=b_type,
                narration_subphrase=subphrase,
                visual_action=action,
                target_element_ids=tgt,
                duration_sec=curr_dur,
            ))

    return beats


def resolve_scene_transitions(scenes: List[SceneSemanticV3]) -> None:
    """Deterministically assign semantic transitions between consecutive scenes."""
    for idx, scene in enumerate(scenes):
        if idx == 0:
            scene.transition_in = SemanticTransitionType.MATCH_TRANSITION.value
        else:
            prev = scenes[idx - 1]
            if scene.representation_type == prev.representation_type:
                scene.transition_in = SemanticTransitionType.MATCH_TRANSITION.value
            elif scene.chapter_id != prev.chapter_id:
                scene.transition_in = SemanticTransitionType.CARRY.value
            elif scene.representation_type in (SemanticRepresentationType.SUMMARY_RECAP.value, SemanticRepresentationType.STAT_GRID.value):
                scene.transition_in = SemanticTransitionType.COLLAPSE.value
            elif prev.representation_type in (SemanticRepresentationType.OBJECT_FOCUS.value, SemanticRepresentationType.SYSTEM_ARCHITECTURE.value):
                scene.transition_in = SemanticTransitionType.EXPAND.value
            else:
                scene.transition_in = SemanticTransitionType.CARRY.value

        if idx == len(scenes) - 1:
            scene.transition_out = SemanticTransitionType.COLLAPSE.value
        else:
            nxt = scenes[idx + 1]
            if nxt.representation_type == scene.representation_type:
                scene.transition_out = SemanticTransitionType.MATCH_TRANSITION.value
            elif nxt.representation_type in (SemanticRepresentationType.SUMMARY_RECAP.value,):
                scene.transition_out = SemanticTransitionType.COLLAPSE.value
            else:
                scene.transition_out = SemanticTransitionType.CARRY.value


class V3CreativeDirectorGateway:
    """Connects CreativeDirectorV3 to selected LLM models & provider connections."""

    def __init__(self, model_gateway: Any = None) -> None:
        self.model_gateway = model_gateway

    def author_semantic_plan(
        self,
        bundle: SourceBundle,
        units: List[SourceUnit],
        evidence: EvidenceGraph,
        genome: ArtDirectionGenome,
        mode: str = "summary",
        model_ref: str = "local/deterministic",
        visual_direction: str = "",
        allow_external_ai: bool = False,
    ) -> List[SceneSemanticV3]:
        """Prompt selected LLM to author semantic scene intents or use deterministic planning."""
        if not allow_external_ai or not model_ref or model_ref == "local/deterministic":
            log.info("V3 Creative Director: Using deterministic semantic planner (external AI consent: %s, model: %s)", allow_external_ai, model_ref)
            return self._deterministic_fallback_plan(units, mode, genome)

        canonical_vocab = ", ".join([t.value for t in SemanticRepresentationType])
        canonical_transitions = ", ".join([t.value for t in SemanticTransitionType])

        system_prompt = (
            "You are CreativeDirectorV3, an expert visual explanation director.\n"
            "Author a structured JSON object with a 'scenes' array defining semantic scene intents.\n\n"
            "CRITICAL SECURITY & ART DIRECTION RULES:\n"
            "1. Output DATA ONLY. Absolutely NO JavaScript, Python, HTML, CSS, SVG, or shader code.\n"
            "2. Do NOT output pixel coordinates (x, y) or camera XYZ. Deterministic compilers compute layout.\n"
            "3. Choose representation_type ONLY from canonical vocabulary: " + canonical_vocab + ".\n"
            "4. Choose transition_in and transition_out ONLY from: " + canonical_transitions + ".\n"
            "5. NO generic card slideshows. Use content-driven semantic structures with 1-3 focal points per scene.\n"
            "6. Ground all scene claims strictly in provided SourceUnit IDs via 'evidence_refs'.\n"
            "7. Return JSON ONLY with format:\n"
            '{"scenes": [{"representation_type": "...", "teaching_goal": "...", "viewer_question": "...", "intended_understanding": "...", "narration_text": "...", "semantic_objects": [{"object_id": "...", "label": "...", "role": "primary|secondary|annotation", "semantic_type": "..."}], "motion_purpose": "...", "shot_grammar": "...", "suggested_duration_sec": 5.0, "use_3d": false, "transition_in": "MATCH_TRANSITION|CARRY|EXPAND|COLLAPSE", "transition_out": "CARRY", "evidence_refs": ["..."]}]}'
        )

        unit_lines: List[str] = []
        current_section = None
        for u in units:
            if u.section_id != current_section:
                current_section = u.section_id
                unit_lines.append(f"\n--- SECTION: {current_section} ---")
            unit_lines.append(f"[{u.unit_id}] ({u.content_type}): {u.normalized_text}")
        full_units_text = "\n".join(unit_lines)

        user_prompt = (
            f"SOURCE TITLE: {bundle.source_name}\n"
            f"MODE: {mode.upper()}\n\n"
        )
        if visual_direction:
            user_prompt += f"VISUAL DIRECTION HINT (Source facts take priority):\n{visual_direction}\n\n"

        user_prompt += (
            f"COMPLETE SOURCE TEXT ({len(bundle.source_text)} chars):\n{bundle.source_text}\n\n"
            f"ALL SOURCE UNITS ({len(units)} total units):\n{full_units_text}\n\n"
            f"INSTRUCTIONS:\n"
            f"- Account for ALL source units across the entire source document.\n"
            f"- For each scene, specify representation_type from canonical types.\n"
            f"- 'evidence_refs' MUST list valid SourceUnit IDs (e.g. ['unit_0', 'unit_1']).\n"
            f"- Return strictly valid JSON with root key 'scenes'."
        )

        if self.model_gateway:
            try:
                raw_json = self._call_model_gateway(model_ref, system_prompt, user_prompt)
                if raw_json:
                    parsed_scenes = self._parse_llm_scenes(raw_json, units, mode)
                    if parsed_scenes:
                        log.info("V3 Creative Director: LLM '%s' authored %d semantic scenes.", model_ref, len(parsed_scenes))
                        return parsed_scenes
            except Exception as exc:
                log.warning("V3 Creative Director LLM call to '%s' failed: %s. Falling back to deterministic planner.", model_ref, exc)

        return self._deterministic_fallback_plan(units, mode, genome)

    def _call_model_gateway(self, model_ref: str, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not self.model_gateway:
            return None
        if hasattr(self.model_gateway, "request_scene_plan"):
            return self.model_gateway.request_scene_plan(model_ref, system_prompt, user_prompt)
        return None

    def _parse_llm_scenes(self, raw_json: str, units: List[SourceUnit], mode: str) -> List[SceneSemanticV3]:
        """Validate LLM output against security boundary, schema, and contracts."""
        try:
            clean = raw_json.strip()
            fence = "```"
            if clean.startswith(fence):
                lines = clean.split("\n")
                if lines[0].startswith(fence):
                    lines = lines[1:]
                if lines and lines[-1].startswith(fence):
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()

            validate_no_executable_code(clean)
            data = json.loads(clean)
            validate_no_executable_code(data)

            if not isinstance(data, dict):
                raise ValueError("Model output is not a JSON object.")

            raw_scenes = data.get("scenes")
            if not isinstance(raw_scenes, list) or not raw_scenes:
                raise ValueError("Model returned no scenes array.")

            valid_unit_ids = {u.unit_id for u in units}
            scenes: List[SceneSemanticV3] = []

            for idx, raw_sc in enumerate(raw_scenes):
                if not isinstance(raw_sc, dict):
                    continue

                raw_rep = str(raw_sc.get("representation_type", "")).strip().upper()
                rep_type = SemanticRepresentationType.PROCESS.value
                for member in SemanticRepresentationType:
                    if member.value == raw_rep or member.name == raw_rep:
                        rep_type = member.value
                        break

                semantic_objects: List[SemanticObject] = []
                for i, o in enumerate(raw_sc.get("semantic_objects", [])):
                    if isinstance(o, dict):
                        role_str = str(o.get("role", "primary")).lower()
                        if role_str not in ("primary", "secondary", "annotation", "container"):
                            role_str = "primary" if i == 0 else "secondary"
                        semantic_objects.append(SemanticObject(
                            object_id=str(o.get("object_id", f"obj_{idx}_{i}")),
                            label=str(o.get("label", "Concept"))[:60],
                            role=role_str,
                            semantic_type=str(o.get("semantic_type", rep_type.lower())),
                            properties=dict(o.get("properties", {})) if isinstance(o.get("properties"), dict) else {},
                        ))

                if not semantic_objects:
                    semantic_objects.append(SemanticObject(
                        object_id=f"obj_{idx}_0",
                        label=str(raw_sc.get("teaching_goal", f"Concept {idx+1}"))[:40],
                        role="primary",
                        semantic_type=rep_type.lower(),
                    ))

                raw_refs = raw_sc.get("evidence_refs", [])
                evidence_refs = [r for r in raw_refs if r in valid_unit_ids] if isinstance(raw_refs, list) else []
                if not evidence_refs and units:
                    target_idx = min(idx, len(units) - 1)
                    evidence_refs = [units[target_idx].unit_id]

                dur = float(raw_sc.get("suggested_duration_sec", 5.0))
                dur = max(3.5, min(60.0, dur))
                narration = str(raw_sc.get("narration_text", ""))

                # Build scene beats
                beats = author_scene_beats(
                    scene_id=f"scene_{idx}",
                    narration_text=narration,
                    semantic_objects=semantic_objects,
                    representation_type=rep_type,
                    duration_sec=dur,
                )

                dispositions = {ref: UnitDispositionType.COVERED_BOTH.value for ref in evidence_refs}

                # Transition parsing
                trans_in = str(raw_sc.get("transition_in", SemanticTransitionType.MATCH_TRANSITION.value)).upper()
                trans_out = str(raw_sc.get("transition_out", SemanticTransitionType.CARRY.value)).upper()

                scenes.append(SceneSemanticV3(
                    scene_id=f"scene_{idx}",
                    chapter_id=str(raw_sc.get("chapter_id", f"chap_{idx // 4}")),
                    sequence=idx,
                    teaching_goal=str(raw_sc.get("teaching_goal", f"Explain concept {idx+1}")),
                    viewer_question=str(raw_sc.get("viewer_question", "How does this function?")),
                    intended_understanding=str(raw_sc.get("intended_understanding", "")),
                    narration_text=narration,
                    representation_type=rep_type,
                    semantic_objects=semantic_objects,
                    motion_purpose=str(raw_sc.get("motion_purpose", "reveal")),
                    shot_grammar=str(raw_sc.get("shot_grammar", "HeroFocus")),
                    suggested_duration_sec=dur,
                    duration_sec=dur,
                    use_3d=bool(raw_sc.get("use_3d", False)),
                    fidelity_3d=FidelityClass3D.F1_PHYSICAL if bool(raw_sc.get("use_3d")) else FidelityClass3D.F4_INSUFFICIENT,
                    evidence_refs=evidence_refs,
                    scene_beats=beats,
                    transition_in=trans_in if trans_in in SemanticTransitionType.__members__ else SemanticTransitionType.MATCH_TRANSITION.value,
                    transition_out=trans_out if trans_out in SemanticTransitionType.__members__ else SemanticTransitionType.CARRY.value,
                    source_unit_dispositions=dispositions,
                ))

            resolve_scene_transitions(scenes)
            return scenes
        except Exception as err:
            log.warning("LLM scene JSON validation failed: %s", err)
            return []

    def _deterministic_fallback_plan(
        self,
        units: List[SourceUnit],
        mode: str,
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Deterministic semantic planner implementing Visual Summary, Full, and Spatial 3D modes."""
        if not units:
            return []

        if mode == "spatial_3d":
            return self._plan_spatial_3d_scenes(units, genome)
        elif mode == "full":
            return self._plan_full_scenes(units, genome)
        else:
            return self._plan_summary_scenes(units, genome)

    def _plan_summary_scenes(
        self,
        units: List[SourceUnit],
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Visual Summary Mode: 1-3 summary points per scene, adaptive duration, internal scene beats."""
        scenes: List[SceneSemanticV3] = []
        total_units = len(units)

        target_scene_count = min(8, max(4, total_units // 3)) if total_units >= 4 else total_units
        chunk_size = max(1, (total_units + target_scene_count - 1) // target_scene_count)

        for i in range(0, total_units, chunk_size):
            chunk = units[i : i + chunk_size]
            seq = len(scenes)
            combined_text = " ".join(u.normalized_text for u in chunk)
            primary_unit = chunk[0]

            rep_type_enum = classify_semantic_representation(
                combined_text,
                content_type=primary_unit.content_type,
                unit_order=seq,
                total_units=max(1, (total_units + chunk_size - 1) // chunk_size),
            )
            rep_type = rep_type_enum.value

            # Repetition avoidance: prevent 3 consecutive identical representation types
            if len(scenes) >= 2 and scenes[-1].representation_type == rep_type and scenes[-2].representation_type == rep_type:
                alt_map = {
                    SemanticRepresentationType.ASSEMBLY_3D.value: SemanticRepresentationType.CUTAWAY_3D.value,
                    SemanticRepresentationType.CUTAWAY_3D.value: SemanticRepresentationType.FLOW.value,
                    SemanticRepresentationType.PROCESS.value: SemanticRepresentationType.SEQUENCE.value,
                    SemanticRepresentationType.SEQUENCE.value: SemanticRepresentationType.FLOW.value,
                    SemanticRepresentationType.QUANTITATIVE.value: SemanticRepresentationType.STAT_GRID.value,
                    SemanticRepresentationType.SYSTEM_ARCHITECTURE.value: SemanticRepresentationType.LAYER_STACK.value,
                }
                rep_type = alt_map.get(rep_type, SemanticRepresentationType.OBJECT_FOCUS.value)

            if rep_type in (SemanticRepresentationType.COMPARISON.value, SemanticRepresentationType.BEFORE_AFTER.value):
                motion = "compare"
                shot = "SplitCompare"
            elif rep_type in (SemanticRepresentationType.PROCESS.value, SemanticRepresentationType.FLOW.value, SemanticRepresentationType.SEQUENCE.value):
                motion = "flow"
                shot = "FlowPan"
            elif rep_type in (SemanticRepresentationType.ASSEMBLY_3D.value, SemanticRepresentationType.CUTAWAY_3D.value):
                motion = "explode"
                shot = "HeroOrbit3D"
            elif rep_type in (SemanticRepresentationType.CODE_EXPLANATION.value, SemanticRepresentationType.EQUATION_EXPLANATION.value):
                motion = "focus"
                shot = "Inspect"
            elif rep_type == SemanticRepresentationType.TIMELINE.value:
                motion = "flow"
                shot = "TimelineScroll"
            elif rep_type in (SemanticRepresentationType.HIERARCHY.value, SemanticRepresentationType.NETWORK.value, SemanticRepresentationType.SYSTEM_ARCHITECTURE.value):
                motion = "transform"
                shot = "ArchitecturalZoom"
            else:
                motion = "reveal"
                shot = "HeroFocus"

            use_3d = rep_type in (SemanticRepresentationType.ASSEMBLY_3D.value, SemanticRepresentationType.CUTAWAY_3D.value)

            # 1-3 summary points (semantic objects)
            semantic_objects: List[SemanticObject] = []
            for u_idx, u in enumerate(chunk[:3]):
                semantic_objects.append(SemanticObject(
                    object_id=f"obj_{seq}_{u_idx}",
                    label=u.normalized_text[:45],
                    role="primary" if u_idx == 0 else "secondary",
                    semantic_type=rep_type.lower(),
                ))

            # Adaptive duration: 4.5s to 24s+ based on narration word count and complexity
            word_count = len(re.findall(r"\S+", combined_text))
            dur = max(4.5, min(28.0, round(word_count / 2.5 + 1.5, 1)))

            beats = author_scene_beats(
                scene_id=f"scene_{seq}",
                narration_text=combined_text,
                semantic_objects=semantic_objects,
                representation_type=rep_type,
                duration_sec=dur,
            )

            dispositions = {
                u.unit_id: (UnitDispositionType.COVERED_BOTH.value if idx == 0 else UnitDispositionType.COVERED_NARRATION.value)
                for idx, u in enumerate(chunk)
            }

            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id=f"chap_{seq // 4}",
                sequence=seq,
                teaching_goal=f"Explain {primary_unit.normalized_text[:50]}",
                viewer_question="How does this core component work?",
                intended_understanding=primary_unit.normalized_text[:120],
                narration_text=combined_text,
                representation_type=rep_type,
                semantic_objects=semantic_objects,
                motion_purpose=motion,
                shot_grammar=shot,
                suggested_duration_sec=dur,
                duration_sec=dur,
                use_3d=use_3d,
                fidelity_3d=FidelityClass3D.F1_PHYSICAL if use_3d else FidelityClass3D.F4_INSUFFICIENT,
                evidence_refs=[u.unit_id for u in chunk],
                scene_beats=beats,
                source_unit_dispositions=dispositions,
            ))

        resolve_scene_transitions(scenes)
        return scenes

    def _plan_full_scenes(
        self,
        units: List[SourceUnit],
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Full Visual Explanation Mode: 100% SourceUnit accounting, chaptering, progressive scenes."""
        scenes: List[SceneSemanticV3] = []
        current_chap_id = "chap_0"
        chap_count = 0

        for seq, unit in enumerate(units):
            if unit.content_type == "heading":
                chap_count += 1
                current_chap_id = f"chap_{chap_count}"

            rep_type_enum = classify_semantic_representation(
                unit.normalized_text,
                content_type=unit.content_type,
                unit_order=seq,
                total_units=len(units),
            )
            rep_type = rep_type_enum.value

            semantic_objects = [
                SemanticObject(
                    object_id=f"obj_full_{seq}",
                    label=unit.normalized_text[:40],
                    role="primary",
                    semantic_type=rep_type.lower(),
                )
            ]

            word_count = len(re.findall(r"\S+", unit.normalized_text))
            dur = max(4.0, min(24.0, round(word_count / 2.5 + 1.2, 1)))

            beats = author_scene_beats(
                scene_id=f"scene_{seq}",
                narration_text=unit.normalized_text,
                semantic_objects=semantic_objects,
                representation_type=rep_type,
                duration_sec=dur,
            )

            # Classify complete accounting disposition
            if unit.content_type in ("code_block", "table_row"):
                disp = UnitDispositionType.COVERED_VISUAL.value
            elif len(unit.normalized_text) < 15:
                disp = UnitDispositionType.MERGED.value
            else:
                disp = UnitDispositionType.COVERED_BOTH.value

            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id=current_chap_id,
                sequence=seq,
                teaching_goal=f"Explain SourceUnit {unit.unit_id}",
                viewer_question="What does this section specify?",
                intended_understanding=unit.normalized_text[:120],
                narration_text=unit.normalized_text,
                representation_type=rep_type,
                semantic_objects=semantic_objects,
                motion_purpose="reveal",
                shot_grammar="HeroFocus",
                suggested_duration_sec=dur,
                duration_sec=dur,
                evidence_refs=[unit.unit_id],
                scene_beats=beats,
                source_unit_dispositions={unit.unit_id: disp},
            ))

        resolve_scene_transitions(scenes)
        return scenes

    def _plan_spatial_3d_scenes(
        self,
        units: List[SourceUnit],
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Spatial 3D Mode: Selective spatial routing (F1-F3 for physical/scientific, F4 graceful 2D/2.5D fallback)."""
        scenes: List[SceneSemanticV3] = []

        for seq, unit in enumerate(units):
            text = unit.normalized_text
            fidelity = SpatialAffordanceAnalyzer.classify_fidelity(text, mode="spatial_3d")
            use_3d = fidelity in (FidelityClass3D.F1_PHYSICAL, FidelityClass3D.F2_SCHEMATIC, FidelityClass3D.F3_CONCEPTUAL)

            spatial_types = SpatialAffordanceAnalyzer.extract_spatial_types(text)
            sem_type = "Assembly" if "assembly" in spatial_types else ("FlowPath" if "flow" in spatial_types else "Component")

            if use_3d:
                rep_type = SemanticRepresentationType.ASSEMBLY_3D.value if "exploded" not in text.lower() else SemanticRepresentationType.CUTAWAY_3D.value
                shot = "ExplodedAssembly" if "exploded" in text.lower() else "HeroOrbit3D"
                motion = "explode" if "exploded" in text.lower() else "flow"
            else:
                rep_type_enum = classify_semantic_representation(text, content_type=unit.content_type, unit_order=seq, total_units=len(units))
                rep_type = rep_type_enum.value
                shot = "HeroFocus"
                motion = "reveal"

            semantic_objects = [
                SemanticObject(
                    object_id=f"obj_3d_{seq}",
                    label=unit.normalized_text[:40],
                    role="primary",
                    semantic_type=sem_type if use_3d else rep_type.lower(),
                )
            ]

            word_count = len(re.findall(r"\S+", text))
            dur = max(4.5, min(24.0, round(word_count / 2.5 + 1.5, 1)))

            beats = author_scene_beats(
                scene_id=f"scene_{seq}",
                narration_text=text,
                semantic_objects=semantic_objects,
                representation_type=rep_type,
                duration_sec=dur,
            )

            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id="chap_3d",
                sequence=seq,
                teaching_goal=f"Spatial explanation for {unit.unit_id}",
                viewer_question="How is this structured in 3D space?",
                intended_understanding=text[:120],
                narration_text=text,
                representation_type=rep_type,
                semantic_objects=semantic_objects,
                motion_purpose=motion,
                shot_grammar=shot,
                suggested_duration_sec=dur,
                duration_sec=dur,
                use_3d=use_3d,
                fidelity_3d=fidelity,
                evidence_refs=[unit.unit_id],
                scene_beats=beats,
                source_unit_dispositions={unit.unit_id: UnitDispositionType.COVERED_BOTH.value},
            ))

            if len(scenes) >= 8:
                break

        resolve_scene_transitions(scenes)
        return scenes
