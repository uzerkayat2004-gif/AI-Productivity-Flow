"""Conservative, deterministic formatting for dictated text."""
from __future__ import annotations

from dataclasses import dataclass
import re
from voice_flow.style_formatter import style_formatter
from voice_flow.style_models import TextboxContext


@dataclass(frozen=True)
class FormattingResult:
    text: str
    press_enter: bool = False


_MENTION_CONTEXT = re.compile(
    r"\b(?:do not(?:\s+ever)?|don't(?:\s+ever)?|never(?:\s+ever)?|"
    r"say|the words?|literal(?:ly)?|phrase)\s*$",
    re.I,
)


def split_press_enter(text: str, enabled: bool) -> FormattingResult:
    """Extract only an unambiguous trailing action, before cleanup/dictionary."""
    text = text.strip()
    if not enabled or not re.search(r"\bpress enter(?:\s*[.!?]+)?$", text, re.I):
        return FormattingResult(text)
    prefix = re.sub(r"\bpress enter(?:\s*[.!?]+)?$", "", text, flags=re.I).rstrip()
    if _MENTION_CONTEXT.search(prefix) or re.search(r"\b(?:write|type)\s+the\s+(?:words?|phrase)\s*$", prefix, re.I):
        return FormattingResult(text)
    prefix = re.sub(r"\s+and$", "", prefix, flags=re.I).rstrip()
    return FormattingResult(prefix, True)


def apply_spoken_punctuation(text: str) -> str:
    """Convert explicit spoken punctuation without changing ordinary wording."""
    return _spoken_punctuation(text)


def cleanup_text(text: str, level: str) -> str:
    """Independent Cleanup layer: handles spoken fillers and hesitation disfluencies."""
    text = text.strip()
    if level == "cleanup_none":
        return text
    text = re.sub(r"\b(?:um|uh|er|ah|hmm)\b[ ,]*", "", text, flags=re.I)
    text = re.sub(r"(?:^|,)\s*you know\s*(?=,|$)", lambda m: "," if m.group(0).startswith(",") else "", text, flags=re.I)
    for pattern, replacement in (
        (r"\blet's meet at\s+([^,.]+?)\s+(?:actually|no wait|wait no)\s+([^,.]+)", r"let's meet at \2"),
        (r"\bsend it\s+([^,.]+?)\s+(?:scratch that|actually)\s+([^,.]+)", r"send it \2"),
        (r"\bmy code is\s+([^,.]+?)\s+(?:no wait|wait no|actually)\s+([^,.]+)", r"my code is \2"),
    ):
        text = re.sub(pattern, replacement, text, flags=re.I)
    if level in ("cleanup_medium", "cleanup_high"):
        text = re.sub(r"\b(\w+(?:\s+\w+){0,5})\s+(?:I mean|rather),?\s+\1\b", r"\1", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _spoken_punctuation(text: str) -> str:
    protected = re.split(r"(https?://\S+|\b\S+@\S+\b)", text)
    for i in range(0, len(protected), 2):
        part = protected[i]
        part = re.sub(r"\bnew paragraph\b", "\n\n", part, flags=re.I)
        part = re.sub(r"\b(?:new line|next line|line break)\b", "\n", part, flags=re.I)
        part = re.sub(r"[ \t]*\n[ \t]*", "\n", part)
        protected_terms = r"(?:character|symbol|key|operator|delimiter|term|word)"
        part = re.sub(rf"\b(?:comma|period|colon|semicolon|hash|question mark|exclamation mark)\s+{protected_terms}\b", lambda m: "__" + m.group(0).replace(" ", "_") + "__", part, flags=re.I)
        part = re.sub(r"\b(?:the\s+word\s+comma|a\s+period\s+is\s+punctuation|period\s+drama|colon\s+cancer|hash\s+table)\b", lambda m: "__" + m.group(0).replace(" ", "_") + "__", part, flags=re.I)
        if not re.search(r"\b(?:write|say|type)\s+the\s+words?\s+(?:question mark|comma|period)\b", part, re.I):
            for spoken, symbol in (("question mark", "?"), ("exclamation mark", "!"), ("full stop", "."), ("comma", ","), ("period", "."), ("colon", ":"), ("semicolon", ";")):
                part = re.sub(rf"\b{spoken}\b", symbol, part, flags=re.I)
        part = re.sub(r"\s+([,.;:?!])", r"\1", part)
        part = re.sub(r"__(.+?)__", lambda m: m.group(1).replace("_", " "), part)
        protected[i] = part
    return "".join(protected)


def _numbered_list(text: str) -> str:
    stripped = text.strip()
    groups = [(r"number one\s+(.+?)\s+number two\s+(.+)", 1), (r"list:\s*first\s+(.+?)\s+second\s+(.+)", 1)]
    for pattern, _ in groups:
        match = re.fullmatch(pattern, stripped, re.I)
        if match:
            return f"1. {match.group(1).strip(' ,;.')}\n2. {match.group(2).strip(' ,;.')}"
    return text


def apply_style(text: str, style_id: str, context=None) -> str:
    """Formats text according to requested style_id and surrounding textbox context."""
    text = text.strip()
    if not text or style_id == "cleanup_none":
        return text

    # Adapt context object if provided
    tb_context = None
    if context:
        if isinstance(context, str):
            tb_context = TextboxContext(before=context, trustworthy=True)
        else:
            tb_context = TextboxContext(
                before=getattr(context, "before", ""),
                selection=getattr(context, "selection", ""),
                after=getattr(context, "after", ""),
                trustworthy=getattr(context, "trustworthy", False),
            )

    return style_formatter.format(text, style=style_id, context=tb_context)


def smart_format(text: str, style_id: str, context=None) -> str:
    return apply_style(_numbered_list(_spoken_punctuation(text)), style_id, context)


# ---------------------------------------------------------------------------
# Spoken number normalization ("twenty five" -> "25"), pure Python, no deps.
# ---------------------------------------------------------------------------

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_ORDINALS = {
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
    "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
    "nineteenth", "twentieth", "thirtieth", "fortieth", "fiftieth",
    "sixtieth", "seventieth", "eightieth", "ninetieth", "hundredth",
    "thousandth",
}
_DIGIT_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}

_ORDINAL_TOKEN = "|".join(sorted(_ORDINALS, key=len, reverse=True))
_NUMBER_TOKEN = "|".join(
    sorted(
        set(_UNITS) | set(_TENS) | set(_SCALES) | {"and", "point", "dot"},
        key=len, reverse=True,
    )
)
_NUM_WORD_PAT = re.compile(rf"^({_NUMBER_TOKEN})([.,;:!?]*)$", re.I)
_ORD_WORD_PAT = re.compile(rf"^({_ORDINAL_TOKEN})([.,;:!?]*)$", re.I)
# A number word directly after a URL-ish token ("example.com/twenty five",
# "user@host", "https://...") is usually part of that token and must not be
# converted. Plain commas/periods do NOT count ("okay, twenty five" -> "25").
_URL_CHARS = "/@:"


def _word_is_urlish(word: str) -> bool:
    return "www" in word.casefold() or any(ch in word for ch in _URL_CHARS)


def _parse_cardinal(tokens: list[str]) -> int | None:
    words = [t.casefold() for t in tokens]
    total = 0
    current = 0
    scale_seen = False
    for word in words:
        if word == "and":
            continue
        if word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word == "hundred":
            # "hundred" multiplies what we have so far ("five hundred" = 500).
            if current == 0:
                current = 1
            current *= 100
            scale_seen = True
        else:  # thousand / million — fold the running total scaled up
            if current == 0:
                current = 1
            total += current * _SCALES[word]
            current = 0
            scale_seen = True
    total += current
    if not scale_seen:
        if "and" in words:
            return None  # "two and three" is ambiguous
        # Without a scale the only valid shape is [tens...][unit] ("twenty
        # five"). "two three" would silently become 2+3 and "five twenty"
        # is not a number phrase — reject both.
        if len(words) > 1 and not (all(w in _TENS for w in words[:-1]) and words[-1] in _UNITS):
            return None
    return total


def _parse_decimal(tokens: list[str]) -> str | None:
    """'three point five six' -> '3.56'; standalone 'point five' -> '0.5'."""
    try:
        point_index = next(i for i, t in enumerate(tokens) if t.casefold() in ("point", "dot"))
    except StopIteration:
        return None
    left = _parse_cardinal(tokens[:point_index]) if point_index > 0 else 0
    if left is None:
        return None
    frac_digits = [_DIGIT_WORDS.get(t.casefold()) for t in tokens[point_index + 1:]]
    if not frac_digits or len(frac_digits) > 3 or any(d is None for d in frac_digits):
        return None
    return f"{left}.{''.join(frac_digits)}"


def _convert_run(words: list[str]) -> str | None:
    """Convert a run of lowercased number words; None means keep as spoken."""
    if not words:
        return None
    lowered = set(words)
    if "point" in lowered or "dot" in lowered:
        return _parse_decimal(words)
    if len(words) == 1:
        word = words[0]
        # "one" is often a pronoun; "zero"/"and"/scales alone are not quantities.
        if word in {"one", "zero", "and", "hundred", "thousand", "million"}:
            return None
        if word in _UNITS or word in _TENS:
            return str(_UNITS.get(word, _TENS.get(word)))
        return None
    cardinal = _parse_cardinal(words)
    return str(cardinal) if cardinal is not None else None


def normalize_spoken_numbers(text: str) -> str:
    """Convert unambiguous spoken cardinal numbers to digits.

    Conservative by design (Wispr-style post-processing, zero models):
    - "twenty five" -> "25", "one hundred and twenty" -> "120",
      "three point five" -> "3.5"
    - Never touches ordinals ("twenty first"), the pronoun "one", "zero",
      ambiguous phrases ("two and three"), or number words that follow a
      URL-ish token ("example.com/twenty five" stays intact).
    """
    if not text:
        return text
    parts = re.split(r"(\s+)", text)
    out: list[str] = []
    i = 0
    n = len(parts)
    while i < n:
        word = parts[i]
        m = _NUM_WORD_PAT.match(word) if word and i % 2 == 0 else None
        if m is None:
            out.append(word)
            i += 1
            continue
        run: list[tuple[int, str, str]] = []  # (index, lower word, trailing punct)
        j = i
        while j < n and parts[j] and j % 2 == 0:
            mm = _NUM_WORD_PAT.match(parts[j])
            if mm is None:
                break
            run.append((j, mm.group(1).casefold(), mm.group(2)))
            j += 2
        next_word = parts[j] if j < n and parts[j] else ""
        prev_word = parts[i - 2] if i >= 2 else ""
        protected = _word_is_urlish(prev_word)
        ordinal_next = bool(next_word and _ORD_WORD_PAT.match(next_word))
        converted = None if (protected or ordinal_next) else _convert_run([r[1] for r in run])
        if converted is None:
            for k in range(i, min(j, n)):
                out.append(parts[k])
            i = j
        else:
            out.append(converted + run[-1][2])
            for k in range(run[-1][0] + 1, min(j, n)):
                out.append(parts[k])
            i = j
    return "".join(out)


def adapt_first_letter(text: str, capitalize: bool | None) -> str:
    """Match the dictated text's first letter to the surrounding textbox.

    True -> uppercase first letter, False -> lowercase it,
    None -> leave the text exactly as the style engine produced it.
    """
    if not text or capitalize is None:
        return text
    for i, char in enumerate(text):
        if char.isalpha():
            if capitalize:
                return text[:i] + char.upper() + text[i + 1:]
            return text[:i] + char.lower() + text[i + 1:]
    return text
