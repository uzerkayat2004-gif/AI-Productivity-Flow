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
        "sensors", "actuator", "prototype", "industrial", "fabrication", "alloy", "metalwork",
        "motor", "engine", "gearbox", "turbine", "machined", "precision", "metallic", "copper",
        "aluminum", "titanium", "sheet metal", "tooling", "drill", "fastener", "bearing"
    ],
    VisualFamilyName.TECHNICAL_SYSTEMS.value: [
        "network", "distributed", "telemetry", "infrastructure", "protocol", "pipeline",
        "system", "circuit", "topology", "cluster", "node", "packet", "bandwidth",
        "latency", "throughput", "monitoring", "server", "mesh", "microservices", "pubsub",
        "signal flow", "telecom", "routing", "switch", "gateway", "queue", "broker", "event bus"
    ],
    VisualFamilyName.SCIENTIFIC_VISUALIZATION.value: [
        "biology", "chemistry", "physics", "medicine", "laboratory", "genetics", "quantum",
        "molecular", "clinical", "research", "optics", "molecule", "cell", "protein",
        "dna", "rna", "organism", "pathogen", "atom", "particle", "spectroscopy", "vaccine",
        "neural", "anatomy", "microscope", "organic structure", "cellular", "enzyme", "biochemical"
    ],
    VisualFamilyName.DATA_EDITORIAL.value: [
        "statistics", "economics", "finance", "market", "chart", "trend", "metric",
        "report", "inflation", "revenue", "publishing", "demographic", "gdp", "growth",
        "percentage", "quarterly", "forecast", "ratio", "benchmark", "dataset", "index",
        "quantitative", "editorial", "economy", "fiscal", "valuation", "profit", "margin", "pie chart", "bar graph"
    ],
    VisualFamilyName.EDITORIAL_DOCUMENTARY.value: [
        "history", "narrative", "biography", "documentary", "journey", "heritage", "story",
        "culture", "retrospective", "memoir", "legacy", "century", "era", "movement",
        "chronicle", "biographical", "historical context", "expedition", "portrait",
        "investigation", "feature story", "epoch", "chronological", "oral history"
    ],
    VisualFamilyName.SOFTWARE_ARCHITECTURE.value: [
        "code", "compiler", "algorithm", "runtime", "stack", "frame", "async", "web",
        "frontend", "backend", "devops", "git", "python", "javascript", "rust", "typescript",
        "api", "graphql", "rest", "database", "orm", "framework", "library", "thread",
        "ast", "syntax", "ide", "debugger", "cloud architecture", "software", "microservice"
    ],
    VisualFamilyName.HISTORICAL_ARCHIVAL.value: [
        "archive", "manuscript", "document", "record", "ancient", "museum", "artifact",
        "primary source", "exhibit", "parchment", "scroll", "inscription", "antiquity",
        "archaeology", "preservation", "catalog", "folio", "charter", "treaty",
        "sepia", "historical record", "paleography", "codex", "chronology"
    ],
    VisualFamilyName.ARCHITECTURAL_SPATIAL.value: [
        "building", "architecture", "spatial", "urban", "blueprint", "construction",
        "floor plan", "civil engineering", "structure", "facade", "interior", "elevation",
        "volume", "beam", "foundation", "concrete", "structural design", "rendering", "zoning",
        "isometric", "cadastral", "structural callout", "cantilever", "truss", "spatial layout"
    ],
    VisualFamilyName.MINIMAL_CONCEPTUAL.value: [
        "philosophy", "abstract", "pure logic", "mathematics", "minimalism", "fundamental",
        "principle", "set theory", "axiom", "concept", "thesis", "dialectic", "paradox",
        "metaphysics", "symbolic", "formal proof", "theorem", "reduction",
        "conceptual", "monochrome", "pure abstraction", "deduction", "epistemology"
    ],
}


class ArtDirectionResolver:
    """Resolver engine that maps content inputs to a canonical ArtDirectionGenome."""

    def __init__(self, default_family: str = VisualFamilyName.TECHNICAL_SYSTEMS.value) -> None:
        self.default_family = default_family

    def classify_family(
        self,
        source_text: str = "",
        topic_hint: str = "",
        visual_direction: str = "",
        mode: str = "summary",
        source_hash: str = "",
    ) -> str:
        """Classifies content into one of the 9 Curated Visual Families.

        Uses weighted keyword matching over visual direction hints, topic hints,
        source text, operational mode, and source_hash seeded diversification.
        """
        # 1. Direct family match in visual_direction or topic_hint
        combined_hints = f"{visual_direction} {topic_hint}".lower()
        for family_name in VISUAL_FAMILIES.keys():
            if family_name.lower() in combined_hints:
                return family_name

        scores: Dict[str, float] = {family: 0.0 for family in VISUAL_FAMILIES.keys()}
        vd_lower = visual_direction.lower()
        topic_lower = topic_hint.lower()
        text_lower = source_text.lower()

        # 2. Weighted keyword scoring across all families
        for family, keywords in FAMILY_KEYWORD_MAP.items():
            for kw in keywords:
                pattern = r"\b" + re.escape(kw) + r"\b"
                vd_matches = len(re.findall(pattern, vd_lower)) if vd_lower else 0
                topic_matches = len(re.findall(pattern, topic_lower)) if topic_lower else 0
                text_matches = len(re.findall(pattern, text_lower)) if text_lower else 0

                scores[family] += (vd_matches * 5.0) + (topic_matches * 3.0) + (text_matches * 1.0)

        # 3. Mode-specific weighting (e.g. spatial_3d favors Architectural / Spatial and Industrial Product)
        if mode == "spatial_3d":
            scores[VisualFamilyName.ARCHITECTURAL_SPATIAL.value] += 2.0
            scores[VisualFamilyName.INDUSTRIAL_PRODUCT.value] += 2.0

        best_family = max(scores, key=lambda f: scores[f])
        if scores[best_family] > 0.0:
            return best_family

        # 4. Source-hash diversification: Guarantee diverse families across diverse unclassified topics
        if source_hash:
            try:
                seed = int(source_hash[:8], 16)
                family_list = list(VISUAL_FAMILIES.keys())
                return family_list[seed % len(family_list)]
            except Exception:
                pass

        return self.default_family

    def resolve(
        self,
        source_text: str = "",
        topic_hint: str = "",
        source_hash: str = "",
        family_override: Optional[str] = None,
        mode: str = "summary",
        visual_direction: str = "",
    ) -> ArtDirectionGenome:
        """Resolves content intent into a fully hydrated ArtDirectionGenome.

        Args:
            source_text: Raw or normalized source text.
            topic_hint: Optional high-level topic or title description.
            source_hash: Unique source content hash for seeded variation.
            family_override: Explicit visual family name override.
            mode: Video generation mode (e.g. summary, full, spatial_3d).
            visual_direction: User visual direction / style hints.

        Returns:
            Fully hydrated ArtDirectionGenome conforming to contracts and anti-generic rules.
        """
        # If family_override matches "Auto" or is empty, resolve dynamically
        if family_override and family_override.strip().lower() != "auto":
            chosen_family_name = family_override
        else:
            chosen_family_name = self.classify_family(
                source_text=source_text,
                topic_hint=topic_hint,
                visual_direction=visual_direction,
                mode=mode,
                source_hash=source_hash,
            )

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
    mode: str = "summary",
    visual_direction: str = "",
) -> ArtDirectionGenome:
    """Convenience top-level function to resolve art direction."""
    resolver = ArtDirectionResolver()
    return resolver.resolve(
        source_text=source_text,
        topic_hint=topic_hint,
        source_hash=source_hash,
        family_override=family_override,
        mode=mode,
        visual_direction=visual_direction,
    )


ArtDirectionResolverV3 = ArtDirectionResolver
