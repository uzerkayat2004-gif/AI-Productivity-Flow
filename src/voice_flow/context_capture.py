"""Bounded, read-only UI Automation cursor context."""
from __future__ import annotations
from dataclasses import dataclass
import os
import threading
from urllib.parse import urlparse


@dataclass(frozen=True)
class CursorContext:
    before: str = ""
    selection: str = ""
    after: str = ""
    trustworthy: bool = False


_state_lock = threading.Lock()
_busy = False


def _owned_by_hwnd(uia, element, hwnd: int) -> bool:
    current = element
    walker = uia.iuia.ControlViewWalker
    for _ in range(40):
        if int(getattr(current, "CurrentNativeWindowHandle", 0) or 0) == int(hwnd): return True
        current = walker.GetParentElement(current)
        if current is None: return False
    return False


def _text_pattern_context(element, automation) -> CursorContext:
    """Read a single UIA TextPattern selection without string searching."""
    pattern = element.GetCurrentPattern(automation.UIA_TextPatternId)
    pattern = pattern.QueryInterface(automation.IUIAutomationTextPattern)
    selections = list(pattern.GetSelection())
    if len(selections) != 1: return CursorContext()
    selected = selections[0]
    selection = selected.GetText(200)
    before_range = selected.Clone(); before_range.Collapse(True)
    before_range.MoveEndpointByUnit(automation.TextPatternRangeEndpoint_Start, automation.TextUnit_Character, -200)
    before = before_range.GetText(200)
    after_range = selected.Clone(); after_range.Collapse(False)
    after_range.MoveEndpointByUnit(automation.TextPatternRangeEndpoint_End, automation.TextUnit_Character, 200)
    after = after_range.GetText(200)
    return CursorContext(before[-200:], selection[:200], after[:200], True)


def _uia_adapter(hwnd: int, *, uia_factory=None, automation=None) -> CursorContext:
    if os.name != "nt" and uia_factory is None: return CursorContext()
    try:
        if uia_factory is None:
            from pywinauto.uia_defines import IUIA
            from comtypes.gen import UIAutomationClient as automation
            uia_factory = IUIA
        uia = uia_factory()
        element = uia.iuia.GetFocusedElement()
        if element is None or not _owned_by_hwnd(uia, element, hwnd): return CursorContext()
        if bool(getattr(element, "CurrentIsPassword", False)): return CursorContext()
        return _text_pattern_context(element, automation)
    except Exception:
        return CursorContext()


def _browser_host_from_snapshot(uia, hwnd: int, automation) -> str | None:
    """Read only an address-bar ValuePattern and retain only its hostname."""
    try:
        root = uia.iuia.ElementFromHandle(hwnd)
        if root is None: return None
        names = {"address and search bar", "address bar"}
        for name in names:
            condition = uia.iuia.CreatePropertyCondition(automation.UIA_NamePropertyId, name)
            element = root.FindFirst(automation.TreeScope_Subtree, condition)
            if element is None or not _owned_by_hwnd(uia, element, hwnd): continue
            if int(getattr(element, "CurrentControlType", 0) or 0) != automation.UIA_EditControlTypeId: continue
            value = element.GetCurrentPattern(automation.UIA_ValuePatternId).QueryInterface(automation.IUIAutomationValuePattern).CurrentValue
            parsed = urlparse(value if "://" in value else "https://" + value)
            return parsed.hostname.lower() if parsed.hostname else None
    except Exception: pass
    return None


def capture_context_and_browser_host(hwnd: int | None, timeout_seconds: float = .08) -> tuple[CursorContext, str | None]:
    """One bounded UIA snapshot for text context and a safe browser hostname."""
    if not hwnd or os.name != "nt": return CursorContext(), None
    result: list[tuple[CursorContext, str | None]] = []
    def reader(_):
        try:
            from pywinauto.uia_defines import IUIA
            from comtypes.gen import UIAutomationClient as automation
            uia = IUIA(); element = uia.iuia.GetFocusedElement()
            context = CursorContext()
            if element is not None and _owned_by_hwnd(uia, element, hwnd) and not bool(getattr(element, "CurrentIsPassword", False)):
                context = _text_pattern_context(element, automation)
            result.append((context, _browser_host_from_snapshot(uia, hwnd, automation)))
            return context
        except Exception: return CursorContext()
    capture_cursor_context(hwnd, timeout_seconds, reader)
    return result[0] if result else (CursorContext(), None)


def _com_initialize():
    try:
        import comtypes
        comtypes.CoInitialize()
        return comtypes
    except Exception:
        return None


def _reset_for_tests() -> None:
    global _busy
    with _state_lock: _busy = False


def capture_cursor_context(hwnd: int | None, timeout_seconds: float = .08, adapter=None) -> CursorContext:
    """Run at most one read-only UIA call; timed out workers are never reused."""
    global _busy
    if not hwnd: return CursorContext()
    reader = adapter or _uia_adapter
    with _state_lock:
        if _busy: return CursorContext()
        _busy = True
    done, result = threading.Event(), []
    def run():
        global _busy
        com = _com_initialize()
        try:
            value = reader(hwnd)
            if isinstance(value, CursorContext): result.append(value)
        except Exception: pass
        finally:
            if com is not None:
                try: com.CoUninitialize()
                except Exception: pass
            with _state_lock: _busy = False
            done.set()
    threading.Thread(target=run, daemon=True, name="voice-flow-uia-context").start()
    if not done.wait(max(0, timeout_seconds)): return CursorContext()
    return result[0] if result else CursorContext()
