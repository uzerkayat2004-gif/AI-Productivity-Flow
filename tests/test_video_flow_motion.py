from __future__ import annotations

from voice_flow.video_flow import VideoFlowPlanner
from voice_flow.video_flow_motion import VideoMotionDirector


def _plan(domain: str = "study") -> dict:
    return {
        "title": "How learning changes memory",
        "mode": "summary",
        "fps": 24,
        "scenes": [
            {
                "id": "scene-001",
                "type": "hook",
                "title": "A memory begins as a fragile trace",
                "body": "A new idea enters working memory before practice strengthens it.",
                "narration": "A new idea enters working memory before practice strengthens it.",
                "domain": domain,
                "durationSeconds": 8.0,
                "visualBeats": [
                    {"text": "A new idea enters working memory", "startRatio": 0.0, "endRatio": 0.48},
                    {"text": "practice strengthens it", "startRatio": 0.48, "endRatio": 1.0},
                ],
            },
            {
                "id": "scene-002",
                "type": "process",
                "title": "Practice builds retrieval paths",
                "body": "Recall, feedback, and spacing turn a weak trace into a reliable path.",
                "narration": "Recall, feedback, and spacing turn a weak trace into a reliable path.",
                "domain": domain,
                "durationSeconds": 9.0,
                "visualBeats": [
                    {"text": "Recall", "startRatio": 0.0, "endRatio": 0.25},
                    {"text": "feedback", "startRatio": 0.25, "endRatio": 0.5},
                    {"text": "spacing", "startRatio": 0.5, "endRatio": 0.75},
                    {"text": "reliable path", "startRatio": 0.75, "endRatio": 1.0},
                ],
            },
        ],
    }


def test_motion_director_builds_renderable_semantic_choreography() -> None:
    directed = VideoMotionDirector().direct(_plan(), video_id="video-one")

    assert directed["motionSystem"]["name"] == "notebook-explanation-director-v5"
    assert directed["motionSystem"]["diversityWindow"] == 10
    assert directed["animationSignature"]
    for scene in directed["scenes"]:
        motion = scene["motionPlan"]
        assert motion["signature"]
        assert len(motion["objects"]) >= 3
        assert motion["actions"]
        assert motion["renderWindows"]
        assert motion["camera"]["mode"] in {"push", "pullback", "pan", "track", "tilt"}
        assert all(0 <= item["x"] <= 1 and 0 <= item["y"] <= 1 for item in motion["objects"])
        assert all(action["cue"] for action in motion["actions"])


def test_ten_videos_do_not_reuse_a_scene_animation_signature() -> None:
    director = VideoMotionDirector()
    history: list[dict] = []
    seen: set[str] = set()

    for index in range(10):
        directed = director.direct(
            _plan(),
            video_id=f"video-{index}",
            recent_history=history[-10:],
        )
        signatures = {scene["motionPlan"]["designSignature"] for scene in directed["scenes"]}
        assert signatures.isdisjoint(seen)
        seen.update(signatures)
        history.append({
            "video_signature": directed["animationSignature"],
            "scene_signatures": sorted(signatures),
        })


def test_domain_changes_the_visual_vocabulary_not_only_the_palette() -> None:
    director = VideoMotionDirector()
    study = director.direct(_plan("study"), video_id="study-video")
    security = director.direct(_plan("security"), video_id="security-video")

    study_motion = study["scenes"][0]["motionPlan"]
    security_motion = security["scenes"][0]["motionPlan"]

    assert study_motion["domainGrammar"] != security_motion["domainGrammar"]
    assert {item["glyph"] for item in study_motion["objects"]} != {
        item["glyph"] for item in security_motion["objects"]
    }
    assert [action["kind"] for action in study_motion["actions"]] != [
        action["kind"] for action in security_motion["actions"]
    ]


def test_same_content_rotates_through_structural_layout_families() -> None:
    director = VideoMotionDirector()
    variants = {
        director.direct(_plan("security"), video_id=f"layout-video-{index}")["scenes"][0]["motionPlan"]["illustrationPlan"]["layoutVariant"]
        for index in range(10)
    }

    assert len(variants) >= 3


def test_v5_enforces_distinct_notebook_editorial_medium() -> None:
    directed = VideoMotionDirector().direct(_plan("science"), video_id="editorial-medium")

    assert directed["artDirection"]["background"] == "notebook-paper"
    assert directed["artDirection"]["shapeLanguage"].startswith("notebook-")
    assert directed["artDirection"]["visualDialect"].startswith("science-")
    assert directed["artDirection"]["assetTreatment"]
    assert directed["motionSystem"]["renderer"] == "editorial-storyboard-v5"

def test_edge_word_boundaries_retime_semantic_actions() -> None:
    director = VideoMotionDirector()
    directed = director.direct(_plan(), video_id="timed-video")
    scene = directed["scenes"][0]
    first_action = scene["motionPlan"]["actions"][0]
    first_action["cue"] = "practice"
    original = first_action["startRatio"]
    scene["wordTimings"] = [
        {"text": "A", "offsetSeconds": 0.0, "durationSeconds": 0.1},
        {"text": "practice", "offsetSeconds": 5.0, "durationSeconds": 0.4},
    ]
    scene["durationSeconds"] = 8.0

    director.synchronize_scene(scene)

    assert first_action["startRatio"] != original
    assert first_action["startRatio"] == 0.625
    assert scene["motionPlan"]["renderWindows"]

def test_local_visual_intent_extracts_concrete_phishing_objects() -> None:
    intent = VideoFlowPlanner._visual_intent(
        "A phishing email copies a trusted login page and places a deceptive link inside an urgent message."
    )

    assert "trusted login page" in intent["entities"]
    assert "deceptive link" in intent["entities"]
    assert "urgent message" in intent["entities"]
    assert "inside" not in {item.lower() for item in intent["entities"]}


def test_phrase_selection_rejects_near_duplicate_labels() -> None:
    phrases = VideoMotionDirector._phrases({
        "title": "Trusted login page",
        "visualIntent": {
            "entities": ["the trusted login page", "deceptive link", "urgent message"],
            "actions": [],
            "relationships": [],
        },
    })

    assert phrases.count("Trusted login page") == 1
    assert len(phrases) == 3

def test_visual_grammar_changes_construction_for_different_meanings() -> None:
    director = VideoMotionDirector()
    sequence_plan = _plan("technology")
    sequence_plan["scenes"][0]["visualIntent"] = {
        "entities": ["request", "service", "response"],
        "actions": ["routes", "fans out", "converges"],
        "relationships": ["ordered flow"],
        "metaphor": "a packet travelling through a service constellation",
        "mood": "technical precision",
        "dataShape": "sequence",
    }
    quantity_plan = _plan("business")
    quantity_plan["scenes"][0]["visualIntent"] = {
        "entities": ["revenue", "risk", "decision"],
        "actions": ["rises", "falls", "changes"],
        "relationships": ["measured change"],
        "metaphor": "a market signal tipping a decision balance",
        "mood": "editorial data story",
        "dataShape": "quantity",
    }

    sequence = director.direct(sequence_plan, video_id="sequence-document")["scenes"][0]["motionPlan"]["visualGrammar"]
    quantity = director.direct(quantity_plan, video_id="quantity-document")["scenes"][0]["motionPlan"]["visualGrammar"]

    assert sequence["dataShape"] == "sequence"
    assert quantity["dataShape"] == "quantity"
    assert sequence["operators"] != quantity["operators"]
    assert sequence["marks"] != quantity["marks"]
    assert sequence["fingerprint"] != quantity["fingerprint"]

def test_scene_plan_contains_a_readable_explanation_contract() -> None:
    directed = VideoMotionDirector().direct(_plan("study"), video_id="explanation-contract")

    for scene in directed["scenes"]:
        explanation = scene["motionPlan"]["explanationPlan"]
        assert explanation["construction"]
        assert 1 <= len(explanation["takeaway"].split()) <= 14
        assert explanation["readingOrder"] == [
            prop["id"] for prop in scene["motionPlan"]["illustrationPlan"]["props"]
        ]
        assert [stage["purpose"] for stage in explanation["stages"]] == [
            "context", "mechanism", "consequence", "takeaway"
        ]
        assert all(relation["label"] for relation in explanation["relations"])


def test_domains_receive_materially_distinct_visual_dialects() -> None:
    director = VideoMotionDirector()
    directions = [
        director.direct(_plan(domain), video_id=f"dialect-{domain}")["artDirection"]
        for domain in ("study", "security", "business", "food", "science")
    ]

    assert len({direction["visualDialect"] for direction in directions}) == len(directions)
    assert len({
        (direction["paperPattern"], direction["assetTreatment"], direction["connectorStyle"])
        for direction in directions
    }) >= 4


def test_ten_same_topic_videos_rotate_real_constructions_not_coordinates() -> None:
    director = VideoMotionDirector()
    constructions = {
        director.direct(_plan("security"), video_id=f"construction-{index}")
        ["scenes"][0]["motionPlan"]["explanationPlan"]["construction"]
        for index in range(10)
    }

    assert len(constructions) >= 4

def test_four_videos_reserve_four_distinct_physical_animation_systems() -> None:
    director = VideoMotionDirector()
    history: list[dict] = []
    systems: set[tuple[str, str, str, str]] = set()

    for domain in ("study", "security", "business", "food"):
        directed = director.direct(
            _plan(domain), video_id=f"four-way-{domain}", recent_history=history,
        )
        direction = directed["artDirection"]
        construction = directed["scenes"][0]["motionPlan"]["explanationPlan"]["construction"]
        systems.add((
            direction["paperPattern"], direction["assetTreatment"],
            direction["connectorStyle"], construction,
        ))
        signatures = [scene["motionPlan"]["designSignature"] for scene in directed["scenes"]]
        history.append({
            "domain": f"{domain}|{direction['id']}",
            "art_direction_id": direction["id"],
            "video_signature": directed["animationSignature"],
            "scene_signatures": signatures,
        })

    assert len(systems) == 4