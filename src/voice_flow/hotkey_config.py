"""Shortcut validation and temporary capture leases, without desktop imports."""
from __future__ import annotations

import re
import threading
import time
from typing import Any

MODIFIERS = {
    'ctrl': 'ctrl', 'control': 'ctrl', 'alt': 'alt', 'menu': 'alt',
    'shift': 'shift', 'win': 'win', 'windows': 'win', 'super': 'win',
    'cmd': 'win', 'meta': 'win',
}
ALIASES = {
    'return': 'enter', 'esc': 'escape', 'caps_lock': 'capslock',
    'del': 'delete', 'page_up': 'pageup', 'page_down': 'pagedown',
    'scroll_lock': 'scrolllock', '`': 'backquote', '~': 'backquote',
    'tilde': 'backquote', 'arrowup': 'up', 'arrowdown': 'down',
    'arrowleft': 'left', 'arrowright': 'right', '-': 'minus', '+': 'plus', '=': 'plus',
    ',': 'comma', '.': 'period', '/': 'slash', '\\': 'backslash',
    ';': 'semicolon', "'": 'quote', '[': 'bracketleft', ']': 'bracketright',
}
VKS = {
    'space': 0x20, 'tab': 0x09, 'enter': 0x0D, 'escape': 0x1B,
    'capslock': 0x14, 'insert': 0x2D, 'delete': 0x2E, 'home': 0x24,
    'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22, 'backquote': 0xC0,
    'scrolllock': 0x91, 'pause': 0x13, 'backspace': 0x08,
    'minus': 0xBD, 'plus': 0xBB, 'comma': 0xBC, 'period': 0xBE,
    'slash': 0xBF, 'backslash': 0xDC, 'semicolon': 0xBA, 'quote': 0xDE,
    'bracketleft': 0xDB, 'bracketright': 0xDD,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'ctrl': 0x11, 'control': 0x11, 'alt': 0x12, 'shift': 0x10, 'win': 0x5B,
}


def key_vk(name: str | None) -> int | None:
    """Map supported key names to Win32 virtual keys without calling Win32."""
    normalized = str(name or '').lower().strip()
    normalized = ALIASES.get(normalized, normalized)
    if normalized in VKS:
        return VKS[normalized]
    if re.fullmatch(r'f(?:[1-9]|1[0-9]|2[0-4])', normalized):
        return 0x6F + int(normalized[1:])
    if len(normalized) == 1 and normalized.isascii() and normalized.isalnum():
        return ord(normalized.upper())
    return None


def parse_hotkey_string(raw: str | None) -> dict[str, Any]:
    """Validate one base key with modifiers; retain legacy hyphen aliases."""
    cleaned = str(raw or '').strip()
    double = bool(re.match(r'^double[ -]', cleaned, re.I))
    if double:
        cleaned = cleaned[7:].strip()
    # Separators must not consume a recorded literal plus or minus key.
    if cleaned == '+':
        cleaned = 'plus'
    elif cleaned == '-':
        cleaned = 'minus'
    elif cleaned.endswith('++'):
        cleaned = cleaned[:-1] + 'plus'
    elif cleaned.endswith('+-'):
        cleaned = cleaned[:-1] + 'minus'
    separator = r'\s*\+\s*' if '+' in cleaned else r'\s*-\s*'
    pieces = re.split(separator, cleaned)
    parts = [ALIASES.get(piece.strip().lower(), piece.strip().lower()) for piece in pieces]
    modifiers: set[str] = set()
    bases: list[str] = []
    error = None
    for part in parts:
        if not part:
            error = 'Complete the shortcut with a key or modifier.'
        elif part in MODIFIERS:
            modifier = MODIFIERS[part]
            if modifier in modifiers:
                error = 'Use each modifier only once.'
            modifiers.add(modifier)
        else:
            bases.append(part)
    if len(bases) > 1:
        error = 'Use one main key with optional modifiers.'
    if bases and any(key_vk(base) is None for base in bases):
        error = 'This key is not supported. Record another shortcut.'
    if not cleaned:
        error = 'Choose a shortcut.'
    base = bases[0] if len(bases) == 1 else None
    if base == 'escape':
        error = 'Escape is reserved to cancel dictation. Choose another shortcut.'
    labels = {'ctrl': 'Ctrl', 'alt': 'Alt', 'shift': 'Shift', 'win': 'Win'}
    canonical_parts = [labels[modifier] for modifier in labels if modifier in modifiers]
    if base:
        canonical_parts.append(base.upper() if len(base) == 1 or re.fullmatch(r'f\d+', base) else base.title())
    canonical = '+'.join(canonical_parts)
    if double:
        canonical = 'Double ' + canonical
    warnings = []
    typing_keys = {
        'minus', 'plus', 'comma', 'period', 'slash', 'backslash',
        'semicolon', 'quote', 'bracketleft', 'bracketright', 'backquote',
    }
    if not error and not modifiers and base and (len(base) == 1 or base in typing_keys):
        warnings.append('This shortcut intercepts normal typing; choose a modifier combination.')
    if not error and (
        base is None or 'win' in modifiers
        or (modifiers == {'alt'} and base in {'space', 'tab'})
        or (modifiers == {'ctrl'} and base in {'a', 'c', 'v', 'x', 'z', 's', 'f'})
    ):
        warnings.append('This shortcut may also be used by Windows or another app.')
    return {
        'raw': raw, 'is_double': double, 'modifiers': modifiers,
        'base_key': base, 'parts': parts, 'valid': error is None,
        'error': error, 'canonical': canonical, 'warnings': warnings,
    }


# Hook readers inspect one immutable tuple without waiting for any lock.
# Only settings API lease writers acquire the lock. Expiry needs no worker.
_capture_lock = threading.Lock()
_capture_lease: tuple[str, float] = ('', 0.0)
CAPTURE_TTL_SECONDS = 30.0


def shortcut_capture_active() -> bool:
    token, expiry = _capture_lease
    return bool(token and time.monotonic() < expiry)


def _begin_shortcut_capture(token: str) -> bool:
    global _capture_lease
    if not isinstance(token, str) or not token:
        return False
    with _capture_lock:
        if shortcut_capture_active() and _capture_lease[0] != token:
            return False
        _capture_lease = (token, time.monotonic() + CAPTURE_TTL_SECONDS)
        return True


def _renew_shortcut_capture(token: str) -> bool:
    global _capture_lease
    with _capture_lock:
        if not shortcut_capture_active() or _capture_lease[0] != token:
            return False
        _capture_lease = (token, time.monotonic() + CAPTURE_TTL_SECONDS)
        return True


def _end_shortcut_capture(token: str) -> bool:
    global _capture_lease
    with _capture_lock:
        if not token or _capture_lease[0] != token:
            return False
        _capture_lease = ('', 0.0)
        return True
