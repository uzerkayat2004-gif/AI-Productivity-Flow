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
    SemanticObject,
    SemanticRepresentationType,
    FidelityClass3D,
    validate_no_executable_code,
)

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
    if any(k in text_lower for k in ["cutaway", "internal section", "cross-section", "exploded view"]):
        return SemanticRepresentationType.CUTAWAY_3D
    if any(k in text_lower for k in ["assembly", "chassis", "cad model", "engine block", "mechanical structure", "physical structure", "drivetrain"]):
        return SemanticRepresentationType.ASSEMBLY_3D

    # 6. Comparisons / Contrasts
    if any(k in text_lower for k in [" versus ", " vs ", " vs. ", "compared to", "differ from", "contrast with", "advantage", "trade-off", "faster than", "better than", "in contrast"]):
        return SemanticRepresentationType.COMPARISON

    # 7. Before / After & Transformations
    if any(k in text_lower for k in ["before and after", "before/after", "previously", "migrated to", "transformed into", "upgrade from"]):
        return SemanticRepresentationType.BEFORE_AFTER
    if any(k in text_lower for k in ["transformation", "converts", "transforms", "metamorphosis", "evolves into"]):
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
    if any(k in text_lower for k in ["step 1", "step 2", "step 3", "first,", "second,", "then,", "next,", "finally,", "procedure", "stage 1", "stage 2", "workflow"]):
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
        """Prompt selected LLM to author semantic scene intents (representation, teaching goals, viewer questions).

        Enforces default DENY: allow_external_ai MUST evaluate to True to execute any provider call.
        """
        # Enforce AI consent default DENY
        if not allow_external_ai or not model_ref or model_ref == "local/deterministic":
            log.info("V3 Creative Director: Using deterministic semantic planner (external AI consent: %s, model: %s)", allow_external_ai, model_ref)
            return self._deterministic_fallback_plan(units, mode, genome)

        # Canonical vocabulary description
        canonical_vocab = ", ".join([t.value for t in SemanticRepresentationType])

        # System prompt enforcing strict data-only security boundary and contracts
        system_prompt = (
            "You are CreativeDirectorV3, an expert visual explanation director.\n"
            "Author a structured JSON object with a 'scenes' array defining semantic scene intents.\n\n"
            "CRITICAL SECURITY RULES:\n"
            "1. Output DATA ONLY. Absolutely NO JavaScript, Python, HTML, CSS, SVG, or shader code.\n"
            "2. Do NOT output pixel coordinates (x, y) or camera XYZ. Deterministic compilers compute layout.\n"
            "3. Choose representation_type ONLY from canonical vocabulary: " + canonical_vocab + ".\n"
            "4. Ground all scene claims strictly in provided SourceUnit IDs via 'evidence_refs'.\n"
            "5. Return JSON ONLY with format:\n"
            '{"scenes": [{"representation_type": "...", "teaching_goal": "...", "viewer_question": "...", "intended_understanding": "...", "narration_text": "...", "semantic_objects": [{"object_id": "...", "label": "...", "role": "primary|secondary|annotation", "semantic_type": "..."}], "motion_purpose": "...", "shot_grammar": "...", "suggested_duration_sec": 5.0, "use_3d": false, "evidence_refs": ["..."]}]}'
        )

        # Build hierarchical / chunked complete-source representation for long documents (NO arbitrary slicing)
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

        # Route via model gateway if configured
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
            # Strip markdown formatting if returned
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

                # Validate and normalize representation_type against canonical vocabulary
                raw_rep = str(raw_sc.get("representation_type", "")).strip().upper()
                rep_type = SemanticRepresentationType.PROCESS.value
                for member in SemanticRepresentationType:
                    if member.value == raw_rep or member.name == raw_rep:
                        rep_type = member.value
                        break

                # Parse semantic_objects
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

                # Preserve 100% provenance back to original SourceUnit IDs
                raw_refs = raw_sc.get("evidence_refs", [])
                evidence_refs = [r for r in raw_refs if r in valid_unit_ids] if isinstance(raw_refs, list) else []
                if not evidence_refs and units:
                    target_idx = min(idx, len(units) - 1)
                    evidence_refs = [units[target_idx].unit_id]

                dur = float(raw_sc.get("suggested_duration_sec", 5.0))
                dur = max(3.0, min(60.0, dur))

                scenes.append(SceneSemanticV3(
                    scene_id=f"scene_{idx}",
                    chapter_id=str(raw_sc.get("chapter_id", f"chap_{idx // 4}")),
                    sequence=idx,
                    teaching_goal=str(raw_sc.get("teaching_goal", f"Explain concept {idx+1}")),
                    viewer_question=str(raw_sc.get("viewer_question", "How does this function?")),
                    intended_understanding=str(raw_sc.get("intended_understanding", "")),
                    narration_text=str(raw_sc.get("narration_text", "")),
                    representation_type=rep_type,
                    semantic_objects=semantic_objects,
                    motion_purpose=str(raw_sc.get("motion_purpose", "reveal")),
                    shot_grammar=str(raw_sc.get("shot_grammar", "HeroFocus")),
                    suggested_duration_sec=dur,
                    duration_sec=dur,
                    use_3d=bool(raw_sc.get("use_3d", False)),
                    fidelity_3d=FidelityClass3D.F1_PHYSICAL if bool(raw_sc.get("use_3d")) else FidelityClass3D.F4_INSUFFICIENT,
                    evidence_refs=evidence_refs,
                ))

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
        """Deterministic semantic fallback mapping units to realistic semantic representation types."""
        if not units:
            return []

        scenes: List[SceneSemanticV3] = []
        total_units = len(units)

        if mode == "summary":
            # Chunk long documents into 4-8 bounded balanced scenes covering ALL units
            target_scene_count = min(8, max(4, total_units // 3)) if total_units >= 4 else total_units
            chunk_size = max(1, (total_units + target_scene_count - 1) // target_scene_count)
        else:
            # Full mode: each unit or logical pair forms a scene for 100% complete accounting
            chunk_size = 1

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

            # Determine motion and shot grammar according to semantic type
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

            # Build semantic objects for this scene
            semantic_objects: List[SemanticObject] = []
            for u_idx, u in enumerate(chunk[:3]):
                semantic_objects.append(SemanticObject(
                    object_id=f"obj_{seq}_{u_idx}",
                    label=u.normalized_text[:45],
                    role="primary" if u_idx == 0 else "secondary",
                    semantic_type=rep_type.lower(),
                ))

            word_count = len(re.findall(r"\S+", combined_text))
            dur = max(4.0, round(word_count / 2.6 + 1.2, 1))

            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id=f"chap_{seq // 4}",
                sequence=seq,
                teaching_goal=f"Explain {primary_unit.normalized_text[:50]}",
                viewer_question="How does this function and relate to the topic?",
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
            ))

        return scenes
