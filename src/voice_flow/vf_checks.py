"""Deterministic fact and safety checks for voice-writing outputs (VF-1).

Used for two things:

1. **Training-data filtering**: a teacher target is rejected when it fails.
2. **Runtime validation** of a local model's output before it is inserted.

These checks are deliberately conservative and explainable.  They never edit
text; they return a list of named failures.  They are not a proof of
correctness — a passing output can still be wrong in ways regexes cannot see —
so they complement, never replace, human review and held-out evaluation.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

FILLERS = ("um", "umm", "uh", "uhh", "er", "erm", "hmm", "mm")
_FILLER_RE = re.compile(r"(?<![\w'])(?:" + "|".join(FILLERS) + r")(?![\w'])[,.]?\s*", re.IGNORECASE)

# Apostrophe-less contractions ASR emits.  Only unambiguous forms.
_BARE_CONTRACTIONS = {
    "dont": "do not", "doesnt": "does not", "didnt": "did not", "cant": "can not", "couldnt": "could not",
    "wouldnt": "would not", "shouldnt": "should not", "isnt": "is not", "arent": "are not",
    "wasnt": "was not", "werent": "were not", "havent": "have not", "hasnt": "has not", "hadnt": "had not",
    "wont": "will not", "mustnt": "must not", "neednt": "need not",
}
_BARE_CONTRACTION_RE = re.compile(r"\b(" + "|".join(_BARE_CONTRACTIONS) + r")\b", re.IGNORECASE)
_APOS_CONTRACTIONS = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not", "can't": "can not", "cannot": "can not",
    "couldn't": "could not", "wouldn't": "would not", "shouldn't": "should not", "isn't": "is not",
    "aren't": "are not", "wasn't": "was not", "weren't": "were not", "haven't": "have not",
    "hasn't": "has not", "hadn't": "had not", "won't": "will not", "mustn't": "must not", "needn't": "need not",
}
_APOS_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _APOS_CONTRACTIONS) + r")(?![\w])", re.IGNORECASE)

# Self-correction cues.  "sorry" only counts when it is not an apology.
_CORRECTION_CUE_RE = re.compile(
    r"(?:,\s*)?\b(?:no\s+wait|wait\s+no|no\s+no|i\s+mean|or\s+rather|make\s+that|scratch\s+that|"
    r"actually\s+no|(?<!\bi'm\s)(?<!\bim\s)(?<!\bam\s)(?<!\bso\s)(?<!\bvery\s)(?<!\breally\s)sorry)\b\s*,?\s*",
    re.IGNORECASE,
)
_QUOTED_RE = re.compile(r"\"[^\"]*\"|“[^”]*”|(?<!\w)'[^']{2,}'(?!\w)")
_WEEKDAYS = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|tonight"
_NUMBER_WORDS = (
    "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    "thousand|lakh|lakhs|crore|crores|million|billion"
)
_NUMERIC_TOKEN_RE = re.compile(rf"^(?:\d[\d,.:]*|{_NUMBER_WORDS})$", re.IGNORECASE)
_WORD_RE = re.compile(r"\S+")


def expand_contractions(text: str) -> str:
    text = _APOS_RE.sub(lambda m: _APOS_CONTRACTIONS[m.group(1).lower().replace("’", "'")], text.replace("’", "'"))
    return _BARE_CONTRACTION_RE.sub(lambda m: _BARE_CONTRACTIONS[m.group(1).lower()], text)


def strip_fillers(text: str) -> str:
    return _FILLER_RE.sub("", text)


def collapse_repeats(text: str, max_n: int = 4) -> str:
    """Remove immediate repetitions of 1..max_n word sequences ("we need to we need to")."""
    words = text.split()
    changed = True
    while changed:
        changed = False
        for n in range(max_n, 0, -1):
            i = 0
            out: list[str] = []
            while i < len(words):
                a = [w.strip(",.").lower() for w in words[i:i + n]]
                b = [w.strip(",.").lower() for w in words[i + n:i + 2 * n]]
                if len(a) == n and a == b and not all(_NUMERIC_TOKEN_RE.match(w) for w in a):
                    i += n
                    changed = True
                    continue
                out.append(words[i])
                i += 1
            words = out
    return " ".join(words)


def resolve_corrections(text: str) -> tuple[str, list[str]]:
    """Apply spoken self-corrections conservatively.

    Returns (text with corrected-away words removed, removed spans).  Rules,
    tried in order for each cue:

    1. The repair repeats a word from just before the cue ("send it to rahul
       no wait send it to priya", "deploy friday sorry don't deploy"): remove
       from that earlier word up to the cue.
    2. The repair starts with a number / weekday: remove back to the last
       number / weekday within the four words before the cue.
    3. Otherwise remove the single word before the cue ("rahul no wait priya").
    """
    removed: list[str] = []
    for _ in range(6):
        # Quoted speech is reproduced verbatim: corrections inside quotes are
        # part of the quote, not edits by the speaker.
        masked = _QUOTED_RE.sub(lambda q: " " * len(q.group(0)), text)
        m = _CORRECTION_CUE_RE.search(masked)
        if not m:
            break
        before = text[:m.start()].rstrip(" ,")
        after = text[m.end():]
        before_words = before.split()
        after_words = after.split()
        if not before_words or not after_words:
            text = (before + " " + after).strip()
            continue
        window = before_words[-8:]
        offset = len(before_words) - len(window)
        cut = None
        lowered_window = [w.strip(",.").lower() for w in window]
        for probe in [w.strip(",.").lower() for w in after_words[:2]]:
            probe = expand_contractions(probe).split()[-1] if probe else probe
            if probe in lowered_window and probe not in {"the", "a", "an", "to", "it", "and"}:
                cut = offset + max(i for i, w in enumerate(lowered_window) if w == probe)
                break
        if cut is None:
            first = after_words[0].strip(",.").lower()
            kind = None
            if _NUMERIC_TOKEN_RE.match(first):
                kind = _NUMERIC_TOKEN_RE
            elif re.fullmatch(_WEEKDAYS, first):
                kind = re.compile(rf"^(?:{_WEEKDAYS})$", re.I)
            if kind is not None:
                for j in range(len(before_words) - 1, max(-1, len(before_words) - 5), -1):
                    if kind.match(before_words[j].strip(",.").lower()):
                        j1 = j
                        j0 = j
                        while j0 - 1 >= 0 and kind is _NUMERIC_TOKEN_RE and _NUMERIC_TOKEN_RE.match(before_words[j0 - 1].strip(",.").lower()):
                            j0 -= 1
                        k = 1
                        while k < len(after_words) and kind is _NUMERIC_TOKEN_RE and _NUMERIC_TOKEN_RE.match(after_words[k].strip(",.").lower()):
                            k += 1
                        # Substitute the value in place: "fifteen units sorry
                        # fifty by friday" -> "fifty units by friday".
                        removed.append(" ".join(before_words[j0:j1 + 1]))
                        text = " ".join(before_words[:j0] + after_words[:k] + before_words[j1 + 1:] + after_words[k:])
                        cut = -1
                        break
        if cut == -1:
            continue
        if cut is None:
            cut = len(before_words) - 1
        removed.append(" ".join(before_words[cut:]))
        text = " ".join(before_words[:cut] + after_words)
    return text, removed


def canonical_source(text: str) -> tuple[str, list[str]]:
    """Fillers removed, repeats collapsed, corrections applied, contractions expanded."""
    t = strip_fillers(text or "")
    t = collapse_repeats(t)
    t, removed = resolve_corrections(t)
    return expand_contractions(t), removed


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------

_SMALL = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000, "crore": 10000000,
           "crores": 10000000, "million": 1000000, "billion": 1000000000}


def _words_to_number(words: list[str]) -> int | None:
    total, current, seen = 0, 0, False
    for w in words:
        if w == "and":
            continue
        if w in _SMALL:
            current += _SMALL[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w in _SCALES:
            scale = _SCALES[w]
            if scale == 100:
                current = max(current, 1) * 100
            else:
                total += max(current, 1) * scale
                current = 0
        else:
            return None
        seen = True
    return total + current if seen else None


_NUM_WORD_RUN = re.compile(
    rf"\b(?:{_NUMBER_WORDS})(?:[\s-]+(?:and[\s-]+)?(?:{_NUMBER_WORDS}))*\b", re.IGNORECASE)


def _price_compound(words: list[str]) -> int | None:
    """'nine ninety nine' -> 999, 'twenty nine ninety nine' -> 2999 (spoken prices)."""
    if len(words) < 2 or any(w in _SCALES or w == "and" for w in words):
        return None
    for split in range(1, len(words)):
        head, tail = words[:split], words[split:]
        h, t = _words_to_number(head), _words_to_number(tail)
        if h is None or t is None:
            continue
        if 1 <= h <= 99 and 10 <= t <= 99 and (tail[0] in _TENS or tail[0] in _SMALL and _SMALL[tail[0]] >= 10):
            return h * 100 + t
    return None


def number_values(text: str) -> list[set[int | float]]:
    """Each spoken or written number as a set of acceptable canonical values."""
    out: list[set] = []
    consumed = re.sub(r"(?<=\d),(?=\d)", "", text or "")
    for m in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", consumed):
        v = float(m.group(0))
        out.append({int(v) if v.is_integer() else v})
    for m in _NUM_WORD_RUN.finditer(text or ""):
        words = [w.lower() for w in re.split(r"[\s-]+", m.group(0)) if w]
        plain = _words_to_number(words)
        options: set = set()
        if plain is not None:
            options.add(plain)
        compound = _price_compound(words)
        if compound is not None:
            options.add(compound)
        if words and all(w in _SMALL or w in _TENS for w in words):
            # "five thirty" may be a time (5:30) or two numbers.
            parts = [_words_to_number([w]) for w in words]
            if len(words) == 2 and words[1] in _TENS | {"fifteen": 0, "forty": 0}:
                options.add(float(f"{parts[0]}.{parts[1]:02d}"))
        if words in (["one"],):
            continue  # "one" is too often a pronoun ("the next one")
        if options:
            out.append(options)
    return out


def _output_numbers(text: str) -> list[int | float]:
    vals: list = []
    t = re.sub(r"(?<=\d),(?=\d)", "", text or "")
    for m in re.finditer(r"(?<![\w.])(\d+)(?::(\d{2}))?(?:\.(\d+))?(?![\w])", t):
        if m.group(2):
            vals.append(float(f"{int(m.group(1))}.{m.group(2)}"))
            vals.append(int(m.group(1)))
        else:
            vals.append(float(m.group(0)) if m.group(3) else int(m.group(1)))
    for sets in number_values(re.sub(r"\d", " ", text or "")):
        vals.extend(sets)
    return vals


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{0,40}\b(?:name|recipient|company|date|your|insert|title)\b[^\]\n]{0,40}\]", re.I)
SUBJECT_RE = re.compile(r"(?im)^\s*subject\s*:")
TAG_ECHO_RE = re.compile(r"</?input_transcript>|\[(?:Transcript|Instruction|Draft|Rules|VF-1)\]|<\|im_(?:start|end)\|>", re.I)
PREAMBLE_RE = re.compile(r"^\s*(?:sure|certainly|of course|here(?:'s| is| are)|okay,? here|i've|i have)\b", re.I)
NEGATION_RE = re.compile(r"\b(?:not|never|no|without|neither|nor|none|nobody|nothing)\b", re.I)
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
FOREIGN_LATIN_RE = re.compile(r"[ąćęłńśźżčěřšťůžőű]", re.I)


@dataclass
class CheckResult:
    ok: bool
    failures: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def check_output(
    source: str,
    output: str,
    *,
    task: str = "cleanup",
    fmt: str | None = None,
    instruction: str | None = None,
    sender: str | None = None,
    recipient: str | None = None,
    allow_number_change: bool = False,
) -> CheckResult:
    """Return named failures for an output given its transcript."""
    failures: list[str] = []
    src_canon, removed = canonical_source(source)
    out = output or ""
    authorised = " ".join(x for x in (instruction or "", sender or "", recipient or "") if x)

    if not out.strip() and src_canon.strip(" .,!?"):
        failures.append("empty_output")
    if TAG_ECHO_RE.search(out):
        failures.append("tag_echo")
    if PREAMBLE_RE.search(out) and not PREAMBLE_RE.search(source or ""):
        failures.append("assistant_preamble")
    if PLACEHOLDER_RE.search(out):
        failures.append("placeholder")
    if SUBJECT_RE.search(out) and not re.search(r"\bsubject\b", source or "", re.I):
        failures.append("invented_subject")

    # Numbers: every number the speaker kept must survive (except in
    # summaries, which may drop minor numbers but never invent or change).
    src_nums = number_values(src_canon)
    auth_nums = number_values(authorised)
    out_nums = _output_numbers(out)
    out_counter = Counter(out_nums)
    if task not in ("summarize",) and not allow_number_change:
        for options in src_nums:
            if not any(out_counter.get(o) for o in options):
                failures.append(f"number_missing:{sorted(options, key=str)[0]}")
    allowed = set().union(*src_nums, *auth_nums) if (src_nums or auth_nums) else set()
    list_markers = set()
    if fmt in ("numbered", "numbered_list"):
        list_markers = {int(n) for n in re.findall(r"(?m)^\s*(\d+)[.)]\s", out)}
    for m in re.finditer(r"(?<![\w.:])(\d+)(?![\w:])", re.sub(r"(?<=\d),(?=\d)", "", out)):
        v = int(m.group(1))
        if v in list_markers or allow_number_change:
            continue
        if allowed and not any(v == a or (isinstance(a, float) and int(a) == v) for a in allowed):
            failures.append(f"number_invented:{v}")
        elif not allowed:
            failures.append(f"number_invented:{v}")

    # Corrected-away words must not come back.
    for span in removed:
        key = span.strip(" ,.").split()[-1].lower() if span.strip() else ""
        if key and len(key) > 2 and re.search(rf"\b{re.escape(key)}\b", out, re.I) \
                and not re.search(rf"\b{re.escape(key)}\b", src_canon, re.I):
            failures.append(f"correction_reverted:{key}")

    # Negations: a non-summary output must keep at least as many negations.
    if task not in ("summarize",):
        src_neg = len(NEGATION_RE.findall(src_canon))
        out_neg = len(NEGATION_RE.findall(expand_contractions(out)))
        if out_neg < src_neg:
            failures.append(f"negation_lost:{src_neg}->{out_neg}")

    # Script / language drift.
    if DEVANAGARI_RE.search(source or "") and not DEVANAGARI_RE.search(out):
        failures.append("script_changed")
    if FOREIGN_LATIN_RE.search(out) and not FOREIGN_LATIN_RE.search(source or ""):
        failures.append("language_drift")

    # A dictated question must stay a question in cleanup.
    if task == "cleanup" and re.search(r"\?|\bquestion mark\b", source or "") and "?" not in out:
        failures.append("question_lost")

    if task == "summarize" and len(out.split()) > 0.8 * max(1, len(src_canon.split())):
        failures.append("summary_not_compressed")

    return CheckResult(ok=not failures, failures=failures)


def rewrite_price_compounds(source: str, candidate: str) -> str:
    """Write spoken price compounds ("nine ninety nine") as digits when the
    candidate shows that reading, so a correct "999" is not a mismatch."""
    cand_vals = set(_output_numbers(candidate))

    def sub(m: re.Match) -> str:
        words = [w.lower() for w in re.split(r"[\s-]+", m.group(0)) if w]
        compound = _price_compound(words)
        if compound is not None and compound in cand_vals and _words_to_number(words) not in cand_vals:
            return str(compound)
        return m.group(0)

    return _NUM_WORD_RUN.sub(sub, source or "")


def normalize_source_for_guard(source: str, candidate: str) -> str:
    """Source text with the spoken-language edits a correct cleanup makes.

    Fillers, immediate repeats and self-corrections are applied; apostrophe-
    less contractions are expanded; spoken price compounds follow the
    candidate's reading.  Only recognised, explainable equivalences.
    """
    text = strip_fillers(source or "")
    text = collapse_repeats(text)
    text, _ = resolve_corrections(text)
    text = rewrite_price_compounds(text, candidate)
    return _BARE_CONTRACTION_RE.sub(lambda m: _BARE_CONTRACTIONS[m.group(1).lower()], text)
