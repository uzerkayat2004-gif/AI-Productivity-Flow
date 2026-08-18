"""Conservative custom vocabulary and text-expansion engine."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import threading
from voice_flow.storage import storage

log = logging.getLogger(__name__)

# Do not allow a vocabulary rule to rewrite text inside these constructs.  They
# are user content, not spoken vocabulary tokens.
_PROTECTED_RE = re.compile(
    r"``[\s\S]*?``|`[^`\n]*`|\[[^\]]+\]\([^\)]+\)|"
    r"(?:https?|ftp)://[^\s<>]+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|"
    r"\bwww\.[^\s<>]+",
    re.IGNORECASE,
)
_STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "and",
    "or", "but", "if", "so", "my", "this", "that", "it", "we", "you", "i",
    "he", "she", "they", "how", "hey", "can", "when", "what", "where", "who",
    "why",
}

# Common English words that must never be "corrected" by fuzzy matching. A
# fuzzy pass is only safe when the token is clearly not ordinary vocabulary.
_COMMON_WORDS = {
    "about", "above", "after", "again", "against", "agent", "agree", "almost",
    "along", "already", "always", "among", "answer", "appear", "apple", "area",
    "argue", "around", "arrive", "ask", "away", "back", "ball", "bank", "battle",
    "beauty", "became", "become", "before", "begin", "behind", "being", "believe",
    "best", "better", "between", "beyond", "black", "blood", "blue", "board",
    "body", "book", "both", "break", "bring", "brother", "build", "business",
    "call", "came", "campaign", "car", "care", "career", "carry", "case", "cause",
    "center", "certain", "change", "charge", "check", "child", "choice", "choose",
    "church", "city", "claim", "class", "clear", "close", "color", "come", "common",
    "community", "company", "compare", "computer", "condition", "consider",
    "contain", "continue", "control", "cost", "could", "count", "country",
    "couple", "course", "court", "cover", "create", "culture", "current", "data",
    "daughter", "day", "dead", "deal", "death", "decide", "decision", "deep",
    "defense", "degree", "demand", "design", "desire", "develop", "difference",
    "different", "difficult", "dinner", "direction", "discover", "discuss",
    "distance", "doctor", "door", "down", "draw", "dream", "drive", "drop",
    "during", "each", "early", "earth", "east", "easy", "eat", "economic",
    "edge", "education", "effect", "effort", "eight", "either", "election",
    "else", "employee", "energy", "enjoy", "enough", "enter", "entire",
    "environment", "especially", "establish", "even", "evening", "event",
    "ever", "every", "everyone", "everything", "example", "expect", "experience",
    "expert", "explain", "face", "fact", "factor", "fail", "fall", "family",
    "far", "fast", "father", "fear", "federal", "feel", "feeling", "field",
    "fight", "figure", "fill", "film", "final", "finally", "financial", "find",
    "fine", "finger", "finish", "fire", "firm", "first", "five", "floor",
    "follow", "food", "foot", "force", "foreign", "forget", "form", "former",
    "forward", "four", "free", "friend", "front", "full", "fund", "future",
    "game", "garden", "general", "get", "girl", "give", "glass", "goal", "good",
    "government", "great", "green", "ground", "group", "grow", "growth", "guess",
    "hair", "half", "hand", "hang", "happen", "happy", "hard", "head", "health",
    "hear", "heart", "heat", "heavy", "help", "here", "herself", "high", "himself",
    "history", "hit", "hold", "home", "hope", "horse", "hospital", "hot", "hotel",
    "hour", "house", "however", "huge", "human", "hundred", "husband", "idea",
    "image", "imagine", "impact", "important", "improve", "include", "increase",
    "indeed", "individual", "industry", "information", "inside", "instead",
    "institution", "interest", "international", "interview", "into", "issue",
    "item", "itself", "job", "join", "keep", "key", "kind", "king", "kitchen",
    "know", "knowledge", "land", "language", "large", "last", "late", "later",
    "laugh", "law", "lawyer", "lead", "leader", "learn", "least", "leave",
    "left", "legal", "less", "let", "letter", "level", "life", "light", "like",
    "likely", "line", "list", "listen", "little", "live", "local", "long",
    "look", "lose", "loss", "lot", "love", "low", "main", "major", "majority",
    "make", "manage", "management", "manager", "many", "market", "marriage",
    "material", "matter", "maybe", "mean", "measure", "media", "medical",
    "meet", "meeting", "member", "memory", "mention", "message", "method",
    "middle", "might", "military", "million", "mind", "minute", "miss", "model",
    "money", "month", "moral", "more", "morning", "most", "mother", "mouth",
    "move", "movement", "movie", "much", "music", "must", "name", "nation",
    "national", "natural", "nature", "near", "necessary", "need", "network",
    "never", "new", "news", "next", "nice", "night", "nine", "nobody", "north",
    "note", "nothing", "notice", "number", "occur", "offer", "office", "officer",
    "often", "oil", "old", "once", "ones", "only", "open", "operation", "opinion",
    "opportunity", "option", "order", "organization", "other", "others", "outside",
    "over", "own", "owner", "page", "pain", "paper", "parent", "part", "participant",
    "particular", "partner", "party", "pass", "past", "patient", "pattern",
    "peace", "people", "per", "perform", "performance", "perhaps", "period",
    "person", "personal", "phone", "physical", "pick", "picture", "piece",
    "place", "plan", "plant", "play", "player", "point", "police", "policy",
    "political", "politics", "poor", "popular", "population", "position",
    "positive", "possible", "power", "practice", "prepare", "present", "president",
    "pretty", "prevent", "price", "private", "probably", "problem", "process",
    "produce", "product", "production", "professional", "program", "project",
    "property", "protect", "prove", "provide", "public", "pull", "purpose",
    "push", "quality", "question", "quickly", "quite", "race", "radio", "raise",
    "range", "rate", "rather", "reach", "read", "ready", "real", "reality",
    "realize", "really", "reason", "receive", "recent", "recently", "recognize",
    "record", "red", "reduce", "reflect", "region", "relate", "relationship",
    "religious", "remain", "remember", "remove", "report", "represent",
    "require", "research", "resource", "respond", "response", "rest", "result",
    "return", "reveal", "right", "rise", "risk", "road", "rock", "role", "room",
    "rule", "run", "safe", "same", "save", "school", "science", "season", "seat",
    "second", "section", "security", "see", "seek", "seem", "sell", "send",
    "senior", "sense", "series", "serious", "serve", "service", "set", "seven",
    "several", "share", "she", "short", "should", "shoulder", "show", "side",
    "sign", "significant", "similar", "simple", "simply", "since", "sing",
    "single", "sister", "sit", "site", "situation", "six", "size", "skill",
    "skin", "small", "social", "society", "soldier", "somebody", "sometime",
    "son", "song", "soon", "sort", "sound", "source", "south", "space",
    "speak", "special", "specific", "speech", "spend", "sport", "spring",
    "staff", "stage", "stand", "standard", "star", "start", "state", "statement",
    "station", "stay", "step", "still", "stock", "stop", "store", "story",
    "straight", "strategy", "street", "strong", "structure", "student", "study",
    "stuff", "style", "subject", "success", "successful", "such", "suddenly",
    "suffer", "suggest", "summer", "support", "sure", "surface", "system",
    "table", "take", "talk", "task", "tax", "teach", "teacher", "team",
    "technology", "television", "tell", "ten", "tend", "term", "test", "than",
    "thank", "that", "them", "themselves", "then", "theory", "there", "these",
    "they", "thing", "think", "third", "those", "though", "thought", "thousand",
    "three", "through", "throughout", "throw", "thus", "time", "today",
    "together", "tonight", "too", "top", "total", "toward", "town", "trade",
    "traditional", "training", "travel", "treat", "tree", "trial", "trip",
    "trouble", "true", "truth", "try", "turn", "two", "type", "under",
    "understand", "unit", "until", "upon", "us", "use", "usually", "value",
    "various", "very", "victim", "view", "violence", "visit", "voice", "vote",
    "wait", "walk", "wall", "want", "war", "watch", "water", "way", "weapon",
    "wear", "week", "weight", "well", "west", "what", "whatever", "when",
    "where", "whether", "which", "while", "white", "who", "whole", "whom",
    "whose", "why", "wide", "wife", "will", "win", "wind", "window", "wish",
    "with", "within", "without", "woman", "wonder", "wood", "word", "work",
    "worker", "world", "would", "write", "writer", "wrong", "yard", "year",
    "yes", "yet", "young",
}


def _levenshtein(a: str, b: str) -> int:
    """Classic DP edit distance for short vocabulary tokens."""
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert = previous[j] + 1
            delete = current[j - 1] + 1
            substitute = previous[j - 1] + (ca != cb)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class _Rule:
    trigger: str
    replacement: str
    snippet: bool = False


def _split_entry(value: str) -> tuple[str, str | None]:
    """Parse one GUI dictionary value without losing delimiters in expansions."""
    for delimiter in ("->", "=>"):
        if delimiter in value:
            trigger, expansion = value.split(delimiter, 1)
            return trigger.strip(), expansion.strip()
    return value.strip(), None


def _rule_pattern(trigger: str) -> re.Pattern[str]:
    escaped = re.escape(trigger)
    # A dictionary trigger is a complete lexical phrase even when it ends in
    # punctuation (for example C++ or C#); otherwise it can rewrite a prefix
    # of a larger symbolic token such as C++x.
    return re.compile(r"(?<!\w)" + escaped + r"(?!\w)", re.IGNORECASE)


def _is_symbolic_trigger(trigger: str) -> bool:
    return any(not char.isalnum() and char != "_" and not char.isspace() for char in trigger)


def _rule_matches(match: re.Match[str], rule: _Rule) -> bool:
    """Keep symbolic triggers from matching a larger identifier."""
    if not _is_symbolic_trigger(rule.trigger):
        return True
    end = match.end()
    return end >= len(match.string) or not (match.string[end].isalnum() or match.string[end] == "_")


def _combined_pattern(rules: tuple[_Rule, ...]) -> tuple[re.Pattern[str], tuple[_Rule, ...]]:
    """Build one callback pattern while retaining each rule's boundaries."""
    usable = tuple(rule for rule in rules if rule.trigger)
    pattern = re.compile(
        "|".join(f"({_rule_pattern(rule.trigger).pattern})" for rule in usable),
        re.IGNORECASE,
    )
    return pattern, usable


class DictionaryEngine:
    """Apply explicit dictionary terms exactly once and never guess by default."""

    def __init__(self) -> None:
        self.words: list[str] = []
        self._rules: tuple[_Rule, ...] = ()
        self._dirty = True
        self._revision: object = None
        self._cached_prompt: str | None = None
        self._prompt_revision: object = None
        # The dictation thread and the API-server thread can reload concurrently;
        # guard the rebuild so readers never observe a half-rebuilt state.
        self._reload_lock = threading.Lock()
        self._ensure_loaded()

    def mark_dirty(self) -> None:
        """Signal that the database changed and the next call must reload."""
        self._dirty = True

    def _get_revision(self) -> object:
        getter = getattr(storage, "get_dictionary_revision", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None

    def _load_source_words(self) -> list[str]:
        # Auto-captured entries are intentionally excluded from the active
        # vocabulary. They were learned from polished text and are not user
        # authorization to rewrite future dictation.
        getter = getattr(storage, "get_dictionary_entries", None)
        if getter is not None:
            try:
                return [str(row["word"]) for row in getter(include_auto=False)]
            except Exception:
                log.exception("Could not load dictionary entries")
        return [str(word) for word in storage.get_dictionary_words()]

    def _load_prompt_words(self) -> list[str]:
        """All dictionary rows (including auto-learned) for Whisper prompt bias.

        Biasing only hints the decoder's spelling preferences; it never rewrites
        text. Auto-learned words therefore belong here even though they are
        excluded from post-processing rewrite rules.
        """
        getter = getattr(storage, "get_dictionary_entries", None)
        if getter is not None:
            try:
                return [str(row["word"]) for row in getter(include_auto=True)]
            except Exception:
                log.exception("Could not load dictionary entries")
        return self._load_source_words()

    def _ensure_loaded(self) -> None:
        with self._reload_lock:
            revision = self._get_revision()
            if not self._dirty and revision == self._revision:
                return

            words = self._load_source_words()
            rules: list[_Rule] = []
            seen: set[str] = set()
            for raw in words:
                trigger, expansion = _split_entry(raw.strip())
                if not trigger or (expansion is not None and not expansion):
                    # Empty snippet expansions are malformed and must never erase
                    # the trigger from dictated text.
                    continue
                key = trigger.casefold()
                if key in seen:
                    continue
                seen.add(key)
                rules.append(_Rule(trigger, expansion if expansion is not None else trigger, expansion is not None))

            # Longer triggers win. Casefold tie-breaking keeps behavior stable even
            # if SQLite returns rows in a different order.
            rules.sort(key=lambda rule: (-len(rule.trigger), rule.trigger.casefold(), rule.trigger))
            self.words = words
            self._rules = tuple(rules)
            self._revision = revision
            self._cached_prompt = None
            self._dirty = False

    def refresh_words(self) -> list[str]:
        self._dirty = True
        self._ensure_loaded()
        return self.words

    def get_initial_prompt(self) -> str:
        """Build a deterministic, bounded Whisper bias prompt from all terms.

        Cached until the dictionary revision changes so repeated dictations
        skip the prompt rebuild and its database revision read entirely.
        """
        with self._reload_lock:
            self._ensure_loaded()
            if self._cached_prompt is not None and self._prompt_revision == self._revision:
                return self._cached_prompt
            prompt_words = self._load_prompt_words()
            terms: list[str] = []
            seen: set[str] = set()
            for raw in prompt_words:
                trigger, _expansion = _split_entry(raw.strip())
                if not trigger:
                    continue
                key = trigger.casefold()
                if key in _STOPWORDS or len(trigger) < 2 or key in seen:
                    continue
                terms.append(trigger)
                seen.add(key)
            # Prefer longer technical phrases over arbitrary alphabetical rows.
            terms = sorted(terms, key=lambda term: (-len(term), term.casefold()))[:40]
            if not terms:
                prompt = "Clear dictation, accurate spelling, proper names."
            else:
                prompt = "Dictionary terms: " + ", ".join(terms) + "."
                log.info("Whisper initial_prompt biased with %d terms (incl. auto-learned)", len(terms))
            self._cached_prompt = prompt
            self._prompt_revision = self._revision
            return prompt

    @staticmethod
    def _apply_segment(segment: str, rules: tuple[_Rule, ...]) -> str:
        if not segment or not rules:
            return segment
        combined, usable_rules = _combined_pattern(rules)
        # One alternation/callback pass means an expansion is never considered
        # as new input for another rule during this dictation.
        def replace(match: re.Match[str]) -> str:
            for index, rule in enumerate(usable_rules, start=1):
                if match.group(index) is not None and _rule_matches(match, rule):
                    return rule.replacement
            return match.group(0)

        return combined.sub(replace, segment)

    def _apply_fuzzy_corrections(self, segment: str, fuzzy_targets: tuple[str, ...]) -> str:
        """Spell-correct misspelled dictated words against user vocabulary.

        Only applies when the dictation engine misheard a user-authored term:
        edit distance 1 (2 for long words), alphabetic token of 4+ chars, the
        token is not common English, and the match is unambiguous. Names like
        "Rohit" misheard as "Roheet" are fixed; everyday words are never touched.
        """
        if not segment or not fuzzy_targets:
            return segment

        def fix_word(match: re.Match[str]) -> str:
            token = match.group(0)
            lowered = token.casefold()
            if len(token) < 4 or lowered in _STOPWORDS or lowered in _COMMON_WORDS:
                return token
            best: str | None = None
            best_distance = 2 if len(token) >= 5 else 1
            for target in fuzzy_targets:
                target_fold = target.casefold()
                if target_fold == lowered:
                    return token
                # Derivational variants (plurals, -ing/-ed forms) are deliberate
                # speech, not mishearings: never "correct" VoiceFlow -> VoiceFlows.
                if lowered.startswith(target_fold) or target_fold.startswith(lowered):
                    continue
                if abs(len(target) - len(token)) > best_distance:
                    continue
                distance = _levenshtein(target_fold, lowered)
                if distance <= best_distance:
                    if best is None or distance < best_distance or (distance == best_distance and len(target) > len(best)):
                        best = target
                        best_distance = distance
            if best is not None:
                return best
            return token

        return re.sub(r"\b[A-Za-z]{4,}\b", fix_word, segment)

    def apply_dictionary_post_processing(self, text: str) -> str:
        """Apply explicit literal terms/snippets once, then conservative fuzzy correction."""
        if not text:
            return text
        self._ensure_loaded()
        if not self._rules:
            return text

        # Fuzzy matching is opt-in via setting; defaults to on but is very
        # conservative (edit-distance 1 on non-common words only).
        fuzzy_enabled = bool(storage.get_setting("dictionary_fuzzy_enabled", True))
        fuzzy_targets: tuple[str, ...] = ()
        if fuzzy_enabled:
            fuzzy_targets = tuple(
                rule.trigger
                for rule in self._rules
                if not rule.snippet
                and rule.trigger.isalpha()
                and len(rule.trigger) >= 4
                and rule.trigger.casefold() not in _STOPWORDS
                and rule.trigger.casefold() not in _COMMON_WORDS
            )

        # Split protected spans out so a term such as ``app`` cannot mutate a
        # URL or email address. The replacement callback keeps each expansion
        # literal, including backslashes and group-looking sequences.
        output: list[str] = []
        cursor = 0
        for protected in _PROTECTED_RE.finditer(text):
            chunk = self._apply_segment(text[cursor:protected.start()], self._rules)
            if fuzzy_targets:
                chunk = self._apply_fuzzy_corrections(chunk, fuzzy_targets)
            output.append(chunk)
            output.append(protected.group(0))
            cursor = protected.end()
        chunk = self._apply_segment(text[cursor:], self._rules)
        if fuzzy_targets:
            chunk = self._apply_fuzzy_corrections(chunk, fuzzy_targets)
        output.append(chunk)
        result = "".join(output)
        if result != text:
            log.info("Applied explicit dictionary rules to dictated text")
        return result


# Singleton instance
dictionary_engine = DictionaryEngine()
