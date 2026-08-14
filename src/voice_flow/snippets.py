"""Separate saved-expansion engine.

Snippets use whitespace boundaries for sentence replacements. This deliberately
does not expand `@shortcut`, `(shortcut)`, or `shortcut,` in a longer sentence,
where punctuation often means the speaker intended literal text.
"""

from __future__ import annotations

import re
import threading

from voice_flow.storage import storage


class SnippetEngine:
    def __init__(self, store=storage) -> None:
        self.store = store
        self.snippets: list[dict] = []
        self._dirty = True
        self._revision = -1
        self._lock = threading.RLock()

    def mark_dirty(self) -> None:
        with self._lock:
            self._dirty = True

    def _ensure_loaded(self) -> None:
        with self._lock:
            get_snapshot = getattr(self.store, "get_snippet_snapshot", None)
            if get_snapshot is not None:
                try:
                    revision, snippets = get_snapshot()
                    if self._dirty or self._revision != revision:
                        self.snippets = snippets
                        self._dirty = False
                        self._revision = revision
                    return
                except Exception:
                    pass
            self.snippets = []

    def apply(self, text: str) -> str:
        if not text:
            return text
        self._ensure_loaded()
        if not self.snippets:
            return text
        # An exact punctuation-bearing trigger must win before the convenient
        # full-dictation terminal punctuation fallback is considered.
        for item in self.snippets:
            if text.casefold() == item.get("trigger", "").casefold():
                return item["expansion"]

        # The only punctuation exception is a punctuation-free full trigger,
        # after smart formatting may have appended one terminal punctuation.
        for item in self.snippets:
            trigger = item.get("trigger", "")
            if trigger and not trigger.endswith((".", "!", "?")) and re.fullmatch(
                re.escape(trigger) + r"([.!?])", text, re.IGNORECASE
            ):
                return item["expansion"]

        ordered = sorted([s for s in self.snippets if s.get("trigger")], key=lambda entry: len(entry["trigger"]), reverse=True)
        if not ordered:
            return text
        # One alternation makes replacements simultaneous: an expansion can
        # never become the input to another snippet in the same dictation.
        expansions = {item["trigger"].casefold(): item["expansion"] for item in ordered}
        alternatives = "|".join(re.escape(item["trigger"]) for item in ordered)
        pattern = re.compile(r"(?<!\S)(" + alternatives + r")(?!\S)", re.IGNORECASE)
        return pattern.sub(lambda match: expansions[match.group(1).casefold()], text)


snippet_engine = SnippetEngine()
