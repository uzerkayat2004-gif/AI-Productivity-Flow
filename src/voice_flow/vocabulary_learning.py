"""Cheap, deterministic quality rules for vocabulary learning.

Only structured names/technical spellings and a small curated set of common
lowercase technical terms qualify. A capital at sentence start is never
enough on its own. Candidate terms become active only after repeated successful
records provide enough independent evidence.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_TOKEN_RE = re.compile(r"(?<!\w)[^\W_]+(?:[.+-][^\W_]+)*(?:\+\+)?(?!\w)", re.UNICODE)
_URL_EMAIL_RE = re.compile(r"(?:https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", re.I)
_CODE_RE = re.compile(r"```[\s\S]*?```|`[^`]*`", re.MULTILINE)
_MAX_SOURCE_CHARS = 12_000

# This is a small denylist for common words that otherwise resemble names in
# dictated prose. Structural signals and cross-record evidence do most of the
# filtering; this list is not intended to approximate an English dictionary.
_COMMON = frozenset("""
feature fix perfect task cancel welcome garbage meeting project today tomorrow
last under behind bar chat hate hit safe scam star type yep mister missus productivity
important email message team update quick thanks please morning evening call
the be to of and a in that have i it for not on with he as you do at this but
his by from they we say her she or an will my one all would there their what so
up out if about who get which go me when make can like time no just him know take
people into year your good some could them see other than then now look only come
its over think also back after use two how our work first well way even new want
because any these give day most us is are was were been being has had having does
did doing should ought where why both each few more such nor own same too very
yesterday hello hey hi ok okay yes yeah thank sorry please check continue
everything however whatever video cloud wait need find try ask turn start show
hear play move live write learn change stop speak read allow spend grow open walk
send stay fall reach app code audio user file line text button card page thing
things stuff something nothing anyone someone everyone night week month voice flow
run execute install terminal powershell sudo apt command invoke chmod curl bash shell git
face best while natural models model book notebook product policing speech insights style
animation engine generation floating global sir integrity plus providers creator control
settings setting menu menus panel panels mode modes search profile profiles account accounts
input output response result results prompt prompts summary summaries history recording
recordings transcription transcript document documents file files folder folders desktop
window windows screen screenshot application website service services option options content
context format formatting font fonts theme themes language languages microphone
January February March April May June July August September October November December
Monday Tuesday Wednesday Thursday Friday Saturday Sunday spring summer autumn winter
first second third fourth fifth sixth seventh eighth ninth tenth seconds minutes minute
hours hour days day weeks week months years year speed rate times faster slower
third-party in-depth race-to-the-bottom pre-release red-teaming world-class back-end
multi-language hard-coded human-like anti-gravity sub-agents end-to-end re-log pre-made
pop-up speech-to-text self-driving non-technical voice-flowing pre-recorded pop-ups
co-founder sub-agent
""".casefold().split())
_NOISE = frozenset("""
uh um umm uhh er ah oh hmm hey hello hi here there ok okay yes yeah no
the a an and or but if so to for of with in on at my this that it we you i
please thanks thank check continue cancel start stop open close delete remove
""".split())

# Lowercase items are admitted only when they are known technical names. This
# helps common dictated jargon such as kubernetes/postgresql without relying
# on title case or adding/installing a general-purpose word-list dependency.
_LOWER_TECHNICAL = frozenset("""
kubernetes postgresql postgres sqlite fastapi pydantic sqlalchemy pytest
numpy pandas pytorch tensorflow scikit-learn redis rabbitmq graphql grpc
javascript typescript golang rustlang langchain langgraph chromadb qdrant
weaviate whisper whisperx faster-whisper
""".split())

_KNOWN_NAMES_BRANDS = frozenset("""
hyperkube langgraph github nvidia vsphere macos anthropic microsoft claude amazon tesla
joey abdul priyanka openai apple google meta aws azure huggingface databricks supabase
mongodb docker kubernetes postgresql postgres sqlite fastapi pydantic sqlalchemy pytest
numpy pandas pytorch tensorflow scikit-learn redis rabbitmq graphql grpc javascript typescript
golang rustlang langchain chromadb qdrant weaviate whisper whisperx faster-whisper deepseek notebooklm
gpt-5.6 qwen3.5
""".split())
_CANONICAL_ACRONYMS = frozenset("""
ai api aws cli cpu css cuda gcp gpu gpt grpc gui html http https json llm mcp
ml nlp rag sdk sql ssh stt tts ui url ux yaml
""".split())
# Common role, department, workflow, and commerce families are poor person-
# name evidence after weak action cues such as "call" or "email". Keep this
# bounded and stem-aware so the rule generalizes across normal inflections
# without pretending to be a full language dictionary.
_GENERIC_NAME_ROOTS = frozenset("""
admin administrator agent billing buyer client contact customer deliver delivery department
design designer developer engineering estimate finance guest help hiring legal manager
marketing member office operation operator order partner payment people person pricing
product project recruiting sale seller service ship shipping staff store support supplier
team user vendor visitor workflow
""".split())
_NAME_CONTEXT_RE = re.compile(
    r"(?:\b(?:ask|call|email|emailed|meet|message|messaged|phone|tell|text)"
    r"|\b(?:met|spoke|talked)\s+(?:to|with)"
    r"|\b(?:doctor|dr|mr|mrs|ms|professor))$",
    re.I,
)
_EXPLICIT_NAMING_CONTEXT_RE = re.compile(
    r"(?:\b(?:acronym|name)\s+(?:is|was)|\b(?:called|named|spelled)"
    r"|\b(?:client|company|contact|customer|person|project|tool|vendor)\s+(?:called|named))$",
    re.I,
)
_TECH_CONTEXT_RE = re.compile(
    r"\b(?:api|app|database|framework|library|model|package|platform|plugin|project|"
    r"repository|runtime|sdk|service|stack|tool|using|use|used|with)\b",
    re.I,
)
_FOOTNOTE_SUFFIX_RE = re.compile(r"(?:\.\d+|\[\d+\])$")
_ORDINAL_RE = re.compile(r"^\d+(?:st|nd|rd|th)$", re.I)
_DURATION_OR_RATE_RE = re.compile(
    r"^\d+(?:\.\d+)?(?:x|s|ms|sec|secs|min|mins|h|hr|hrs|hour|hours|d|day|days|pm|am|mph|kph|fps|hz|khz|mhz|gb|mb|tb|kb)$",
    re.I,
)


def strip_protected_spans(text: str) -> str:
    text = _CODE_RE.sub(" ", (text or "")[:_MAX_SOURCE_CHARS])
    return _URL_EMAIL_RE.sub(" ", text)


def _sentence_context(text: str, start: int, end: int) -> str:
    """Bound context to the candidate's sentence and a small fixed window."""
    left = max(0, start - 100)
    right = min(len(text), end + 80)
    prior_boundary = max(text.rfind(mark, left, start) for mark in ".!?")
    if prior_boundary >= 0:
        left = prior_boundary + 1
    following = [position for mark in ".!?" if (position := text.find(mark, end, right)) >= 0]
    if following:
        right = min(following)
    return text[left:right]


def _context_signal(context: str, term: str) -> str:
    """Return the narrow semantic signal surrounding an otherwise unknown term."""
    if not context:
        return ""
    match = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", context, re.I)
    before = context[:match.start()] if match else context
    before = " ".join(before.split()[-5:])
    around = " ".join(context.split()[-10:])
    if _EXPLICIT_NAMING_CONTEXT_RE.search(before):
        return "explicit"
    if _NAME_CONTEXT_RE.search(before):
        return "name"
    if _TECH_CONTEXT_RE.search(around):
        return "technical"
    return ""


def _is_generic_name_family(value: str) -> bool:
    folded = value.casefold()
    forms = {folded}
    if folded.endswith("ies") and len(folded) > 4:
        forms.add(folded[:-3] + "y")
    if folded.endswith("es") and len(folded) > 4:
        forms.update({folded[:-2], folded[:-1]})
    elif folded.endswith("s") and len(folded) > 3:
        forms.add(folded[:-1])
    if folded.endswith("ing") and len(folded) > 5:
        stem = folded[:-3]
        forms.update({stem, stem + "e"})
        if len(stem) > 2 and stem[-1:] == stem[-2:-1]:
            forms.add(stem[:-1])
    if folded.endswith("ed") and len(folded) > 4:
        stem = folded[:-2]
        forms.update({stem, stem + "e"})
        if len(stem) > 2 and stem[-1:] == stem[-2:-1]:
            forms.add(stem[:-1])
    return bool(forms & _GENERIC_NAME_ROOTS)


def _letters(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in normalized if ch.isalpha() and not unicodedata.combining(ch))


def is_plausible_spelling_correction(term: str, variant: str) -> bool:
    """Cheap lexical check that separates spelling fixes from rewrites.

    This is intentionally only a relation check. The desired term must still
    have a name/technical context or a known/structured spelling signal.
    """
    desired = _letters(term)
    heard = _letters(variant)
    if len(desired) < 3 or len(heard) < 3:
        return False
    if desired == heard:
        return term.strip().casefold() != variant.strip().casefold()
    length_ratio = len(desired) / len(heard)
    if not 0.45 <= length_ratio <= 2.2:
        return False
    return SequenceMatcher(None, desired, heard, autojunk=False).ratio() >= 0.58


def is_useful_term(
    term: str,
    *,
    allow_sentence_initial: bool = False,
    context: str = "",
    correction_variant: str = "",
) -> bool:
    """Return whether a token has a bounded name/technical spelling signal.

    ``allow_sentence_initial`` remains for caller compatibility, but casing by
    itself is never evidence. Unknown names need an actual name context;
    unknown technical spellings need technical context or a close heard form.
    """
    if not isinstance(term, str):
        return False
    value = term.strip().strip(".,!?;:'\"()[]{}")
    if not value or len(value) < 3 or len(value) > 80:
        return False
    folded = value.casefold()
    footnote = _FOOTNOTE_SUFFIX_RE.search(value)
    if (footnote and not any(char.isdigit() for char in value[:footnote.start()])) or _ORDINAL_RE.fullmatch(value):
        return False
    if _DURATION_OR_RATE_RE.fullmatch(value) or re.fullmatch(r"\d{1,2}(?:AM|PM)", value, re.I):
        return False
    if not any(char.isalpha() for char in value):
        return False
    if folded in _COMMON or folded in _NOISE:
        return False
    if any(ch.isspace() for ch in value) or "@" in value or "://" in value:
        return False
    if _URL_EMAIL_RE.search(value):
        return False
    if folded in _KNOWN_NAMES_BRANDS or folded in _LOWER_TECHNICAL or folded in _CANONICAL_ACRONYMS:
        return True
    if re.fullmatch(r"[vV]?\d+(?:\.\d+)+", value):
        return False
    signal = _context_signal(context, value)
    # An unknown all-caps token is not self-authenticating. A narrow explicit
    # naming/spelling phrase can establish it without a permanent whitelist.
    if value.isupper():
        return signal == "explicit"
    related_correction = bool(correction_variant) and is_plausible_spelling_correction(value, correction_variant)
    has_internal_cap = any(ch.isupper() for ch in value[1:]) and any(ch.islower() for ch in value)
    has_structured_number = any(ch.isdigit() for ch in value) and any(ch.islower() for ch in value)
    if has_internal_cap or has_structured_number:
        if correction_variant:
            return related_correction and signal in {"explicit", "name", "technical"}
        return signal in {"explicit", "technical"}
    if any(ch in value for ch in ".+-"):
        return False
    if value[0].isupper() and value[1:].islower():
        return signal == "explicit" or (signal == "name" and not _is_generic_name_family(value))
    return False


def extract_vocabulary_candidates(text: str, *, limit: int = 24) -> list[str]:
    """Extract bounded unique candidate spellings from one raw record."""
    safe = strip_protected_spans(text)
    result: list[str] = []
    seen: set[str] = set()
    previous_end = 0
    saw_token = False
    for match in _TOKEN_RE.finditer(safe):
        term = match.group(0).strip(".,!?;:'\"()[]{}")
        folded = term.casefold()
        gap = safe[previous_end:match.start()]
        sentence_initial = not saw_token or bool(re.search(r"[.!?][\"')\]]*\s*$", gap))
        previous_end = match.end()
        saw_token = True
        if folded in seen or folded in _NOISE:
            continue
        context = _sentence_context(safe, match.start(), match.end())
        if is_useful_term(
            term,
            allow_sentence_initial=not sentence_initial,
            context=context,
        ):
            seen.add(folded)
            result.append(term)
            if len(result) >= max(1, limit):
                break
    return result


def is_noise_variant(variant: str) -> bool:
    """Reject generic/noisy heard-as text while allowing phonetic phrases."""
    if not isinstance(variant, str):
        return True
    value = variant.strip()
    if not value or len(value) > 120 or "@" in value or "://" in value:
        return True
    if _CODE_RE.search(value) or _URL_EMAIL_RE.search(value):
        return True
    words = [word.casefold() for word in re.findall(r"[^\W_]+", value, re.UNICODE)]
    return not words or all(word in _NOISE or word in _COMMON for word in words)
