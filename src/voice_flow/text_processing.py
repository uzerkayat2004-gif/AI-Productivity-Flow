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


_FILLER_RE = re.compile(r"\b(um|uh|er|ah|hmm)\b[ ,]*", re.IGNORECASE)
# Internal lower-to-upper transitions (parseJSON, iPhone) and an acronym
# followed by a capitalized component (HTTPClient) identify case-sensitive
# tokens. Ordinary Titlecase words and all-uppercase prose do not qualify.
_MIXED_CASE_IDENTIFIER_PATTERN = (
    r"\b(?=[A-Za-z_][A-Za-z0-9_]*\b)"
    r"(?=[A-Za-z0-9_]*(?:[a-z][A-Z]|[A-Z]{2}[a-z]))[A-Za-z0-9_]+\b"
)
_PROTECTED_CLEANUP_SPAN_RE = re.compile(
    r"(``[\s\S]*?``|`[^`\n]*`|\[[^\]]+\]\([^\)]+\)|"
    r"(?:https?|ftp)://[^\s<>]+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|\bwww\.[^\s<>]+|"
    r"(?:[A-Za-z]:[\\/]|\\\\|(?:\.{1,2}/|/))[^\s<>]*|\$\w+|--[\w-]+|\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b|"
    r"\"(?:\\.|[^\"\\])*\"|(?<!\w)'(?:\\.|[^'\\])*'(?!\w)|"
    + _MIXED_CASE_IDENTIFIER_PATTERN + r")"
)


def is_protected_literal(text: str) -> bool:
    """Return whether the entire nonblank input is one protected literal span."""
    return bool(isinstance(text, str) and _PROTECTED_CLEANUP_SPAN_RE.fullmatch(text.strip()))


def sentence_case_text(text: str) -> str:
    """Capitalize ordinary sentence and paragraph starts without editing literals.

    Protected spans use the same boundaries as deterministic cleanup, so dots
    inside identifiers, links, paths, code, and quotes never create a sentence
    boundary or have their contents changed.
    """
    if not isinstance(text, str) or not text:
        return text

    parts = _PROTECTED_CLEANUP_SPAN_RE.split(text)
    at_sentence_start = True
    for index, part in enumerate(parts):
        if index % 2:
            # The protected token occupies any pending sentence-start slot;
            # its spelling and punctuation remain entirely literal.
            at_sentence_start = False
            continue

        output: list[str] = []
        for position, char in enumerate(part):
            if at_sentence_start and char.isalnum():
                output.append(char.upper() if char.isalpha() else char)
                at_sentence_start = False
                continue
            output.append(char)

            if char == "\n":
                at_sentence_start = True
            elif char in "!?":
                at_sentence_start = True
            elif char == ".":
                previous = part[position - 1] if position else ""
                following = part[position + 1] if position + 1 < len(part) else ""
                # Decimal points are internal punctuation, not sentence ends.
                if not (previous.isdigit() and following.isdigit()):
                    at_sentence_start = True
        parts[index] = "".join(output)
    return "".join(parts)


def lowercase_prose_text(text: str) -> str:
    """Lowercase prose while preserving spans protected by deterministic cleanup."""
    if not isinstance(text, str) or not text:
        return text
    parts = _PROTECTED_CLEANUP_SPAN_RE.split(text)
    for index in range(0, len(parts), 2):
        parts[index] = parts[index].lower()
    return "".join(parts)


_DICTATED_EMAIL_SALUTATION_RE = re.compile(
    r"^\s*(?P<salutation>(?:(?:dear|hi|hello|hey)\s+[A-Za-z][A-Za-z .'-]{0,50}|(?!(?:please|tomorrow|however|therefore|first|second|finally|yes|no)\b)[A-Z][A-Za-z'-]{1,40})),[ \t]+(?P<body>\S[\s\S]*?)\s*$",
    re.IGNORECASE,
)
_UNPUNCTUATED_EMAIL_SALUTATION_RE = re.compile(
    r"^\s*(?P<salutation>(?i:dear|hi|hello)\s+[A-Z][A-Za-z'-]*"
    r"(?:[ \t]+[A-Z][A-Za-z'-]*){0,2})[ \t]+"
    r"(?P<body>(?i:please|can|could|would|will|i|we)\b[\s\S]+?)\s*$"
)
_DICTATED_EMAIL_SIGNOFF_RE = re.compile(
    r"(?:[ \t\n]+)(?P<closing>(?i:thanks|thank you|regards|best regards|kind regards))"
    r"[, \t]+(?P<sender>[A-Z][A-Za-z'-]*(?:[ \t]+[A-Z][A-Za-z'-]*){0,2}[.!?]?)\s*$"
)


def _repair_unambiguous_agreement(segment: str) -> str:
    """Repair only agreement errors with one clear grammatical outcome.

    This is intentionally not a general grammar checker.  It handles a small
    set of common ASR errors locally, without changing wording or attempting
    subject/noun inference.  The caller applies it only to unprotected spans,
    so quoted text, code, links, paths, and email addresses remain literal.
    """
    for pattern, replacement in (
        (r"\bi\s+is\b", "I am"),
        (r"\bi\s+has\b", "I have"),
        (r"\bi\s+does\b", "I do"),
        (r"\b(you|we|they)\s+is\b", r"\1 are"),
        (r"\b(you|we|they)\s+was\b", r"\1 were"),
        (r"\b(you|we|they)\s+has\b", r"\1 have"),
        (r"\b(you|we|they)\s+does\b", r"\1 do"),
        (r"\b(he|she|it)\s+are\b", r"\1 is"),
        (r"\b(he|she|it)\s+were\b", r"\1 was"),
        (r"\b(this|that)\s+are\b", r"\1 is"),
        (r"\b(these|those)\s+is\b", r"\1 are"),
    ):
        segment = re.sub(pattern, replacement, segment, flags=re.IGNORECASE)
    return re.sub(r"\bi\b", "I", segment, flags=re.IGNORECASE)


def _strip_filler(match: "re.Match[str]") -> str:
    """Drop a hesitation filler, but keep an ALL-CAPS acronym that spells one.

    "The ER team approved it" must not lose "ER": it is content, not a
    hesitation sound. An all-uppercase occurrence is treated as an acronym and
    preserved; ordinary "er"/"um"/"uh" (including sentence-initial "Um,") is
    removed.
    """
    word = match.group(1)
    if word.isupper():
        return match.group(0)
    return ""


def cleanup_text(text: str, level: str, preserve_repetitions: bool = False) -> str:
    """Independent Cleanup layer: handles spoken fillers and hesitation disfluencies."""
    if level == "cleanup_none":
        return text
    text = text.strip()

    def clean_unprotected(segment: str) -> str:
        segment = _FILLER_RE.sub(_strip_filler, segment)
        segment = re.sub(r"(?:^|,)\s*you know\s*(?=,|$)", lambda m: "," if m.group(0).startswith(",") else "", segment, flags=re.I)
        for pattern, replacement in (
            (r"\blet's meet at\s+([^,.]+?)\s+(?:actually|no wait|wait no)\s+([^,.]+)", r"let's meet at \2"),
            (r"\bsend it\s+([^,.]+?)\s+(?:scratch that|actually)\s+([^,.]+)", r"send it \2"),
            (r"\bmy code is\s+([^,.]+?)\s+(?:no wait|wait no|actually)\s+([^,.]+)", r"my code is \2"),
        ):
            segment = re.sub(pattern, replacement, segment, flags=re.I)
        # A doubled first-person pronoun is a common ASR stutter. Keep all
        # other single-word repetitions because they can carry meaning.
        segment = re.sub(r"\b(I)(?:[ \t]+\1\b)+", r"\1", segment, flags=re.I)
        if not preserve_repetitions:
            segment = collapse_echo_repeats(segment)
        if level in ("cleanup_medium", "cleanup_high"):
            segment = re.sub(r"\b(\w+(?:\s+\w+){0,5})\s+(?:I mean|rather),?\s+\1\b", r"\1", segment, flags=re.I)
        segment = _repair_unambiguous_agreement(segment)
        # Explicit punctuation often reaches this layer as a symbol before
        # deterministic cleanup.  Removing only its preceding whitespace is
        # safe and preserves every dictated word and line boundary.
        segment = re.sub(r"[ \t]+([,.;:?!])", r"\1", segment)
        # Newlines are dictated structure. Normalize horizontal spacing only.
        return re.sub(r"[ \t]+", " ", segment)

    parts = _PROTECTED_CLEANUP_SPAN_RE.split(text)
    for index in range(0, len(parts), 2):
        parts[index] = clean_unprotected(parts[index])
    return "".join(parts).strip()


def format_dictated_email(text: str) -> str | None:
    """Lay out an already-dictated email salutation without inventing content.

    This intentionally does not create a subject, greeting, sign-off, sender,
    or new wording. It is only a deterministic fallback when a requested AI
    email transformation could not be safely accepted.
    """
    match = _DICTATED_EMAIL_SALUTATION_RE.match(text or "") or _UNPUNCTUATED_EMAIL_SALUTATION_RE.match(text or "")
    if not match:
        return None
    body = match.group("body")
    signoff = _DICTATED_EMAIL_SIGNOFF_RE.search(body)
    if signoff:
        body = body[:signoff.start()].rstrip()
    if body[:1].islower():
        body = body[:1].upper() + body[1:]
    result = f"{match.group('salutation')},\n\n{body}"
    if signoff:
        closing = signoff.group('closing')
        result += f"\n\n{closing[:1].upper() + closing[1:]},\n{signoff.group('sender')}"
    return result


# Speech recognition often hears a leading "Hey <Name>," as "He <Name>,".
# Only 1-3 name words, then a comma, and never a reporting verb ("He said,").
_MISHEARD_HEY_RE = re.compile(
    r"^\s*He\s+(?P<name>(?!(?:said|says|told|tells|asked|asks|wrote|writes|thinks|thought|is|was|will|would|has|had|and|also|then|just|never|always)\b)"
    r"[A-Za-z][A-Za-z'-]*(?:[ \t]+[A-Za-z][A-Za-z'-]*){0,2}),[ \t]+(?=\S)",
)
# Unpunctuated "Hey/He <name words> I have ..." at the very start of an
# email command: the greeting ends where a first-person/request body begins.
_UNPUNCTUATED_HEY_RE = re.compile(
    r"^\s*(?:Hey|He)\s+(?P<name>(?!(?:said|says|told|tells|asked|asks|wrote|writes|thinks|thought|is|was|will|would|has|had|and|also|then|just|never|always|i|we)\b)"
    r"[A-Za-z][A-Za-z'-]*(?:[ \t]+(?!(?:i|we|please|can|could|would)\b)[A-Za-z][A-Za-z'-]*){0,2})"
    r"[ \t]+(?P<body>(?:I|I'm|I've|We|we|please|Please|can|Can|could|Could)\b[\s\S]+?)\s*$",
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def format_email_command_fallback(text: str) -> str | None:
    """Local layout for an explicit email command whose AI pass failed.

    Uses only words the user dictated: never adds a greeting, subject,
    sign-off or sender. Order of attempts:
    1. an explicit dictated salutation (``format_dictated_email``);
    2. the same after repairing a leading misheard "He <Name>," -> "Hey";
    3. with no salutation, sentence-boundary paragraphs (needs 2+ sentences).
    """
    if not text or not text.strip():
        return None
    layout = format_dictated_email(text)
    if layout is not None:
        return layout
    repaired = _MISHEARD_HEY_RE.sub(lambda m: f"Hey {m.group('name')}, ", text, count=1)
    if repaired != text:
        layout = format_dictated_email(repaired)
        if layout is not None:
            return layout
    unpunctuated = _UNPUNCTUATED_HEY_RE.match(text)
    if unpunctuated:
        body = unpunctuated.group("body")
        layout = format_dictated_email(f"Hey {unpunctuated.group('name')}, {body[:1].upper() + body[1:]}")
        if layout is not None:
            return layout
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    if len(sentences) < 2:
        return None
    # Group into short paragraphs of at most two sentences each.
    paragraphs = [" ".join(sentences[i:i + 2]) for i in range(0, len(sentences), 2)]
    return "\n\n".join(paragraphs)


def collapse_echo_repeats(text: str) -> str:
    """Collapse a phrase the speaker repeated immediately (dictation echo).

    "hey fix this hey fix this" -> "hey fix this". Only BACK-TO-BACK
    repetitions of a 2-6 word phrase count; the same phrase appearing twice
    in different places of the dictation is intentional and is kept.

    A repetition that crosses a sentence boundary ("Send the report today.
    Send the report today.") is deliberate emphasis or quoted text, so the
    two halves are never merged across a terminator.
    """
    if not text or " " not in text:
        return text

    def _norm(word: str) -> str:
        return re.sub(r"[^\w']", "", word).lower()

    for _ in range(4):  # chained echoes: "a b a b a b"
        tokens = text.split(" ")
        n = len(tokens)
        replaced = False
        for size in range(min(6, n // 2), 1, -1):
            i = 0
            while i + 2 * size <= n:
                first = [_norm(w) for w in tokens[i:i + size]]
                second = [_norm(w) for w in tokens[i + size:i + 2 * size]]
                if first and first == second and all(first):
                    # Do not merge across a sentence terminator: a complete
                    # sentence repeated is intentional, not an echo.
                    boundary = any(
                        w.endswith((".", "!", "?"))
                        for w in tokens[i:i + size - 1]
                    ) or tokens[i + size - 1].endswith((".", "!", "?"))
                    if boundary:
                        i += 1
                        continue
                    tokens = tokens[:i] + tokens[i + size:]
                    text = " ".join(tokens)
                    replaced = True
                    break
                i += 1
            if replaced:
                break
        if not replaced:
            break
    return text


# ---------------------------------------------------------------------------
# Stutter fragments
# ---------------------------------------------------------------------------
# The native streaming endpointer finalizes each false start of a stutter as
# its own punctuated segment ("My. Ag. My agent", "Q? Q. Quest? Question.",
# "So the plan is. Is to ship. Ship on Friday."). The collapser below removes
# only words that are immediately repeated (or are a prefix of the word that
# follows); it never removes a word that is not said again right after it.

# A segment ending in one of these is grammatically unfinished, so a restart
# that repeats it is a stutter rather than a new sentence.
_UNFINISHED_ENDINGS = frozenset("""
a an the is are was were am be been to of and but or nor so for with from in
on at by into onto my your our their his its will would can could should must
shall may might have has i we they if because than as
""".split())
# Immediate duplicates of these are disfluencies ("the the plan"); content
# words ("very very", "no no") and grammatical doubles ("had had", "that
# that") are left alone.
_DUPLICABLE_FUNCTION_WORDS = frozenset(
    "the a an to of and i in on at for my we our your is are it".split()
)
_STUTTER_MAX_FRAGMENT_WORDS = 2
_STUTTER_MAX_RUN_WORDS = 4


def _stutter_norm(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


def _stutter_segments(line: str) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for token in line.split():
        current.append(token)
        if token[-1] in ".?!":
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def _words_restart(fragment: list[str], following: list[str]) -> bool:
    """True when *fragment* is an aborted start of *following*."""
    if not fragment or len(following) <= len(fragment) - 1:
        return False
    for index, word in enumerate(fragment):
        if not word or index >= len(following):
            return False
        nxt = following[index]
        if index < len(fragment) - 1:
            if word != nxt:
                return False
        elif not (word == nxt or (len(word) < len(nxt) and nxt.startswith(word))):
            return False
    # The restart must continue: an exact, complete repeat ("Okay. Okay.")
    # is deliberate and kept.
    return len(following) > len(fragment) or following[len(fragment) - 1] != fragment[-1]


def _collapse_stutter_line(line: str) -> str:
    segments = _stutter_segments(line)
    if len(segments) < 2 and not any(
        _stutter_norm(a) == _stutter_norm(b) and _stutter_norm(a) in _DUPLICABLE_FUNCTION_WORDS
        for a, b in zip(line.split(), line.split()[1:])
    ):
        return line
    changed = False
    question_lost = False

    # 1. Drop runs of short punctuated fragments that restart the following text.
    out: list[list[str]] = []
    i = 0
    while i < len(segments):
        dropped = False
        for k in range(1, 4):
            run = segments[i:i + k]
            if len(run) < k or i + k >= len(segments):
                break
            if any(len(seg) > _STUTTER_MAX_FRAGMENT_WORDS or seg[-1][-1] not in ".?!" for seg in run):
                break
            words = [_stutter_norm(w) for seg in run for w in seg]
            if len(words) > _STUTTER_MAX_RUN_WORDS:
                break
            following = [_stutter_norm(w) for seg in segments[i + k:] for w in seg][:len(words) + 1]
            if _words_restart(words, following):
                question_lost = question_lost or any(seg[-1].endswith("?") for seg in run)
                i += k
                dropped = changed = True
                break
        if not dropped:
            out.append(list(segments[i]))
            i += 1
    segments = out

    # 2. Merge a segment boundary where the next segment restarts with the
    #    last words of an unfinished (or already-restarted) segment.
    merged: list[list[str]] = []
    restarted: list[bool] = []
    for seg in segments:
        if merged:
            prev = merged[-1]
            prev_words = [_stutter_norm(w) for w in prev]
            seg_words = [_stutter_norm(w) for w in seg]
            for k in (3, 2, 1):
                if len(prev) < k or len(seg) <= k:
                    continue
                if prev_words[-k:] != seg_words[:k] or not all(prev_words[-k:]):
                    continue
                # A capitalised word mid-segment is a name ("call Bob. Bob
                # will know"); never merge on it.
                start = len(prev) - k
                if any(w[:1].isupper() and j > 0 and w != "I" for j, w in enumerate(prev[start:], start)):
                    continue
                if not (prev_words[-1] in _UNFINISHED_ENDINGS or restarted[-1]):
                    continue
                prev[-1] = prev[-1].rstrip(".?!")
                prev.extend(seg[k:])
                restarted[-1] = True
                changed = True
                break
            else:
                merged.append(list(seg))
                restarted.append(False)
                continue
            continue
        merged.append(list(seg))
        restarted.append(False)
    segments = merged

    # 3. Immediate duplicate function words inside a segment ("the the").
    for seg in segments:
        j = 1
        while j < len(seg):
            a, b = _stutter_norm(seg[j - 1]), _stutter_norm(seg[j])
            if a == b and a in _DUPLICABLE_FUNCTION_WORDS and seg[j - 1][-1:].isalnum():
                if j - 1 == 0 and seg[0][:1].isupper() and seg[1][:1].islower():
                    seg[1] = seg[1][:1].upper() + seg[1][1:]
                del seg[j - 1]
                changed = True
            else:
                j += 1

    if not changed:
        return line
    if question_lost and len(segments) == 1 and segments[0][-1].endswith("."):
        # The recognizer heard question intonation on the false starts.
        segments[0][-1] = segments[0][-1][:-1] + "?"
    if segments and segments[0] and segments[0][0][:1].islower() and line.lstrip()[:1].isupper():
        segments[0][0] = segments[0][0][:1].upper() + segments[0][0][1:]
    return " ".join(w for seg in segments for w in seg)


def collapse_stutter_fragments(text: str) -> str:
    """Collapse endpointer stutter fragments without dropping any unrepeated word.

    "My. Ag. My agent" -> "My agent"; "Q? Q. Quest? Question." -> "Question?";
    "So the the plan is. Is to ship. Ship on Friday." -> "So the plan is to
    ship on Friday." Deliberate complete repeats ("Okay. Okay.") and short
    sentences that do not restart the next one ("I. Am.") are kept.
    """
    if not text or not text.strip():
        return text
    try:
        return "\n".join(_collapse_stutter_line(line) if line.strip() else line for line in text.split("\n"))
    except Exception:
        return text


# Spoken punctuation is a *command*, not a word substitution. "period",
# "comma", "new line" and friends are ordinary English words ("the trial
# period ends in May", "a comma separated list", "a new line of products"),
# so a term is converted only when it stands alone as a command:
#   * it ends the utterance ("send it today period"), or
#   * it sits on a sentence boundary: the recognizer attached punctuation to
#     it ("today period. Then") or the next word starts a new sentence
#     ("alpha new line Beta"),
# and in every case the word before it is not a determiner, preposition or
# modifier that makes the term a noun ("a comma", "the colon", "long period").
# False negatives (the literal word is kept) are much cheaper than silently
# rewriting what the user said.
_SPOKEN_TERMS = (
    ("new paragraph", "\n\n"),
    ("new line", "\n"),
    ("next line", "\n"),
    ("line break", "\n"),
    ("question mark", "?"),
    ("exclamation mark", "!"),
    ("exclamation point", "!"),
    ("full stop", "."),
    ("semicolon", ";"),
    ("period", "."),
    ("comma", ","),
    ("colon", ":"),
)
_SPOKEN_TERM_SYMBOLS = {term: symbol for term, symbol in _SPOKEN_TERMS}
_SPOKEN_TERM_RE = re.compile(
    r"(?<![\w'-])(" + "|".join(t.replace(" ", r"\s+") for t, _ in _SPOKEN_TERMS) + r")(?![\w'-])([.,!?;:]?)",
    re.I,
)
# A term preceded by one of these is being used as a noun, never a command.
_SPOKEN_TERM_BLOCKERS = frozenset("""
a an the this that these those my your his her its our their whose which what
each every any some no one another same such own other
of for over during per in on at by with without within to from into about
than like as is was be been being are were
long short trial grace waiting cooling probation probationary billing
given whole entire specific certain first last next final previous current
time rest double single serial oxford
word words term terms symbol key character
""".split())
_SPOKEN_NOUN_DETERMINERS = frozenset(
    "a an the this that these those my your his her its our their each every any no".split()
)
# Measures of time and counts make "period" a noun ("a two week period").
_SPOKEN_PERIOD_NOUN_MODIFIERS = frozenset("""
week weeks month months year years quarter quarters hour hours
minute minutes second seconds decade decades season seasons semester term
two three four five six seven eight nine ten twelve fifteen thirty ninety
sales holiday notice transition review reporting payment free cool off
""".split())
# ASR rarely capitalizes after a spoken mark ("today period then call me
# comma please"), so a lowercase next word is accepted only for the marks
# that end a clause, and only when that word opens a new clause. The noun
# readings ("the trial period ends", "a comma separated list") are rejected
# earlier by the blocker words, and none of their usual continuations
# ("ends", "separated", "of", "is") is a clause opener.
_SPOKEN_CLAUSE_MARKS = frozenset({".", ",", "?", "!"})
_SPOKEN_CLAUSE_OPENERS = frozenset("""
then and but so also please thanks thank i i'm i'll i've we we're we'll you
you're he she they it it's let's lets after afterwards next finally okay ok
now hi hello dear regards cheers see call send
""".split())
_SPOKEN_LITERAL_RE = re.compile(
    r"\b(?:write|say|type)\s+the\s+words?\s+(?:question mark|comma|period|colon|new line)\b", re.I
)
_CMD_PUNCT = "\x01"
_CMD_BREAK = "\x02"


def _spoken_term_replacement(part: str, match: re.Match) -> str:
    term = re.sub(r"\s+", " ", match.group(1).lower())
    symbol = _SPOKEN_TERM_SYMBOLS[term]
    before = part[:match.start()]
    after = part[match.end():]
    prev = re.search(r"([\w']+)[^\w]*$", before)
    if prev is None:
        return match.group(0)  # nothing to punctuate yet
    if prev.group(1).lower() in _SPOKEN_TERM_BLOCKERS:
        return match.group(0)
    if term in ("period", "colon"):
        # "the reporting period", "the Jurassic period": a determiner two
        # words back still makes these a noun phrase.
        prev2 = re.search(r"([\w']+)[^\w]+[\w']+[^\w]*$", before)
        if prev2 is not None and prev2.group(1).lower() in _SPOKEN_NOUN_DETERMINERS:
            return match.group(0)
    if term in ("period", "full stop"):
        prev_word = prev.group(1).lower()
        if prev_word in _SPOKEN_PERIOD_NOUN_MODIFIERS:
            return match.group(0)
        if prev_word in ("day", "days"):
            # "a 30 day period" / "a two day period" is a noun phrase, while
            # "send it to day period" is ASR splitting "today".
            prev2 = re.search(r"([\w'-]+)[^\w]+[\w']+[^\w]*$", before)
            if prev2 is not None and (
                prev2.group(1)[:1].isdigit() or prev2.group(1).lower() in _SPOKEN_PERIOD_NOUN_MODIFIERS
            ):
                return match.group(0)
    at_end = not after.strip(" \t\r\n.,!?;:")
    attached = bool(match.group(2))
    nxt = re.match(r"\s*([^\s]+)", after)
    sentence_start = bool(nxt and nxt.group(1)[:1].isupper())
    clause_opener = bool(
        nxt
        and symbol in _SPOKEN_CLAUSE_MARKS
        and re.sub(r"[^\w']", "", nxt.group(1)).lower() in _SPOKEN_CLAUSE_OPENERS
    )
    if not (at_end or attached or sentence_start or clause_opener):
        return match.group(0)
    if symbol.startswith("\n"):
        return _CMD_BREAK + symbol
    return _CMD_PUNCT + symbol


def _spoken_punctuation(text: str) -> str:
    protected = re.split(r"(https?://\S+|\b\S+@\S+\b)", text)
    for i in range(0, len(protected), 2):
        part = protected[i]
        if not part or _SPOKEN_LITERAL_RE.search(part):
            continue
        # Resolve left to right so a converted term is the context for the next.
        pos = 0
        while True:
            match = _SPOKEN_TERM_RE.search(part, pos)
            if match is None:
                break
            replacement = _spoken_term_replacement(part, match)
            part = part[:match.start()] + replacement + part[match.end():]
            pos = match.start() + len(replacement)
        if _CMD_PUNCT in part:
            # A spoken sentence end starts a new sentence ("today. Then").
            part = re.sub(
                _CMD_PUNCT + r"([.!?])([ \t]+)([a-z])",
                lambda m: _CMD_PUNCT + m.group(1) + m.group(2) + m.group(3).upper(),
                part,
            )
            # The spoken mark replaces whatever the recognizer guessed there.
            part = re.sub(r"[ \t]*[,.;:!?]*[ \t]*" + _CMD_PUNCT + r"([,.;:!?])", r"\1", part)
        if _CMD_BREAK in part:
            part = re.sub(r"[ \t]*" + _CMD_BREAK + r"(\n+)[ \t]*", r"\1", part)
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
