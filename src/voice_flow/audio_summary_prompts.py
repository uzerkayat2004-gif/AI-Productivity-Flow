"""Spoken Explanation Prompts for Audio Flow Summarization.

Builds prompts tailored specifically for text-to-speech audio narration.
Outputs clean prose ready for TTS without markdown, bullets, or visual symbols.
Semantic coverage targets:
  - Short: Essential understanding and top conclusions only.
  - Balanced: All major ideas and important supporting context.
  - Detailed: Thorough spoken summary covering reasoning, numbers, conditions, caveats, and relationships.
"""

from __future__ import annotations

import re

AUDIO_SUMMARY_SYSTEM_PROMPT = """You are an expert audio narrator and plain-language explainer.
Your job is to convert the user's source text into a natural, engaging spoken explanation designed to be heard out loud via text-to-speech.

CRITICAL AUDIO NARRATION RULES:
1. OUTPUT ONLY CLEAN NARRATION PROSE. Absolutely NO markdown headers (#), NO bolding (**), NO italics (*), NO bullet points (- or *), NO numbered lists, NO tables, and NO ASCII diagrams.
2. NO VISUAL OR CITATION MARKERS. Do NOT include URLs, bracketed citations like [1], footnote markers, or inline code blocks.
3. NATURAL SPOKEN STYLE. Write as a knowledgeable person naturally explaining the material to a listener. Use complete, grammatically smooth sentences and natural, varied transitions suited for listening out loud. Do not repeat canned phrases.
4. FAITHFUL TO SOURCE. Strictly constrain narration to facts supported by the source text. Do NOT invent outside facts, unsupported implications, or unstated conclusions. Preserve important names, exact numbers, financial figures, dates, conditions, caveats, warnings, and attributions.
5. ADAPT TO DOCUMENT TYPE:
   - Technical / Educational: Explain concepts and relationships clearly in prose.
   - Business / Reports: Explain findings, key numbers, causes, and major conclusions.
   - Instructions / Process: Preserve the sequence of steps naturally in spoken language.
   - Policy / Legal: Preserve obligations, conditions, limitations, exceptions, and distinctions.
   - Data-Heavy: Explain meaningful trends and key numbers without listing every raw figure.

DEPTH GUIDELINES (adapt narration depth to source size and complexity):
- Short: Create a concise spoken summary focusing on the essential central idea and top conclusions only. Omit minor supporting details and secondary context.
- Balanced: Create a balanced spoken summary covering all major ideas in the source and the important supporting context required to understand those ideas. Preserve meaningful facts, relationships, conclusions, conditions, and caveats. For a multi-section source, do not reduce the entire document to only a few sentences.
- Detailed: Create a thorough spoken summary covering all major ideas and important sections. Preserve relevant reasoning, explanations, examples, facts, numbers, dates, conditions, caveats, warnings, exceptions, relationships, and conclusions while remaining a summary.
(Let narration length adapt naturally to the source size and complexity. Do not stretch short texts unnaturally; do not over-compress long documents.)
"""


def build_audio_summary_prompt(source_text: str, depth: str = "balanced") -> str:
    """Construct a full prompt for spoken explanation generation."""
    raw_depth = (depth or "balanced").lower().strip()
    depth_aliases = {
        "quick": "short",
        "short": "short",
        "standard": "balanced",
        "balanced": "balanced",
        "detailed": "detailed",
    }
    clean_depth = depth_aliases.get(raw_depth, "balanced")

    depth_instructions = {
        "short": "Provide a short, concise spoken summary focusing only on the essential central idea and top conclusions.",
        "balanced": "Provide a balanced spoken summary covering all major ideas and the important supporting context required to understand them.",
        "detailed": "Provide a thorough spoken summary covering all major ideas, key reasoning, examples, numbers, conditions, caveats, and conclusions.",
    }

    instruction = depth_instructions[clean_depth]

    return f"""{AUDIO_SUMMARY_SYSTEM_PROMPT}

TARGET DEPTH: {clean_depth.upper()}
{instruction}

SOURCE TEXT:
{source_text.strip()}
"""


def sanitize_narration_text(raw_text: str) -> str:
    """Clean harmless formatting artifacts without destructive regex transformations."""
    if not raw_text:
        return ""
    text = raw_text.strip()
    # Strip markdown code block wrappers if present
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    # Remove markdown headers (#, ##, ###)
    text = re.sub(r"^[#]+\s*", "", text, flags=re.MULTILINE)
    # Remove bold/italics syntax
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # Convert list bullet lines to natural sentence flow
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Collapse excess whitespace/newlines into paragraph flow
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
