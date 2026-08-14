"""Semantic, domain-aware, history-aware animation planning for Video Flow.

The renderer deliberately receives objects and actions instead of a template
name.  A scene's animation signature describes its choreography at the recipe
level, so changing coordinates alone cannot bypass the ten-video diversity
window.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
from typing import Any, Iterable


DOMAIN_GRAMMARS: dict[str, dict[str, Any]] = {
    "study": {
        "glyphs": ["book", "pencil", "brain", "bookmark", "question"],
        "layouts": ["lesson-ladder", "margin-map", "memory-spiral", "flashcard-constellation", "question-branch"],
        "choreographies": [
            ["write", "underline", "connect", "highlight"],
            ["flip", "stack", "annotate", "trace"],
            ["assemble", "circle", "recall", "reframe"],
            ["sketch", "link", "practice", "stamp"],
        ],
    },
    "business": {
        "glyphs": ["chart", "target", "coin", "briefcase", "arrow-up"],
        "layouts": ["decision-funnel", "market-quadrants", "value-staircase", "metric-orbit", "tradeoff-split"],
        "choreographies": [
            ["count", "compare", "project", "stamp"],
            ["flow", "rank", "converge", "highlight"],
            ["split", "measure", "rebalance", "reframe"],
            ["stack", "trace", "target", "resolve"],
        ],
    },
    "gaming": {
        "glyphs": ["controller", "trophy", "flag", "gem", "map"],
        "layouts": ["level-path", "boss-arena", "quest-branch", "score-orbit", "upgrade-tree"],
        "choreographies": [
            ["spawn", "travel", "unlock", "celebrate"],
            ["charge", "dodge", "counter", "level-up"],
            ["collect", "branch", "combine", "stamp"],
            ["race", "score", "reveal", "reframe"],
        ],
    },
    "science": {
        "glyphs": ["flask", "atom", "microscope", "molecule", "wave"],
        "layouts": ["experiment-bench", "evidence-chain", "molecule-orbit", "hypothesis-split", "observation-grid"],
        "choreographies": [
            ["mix", "react", "measure", "conclude"],
            ["observe", "zoom", "label", "connect"],
            ["orbit", "collide", "transform", "stabilize"],
            ["compare", "filter", "plot", "highlight"],
        ],
    },
    "technology": {
        "glyphs": ["chip", "terminal", "network", "database", "robot"],
        "layouts": ["packet-route", "system-layers", "dependency-graph", "request-waterfall", "data-pipeline"],
        "choreographies": [
            ["boot", "route", "process", "respond"],
            ["connect", "transfer", "transform", "cache"],
            ["compile", "branch", "merge", "deploy"],
            ["pulse", "trace", "fan-out", "resolve"],
        ],
    },
    "health": {
        "glyphs": ["heart", "pulse", "cross", "cell", "care"],
        "layouts": ["care-path", "body-map", "recovery-cycle", "evidence-rings", "symptom-branch"],
        "choreographies": [
            ["pulse", "scan", "diagnose", "recover"],
            ["flow", "block", "treat", "stabilize"],
            ["compare", "measure", "support", "highlight"],
            ["trace", "focus", "heal", "reframe"],
        ],
    },
    "food": {
        "glyphs": ["bowl", "leaf", "timer", "flame", "ingredient"],
        "layouts": ["recipe-counter", "ingredient-orbit", "heat-timeline", "plate-assembly", "before-after"],
        "choreographies": [
            ["pour", "mix", "heat", "plate"],
            ["slice", "scatter", "combine", "garnish"],
            ["measure", "sequence", "transform", "serve"],
            ["compare", "balance", "finish", "stamp"],
        ],
    },
    "nature": {
        "glyphs": ["leaf", "globe", "drop", "sun", "tree"],
        "layouts": ["ecosystem-web", "season-cycle", "watershed-flow", "impact-rings", "growth-branch"],
        "choreographies": [
            ["seed", "grow", "branch", "bloom"],
            ["flow", "evaporate", "gather", "rain"],
            ["orbit", "shift", "adapt", "balance"],
            ["spread", "connect", "restore", "highlight"],
        ],
    },
    "security": {
        "glyphs": ["shield", "lock", "warning", "key", "packet"],
        "layouts": ["threat-route", "trust-boundaries", "attack-tree", "defense-rings", "control-layers"],
        "choreographies": [
            ["probe", "trace", "intercept", "lock"],
            ["breach", "spread", "contain", "recover"],
            ["challenge", "verify", "block", "stamp"],
            ["scan", "flag", "reroute", "shield"],
        ],
    },
    "general": {
        "glyphs": ["bulb", "note", "arrow", "circle", "star"],
        "layouts": ["idea-burst", "concept-bridge", "story-arc", "question-cluster", "cause-ripple"],
        "choreographies": [
            ["sketch", "connect", "transform", "highlight"],
            ["reveal", "branch", "combine", "resolve"],
            ["write", "circle", "travel", "reframe"],
            ["scatter", "group", "rank", "stamp"],
        ],
    },
}

CAMERAS = ["push", "pullback", "pan", "track", "tilt"]
TRANSITIONS = ["ink-wipe", "page-slide", "marker-sweep", "focus-pull", "paper-cut", "diagram-match"]
DIRECTIONS = ["left", "right", "up", "down", "clockwise", "counterclockwise"]
SURFACE_STYLES = ["annotation", "sticky", "badge", "cutout", "label", "panel"]

# Video-level visual genres. These change the complete graphic language, not
# merely scene coordinates. A genre is reserved across the same ten-video
# history window as animation recipes.
ART_DIRECTIONS: dict[str, dict[str, Any]] = {
    "editorial-sketch": {"name": "Editorial Sketch", "background": "editorial-paper", "shapeLanguage": "ink-annotations", "motionPhysics": "drawn", "titleTreatment": "editorial", "fontSystem": "humanist", "palette": {"background": "#fbfaf5", "text": "#171717", "muted": "#696761", "accents": ["#ff8a1f", "#ffd65a", "#78cae2", "#82c760", "#ef554d"]}},
    "swiss-signal": {"name": "Swiss Signal", "background": "swiss-grid", "shapeLanguage": "geometric-modules", "motionPhysics": "snap", "titleTreatment": "grid-lock", "fontSystem": "grotesk", "palette": {"background": "#f2f1ed", "text": "#121212", "muted": "#555555", "accents": ["#0057ff", "#ff3b30", "#f2c94c", "#111111", "#7b61ff"]}},
    "shadow-investigation": {"name": "Shadow Investigation", "background": "cinematic-noir", "shapeLanguage": "silhouette-cuts", "motionPhysics": "glide", "titleTreatment": "noir", "fontSystem": "condensed", "palette": {"background": "#090909", "text": "#f0eee8", "muted": "#aaa7a0", "accents": ["#c1121f", "#f0eee8", "#5b6068", "#d99824", "#6b1d24"]}},
    "blueprint-systems": {"name": "Blueprint Systems", "background": "blueprint", "shapeLanguage": "technical-wireframe", "motionPhysics": "mechanical", "titleTreatment": "technical", "fontSystem": "mono", "palette": {"background": "#082a4a", "text": "#e9f7ff", "muted": "#9ec7dc", "accents": ["#64d8ff", "#ffffff", "#ffc857", "#62d6a7", "#ff6b6b"]}},
    "kinetic-poster": {"name": "Kinetic Poster", "background": "poster-blocks", "shapeLanguage": "type-blocks", "motionPhysics": "slam", "titleTreatment": "giant-type", "fontSystem": "display", "palette": {"background": "#f4df26", "text": "#111111", "muted": "#3b3210", "accents": ["#e63946", "#111111", "#ffffff", "#0066ff", "#ff7a00"]}},
    "soft-organic": {"name": "Soft Organic", "background": "soft-field", "shapeLanguage": "organic-blobs", "motionPhysics": "drift", "titleTreatment": "serif", "fontSystem": "serif", "palette": {"background": "#fff6e9", "text": "#2d2a26", "muted": "#776f66", "accents": ["#d98f70", "#8faf8c", "#c4a3a3", "#efc46f", "#79a9b8"]}},
    "chalk-lesson": {"name": "Chalk Lesson", "background": "chalkboard", "shapeLanguage": "chalk-marks", "motionPhysics": "drawn", "titleTreatment": "chalk", "fontSystem": "handwritten", "palette": {"background": "#193d34", "text": "#f4f0df", "muted": "#b9c8bd", "accents": ["#ffd166", "#efefef", "#73d2de", "#ef767a", "#8ed081"]}},
    "paper-collage": {"name": "Paper Collage", "background": "collage", "shapeLanguage": "torn-paper", "motionPhysics": "bounce", "titleTreatment": "cutout", "fontSystem": "editorial", "palette": {"background": "#efe4d1", "text": "#201d19", "muted": "#6e6255", "accents": ["#e4572e", "#17bebb", "#ffc914", "#5c415d", "#76b041"]}},
    "retro-terminal": {"name": "Retro Terminal", "background": "terminal", "shapeLanguage": "terminal-windows", "motionPhysics": "jitter", "titleTreatment": "prompt", "fontSystem": "mono", "palette": {"background": "#07110a", "text": "#b8ffbf", "muted": "#62a86a", "accents": ["#39ff6a", "#f4ff52", "#00c8ff", "#ff5470", "#d7ffd9"]}},
    "folk-diagram": {"name": "Folk Diagram", "background": "folk-pattern", "shapeLanguage": "pattern-tiles", "motionPhysics": "bounce", "titleTreatment": "playful", "fontSystem": "rounded", "palette": {"background": "#fffdf5", "text": "#1b1b1b", "muted": "#665c54", "accents": ["#ff1493", "#0047ab", "#ffe000", "#009b77", "#f15a24"]}},
    "archival-report": {"name": "Archival Report", "background": "archive", "shapeLanguage": "document-stamps", "motionPhysics": "measured", "titleTreatment": "masthead", "fontSystem": "serif", "palette": {"background": "#e7dcc6", "text": "#221f1a", "muted": "#6b6256", "accents": ["#8b1e1e", "#263b5a", "#9a7b3f", "#3d5a40", "#c06c45"]}},
    "data-constellation": {"name": "Data Constellation", "background": "data-space", "shapeLanguage": "light-nodes", "motionPhysics": "float", "titleTreatment": "minimal-glow", "fontSystem": "grotesk", "palette": {"background": "#080b18", "text": "#edf4ff", "muted": "#8996ac", "accents": ["#7c3aed", "#06b6d4", "#38bdf8", "#f472b6", "#a3e635"]}},
}

DOMAIN_ART_DIRECTION_ORDER: dict[str, list[str]] = {
    "study": ["chalk-lesson", "editorial-sketch", "archival-report", "paper-collage", "soft-organic", "swiss-signal"],
    "business": ["swiss-signal", "archival-report", "blueprint-systems", "shadow-investigation", "editorial-sketch", "data-constellation"],
    "gaming": ["kinetic-poster", "retro-terminal", "folk-diagram", "data-constellation", "paper-collage", "blueprint-systems"],
    "science": ["blueprint-systems", "data-constellation", "chalk-lesson", "editorial-sketch", "swiss-signal", "archival-report"],
    "technology": ["data-constellation", "blueprint-systems", "retro-terminal", "swiss-signal", "kinetic-poster", "shadow-investigation"],
    "health": ["soft-organic", "editorial-sketch", "swiss-signal", "folk-diagram", "chalk-lesson", "paper-collage"],
    "food": ["folk-diagram", "paper-collage", "soft-organic", "editorial-sketch", "kinetic-poster", "archival-report"],
    "nature": ["soft-organic", "folk-diagram", "editorial-sketch", "data-constellation", "paper-collage", "chalk-lesson"],
    "security": ["shadow-investigation", "blueprint-systems", "retro-terminal", "archival-report", "swiss-signal", "kinetic-poster"],
    "general": ["editorial-sketch", "swiss-signal", "paper-collage", "kinetic-poster", "soft-organic", "data-constellation"],
}
# Concrete illustration vocabulary. These are ingredients rather than scene
# templates: the director combines them with document entities, spatial
# composition, and semantic events to create a purpose-built scene world.
DOMAIN_ILLUSTRATION_PROPS: dict[str, list[str]] = {
    "study": ["book", "page", "pencil", "brain", "question", "annotation", "memory-path", "example"],
    "business": ["ledger", "coin", "bar-chart", "scale", "target", "market-arrow", "risk-meter", "customer"],
    "gaming": ["player", "controller", "level-map", "gate", "trophy", "health-bar", "skill-tree", "boss"],
    "science": ["flask", "molecule", "atom", "microscope", "specimen", "cell", "wave", "gauge"],
    "technology": ["request", "packet", "service", "database", "terminal", "chip", "queue", "cable"],
    "health": ["heart", "pulse", "cell", "body", "care-team", "medicine", "recovery-path", "scan"],
    "food": ["ingredient", "bowl", "flame", "timer", "knife", "pan", "plate", "steam"],
    "nature": ["tree", "leaf", "river", "cloud", "sun", "root", "animal", "water-drop"],
    "security": ["email", "cursor", "clock", "fingerprint", "credential", "laptop", "server", "cloud", "lock", "gate", "shield", "key"],
    "general": ["document", "idea", "person", "path", "target", "tool", "signal", "result"],
}

DOMAIN_ILLUSTRATION_WORLDS: dict[str, list[str]] = {
    "study": ["lesson-desk", "memory-landscape", "annotated-page", "question-trail"],
    "business": ["decision-room", "market-landscape", "ledger-table", "value-scale"],
    "gaming": ["level-world", "quest-map", "upgrade-workbench", "boss-arena"],
    "science": ["lab-bench", "specimen-field", "experiment-cutaway", "evidence-wall"],
    "technology": ["system-cutaway", "packet-landscape", "service-workbench", "data-route"],
    "health": ["care-journey", "body-landscape", "recovery-room", "diagnostic-cutaway"],
    "food": ["recipe-counter", "ingredient-landscape", "kitchen-process", "plate-assembly"],
    "nature": ["ecosystem-landscape", "watershed-map", "growth-cutaway", "season-field"],
    "security": ["evidence-board", "attack-route", "trust-boundary", "containment-room"],
    "general": ["story-landscape", "idea-workbench", "concept-map", "transformation-stage"],
}

ILLUSTRATION_STYLES = [
    "editorial-ink", "cut-paper", "technical-engraving", "soft-gouache",
    "chalk-science", "archival-map", "diagrammatic-line", "screenprint",
]

NOTEBOOK_EDITORIAL_PALETTES: dict[str, list[str]] = {
    "study": ["#f28c28", "#f5cc52", "#6eafd4", "#d86d67", "#789c67"],
    "business": ["#f2c94c", "#e58b2a", "#537aa5", "#c65050", "#6c8b78"],
    "gaming": ["#e9762b", "#edc84b", "#507bb5", "#c95f73", "#5f9273"],
    "science": ["#4f9ebd", "#efc84a", "#df7d50", "#6d9b72", "#9d73a7"],
    "technology": ["#4c91b8", "#f0c54a", "#e37b42", "#667c9f", "#6a9d86"],
    "health": ["#d76761", "#efb84e", "#5b9eb3", "#79a46c", "#b47c9f"],
    "food": ["#e77e32", "#efc54a", "#74a45f", "#c75d4e", "#6998ae"],
    "nature": ["#6c9d64", "#e2b347", "#4e98a8", "#d87545", "#8f765d"],
    "security": ["#e67e22", "#efc94c", "#4a8fb3", "#cb4e46", "#687780"],
    "general": ["#e9812d", "#efc84b", "#5598b4", "#cb6256", "#77916a"],
}
# A visual dialect changes the physical language of an entire video while
# retaining the clean editorial restraint of the NotebookLM reference.
DIALECT_BY_DIRECTION: dict[str, dict[str, str]] = {
    "editorial-sketch": {"name": "field-notes", "paperPattern": "clean", "assetTreatment": "marker-wash", "connectorStyle": "curved", "typography": "humanist", "motionProfile": "measured-draw", "frameTreatment": "open-margin"},
    "swiss-signal": {"name": "analysis-grid", "paperPattern": "graph", "assetTreatment": "technical", "connectorStyle": "right-angle", "typography": "grotesk", "motionProfile": "precise-build", "frameTreatment": "registration-grid"},
    "shadow-investigation": {"name": "case-dossier", "paperPattern": "archive", "assetTreatment": "engraved", "connectorStyle": "dashed", "typography": "condensed", "motionProfile": "evidence-reveal", "frameTreatment": "case-file"},
    "blueprint-systems": {"name": "systems-blueprint", "paperPattern": "ledger", "assetTreatment": "technical", "connectorStyle": "loop", "typography": "mono", "motionProfile": "trace-build", "frameTreatment": "blueprint-index"},
    "kinetic-poster": {"name": "poster-notes", "paperPattern": "clean", "assetTreatment": "marker-wash", "connectorStyle": "ribbon", "typography": "display", "motionProfile": "kinetic-build", "frameTreatment": "bold-rule"},
    "soft-organic": {"name": "field-atlas", "paperPattern": "field", "assetTreatment": "marker-wash", "connectorStyle": "curved", "typography": "serif", "motionProfile": "gentle-grow", "frameTreatment": "botanical-margin"},
    "chalk-lesson": {"name": "classroom-notes", "paperPattern": "ruled", "assetTreatment": "engraved", "connectorStyle": "loop", "typography": "handwritten", "motionProfile": "chalk-build", "frameTreatment": "lesson-margin"},
    "paper-collage": {"name": "cut-paper-folio", "paperPattern": "clean", "assetTreatment": "cutout", "connectorStyle": "ribbon", "typography": "editorial", "motionProfile": "piece-assemble", "frameTreatment": "taped-corners"},
    "retro-terminal": {"name": "trace-log", "paperPattern": "ledger", "assetTreatment": "technical", "connectorStyle": "right-angle", "typography": "mono", "motionProfile": "packet-trace", "frameTreatment": "log-index"},
    "folk-diagram": {"name": "illustrated-folio", "paperPattern": "field", "assetTreatment": "cutout", "connectorStyle": "curved", "typography": "rounded", "motionProfile": "folk-assemble", "frameTreatment": "ornamented-margin"},
    "archival-report": {"name": "archive-report", "paperPattern": "archive", "assetTreatment": "archive", "connectorStyle": "dashed", "typography": "serif", "motionProfile": "document-reveal", "frameTreatment": "report-border"},
    "data-constellation": {"name": "research-map", "paperPattern": "ledger", "assetTreatment": "engraved", "connectorStyle": "loop", "typography": "grotesk", "motionProfile": "node-build", "frameTreatment": "indexed-field"},
}

CONSTRUCTION_FAMILIES: dict[str, list[str]] = {
    "hook": ["editorial-cover", "question-led", "object-hero", "cold-open", "annotated-poster"],
    "sequence": ["causal-chain", "step-ladder", "layered-flow", "domino", "radial-process"],
    "comparison": ["balance", "before-after", "fork", "spectrum", "evidence-columns"],
    "measure": ["columns", "horizontal-bars", "line-plot", "slope", "annotated-number"],
    "network": ["hub-spoke", "boundary-crossing", "layered-cutaway", "evidence-board", "orbit-map"],
    "closing": ["emblem", "resolved-system", "seal", "before-after-summary", "synthesis-map"],
    "concept": ["margin-essay", "cause-map", "object-story", "annotated-cutaway", "visual-equation"],
}
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "for", "from",
    "has", "in", "into", "is", "it", "of", "on", "or", "that", "the", "their",
    "this", "to", "turn", "with",
}


def _digest(value: Any, length: int = 20) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def _clean_label(value: str, maximum: int = 46) -> str:
    text = re.sub(r"\s+", " ", value).strip(" .,:;-\n\t")
    words = text.split()
    if len(words) > 8:
        text = " ".join(words[:8])
    return text[:maximum].rstrip()


def _cue(label: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", label.lower())
    return next((word for word in words if word not in STOP_WORDS and len(word) > 2), words[0] if words else "idea")


class VideoMotionDirector:
    """Compile semantic scenes into unique procedural animation plans."""

    DIVERSITY_WINDOW = 10

    def direct(
        self,
        plan: dict[str, Any],
        *,
        video_id: str,
        visual_language: dict[str, Any] | None = None,
        recent_history: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result = copy.deepcopy(plan)
        history = list(recent_history or [])[-self.DIVERSITY_WINDOW :]
        disallowed_scene_signatures = {
            str(signature)
            for item in history
            for signature in item.get("scene_signatures", [])
        }
        disallowed_video_signatures = {str(item.get("video_signature", "")) for item in history}
        chosen_scene_signatures: set[str] = set()
        visual_language = visual_language or {}
        art_direction = self._select_art_direction(result, video_id, visual_language, history)
        art_direction = self._notebook_editorial_direction(art_direction, visual_language)
        result["artDirection"] = art_direction
        illustration_bible = self._illustration_bible(result, video_id, visual_language, art_direction)
        result["illustrationBible"] = illustration_bible

        for scene_index, scene in enumerate(result.get("scenes") or []):
            motion = self._unique_scene_plan(
                scene,
                video_id=video_id,
                scene_index=scene_index,
                forbidden=disallowed_scene_signatures | chosen_scene_signatures,
                art_direction=art_direction,
                illustration_bible=illustration_bible,
            )
            scene["motionPlan"] = motion
            scene["visualVariant"] = motion["signature"]
            chosen_scene_signatures.add(motion.get("designSignature", motion["signature"]))

        scene_signatures = [scene["motionPlan"].get("designSignature", scene["motionPlan"]["signature"]) for scene in result.get("scenes") or []]
        video_signature = _digest(scene_signatures)
        if video_signature in disallowed_video_signatures:
            # This is extraordinarily unlikely after per-scene rejection, but
            # the video-level guard makes concurrent/replayed jobs explicit.
            salt = 1
            while video_signature in disallowed_video_signatures:
                video_signature = _digest([*scene_signatures, video_id, salt])
                salt += 1
        result["animationSignature"] = video_signature
        result["motionSystem"] = {
            "name": "notebook-explanation-director-v5",
            "version": 5,
            "diversityWindow": self.DIVERSITY_WINDOW,
            "historyChecked": len(history),
            "houseStyle": visual_language.get("system", "adaptive-motion"),
            "artDirectionId": art_direction["id"],
            "visualDialect": art_direction["visualDialect"],
            "renderer": "editorial-storyboard-v5",
        }
        return result

    @staticmethod
    def _notebook_editorial_direction(
        selected: dict[str, Any], visual_language: dict[str, Any]
    ) -> dict[str, Any]:
        """Translate a selected genre into a visibly different editorial dialect."""
        domain = str(visual_language.get("domain") or selected.get("domain") or "general").lower()
        if domain not in NOTEBOOK_EDITORIAL_PALETTES:
            domain = "general"
        source_id = str(selected.get("id") or "editorial-sketch")
        dialect = DIALECT_BY_DIRECTION.get(source_id, DIALECT_BY_DIRECTION["editorial-sketch"])
        paper_colors = {
            "clean": "#fbfaf6", "ruled": "#fbfaf5", "graph": "#f7f8f4",
            "ledger": "#f6f3eb", "archive": "#f2eadb", "field": "#faf7ee",
        }
        result = copy.deepcopy(selected)
        result.update({
            "name": f"{domain.title()} · {dialect['name'].replace('-', ' ').title()}",
            "background": "notebook-paper",
            "paperPattern": dialect["paperPattern"],
            "assetTreatment": dialect["assetTreatment"],
            "connectorStyle": dialect["connectorStyle"],
            "visualDialect": f"{domain}-{dialect['name']}",
            "shapeLanguage": f"notebook-{dialect['assetTreatment']}",
            "motionPhysics": dialect["motionProfile"],
            "titleTreatment": dialect["frameTreatment"],
            "fontSystem": dialect["typography"],
            "referenceStyle": "classic-editorial-illustration",
            "sourceDirectionId": source_id,
            "palette": {
                "background": paper_colors[dialect["paperPattern"]],
                "text": "#171612", "muted": "#69665f",
                "accents": NOTEBOOK_EDITORIAL_PALETTES[domain],
            },
        })
        return result
    def _select_art_direction(
        self,
        plan: dict[str, Any],
        video_id: str,
        visual_language: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        scenes = list(plan.get("scenes") or [])
        domain = str(visual_language.get("domain") or (scenes[0].get("domain") if scenes else "general") or "general")
        if domain not in DOMAIN_ART_DIRECTION_ORDER:
            domain = "general"
        used: set[str] = set()
        for item in history:
            explicit = str(item.get("art_direction_id") or "")
            stored_domain = str(item.get("domain") or "")
            if explicit:
                used.add(explicit)
            if "|" in stored_domain:
                used.add(stored_domain.rsplit("|", 1)[-1])
        preferred = DOMAIN_ART_DIRECTION_ORDER[domain]
        remaining = [key for key in ART_DIRECTIONS if key not in preferred]
        offset = int(_digest([video_id, domain], 8), 16) % len(preferred)
        ordered = [*preferred[offset:], *preferred[:offset], *remaining]
        selected_id = next((key for key in ordered if key not in used), ordered[0])
        profile = copy.deepcopy(ART_DIRECTIONS[selected_id])
        profile.update({"id": selected_id, "domain": domain, "selectionWindow": self.DIVERSITY_WINDOW})
        return profile
    def synchronize_scene(self, scene: dict[str, Any]) -> None:
        """Retarget motion cues to Edge TTS word boundaries when available."""
        motion = scene.get("motionPlan") or {}
        actions = motion.get("actions") or []
        words = scene.get("wordTimings") or []
        duration = max(0.001, float(scene.get("durationSeconds") or 1))
        by_word: dict[str, float] = {}
        for word in words:
            token = _cue(str(word.get("text") or ""))
            if token and token not in by_word:
                by_word[token] = float(word.get("offsetSeconds") or 0)
        for action in actions:
            match = by_word.get(_cue(str(action.get("cue") or "")))
            if match is None:
                continue
            old_start = float(action.get("startRatio") or 0)
            old_end = float(action.get("endRatio") or min(1.0, old_start + 0.12))
            span = max(0.055, old_end - old_start)
            start = max(0.015, min(0.92, match / duration))
            action["startRatio"] = round(start, 4)
            action["endRatio"] = round(min(0.985, start + span), 4)
        action_by_id = {str(action.get("id") or ""): action for action in actions}
        for event in (motion.get("illustrationPlan") or {}).get("events") or []:
            action = action_by_id.get(str(event.get("actionId") or ""))
            if action:
                event["startRatio"] = action["startRatio"]
                event["endRatio"] = action["endRatio"]
        motion["renderWindows"] = self._render_windows(actions)
        motion["timingSource"] = "edge-word-boundaries" if words else "semantic-beats"

    def _unique_scene_plan(
        self,
        scene: dict[str, Any],
        *,
        video_id: str,
        scene_index: int,
        forbidden: set[str],
        art_direction: dict[str, Any],
        illustration_bible: dict[str, Any],
    ) -> dict[str, Any]:
        for attempt in range(160):
            candidate = self._scene_plan(scene, video_id, scene_index, attempt, art_direction, illustration_bible)
            if candidate.get("designSignature", candidate["signature"]) not in forbidden:
                return candidate
        raise RuntimeError("Could not produce a fresh animation recipe inside the ten-video diversity window.")

    def _scene_plan(self, scene: dict[str, Any], video_id: str, scene_index: int, attempt: int, art_direction: dict[str, Any], illustration_bible: dict[str, Any]) -> dict[str, Any]:
        domain = str(scene.get("domain") or "general").lower()
        if domain not in DOMAIN_GRAMMARS:
            domain = "general"
        grammar = DOMAIN_GRAMMARS[domain]
        semantic_mode = self._semantic_mode(scene)
        composition_family = self._composition_family(scene, semantic_mode, scene_index, video_id)
        visual_grammar = self._visual_grammar(scene, semantic_mode, domain, scene_index, video_id, art_direction)
        seed_text = f"{video_id}|{scene.get('id')}|{scene.get('title')}|{scene.get('narration')}|{attempt}"
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        layout = grammar["layouts"][(seed + scene_index + attempt) % len(grammar["layouts"])]
        choreography = grammar["choreographies"][(seed // 11 + attempt) % len(grammar["choreographies"])]
        camera_mode = CAMERAS[(seed // 17 + attempt) % len(CAMERAS)]
        camera_direction = DIRECTIONS[(seed // 23 + scene_index) % len(DIRECTIONS)]
        transition = TRANSITIONS[(seed // 31 + attempt) % len(TRANSITIONS)]
        tempo = ["measured", "brisk", "elastic", "editorial"][(seed // 37 + attempt) % 4]
        surface_style = SURFACE_STYLES[(seed // 41 + scene_index + attempt) % len(SURFACE_STYLES)]
        title_placement = ["top-left", "top-right", "side-left", "side-right"][(seed // 43 + attempt) % 4]
        phrases = self._phrases(scene)
        count = max(3, min(5, len(phrases)))
        while len(phrases) < count:
            phrases.append(f"{str(scene.get('title') or 'Key idea')} {len(phrases) + 1}")
        positions = self._positions(layout, count, rng)
        objects = []
        for index in range(count):
            label = _clean_label(phrases[index]) or f"Idea {index + 1}"
            objects.append({
                "id": f"object-{index + 1}",
                "kind": "metric" if re.search(r"\b\d+(?:[.,]\d+)?(?:%|x|×)?\b", label) else "concept",
                "label": label,
                "glyph": grammar["glyphs"][(seed + index * 3 + attempt) % len(grammar["glyphs"])],
                "x": positions[index][0],
                "y": positions[index][1],
                "scale": round(rng.uniform(0.86, 1.14), 3),
                "rotation": round(rng.uniform(-3.8, 3.8), 2),
                "accent": (scene_index + index + seed) % 5,
                "emphasis": "primary" if index == 0 else ("supporting" if index < count - 1 else "outcome"),
            })
        edges = self._edges(semantic_mode, objects, rng)
        actions = self._actions(scene, objects, choreography, tempo, rng)
        illustration_plan = self._illustration_plan(scene, domain, semantic_mode, visual_grammar, objects, actions, scene_index, video_id, illustration_bible, attempt)
        explanation_plan = self._explanation_plan(
            scene, semantic_mode, visual_grammar, illustration_plan["props"],
            video_id, attempt, art_direction,
        )
        recipe = {
            "domain": domain,
            "artDirectionId": art_direction["id"],
            "shapeLanguage": art_direction["shapeLanguage"],
            "motionPhysics": art_direction["motionPhysics"],
            "compositionFamily": composition_family,
            "visualGrammar": visual_grammar,
            "illustrationPlan": illustration_plan,
            "explanationPlan": explanation_plan,
            "semanticMode": semantic_mode,
            "layout": layout,
            "choreography": choreography,
            "camera": [camera_mode, camera_direction],
            "transition": transition,
            "tempo": tempo,
            "surfaceStyle": surface_style,
            "titlePlacement": title_placement,
            "objectCount": count,
            "edgePattern": [edge["from"].split("-")[-1] + edge["to"].split("-")[-1] for edge in edges],
        }
        design_signature = _digest([art_direction["visualDialect"], illustration_bible["signature"], explanation_plan["construction"], explanation_plan["readingOrder"], [relation["label"] for relation in explanation_plan["relations"]], illustration_plan["world"], [prop["kind"] for prop in illustration_plan["props"]]])
        return {
            "version": 5,
            "signature": _digest(recipe),
            "designSignature": design_signature,
            "domainGrammar": f"{domain}:{layout}:{choreography[0]}",
            "artDirectionId": art_direction["id"],
            "shapeLanguage": art_direction["shapeLanguage"],
            "motionPhysics": art_direction["motionPhysics"],
            "compositionFamily": composition_family,
            "visualGrammar": visual_grammar,
            "illustrationPlan": illustration_plan,
            "explanationPlan": explanation_plan,
            "semanticMode": semantic_mode,
            "layout": {"algorithm": layout, "seed": seed % 2_147_483_647},
            "camera": {"mode": camera_mode, "direction": camera_direction, "strength": round(rng.uniform(0.035, 0.095), 3)},
            "transition": {"kind": transition, "direction": camera_direction, "durationSeconds": round(rng.uniform(0.18, 0.34), 3)},
            "tempo": tempo,
            "surfaceStyle": surface_style,
            "titlePlacement": title_placement,
            "objects": objects,
            "edges": edges,
            "actions": actions,
            "renderWindows": self._render_windows(actions),
            "timingSource": "semantic-beats",
        }

    @staticmethod
    def _visual_grammar(
        scene: dict[str, Any],
        semantic_mode: str,
        domain: str,
        scene_index: int,
        video_id: str,
        art_direction: dict[str, Any],
    ) -> dict[str, Any]:
        intent = scene.get("visualIntent") or {}
        scene_type = str(scene.get("type") or "statement").lower()
        text = f"{scene.get('title', '')} {scene.get('body', '')} {scene.get('narration', '')}".lower()
        data_shape = str(intent.get("dataShape") or "").lower()
        if data_shape not in {"sequence", "comparison", "quantity", "network", "hierarchy", "cycle", "spatial", "statement"}:
            data_shape = {
                "sequence": "sequence", "contrast": "comparison", "measurement": "quantity",
                "relationship": "network", "cause-effect": "sequence",
            }.get(semantic_mode, "statement")
        metaphor = _clean_label(str(intent.get("metaphor") or ""), 90)
        if not metaphor:
            metaphor = {
                "study": "an idea being annotated and understood",
                "business": "a signal becoming a decision",
                "gaming": "progress through a changing level",
                "science": "evidence transforming a model",
                "technology": "information moving through a system",
                "health": "a condition moving toward recovery",
                "food": "ingredients transforming through time",
                "nature": "a living system exchanging energy",
                "security": "evidence tracing a threat to containment",
                "general": "an idea changing shape as it becomes clear",
            }[domain]
        mood = _clean_label(str(intent.get("mood") or art_direction.get("name") or "editorial clarity"), 70)
        operators_by_shape = {
            "sequence": ["path", "step", "cascade", "track", "branch"],
            "comparison": ["split", "mirror", "balance", "before-after", "diverge"],
            "quantity": ["scale", "accumulate", "rank", "plot", "radial-measure"],
            "network": ["cluster", "orbit", "flow", "constellation", "nested"],
            "hierarchy": ["tree", "nested", "stack", "funnel", "branch"],
            "cycle": ["orbit", "loop", "ring", "radial-flow", "spiral"],
            "spatial": ["map", "field", "route", "zones", "scatter"],
            "statement": ["focus", "frame", "metaphor", "scale-shift", "assembly"],
        }
        marks_by_shape = {
            "sequence": ["arrow", "path", "node", "number", "label", "icon"],
            "comparison": ["bar", "boundary", "arrow", "circle", "label", "icon"],
            "quantity": ["number", "bar", "line", "dot", "ring", "area"],
            "network": ["node", "line", "arrow", "circle", "pulse", "label"],
            "hierarchy": ["node", "branch", "brace", "label", "container", "icon"],
            "cycle": ["ring", "arc", "arrow", "orbit", "icon", "label"],
            "spatial": ["path", "zone", "dot", "arrow", "label", "boundary"],
            "statement": ["type", "icon", "circle", "underline", "arrow", "highlight"],
        }
        domain_marks = {
            "study": ["page", "underline", "brace", "highlight"],
            "business": ["bar", "slope", "target", "number"],
            "gaming": ["meter", "badge", "path", "burst"],
            "science": ["particle", "wave", "plot", "ring"],
            "technology": ["packet", "trace", "port", "terminal"],
            "health": ["pulse", "cell", "ring", "measure"],
            "food": ["ingredient", "steam", "timer", "measure"],
            "nature": ["leaf", "wave", "root", "particle"],
            "security": ["packet", "boundary", "alert", "stamp"],
            "general": ["circle", "arrow", "path", "highlight"],
        }
        verbs_by_shape = {
            "sequence": ["travels", "draws", "steps", "hands-off", "resolves"],
            "comparison": ["splits", "weighs", "contrasts", "switches", "reconciles"],
            "quantity": ["counts", "grows", "plots", "fills", "locks"],
            "network": ["routes", "connects", "pulses", "fans-out", "converges"],
            "hierarchy": ["branches", "nests", "stacks", "expands", "focuses"],
            "cycle": ["orbits", "circulates", "loops", "returns", "stabilizes"],
            "spatial": ["maps", "traces", "crosses", "clusters", "arrives"],
            "statement": ["reveals", "assembles", "underlines", "transforms", "stamps"],
        }
        seed = int(_digest([video_id, scene.get("id"), scene.get("title"), metaphor, data_shape], 12), 16)
        rng = random.Random(seed)
        operators = operators_by_shape[data_shape]
        primary = operators[seed % len(operators)]
        secondary = operators[(seed // 7 + 2) % len(operators)]
        if secondary == primary:
            secondary = operators[(operators.index(primary) + 1) % len(operators)]
        mark_pool = list(dict.fromkeys([*marks_by_shape[data_shape], *domain_marks[domain]]))
        rng.shuffle(mark_pool)
        mark_count = 5 + seed % 4
        marks = mark_pool[:mark_count]
        verbs = verbs_by_shape[data_shape]
        rhythm = ["punch-build-hold", "draw-cascade-resolve", "reveal-breathe-impact", "trace-focus-release"][seed % 4]
        camera = ["locked", "lateral-follow", "slow-push", "overhead-drift", "focus-pull"][seed // 13 % 5]
        atmosphere = ["ghost-type", "registration-lines", "grain", "field-dots", "contour-lines", "moving-rule"]
        rng.shuffle(atmosphere)
        number_match = re.search(r"\b\d+(?:[.,]\d+)?(?:%|x|×)?\b", text)
        return {
            "version": 2,
            "metaphor": metaphor,
            "mood": mood,
            "dataShape": data_shape,
            "operators": [primary, secondary],
            "marks": marks,
            "motionVerbs": [verbs[(seed + index * 2) % len(verbs)] for index in range(max(5, mark_count))],
            "rhythm": rhythm,
            "cameraBehavior": camera,
            "atmosphere": atmosphere[:2 + seed % 3],
            "metric": number_match.group(0) if number_match else "",
            "sceneType": scene_type,
            "fingerprint": _digest([metaphor, data_shape, primary, secondary, marks, rhythm, camera]),
        }
    @staticmethod
    def _illustration_bible(
        plan: dict[str, Any],
        video_id: str,
        visual_language: dict[str, Any],
        art_direction: dict[str, Any],
    ) -> dict[str, Any]:
        scenes = list(plan.get("scenes") or [])
        domain = str(visual_language.get("domain") or (scenes[0].get("domain") if scenes else "general") or "general").lower()
        if domain not in DOMAIN_ILLUSTRATION_PROPS:
            domain = "general"
        seed = int(_digest([video_id, domain, art_direction.get("id"), [scene.get("title") for scene in scenes]], 12), 16)
        style_by_direction = {
            "editorial-sketch": "editorial-ink", "swiss-signal": "diagrammatic-line",
            "shadow-investigation": "screenprint", "blueprint-systems": "technical-engraving",
            "kinetic-poster": "screenprint", "soft-organic": "soft-gouache",
            "chalk-lesson": "chalk-science", "paper-collage": "cut-paper",
            "retro-terminal": "diagrammatic-line", "folk-diagram": "cut-paper",
            "archival-report": "archival-map", "data-constellation": "technical-engraving",
        }
        style = style_by_direction.get(str(art_direction.get("id") or ""), ILLUSTRATION_STYLES[seed % len(ILLUSTRATION_STYLES)])
        worlds = DOMAIN_ILLUSTRATION_WORLDS[domain]
        base_world = worlds[seed % len(worlds)]
        line_character = ["precise", "warm-rough", "soft", "bold", "fine-technical"][seed // 7 % 5]
        density = ["spacious", "balanced", "rich"][seed // 13 % 3]
        bible = {
            "version": 1, "domain": domain, "style": style, "baseWorld": base_world,
            "lineCharacter": line_character, "density": density,
            "props": DOMAIN_ILLUSTRATION_PROPS[domain],
            "rules": ["one coherent illustrated world per video", "large concrete objects instead of UI cards", "only meaningful objects move", "short labels only", "build, breathe, resolve"],
        }
        bible["signature"] = _digest([domain, style, base_world, line_character, density, seed % 97])
        return bible

    @staticmethod
    def _prop_for_text(text: str, domain: str, fallback_index: int) -> str:
        normalized = text.lower()
        aliases = {
            "email": "email", "message": "email", "phish": "email", "click": "cursor",
            "time": "clock", "minute": "clock", "hour": "clock", "credential": "credential",
            "password": "key", "identity": "fingerprint", "device": "laptop", "computer": "laptop",
            "server": "server", "cloud": "cloud", "protect": "shield", "secure": "shield",
            "block": "gate", "trust": "gate", "database": "database", "data": "database",
            "request": "request", "packet": "packet", "service": "service", "queue": "queue",
            "code": "terminal", "chip": "chip", "book": "book", "learn": "book",
            "memory": "brain", "question": "question", "write": "pencil", "page": "page",
            "experiment": "flask", "chemical": "flask", "molecule": "molecule", "atom": "atom",
            "cell": "cell", "wave": "wave", "measure": "gauge", "heart": "heart",
            "health": "heart", "medicine": "medicine", "recover": "recovery-path",
            "ingredient": "ingredient", "cook": "pan", "heat": "flame", "recipe": "bowl",
            "tree": "tree", "leaf": "leaf", "water": "water-drop", "river": "river",
            "climate": "cloud", "sun": "sun", "root": "root", "game": "controller",
            "player": "player", "level": "level-map", "score": "trophy", "boss": "boss",
            "market": "market-arrow", "money": "coin", "cost": "coin", "risk": "risk-meter",
            "chart": "bar-chart", "target": "target", "customer": "customer", "decision": "scale",
            "person": "person", "people": "person", "document": "document", "result": "result",
        }
        for keyword, prop in aliases.items():
            if keyword in normalized:
                return prop
        pool = DOMAIN_ILLUSTRATION_PROPS.get(domain, DOMAIN_ILLUSTRATION_PROPS["general"])
        return pool[fallback_index % len(pool)]

    @staticmethod
    def _illustration_composition(scene: dict[str, Any], data_shape: str, semantic_mode: str, scene_index: int) -> str:
        scene_type = str(scene.get("type") or "statement").lower()
        if scene_type == "hook": return "chapter-card"
        if scene_type == "closing": return "portrait"
        if scene_type in {"timeline", "process"} or data_shape == "sequence": return "journey" if scene_index % 2 == 0 else "timeline"
        if scene_type in {"metric", "chart"} or data_shape == "quantity": return "measure"
        if scene_type == "comparison" or data_shape == "comparison": return "comparison"
        if data_shape == "cycle": return "cycle"
        if data_shape in {"network", "hierarchy"} or semantic_mode == "relationship": return "cutaway"
        return ["inspection", "workbench", "landscape"][scene_index % 3]

    @staticmethod
    def _takeaway(scene: dict[str, Any]) -> str:
        source = str(scene.get("body") or scene.get("narration") or scene.get("title") or "Key idea")
        sentence = re.split(r"(?<=[.!?])\s+", source.strip())[0]
        words = sentence.strip(" .").split()
        takeaway = " ".join(words[:14]).rstrip(" ,;:")
        return takeaway if len(takeaway) <= 100 else takeaway[:100].rsplit(" ", 1)[0]

    @staticmethod
    def _relation_label(value: str, fallback: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", str(value))
        label = " ".join(words[:3]).strip()
        return label or fallback

    def _explanation_plan(
        self, scene: dict[str, Any], semantic_mode: str, visual_grammar: dict[str, Any],
        props: list[dict[str, Any]], video_id: str, attempt: int,
        art_direction: dict[str, Any],
    ) -> dict[str, Any]:
        intent = scene.get("visualIntent") or {}
        data_shape = str(visual_grammar.get("dataShape") or "statement")
        scene_type = str(scene.get("type") or "statement").lower()
        if scene_type == "hook":
            family = "hook"
        elif scene_type == "closing":
            family = "closing"
        elif scene_type in {"timeline", "process"} or data_shape in {"sequence", "cycle"}:
            family = "sequence"
        elif scene_type == "comparison" or data_shape == "comparison" or semantic_mode == "contrast":
            family = "comparison"
        elif scene_type in {"metric", "chart"} or data_shape == "quantity" or semantic_mode == "measurement":
            family = "measure"
        elif data_shape in {"network", "hierarchy"} or semantic_mode == "relationship":
            family = "network"
        else:
            family = "concept"
        choices = CONSTRUCTION_FAMILIES[family]
        domain = str(scene.get("domain") or "general").lower()
        domain_offset = list(DOMAIN_GRAMMARS).index(domain) if domain in DOMAIN_GRAMMARS else 0
        source_id = str(art_direction.get("sourceDirectionId") or art_direction.get("id") or "editorial-sketch")
        direction_offset = list(ART_DIRECTIONS).index(source_id) if source_id in ART_DIRECTIONS else 0
        scene_offset = int(_digest([scene.get("id"), scene.get("title")], 8), 16)
        selection = int(_digest(video_id, 12), 16) + domain_offset + direction_offset + scene_offset + attempt
        construction = choices[selection % len(choices)]
        action_words = [str(value) for value in intent.get("actions") or [] if str(value).strip()]
        relationship_words = [str(value) for value in intent.get("relationships") or [] if str(value).strip()]
        fallback = {
            "sequence": "then becomes", "contrast": "differs from", "measurement": "changes by",
            "cause-effect": "leads to", "relationship": "connects to", "concept-development": "explains",
        }.get(semantic_mode, "leads to")
        labels = action_words or relationship_words or [fallback]
        reading_order = [str(prop["id"]) for prop in props]
        relations = []
        for index in range(max(0, len(reading_order) - 1)):
            relations.append({
                "id": f"relation-{index + 1}",
                "from": reading_order[index], "to": reading_order[index + 1],
                "label": self._relation_label(labels[index % len(labels)], fallback),
                "startRatio": round(0.20 + index * (0.34 / max(1, len(reading_order) - 1)), 3),
                "endRatio": round(0.44 + index * (0.30 / max(1, len(reading_order) - 1)), 3),
            })
        stages = [
            {"purpose": "context", "startRatio": 0.02, "endRatio": 0.24},
            {"purpose": "mechanism", "startRatio": 0.18, "endRatio": 0.58},
            {"purpose": "consequence", "startRatio": 0.52, "endRatio": 0.80},
            {"purpose": "takeaway", "startRatio": 0.74, "endRatio": 0.98},
        ]
        takeaway = self._takeaway(scene)
        return {
            "version": 1, "family": family, "construction": construction,
            "visualSentence": takeaway, "takeaway": takeaway,
            "readingOrder": reading_order, "relations": relations, "stages": stages,
            "dialect": art_direction.get("visualDialect"),
            "signature": _digest([construction, reading_order, relations, takeaway]),
        }
    def _illustration_plan(
        self, scene: dict[str, Any], domain: str, semantic_mode: str,
        visual_grammar: dict[str, Any], objects: list[dict[str, Any]], actions: list[dict[str, Any]],
        scene_index: int, video_id: str, bible: dict[str, Any], attempt: int,
    ) -> dict[str, Any]:
        intent = scene.get("visualIntent") or {}
        entities = [str(value) for value in intent.get("entities") or [] if str(value).strip()]
        phrases = entities or [str(item.get("label") or "") for item in objects]
        seed = int(_digest([video_id, scene.get("id"), scene.get("title"), phrases, attempt], 12), 16)
        rng = random.Random(seed)
        composition = self._illustration_composition(scene, str(visual_grammar.get("dataShape") or "statement"), semantic_mode, scene_index)
        worlds = DOMAIN_ILLUSTRATION_WORLDS.get(domain, DOMAIN_ILLUSTRATION_WORLDS["general"])
        world = worlds[(worlds.index(bible["baseWorld"]) + scene_index + attempt) % len(worlds)] if bible.get("baseWorld") in worlds else worlds[(seed + scene_index) % len(worlds)]
        count = max(3, min(5, len(objects)))
        labels = list(dict.fromkeys([_clean_label(value, 34) for value in phrases if _clean_label(value, 34)]))
        while len(labels) < count:
            labels.append(_clean_label(str(objects[len(labels) % len(objects)].get("label") or f"Step {len(labels) + 1}"), 34))
        labels = labels[:count]
        if composition in {"journey", "timeline"}:
            positions = [(0.14 + index * (0.72 / max(1, count - 1)), 0.58 + (0.08 if index % 2 else -0.06)) for index in range(count)]
        elif composition == "comparison": positions = [(0.28, 0.48), (0.72, 0.48), (0.5, 0.72), (0.18, 0.72), (0.82, 0.72)][:count]
        elif composition == "cycle": positions = [(0.5 + math.cos(-math.pi / 2 + index * 2 * math.pi / count) * 0.27, 0.52 + math.sin(-math.pi / 2 + index * 2 * math.pi / count) * 0.27) for index in range(count)]
        elif composition == "measure": positions = [(0.28, 0.52), (0.61, 0.62), (0.72, 0.48), (0.83, 0.34), (0.91, 0.23)][:count]
        elif composition == "cutaway": positions = [(0.5, 0.52), (0.2, 0.34), (0.8, 0.34), (0.24, 0.75), (0.76, 0.75)][:count]
        elif composition == "chapter-card": positions = [(0.73, 0.5), (0.86, 0.28), (0.88, 0.72), (0.58, 0.75), (0.58, 0.25)][:count]
        else: positions = [(0.56, 0.52), (0.2, 0.36), (0.82, 0.3), (0.25, 0.74), (0.84, 0.73)][:count]
        props: list[dict[str, Any]] = []
        used_kinds: set[str] = set()
        for index, label in enumerate(labels):
            kind = self._prop_for_text(label, domain, index + scene_index)
            if kind in used_kinds:
                pool = DOMAIN_ILLUSTRATION_PROPS.get(domain, DOMAIN_ILLUSTRATION_PROPS["general"])
                kind = next((candidate for candidate in pool if candidate not in used_kinds), kind)
            used_kinds.add(kind)
            props.append({"id": f"prop-{index + 1}", "kind": kind, "label": label,
                "x": round(positions[index][0], 4), "y": round(positions[index][1], 4),
                "scale": round(1.32 if index == 0 else rng.uniform(0.72, 1.0), 3),
                "role": "hero" if index == 0 else ("outcome" if index == count - 1 else "support"),
                "accent": (seed + index * 3) % 5})
        if composition in {"journey", "timeline"}: event_kinds = ["reveal", "travel", "draw-path", "transform", "resolve"]
        elif composition == "comparison": event_kinds = ["reveal", "split", "weigh", "contrast", "resolve"]
        elif composition == "measure": event_kinds = ["reveal", "count", "grow", "plot", "lock"]
        elif composition == "cycle": event_kinds = ["reveal", "orbit", "transfer", "return", "stabilize"]
        elif composition == "cutaway": event_kinds = ["reveal", "route", "scan", "connect", "resolve"]
        elif composition == "inspection": event_kinds = ["reveal", "scan", "focus", "circle", "resolve"]
        elif composition == "chapter-card": event_kinds = ["draw", "reveal", "settle", "accent", "hold"]
        else: event_kinds = ["reveal", "assemble", "demonstrate", "transform", "resolve"]
        events = []
        for index, prop in enumerate(props):
            action = actions[index % len(actions)] if actions else {}
            events.append({"id": f"event-{index + 1}", "actionId": str(action.get("id") or ""),
                "kind": event_kinds[index % len(event_kinds)], "subjectId": prop["id"],
                "targetId": props[index + 1]["id"] if index + 1 < len(props) else "",
                "startRatio": float(action.get("startRatio") or (0.05 + index * 0.15)),
                "endRatio": float(action.get("endRatio") or min(0.92, 0.18 + index * 0.15))})
        return {"version": 1, "world": world, "style": bible["style"], "composition": composition,
            "layoutVariant": (seed + attempt + scene_index) % 4, "domain": domain,
            "metaphor": visual_grammar.get("metaphor") or "", "heroId": "prop-1", "props": props, "events": events,
            "titleMode": "chapter" if composition == "chapter-card" else ("embedded" if scene_index % 2 else "caption"),
            "chapterNumber": scene_index + 1,
            "signature": _digest([world, composition, [prop["kind"] for prop in props], event_kinds, seed % 101])}
    @staticmethod
    def _composition_family(scene: dict[str, Any], semantic_mode: str, scene_index: int, video_id: str) -> str:
        scene_type = str(scene.get("type") or "statement").lower()
        explicit = {
            "hook": "hero-path",
            "process": "process-path",
            "timeline": "timeline-track",
            "metric": "metric-focus",
            "chart": "metric-focus",
            "comparison": "split-contrast",
            "diagram": "network-trace",
            "grid": "network-trace",
            "quote": "quote-focus",
            "closing": "synthesis",
        }
        if scene_type in explicit:
            return explicit[scene_type]
        families = {
            "sequence": ["process-path", "timeline-track"],
            "contrast": ["split-contrast", "metric-focus"],
            "measurement": ["metric-focus", "network-trace"],
            "cause-effect": ["hero-path", "process-path"],
            "relationship": ["network-trace", "hero-path"],
            "concept-development": ["hero-path", "network-trace", "metric-focus", "synthesis"],
        }
        options = families.get(semantic_mode, families["concept-development"])
        seed = int(_digest([video_id, scene.get("id"), scene.get("title"), scene_type], 8), 16)
        return options[(seed + scene_index) % len(options)]
    @staticmethod
    def _semantic_mode(scene: dict[str, Any]) -> str:
        scene_type = str(scene.get("type") or "statement").lower()
        text = f"{scene.get('title', '')} {scene.get('body', '')}".lower()
        if scene_type in {"process", "timeline"}:
            return "sequence"
        if scene_type == "comparison":
            return "contrast"
        if scene_type in {"metric", "chart"}:
            return "measurement"
        if re.search(r"\b(cause|because|leads to|results in|therefore|effect)\b", text):
            return "cause-effect"
        if re.search(r"\b(connect|network|relationship|depends|system)\b", text):
            return "relationship"
        return "concept-development"

    @staticmethod
    def _phrases(scene: dict[str, Any]) -> list[str]:
        intent = scene.get("visualIntent") or {}
        values: list[str] = []
        for key in ("entities", "actions", "relationships"):
            raw = intent.get(key) or []
            if isinstance(raw, list):
                values.extend(str(item) for item in raw if str(item).strip())
        if not values:
            values.extend(str(beat.get("text") or "") for beat in scene.get("visualBeats") or [])
        if len(values) < 3:
            values.extend(re.split(r"(?<=[.!?;:])\s+|,\s+|\b(?:then|while|because|but)\b", str(scene.get("body") or scene.get("narration") or ""), flags=re.IGNORECASE))
        values.insert(0, str(scene.get("title") or "Key idea"))
        cleaned = [_clean_label(value) for value in values]
        unique: list[str] = []
        for value in cleaned:
            if not value:
                continue
            candidate_tokens = set(re.findall(r"[a-z0-9]+", value.lower()))
            is_near_duplicate = False
            for item in unique:
                item_tokens = set(re.findall(r"[a-z0-9]+", item.lower()))
                smaller = min(len(candidate_tokens), len(item_tokens))
                if smaller and len(candidate_tokens & item_tokens) / smaller >= 0.75:
                    is_near_duplicate = True
                    break
            if not is_near_duplicate:
                unique.append(value)
        return unique[:5]

    @staticmethod
    def _positions(layout: str, count: int, rng: random.Random) -> list[tuple[float, float]]:
        if any(token in layout for token in ("orbit", "rings", "cycle", "spiral", "ripple", "arena")):
            positions = [(0.5, 0.5)]
            radius = 0.27
            for index in range(1, count):
                angle = -math.pi / 2 + (index - 1) * (2 * math.pi / max(1, count - 1)) + rng.uniform(-0.12, 0.12)
                positions.append((0.5 + math.cos(angle) * radius, 0.52 + math.sin(angle) * radius))
        elif any(token in layout for token in ("split", "quadrants", "boundaries", "before-after", "hypothesis")):
            base = [(0.24, 0.34), (0.76, 0.34), (0.24, 0.68), (0.76, 0.68), (0.5, 0.52)]
            positions = base[:count]
        elif any(token in layout for token in ("ladder", "staircase", "layers", "waterfall", "timeline", "path", "route", "pipeline", "chain")):
            positions = [(0.14 + index * (0.72 / max(1, count - 1)), 0.3 + (index % 2) * 0.34) for index in range(count)]
        elif any(token in layout for token in ("branch", "tree", "funnel", "fan")):
            base = [(0.5, 0.22), (0.25, 0.5), (0.75, 0.5), (0.18, 0.78), (0.82, 0.78)]
            positions = base[:count]
        else:
            base = [(0.18, 0.34), (0.5, 0.24), (0.82, 0.38), (0.34, 0.72), (0.7, 0.72)]
            positions = base[:count]
        return [
            (round(max(0.1, min(0.9, x + rng.uniform(-0.025, 0.025))), 4), round(max(0.18, min(0.84, y + rng.uniform(-0.025, 0.025))), 4))
            for x, y in positions
        ]

    @staticmethod
    def _edges(mode: str, objects: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        if mode in {"sequence", "cause-effect", "measurement"}:
            pairs = list(zip(objects, objects[1:]))
        elif mode == "contrast":
            pairs = [(objects[0], item) for item in objects[1:]]
        else:
            center = objects[rng.randrange(len(objects))]
            pairs = [(center, item) for item in objects if item is not center]
        for index, (start, end) in enumerate(pairs):
            edges.append({
                "id": f"edge-{index + 1}",
                "from": start["id"],
                "to": end["id"],
                "style": ["ink", "dashed", "double", "marker"][index % 4],
                "accent": int(end["accent"]),
            })
        return edges

    @staticmethod
    def _actions(
        scene: dict[str, Any],
        objects: list[dict[str, Any]],
        choreography: list[str],
        tempo: str,
        rng: random.Random,
    ) -> list[dict[str, Any]]:
        beats = scene.get("visualBeats") or []
        actions: list[dict[str, Any]] = []
        speed = {"brisk": 0.075, "elastic": 0.13, "editorial": 0.16, "measured": 0.19}[tempo]
        total_actions = max(len(objects), len(choreography))
        for index in range(total_actions):
            target = objects[index % len(objects)]
            if index < len(beats):
                start = float(beats[index].get("startRatio") or 0)
            else:
                start = 0.06 + index * (0.68 / max(1, total_actions - 1))
            start = max(0.025, min(0.88, start + rng.uniform(-0.018, 0.018)))
            kind = choreography[index % len(choreography)]
            actions.append({
                "id": f"action-{index + 1}",
                "kind": kind,
                "targetId": target["id"],
                "cue": _cue(target["label"]),
                "startRatio": round(start, 4),
                "endRatio": round(min(0.97, start + speed + rng.uniform(-0.018, 0.025)), 4),
                "direction": DIRECTIONS[rng.randrange(len(DIRECTIONS))],
                "intensity": round(rng.uniform(0.72, 1.0), 3),
            })
        return sorted(actions, key=lambda action: action["startRatio"])

    @staticmethod
    def _render_windows(actions: list[dict[str, Any]]) -> list[dict[str, float]]:
        raw = sorted(
            (
                max(0.0, float(action.get("startRatio") or 0) - 0.025),
                min(0.995, float(action.get("endRatio") or 0) + 0.035),
            )
            for action in actions
        )
        merged: list[list[float]] = []
        for start, end in raw:
            if merged and start <= merged[-1][1] + 0.025:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, max(start + 0.055, end)])
        return [
            {"startRatio": round(start, 4), "endRatio": round(min(0.995, end), 4)}
            for start, end in merged[:5]
        ]
