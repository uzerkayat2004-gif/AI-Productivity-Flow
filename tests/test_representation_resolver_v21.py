"""Structural-family and safe-descriptor tests for the V2.1 resolver."""

from __future__ import annotations

import json

import pytest

from voice_flow.video_flow_engine.representation_resolver import STRUCTURAL_FAMILIES, RepresentationResolverError, resolve_representation


def test_all_structural_families_emit_recognizable_parts_and_safe_descriptors() -> None:
    for family in sorted(STRUCTURAL_FAMILIES):
        result = resolve_representation({"id": "demo", "semantic_name": "demo", "structural_family": family})
        assert result["family"] == family
        assert result["parts"]
        assert result["svg"]["forms"]
        assert result["three"]["objects"]
        encoded = json.dumps(result.to_dict()).lower()
        assert "<script" not in encoded
        assert "javascript:" not in encoded
        assert "threemodule" not in encoded
        assert "<svg" not in encoded
        assert all("color" not in json.dumps(part).lower() for part in result["parts"])


def test_family_output_is_deterministic_and_uses_numeric_data_when_present() -> None:
    subject = {"id": "revenue", "semantic_name": "quarterly revenue", "structural_family": "quantitative_data", "values": [0.2, 0.7, 0.4]}
    first = resolve_representation(subject).to_dict()
    second = resolve_representation(subject).to_dict()
    assert first == second
    bars = [form for form in first["svg"]["forms"] if form["kind"] == "bars"]
    assert bars
    assert bars[0]["geometry"]["height"] in subject["values"]


def test_orbit_descriptor_uses_group_center_and_child_offset() -> None:
    result = resolve_representation({"id": "planetary", "structural_family": "celestial_body", "events": [{"type": "PATH_MOTION", "subject": "planet", "path": {"kind": "orbit", "center": "star", "radius": 0.28}, "duration": 4}]})
    group = result["three"]["groups"][0]
    assert group["type"] == "group"
    assert group["children"]
    child = next(item for item in group["children"] if item["id"] == "planet")
    assert child["position"] != [0.0, 0.0, 0.0]
    assert group["animate"]["property"] == "rotation.y"
    assert result["animations"][0]["kind"] == "orbit_position"


def test_untrusted_markup_and_unknown_family_do_not_cross_the_boundary() -> None:
    result = resolve_representation({"id": "<script>alert(1)</script>", "semantic_name": "<script>bad</script>", "structural_family": "organic_body"})
    encoded = json.dumps(result.to_dict()).lower()
    assert "<script" not in encoded
    with pytest.raises(RepresentationResolverError):
        resolve_representation({"id": "x", "structural_family": "subject_template"})
