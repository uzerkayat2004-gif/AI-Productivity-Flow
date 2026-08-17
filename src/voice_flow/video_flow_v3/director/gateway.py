"""V3 AI Creative Director Gateway.

Routes semantic scene authoring to user-selected LLM models (Gemini, Claude, OpenAI, Groq, Combos)
via VideoModelGateway & provider connections while enforcing:
1. Strict AI Security Boundary: NO executable code (eval/JS/Python/shaders/HTML/SVG).
2. NO raw pixel coordinates (x, y) or camera XYZ.
3. External AI consent policies.
4. Fallback to deterministic semantic planning when models are offline.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from voice_flow.video_flow_v3.contracts import (
    SourceBundle,
    SourceUnit,
    EvidenceGraph,
    CoverageLedger,
    ArtDirectionGenome,
    SceneSemanticV3,
    SemanticObject,
    FidelityClass3D,
    validate_no_executable_code,
)

log = logging.getLogger(__name__)


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
        allow_external_ai: bool = True,
    ) -> List[SceneSemanticV3]:
        """Prompt selected LLM to author semantic scene intents (representation, teaching goals, viewer questions)."""

        # System prompt enforcing strict data-only security boundary
        system_prompt = (
            "You are CreativeDirectorV3, an expert visual explanation director.\n"
            "Author a structured JSON array of semantic scenes.\n"
            "CRITICAL SECURITY RULES:\n"
            "1. Output DATA ONLY. Absolutely NO JavaScript, Python, HTML, CSS, SVG, or shader code.\n"
            "2. Do NOT output pixel coordinates (x, y) or camera XYZ. Deterministic compilers handle layout.\n"
            "3. Choose representation_type from: PROCESS, COMPARISON, TIMELINE, HIERARCHY, NETWORK, QUANTITATIVE, SYSTEM_ARCHITECTURE, OBJECT_FOCUS, FLOW, ASSEMBLY_3D, CUTAWAY_3D.\n"
            "4. Ground all scene claims strictly in provided SourceUnit IDs.\n"
        )

        # Incorporate visual direction prompt if provided
        user_prompt = f"SOURCE TEXT:\n{bundle.source_text}\n\nMODE: {mode.upper()}\n"
        if visual_direction:
            user_prompt += f"VISUAL DIRECTION HINT (Source facts take priority):\n{visual_direction}\n\n"

        user_prompt += f"SOURCE UNITS:\n" + "\n".join([f"[{u.unit_id}] ({u.content_type}): {u.normalized_text}" for u in units[:15]])

        # If LLM model gateway is available and allowed, attempt structured LLM authoring
        if self.model_gateway and model_ref and model_ref != "local/deterministic" and allow_external_ai:
            try:
                raw_json = self._call_model_gateway(model_ref, system_prompt, user_prompt)
                if raw_json:
                    parsed_scenes = self._parse_llm_scenes(raw_json, units, mode)
                    if parsed_scenes:
                        log.info(f"V3 Creative Director: LLM '{model_ref}' authored {len(parsed_scenes)} semantic scenes.")
                        return parsed_scenes
            except Exception as exc:
                log.warning(f"V3 Creative Director LLM call to '{model_ref}' failed: {exc}. Falling back to deterministic planner.")

        # Deterministic fallback when offline or local model selected
        return self._deterministic_fallback_plan(units, mode, genome)

    def _call_model_gateway(self, model_ref: str, system_prompt: str, user_prompt: str) -> Optional[str]:
        if not self.model_gateway:
            return None
        # Route via VideoModelGateway
        if hasattr(self.model_gateway, "request_scene_plan"):
            return self.model_gateway.request_scene_plan(model_ref, system_prompt, user_prompt)
        return None

    def _parse_llm_scenes(self, raw_json: str, units: List[SourceUnit], mode: str) -> List[SceneSemanticV3]:
        """Validate LLM output against security boundary and contracts."""
        try:
            data = json.loads(raw_json)
            validate_no_executable_code(data)
            scenes = []
            for idx, raw_sc in enumerate(data.get("scenes", [])):
                scenes.append(SceneSemanticV3(
                    scene_id=f"scene_{idx}",
                    chapter_id=str(raw_sc.get("chapter_id", "chap_0")),
                    sequence=idx,
                    teaching_goal=str(raw_sc.get("teaching_goal", "Visual explanation")),
                    viewer_question=str(raw_sc.get("viewer_question", "What is happening?")),
                    intended_understanding=str(raw_sc.get("intended_understanding", "")),
                    narration_text=str(raw_sc.get("narration_text", "")),
                    semantic_objects=[
                        SemanticObject(
                            object_id=str(o.get("object_id", f"obj_{idx}_{i}")),
                            label=str(o.get("label", "Concept")),
                            role=str(o.get("role", "primary")),
                            semantic_type=str(o.get("semantic_type", "claim_card")),
                        )
                        for i, o in enumerate(raw_sc.get("semantic_objects", []))
                    ],
                    motion_purpose=str(raw_sc.get("motion_purpose", "reveal")),
                    shot_grammar=str(raw_sc.get("shot_grammar", "HeroFocus")),
                    suggested_duration_sec=float(raw_sc.get("suggested_duration_sec", 5.0)),
                    use_3d=bool(raw_sc.get("use_3d", False)),
                    evidence_refs=list(raw_sc.get("evidence_refs", [])),
                ))
            return scenes
        except Exception as err:
            log.warning(f"LLM scene JSON validation failed: {err}")
            return []

    def _deterministic_fallback_plan(
        self,
        units: List[SourceUnit],
        mode: str,
        genome: ArtDirectionGenome,
    ) -> List[SceneSemanticV3]:
        """Deterministic semantic fallback when LLM is offline."""
        scenes: List[SceneSemanticV3] = []
        chunk_size = max(1, len(units) // 4) if mode == "summary" else 1

        for i in range(0, len(units), chunk_size):
            chunk = units[i : i + chunk_size]
            seq = len(scenes)
            combined = " ".join(u.normalized_text for u in chunk)
            text_lower = combined.lower()

            # Varied representation selection based on content semantics
            sem_type = "claim_card"
            if "versus" in text_lower or "than" in text_lower or "compared" in text_lower:
                sem_type = "Comparison"
            elif "step" in text_lower or "first" in text_lower or "then" in text_lower:
                sem_type = "Process"
            elif "year" in text_lower or "date" in text_lower or "history" in text_lower:
                sem_type = "Timeline"
            elif "code" in text_lower or "function" in text_lower or "def " in text_lower:
                sem_type = "CodeExplanation"
            elif any(w in text_lower for w in ["structure", "assembly", "component", "drivetrain"]):
                sem_type = "Assembly"

            motion = "compare" if sem_type == "Comparison" else ("flow" if sem_type == "Process" else "reveal")
            shot = "Inspect" if seq % 2 == 1 else "HeroFocus"

            scenes.append(SceneSemanticV3(
                scene_id=f"scene_{seq}",
                chapter_id="chap_0",
                sequence=seq,
                teaching_goal=f"Explain section {seq + 1}",
                viewer_question="How does this function?",
                intended_understanding=chunk[0].normalized_text[:120],
                narration_text=combined,
                semantic_objects=[
                    SemanticObject(
                        object_id=f"obj_{seq}_{u_idx}",
                        label=u.normalized_text[:40],
                        role="primary" if u_idx == 0 else "secondary",
                        semantic_type=sem_type,
                    )
                    for u_idx, u in enumerate(chunk[:3])
                ],
                motion_purpose=motion,
                shot_grammar=shot,
                suggested_duration_sec=5.0,
                evidence_refs=[u.unit_id for u in chunk],
            ))

        return scenes
