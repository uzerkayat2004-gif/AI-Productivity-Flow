"""Configurable assistant identity and activation phrases (VF-1 host layer).

The writing model has no name.  A *host* application decides what the user
says to address it ("Hey Voice Flow", "Hey Nova", "Okay Wispr", ...), and this
module turns that configuration into a matcher the reference command processor
(:mod:`voice_flow.voice_commands`) can use.

Design rules:

* Only phrases a developer configures can activate commands.  Company or
  product names that merely appear in dictation are never treated as wake
  phrases unless they were configured.
* ``enabled=False`` is plain dictation mode: the assistant name may be spoken
  freely and nothing is ever interpreted as a command.
* A *greeting phrase* ("hey nova") activates wherever it starts a clause.  The
  *bare name* ("nova, make this shorter") activates only at the start of a
  clause and only when an editing verb follows immediately, so "Nova shipped
  a new release" stays dictation.
* Hosts that already separate content from instructions do not need any wake
  phrase: they call :func:`voice_flow.voice_commands.parse_instruction` or
  build a VF-1 request directly (:mod:`voice_flow.vf_contract`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

# Words that, when they open a configured phrase, behave as a greeting prefix
# ("hey", "ok", "okay", "hi", "yo").  Everything after them is the name.
GREETING_WORDS = frozenset({"hey", "hi", "hello", "ok", "okay", "yo", "hay"})

# Verbs that may follow a bare assistant name for it to count as a command.
_EDIT_VERBS = (
    r"make|turn|use|write|create|change|rewrite|summari[sz]e|fix|shorten|clean|"
    r"polish|convert|generate|draft|format|simplify|tighten|expand|keep|remove|"
    r"translate|answer|send|reply|search|delete|don['’]?t|do\s+not"
)
BARE_NAME_CONTINUATION_RE = re.compile(
    rf"^\s*[,.:!\-—]?\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+(?:please\s+)?)?(?:{_EDIT_VERBS})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ActivationConfig:
    """How a host application lets the user address its assistant.

    ``assistant_name``: display name, also the bare-name trigger when
    ``allow_bare_name`` is true.  ``phrases``: full activation phrases.  When
    empty, ``hey|ok|okay <name>`` are derived.  ``aliases``: extra ASR
    renderings of the *name* only (e.g. "voiceflow", "vice flow").
    ``legacy_voice_flow``: use the historical Voice Flow matcher with its
    verified ASR aliases (the AI Productivity Flow default).
    """

    assistant_name: str = "Voice Flow"
    phrases: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    allow_bare_name: bool = True
    enabled: bool = True
    legacy_voice_flow: bool = False

    # ------------------------------------------------------------------
    @property
    def names(self) -> tuple[str, ...]:
        out = [self.assistant_name] + list(self.aliases)
        return tuple(dict.fromkeys(n.strip() for n in out if n and n.strip()))

    @property
    def all_phrases(self) -> tuple[str, ...]:
        if self.phrases:
            return tuple(p.strip() for p in self.phrases if p and p.strip())
        derived = []
        for name in self.names:
            for greeting in ("hey", "ok", "okay"):
                derived.append(f"{greeting} {name}")
        return tuple(derived)


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)?", text, flags=re.UNICODE)


def _name_pattern(name: str) -> str:
    """Regex for a (possibly multi-word) name, tolerant of ASR spacing/hyphens."""
    words = _words(name)
    if not words:
        return r"(?!x)x"
    if len(words) == 1:
        w = words[0]
        # "voiceflow" style single tokens may also be heard split; keep literal.
        return re.escape(w)
    return r"[\s\-]{0,3}".join(re.escape(w) for w in words)


def phrase_pattern(phrase: str) -> tuple[str, bool]:
    """Return (regex, has_greeting) for one configured phrase."""
    words = _words(phrase)
    if not words:
        return r"(?!x)x", False
    if words[0].casefold() in GREETING_WORDS and len(words) > 1:
        greeting = re.escape(words[0])
        rest = " ".join(words[1:])
        return rf"{greeting}\s*[,.:!\-—]?\s*{_name_pattern(rest)}", True
    return _name_pattern(phrase), False


@dataclass(frozen=True)
class WakeMatch:
    start: int
    end: int
    bare: bool


def compile_matchers(config: ActivationConfig) -> list[tuple[re.Pattern, bool]]:
    """(pattern, is_bare_name) pairs, longest phrases first."""
    pats: list[tuple[str, bool]] = []
    for phrase in sorted(config.all_phrases, key=len, reverse=True):
        rx, has_greeting = phrase_pattern(phrase)
        pats.append((rx, not has_greeting))
    if config.allow_bare_name:
        for name in sorted(config.names, key=len, reverse=True):
            pats.append((_name_pattern(name), True))
    compiled = []
    for rx, bare in pats:
        compiled.append((re.compile(rf"(?<![\w]){rx}(?![\w])", re.IGNORECASE), bare))
    return compiled


DEFAULT_ACTIVATION = ActivationConfig(
    assistant_name="Voice Flow",
    phrases=("hey voice flow", "ok voice flow", "okay voice flow"),
    aliases=(),
    allow_bare_name=True,
    enabled=True,
    legacy_voice_flow=True,
)


def activation_from_settings(get_setting) -> ActivationConfig:
    """Build the host configuration from app settings.

    Settings (all optional; defaults keep today's behavior):
      ``assistant_name``         str, default "Voice Flow"
      ``activation_phrases``     list[str] or comma-separated str
      ``voice_commands_enabled`` bool, default True (False = dictation mode)
    """
    try:
        name = str(get_setting("assistant_name", "") or "").strip()
        raw_phrases = get_setting("activation_phrases", "") or ""
        enabled_raw = get_setting("voice_commands_enabled", True)
    except Exception:
        return DEFAULT_ACTIVATION
    enabled = not (str(enabled_raw).strip().lower() in {"0", "false", "no", "off"})
    if isinstance(raw_phrases, str):
        phrases = tuple(p.strip() for p in raw_phrases.split(",") if p.strip())
    else:
        try:
            phrases = tuple(str(p).strip() for p in raw_phrases if str(p).strip())
        except TypeError:
            phrases = ()
    if (not name or name.casefold() == "voice flow") and not phrases:
        return replace(DEFAULT_ACTIVATION, enabled=enabled)
    return ActivationConfig(
        assistant_name=name or "Voice Flow",
        phrases=phrases,
        enabled=enabled,
        legacy_voice_flow=False,
    )
