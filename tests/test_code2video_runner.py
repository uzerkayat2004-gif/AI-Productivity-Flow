from __future__ import annotations

from pathlib import Path

from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner


import pytest

from voice_flow import runtime_env as _runtime_env

if not (_runtime_env.code2video_root() and (_runtime_env.code2video_root() / "prompts" / "stage1.py").is_file()):
    pytest.skip("vendored Code2Video prompts not present (third_party/code2video)", allow_module_level=True)


def test_planner_uses_vendored_outline_and_storyboard_prompts(tmp_path: Path) -> None:
    prompts: list[str] = []

    def gateway(prompt: str, **_: object) -> str:
        prompts.append(prompt)
        if "instructional design expert" in prompt:
            return """{
                "topic": "End-to-end driving",
                "target_audience": "general learners",
                "sections": [{
                    "id": "section_1",
                    "title": "The modular baseline",
                    "content": "Explain perception, planning, and control.",
                    "example": "camera to steering"
                }]
            }"""
        return """{
            "sections": [{
                "id": "section_1",
                "title": "The modular baseline",
                "lecture_lines": ["Perception finds objects.", "Planning chooses a path."],
                "animations": ["Reveal three modules.", "Connect them with arrows."]
            }]
        }"""

    gateway.is_local = True
    runner = Code2VideoRunner(gateway=gateway)
    result = runner.plan(
        "We're moving toward end-to-end neural networks for autonomous driving.",
        project_dir=tmp_path,
        duration_seconds=30,
        allow_external_ai=True,
        mode="full",
        visual_direction="diagram-first comparison",
    )

    assert result["topic"] == "End-to-end driving"
    assert result["sections"][0]["lecture_lines"][0] == "Perception finds objects."
    assert "instructional design expert" in prompts[0]
    assert "professional education Explainer and Animator" in prompts[1]
    assert "Voice Flow mode: full." in prompts[0]
    assert "Visual direction: diagram-first comparison." in prompts[1]
    assert (tmp_path / "plan" / "outline.json").is_file()
    assert (tmp_path / "storyboard" / "storyboard.json").is_file()


def test_extract_json_object_strips_markdown_bold_and_repairs():
    from voice_flow.video_flow_engine.code2video_runner import _extract_json_object

    # Case 1: wrapped in markdown bold like vf-7053030dcf214e15890cb9226fea18aa
    raw_response = """{
        "topic": "AI Productivity Flow",
        **"target_audience": "University students and professionals",**
        "sections": [{"id": "s1", "title": "Intro", "content": "Text"}]
    }"""
    parsed = _extract_json_object(raw_response)
    assert parsed["topic"] == "AI Productivity Flow"
    assert parsed["target_audience"] == "University students and professionals"
    assert len(parsed["sections"]) == 1

    # Case 2: key-level bold, unquoted bold keys, and markdown bullets with trailing commas
    raw_bullets = """
    Here is the outline:
    ```json
    {
        **"topic"**: "Test Topic",
        **target_audience**: "Learners",
        "sections": [
            * {"id": "s1", "title": "Sec 1", },
        ],
    }
    ```
    """
    parsed2 = _extract_json_object(raw_bullets)
    assert parsed2["topic"] == "Test Topic"
    assert parsed2["target_audience"] == "Learners"

    # Case 3: Python relaxed dict with single quotes and boolean true
    raw_relaxed = "{'topic': 'Relaxed', 'sections': [{'id': 's1', 'active': true}]}"
    parsed3 = _extract_json_object(raw_relaxed)
    assert parsed3["topic"] == "Relaxed"


def test_code2video_runner_respects_allow_local_fallback(tmp_path: Path):
    from voice_flow.video_flow_engine.code2video_runner import Code2VideoRunner

    def broken_gateway(_prompt: str, **_: object) -> str:
        raise RuntimeError("Gateway connection failed completely")

    broken_gateway.is_local = True
    runner = Code2VideoRunner(gateway=broken_gateway)

    # When allow_local_fallback is True, should fall back to deterministic storyboard instead of raising
    result = runner.plan(
        "Source text explaining distributed systems and consensus.",
        project_dir=tmp_path,
        duration_seconds=30,
        allow_external_ai=True,
        allow_local_fallback=True,
    )
    assert "topic" in result
    assert len(result["sections"]) >= 1
    assert (tmp_path / "storyboard" / "storyboard.json").is_file()
