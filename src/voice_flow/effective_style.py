"""Effective Style resolution for Voice Flow (spec §20, §45).

The application — never the AI model — decides which preference wins. The
resolver merges, in ascending priority:

1. system defaults
2. the saved Style profile for the effective category (``style_<category>``)
3. Auto Context (the base :class:`~voice_flow.style_engine.ResolvedStyle`
   already carries the Auto Context routing decision)
4. an explicit format command ("make this an email" activates the Email
   profile; it does NOT invent a tone)
5. temporary command overrides ("excited", "short", "keep my wording", …)

The output is one composed instruction string for the polishing model plus
metadata (target style id for deterministic formatting, whether AI is
required, a short UI label). Persistent changes ("always make my work
messages short") are applied by :func:`apply_persistent_change` and are
strictly separate from per-dictation overrides (spec §13, §47).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from voice_flow.storage import storage

log = logging.getLogger(__name__)

# Formats that map onto a saved Style profile category. Formats without a
# profile (note, bullet list, LinkedIn post) keep the caller's base profile
# and add a format instruction instead.
FORMAT_TO_CATEGORY: dict[str, str | None] = {
    "email": "email",
    "work_message": "work",
    "personal_message": "personal",
    "note": "other",
    "linkedin_post": "other",
    "bullet_list": "other",
    "prompt": None,
}

OVERRIDE_INSTRUCTIONS: dict[str, str] = {
    "tone:excited": "Use an excited, energetic tone.",
    "tone:casual": "Use a casual, relaxed tone.",
    "tone:friendly": "Use a friendly tone.",
    "tone:conversational": "Use a conversational tone.",
    "tone:confident": "Use a confident tone.",
    "tone:persuasive": "Use a persuasive tone.",
    "tone:playful": "Use a playful tone.",
    "formality:professional": "Keep the register professional.",
    "formality:formal": "Keep the register formal.",
    "length:short": "Be concise; keep the result short.",
    "length:detailed": "Expand with more detail where it helps.",
    "clarity:simplified": "Simplify the wording for easy reading.",
    "grammar:fix": "Correct grammar and punctuation.",
    "dedupe:remove": "Remove repetitive phrases.",
}

FORMAT_INSTRUCTIONS: dict[str, str] = {
    "note": "Format the result as a short note with a clear first line.",
    "bullet_list": "Format the result as a concise bullet list.",
    "linkedin_post": "Format the result as a LinkedIn post: hook, short paragraphs, no subject line.",
    "email": "Format the result as an email: greeting, body, sign-off.",
    "work_message": "Format the result as a workplace chat message: no subject line, no sign-off.",
    "personal_message": "Format the result as a personal message: natural, no formal structure.",
}

TASK_INSTRUCTIONS: dict[str, str] = {
    "summarize": "Summarize the transcript into its key points.",
}

PROMPT_MODE_INSTRUCTION = (
    "Turn the transcript into a well-structured prompt for an AI assistant. "
    "The transcript IS the user's task description: keep every requirement, "
    "detail, and constraint the user dictated, in the user's own terms. "
    "Organize it with clear labels (Objective, Context, Requirements, Expected output) "
    "ONLY where they genuinely fit — if the task is simple, a single clear instruction "
    "sentence is better than a skeleton. Fix grammar and vague phrasing, but NEVER "
    "change what the user is asking for, never invent requirements, never answer or "
    "execute the task, and never drop any detail the user dictated."
)

PRESERVE_WORDING_INSTRUCTION = (
    "Preserve the user's original wording as much as possible; fix only grammar, "
    "spelling, and formatting. Do not re-author the content."
)


@dataclass(frozen=True)
class EffectiveStyle:
    instruction: str          # composed instruction for the polishing model
    style_id: str             # style id for deterministic post-formatting
    category: str             # effective category
    format: str | None        # requested output format, if any
    task: str                 # "cleanup" | "rewrite" | "summarize" | "prompt"
    requires_ai: bool         # True when deterministic cleanup cannot satisfy it
    preserve_wording: bool
    label: str                # short UI label, e.g. "Email / Excited"


def _extra_instruction(category: str) -> str:
    try:
        extra = str(storage.get_setting(f"style_{category}_extra", "") or "")
    except Exception:
        return ""
    return extra.strip()


def _compose(parts: list[str]) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


def _profile_for_category(category: str) -> str | None:
    """Return the full saved card id for a category, including same-category commands."""
    try:
        from voice_flow import style_engine as style_engine_mod

        saved = str(
            style_engine_mod.storage.get_setting(
                f"style_{category}",
                style_engine_mod.CATEGORY_DEFAULTS.get(category, "other_formal"),
            )
            or ""
        ).strip()
        # Older settings may contain a short card name ("formal").
        if saved and not saved.startswith(f"{category}_"):
            candidate = f"{category}_{saved}"
            if candidate in style_engine_mod.STYLE_PRESETS:
                saved = candidate
        return saved or None
    except Exception:
        log.exception("[EFFECTIVE STYLE] could not load profile for %s", category)
        return None


def _explicit_register_profile(category: str, overrides: dict) -> str | None:
    """Choose the matching card for an explicit register command.

    A one-off "professional" or "casual" request has to control both the
    model instruction and deterministic post-formatting.  It therefore picks
    a card directly instead of retaining a contradictory saved card such as
    ``email_very_casual``.
    """
    suffix = None
    if overrides.get("formality") in ("professional", "formal"):
        suffix = "formal"
    elif overrides.get("tone") in ("casual", "friendly", "conversational"):
        suffix = "casual"
    if not suffix:
        return None
    candidate = f"{category}_{suffix}"
    try:
        from voice_flow.style_engine import STYLE_PRESETS

        return candidate if candidate in STYLE_PRESETS else None
    except Exception:
        return None


def resolve_effective_style(base, command) -> EffectiveStyle:
    """Merge the base (Auto Context + saved profile) resolution with a command.

    ``base`` is the session's :class:`ResolvedStyle`; ``command`` may be None
    (plain dictation). This function never raises on odd input by contract.
    """
    base_category = getattr(base, "category", "other") or "other"
    if not isinstance(base_category, str):
        base_category = str(base_category)
    base_style_id = getattr(base, "style_id", "other_formal") or "other_formal"
    if not isinstance(base_style_id, str):
        base_style_id = str(base_style_id)
    base_instruction = getattr(base, "instruction", "") or "Format text."
    if not isinstance(base_instruction, str):
        base_instruction = str(base_instruction)

    extra = _extra_instruction(base_category)

    if command is None:
        instruction = _compose([base_instruction, extra])
        return EffectiveStyle(
            instruction=instruction,
            style_id=base_style_id,
            category=base_category,
            format=None,
            task="cleanup",
            requires_ai=False,
            preserve_wording=False,
            label="",
        )

    fmt = getattr(command, "format", None)
    if not isinstance(fmt, str):
        fmt = None
    ctx = getattr(command, "context_reference", None)
    if not isinstance(ctx, str):
        ctx = None
    overrides = getattr(command, "overrides", {}) or {}
    if not hasattr(overrides, "get"):
        overrides = {}
    operation = getattr(command, "operation", "rewrite")
    if not isinstance(operation, str):
        operation = "rewrite"
    preserve_wording = bool(getattr(command, "preserve_wording", False))
    override_parts: list[str] = []
    profile_style_id: str | None = None
    effective_category = base_category

    # Priority 4: an explicit format command activates that format's saved
    # profile (spec §21) — tone stays out unless commanded (spec §27).
    target_category = FORMAT_TO_CATEGORY.get(fmt) if fmt else None
    if ctx and ctx in ("email", "work", "personal", "other"):
        # Priority 4b: "use my usual email/work/personal style" (spec §28).
        target_category = ctx
    if target_category:
        # Load the card even when the current Auto Context category happens
        # to match.  A generic "make this an email" must use the actual saved
        # Email card, rather than a possibly stale base resolution.
        profile_style_id = _profile_for_category(target_category)
        effective_category = target_category

    # Explicit register is a temporary, deterministic card selection.  This
    # keeps post-formatting in sync with the model instruction and never
    # mutates saved preferences.
    explicit_profile_id = _explicit_register_profile(effective_category, overrides)
    if explicit_profile_id:
        profile_style_id = explicit_profile_id

    parts: list[str] = [base_instruction]
    if profile_style_id:
        try:
            from voice_flow.style_engine import STYLE_INSTRUCTIONS

            parts = [STYLE_INSTRUCTIONS.get(profile_style_id, base_instruction)]
        except Exception:
            pass
    if fmt and fmt in FORMAT_INSTRUCTIONS:
        # Saved presets describe casing/punctuation; the format behaviour
        # (greeting/body/sign-off for an email, no subject for a work message)
        # is added explicitly so the profile + format stay composable (§16).
        override_parts.append(FORMAT_INSTRUCTIONS[fmt])

    task = "rewrite" if (fmt or overrides) else "cleanup"
    if operation == "summarize":
        task = "summarize"
        override_parts.append(TASK_INSTRUCTIONS["summarize"])
    elif operation == "prompt_generation":
        task = "prompt"
        override_parts.append(PROMPT_MODE_INSTRUCTION)

    for key in ("tone", "formality", "length", "clarity", "grammar", "dedupe"):
        value = overrides.get(key)
        if value:
            override_parts.append(OVERRIDE_INSTRUCTIONS.get(f"{key}:{value}", ""))
    if preserve_wording:
        override_parts.append(PRESERVE_WORDING_INSTRUCTION)

    # A saved standing instruction may itself demand lowercase/casual output.
    # Do not let it undo an explicit per-dictation professional/casual card.
    # Persistent commands still update storage separately in
    # ``apply_persistent_change``.
    effective_extra = "" if explicit_profile_id else (
        _extra_instruction(effective_category) if effective_category != base_category else extra
    )

    instruction = _compose(parts + [effective_extra] + override_parts)
    requires_ai = bool(
        fmt or overrides or ctx
        or operation in ("summarize", "prompt_generation")
        or preserve_wording
    )

    try:
        label = command.label()
    except Exception:
        label = ""

    return EffectiveStyle(
        instruction=instruction,
        style_id=profile_style_id or base_style_id,
        category=effective_category,
        format=fmt,
        task=task,
        requires_ai=requires_ai,
        preserve_wording=preserve_wording,
        label=label,
    )


# --------------------------------------------------------------------------
# Persistent changes (spec §13, §47) — explicit language only
# --------------------------------------------------------------------------


def apply_persistent_change(command) -> str | None:
    """Apply a persistent command ("always make my work messages short").

    Returns a short description of what changed, or None when nothing
    qualified. Never touches anything without ``persistent_change``.
    """
    if command is None or not getattr(command, "persistent_change", False):
        return None

    fmt = getattr(command, "format", None)
    if not isinstance(fmt, str):
        fmt = None
    context_reference = getattr(command, "context_reference", None)
    if not isinstance(context_reference, str):
        context_reference = None
    overrides = getattr(command, "overrides", {}) or {}
    if not hasattr(overrides, "get"):
        overrides = {}
    target = context_reference or FORMAT_TO_CATEGORY.get(fmt or "")
    if target not in ("email", "work", "personal", "other"):
        return None

    changed: list[str] = []
    tone = overrides.get("tone")
    formality = overrides.get("formality")

    # A tone/formality word that matches a saved preset switches the profile.
    preset_suffix = None
    if formality in ("formal", "professional"):
        preset_suffix = "formal"
    elif tone == "excited":
        preset_suffix = "excited"
    elif tone in ("casual", "friendly", "conversational"):
        preset_suffix = "casual"

    if preset_suffix:
        preset_id = f"{target}_{preset_suffix}"
        try:
            from voice_flow.style_engine import STYLE_PRESETS

            if preset_id in STYLE_PRESETS:
                if storage.save_setting(f"style_{target}", preset_id):
                    changed.append(f"{target} style -> {preset_suffix}")
                else:
                    log.warning("[PERSISTENT] did not save %s preset", target)
        except Exception:
            log.exception("[PERSISTENT] could not save %s preset", target)

    # Property overrides that no preset captures become standing instructions.
    standing: list[str] = []
    for key in ("length", "clarity", "dedupe", "grammar"):
        value = overrides.get(key)
        if not value:
            continue
        sentence = OVERRIDE_INSTRUCTIONS.get(f"{key}:{value}")
        if sentence and sentence not in standing:
            standing.append(sentence)
    if standing:
        try:
            key_name = f"style_{target}_extra"
            existing = str(storage.get_setting(key_name, "") or "").strip()
            merged = existing
            for sentence in standing:
                if sentence.lower() not in merged.lower():
                    merged = _compose([merged, sentence])
            if merged != existing:
                if storage.save_setting(key_name, merged):
                    changed.append(f"{target} standing instruction updated")
                else:
                    log.warning("[PERSISTENT] did not save %s standing instruction", target)
            else:
                changed.append(f"{target} standing instruction already saved")
        except Exception:
            log.exception("[PERSISTENT] could not save %s standing instruction", target)

    if not changed:
        return None
    return "; ".join(changed)
