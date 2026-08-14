"""Adaptive, content-driven visual-language rules for Video Flow.

The policy supplies semantic ingredients and accessibility constraints. The motion
director composes a fresh visual world and scene grammar for every document.
"""

from __future__ import annotations

import re
from typing import Any


_PAPER = "#fbfaf5"
_CARD = "rgba(255,255,255,0.92)"
_INK = "#171717"
_MUTED = "#696761"


THEME_PALETTES: dict[str, dict[str, Any]] = {
    "voice-flow": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#ff8a1f", "#ffd65a", "#8bd7e6", "#89c95d", "#ef4b43"],
    },
    "midnight": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#3448a5", "#7f73d8", "#8bd7e6", "#ffd65a", "#ff8a1f"],
    },
    "paper": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#ff8a1f", "#ffd65a", "#8bd7e6", "#89c95d", "#ef4b43"],
    },
    "neon": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#f04fb6", "#42d7c8", "#8b6de9", "#ddeb48", "#ff8a1f"],
    },
    "ocean": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#3aaed8", "#79d4d0", "#4f76c7", "#89c95d", "#ffd65a"],
    },
    "forest": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#6fba62", "#9fd07f", "#d7a94d", "#79c9c3", "#ff8a1f"],
    },
    "sunset": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#ff7b3f", "#ffbd55", "#ef6f87", "#8bd7e6", "#89c95d"],
    },
    "mono": {
        "background": _PAPER, "surface": _CARD, "text": _INK, "muted": _MUTED,
        "accents": ["#171717", "#5b5b5b", "#919191", "#c3c3c3", "#ededed"],
    },
}


DOMAIN_VISUAL_PROFILES: dict[str, dict[str, Any]] = {
    "study": {"motifs": ["margin-note", "memory-path", "concept-lens", "lesson-map"], "operators": ["annotate", "sequence", "nest", "compare"], "marks": ["underline", "brace", "page", "circle", "arrow"]},
    "business": {"motifs": ["market-signal", "decision-balance", "value-flow", "forecast"], "operators": ["rank", "split", "scale", "flow"], "marks": ["bar", "slope", "number", "band", "target"]},
    "gaming": {"motifs": ["level-map", "skill-tree", "score-race", "boss-gate"], "operators": ["branch", "path", "unlock", "orbit"], "marks": ["path", "badge", "meter", "node", "burst"]},
    "science": {"motifs": ["experiment", "system-model", "evidence-chain", "field-study"], "operators": ["measure", "orbit", "label", "transform"], "marks": ["plot", "particle", "ring", "wave", "callout"]},
    "technology": {"motifs": ["packet-journey", "system-stack", "dependency-map", "state-machine"], "operators": ["route", "layer", "branch", "contain"], "marks": ["port", "trace", "block", "terminal", "pulse"]},
    "health": {"motifs": ["care-journey", "body-system", "recovery-curve", "evidence-pulse"], "operators": ["flow", "focus", "cycle", "compare"], "marks": ["pulse", "ring", "path", "cell", "measure"]},
    "food": {"motifs": ["ingredient-story", "heat-change", "recipe-rhythm", "plate-build"], "operators": ["gather", "sequence", "transform", "balance"], "marks": ["ingredient", "timer", "steam", "measure", "plate"]},
    "nature": {"motifs": ["ecosystem", "season-cycle", "watershed", "growth-ring"], "operators": ["branch", "cycle", "flow", "accumulate"], "marks": ["leaf", "wave", "ring", "root", "particle"]},
    "security": {"motifs": ["evidence-board", "attack-route", "trust-boundary", "containment"], "operators": ["trace", "intercept", "partition", "verify"], "marks": ["packet", "boundary", "stamp", "alert", "shield"]},
    "general": {"motifs": ["idea-journey", "cause-ripple", "concept-bridge", "story-arc"], "operators": ["connect", "cluster", "sequence", "focus"], "marks": ["circle", "arrow", "label", "path", "highlight"]},
}


class VideoFlowThemePolicy:
    """Resolve explicit direction first, then stable subject-matter defaults."""

    RULES_VERSION = "2026.08.5-notebook-explanation-director"

    _direction_rules = (
        ("midnight", r"\b(night|midnight|moon|dark blue|deep blue|noir)\b"),
        ("neon", r"\b(neon|cyber|electric|magenta|hot pink|arcade)\b"),
        ("ocean", r"\b(ocean|sea|underwater|aqua|teal|cool blue)\b"),
        ("forest", r"\b(forest|nature|green|earthy|botanical|garden)\b"),
        ("paper", r"\b(paper|editorial|cream|white|minimal|daylight)\b"),
        ("sunset", r"\b(sunset|warm|orange|amber|red|golden hour|kitchen)\b"),
        ("mono", r"\b(monochrome|black and white|greyscale|grayscale|gray|grey)\b"),
    )

    _domain_patterns = (
        ("food", r"\b(recipe|cook|cooking|kitchen|food|bake|ingredient|restaurant|coffee)\w*\b"),
        ("business", r"\b(finance|revenue|market|investment|business|sales|margin|risk|econom|startup|customer)\w*\b"),
        ("gaming", r"\b(game|gaming|player|level|quest|esport|console|controller)\w*\b"),
        ("science", r"\b(science|research|experiment|laboratory|cell|molecule|physics|chemistry|biology|space exploration|astronomy|cosmos|planet)\w*\b"),
        # Specific security language wins over broad terms such as network.
        ("security", r"\b(legal|compliance|security|incident|forensic|audit|regulation|privacy|threat|phishing|credential|attacker|breach|malware|ransomware|authentication|firewall)\w*\b"),
        ("technology", r"\b(technology|software|data|code|api|network|computer|artificial intelligence|machine learning)\w*\b"),
        ("health", r"\b(health|medical|patient|disease|therapy|doctor|hospital|wellness)\w*\b"),
        ("nature", r"\b(environment|climate|nature|garden|agriculture|sustainab|wildlife|plant)\w*\b"),
        ("study", r"\b(history|education|lesson|book|writing|policy|guide|tutorial|literature|study|exam|course)\w*\b"),
    )

    _domain_rules = (
        ("sunset", r"\b(recipe|cook|cooking|kitchen|food|bake|ingredient|restaurant|coffee)\w*\b",
         "Tactile ingredient transformations, heat, timing, and plate-building motion."),
        ("midnight", r"\b(finance|revenue|market|investment|business|sales|margin|risk|econom)\w*\b",
         "Precise editorial data motion with value, risk, and decision structures."),
        ("ocean", r"\b(science|research|experiment|technology|software|data|medical|cell|molecule|space exploration|astronomy|cosmos|planet)\w*\b",
         "Evidence-led scientific or technical diagrams with measured transformations."),
        ("forest", r"\b(environment|climate|nature|garden|agriculture|sustainab|wildlife|plant)\w*\b",
         "Organic systems, growth, flow, and patient ecological pacing."),
        ("neon", r"\b(game|gaming|music|fashion|creative|art|festival|entertainment|future)\w*\b",
         "Expressive level, rhythm, score, or culture-driven motion."),
        ("paper", r"\b(history|education|lesson|book|writing|policy|guide|tutorial|literature)\w*\b",
         "Teachable visual explanations built from annotations, memory paths, and concepts."),
        ("mono", r"\b(legal|compliance|security|incident|forensic|audit|regulation)\w*\b",
         "Forensic evidence, boundaries, provenance, and unambiguous verification motion."),
    )

    @classmethod
    def classify_domain(cls, text: str) -> str:
        for domain, pattern in cls._domain_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return domain
        return "general"

    def choose(
        self,
        source_text: str,
        *,
        title: str = "",
        requested_theme: str = "auto",
        visual_direction: str = "",
    ) -> dict[str, Any]:
        direction = visual_direction.strip()
        corpus = f"{title}\n{source_text[:80_000]}".lower()
        domain = self.classify_domain(corpus)
        if direction:
            theme = self._theme_from_direction(direction) or (
                requested_theme if requested_theme in THEME_PALETTES and requested_theme != "auto" else "voice-flow"
            )
            return self._choice(theme, "user_direction", direction, domain)

        if requested_theme in THEME_PALETTES and requested_theme != "auto":
            return self._choice(
                requested_theme,
                "explicit_theme",
                f"Use the {requested_theme} palette as a starting point, then derive the composition from the document.",
                domain,
            )

        for theme, pattern, guidance in self._domain_rules:
            if re.search(pattern, corpus, flags=re.IGNORECASE):
                return self._choice(theme, "domain_rule", guidance, domain)
        return self._choice(
            "voice-flow",
            "default_rule",
            "Derive a distinctive visual world from the document's domain, tone, evidence, and central metaphor.",
            domain,
        )

    def _theme_from_direction(self, direction: str) -> str | None:
        for theme, pattern in self._direction_rules:
            if re.search(pattern, direction, flags=re.IGNORECASE):
                return theme
        return None

    def _choice(self, theme: str, source: str, direction: str, domain: str) -> dict[str, Any]:
        return {
            "system": "notebook-explanation-v5",
            "renderer": "editorial-storyboard-v5",
            "theme": theme,
            "source": source,
            "direction": direction,
            "domain": domain,
            "domain_profile": DOMAIN_VISUAL_PROFILES[domain],
            "palette": THEME_PALETTES[theme],
            "rules_version": self.RULES_VERSION,
            "scene_grammar": {
                "allowed": [
                    "hook", "statement", "quote", "metric", "comparison",
                    "process", "timeline", "grid", "chart", "diagram", "closing",
                ],
                "preferred_sequence": ["hook", "process", "metric", "comparison", "quote", "closing"],
                "one_dominant_idea": True,
                "maximum_cards": 4,
                "maximum_visible_sentences": 4,
            },
            "visual_rules": {
                "derive_world_from_content": True,
                "compose_primitives_not_templates": True,
                "semantic_marks_only": True,
                "rough_ink_outlines": True,
                "asset_first": True,
                "two_focal_points": True,
                "three_depth_layers": True,
                "avoid_repeated_card_grids": True,
                "avoid_generic_dashboard_decoration": True,
                "preserve_readability": True,
            },
            "motion_rules": {
                "intentional": True,
                "max_simultaneous_emphasis": 2,
                "avoid_generic_decoration": True,
                "preserve_readability": True,
                "path_reveals": True,
                "soft_card_settles": True,
                "hold_after_reveal": True,
            },
        }


video_flow_theme_policy = VideoFlowThemePolicy()
