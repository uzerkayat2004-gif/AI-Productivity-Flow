"""Material creative fingerprints and cross-video diversity review.

Plan hashes are useful for cache keys, but they are a poor proxy for whether
two videos look or explain differently.  This module extracts visible and
structural dimensions from treatments, scene programs, and preview metadata.
Labels, exact coordinates, and object IDs are intentionally ignored in the
structural projection so renaming a node or nudging it by a few pixels cannot
evade the history gate.

No image/ML dependency is required.  When a renderer supplies pixel samples,
keyframe features, or perceptual embeddings they are folded in as additional
signals; they never replace the topology and motion comparison.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Iterator

from .director import ArtifactMap, _artifact, _digest, _list, _mapping, _pick, _safe_float, _text


def _camel(name: str) -> str:
    bits = name.split("_")
    return bits[0] + "".join(bit.title() for bit in bits[1:])


def _tokens(value: Any, *, remove_values: bool = False) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        tokens: list[str] = []
        for key, item in value.items():
            key_text = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(key)).lower()
            if key_text in {"id", "key", "label", "text", "title", "name", "content", "x", "y", "left", "top", "right", "bottom", "width", "height", "transform", "position"}:
                if remove_values or key_text in {"id", "key", "label", "text", "title", "name", "content"}:
                    continue
            tokens.extend(_tokens(item, remove_values=remove_values))
            if key_text not in {"id", "key", "label", "text", "title", "name", "content"}:
                tokens.append(key_text)
        return tokens
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_tokens(item, remove_values=remove_values))
        return result
    if isinstance(value, (int, float)):
        return [] if remove_values else [str(value)]
    text = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(value)).lower()
    return re.findall(r"[a-z][a-z0-9_-]{1,}", text)


def _normalise_vocab(value: Any, *, limit: int = 32) -> tuple[str, ...]:
    stop = {"true", "false", "none", "scene", "element", "object", "value", "item"}
    return tuple(sorted({token for token in _tokens(value, remove_values=True) if token not in stop})[:limit])


def _freeze(value: Any, *, drop_keys: set[str] | None = None) -> Any:
    """Stable, JSON-friendly representation used by the fingerprint."""

    drop = {key.lower() for key in (drop_keys or set())}
    if isinstance(value, Mapping):
        pairs: list[tuple[str, Any]] = []
        for key, item in value.items():
            normalized = str(key)
            if normalized.lower() in drop:
                continue
            pairs.append((normalized, _freeze(item, drop_keys=drop)))
        return tuple(sorted(pairs))
    if isinstance(value, (list, tuple, set)):
        return tuple(_freeze(item, drop_keys=drop) for item in value)
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else 0.0
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return _text(value)


def _unfreeze(value: Any) -> Any:
    if isinstance(value, tuple):
        # Pairs from a mapping are represented as two-item tuples whose first
        # member is a string.  This heuristic preserves ordinary list tuples.
        if value and all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {item[0]: _unfreeze(item[1]) for item in value}
        return [_unfreeze(item) for item in value]
    return value


def _hex_rgb(value: Any) -> tuple[int, int, int] | None:
    text = _text(value).strip().lower()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6 or not re.fullmatch(r"[0-9a-f]{6}", text):
        return None
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _colour_bucket(rgb: tuple[int, int, int]) -> str:
    return "r{}g{}b{}".format(*(component // 32 for component in rgb))


def _colour_histogram(value: Any) -> tuple[tuple[str, float], ...]:
    """Coarsen colors into a normalized material palette histogram."""

    counts: Counter[str] = Counter()
    total = 0.0

    def add(color: Any, weight: float = 1.0) -> None:
        nonlocal total
        rgb = _hex_rgb(color)
        if rgb is None and isinstance(color, (list, tuple)) and len(color) >= 3:
            try:
                rgb = tuple(max(0, min(255, int(float(component)))) for component in color[:3])  # type: ignore[assignment]
            except (TypeError, ValueError):
                rgb = None
        if rgb is None:
            return
        amount = max(0.0, _safe_float(weight, 1.0))
        counts[_colour_bucket(rgb)] += amount
        total += amount

    if isinstance(value, Mapping):
        for color, weight in value.items():
            if _hex_rgb(weight) is not None or (isinstance(weight, (list, tuple)) and len(weight) >= 3):
                add(weight)
            elif isinstance(weight, Mapping):
                add(color, _pick(weight, "weight", "count", "value", default=1.0))
                for nested in weight.values():
                    if isinstance(nested, (Mapping, list, tuple, set)):
                        for nested_color in _list(nested):
                            add(nested_color)
                    else:
                        add(nested)
            else:
                add(color, weight)
    elif hasattr(value, "getdata") and callable(getattr(value, "getdata")):
        try:
            pixels = list(value.getdata())
            for pixel in pixels[:250_000]:
                add(pixel)
        except Exception:
            pass
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, Mapping):
                color = _pick(item, "color", "hex", "rgb", "value", default=None)
                add(color, _pick(item, "weight", "count", default=1.0))
            else:
                add(item)
    else:
        add(value)
    if total <= 0:
        return ()
    return tuple(sorted(((key, round(amount / total, 4)) for key, amount in counts.items()), key=lambda pair: (-pair[1], pair[0])))


def _distribution(value: Any, *, bins: int = 8) -> tuple[float, ...]:
    if isinstance(value, Mapping):
        values = []
        for key, item in value.items():
            number = _safe_float(item, math.nan)
            if math.isfinite(number):
                values.append(number)
            else:
                rgb = _hex_rgb(key)
                if rgb:
                    values.append(sum(rgb) / (3 * 255))
    elif isinstance(value, (list, tuple, set)):
        values = [_safe_float(item, math.nan) for item in value]
        values = [item for item in values if math.isfinite(item)]
    else:
        number = _safe_float(value, math.nan)
        values = [number] if math.isfinite(number) else []
    if not values:
        return ()
    histogram = [0.0] * bins
    for number in values:
        number = max(0.0, min(1.0, number if number <= 1 else number / 255.0))
        index = min(bins - 1, int(number * bins))
        histogram[index] += 1.0
    total = sum(histogram)
    return tuple(round(item / total, 4) for item in histogram)


def _hist_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    if not first or not second:
        return 0.5 if first == second else 0.0
    size = max(len(first), len(second))
    left = list(first) + [0.0] * (size - len(first))
    right = list(second) + [0.0] * (size - len(second))
    return max(0.0, min(1.0, 1.0 - 0.5 * sum(abs(a - b) for a, b in zip(left, right))))


def _vocab_similarity(first: Sequence[str], second: Sequence[str]) -> float:
    left, right = set(first), set(second)
    if not left or not right:
        return 0.5 if left == right else 0.0
    return len(left & right) / max(1, len(left | right))


def _value_similarity(first: Any, second: Any) -> float:
    if first in (None, "", (), [], {}) and second in (None, "", (), [], {}):
        return 1.0
    if first in (None, "", (), [], {}) or second in (None, "", (), [], {}):
        return 0.0
    if isinstance(first, (int, float)) and isinstance(second, (int, float)):
        scale = max(abs(float(first)), abs(float(second)), 1.0)
        return max(0.0, 1.0 - abs(float(first) - float(second)) / scale)
    if isinstance(first, Mapping) and isinstance(second, Mapping):
        keys = set(first) | set(second)
        if not keys:
            return 1.0
        return sum(_value_similarity(first.get(key), second.get(key)) for key in keys) / len(keys)
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)) and isinstance(second, Sequence) and not isinstance(second, (str, bytes)):
        if all(isinstance(item, (int, float)) for item in [*first, *second]):
            return _hist_similarity([float(item) for item in first], [float(item) for item in second])
        return _vocab_similarity([_text(item) for item in first], [_text(item) for item in second])
    return 1.0 if str(first).lower() == str(second).lower() else 0.0


def _coarse_region(value: Any) -> str | None:
    data = _mapping(value)
    x = _safe_float(_pick(data, "x", "left", default=math.nan), math.nan)
    y = _safe_float(_pick(data, "y", "top", default=math.nan), math.nan)
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    horizontal = "left" if x < 0.34 else "right" if x > 0.66 else "center"
    vertical = "top" if y < 0.34 else "bottom" if y > 0.66 else "middle"
    return f"{vertical}-{horizontal}"


def structural_scene_fingerprint(scene: Any) -> ArtifactMap:
    """Return topology/relationship features independent of labels and pixels."""

    data = _mapping(scene)
    raw_elements = _pick(data, "elements", "nodes", "objects", "layers", "visual_elements", default=[])
    raw_edges = _pick(data, "edges", "links", "connections", "relationships", default=[])
    elements = _list(raw_elements)
    edges = _list(raw_edges)
    root = _mapping(_pick(data, "root", default={}))
    hierarchy_edges: list[ArtifactMap] = []
    if root:
        elements = []
        def visit(node: Mapping[str, Any], depth: int = 0, parent_id: str = "") -> None:
            item = ArtifactMap(_artifact(node))
            item["depth"] = depth
            elements.append(item)
            node_id = _text(_pick(item, "id", default=f"node-{len(elements)}"))
            if parent_id:
                hierarchy_edges.append(ArtifactMap({"from": parent_id, "to": node_id, "relation": "contains"}))
            for child in _list(_pick(item, "children", default=[])):
                child_map = _mapping(child)
                if child_map:
                    visit(child_map, depth + 1, node_id)
        visit(root)
        for element in elements:
            payload = _mapping(_pick(element, "network", default={}))
            edges.extend(_list(_pick(payload, "edges", default=[])))
        edges.extend(hierarchy_edges)
    roles: Counter[str] = Counter()
    regions: Counter[str] = Counter()
    depths: Counter[int] = Counter()
    text_blocks = 0
    anchors = 0
    for element in elements:
        item = _mapping(element)
        role = _text(_pick(item, "role", "kind", "type", "semantic_role", "semanticRole", default="visual"))
        role = re.sub(r"[^a-z0-9_-]+", "-", role.lower()).strip("-") or "visual"
        roles[role] += 1
        region = _coarse_region(item)
        if region:
            regions[region] += 1
        depth = int(_safe_float(_pick(item, "depth", "z", "layer", default=0), 0))
        depths[max(-4, min(4, depth))] += 1
        if _pick(item, "text", "label", "content", "copy", default=None) not in (None, ""):
            text_blocks += 1
        if _contains_any(item, "anchor", "semantic_anchor", "semanticAnchor", "referent"):
            anchors += 1
    relations: Counter[str] = Counter()
    degree: Counter[int] = Counter()
    for edge in edges:
        item = _mapping(edge)
        relation = _text(_pick(item, "relation", "kind", "type", "verb", "relationship", default="connect"))
        relation = re.sub(r"[^a-z0-9_-]+", "-", relation.lower()).strip("-") or "connect"
        relations[relation] += 1
        source = _text(_pick(item, "source", "from", "source_id", "sourceId", default=""))
        target = _text(_pick(item, "target", "to", "target_id", "targetId", default=""))
        if source:
            degree[int(_digest(source, 4), 16) % 17] += 1
        if target:
            degree[int(_digest(target, 4), 16) % 17] += 1
    composition = _pick(data, "composition_intent", "composition", "spatial_intent", default={})
    composition_tokens = _normalise_vocab(composition)
    motion = _pick(data, "motion_events", "motion", "actions", default=[])
    motion_tokens = _normalise_vocab(motion)
    representation = _text(_pick(data, "representation", "chosen_representation", "media_type", default=""))
    # A scene brief has no explicit nodes yet.  Its semantic anchors still
    # provide a meaningful graph projection for pre-render diversity checks.
    if not elements:
        visible = _list(_pick(data, "visible_entities", "entities", "visual_entities", default=[]))
        roles.update({"hero": 1} if visible else {})
        roles.update({"support": max(0, len(visible) - 1)})
        relation_values = _list(_pick(data, "visible_relationships", "relationships", default=[]))
        relations.update({re.sub(r"[^a-z0-9_-]+", "-", _text(value).lower()).strip("-")[:40] or "relationship": 1 for value in relation_values})
        anchors = len(_list(_pick(data, "visual_anchors", "anchors", default=[])))
    return ArtifactMap(
        {
            "node_roles": tuple(sorted(roles.items())),
            "relation_types": tuple(sorted(relations.items())),
            "degree_profile": tuple(sorted(degree.values())),
            "depth_profile": tuple(sorted(depths.items())),
            "coarse_regions": tuple(sorted(regions.items())),
            "text_block_count": text_blocks,
            "semantic_anchor_count": anchors,
            "composition_vocabulary": composition_tokens,
            "motion_vocabulary": motion_tokens,
            "representation": representation.lower(),
            "element_count": len(elements),
            "edge_count": len(edges),
        }
    )


def _contains_any(value: Any, *needles: str) -> bool:
    data = _mapping(value)
    normalized = {re.sub(r"([a-z])([A-Z])", r"\1_\2", str(key)).lower() for key in data}
    return any(needle.lower() in normalized for needle in needles)


def _rendered_features(rendered: Any) -> ArtifactMap:
    data = _mapping(rendered)
    frames = _list(_pick(data, "frames", "keyframes", "preview_frames", "previewFrames", default=[]))
    visible = _list(_pick(data, "visible_elements", "elements", "objects", default=[]))
    text_blocks = _list(_pick(data, "text_blocks", "textBlocks", "labels", "visible_text", default=[]))
    regions = Counter()
    for item in visible:
        region = _coarse_region(item)
        if region:
            regions[region] += 1
    area = _safe_float(_pick(data, "occupied_area", "area_coverage", "areaCoverage", default=math.nan), math.nan)
    if not math.isfinite(area):
        area = min(1.0, len(visible) / 24.0) if visible else 0.0
    keyframe_features = _pick(data, "visual_embeddings", "embeddings", "perceptual_features", "rendered_features", default=[])
    if isinstance(keyframe_features, Mapping):
        keyframe_features = list(keyframe_features.values())
    flat_features: list[float] = []
    for feature in _list(keyframe_features):
        if isinstance(feature, Sequence) and not isinstance(feature, (str, bytes)):
            flat_features.extend(_safe_float(value, 0.0) for value in feature[:128])
        else:
            flat_features.append(_safe_float(feature, 0.0))
    return ArtifactMap(
        {
            "frame_count": len(frames),
            "visible_element_count": len(visible),
            "text_block_count": len(text_blocks),
            "occupied_area": round(max(0.0, min(1.0, area)), 4),
            "occupied_regions": tuple(sorted(regions.items())),
            "edge_density": round(_safe_float(_pick(data, "edge_density", "edgeDensity", default=0.0), 0.0), 4),
            "contrast_distribution": _distribution(_pick(data, "contrast_distribution", "contrastDistribution", "contrast", default=[])),
            "luminance_distribution": _distribution(_pick(data, "luminance_distribution", "luminanceDistribution", "luminance", default=[])),
            "perceptual_features": tuple(round(value, 5) for value in flat_features[:128]),
            "motion_energy": round(_safe_float(_pick(data, "motion_energy", "motionEnergy", default=0.0), 0.0), 4),
        }
    )


@dataclass(frozen=True)
class CreativeFingerprint(Mapping[str, Any]):
    """Material dimensions used for diversity review.

    The class implements ``Mapping`` and exposes both attributes and
    ``fingerprint["layout_graph"]`` access, making it straightforward to map
    into whichever canonical contract the engine adopts.
    """

    palette_histogram: tuple[tuple[str, float], ...] = ()
    luminance_distribution: tuple[float, ...] = ()
    background_treatment: str = ""
    semantic_color_roles: tuple[str, ...] = ()
    typography_category: str = ""
    typography_hierarchy: tuple[str, ...] = ()
    text_density: float = 0.0
    shape_material_vocabulary: tuple[str, ...] = ()
    illustration_style: str = ""
    layout_graph: tuple[Any, ...] = ()
    metaphor_families: tuple[str, ...] = ()
    motion_verbs: tuple[str, ...] = ()
    easing_distribution: tuple[str, ...] = ()
    simultaneity: float = 0.0
    camera_grammar: str = ""
    transition_language: tuple[str, ...] = ()
    rhythm: tuple[str, ...] = ()
    media_balance: tuple[tuple[str, float], ...] = ()
    rendered_features: tuple[Any, ...] = ()
    scene_fingerprints: tuple[Any, ...] = ()
    plan_digest: str = ""
    extras: tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    DIMENSIONS = (
        "palette_histogram", "luminance_distribution", "background_treatment", "semantic_color_roles",
        "typography_category", "typography_hierarchy", "text_density", "shape_material_vocabulary",
        "illustration_style", "layout_graph", "metaphor_families", "motion_verbs", "easing_distribution",
        "simultaneity", "camera_grammar", "transition_language", "rhythm", "media_balance",
        "rendered_features", "scene_fingerprints",
    )
    # Structure and rendered evidence are intentionally heavier than a plan
    # digest.  A digest is retained for diagnostics/cache correlation only.
    WEIGHTS = {
        "palette_histogram": 0.06,
        "luminance_distribution": 0.04,
        "background_treatment": 0.06,
        "semantic_color_roles": 0.04,
        "typography_category": 0.04,
        "typography_hierarchy": 0.03,
        "text_density": 0.04,
        "shape_material_vocabulary": 0.08,
        "illustration_style": 0.07,
        "layout_graph": 0.16,
        "metaphor_families": 0.09,
        "motion_verbs": 0.07,
        "easing_distribution": 0.03,
        "simultaneity": 0.03,
        "camera_grammar": 0.04,
        "transition_language": 0.04,
        "rhythm": 0.03,
        "media_balance": 0.04,
        "rendered_features": 0.08,
        "scene_fingerprints": 0.09,
    }

    def __getitem__(self, key: str) -> Any:
        if key in self.DIMENSIONS or key in {"plan_digest", "signature", "extras"}:
            if key == "signature":
                return self.signature
            return getattr(self, key)
        aliases = {name: name for name in self.DIMENSIONS}
        aliases.update({_camel(name): name for name in self.DIMENSIONS})
        if key in aliases:
            return getattr(self, aliases[key])
        for extra_key, value in self.extras:
            if extra_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter((*self.DIMENSIONS, "plan_digest", "signature"))

    def __len__(self) -> int:
        return len(self.DIMENSIONS) + 2

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    @property
    def signature(self) -> str:
        return _digest(self.to_mapping(include_signature=False), 24)

    @property
    def structural_signature(self) -> str:
        return _digest({"layout_graph": self.layout_graph, "scene_fingerprints": self.scene_fingerprints, "motion_verbs": self.motion_verbs}, 24)

    def to_mapping(self, *, include_signature: bool = True, aliases: bool = False) -> ArtifactMap:
        result = ArtifactMap({name: _artifact(getattr(self, name)) for name in self.DIMENSIONS})
        result["plan_digest"] = self.plan_digest
        if self.extras:
            result["extras"] = ArtifactMap({key: _artifact(value) for key, value in self.extras})
        if aliases:
            for name in self.DIMENSIONS:
                result[_camel(name)] = result[name]
        if include_signature:
            result["signature"] = self.signature
            result["structural_signature"] = self.structural_signature
        return result

    @classmethod
    def from_mapping(cls, value: Any) -> "CreativeFingerprint":
        if isinstance(value, cls):
            return value
        data = _mapping(value)
        kwargs: dict[str, Any] = {}
        for name in cls.DIMENSIONS:
            raw = _pick(data, name, _camel(name), default=None)
            if name in {"palette_histogram", "media_balance"}:
                if isinstance(raw, Mapping):
                    raw = tuple((str(key), _safe_float(item, 0.0)) for key, item in raw.items())
                else:
                    raw = tuple((str(_pick(_mapping(item), "color", "key", "name", default=item)), _safe_float(_pick(_mapping(item), "weight", "value", default=1.0), 1.0)) if isinstance(item, Mapping) else (str(item), 1.0) for item in _list(raw))
            elif name in {"luminance_distribution", "rendered_features"}:
                raw = tuple(_freeze(item) if not isinstance(item, (int, float)) else round(float(item), 5) for item in _list(raw))
            elif name in {"text_density", "simultaneity"}:
                raw = _safe_float(raw, 0.0)
            elif name == "layout_graph" or name == "scene_fingerprints":
                raw = tuple(_freeze(item, drop_keys={"id", "label", "text", "title", "name", "x", "y", "left", "top", "width", "height", "coordinates"}) for item in _list(raw))
            elif name in {"background_treatment", "typography_category", "illustration_style", "camera_grammar"}:
                raw = _text(raw)
            else:
                raw = _normalise_vocab(raw) if name not in {"easing_distribution", "transition_language", "rhythm", "typography_hierarchy", "shape_material_vocabulary", "metaphor_families", "motion_verbs", "semantic_color_roles"} else tuple(sorted({_text(item).lower() for item in _list(raw) if _text(item)}))
            kwargs[name] = raw or (() if name not in {"text_density", "simultaneity", "background_treatment", "typography_category", "illustration_style", "camera_grammar"} else (0.0 if name in {"text_density", "simultaneity"} else ""))
        extras = _pick(data, "extras", default={})
        kwargs["plan_digest"] = _text(_pick(data, "plan_digest", "planDigest", "hash", default=""))
        kwargs["extras"] = tuple((str(key), _freeze(item)) for key, item in _mapping(extras).items())
        return cls(**kwargs)

    @classmethod
    def from_treatment(cls, treatment: Any, *, scenes: Sequence[Any] | None = None, rendered: Any = None) -> "CreativeFingerprint":
        data = _mapping(treatment)
        scene_values = list(scenes or _list(_pick(data, "scenes", "scene_briefs", "sceneBriefs", default=[])))
        palette = _pick(data, "palette_roles", "palette", "colors", "colour_roles", default={})
        semantic_roles = _pick(_mapping(palette), "semantic_roles", "semanticRoles", "roles", default={})
        type_data = _mapping(_pick(data, "typography", "type_system", "typeSystem", default={}))
        media = _pick(data, "media_balance", "mediaBalance", default={})
        rendered_data = _rendered_features(rendered) if rendered is not None else ArtifactMap()
        structural = [structural_scene_fingerprint(scene) for scene in scene_values]
        motion_values = _pick(data, "motion_personality", "motion_verbs", "motion", default="")
        transitions = _pick(data, "transition_logic", "transitions", "transition_language", default="")
        shape = _pick(data, "material_language", "shape_material_vocabulary", "shapeLanguage", default="")
        illustration = _pick(data, "illustration_strategy", "illustration_style", "modeling_strategy", default="")
        layout = tuple(
            _freeze({key: value for key, value in _mapping(item).items() if key not in {"coarse_regions", "coarseRegions"}}, drop_keys={"id", "label", "text", "title", "name", "x", "y", "coordinates"})
            for item in structural
        )
        text_density = _safe_float(_pick(data, "text_density", "average_density", "averageDensity", default=0.0), 0.0)
        if not text_density and scene_values:
            counts = []
            for scene in scene_values:
                scene_data = _mapping(scene)
                visible = _text(_pick(scene_data, "visible_text", "text", "labels", default=""))
                counts.append(len(re.findall(r"\w+", visible)))
            text_density = sum(counts) / max(1, len(counts))
        fingerprint = cls(
            palette_histogram=_colour_histogram(palette),
            luminance_distribution=_distribution(_pick(data, "luminance_distribution", "luminance", default=[])),
            background_treatment=_text(_pick(data, "background_treatment", "background", "surface", default=_pick(_mapping(palette), "background", default=""))),
            semantic_color_roles=_normalise_vocab(semantic_roles),
            typography_category=_text(_pick(type_data, "category", "font_category", "fontCategory", default=_pick(data, "typography_category", default=""))),
            typography_hierarchy=tuple(sorted({_text(item).lower() for item in _list(_pick(type_data, "hierarchy", "levels", default=[])) if _text(item)})),
            text_density=round(text_density, 4),
            shape_material_vocabulary=_normalise_vocab(shape),
            illustration_style=_text(illustration),
            layout_graph=layout,
            metaphor_families=tuple(sorted({_text(_pick(_mapping(scene), "metaphor", "metaphor_family", "visual_metaphor", default="")).lower() for scene in scene_values if _text(_pick(_mapping(scene), "metaphor", "metaphor_family", "visual_metaphor", default=""))})),
            motion_verbs=tuple(sorted(set(_normalise_vocab(motion_values)))),
            easing_distribution=tuple(sorted({_text(item).lower() for item in _list(_pick(data, "easing_distribution", "easing", default=[])) if _text(item)})),
            simultaneity=round(_safe_float(_pick(data, "simultaneity", "simultaneous_events", "simultaneousEvents", default=0.0), 0.0), 4),
            camera_grammar=_text(_pick(data, "camera_grammar", "camera", default="")),
            transition_language=tuple(sorted(set(_normalise_vocab(transitions)))),
            rhythm=tuple(sorted({_text(item).lower() for item in _list(_pick(data, "rhythm", "rhythm_profile", "rhythmProfile", default=[])) if _text(item)})),
            media_balance=tuple((str(key), _safe_float(item, 0.0)) for key, item in _mapping(media).items()),
            rendered_features=tuple(_freeze(item) for item in rendered_data.get("perceptual_features", ())) + (_freeze(rendered_data.get("occupied_regions", ())),),
            scene_fingerprints=tuple(layout),
            plan_digest=_text(_pick(data, "fingerprint", "plan_digest", "planDigest", "signature", default="")),
        )
        return fingerprint

    @classmethod
    def from_scene(cls, scene: Any, *, treatment: Any = None, rendered: Any = None) -> "CreativeFingerprint":
        scene_data = _mapping(scene)
        treatment_data = _mapping(treatment)
        merged = ArtifactMap(treatment_data)
        merged["scenes"] = [scene_data]
        if not treatment_data:
            merged.update(scene_data)
        return cls.from_treatment(merged, scenes=[scene_data], rendered=rendered)

    @classmethod
    def from_rendered(cls, rendered: Any, *, treatment: Any = None, scenes: Sequence[Any] | None = None) -> "CreativeFingerprint":
        fingerprint = cls.from_treatment(treatment or {}, scenes=scenes, rendered=rendered)
        rendered_data = _rendered_features(rendered)
        palette = _colour_histogram(_pick(_mapping(rendered), "palette_histogram", "palette", "colors", default=[]))
        luminance = _distribution(_pick(_mapping(rendered), "luminance_distribution", "luminance", default=[]))
        return cls(
            **{field_name: getattr(fingerprint, field_name) for field_name in cls.DIMENSIONS if field_name not in {"palette_histogram", "luminance_distribution", "rendered_features"}},
            palette_histogram=palette or fingerprint.palette_histogram,
            luminance_distribution=luminance or fingerprint.luminance_distribution,
            rendered_features=tuple(_freeze(value) for value in rendered_data.values()),
            plan_digest=fingerprint.plan_digest,
            extras=fingerprint.extras,
        )

    @classmethod
    def from_artifacts(cls, artifacts: Any, *, rendered: Any = None) -> "CreativeFingerprint":
        data = _mapping(artifacts)
        treatment = _pick(data, "treatment", "creative_treatment", "creativeTreatment", default=data)
        scenes = _list(_pick(data, "scenes", "scene_briefs", "sceneBriefs", default=_pick(_mapping(_pick(data, "storyboard", "semantic_storyboard", default={})), "scenes", default=[])))
        return cls.from_treatment(treatment, scenes=scenes, rendered=rendered)

    @classmethod
    def build(cls, value: Any, *, rendered: Any = None) -> "CreativeFingerprint":
        data = _mapping(value)
        if any(key in data for key in ("palette_histogram", "layout_graph", "structural_signature")):
            return cls.from_mapping(data)
        return cls.from_artifacts(value, rendered=rendered)

    def dimension_similarities(self, other: Any) -> ArtifactMap:
        candidate = CreativeFingerprint.build(other)
        return ArtifactMap({name: round(_value_similarity(getattr(self, name), getattr(candidate, name)), 4) for name in self.DIMENSIONS})

    def similarity(self, other: Any) -> float:
        candidate = CreativeFingerprint.build(other)
        parts = self.dimension_similarities(candidate)
        weights = self.WEIGHTS
        total_weight = sum(weights.values()) or 1.0
        return round(sum(weights[name] * parts[name] for name in self.DIMENSIONS) / total_weight, 4)

    def compare(self, other: Any, *, threshold: float = 0.72) -> ArtifactMap:
        candidate = CreativeFingerprint.build(other)
        dimensions = self.dimension_similarities(candidate)
        repeated = [
            name for name, score in dimensions.items()
            if score >= (0.68 if name in {"layout_graph", "scene_fingerprints", "metaphor_families"} else 0.82)
        ]
        structural = round(
            sum(self.WEIGHTS[name] * dimensions[name] for name in ("layout_graph", "scene_fingerprints", "shape_material_vocabulary", "motion_verbs", "metaphor_families"))
            / sum(self.WEIGHTS[name] for name in ("layout_graph", "scene_fingerprints", "shape_material_vocabulary", "motion_verbs", "metaphor_families")),
            4,
        )
        rendered = round(
            sum(self.WEIGHTS[name] * dimensions[name] for name in ("palette_histogram", "luminance_distribution", "rendered_features", "background_treatment"))
            / sum(self.WEIGHTS[name] for name in ("palette_histogram", "luminance_distribution", "rendered_features", "background_treatment")),
            4,
        )
        score = self.similarity(candidate)
        # A high structural match is material repetition even when the palette
        # was substituted.  This rule is the key distinction from hash-only
        # diversity checks.
        accepted = not (score >= threshold or structural >= 0.78)
        reasons: list[str] = []
        if score >= threshold:
            reasons.append(f"material similarity {score:.2f} crosses {threshold:.2f}")
        if structural >= 0.78:
            reasons.append(f"structural similarity {structural:.2f} repeats visible construction")
        if rendered >= 0.84 and structural >= 0.62:
            reasons.append("rendered evidence and structural topology agree")
        return ArtifactMap(
            {
                "similarity": score,
                "material_similarity": score,
                "structural_similarity": structural,
                "rendered_similarity": rendered,
                "repeated_dimensions": repeated,
                "accepted": accepted,
                "reasons": reasons,
                "candidate_signature": candidate.signature,
                "reference_signature": self.signature,
            }
        )


@dataclass
class DiversityLedger:
    """Compare candidate fingerprints against a bounded completed-video history."""

    history: list[Any] = field(default_factory=list)
    window: int = 10
    threshold: float = 0.72

    def __post_init__(self) -> None:
        self.history = list(self.history or [])[-max(1, int(self.window)) :]

    @property
    def recent(self) -> list[CreativeFingerprint]:
        return [CreativeFingerprint.build(item) for item in self.history]

    def compare(self, candidate: Any, history: Iterable[Any] | None = None) -> ArtifactMap:
        fingerprint = CreativeFingerprint.build(candidate)
        references = [CreativeFingerprint.build(item) for item in (history if history is not None else self.history)][-self.window :]
        comparisons = [fingerprint.compare(reference, threshold=self.threshold) for reference in references]
        best_index = max(range(len(comparisons)), key=lambda index: comparisons[index]["similarity"], default=-1)
        best = comparisons[best_index] if best_index >= 0 else ArtifactMap({"similarity": 0.0, "accepted": True, "reasons": []})
        accepted = bool(best.get("accepted", True))
        if not references:
            accepted = True
        return ArtifactMap(
            {
                "accepted": accepted,
                "candidate": fingerprint,
                "similarity": best.get("similarity", 0.0),
                "material_similarity": best.get("material_similarity", 0.0),
                "structural_similarity": best.get("structural_similarity", 0.0),
                "rendered_similarity": best.get("rendered_similarity", 0.0),
                "repeated_dimensions": best.get("repeated_dimensions", []),
                "reasons": best.get("reasons", []),
                "reference_index": best_index,
                "comparisons": comparisons,
                "history_count": len(references),
            }
        )

    def review(self, candidate: Any, history: Iterable[Any] | None = None) -> ArtifactMap:
        return self.compare(candidate, history)

    def check(self, candidate: Any, history: Iterable[Any] | None = None) -> ArtifactMap:
        return self.compare(candidate, history)

    def is_repeat(self, candidate: Any, history: Iterable[Any] | None = None) -> bool:
        return not bool(self.compare(candidate, history)["accepted"])

    def accept(self, candidate: Any, *, force: bool = False) -> ArtifactMap:
        result = self.compare(candidate)
        if result["accepted"] or force:
            self.history.append(candidate)
            self.history = self.history[-max(1, int(self.window)) :]
            result["reserved"] = True
        else:
            result["reserved"] = False
        return result

    reserve = accept
    add = accept


def fingerprint(value: Any, *, rendered: Any = None) -> CreativeFingerprint:
    """Convenience factory used by scene/runtime adapters."""

    return CreativeFingerprint.build(value, rendered=rendered)


def compare_fingerprints(first: Any, second: Any, *, threshold: float = 0.72) -> ArtifactMap:
    return CreativeFingerprint.build(first).compare(second, threshold=threshold)


__all__ = [
    "CreativeFingerprint",
    "DiversityLedger",
    "compare_fingerprints",
    "fingerprint",
    "structural_scene_fingerprint",
]


