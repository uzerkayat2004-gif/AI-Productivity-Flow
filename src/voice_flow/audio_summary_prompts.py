"""Spoken Explanation Prompts for Audio Flow Summarization.

Builds prompts tailored specifically for text-to-speech audio narration.
Outputs clean, audio-first prose ready for TTS without markdown, bullets, visual symbols, or visual idioms.

Semantic coverage targets:
  - Quick / Short (quick, short): Extract the single most important takeaway from each
    major section, adapting summary length to cover all core key points without omitting
    important sections, while cutting out background preamble, methodology, and filler.
  - Standard / Medium (standard, medium, balanced): Balanced narrative covering all major
    sections, their supporting mechanisms, and key outcomes proportionally to the document's length.
  - Detailed / Long (detailed, long): Comprehensive, section-by-section spoken walkthrough
    preserving all specific numbers, data, conditions, caveats, and conclusions proportionally
    to the document's depth.
"""

from __future__ import annotations

import re

AUDIO_SUMMARY_SYSTEM_PROMPT = """You are an expert audio narrator and spoken-word explainer.
Your mission is to transform the user's source text into natural, compelling spoken audio prose designed to be heard through text-to-speech earphones or speakers.

CRITICAL SPOKEN AUDIO RULES:
1. AUDIO-FIRST, NATURAL SPOKEN PROSE. Write exactly as a clear, articulate person would speak to a listener. Use natural, conversational cadence, varied transitions, and clean spoken rhythm. Avoid robotic phrasing, stilted lists, or breathless run-on sentences.
2. ZERO MARKDOWN FORMATTING. The text-to-speech engine must read clean sentences only. Output ABSOLUTELY NO markdown headers (#), NO bolding (**), NO italics (* or _), NO strikethrough (~~), NO inline code or backticks (`), NO code blocks (```), NO bullet points (- or *), NO numbered lists, NO tables, and NO ASCII diagrams.
3. SPOKEN WORDS FOR SYMBOLS. Never output raw visual symbols that confuse speech synthesizers. Always expand symbols into full spoken words:
   - Expand "%" to "percent" (for example, write "twenty-five percent" or "25 percent", never "25%").
   - Expand "$" to "dollars" (for example, write "50 dollars" or "100 million dollars", never "$50" or "$100M").
   - Expand "&" to "and".
   - Expand "+" to "plus" (for example, "10 plus", not "10+").
   - Expand "@" to "at".
   - Expand "°" to "degrees" or "degrees Celsius/Fahrenheit".
   - Spell out abbreviations: write "with" instead of "w/", "without" instead of "w/o", "for example" instead of "e.g.", "that is" instead of "i.e.", and "and so on" instead of "etc.".
4. NO VISUAL OR SPATIAL IDIOMS. The listener is listening with their ears and cannot see any screen, page, or diagram. Absolutely NEVER use visual phrases such as:
   - "as shown in the diagram" or "as seen in the chart"
   - "in the table below" or "in the figure above"
   - "click here", "tap here", or "refer to the graphic"
   - "as pictured here" or "as outlined below".
   Translate all key ideas into direct, descriptive spoken explanations.
5. NO CITATIONS OR LINK ARTIFACTS. Do NOT include bracketed citation numbers like [1] or [2], footnote indicators, parenthetical academic author-date citations like (Smith, 2023), or raw URLs.
6. STRICT FACTUAL FIDELITY. Ground every spoken point strictly in the facts provided in the source text. Do NOT invent outside facts, ungrounded speculation, or exaggerated claims. Faithfully preserve crucial names, specific numbers, metrics, dates, obligations, caveats, and conclusions.
7. NO ANNOUNCER CHATTER OR BOILERPLATE. Output ONLY the narration itself. Do NOT include introductory greetings, boilerplate meta-commentary, or closing chatter (for example, never say "Here is a quick summary:", "In summary,", "Sure, here's the explanation:", or "I hope this helps!"). Start immediately with the first spoken sentence.
8. HUMAN EXPLANATORY CADENCE (EXPLAIN, DO NOT JUST READ). Speak as a knowledgeable, articulate person explaining the core ideas directly to a listener, NOT like a robot dryly reading out text. Connect concepts with natural conversational transitions ("The core idea here is...", "Here is how it works:", "What this means in practice is...", "The main trade-off, however, is...", "Looking at the big picture,", "The bottom line is..."). Keep the cadence engaging, conversational, and effortless to understand by ear.
9. NO FIELD LABELS OR BULLET HEADERS. Never output presentation tags, slide headers, or field prefixes like "Key Takeaway:", "Main Mechanism:", "Performance:", "Security:", "Methodology:", or "Conclusion:". Weave all points seamlessly into fluent, spoken sentences with natural conversational transitions ("On the performance side...", "When looking at the architecture...", "The main trade-off is...").
10. GROUNDED TOPIC ANCHORING. Always begin the audio explanation by establishing the document's central subject matter so the listener immediately understands what is being explained. Never open with dangling pronouns, isolated metrics, or disconnected data points.

ADAPTIVE DEPTH GUIDELINES:
- QUICK / SHORT: Extract the single most important takeaway from each major section. Adapt summary length to cover all core key points without omitting important sections, while cutting out all background preamble, methodology, and filler. Ensure every crucial finding is heard, but keep it as concise as possible.
- STANDARD / MEDIUM / BALANCED: Provide a balanced narrative covering all major sections, their supporting mechanisms, and the key outcomes proportionally to the document's length. Give each important section its appropriate coverage.
- DETAILED / LONG: Provide a comprehensive, section-by-section spoken walkthrough preserving all specific numbers, data, conditions, caveats, and conclusions proportionally to the document's depth.
"""

DEPTH_CONFIGS = {
    "short": {
        "label": "SHORT",
        "name": "Quick / Short Summary",
        "drafting_rule": (
            "DRAFTING RULE: Extract the single most important takeaway from each major section. "
            "Adapt summary length to cover all core key points without omitting important sections, "
            "while cutting out all background preamble, methodology, and filler. "
            "Ensure every crucial finding is heard, but keep it as concise as possible."
        ),
        "instruction": (
            "Extract the single most important takeaway from each major section. "
            "Adapt summary length to cover all core key points without omitting important sections, "
            "while cutting out all background preamble, methodology, and filler. "
            "Ensure every crucial finding is heard, but keep it as concise as possible."
        ),
    },
    "balanced": {
        "label": "BALANCED",
        "name": "Standard / Medium Summary",
        "drafting_rule": (
            "DRAFTING RULE: Provide a balanced narrative covering all major sections, their supporting mechanisms, "
            "and the key outcomes proportionally to the document's length. "
            "Give each important section its appropriate coverage."
        ),
        "instruction": (
            "Provide a balanced narrative covering all major sections, their supporting mechanisms, "
            "and the key outcomes proportionally to the document's length. "
            "Give each important section its appropriate coverage."
        ),
    },
    "detailed": {
        "label": "DETAILED",
        "name": "Detailed / Long Summary",
        "drafting_rule": (
            "DRAFTING RULE: Provide a comprehensive, section-by-section spoken walkthrough preserving all specific numbers, "
            "data, conditions, caveats, and conclusions proportionally to the document's depth."
        ),
        "instruction": (
            "Provide a comprehensive, section-by-section spoken walkthrough preserving all specific numbers, "
            "data, conditions, caveats, and conclusions proportionally to the document's depth."
        ),
    },
}


def build_audio_summary_prompt(source_text: str, depth: str = "balanced") -> str:
    """Construct a full prompt for spoken explanation generation with adaptive scale, sentence budgeting, and audio constraints."""
    raw_depth = (depth or "balanced").lower().strip()
    depth_aliases = {
        "quick": "short",
        "short": "short",
        "standard": "balanced",
        "medium": "balanced",
        "balanced": "balanced",
        "detailed": "detailed",
        "long": "detailed",
    }
    clean_depth = depth_aliases.get(raw_depth, "balanced")
    config = DEPTH_CONFIGS[clean_depth]

    words = len(re.findall(r'\b\w+\b', source_text))
    paragraphs = len([p for p in source_text.split('\n\n') if p.strip()])
    estimated_pages = max(1, round(words / 350))

    # Calculate explicit sentence and word budgets tailored to document scale & depth
    if clean_depth == "short":
        if estimated_pages <= 1:
            budget_sents = "2 to 3"
            budget_words = "35 to 65"
        elif estimated_pages <= 4:
            budget_sents = "3 to 4"
            budget_words = "65 to 110"
        else:
            budget_sents = "4 to 6"
            budget_words = "90 to 160"
    elif clean_depth == "detailed":
        if estimated_pages <= 1:
            budget_sents = "6 to 9"
            budget_words = "130 to 220"
        elif estimated_pages <= 4:
            budget_sents = "12 to 20"
            budget_words = "250 to 450"
        else:
            budget_sents = "25 to 40"
            budget_words = "600 to 880"
    else:  # balanced / standard
        if estimated_pages <= 1:
            budget_sents = "3 to 5"
            budget_words = "70 to 125"
        elif estimated_pages <= 4:
            budget_sents = "6 to 10"
            budget_words = "130 to 220"
        else:
            budget_sents = "12 to 18"
            budget_words = "250 to 380"

    return f"""{AUDIO_SUMMARY_SYSTEM_PROMPT}

TARGET DEPTH: {config['label']} ({config['name']})
SOURCE SCALE: Approximately {estimated_pages} page(s) ({words} words across {paragraphs} sections).
{config['drafting_rule']}
SENTENCE BUDGET: Aim for approximately {budget_sents} spoken explanation sentences (around {budget_words} words).
SECTION COVERAGE: For multi-section and multi-page articles, ensure coverage is distributed across the entire document from the opening thesis through the middle mechanisms to the final conclusion.
STYLE: Spoken prose only, no markdown, no symbols (use spoken words like 'percent', 'dollars').

SOURCE TEXT:
{source_text.strip()}
"""


def sanitize_narration_text(raw_text: str) -> str:
    """Clean formatting artifacts, symbols, and visual idioms for spoken audio."""
    if not raw_text:
        return ""
    text = raw_text.strip()

    # 1. Strip markdown code block wrappers if present
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", text)
        text = re.sub(r"\n?\s*```$", "", text).strip()

    # 2. Strip conversational intro / announcer boilerplate if generated by LLM
    intro_patterns = [
        r"^(?:Sure,?\s*)?Here(?:'s|\s+is)\s+(?:a\s+|the\s+|your\s+)?(?:quick|short|standard|medium|balanced|detailed|long|spoken|audio)?\s*(?:summary|explanation|walkthrough)?\s*:\s*",
        r"^(?:Quick|Short|Standard|Medium|Balanced|Detailed|Long|Spoken|Audio)?\s*Summary:\s*",
        r"^In\s+summary,\s*",
        r"^(?:Certainly|Sure|Okay|Alright|Of course),?\s*(?:here(?:'s|\s+is)\s+.*?:)?\s*",
        r"^(?:In\s+this\s+(?:article|document|report|text|paper),\s+(?:the\s+author\s+explains|we\s+explore|we\s+see|it\s+discusses|the\s+focus\s+is\s+on))\s*",
        r"^Here(?:'s|\s+is)\s+(?:what\s+you\s+need\s+to\s+know|a\s+breakdown|an\s+explanation|the\s+overview)(?:\s+of\s+.*?)?:\s*",
        r"^Let(?:'s|\s+us)\s+(?:dive\s+in|break\s+this\s+down|look\s+at\s+this):\s*",
    ]
    for ip in intro_patterns:
        text = re.sub(ip, "", text, flags=re.IGNORECASE | re.MULTILINE)

    # 3. Strip closing conversational chatter if generated by LLM
    closing_patterns = [
        r"\s*(?:I\s+)?hope\s+this\s+(?:helps|explanation\s+helps|summary\s+helps)[\.!]?\s*$",
        r"\s*Let\s+me\s+know\s+if\s+you\s+(?:have\s+any\s+questions|need\s+anything\s+else)[\.!]?\s*$",
        r"\s*Feel\s+free\s+to\s+ask\s+if\s+you\s+have\s+any\s+questions[\.!]?\s*$",
    ]
    for cp in closing_patterns:
        text = re.sub(cp, "", text, flags=re.IGNORECASE)

    # 3b. Strip presentation field labels (e.g. "Key Takeaway:", "Main Mechanism:", "Performance:", "Security:")
    field_label_pattern = (
        r"(?:^|(?<=[\.\?!]\s)|(?<=\n))\s*(?:\*\*)?(?:"
        r"Key Takeaways?|Main Takeaways?|Core Takeaways?|Primary Takeaways?|Takeaways?|"
        r"Core Idea|Overview|Background|Architecture|Performance|Security|"
        r"Main Mechanism|Mechanism|Methodology|Key Findings?|Findings?|"
        r"The Bottom Line|Bottom Line|Main Point|Core Insight"
        r")(?:\*\*)?:\s*"
    )
    text = re.sub(field_label_pattern, "", text, flags=re.IGNORECASE)

    # 4. Remove markdown headers (#, ##, ###)
    text = re.sub(r"^[#]+\s*", "", text, flags=re.MULTILINE)

    # 5. Remove blockquotes
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)

    # 6. Remove bold, italics, strikethrough syntax
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)

    # 7. Remove inline backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 8. Convert list bullets and numbered list lines to natural sentence flow
    text = re.sub(r"^\s*[-*+•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+[\.\)]\s+", "", text, flags=re.MULTILINE)

    # 9. Remove markdown links and standalone URLs
    text = re.sub(r"\[([^\]]+)\]\((?:https?://[^\)]+|[^\)]+)\)", r"\1", text)
    text = re.sub(r"<https?://[^>]+>", "", text)
    text = re.sub(r"https?://\S+", "", text)

    # 10. Remove visual / diagram / UI references
    visual_patterns = [
        r"\b(?:as\s+(?:shown|seen|illustrated|indicated|depicted|pictured)\s+(?:in\s+the\s+(?:diagram|chart|table|figure|image|graphic|graph|screenshot)(?:\s+(?:below|above))?|below|above))\b,?\s*",
        r"\b(?:in\s+the\s+(?:table|diagram|chart|figure|image|graphic|graph)\s+(?:below|above))\b,?\s*",
        r"\b(?:see\s+(?:the\s+)?(?:table|chart|diagram|figure|image|graphic)\s*(?:below|above)?)\b,?\s*",
        r"\b(?:refer\s+to\s+(?:the\s+)?(?:table|chart|diagram|figure|image|graphic)\s*(?:below|above)?)\b,?\s*",
        r"\bclick\s+here\b,?\s*",
        r"\b(?:as\s+(?:described|noted)\s+(?:below|above))\b,?\s*",
    ]
    for vp in visual_patterns:
        text = re.sub(vp, "", text, flags=re.IGNORECASE)

    # 11. Expand spoken symbols to natural spoken words
    # Numeric ranges: 800-2400 -> 800 to 2400, 10–20 -> 10 to 20
    text = re.sub(r"\b(\d+)\s*[-–—]\s*(\d+)\b", r"\1 to \2", text)

    # Currency ($)
    suffix_map = {"k": "thousand", "m": "million", "b": "billion", "t": "trillion"}
    text = re.sub(
        r"\$([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*([KkMmBbTt])\b",
        lambda m: f"{m.group(1)} {suffix_map[m.group(2).lower()]} dollars",
        text,
    )
    text = re.sub(
        r"\$([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(trillion|billion|million|thousand)\b",
        r"\1 \2 dollars",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\$1(?:\.00)?(?!\d)", "1 dollar", text)
    text = re.sub(r"\$([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)", r"\1 dollars", text)
    text = re.sub(r"\$", " dollars ", text)

    # Percentage (%)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1 percent", text)
    text = re.sub(r"%", " percent", text)

    # Ampersand (&)
    text = re.sub(r"\s*&\s*", " and ", text)

    # Mathematical / unit symbols
    text = re.sub(r"(\d+)\s*\+", r"\1 plus", text)
    text = re.sub(r"\s+@\s+", " at ", text)
    text = re.sub(r"(\d+)\s*°\s*[Cc]\b", r"\1 degrees Celsius", text)
    text = re.sub(r"(\d+)\s*°\s*[Ff]\b", r"\1 degrees Fahrenheit", text)
    text = re.sub(r"(\d+)\s*°", r"\1 degrees", text)
    text = re.sub(r"°", " degrees ", text)

    # Fractions
    text = re.sub(r"\b1/2\b", "one half", text)
    text = re.sub(r"\b1/4\b", "one quarter", text)
    text = re.sub(r"\b3/4\b", "three quarters", text)

    # Units
    text = re.sub(r"(\d+(?:\.\d+)?)\s*km/h\b", r"\1 kilometers per hour", text, flags=re.IGNORECASE)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*mph\b", r"\1 miles per hour", text, flags=re.IGNORECASE)

    # Common written abbreviations to spoken prose (handle w/o before w/)
    text = re.sub(r"(?:^|\s)w/o(?:\s|$)", " without ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:^|\s)w/(?:\s|$)", " with ", text, flags=re.IGNORECASE)
    text = re.sub(r"\be\.g\.,?\s*", "for example, ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bi\.e\.,?\s*", "that is, ", text, flags=re.IGNORECASE)
    text = re.sub(r"\betc\.\b", "and so on", text, flags=re.IGNORECASE)
    text = re.sub(r"\bapprox\.\s*", "approximately ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bavg\.\s*", "average ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmin\.\s*(?=\d|\b)", "minutes ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsec\.\s*(?=\d|\b)", "seconds ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:hrs?|hr)\.\s*(?=\d|\b)", "hours ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:yrs?|yr)\.\s*(?=\d|\b)", "years ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bvs\.\s*", "versus ", text, flags=re.IGNORECASE)

    # 12. Normalize punctuation and collapse excess whitespace
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ", ", text)
    text = re.sub(r",\s*\.", ".", text)
    text = re.sub(r"^\s*,\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Capitalize after sentence-ending punctuation or at start
    text = re.sub(r"([\.\?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text

