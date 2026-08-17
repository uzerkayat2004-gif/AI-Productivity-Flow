"""Art Direction Resolver for Video Flow V3.

Determines the most appropriate Visual Family based on source text, topic hints,
or explicit overrides, and resolves a deterministic, fully hydrated ArtDirectionGenome
using source_hash for seeded variation.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Union

try:
    from voice_flow.video_flow_v3.contracts import ArtDirectionGenome
except ImportError:
    from ..contracts import ArtDirectionGenome

from voice_flow.video_flow_v3.art_direction.families import (
    VISUAL_FAMILIES,
    VisualFamilyName,
    VisualFamilySpec,
    get_visual_family_spec,
)
from voice_flow.video_flow_v3.art_direction.genome import (
    build_genome_from_family,
    validate_art_genome,
)


# Keyword mappings for visual family intent classification
FAMILY_KEYWORD_MAP: Dict[str, List[str]] = {
    VisualFamilyName.INDUSTRIAL_PRODUCT.value: [
        "hardware", "cad", "mechanical", "engineering", "manufacturing", "product design",
        "machinery", "chassis", "thermal", "component", "assembly", "enclosure", "robotics",
        "sensors", "actuator", "prototype", "industrial", "fabrication", "alloy", "metalwork"
    ],
    VisualFamilyName.TECHNICAL_SYSTEMS.value: [
        "network", "distributed", "telemetry", "infrastructure", "protocol", "pipeline",
        "system", "circuit", "topology", "cluster", "node", "packet", "bandwidth",
        "latency", "throughput", "monitoring", "server", "mesh", "microservices", "pubsub"
    ],
    VisualFamilyName.SCIENTIFIC_VISUALIZATION.value: [
        "biology", "chemistry", "physics", "medicine", "laboratory", "genetics", "quantum",
        "molecular", "clinical", "research", "optics", "molecule", "cell", "protein",
        "dna", "rna", "organism", "pathogen", "atom", "particle", "spectroscopy", "vaccine"
    ],
    VisualFamilyName.DATA_EDITORIAL.value: [
        "statistics", "economics", "finance", "market", "chart", "trend", "metric",
        "report", "inflation", "revenue", "publishing", "demographic", "gdp", "growth",
        "percentage", "quarterly", "forecast", "ratio", "benchmark", "dataset", "index"
    ],
    VisualFamilyName.EDITORIAL_DOCUMENTARY.value: [
        "history", "narrative", "biography", "documentary", "journey", "heritage", "story",
        "culture", "retrospective", "memoir", "legacy", "century", "era", "movement",
        "chronicle", "biographical", "historical context", "expedition", "portrait"
    ],
    VisualFamilyName.SOFTWARE_ARCHITECTURE.value: [
        "code", "compiler", "algorithm", "runtime", "stack", "frame", "async", "web",
        "frontend", "backend", "devops", "git", "python", "javascript", "rust", "typescript",
        "api", "graphql", "rest", "database", "orm", "framework", "library", "thread"
    ],
    VisualFamilyName.HISTORICAL_ARCHIVAL.value: [
        "archive", "manuscript", "document", "record", "ancient", "museum", "artifact",
        "primary source", "exhibit", "parchment", "scroll", "inscription", "antiquity",
        "archaeology", "preservation", "catalog", "folio", "charter", "treaty"
    ],
    VisualFamilyName.ARCHITECTURAL_SPATIAL.value: [
        "building", "architecture", "spatial", "urban", "blueprint", "construction",
        "floor plan", "civil engineering", "structure", "facade", "interior", "elevation",
        "volume", "beam", "foundation", "concrete", "structural design", "rendering", "zoning"
    ],
    VisualFamilyName.MINIMAL_CONCEPTUAL.value: [
        "philosophy", "abstract", "pure logic", "mathematics", "minimalism", "fundamental",
        "principle", "set theory", "axiom", "concept", "thesis", "dialectic", "paradox",
        "metaphysics", "symbolic", "formal proof", "theorem", "reduction"
    ],
}


class ArtDirectionResolver:
    """Resolver engine that maps content inputs to a canonical ArtDirectionGenome."""

    def __init__(self, default_family: str = VisualFamilyName.TECHNICAL_SYSTEMS.value) -> None:
        self.default_family = default_family

    def classify_family(self, source_text: str = "", topic_hint: str = "") -> str:
        """Classifies content into one of the 9 Curated Visual Families.

        Uses weighted keyword matching over combined topic hints and source text.
        """
        combined_text = f"{topic_hint} {topic_hint} {source_text}".lower()
        words = re.findall(r"\b\w+\b", combined_text)
        if not words:
            return self.default_family

        scores: Dict[str, float] = {family: 0.0 for family in VISUAL_FAMILIES.keys()}

        for family, keywords in FAMILY_KEYWORD_MAP.items():
            for kw in keywords:
                # Give higher weight to matches in topic_hint
                topic_matches = len(re.findall(r"\b" + re.escape(kw) + r"\b", topic_hint.lower()))
                text_matches = len(re.findall(r"\b" + re.escape(kw) + r"\b", source_text.lower()))
                scores[family] += (topic_matches * 3.0) + (text_matches * 1.0)

        best_family = max(scores, key=lambda f: scores[f])
        if scores[best_family] > 0.0:
            return best_family

        return self.default_family

    def resolve(
        self,
        source_text: str = "",
        topic_hint: str = "",
        source_hash: str = "",
        family_override: Optional[str] = None,
    ) -> ArtDirectionGenome:
        """Resolves content intent into a fully hydrated ArtDirectionGenome.

        Args:
            source_text: Raw or normalized source text.
            topic_hint: Optional high-level topic or title description.
            source_hash: Unique source content hash for seeded variation.
            family_override: Explicit visual family name override.

        Returns:
            Fully hydrated ArtDirectionGenome conforming to contracts and anti-generic rules.
        """
        if family_override:
            chosen_family_name = family_override
        else:
            chosen_family_name = self.classify_family(source_text, topic_hint)

        family_spec = get_visual_family_spec(chosen_family_name)

        genome = build_genome_from_family(
            family_spec=family_spec,
            source_hash=source_hash,
            enable_variation=True,
        )

        return genome


def resolve_art_direction(
    source_text: str = "",
    topic_hint: str = "",
    source_hash: str = "",
    family_override: Optional[str] = None,
) -> ArtDirectionGenome:
    """Convenience top-level function to resolve art direction."""
    resolver = ArtDirectionResolver()
    return resolver.resolve(
        source_text=source_text,
        topic_hint=topic_hint,
        source_hash=source_hash,
        family_override=family_override,
    )


ArtDirectionResolverV3 = ArtDirectionResolver
