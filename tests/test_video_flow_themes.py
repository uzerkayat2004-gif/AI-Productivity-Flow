from voice_flow.video_flow_themes import VideoFlowThemePolicy


def test_explicit_user_visual_direction_wins_over_subject_defaults():
    choice = VideoFlowThemePolicy().choose(
        "A bright recipe for a summer salad.",
        title="Kitchen guide",
        requested_theme="auto",
        visual_direction="Make every scene feel like a quiet midnight kitchen with deep blue light.",
    )

    assert choice["theme"] == "midnight"
    assert choice["source"] == "user_direction"
    assert "midnight" in choice["direction"].lower()


def test_auto_theme_uses_adaptive_domain_rules():
    policy = VideoFlowThemePolicy()

    kitchen = policy.choose("Chop onions, heat the pan, and finish the recipe with herbs.")
    finance = policy.choose("Revenue, margins, market growth and quarterly investment risk.")
    science = policy.choose("The experiment studies cells, molecules, data, and laboratory evidence.")

    assert kitchen["theme"] == "sunset"
    assert finance["theme"] == "midnight"
    assert science["theme"] == "ocean"
    assert kitchen["rules_version"] == finance["rules_version"] == science["rules_version"]


def test_named_theme_is_preserved_without_auto_classification():
    choice = VideoFlowThemePolicy().choose(
        "Any subject",
        requested_theme="paper",
        visual_direction="",
    )

    assert choice["theme"] == "paper"
    assert choice["source"] == "explicit_theme"


def test_domain_profiles_change_marks_operators_and_motifs():
    policy = VideoFlowThemePolicy()

    study = policy.choose("A lesson and study guide for the exam.")
    gaming = policy.choose("A player finishes a game level and earns a trophy.")
    security = policy.choose("A security audit maps a privacy threat and control.")

    assert study["domain"] == "study"
    assert gaming["domain"] == "gaming"
    assert security["domain"] == "security"
    assert study["domain_profile"]["marks"] != gaming["domain_profile"]["marks"]
    assert gaming["domain_profile"]["operators"] != security["domain_profile"]["operators"]
    assert study["domain_profile"]["motifs"] != security["domain_profile"]["motifs"]
    assert study["system"] == "notebook-explanation-v5"

def test_specific_security_domain_wins_over_broad_technology_terms():
    choice = VideoFlowThemePolicy().choose(
        "A phishing attacker captures credentials before they cross the network boundary."
    )

    assert choice["domain"] == "security"


def test_spaced_practice_is_study_not_outer_space_science():
    choice = VideoFlowThemePolicy().choose(
        'A lesson uses recall, feedback, and spaced practice before an exam.'
    )

    assert choice['domain'] == 'study'
