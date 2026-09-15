"""Authoritative, data-only capability registry for Visual Engine V2.1.

The planner, parser, validator, and compiler must agree on one vocabulary.  A
capability is therefore registered with more than a name: it carries the
bounded input requirements, the trusted compiler binding, and the observable
QA obligation that makes the semantic operation real.  The registry contains
no executable model supplied code and is safe to expose as prompt context.

This module deliberately does not import the legacy V2 planner/compiler.  V2.0
is a production fallback and keeps its historical vocabulary intact.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping


class VisualCapabilityError(ValueError):
    """Raised when a capability is unknown or the registry is inconsistent."""


# These are intentionally compact.  They describe a communication intent,
# not a scene template.
CONTENT_INTENTS: tuple[str, ...] = (
    "EXPLAIN",
    "DEMONSTRATE",
    "VISUALIZE",
    "NARRATE",
    "ANALYZE",
    "COMPARE",
    "TEACH",
)

REPRESENTATION_STRATEGIES: tuple[str, ...] = (
    "DIRECT_DEPICTION",
    "STATE_EVOLUTION",
    "MECHANISM",
    "SPATIAL",
    "DATA",
    "MATHEMATICAL",
    "GEOGRAPHIC",
    "CHRONOLOGICAL",
    "CONCEPTUAL",
    "MIXED",
)

STRUCTURAL_FAMILIES: tuple[str, ...] = (
    "organic_branching",
    "organic_body",
    "fluid_system",
    "mechanical_linkage",
    "rigid_assembly",
    "architecture",
    "terrain",
    "atmospheric_system",
    "network",
    "celestial_body",
    "particle_system",
    "infrastructure",
)

RELATIONSHIP_TYPES: tuple[str, ...] = (
    "contains",
    "part_of",
    "attached_to",
    "connects_to",
    "flows_to",
    "bypasses",
    "merges_into",
    "causes",
    "supports",
    "orbits",
    "transforms_into",
    "compares_with",
)

EVENT_TYPES: tuple[str, ...] = (
    "CREATE",
    "REMOVE",
    "TRANSFORM",
    "TRANSFER",
    "GROW",
    "ASSEMBLE",
    "DISASSEMBLE",
    "PATH_MOTION",
    "PROPAGATE",
    "CONNECT",
    "DISCONNECT",
    "CAMERA",
    "EMPHASIZE",
    "MERGE",
    "SPLIT",
    "ORBIT_AROUND",
)

RENDERER_MODES: tuple[str, ...] = (
    "vector_2d",
    "procedural_2d",
    "data_2d",
    "mathematical_2d",
    "semantic_3d",
    "hybrid",
)

FEATURES_2D: tuple[str, ...] = (
    "text",
    "label",
    "shape",
    "path",
    "line",
    "arrow",
    "group",
    "draw",
    "grow",
    "count",
    "mark",
    "position",
    "scale",
    "opacity",
    "rotation",
)

CHART_FEATURES: tuple[str, ...] = (
    "bar",
    "line_chart",
    "area",
    "point",
    "axis",
    "legend",
    "numeric_label",
)

FEATURES_3D: tuple[str, ...] = (
    "group",
    "mesh",
    "primitive",
    "child_offset",
    "parent_rotation",
    "position",
    "scale",
    "camera",
)

# Names used by a few downstream integrations and by the architecture note.
OBJECT_FAMILIES = STRUCTURAL_FAMILIES
REPRESENTATIONS = REPRESENTATION_STRATEGIES
RELATIONSHIPS = RELATIONSHIP_TYPES
EVENTS = EVENT_TYPES
CAMERA_EVENTS: tuple[str, ...] = ("CAMERA",)


@dataclass(frozen=True)
class CapabilitySpec:
    """The executable contract around one registered semantic capability.

    ``compiler_binding`` is a symbolic trusted-engine binding (for example
    ``motion.transfer``), never source code.  The three obligation fields make
    it impossible for a name to be added as an enum-only capability.
    """

    name: str
    kind: str
    requirements: tuple[str, ...]
    compiler_binding: str
    observable_behavior: str
    validation_obligation: str
    qa_obligation: str
    renderer_modes: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    requirement_alternatives: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        if not self.name or not self.kind:
            raise VisualCapabilityError("capability name and kind are required")
        for field_name in (
            "compiler_binding",
            "observable_behavior",
            "validation_obligation",
            "qa_obligation",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise VisualCapabilityError(f"{field_name} is required for {self.name!r}")
        if len(set(self.requirements)) != len(self.requirements):
            raise VisualCapabilityError(f"duplicate requirements for {self.name!r}")
        if len(set(self.renderer_modes)) != len(self.renderer_modes):
            raise VisualCapabilityError(f"duplicate renderer modes for {self.name!r}")
        for alternative in self.requirement_alternatives:
            if not alternative or len(set(alternative)) != len(alternative):
                raise VisualCapabilityError(f"invalid requirement alternative for {self.name!r}")

    @property
    def compiler(self) -> str:
        """Compatibility spelling for the trusted symbolic compiler binding."""

        return self.compiler_binding

    @property
    def qa(self) -> str:
        """Compatibility spelling for the required QA obligation."""

        return self.qa_obligation

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "requirements": list(self.requirements),
            "compiler_binding": self.compiler_binding,
            "observable_behavior": self.observable_behavior,
            "validation_obligation": self.validation_obligation,
            "qa_obligation": self.qa_obligation,
            "renderer_modes": list(self.renderer_modes),
            "forbidden_behaviors": list(self.forbidden_behaviors),
            "requirement_alternatives": [list(alternative) for alternative in self.requirement_alternatives],
        }


def _spec(
    name: str,
    kind: str,
    requirements: Iterable[str],
    binding: str,
    behavior: str,
    validation: str,
    qa: str,
    *,
    renderer_modes: Iterable[str] = (),
    forbidden: Iterable[str] = (),
    alternatives: Iterable[Iterable[str]] = (),
) -> CapabilitySpec:
    return CapabilitySpec(
        name=name,
        kind=kind,
        requirements=tuple(requirements),
        compiler_binding=binding,
        observable_behavior=behavior,
        validation_obligation=validation,
        qa_obligation=qa,
        renderer_modes=tuple(renderer_modes),
        forbidden_behaviors=tuple(forbidden),
        requirement_alternatives=tuple(tuple(item) for item in alternatives),
    )


def _make_specs() -> tuple[CapabilitySpec, ...]:
    specs: list[CapabilitySpec] = []
    for name in CONTENT_INTENTS:
        specs.append(
            _spec(
                name,
                "content_intent",
                (),
                "director.intent",
                "the scene communicates the selected high-level intent",
                "intent is one of the registered bounded values",
                "review representation appropriateness for the intent",
            )
        )
    for name in REPRESENTATION_STRATEGIES:
        specs.append(
            _spec(
                name,
                "representation_strategy",
                (),
                "resolver.representation",
                "the selected representation is visible in the scene",
                "strategy is registered and compatible with scene data",
                "verify the representation matches the source meaning",
            )
        )
    for name in STRUCTURAL_FAMILIES:
        specs.append(
            _spec(
                name,
                "structural_family",
                ("semantic_name",),
                "resolver.structural_family",
                "the trusted procedural family shapes the subject",
                "family is registered and subject parts are bounded",
                "verify subject structure is recognizable and stable",
                renderer_modes=("vector_2d", "procedural_2d", "semantic_3d", "hybrid"),
            )
        )

    relation_specs = {
        "contains": (("source", "target"), "relation.contains", "target is spatially nested in source", "source and target exist; hierarchy has no cycle", "inspect nesting and group bounds"),
        "part_of": (("source", "target"), "relation.part_of", "source is grouped as a part of target", "source and target exist; hierarchy has no cycle", "inspect persistent part grouping"),
        "attached_to": (("source", "target"), "relation.attached_to", "source remains attached to target while it moves", "source and target exist", "sample relative attachment distance"),
        "connects_to": (("source", "target"), "relation.connects_to", "a stable visible connector joins source and target", "source and target exist and are distinct", "verify connector endpoints"),
        "flows_to": (("source", "target"), "relation.flows_to", "a directed route and optional carrier move from source to target", "source and target exist and direction is explicit", "sample carrier displacement and direction"),
        "bypasses": (("source", "target"), "relation.bypasses", "an alternate route avoids an intermediate structure", "source and target exist; route is not a generic connector", "verify route avoids declared intermediate nodes"),
        "merges_into": (("source", "target"), "relation.merges_into", "source visibly converges into target/result", "source and target exist and target is a result", "sample convergence rather than target-only reveal"),
        "causes": (("source", "target"), "relation.causes", "a source event can trigger a target state change", "source and target exist; a causal event is present", "verify target state changes after source event"),
        "supports": (("source", "target"), "relation.supports", "source provides a stable supporting relationship", "source and target exist", "verify support remains stable during motion"),
        "orbits": (("source", "target"), "relation.orbits", "source changes world position around target", "source and center exist; radius/trajectory is available", "sample relative positions around the center", ("self-rotation only",)),
        "transforms_into": (("source", "target"), "relation.transforms_into", "source state visibly becomes target state", "source and target exist; transform event is present", "verify geometry/state changes over time"),
        "compares_with": (("source", "target"), "relation.compares_with", "both values/subjects are shown with a meaningful comparison", "source and target exist", "verify comparison remains legible"),
    }
    for name, values in relation_specs.items():
        requirements, binding, behavior, validation, qa, *rest = values
        specs.append(
            _spec(
                name,
                "relationship",
                requirements,
                binding,
                behavior,
                validation,
                qa,
                renderer_modes=("vector_2d", "procedural_2d", "data_2d", "mathematical_2d", "semantic_3d", "hybrid"),
                forbidden=rest[0] if rest else (),
            )
        )

    event_specs = {
        "CREATE": (("subject",), "state.create", "the subject appears in the persistent scene state", "subject exists and receives a stable ID", "verify the subject is present after the event"),
        "REMOVE": (("subject",), "state.remove", "the subject leaves the visible persistent state", "subject exists and is not removed before use", "verify visibility/state removal"),
        "TRANSFORM": (("subject", "from_state", "to_state"), "state.transform", "the subject changes from one semantic state to another", "subject and both states are present", "sample before/after geometry or state"),
        "TRANSFER": (("source", "destination", "carrier"), "motion.transfer", "the carrier travels from source to destination", "source, destination, carrier exist and endpoints differ", "sample carrier displacement at multiple times"),
        "GROW": (("subject", "from_state", "to_state"), "motion.grow", "the subject geometry/state develops over time", "subject and states exist; target state differs", "sample measurable geometry/state increase", ("reveal-only",)),
        "ASSEMBLE": (("parts", "target"), "state.assemble", "parts move or appear as a coherent whole", "all parts and target exist", "verify part-to-whole convergence"),
        "DISASSEMBLE": (("subject", "parts"), "state.disassemble", "a whole separates into persistent parts", "subject and parts exist", "verify parts separate and remain addressable"),
        "PATH_MOTION": (("subject",), "motion.path", "the subject follows a trusted semantic route between subjects or orbits a center", "subject and one semantic route alternative are present", "sample subject displacement along the route", ("path coordinates",), (("source", "destination"), ("center", "radius", "mode"))),
        "PROPAGATE": (("source", "targets"), "motion.propagate", "a state/effect spreads from source through targets", "source and targets exist and are ordered", "verify propagation order and changed targets"),
        "CONNECT": (("source", "target"), "relation.connect", "a visible connection is created", "source and target exist and are distinct", "verify endpoint connection"),
        "DISCONNECT": (("source", "target"), "relation.disconnect", "an existing connection is visibly removed", "source and target exist", "verify connection absence after event"),
        "CAMERA": (("mode",), "camera.intent", "the camera changes according to bounded shot intent around a semantic target", "mode and a subject/target reference are present", "sample framing around the semantic target", (), (("mode", "subject"), ("mode", "target"))),
        "EMPHASIZE": (("subject",), "style.emphasize", "the subject receives a bounded emphasis treatment", "subject exists", "verify emphasis is visible without hiding context"),
        "MERGE": (("sources", "target"), "motion.merge", "two or more sources converge into a target/result", "sources and target exist; at least two sources", "sample source convergence and result state", ("target-only reveal",)),
        "SPLIT": (("subject", "targets"), "motion.split", "one persistent subject separates into target branches", "subject and at least two targets exist", "sample branch displacement"),
        "ORBIT_AROUND": (("subject", "center", "radius"), "motion.orbit", "subject world position changes around the center", "center exists; radius is positive", "sample relative positions and verify radius", ("self-rotation only",)),
    }
    for name, values in event_specs.items():
        requirements, binding, behavior, validation, qa, *rest = values
        alternatives: tuple[tuple[str, ...], ...] = ()
        forbidden: tuple[str, ...] = ()
        if rest and isinstance(rest[-1], tuple) and rest[-1] and isinstance(rest[-1][0], tuple):
            alternatives = tuple(tuple(item) for item in rest.pop())
        if rest:
            forbidden = tuple(rest[0])
        specs.append(
            _spec(
                name,
                "event",
                requirements,
                binding,
                behavior,
                validation,
                qa,
                renderer_modes=("vector_2d", "procedural_2d", "data_2d", "mathematical_2d", "semantic_3d", "hybrid"),
                forbidden=forbidden,
                alternatives=alternatives,
            )
        )

    renderer_specs = {
        "vector_2d": ("renderer.vector", "trusted SVG/vector structure is constructed from semantic data", "renderer mode is registered", "check SVG structure and safe bounds"),
        "procedural_2d": ("renderer.procedural", "trusted procedural family constructs the subject", "family and features are registered", "inspect structural recognizability"),
        "data_2d": ("renderer.data", "numeric series becomes an appropriate chart", "series is finite and bounded", "verify scale, labels, and values"),
        "mathematical_2d": ("renderer.math", "mathematical objects preserve their relationships", "numeric constraints are finite and bounded", "verify geometric/equation correctness"),
        "semantic_3d": ("renderer.three", "trusted groups and camera produce semantic 3D", "only registered primitives/features are used", "sample camera and relative motion"),
        "hybrid": ("renderer.hybrid", "registered 2D and 3D layers compose safely", "each layer has a registered mode", "verify cross-layer alignment"),
    }
    for name, (binding, behavior, validation, qa) in renderer_specs.items():
        specs.append(_spec(name, "renderer_mode", (), binding, behavior, validation, qa))

    # Features are included in the same registry so prompt generation and
    # schema checks can never accidentally advertise an unimplemented feature.
    for name in FEATURES_2D:
        specs.append(_spec(name, "feature_2d", (), f"feature.2d.{name}", f"the bounded 2D feature {name} is visible", "feature is registered", f"verify {name} at output resolution", renderer_modes=("vector_2d", "procedural_2d", "data_2d", "mathematical_2d", "hybrid")))
    for name in CHART_FEATURES:
        specs.append(_spec(name, "chart_feature", (), f"feature.chart.{name}", f"the chart feature {name} is visible", "feature is registered", f"verify chart {name} is legible", renderer_modes=("data_2d", "hybrid")))
    for name in FEATURES_3D:
        specs.append(_spec(name, "feature_3d", (), f"feature.3d.{name}", f"the semantic 3D feature {name} is visible", "feature is registered", f"verify 3D {name} behavior", renderer_modes=("semantic_3d", "hybrid")))
    return tuple(specs)


@dataclass(frozen=True)
class VisualCapabilities:
    """Immutable registry consumed by every V2.1 contract layer."""

    content_intents: tuple[str, ...]
    representation_strategies: tuple[str, ...]
    structural_families: tuple[str, ...]
    relationship_types: tuple[str, ...]
    event_types: tuple[str, ...]
    renderer_modes: tuple[str, ...]
    features_2d: tuple[str, ...]
    chart_features: tuple[str, ...]
    features_3d: tuple[str, ...]
    specs: Mapping[str, CapabilitySpec]

    def __post_init__(self) -> None:
        object.__setattr__(self, "specs", MappingProxyType(dict(self.specs)))
        errors = registry_alignment_errors(self)
        if errors:
            raise VisualCapabilityError("; ".join(errors))

    # Architecture-plan spellings and concise aliases.
    @property
    def representations(self) -> tuple[str, ...]:
        return self.representation_strategies

    @property
    def relationships(self) -> tuple[str, ...]:
        return self.relationship_types

    @property
    def events(self) -> tuple[str, ...]:
        return self.event_types

    @property
    def camera_events(self) -> tuple[str, ...]:
        return tuple(name for name in self.event_types if name == "CAMERA")

    @property
    def object_families(self) -> tuple[str, ...]:
        return self.structural_families

    @property
    def two_d_features(self) -> tuple[str, ...]:
        return self.features_2d

    @property
    def three_d_features(self) -> tuple[str, ...]:
        return self.features_3d

    def key(self, kind: str, name: str) -> str:
        return f"{kind}:{name}"

    def get(self, name: str, kind: str | None = None) -> CapabilitySpec | None:
        if kind is not None:
            canonical = canonical_capability_name(name, kind=kind, registry=self)
            return self.specs.get(self.key(kind, canonical))
        if not isinstance(name, str) or not name.strip():
            return None
        exact = [spec for spec in self.specs.values() if spec.name == name]
        if len(exact) == 1:
            return exact[0]
        token = _normalise_token(name)
        aliases = {alias: canonical for values in _ALIASES.values() for alias, canonical in values.items()}
        matches = [spec for spec in self.specs.values() if _normalise_token(spec.name) == token or aliases.get(token) == spec.name]
        return matches[0] if len(matches) == 1 else None

    def require(self, name: str, kind: str | None = None) -> CapabilitySpec:
        spec = self.get(name, kind=kind)
        if spec is None:
            scope = f" in {kind}" if kind else ""
            raise VisualCapabilityError(f"Unsupported capability{scope}: {name!r}")
        return spec

    def has(self, name: str, kind: str | None = None) -> bool:
        return self.get(name, kind=kind) is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_intents": list(self.content_intents),
            "representation_strategies": list(self.representation_strategies),
            "structural_families": list(self.structural_families),
            "relationship_types": list(self.relationship_types),
            "event_types": list(self.event_types),
            "renderer_modes": list(self.renderer_modes),
            "features_2d": list(self.features_2d),
            "chart_features": list(self.chart_features),
            "features_3d": list(self.features_3d),
            "specs": [self.specs[key].to_dict() for key in sorted(self.specs)],
        }

    def prompt_payload(self) -> dict[str, Any]:
        """Return only safe, semantic capability information for a prompt."""

        return {
            "content_intents": list(self.content_intents),
            "representation_strategies": list(self.representation_strategies),
            "structural_families": list(self.structural_families),
            "relationship_types": list(self.relationship_types),
            "event_types": list(self.event_types),
            "renderer_modes": list(self.renderer_modes),
            "2d_features": list(self.features_2d),
            "chart_features": list(self.chart_features),
            "3d_features": list(self.features_3d),
            "event_obligations": {
                name: self.specs[self.key("event", name)].to_dict() for name in self.event_types
            },
            "relationship_obligations": {
                name: self.specs[self.key("relationship", name)].to_dict() for name in self.relationship_types
            },
        }

    def prompt_text(self) -> str:
        return json.dumps(self.prompt_payload(), sort_keys=True, separators=(",", ":"))


def _normalise_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").casefold()


_ALIASES: dict[str, dict[str, str]] = {
    "event": {"orbit": "ORBIT_AROUND", "orbit_around": "ORBIT_AROUND", "merge_into": "MERGE", "split_into": "SPLIT"},
    "relationship": {"merge": "merges_into", "flow": "flows_to", "orbit": "orbits", "partof": "part_of"},
    "renderer_mode": {"svg": "vector_2d", "vector": "vector_2d", "procedural": "procedural_2d", "data": "data_2d", "3d": "semantic_3d", "three": "semantic_3d"},
}


def canonical_capability_name(name: Any, kind: str, registry: VisualCapabilities | None = None) -> str:
    if not isinstance(name, str) or not name.strip():
        raise VisualCapabilityError(f"{kind} capability must be a non-empty string")
    active = registry or _REGISTRY_PLACEHOLDER
    candidates = {
        "content_intent": active.content_intents,
        "representation_strategy": active.representation_strategies,
        "structural_family": active.structural_families,
        "relationship": active.relationship_types,
        "event": active.event_types,
        "renderer_mode": active.renderer_modes,
        "feature_2d": active.features_2d,
        "chart_feature": active.chart_features,
        "feature_3d": active.features_3d,
    }.get(kind)
    if candidates is None:
        raise VisualCapabilityError(f"unknown capability kind: {kind!r}")
    aliases = _ALIASES.get(kind, {})
    token = _normalise_token(name)
    for candidate in candidates:
        if _normalise_token(candidate) == token:
            return candidate
    if token in aliases:
        canonical = aliases[token]
        if canonical in candidates:
            return canonical
    raise VisualCapabilityError(f"Unsupported {kind}: {name!r}")


def registry_alignment_errors(registry: VisualCapabilities) -> tuple[str, ...]:
    """Return schema/compiler alignment defects instead of hiding them."""

    errors: list[str] = []
    categories = {
        "content_intent": registry.content_intents,
        "representation_strategy": registry.representation_strategies,
        "structural_family": registry.structural_families,
        "relationship": registry.relationship_types,
        "event": registry.event_types,
        "renderer_mode": registry.renderer_modes,
        "feature_2d": registry.features_2d,
        "chart_feature": registry.chart_features,
        "feature_3d": registry.features_3d,
    }
    for kind, names in categories.items():
        for name in names:
            key = f"{kind}:{name}"
            spec = registry.specs.get(key)
            if spec is None:
                errors.append(f"missing registry spec: {key}")
                continue
            if spec.kind != kind or spec.name != name:
                errors.append(f"mis-keyed registry spec: {key}")
            if not spec.compiler_binding or not spec.qa_obligation:
                errors.append(f"incomplete registry spec: {key}")
    for key, spec in registry.specs.items():
        if key != f"{spec.kind}:{spec.name}":
            errors.append(f"unexpected spec key: {key}")
    return tuple(errors)


def validate_registry_schema_alignment(registry: VisualCapabilities | None = None) -> bool:
    """Return whether every advertised capability has a full contract."""

    return not registry_alignment_errors(registry or VISUAL_CAPABILITIES)


def assert_registry_schema_alignment(registry: VisualCapabilities | None = None) -> None:
    errors = registry_alignment_errors(registry or VISUAL_CAPABILITIES)
    if errors:
        raise VisualCapabilityError("; ".join(errors))


def capability_spec(name: str, kind: str, registry: VisualCapabilities | None = None) -> CapabilitySpec:
    return (registry or VISUAL_CAPABILITIES).require(name, kind=kind)


# Construct the immutable default once.  The placeholder is only used while
# canonical helper functions are defined; construction itself uses exact
# registry keys and does not call the helper.
_REGISTRY_PLACEHOLDER = VisualCapabilities.__new__(VisualCapabilities)
object.__setattr__(_REGISTRY_PLACEHOLDER, "content_intents", CONTENT_INTENTS)
object.__setattr__(_REGISTRY_PLACEHOLDER, "representation_strategies", REPRESENTATION_STRATEGIES)
object.__setattr__(_REGISTRY_PLACEHOLDER, "structural_families", STRUCTURAL_FAMILIES)
object.__setattr__(_REGISTRY_PLACEHOLDER, "relationship_types", RELATIONSHIP_TYPES)
object.__setattr__(_REGISTRY_PLACEHOLDER, "event_types", EVENT_TYPES)
object.__setattr__(_REGISTRY_PLACEHOLDER, "renderer_modes", RENDERER_MODES)
object.__setattr__(_REGISTRY_PLACEHOLDER, "features_2d", FEATURES_2D)
object.__setattr__(_REGISTRY_PLACEHOLDER, "chart_features", CHART_FEATURES)
object.__setattr__(_REGISTRY_PLACEHOLDER, "features_3d", FEATURES_3D)
_default_specs = {f"{spec.kind}:{spec.name}": spec for spec in _make_specs()}
VISUAL_CAPABILITIES = VisualCapabilities(
    content_intents=CONTENT_INTENTS,
    representation_strategies=REPRESENTATION_STRATEGIES,
    structural_families=STRUCTURAL_FAMILIES,
    relationship_types=RELATIONSHIP_TYPES,
    event_types=EVENT_TYPES,
    renderer_modes=RENDERER_MODES,
    features_2d=FEATURES_2D,
    chart_features=CHART_FEATURES,
    features_3d=FEATURES_3D,
    specs={key: value for key, value in _default_specs.items()},
)
DEFAULT_VISUAL_CAPABILITIES = VISUAL_CAPABILITIES


def get_visual_capabilities() -> VisualCapabilities:
    return VISUAL_CAPABILITIES


def capabilities_for_prompt() -> dict[str, Any]:
    return VISUAL_CAPABILITIES.prompt_payload()


def visual_director_capability_prompt() -> str:
    return VISUAL_CAPABILITIES.prompt_text()


__all__ = [
    "CAMERA_EVENTS",
    "CapabilitySpec",
    "CHART_FEATURES",
    "CONTENT_INTENTS",
    "DEFAULT_VISUAL_CAPABILITIES",
    "EVENTS",
    "EVENT_TYPES",
    "FEATURES_2D",
    "FEATURES_3D",
    "OBJECT_FAMILIES",
    "RELATIONSHIPS",
    "RELATIONSHIP_TYPES",
    "REPRESENTATIONS",
    "REPRESENTATION_STRATEGIES",
    "RENDERER_MODES",
    "STRUCTURAL_FAMILIES",
    "VISUAL_CAPABILITIES",
    "VisualCapabilities",
    "VisualCapabilityError",
    "assert_registry_schema_alignment",
    "capabilities_for_prompt",
    "capability_spec",
    "canonical_capability_name",
    "get_visual_capabilities",
    "registry_alignment_errors",
    "validate_registry_schema_alignment",
    "visual_director_capability_prompt",
]
