"""Cheap, deterministic quality rules for vocabulary learning.

Only structured names/technical spellings and a small curated set of common
lowercase technical terms qualify. A capital at sentence start is never
enough on its own. Candidate terms become active only after repeated successful
records provide enough independent evidence.
"""
from __future__ import annotations

import re

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
golang rustlang langchain chromadb qdrant weaviate whisper whisperx faster-whisper
""".split())
_FOOTNOTE_SUFFIX_RE = re.compile(r"(?:\.\d+|\[\d+\])$")
_ORDINAL_RE = re.compile(r"^\d+(?:st|nd|rd|th)$", re.I)
_DURATION_OR_RATE_RE = re.compile(
    r"^\d+(?:\.\d+)?(?:x|s|ms|sec|secs|min|mins|h|hr|hrs|hour|hours|d|day|days|pm|am|mph|kph|fps|hz|khz|mhz|gb|mb|tb|kb)$",
    re.I,
)


def strip_protected_spans(text: str) -> str:
    text = _CODE_RE.sub(" ", (text or "")[:_MAX_SOURCE_CHARS])
    return _URL_EMAIL_RE.sub(" ", text)


def is_useful_term(term: str, *, allow_sentence_initial: bool = False) -> bool:
    """Return whether a token has a useful name/technical spelling signal."""
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
    if folded in _KNOWN_NAMES_BRANDS or folded in _LOWER_TECHNICAL:
        return True
    # Acronyms and internal capitals carry a useful signal. Punctuation and
    # digits qualify only as part of a mixed-case structured identifier.
    if value.isupper() and 2 <= len(value) <= 12:
        return True
    if any(ch.isdigit() for ch in value):
        return any(ch.isupper() for ch in value)
    if any(ch.isupper() for ch in value[1:]) and any(ch.islower() for ch in value):
        return True
    if any(ch in value for ch in ".+-"):
        return False
    if value[0].isupper() and value[1:].islower():
        return allow_sentence_initial
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
        if is_useful_term(term, allow_sentence_initial=not sentence_initial):
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
