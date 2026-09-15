from __future__ import annotations

import json

import pytest

from voice_flow.video_flow_engine.visual_capabilities import (
    EVENT_TYPES,
    RELATIONSHIP_TYPES,
    VISUAL_CAPABILITIES,
    VisualCapabilityError,
    assert_registry_schema_alignment,
    capabilities_for_prompt,
    validate_registry_schema_alignment,
)


def test_authoritative_registry_has_a_complete_contract_for_every_active_value() -> None:
    assert validate_registry_schema_alignment()
    assert_registry_schema_alignment()
    for event_type in EVENT_TYPES:
        spec = VISUAL_CAPABILITIES.require(event_type, kind="event")
        assert spec.requirements
        assert spec.compiler_binding
        assert spec.qa_obligation
    for relation_type in RELATIONSHIP_TYPES:
        spec = VISUAL_CAPABILITIES.require(relation_type, kind="relationship")
        assert spec.compiler_binding
        assert spec.validation_obligation


def test_semantic_motion_and_camera_obligations_are_explicit() -> None:
    path = VISUAL_CAPABILITIES.require("PATH_MOTION", kind="event")
    assert path.requirements == ("subject",)
    assert path.requirement_alternatives == (("source", "destination"), ("center", "radius", "mode"))
    assert "path coordinates" in path.forbidden_behaviors

    camera = VISUAL_CAPABILITIES.require("CAMERA", kind="event")
    assert camera.requirement_alternatives == (("mode", "subject"), ("mode", "target"))

def test_registry_prompt_is_derived_from_the_same_contract() -> None:
    payload = capabilities_for_prompt()
    assert payload["event_types"] == list(EVENT_TYPES)
    assert set(payload["event_obligations"]) == set(EVENT_TYPES)
    assert set(payload["relationship_obligations"]) == set(RELATIONSHIP_TYPES)
    json.dumps(payload)


def test_unknown_capabilities_are_rejected_and_aliases_are_canonicalised() -> None:
    with pytest.raises(VisualCapabilityError):
        VISUAL_CAPABILITIES.require("invented_event", kind="event")
    assert VISUAL_CAPABILITIES.require("orbit", kind="event").name == "ORBIT_AROUND"
    assert VISUAL_CAPABILITIES.require("svg", kind="renderer_mode").name == "vector_2d"

