"""Data models and preset definitions for the Context-Aware Style System."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WritingStyle = Literal["formal", "casual", "very_casual", "excited"]
StyleCategory = Literal["personal", "work", "email", "developer", "other"]
CleanupStrength = Literal["cleanup_none", "cleanup_light", "cleanup_medium", "cleanup_high"]


@dataclass(frozen=True)
class StyleConfig:
    """Detailed deterministic configuration for a Writing Style."""
    id: WritingStyle
    name: str
    description: str
    capitalization: Literal["normal", "minimal"] = "normal"
    punctuation_density: Literal["minimal", "light", "normal", "expressive"] = "normal"
    sentence_periods: Literal["minimal", "normal"] = "normal"
    exclamation_level: Literal["none", "natural", "expressive"] = "natural"
    capitalize_pronoun_i: bool = True
    allow_lowercase_first_letter: bool = False
    preserve_acronyms: bool = True
    preserve_urls_emails: bool = True
    preserve_code_tokens: bool = True
    preserve_numbers_currencies: bool = True
    example_output: str = ""


@dataclass(frozen=True)
class TextboxContext:
    """Bounded, privacy-conscious snapshot of text around the insertion point."""
    before: str = ""
    selection: str = ""
    after: str = ""
    trustworthy: bool = False


@dataclass(frozen=True)
class AppClassification:
    """Mapping from an active application or web domain to a Style category."""
    app_identifier: str
    category: StyleCategory
    domain: str | None = None
    is_user_override: bool = False


@dataclass(frozen=True)
class ActiveStyleResolution:
    """Complete resolution payload for a dictation session."""
    app_name: str
    category: StyleCategory
    category_style: WritingStyle
    temporary_override: WritingStyle | None
    resolved_style: WritingStyle
    domain: str | None = None
    config: StyleConfig = field(default_factory=lambda: FORMAL_STYLE_CONFIG)


# Canonical Style Configurations
FORMAL_STYLE_CONFIG = StyleConfig(
    id="formal",
    name="Formal",
    description="Standard capitalization, natural commas, and complete sentence-ending punctuation. Professional and polished.",
    capitalization="normal",
    punctuation_density="normal",
    sentence_periods="normal",
    exclamation_level="natural",
    capitalize_pronoun_i=True,
    allow_lowercase_first_letter=False,
    example_output="Hey Sarah, just wanted to check if you received the document. Let me know when you get a chance.",
)

CASUAL_STYLE_CONFIG = StyleConfig(
    id="casual",
    name="Casual",
    description="Normal capitalization with lighter punctuation. Omits unnecessary periods on conversational fragments.",
    capitalization="normal",
    punctuation_density="light",
    sentence_periods="minimal",
    exclamation_level="natural",
    capitalize_pronoun_i=True,
    allow_lowercase_first_letter=False,
    example_output="Hey are you free later? We can grab coffee if you want",
)

VERY_CASUAL_STYLE_CONFIG = StyleConfig(
    id="very_casual",
    name="Very Casual",
    description="Minimal punctuation and lowercase sentence beginnings. Loose, quick message feel for chat.",
    capitalization="minimal",
    punctuation_density="minimal",
    sentence_periods="minimal",
    exclamation_level="natural",
    capitalize_pronoun_i=False,
    allow_lowercase_first_letter=True,
    example_output="hey are you coming tonight let me know",
)

EXCITED_STYLE_CONFIG = StyleConfig(
    id="excited",
    name="Excited",
    description="Expressive punctuation with enthusiastic exclamation marks on positive sentence boundaries. Never spams.",
    capitalization="normal",
    punctuation_density="light",
    sentence_periods="minimal",
    exclamation_level="expressive",
    capitalize_pronoun_i=True,
    allow_lowercase_first_letter=False,
    example_output="That's amazing! Congrats! I'm really happy for you!",
)

STYLE_CONFIGS: dict[WritingStyle, StyleConfig] = {
    "formal": FORMAL_STYLE_CONFIG,
    "casual": CASUAL_STYLE_CONFIG,
    "very_casual": VERY_CASUAL_STYLE_CONFIG,
    "excited": EXCITED_STYLE_CONFIG,
}

# Default category mappings
DEFAULT_CATEGORY_STYLES: dict[StyleCategory, WritingStyle] = {
    "personal": "casual",
    "work": "casual",
    "email": "formal",
    "developer": "casual",
    "other": "casual",
}
