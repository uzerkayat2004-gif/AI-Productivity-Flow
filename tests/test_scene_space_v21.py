from __future__ import annotations

import math

import pytest

from voice_flow.video_flow_engine.scene_space import Rect, SceneSpace, SceneSpaceError


def test_default_space_matches_narova_logical_stage_and_pixel_metadata() -> None:
    space = SceneSpace()

    assert (space.logical_width, space.logical_height) == (1280, 720)
    assert space.pixel_target == (1920, 1080)
    assert space.aspect_ratio == pytest.approx(16 / 9)
    assert space.pixel_aspect_ratio == pytest.approx(16 / 9)
    assert str(space.svg_viewbox) == "0 0 1280 720"
    assert space.svg_viewbox() == "0 0 1280 720"
    assert space.three_aspect == pytest.approx(16 / 9)


def test_normalized_conversion_is_resolution_independent() -> None:
    space = SceneSpace()
    normalized = Rect(0.125, 0.25, 0.5, 0.25)

    logical = space.denormalize(normalized)
    pixels = space.normalized_to_pixel(normalized)

    assert logical == Rect(160, 180, 640, 180)
    assert pixels == Rect(240, 270, 960, 270)
    assert space.pixel_to_normalized(pixels) == normalized
    assert space.normalized_to_logical(normalized) == logical


def test_caption_region_and_safe_insets_define_content_region() -> None:
    space = SceneSpace()
    content = space.content_rect

    assert content.x >= space.safe_insets.left
    assert content.y >= space.safe_insets.top
    assert content.right <= space.logical_width - space.safe_insets.right
    assert content.bottom <= space.caption_region.y
    assert space.is_caption_safe(space.normalize(content))
    assert not space.is_caption_safe(space.normalize(Rect(content.x, space.caption_region.y, 100, 20)))


def test_three_position_uses_normalized_center_and_flips_browser_y() -> None:
    space = SceneSpace()

    assert space.three_position(Rect(0, 0, 0, 0)) == pytest.approx((-1, 1, 0))
    assert space.three_position(Rect(0.25, 0.25, 0.5, 0.5), depth=2) == pytest.approx((0, 0, 2))
    assert space.logical_to_three_position(Rect(320, 180, 640, 360)) == pytest.approx((0, 0, 0))


def test_custom_invalid_space_is_rejected() -> None:
    with pytest.raises(SceneSpaceError):
        SceneSpace(logical_width=100, logical_height=100, safe_insets=(60, 10, 60, 10))

