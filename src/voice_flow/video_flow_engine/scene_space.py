"""The renderer-owned coordinate contract for Video Flow V2.1.

The old V2 layout code emits 1920x1080 boxes while the Narova browser stage
is 1280x720.  V2.1 keeps one logical space at the boundary of the renderer
and only converts to pixels at the last possible moment.  This module is
deliberately small and dependency free so it can be shared by a compiler,
SVG preview, and a Three scene without importing any of those systems.

``SceneSpace`` uses the Narova logical stage (1280x720) as its canonical
coordinate system.  ``pixel_target`` is output metadata, not the coordinate
system used by scene programs.  Scene IR should normally store
``NormalizedRect`` values and use the conversion helpers when producing
markup or renderer metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


class SceneSpaceError(ValueError):
    """Raised when a scene-space value cannot be represented safely."""


class _CallableString(str):
    """A string that also supports the historical ``value()`` spelling.

    A few renderer call sites naturally treat ``svg_viewbox`` as a property,
    while others treat it as a helper.  Returning this tiny ``str`` subclass
    keeps both forms harmless and avoids duplicate coordinate constants.
    """

    def __call__(self) -> str:
        return str(self)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise SceneSpaceError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SceneSpaceError(f"{name} must be numeric") from exc
    if not isfinite(number):
        raise SceneSpaceError(f"{name} must be finite")
    return number


@dataclass(frozen=True, slots=True)
class Insets:
    """Logical safe-area insets, measured from each edge of the stage."""

    left: float = 48.0
    top: float = 32.0
    right: float = 48.0
    bottom: float = 32.0

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        names = ("left", "top", "right", "bottom")
        for name, value in zip(names, values):
            number = _number(value, f"safe_insets.{name}")
            if number < 0:
                raise SceneSpaceError(f"safe_insets.{name} cannot be negative")
            object.__setattr__(self, name, number)

    def to_dict(self) -> dict[str, float]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
        }

    def __iter__(self):
        yield self.left
        yield self.top
        yield self.right
        yield self.bottom


@dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned rectangle in a named SceneSpace coordinate system."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "width", "height"):
            value = _number(getattr(self, name), name)
            if name in {"width", "height"} and value < 0:
                raise SceneSpaceError(f"{name} cannot be negative")
            object.__setattr__(self, name, value)

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    def translated(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def inset(self, amount: float | Sequence[float]) -> "Rect":
        if isinstance(amount, Sequence) and not isinstance(amount, (str, bytes)):
            values = tuple(amount)
            if len(values) != 4:
                raise SceneSpaceError("rect inset sequences must contain four values")
            left, top, right, bottom = (_number(item, "inset") for item in values)
        else:
            left = top = right = bottom = _number(amount, "inset")
        result = Rect(
            self.x + left,
            self.y + top,
            self.width - left - right,
            self.height - top - bottom,
        )
        if result.width < 0 or result.height < 0:
            raise SceneSpaceError("inset is larger than the rectangle")
        return result


NormalizedRect = Rect
LogicalRect = Rect
PixelRect = Rect
SceneRect = Rect


def _coerce_rect(value: Any, name: str = "rect") -> Rect:
    if isinstance(value, Rect):
        return value
    if isinstance(value, Mapping):
        try:
            return Rect(value["x"], value["y"], value["width"], value["height"])
        except KeyError as exc:
            raise SceneSpaceError(f"{name} is missing {exc.args[0]!r}") from exc
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = tuple(value)
        if len(values) == 4:
            return Rect(*values)
    try:
        return Rect(value.x, value.y, value.width, value.height)
    except AttributeError as exc:
        raise SceneSpaceError(f"{name} must be a rectangle-like value") from exc


def _coerce_insets(value: Any) -> Insets:
    if isinstance(value, Insets):
        return value
    if isinstance(value, Mapping):
        return Insets(
            value.get("left", 0),
            value.get("top", 0),
            value.get("right", 0),
            value.get("bottom", 0),
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = tuple(value)
        if len(values) == 4:
            return Insets(*values)
    try:
        return Insets(value.left, value.top, value.right, value.bottom)
    except AttributeError as exc:
        raise SceneSpaceError("safe_insets must be an Insets-like value") from exc


class SceneSpace:
    """Canonical logical space shared by V2.1 composition and renderers.

    Parameters are intentionally explicit so tests and future portrait
    previews can use the same conversion code.  The defaults are the only
    production contract: 1280x720 logical, 16:9, and 1920x1080 output
    metadata.  A caption region is reserved from the bottom of the logical
    stage and is never part of ``content_rect``.
    """

    DEFAULT_LOGICAL_WIDTH = 1280
    DEFAULT_LOGICAL_HEIGHT = 720
    DEFAULT_PIXEL_TARGET = (1920, 1080)

    def __init__(
        self,
        logical_width: int | float = DEFAULT_LOGICAL_WIDTH,
        logical_height: int | float = DEFAULT_LOGICAL_HEIGHT,
        *,
        safe_insets: Insets | Mapping[str, Any] | Sequence[float] = Insets(),
        caption_region: Rect | Mapping[str, Any] | Sequence[float] | None = None,
        pixel_target: Sequence[int] = DEFAULT_PIXEL_TARGET,
        device_scale: float = 1.0,
    ) -> None:
        width = _number(logical_width, "logical_width")
        height = _number(logical_height, "logical_height")
        if width <= 0 or height <= 0:
            raise SceneSpaceError("logical dimensions must be positive")
        if isinstance(logical_width, bool) or isinstance(logical_height, bool):
            raise SceneSpaceError("logical dimensions must be numeric")
        if isinstance(pixel_target, Sequence) and len(tuple(pixel_target)) == 2:
            pixel_width = _number(tuple(pixel_target)[0], "pixel_target.width")
            pixel_height = _number(tuple(pixel_target)[1], "pixel_target.height")
        else:
            raise SceneSpaceError("pixel_target must contain width and height")
        if pixel_width <= 0 or pixel_height <= 0:
            raise SceneSpaceError("pixel_target dimensions must be positive")
        scale = _number(device_scale, "device_scale")
        if scale <= 0:
            raise SceneSpaceError("device_scale must be positive")

        insets = _coerce_insets(safe_insets)
        if insets.left + insets.right >= width or insets.top + insets.bottom >= height:
            raise SceneSpaceError("safe insets leave no usable stage")
        if caption_region is None:
            # A 120 logical-pixel caption rail maps to 180 output pixels at
            # the 1920x1080 target, close to the legacy rail while remaining
            # owned by this canonical space rather than the old solver.
            caption = Rect(0.0, height * (5.0 / 6.0), width, height / 6.0)
        else:
            caption = _coerce_rect(caption_region, "caption_region")
        if caption.x < 0 or caption.y < 0 or caption.right > width or caption.bottom > height:
            raise SceneSpaceError("caption_region must fit inside the logical stage")
        if caption.height <= 0:
            raise SceneSpaceError("caption_region must have positive height")
        if caption.y <= insets.top:
            raise SceneSpaceError("caption_region leaves no content area")

        self.logical_width = width
        self.logical_height = height
        self.safe_insets = insets
        self.caption_region = caption
        self.pixel_target = (int(round(pixel_width)), int(round(pixel_height)))
        self.device_scale = scale

    def __repr__(self) -> str:
        return (
            "SceneSpace("
            f"logical_width={self.logical_width:g}, logical_height={self.logical_height:g}, "
            f"pixel_target={self.pixel_target!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SceneSpace):
            return NotImplemented
        return (
            self.logical_width,
            self.logical_height,
            self.safe_insets,
            self.caption_region,
            self.pixel_target,
            self.device_scale,
        ) == (
            other.logical_width,
            other.logical_height,
            other.safe_insets,
            other.caption_region,
            other.pixel_target,
            other.device_scale,
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.logical_width,
                self.logical_height,
                self.safe_insets,
                self.caption_region,
                self.pixel_target,
                self.device_scale,
            )
        )

    @property
    def aspect_ratio(self) -> float:
        return self.logical_width / self.logical_height

    @property
    def pixel_width(self) -> int:
        return self.pixel_target[0]

    @property
    def pixel_height(self) -> int:
        return self.pixel_target[1]

    @property
    def pixel_aspect_ratio(self) -> float:
        return self.pixel_width / self.pixel_height

    @property
    def scale_x(self) -> float:
        return self.pixel_width / self.logical_width

    @property
    def scale_y(self) -> float:
        return self.pixel_height / self.logical_height

    @property
    def safe_rect(self) -> Rect:
        return Rect(
            self.safe_insets.left,
            self.safe_insets.top,
            self.logical_width - self.safe_insets.left - self.safe_insets.right,
            self.logical_height - self.safe_insets.top - self.safe_insets.bottom,
        )

    @property
    def content_rect(self) -> Rect:
        safe = self.safe_rect
        bottom = min(safe.bottom, self.caption_region.y)
        if bottom <= safe.y:
            raise SceneSpaceError("safe insets and caption region leave no content area")
        return Rect(safe.x, safe.y, safe.width, bottom - safe.y)

    @property
    def caption_safe_rect(self) -> Rect:
        """The largest rectangle guaranteed not to intersect captions."""

        return self.content_rect

    @property
    def content_region(self) -> Rect:
        return self.content_rect

    @property
    def caption_region_normalized(self) -> Rect:
        return self.normalize(self.caption_region)

    @property
    def safe_insets_normalized(self) -> Insets:
        return Insets(
            self.safe_insets.left / self.logical_width,
            self.safe_insets.top / self.logical_height,
            self.safe_insets.right / self.logical_width,
            self.safe_insets.bottom / self.logical_height,
        )

    @property
    def safe_rect_normalized(self) -> Rect:
        return self.normalize(self.safe_rect)

    @property
    def content_rect_normalized(self) -> Rect:
        return self.normalize(self.content_rect)

    @property
    def svg_viewbox(self) -> _CallableString:
        return _CallableString(f"0 0 {self.logical_width:g} {self.logical_height:g}")

    @property
    def svg_view_box(self) -> _CallableString:
        return self.svg_viewbox

    def svg_attributes(self) -> dict[str, str]:
        return {
            "viewBox": str(self.svg_viewbox),
            "width": str(self.logical_width),
            "height": str(self.logical_height),
            "preserveAspectRatio": "xMidYMid meet",
        }

    @property
    def three_aspect(self) -> float:
        """Aspect ratio to pass to a Three perspective camera."""

        return self.aspect_ratio

    @property
    def three_camera_aspect(self) -> float:
        return self.three_aspect

    def normalize(self, value: Any) -> Rect:
        """Convert a logical-space rectangle to normalized coordinates."""

        rect = _coerce_rect(value)
        return Rect(
            rect.x / self.logical_width,
            rect.y / self.logical_height,
            rect.width / self.logical_width,
            rect.height / self.logical_height,
        )

    def denormalize(self, value: Any) -> Rect:
        """Convert a normalized rectangle to canonical logical coordinates."""

        rect = _coerce_rect(value)
        return Rect(
            rect.x * self.logical_width,
            rect.y * self.logical_height,
            rect.width * self.logical_width,
            rect.height * self.logical_height,
        )

    def normalized_to_logical(self, value: Any) -> Rect:
        return self.denormalize(value)

    def logical_to_normalized(self, value: Any) -> Rect:
        return self.normalize(value)

    def logical_to_pixel(self, value: Any) -> Rect:
        rect = _coerce_rect(value)
        return Rect(rect.x * self.scale_x, rect.y * self.scale_y, rect.width * self.scale_x, rect.height * self.scale_y)

    def pixel_to_logical(self, value: Any) -> Rect:
        rect = _coerce_rect(value)
        return Rect(rect.x / self.scale_x, rect.y / self.scale_y, rect.width / self.scale_x, rect.height / self.scale_y)

    def normalized_to_pixel(self, value: Any) -> Rect:
        return self.logical_to_pixel(self.denormalize(value))

    def pixel_to_normalized(self, value: Any) -> Rect:
        return self.normalize(self.pixel_to_logical(value))

    def to_pixels(self, value: Any) -> Rect:
        """Alias for ``normalized_to_pixel`` used by compiler adapters."""

        return self.normalized_to_pixel(value)

    def from_pixels(self, value: Any) -> Rect:
        return self.pixel_to_normalized(value)

    def clamp(self, value: Any, *, region: str = "content") -> Rect:
        """Clamp a normalized rectangle into ``content`` or ``safe`` space."""

        rect = _coerce_rect(value)
        bounds = self.content_rect_normalized if region in {"content", "caption-safe", "caption_safe"} else self.safe_rect_normalized
        width = min(rect.width, bounds.width)
        height = min(rect.height, bounds.height)
        x = min(max(rect.x, bounds.x), bounds.right - width)
        y = min(max(rect.y, bounds.y), bounds.bottom - height)
        return Rect(x, y, width, height)

    def contains(self, value: Any, *, region: str = "content", epsilon: float = 1e-9) -> bool:
        rect = _coerce_rect(value)
        bounds = self.content_rect_normalized if region in {"content", "caption-safe", "caption_safe"} else self.safe_rect_normalized
        return (
            rect.x >= bounds.x - epsilon
            and rect.y >= bounds.y - epsilon
            and rect.right <= bounds.right + epsilon
            and rect.bottom <= bounds.bottom + epsilon
        )

    def is_caption_safe(self, value: Any, *, epsilon: float = 1e-9) -> bool:
        return self.contains(value, region="content", epsilon=epsilon)

    def three_position(self, value: Any, depth: float = 0.0, *, z: float | None = None) -> tuple[float, float, float]:
        """Map a normalized box center to a stable Three world position.

        X and Y span ``[-1, 1]`` and retain the browser's top-left origin
        convention (positive Three Y points upward).  ``depth``/``z`` is
        compiler-owned and is never read from untrusted scene data.
        """

        rect = _coerce_rect(value)
        world_z = depth if z is None else z
        return (
            (rect.center_x - 0.5) * 2.0,
            (0.5 - rect.center_y) * 2.0,
            _number(world_z, "depth"),
        )

    def normalized_to_three_position(self, value: Any, depth: float = 0.0) -> tuple[float, float, float]:
        return self.three_position(value, depth)

    def logical_to_three_position(self, value: Any, depth: float = 0.0) -> tuple[float, float, float]:
        return self.three_position(self.normalize(value), depth)

    def three_camera(self, *, position: Sequence[float] = (0.0, 0.0, 3.0), look_at: Sequence[float] = (0.0, 0.0, 0.0)) -> dict[str, Any]:
        """Return safe, renderer-neutral camera metadata for Three adapters."""

        if len(tuple(position)) != 3 or len(tuple(look_at)) != 3:
            raise SceneSpaceError("Three camera position and look_at must be 3-vectors")
        return {
            "aspect": self.three_aspect,
            "position": tuple(_number(item, "camera position") for item in position),
            "look_at": tuple(_number(item, "camera look_at") for item in look_at),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_width": self.logical_width,
            "logical_height": self.logical_height,
            "aspect_ratio": self.aspect_ratio,
            "safe_insets": self.safe_insets.to_dict(),
            "safe_rect": self.safe_rect.to_dict(),
            "content_rect": self.content_rect.to_dict(),
            "caption_region": self.caption_region.to_dict(),
            "pixel_target": {"width": self.pixel_width, "height": self.pixel_height},
            "device_scale": self.device_scale,
            "svg_viewBox": str(self.svg_viewbox),
            "three_aspect": self.three_aspect,
        }


DEFAULT_SCENE_SPACE = SceneSpace()


__all__ = [
    "DEFAULT_SCENE_SPACE",
    "Insets",
    "LogicalRect",
    "NormalizedRect",
    "PixelRect",
    "Rect",
    "SceneRect",
    "SceneSpace",
    "SceneSpaceError",
]
