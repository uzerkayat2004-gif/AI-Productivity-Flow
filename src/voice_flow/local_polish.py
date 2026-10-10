"""Routing for on-device Voice Flow polish models (S1-mini, Liquid LFM 2.5).

Each engine module exposes ``MODEL_ID``, ``is_model_ref``, ``is_downloaded``,
``polish`` and ``local_polish_allowance``.
"""
from __future__ import annotations

from types import ModuleType


def _engines() -> tuple[ModuleType, ...]:
    from voice_flow import lfm_engine, s1_engine

    # Preference order for the offline safety net: the purpose-built
    # normalizer first.
    return (s1_engine, lfm_engine)


def engine_for(model_ref: object) -> ModuleType | None:
    ref = str(model_ref or "")
    for engine in _engines():
        if engine.is_model_ref(ref):
            return engine
    return None


def is_local_polish_model_ref(model_ref: object) -> bool:
    return engine_for(model_ref) is not None


def polish_allowance(model_ref: object, word_count: int) -> float | None:
    """Seconds the selected local model may need, or ``None`` for a non-local selection."""
    engine = engine_for(model_ref)
    return engine.local_polish_allowance(word_count) if engine is not None else None


def safety_net_engine(selected_model: object, *, selected_attempted: bool) -> ModuleType | None:
    """The downloaded local model to try after the selected polish failed.

    A selected local model that already had its attempt is not run again,
    and no second local model is substituted for it.
    """
    selected = engine_for(selected_model)
    if selected is not None:
        if selected_attempted or not selected.is_downloaded():
            return None
        return selected
    for engine in _engines():
        if engine.is_downloaded():
            return engine
    return None
