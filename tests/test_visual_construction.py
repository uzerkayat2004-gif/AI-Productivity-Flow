"""Tests for the Video Flow V2.1 Visual Construction Layer across all 12 Structural Families."""

import pytest
from voice_flow.video_flow_engine.visual_construction import (
    SubjectBlueprint,
    SemanticPart,
    PartRelationship,
    AppearanceIntent,
    AnimationBinding,
    SubjectConstraintSolver,
    SubjectFidelityQA,
    VisualConstructionError,
    construct_apple_growth,
    construct_heart_circulation,
    construct_fluid_system,
    construct_four_stroke_engine,
    construct_house_construction,
    construct_castle_architecture,
    construct_volcano_terrain,
    construct_thunderstorm,
    construct_network,
    construct_mars_orbit,
    construct_ai_data_center,
    construct_resnet_block,
    build_subject_blueprint,
    _GRAMMAR_FACTORIES,
)
from voice_flow.video_flow_engine.representation_resolver import (
    RepresentationResolver,
    resolve_representation,
)


class TestVisualConstructionDataModels:
    """Test data model contracts and immutability."""

    def test_semantic_part_immutability_and_dict(self):
        part = SemanticPart(
            part_id="piston_01",
            name="Reciprocating Piston",
            kind="rect",
            geometry_role="piston",
            palette_role="primary_structure",
            position=(0.5, 0.4, 0.2),
            geometry={"origin": (0.38, 0.32), "width": 0.24, "height": 0.12},
        )
        assert part.part_id == "piston_01"
        assert part.palette_role == "primary_structure"
        d = part.to_dict()
        assert d["part_id"] == "piston_01"
        assert d["position"] == [0.5, 0.4, 0.2]
        with pytest.raises(Exception):
            part.kind = "circle"

    def test_subject_blueprint_serialization(self):
        blueprint = construct_apple_growth("tree_01")
        assert blueprint.subject_id == "tree_01"
        assert blueprint.structural_family == "organic_branching"
        d = blueprint.to_dict()
        assert d["subject_id"] == "tree_01"
        assert len(d["parts"]) >= 7
        assert len(d["relationships"]) >= 6
        assert len(d["animation_bindings"]) >= 3


class TestSubjectConstraintSolver:
    """Test deterministic local constraint solving."""

    def test_solve_spatial_relationships(self):
        solver = SubjectConstraintSolver()
        blueprint = construct_four_stroke_engine("engine_test")
        solved = solver.solve(blueprint)
        assert len(solved) == len(blueprint.parts)
        for pid, pos in solved.items():
            assert 0.0 <= pos[0] <= 1.0, f"X out of bounds for {pid}: {pos[0]}"
            assert 0.0 <= pos[1] <= 1.0, f"Y out of bounds for {pid}: {pos[1]}"

    def test_solve_branching_and_attachments(self):
        solver = SubjectConstraintSolver()
        blueprint = construct_apple_growth("apple_test")
        solved = solver.solve(blueprint)
        assert solved["secondary_twig_left"][0] <= solved["branch_trunk"][0]
        assert solved["secondary_twig_right"][0] >= solved["branch_trunk"][0]
        assert solved["apple_fruit"][1] >= solved["apple_stem"][1]


class TestAllTwelveStructuralConstructionGrammars:
    """Test all 12 structural family grammars for construction validity."""

    @pytest.mark.parametrize("family,constructor", [
        ("organic_branching", construct_apple_growth),
        ("organic_body", construct_heart_circulation),
        ("fluid_system", construct_fluid_system),
        ("mechanical_linkage", construct_four_stroke_engine),
        ("rigid_assembly", construct_house_construction),
        ("architecture", construct_castle_architecture),
        ("terrain", construct_volcano_terrain),
        ("atmospheric_system", construct_thunderstorm),
        ("network", construct_network),
        ("celestial_body", construct_mars_orbit),
        ("infrastructure", construct_ai_data_center),
        ("mathematical_geometry", construct_resnet_block),
    ])
    def test_structural_grammar_validity(self, family, constructor):
        blueprint = constructor()
        assert blueprint.structural_family == family
        qa = SubjectFidelityQA.validate_blueprint(blueprint)
        assert qa["valid"] is True
        assert qa["part_count"] >= 5
        assert qa["relationship_count"] >= 4


class TestSubjectFidelityQA:
    """Test deterministic QA verification."""

    def test_reject_empty_parts(self):
        blueprint = SubjectBlueprint(
            subject_id="empty",
            semantic_name="Empty Subject",
            structural_family="organic_branching",
            parts=(),
            relationships=(),
            appearance_intent=AppearanceIntent(family="organic_branching"),
        )
        with pytest.raises(VisualConstructionError):
            SubjectFidelityQA.validate_blueprint(blueprint)

    def test_reject_invalid_relationship_reference(self):
        part = SemanticPart("p1", "Part 1", "circle")
        rel = PartRelationship("p1", "above", "p_nonexistent")
        blueprint = SubjectBlueprint(
            subject_id="broken_rel",
            semantic_name="Broken Relation",
            structural_family="organic_branching",
            parts=(part,),
            relationships=(rel,),
            appearance_intent=AppearanceIntent(family="organic_branching"),
        )
        with pytest.raises(VisualConstructionError):
            SubjectFidelityQA.validate_blueprint(blueprint)


class TestResolverIntegration:
    """Test that RepresentationResolver uses the Visual Construction Layer."""

    def test_resolve_apple_tree_produces_rich_parts(self):
        resolver = RepresentationResolver()
        subject = {"id": "apple_01", "name": "Apple Growth", "structural_family": "organic_branching"}
        plan = resolver.resolve(subject)
        assert plan.subject_id == "apple_01"
        assert len(plan.parts) >= 7
        part_ids = {p["id"] for p in plan.parts}
        assert "branch_trunk" in part_ids

    def test_resolve_four_stroke_engine_produces_linkage(self):
        plan = resolve_representation({"id": "engine_01", "name": "4-Stroke Combustion Engine", "structural_family": "mechanical_linkage"})
        assert len(plan.parts) >= 8
        part_ids = {p["id"] for p in plan.parts}
        assert "piston" in part_ids
        assert "crankshaft" in part_ids

    def test_resolve_heart_circulation(self):
        plan = resolve_representation({"id": "heart_01", "name": "Human Cardiac Cycle", "structural_family": "organic_body"})
        assert len(plan.parts) >= 7
        part_ids = {p["id"] for p in plan.parts}
        assert "left_ventricle" in part_ids

    def test_resolve_mars_orbit(self):
        plan = resolve_representation({"id": "mars_01", "name": "Mars Orbital Mechanics", "structural_family": "celestial_body"})
        assert len(plan.parts) >= 4
        part_ids = {p["id"] for p in plan.parts}
        assert "star" in part_ids
        assert "planet" in part_ids

