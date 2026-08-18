"""3D Scene Functions for Video Flow V3 Manim Engine.

Uses Manim's ThreeDScene for assembly, cutaway, and spatial 3D representations.
Falls back to premium 2.5D if 3D rendering is not available.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from manim import (
    ThreeDScene, Scene, VGroup,
    # 3D objects
    Surface, Sphere, Cube, Cone, Cylinder, Torus,
    Line3D, Arrow3D, Dot3D,
    # 2D fallbacks
    Circle, Square, Rectangle, RoundedRectangle,
    Text, Arrow, Line, Dot,
    # Positioning
    UP, DOWN, LEFT, RIGHT, ORIGIN, OUT, IN,
    PI, TAU, DEGREES,
    np,
    # Animations
    Write, Create, FadeIn, FadeOut, GrowFromCenter, GrowArrow,
    Rotate, AnimationGroup, LaggedStart,
    # Colors
    WHITE, BLUE, GREEN, RED, YELLOW, GREY, ORANGE, TEAL,
    BLUE_A, BLUE_C, BLUE_D, BLUE_E,
    GREEN_C, GREEN_D,
    RED_C,
    GREY_A, GREY_C, GREY_D,
    # Config
    config,
)

from voice_flow.video_flow_v3.manim_engine.styles import ManimStyle

log = logging.getLogger(__name__)


def render_assembly_3d_scene(
    scene: ThreeDScene,
    objects: List[Dict[str, Any]],
    narration: str,
    teaching_goal: str,
    style: ManimStyle,
) -> None:
    """Render a 3D mechanical assembly with rotating parts."""
    scene.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)

    # Title (2D overlay)
    title = Text(
        teaching_goal[:40],
        font_size=28, color=style.text_color, weight="BOLD",
    ).to_corner(UP + LEFT, buff=0.3).scale(0.7)
    scene.add_fixed_in_frame_mobjects(title)
    scene.play(FadeIn(title), run_time=0.4)

    # Build 3D assembly from objects
    labels = [o.get("label", f"Part {i+1}") for i, o in enumerate(objects)]
    if not labels:
        labels = ["Core", "Shell", "Connector", "Module"]

    parts = []
    colors = [BLUE_C, GREEN_C, RED_C, YELLOW, ORANGE, TEAL]

    # Central core
    core = Sphere(radius=0.6, resolution=(20, 20))
    core.set_color(colors[0])
    core.set_opacity(0.7)
    parts.append(core)

    # Surrounding components
    n = min(len(labels) - 1, 5)
    for i in range(n):
        angle = i * TAU / max(n, 1)
        r = 1.8

        if i % 3 == 0:
            part = Cube(side_length=0.5)
        elif i % 3 == 1:
            part = Cylinder(radius=0.25, height=0.6, resolution=(15, 15))
        else:
            part = Cone(base_radius=0.3, height=0.5, resolution=(15, 15))

        part.set_color(colors[(i + 1) % len(colors)])
        part.set_opacity(0.8)
        part.move_to([r * math.cos(angle), r * math.sin(angle), 0.3 * (i % 3 - 1)])
        parts.append(part)

    # Animate assembly
    scene.play(GrowFromCenter(core), run_time=0.8)

    for part in parts[1:]:
        scene.play(FadeIn(part, shift=OUT * 0.3), run_time=0.4)

    # Slow rotation to show all angles
    assembly = VGroup(*parts)
    scene.play(Rotate(assembly, angle=PI / 2, axis=UP), run_time=2.0)

    # Add connecting lines
    for part in parts[1:]:
        line = Line3D(
            core.get_center(), part.get_center(),
            color=GREY_A,
        )
        scene.play(Create(line), run_time=0.2)

    scene.play(Rotate(assembly, angle=PI / 4, axis=RIGHT), run_time=1.5)
    scene.wait(style.scene_hold_time)


def render_cutaway_3d_scene(
    scene: ThreeDScene,
    objects: List[Dict[str, Any]],
    narration: str,
    teaching_goal: str,
    style: ManimStyle,
) -> None:
    """Render a 3D cutaway/cross-section view."""
    scene.set_camera_orientation(phi=65 * DEGREES, theta=-40 * DEGREES)

    title = Text(
        teaching_goal[:40],
        font_size=28, color=style.text_color, weight="BOLD",
    ).to_corner(UP + LEFT, buff=0.3).scale(0.7)
    scene.add_fixed_in_frame_mobjects(title)
    scene.play(FadeIn(title), run_time=0.4)

    # Outer shell (semi-transparent)
    outer = Sphere(radius=1.5, resolution=(24, 24))
    outer.set_color(BLUE_D)
    outer.set_opacity(0.2)

    # Inner core
    inner = Sphere(radius=0.7, resolution=(16, 16))
    inner.set_color(RED_C)
    inner.set_opacity(0.8)

    # Middle layer
    middle = Torus(major_radius=1.1, minor_radius=0.15, resolution=(16, 16))
    middle.set_color(GREEN_C)
    middle.set_opacity(0.6)

    scene.play(GrowFromCenter(outer), run_time=0.8)
    scene.play(FadeIn(middle), run_time=0.5)
    scene.play(GrowFromCenter(inner), run_time=0.6)

    # Rotate to show cutaway
    group = VGroup(outer, middle, inner)
    scene.play(Rotate(group, angle=PI / 3, axis=UP + RIGHT), run_time=2.0)

    # Labels
    labels = [o.get("label", "") for o in objects[:3]]
    if not labels or not labels[0]:
        labels = ["Outer Shell", "Middle Layer", "Inner Core"]

    label_objs = [outer, middle, inner]
    for i, (label, obj) in enumerate(zip(labels, label_objs)):
        if label:
            text = Text(label[:20], font_size=16, color=style.text_color)
            scene.add_fixed_in_frame_mobjects(text)
            text.move_to(RIGHT * 3 + UP * (1.5 - i * 1.2))
            arrow = Arrow(
                text.get_left(), text.get_left() + LEFT * 0.8,
                buff=0.1, color=style.muted_color, stroke_width=1.5,
            )
            scene.add_fixed_in_frame_mobjects(arrow)
            scene.play(FadeIn(text), GrowArrow(arrow), run_time=0.4)

    scene.wait(style.scene_hold_time)


def render_spatial_3d_scene(
    scene: ThreeDScene,
    objects: List[Dict[str, Any]],
    narration: str,
    teaching_goal: str,
    style: ManimStyle,
) -> None:
    """Render a spatial 3D system — orbital/spatial arrangement of elements."""
    scene.set_camera_orientation(phi=60 * DEGREES, theta=-50 * DEGREES)

    title = Text(
        teaching_goal[:40],
        font_size=28, color=style.text_color, weight="BOLD",
    ).to_corner(UP + LEFT, buff=0.3).scale(0.7)
    scene.add_fixed_in_frame_mobjects(title)
    scene.play(FadeIn(title), run_time=0.4)

    # Central body
    center = Sphere(radius=0.5, resolution=(16, 16))
    center.set_color(YELLOW)
    center.set_opacity(0.9)
    scene.play(GrowFromCenter(center), run_time=0.6)

    # Orbital elements
    labels = [o.get("label", f"Node {i+1}") for i, o in enumerate(objects)]
    if not labels:
        labels = ["Alpha", "Beta", "Gamma", "Delta"]

    n = min(len(labels), 6)
    colors = [BLUE_C, GREEN_C, RED_C, ORANGE, TEAL, GREY_A]

    for i in range(n):
        angle = i * TAU / n
        r = 2.0 + 0.3 * (i % 2)
        z = 0.5 * math.sin(angle * 2)

        satellite = Sphere(radius=0.2, resolution=(12, 12))
        satellite.set_color(colors[i % len(colors)])
        satellite.set_opacity(0.8)
        satellite.move_to([r * math.cos(angle), r * math.sin(angle), z])

        orbit = Circle(radius=r, color=GREY_D, stroke_width=0.5, stroke_opacity=0.3)
        orbit.rotate(PI / 2, axis=RIGHT)

        line = Line3D(
            center.get_center(), satellite.get_center(),
            color=GREY_C,
        )

        scene.play(
            Create(orbit),
            GrowFromCenter(satellite),
            Create(line),
            run_time=0.5,
        )

    # Gentle rotation
    all_objects = VGroup(*scene.mobjects)
    scene.play(Rotate(all_objects, angle=PI / 3, axis=UP), run_time=2.5)
    scene.wait(style.scene_hold_time)


# Dispatcher for 3D types
SCENE_3D_RENDERERS = {
    "ASSEMBLY_3D": render_assembly_3d_scene,
    "CUTAWAY_3D": render_cutaway_3d_scene,
}


def get_3d_renderer(representation_type: str):
    """Get the 3D render function for a representation type, or None."""
    return SCENE_3D_RENDERERS.get(representation_type, None)


def is_3d_type(representation_type: str) -> bool:
    """Check if this representation type requires 3D rendering."""
    return representation_type in SCENE_3D_RENDERERS
