import pytest
from dataclasses import dataclass
from voice_flow.video_flow_engine.scene_evaluator_v21 import (
    check_cue_spread,
    evaluate_scene_v21,
    evaluate_video_v21,
)

@dataclass
class DummySubject:
    id: str
    structural_family: str

@dataclass
class DummyRelationship:
    source: str
    target: str

@dataclass
class DummySceneProgram:
    scene_id: str
    subjects: list[DummySubject]
    relationships: list[DummyRelationship]
    representation_strategy: list[str]

@dataclass
class DummyVideoProgram:
    scenes: list[DummySceneProgram]


def test_front_loaded_animation():
    html = '<div data-cue="0"></div>' * 10
    spread, max_cue, distinct, front_loaded = check_cue_spread(html)
    assert front_loaded is True
    assert distinct == 1
    assert max_cue == 0
    assert spread == 1.0


def test_cue_spread_good():
    html = '<div data-cue="0"></div><div data-cue="1"></div><div data-cue="2"></div><div data-cue="3"></div>'
    spread, max_cue, distinct, front_loaded = check_cue_spread(html)
    assert not front_loaded
    assert max_cue == 3
    assert distinct == 4
    assert spread >= 0.5


def test_video_structural_diversity_low():
    scene1 = DummySceneProgram(
        scene_id="s1",
        subjects=[DummySubject("obj1", "cards"), DummySubject("obj2", "cards")],
        relationships=[],
        representation_strategy=["cards"]
    )
    scene2 = DummySceneProgram(
        scene_id="s2",
        subjects=[DummySubject("obj3", "cards")],
        relationships=[],
        representation_strategy=["cards"]
    )
    program = DummyVideoProgram(scenes=[scene1, scene2])
    
    class DummyCompiledProduction:
        def __init__(self, scenes):
            self.scenes = scenes
            
    compiled = DummyCompiledProduction(scenes=[
        {"body": '<div id="obj1"></div><div id="obj2"></div>'},
        {"body": '<div id="obj3"></div>'}
    ])
    
    result = evaluate_video_v21(program, compiled)
    assert result.structural_diversity_score < 0.5
    assert result.distinct_families_used == 1


def test_video_structural_diversity_high():
    scene1 = DummySceneProgram(
        scene_id="s1",
        subjects=[DummySubject("obj1", "cards"), DummySubject("obj2", "3d_model")],
        relationships=[],
        representation_strategy=["cards"]
    )
    scene2 = DummySceneProgram(
        scene_id="s2",
        subjects=[DummySubject("obj3", "particles"), DummySubject("obj4", "typography")],
        relationships=[],
        representation_strategy=["particles"]
    )
    program = DummyVideoProgram(scenes=[scene1, scene2])
    
    class DummyCompiledProduction:
        def __init__(self, scenes):
            self.scenes = scenes
            
    compiled = DummyCompiledProduction(scenes=[
        {"body": '<div id="obj1"></div><div id="obj2"></div>'},
        {"body": '<div id="obj3"></div><div id="obj4"></div>'}
    ])
    
    result = evaluate_video_v21(program, compiled)
    assert result.structural_diversity_score >= 0.5
    assert result.distinct_families_used == 4
