"""Low-level macOS framework bindings via ctypes.

Voice Flow needs four things from the macOS system layer:

  1. Synthesize keyboard chords (Cmd+V / Cmd+C / Return)     -> CoreGraphics
  2. Probe Accessibility trust                               -> ApplicationServices
  3. Probe Input Monitoring + Microphone authorization        -> IOKit + AVFoundation
  4. Read the frontmost window's owner app                    -> CoreGraphics + CoreFoundation

All four are reachable through plain ``ctypes`` calls against frameworks that
ship with every macOS install. That matters: it means the macOS backend works
on a bare ``pip install`` with **no PyObjC dependency**, which keeps the
install footprint identical to Windows.

Every symbol is resolved lazily and cached. If a framework or symbol is missing
(future macOS rename, hardened runtime quirk) the accessor returns ``None`` and
the caller degrades instead of crashing.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

IS_MACOS = sys.platform == "darwin"

# ---------------------------------------------------------------------------
# Constants (from the macOS SDK headers)
# ---------------------------------------------------------------------------

# CoreGraphics event taps
kCGHIDEventTap = 0
kCGSessionEventTap = 1
kCGAnnotatedSessionEventTap = 2

# CoreGraphics modifier flags
kCGEventFlagMaskShift = 0x00020000
kCGEventFlagMaskControl = 0x00040000
kCGEventFlagMaskAlternate = 0x00080000
kCGEventFlagMaskCommand = 0x00100000

# Virtual key codes (HIToolbox/Events.h) — US ANSI layout
KEY_C = 0x08
KEY_V = 0x09
KEY_RETURN = 0x24
KEY_TAB = 0x30
KEY_ESCAPE = 0x35

# AXIsProcessTrustedWithOptions dictionary keys
kAXTrustedCheckOptionPrompt = b"AXTrustedCheckOptionPrompt"

# IOKit access probe
kIOHIDRequestTypeListenEvent = 1
kIOHIDRequestTypePostEvent = 2
IOHID_ACCESS_GRANTED = 0
IOHID_ACCESS_DENIED = 1
IOHID_ACCESS_UNKNOWN = 2

# AVFoundation authorization status
AV_STATUS_NOT_DETERMINED = 0
AV_STATUS_RESTRICTED = 1
AV_STATUS_DENIED = 2
AV_STATUS_AUTHORIZED = 3

# CoreGraphics window list options
kCGWindowListOptionOnScreenOnly = 1 << 0
kCGWindowListExcludeDesktopElements = 1 << 4
kCGNullWindowID = 0

# CoreFoundation
kCFStringEncodingUTF8 = 0x08000100
kCFNumberIntType = 9

_FRAMEWORK_PATHS = {
    "CoreGraphics": "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics",
    "ApplicationServices": "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices",
    "CoreFoundation": "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
    "IOKit": "/System/Library/Frameworks/IOKit.framework/IOKit",
    "AVFoundation": "/System/Library/Frameworks/AVFoundation.framework/AVFoundation",
    "Foundation": "/System/Library/Frameworks/Foundation.framework/Foundation",
    "objc": "/usr/lib/libobjc.A.dylib",
}


class _Loader:
    """Lazy, cached framework/symbol resolver."""

    def __init__(self) -> None:
        self._handles: dict[str, Any] = {}
        self._symbols: dict[tuple[str, str], Any] = {}
        self._failed: set[str] = set()

    def framework(self, name: str) -> Any | None:
        if not IS_MACOS:
            return None
        if name in self._handles:
            return self._handles[name]
        if name in self._failed:
            return None
        path = _FRAMEWORK_PATHS.get(name) or ctypes.util.find_library(name)
        if not path:
            log.debug("[MACOS] framework %s not found", name)
            self._failed.add(name)
            return None
        try:
            handle = ctypes.CDLL(path)
        except OSError as exc:
            log.debug("[MACOS] framework %s failed to load: %s", name, exc)
            self._failed.add(name)
            return None
        self._handles[name] = handle
        return handle

    def symbol(self, framework: str, name: str, *, optional: bool = False) -> Any | None:
        key = (framework, name)
        if key in self._symbols:
            return self._symbols[key]
        handle = self.framework(framework)
        if handle is None:
            if not optional:
                log.debug("[MACOS] %s.%s unavailable (framework missing)", framework, name)
            return None
        try:
            func = getattr(handle, name)
        except AttributeError:
            if not optional:
                log.debug("[MACOS] symbol %s.%s not present", framework, name)
            return None
        self._symbols[key] = func
        return func

    def data_symbol(self, framework: str, name: str, *, optional: bool = False) -> int | None:
        handle = self.framework(framework)
        if handle is None:
            return None
        try:
            return ctypes.c_void_p.in_dll(handle, name).value
        except (AttributeError, ValueError) as exc:
            if not optional:
                log.debug("[MACOS] data symbol %s.%s not present: %s", framework, name, exc)
            return None


_loader = _Loader()


def available() -> bool:
    """True when the macOS framework layer is usable at all."""
    return IS_MACOS and _loader.framework("CoreGraphics") is not None


# ---------------------------------------------------------------------------
# CoreFoundation helpers
# ---------------------------------------------------------------------------


def _cf() -> Any | None:
    return _loader.framework("CoreFoundation")


def cfstring_from_python(text: str) -> int:
    """Create a CFStringRef from a Python str (caller owns a reference)."""
    core_foundation = _cf()
    if core_foundation is None:
        return 0
    fn = _loader.symbol("CoreFoundation", "CFStringCreateWithCString")
    if fn is None:
        return 0
    fn.restype = ctypes.c_void_p
    fn.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    return fn(None, text.encode("utf-8"), kCFStringEncodingUTF8) or 0


def cfstring_to_python(ref: int) -> str:
    """Convert a CFStringRef to a Python str. Does not release ``ref``."""
    if not ref:
        return ""
    core_foundation = _cf()
    if core_foundation is None:
        return ""
    length_fn = _loader.symbol("CoreFoundation", "CFStringGetLength")
    get_fn = _loader.symbol("CoreFoundation", "CFStringGetCString")
    if length_fn is None or get_fn is None:
        return ""
    length_fn.restype = ctypes.c_long
    length_fn.argtypes = [ctypes.c_void_p]
    get_fn.restype = ctypes.c_bool
    get_fn.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    length = length_fn(ref)
    if length <= 0:
        return ""
    buf = ctypes.create_string_buffer((length * 4) + 1)
    if not get_fn(ref, buf, len(buf), kCFStringEncodingUTF8):
        return ""
    return buf.value.decode("utf-8", errors="replace")


def cf_is_string(ref: int) -> bool:
    """True when ``ref`` is a CFStringRef (guards AX values of other types)."""
    if not ref:
        return False
    type_fn = _loader.symbol("CoreFoundation", "CFGetTypeID", optional=True)
    str_type_fn = _loader.symbol("CoreFoundation", "CFStringGetTypeID", optional=True)
    if type_fn is None or str_type_fn is None:
        return False
    type_fn.restype = ctypes.c_ulong
    type_fn.argtypes = [ctypes.c_void_p]
    str_type_fn.restype = ctypes.c_ulong
    str_type_fn.argtypes = []
    try:
        return int(type_fn(ref)) == int(str_type_fn())
    except Exception:
        return False


def cf_release(ref: int) -> None:
    if not ref:
        return
    fn = _loader.symbol("CoreFoundation", "CFRelease", optional=True)
    if fn is not None:
        fn.argtypes = [ctypes.c_void_p]
        fn(ref)


def cfbool(value: bool) -> int:
    """Create a CFBooleanRef (constants, not owned)."""
    sym = "kCFBooleanTrue" if value else "kCFBooleanFalse"
    ptr = _loader.data_symbol("CoreFoundation", sym, optional=True)
    return ptr or 0


class _CFDictionaryKeyCallBacks(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_long),
        ("retain", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("copyDescription", ctypes.c_void_p),
        ("equal", ctypes.c_void_p),
        ("hash", ctypes.c_void_p),
    ]


class _CFDictionaryValueCallBacks(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_long),
        ("retain", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("copyDescription", ctypes.c_void_p),
        ("equal", ctypes.c_void_p),
    ]


def cf_dictionary(pairs: list[tuple[int, int]]) -> int:
    """Build a CFDictionaryRef from (key, value) raw pointers."""
    if not pairs or any(not key or not value for key, value in pairs):
        # AX calls CFGetTypeID on option values: never pass NULL CF objects.
        return 0
    core_foundation = _cf()
    if core_foundation is None:
        return 0
    try:
        key_callbacks = _CFDictionaryKeyCallBacks.in_dll(
            core_foundation, "kCFTypeDictionaryKeyCallBacks"
        )
        value_callbacks = _CFDictionaryValueCallBacks.in_dll(
            core_foundation, "kCFTypeDictionaryValueCallBacks"
        )
    except (ValueError, AttributeError, OSError):
        # Without CF object equality and ownership, this is not a CF dictionary
        # that framework clients can safely consume.
        return 0
    fn = _loader.symbol("CoreFoundation", "CFDictionaryCreate")
    if fn is None:
        return 0
    fn.restype = ctypes.c_void_p
    fn.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    keys = (ctypes.c_void_p * len(pairs))(*[ctypes.c_void_p(k) for k, _ in pairs])
    values = (ctypes.c_void_p * len(pairs))(*[ctypes.c_void_p(v) for _, v in pairs])
    # CFString keys must compare by content, not pointer identity. The CFType
    # callbacks also retain keys/values for the lifetime of the dictionary.
    return fn(
        None, keys, values, len(pairs),
        ctypes.byref(key_callbacks), ctypes.byref(value_callbacks),
    ) or 0


# ---------------------------------------------------------------------------
# CoreGraphics — synthetic keyboard events
# ---------------------------------------------------------------------------


def _new_key_event(keycode: int, key_down: bool) -> int:
    fn = _loader.symbol("CoreGraphics", "CGEventCreateKeyboardEvent")
    if fn is None:
        return 0
    fn.restype = ctypes.c_void_p
    fn.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    return fn(None, keycode, key_down) or 0


def _set_event_flags(event: int, flags: int) -> None:
    fn = _loader.symbol("CoreGraphics", "CGEventSetFlags")
    if fn is None:
        return
    fn.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    fn(event, flags)


def _post_event(event: int, tap: int = kCGHIDEventTap) -> None:
    fn = _loader.symbol("CoreGraphics", "CGEventPost")
    if fn is None:
        return
    fn.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    fn(tap, event)


def _event_flags() -> int:
    fn = _loader.symbol("CoreGraphics", "CGEventGetFlags", optional=True)
    if fn is None:
        return 0
    fn.restype = ctypes.c_uint64
    fn.argtypes = [ctypes.c_void_p]
    return 0  # no source event to query without a tap


kCGEventSourceStateCombinedSessionState = 0
_MODIFIER_MASK = (
    kCGEventFlagMaskShift | kCGEventFlagMaskControl | kCGEventFlagMaskAlternate | kCGEventFlagMaskCommand
)


def current_modifier_flags() -> int:
    """Modifier keys the user is physically holding right now (CGEventFlags)."""
    if not IS_MACOS:
        return 0
    fn = _loader.symbol("CoreGraphics", "CGEventSourceFlagsState", optional=True)
    if fn is None:
        return 0
    fn.restype = ctypes.c_uint64
    fn.argtypes = [ctypes.c_int32]
    try:
        return int(fn(kCGEventSourceStateCombinedSessionState)) & _MODIFIER_MASK
    except Exception:
        return 0


def wait_for_modifiers_released(timeout: float = 1.0) -> bool:
    """Wait until no modifier key is held (e.g. after a Ctrl+Option+L hotkey).

    A synthetic Cmd+C sent while the user still holds Ctrl+Option reaches the
    app as Cmd+Ctrl+Option+C and copies nothing. Returns True when released."""
    import time

    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if not current_modifier_flags():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def send_key_combo(keycode: int, flags: int = 0, *, key_delay: float = 0.012) -> bool:
    """Post a key chord such as Cmd+V (keycode=KEY_V, flags=kCGEventFlagMaskCommand).

    Sends a modifier-less keyDown/keyUp pair carrying the modifier *flags*,
    which is how CGEvent models chords. Never raises.
    """
    if not IS_MACOS:
        return False
    import time

    down = _new_key_event(keycode, True)
    up = _new_key_event(keycode, False)
    if not down or not up:
        cf_release(down)
        cf_release(up)
        return False
    try:
        if flags:
            _set_event_flags(down, flags)
            _set_event_flags(up, flags)
        _post_event(down)
        time.sleep(key_delay)
        _post_event(up)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[MACOS] send_key_combo failed: %s", exc)
        return False
    finally:
        cf_release(down)
        cf_release(up)


def send_return_key() -> bool:
    return send_key_combo(KEY_RETURN)


# ---------------------------------------------------------------------------
# CoreGraphics — frontmost window owner
# ---------------------------------------------------------------------------


def frontmost_window_owner() -> dict[str, Any]:
    """Return {'app': str, 'title': str, 'pid': int} for the frontmost window.

    Uses ``CGWindowListCopyWindowInfo`` restricted to on-screen layer-0 windows
    and takes the first entry, which is the frontmost window. This needs **no**
    Accessibility or Automation permission, unlike an AppleScript query.

    Returns an empty dict when the information is unavailable.
    """
    if not IS_MACOS:
        return {}
    list_fn = _loader.symbol("CoreGraphics", "CGWindowListCopyWindowInfo")
    if list_fn is None:
        return {}
    list_fn.restype = ctypes.c_void_p
    list_fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32]

    count_fn = _loader.symbol("CoreFoundation", "CFArrayGetCount")
    at_fn = _loader.symbol("CoreFoundation", "CFArrayGetValueAtIndex")
    dict_get_fn = _loader.symbol("CoreFoundation", "CFDictionaryGetValue")
    if count_fn is None or at_fn is None or dict_get_fn is None:
        return {}

    count_fn.restype = ctypes.c_long
    count_fn.argtypes = [ctypes.c_void_p]
    at_fn.restype = ctypes.c_void_p
    at_fn.argtypes = [ctypes.c_void_p, ctypes.c_long]
    dict_get_fn.restype = ctypes.c_void_p
    dict_get_fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    # Constant CFStringRef keys exported by CoreGraphics.
    key_names = {
        "owner": b"kCGWindowOwnerName",
        "title": b"kCGWindowName",
        "pid": b"kCGWindowOwnerPID",
        "layer": b"kCGWindowLayer",
    }
    key_refs: dict[str, int] = {}
    for label, symbol_name in key_names.items():
        val = _loader.data_symbol("CoreGraphics", symbol_name.decode(), optional=True)
        key_refs[label] = val or 0

    arr = list_fn(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID)
    if not arr:
        return {}
    try:
        total = count_fn(arr)
        # Scan the whole list: menu-bar extras, the Dock, our own floating bar,
        # widget, menu and toasts all sit above layer 0, and with enough of
        # them (macOS 14 runner, Oct 2026) the first 20 entries held no normal
        # window at all -- focus restore and AX reads then silently gave up.
        for index in range(min(total, 1000)):
            entry = at_fn(arr, index)
            if not entry:
                continue

            def _string(key: str) -> str:
                ref = key_refs.get(key)
                if not ref:
                    return ""
                value = dict_get_fn(entry, ctypes.c_void_p(ref))
                return cfstring_to_python(value) if value else ""

            layer_ref = key_refs.get("layer")
            layer = 0
            if layer_ref:
                value = dict_get_fn(entry, ctypes.c_void_p(layer_ref))
                if value:
                    get_int = _loader.symbol("CoreFoundation", "CFNumberGetValue", optional=True)
                    if get_int is not None:
                        get_int.restype = ctypes.c_bool
                        get_int.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
                        out = ctypes.c_int(0)
                        if get_int(value, kCFNumberIntType, ctypes.byref(out)):
                            layer = out.value
            # Layer 0 == normal application window. Skip menu bar / Dock / overlays.
            if layer != 0:
                continue
            app = _string("owner")
            title = _string("title")
            if not app:
                continue
            pid = 0
            pid_ref = key_refs.get("pid")
            if pid_ref:
                value = dict_get_fn(entry, ctypes.c_void_p(pid_ref))
                if value:
                    get_int = _loader.symbol("CoreFoundation", "CFNumberGetValue", optional=True)
                    if get_int is not None:
                        get_int.restype = ctypes.c_bool
                        get_int.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
                        out = ctypes.c_int(0)
                        if get_int(value, kCFNumberIntType, ctypes.byref(out)):
                            pid = out.value
            return {"app": app, "title": title, "pid": pid}
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[MACOS] frontmost_window_owner failed: %s", exc)
    finally:
        cf_release(arr)
    return {}


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


def window_owner_at_point(x: float, y: float, only_pids: set[int] | None = None) -> dict[str, Any]:
    """Return {'app', 'pid', 'layer'} of the topmost on-screen window under (x, y).

    Coordinates are global display points with a top-left origin (the same
    space Quartz mouse events and Tk use). Needs no permission. With
    ``only_pids`` only windows of those processes are considered. Used to tell
    whether a click landed on one of our own floating windows without calling
    into Tk from a background thread. Returns {} when unknown.
    """
    if not IS_MACOS:
        return {}
    list_fn = _loader.symbol("CoreGraphics", "CGWindowListCopyWindowInfo")
    rect_fn = _loader.symbol("CoreGraphics", "CGRectMakeWithDictionaryRepresentation", optional=True)
    count_fn = _loader.symbol("CoreFoundation", "CFArrayGetCount")
    at_fn = _loader.symbol("CoreFoundation", "CFArrayGetValueAtIndex")
    dict_get_fn = _loader.symbol("CoreFoundation", "CFDictionaryGetValue")
    num_fn = _loader.symbol("CoreFoundation", "CFNumberGetValue", optional=True)
    if None in (list_fn, rect_fn, count_fn, at_fn, dict_get_fn, num_fn):
        return {}
    list_fn.restype = ctypes.c_void_p
    list_fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    rect_fn.restype = ctypes.c_bool
    rect_fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(_CGRect)]
    count_fn.restype = ctypes.c_long
    count_fn.argtypes = [ctypes.c_void_p]
    at_fn.restype = ctypes.c_void_p
    at_fn.argtypes = [ctypes.c_void_p, ctypes.c_long]
    dict_get_fn.restype = ctypes.c_void_p
    dict_get_fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    num_fn.restype = ctypes.c_bool
    num_fn.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]

    keys = {
        name: _loader.data_symbol("CoreGraphics", sym, optional=True) or 0
        for name, sym in (
            ("bounds", "kCGWindowBounds"),
            ("pid", "kCGWindowOwnerPID"),
            ("owner", "kCGWindowOwnerName"),
            ("layer", "kCGWindowLayer"),
        )
    }
    if not keys["bounds"] or not keys["pid"]:
        return {}

    def _int(entry: int, key: str) -> int:
        ref = keys.get(key)
        if not ref:
            return 0
        value = dict_get_fn(entry, ctypes.c_void_p(ref))
        out = ctypes.c_int(0)
        if value and num_fn(value, kCFNumberIntType, ctypes.byref(out)):
            return out.value
        return 0

    arr = list_fn(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID)
    if not arr:
        return {}
    try:
        for index in range(min(count_fn(arr), 200)):
            entry = at_fn(arr, index)
            if not entry:
                continue
            bounds = dict_get_fn(entry, ctypes.c_void_p(keys["bounds"]))
            rect = _CGRect()
            if not bounds or not rect_fn(bounds, ctypes.byref(rect)):
                continue
            if not (rect.origin.x <= x <= rect.origin.x + rect.size.width
                    and rect.origin.y <= y <= rect.origin.y + rect.size.height):
                continue
            if only_pids is not None and _int(entry, "pid") not in only_pids:
                # e.g. the Dock owns an invisible full-screen window above
                # floating windows; callers asking "is this one of ours?" pass
                # their pids and skip everything else.
                continue
            owner = ""
            if keys["owner"]:
                ref = dict_get_fn(entry, ctypes.c_void_p(keys["owner"]))
                owner = cfstring_to_python(ref) if ref else ""
            return {"app": owner, "pid": _int(entry, "pid"), "layer": _int(entry, "layer")}
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[MACOS] window_owner_at_point failed: %s", exc)
    finally:
        cf_release(arr)
    return {}


# ---------------------------------------------------------------------------
# ApplicationServices — Accessibility trust
# ---------------------------------------------------------------------------


def accessibility_trusted(prompt: bool = False) -> bool:
    """True when this process is trusted for Accessibility (AX) control.

    ``prompt=True`` asks macOS to show the "…would like to control this
    computer" dialog. That dialog only appears once per app identity, so the
    onboarding screen should use ``prompt=False`` for status polling and
    ``prompt=True`` only when the user clicks the grant button.
    """
    if not IS_MACOS:
        return False
    if not prompt:
        fn = _loader.symbol("ApplicationServices", "AXIsProcessTrusted", optional=True)
        if fn is None:
            return False
        fn.restype = ctypes.c_ubyte
        try:
            return bool(fn())
        except Exception:
            return False

    fn = _loader.symbol("ApplicationServices", "AXIsProcessTrustedWithOptions", optional=True)
    if fn is None:
        return False
    fn.restype = ctypes.c_ubyte
    fn.argtypes = [ctypes.c_void_p]
    key = cfstring_from_python(kAXTrustedCheckOptionPrompt.decode())
    if not key:
        return False
    try:
        options = cf_dictionary([(key, cfbool(True))])
        if not options:
            return False
        try:
            return bool(fn(options))
        finally:
            cf_release(options)
    except Exception as exc:
        log.debug("[MACOS] accessibility prompt failed: %s", exc)
        return False
    finally:
        cf_release(key)


def preflight_post_event_access() -> bool:
    """CGPreflightPostEventAccess(): the live "may post events" TCC check."""
    if not IS_MACOS:
        return False
    fn = _loader.symbol("CoreGraphics", "CGPreflightPostEventAccess", optional=True)
    if fn is None:
        return False
    fn.restype = ctypes.c_bool
    fn.argtypes = []
    try:
        return bool(fn())
    except Exception:
        return False


def can_post_events() -> bool:
    """True when synthetic key events (Cmd+V / Cmd+C) will actually reach apps.

    macOS silently drops ``CGEventPost`` events from a process that has neither
    Accessibility trust nor the "post events" grant, while the call itself
    still "succeeds". Callers must check this before claiming a paste worked.
    """
    if not IS_MACOS:
        return False
    return accessibility_trusted(prompt=False) or preflight_post_event_access()


# ---------------------------------------------------------------------------
# IOKit — Input Monitoring
# ---------------------------------------------------------------------------


def input_monitoring_status() -> int:
    """Raw IOHID access status for listening to input events.

    ``IOHID_ACCESS_GRANTED`` / ``IOHID_ACCESS_DENIED`` / ``IOHID_ACCESS_UNKNOWN``.
    Returns ``IOHID_ACCESS_UNKNOWN`` when IOKit is unavailable.
    """
    if not IS_MACOS:
        return IOHID_ACCESS_UNKNOWN
    fn = _loader.symbol("IOKit", "IOHIDCheckAccess", optional=True)
    if fn is None:
        return IOHID_ACCESS_UNKNOWN
    fn.restype = ctypes.c_uint32
    fn.argtypes = [ctypes.c_uint32]
    try:
        return int(fn(kIOHIDRequestTypeListenEvent))
    except Exception:
        return IOHID_ACCESS_UNKNOWN


def request_input_monitoring() -> int:
    """Trigger the Input Monitoring prompt. Returns the resulting status."""
    if not IS_MACOS:
        return IOHID_ACCESS_UNKNOWN
    fn = _loader.symbol("IOKit", "IOHIDRequestAccess", optional=True)
    if fn is None:
        return input_monitoring_status()
    fn.restype = ctypes.c_bool
    fn.argtypes = [ctypes.c_uint32]
    try:
        fn(kIOHIDRequestTypeListenEvent)
    except Exception:
        pass
    return input_monitoring_status()


# ---------------------------------------------------------------------------
# AVFoundation — Microphone authorization
# ---------------------------------------------------------------------------


def microphone_status() -> int | None:
    """AVAuthorizationStatus for audio capture, or None when unobtainable.

    Uses the Objective-C runtime, so it does not require PyObjC.
    """
    if not IS_MACOS:
        return None
    objc = _loader.framework("objc")
    av = _loader.framework("AVFoundation")
    if objc is None or av is None:
        return None
    try:
        get_class = objc.objc_getClass
        get_class.restype = ctypes.c_void_p
        get_class.argtypes = [ctypes.c_char_p]
        sel_register = objc.sel_registerName
        sel_register.restype = ctypes.c_void_p
        sel_register.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend
        send.restype = ctypes.c_long
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

        cls = get_class(b"AVCaptureDevice")
        if not cls:
            return None
        sel = sel_register(b"authorizationStatusForMediaType:")
        if not sel:
            return None
        # AVMediaTypeAudio is an exported NSString* constant.
        media_type = _loader.data_symbol("AVFoundation", "AVMediaTypeAudio", optional=True)
        if not media_type:
            return None
        return int(send(cls, sel, ctypes.c_void_p(media_type)))
    except Exception as exc:
        log.debug("[MACOS] microphone_status failed: %s", exc)
        return None


def request_microphone_access(callback: Any = None) -> bool:
    """Trigger the microphone permission prompt (non-blocking)."""
    if not IS_MACOS:
        return False
    objc = _loader.framework("objc")
    av = _loader.framework("AVFoundation")
    if objc is None or av is None:
        return False
    try:
        get_class = objc.objc_getClass
        get_class.restype = ctypes.c_void_p
        get_class.argtypes = [ctypes.c_char_p]
        sel_register = objc.sel_registerName
        sel_register.restype = ctypes.c_void_p
        sel_register.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

        cls = get_class(b"AVCaptureDevice")
        if not cls:
            return False
        sel = sel_register(b"requestAccessForMediaType:completionHandler:")
        if not sel:
            return False
        media_type = _loader.data_symbol("AVFoundation", "AVMediaTypeAudio", optional=True)
        if not media_type:
            return False
        # A NULL block is acceptable: macOS still shows the prompt, we simply
        # poll the status afterwards instead of receiving the callback.
        send(cls, sel, ctypes.c_void_p(media_type), None)
        return True
    except Exception as exc:
        log.debug("[MACOS] request_microphone_access failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# ApplicationServices — focused UI element selected text (Accessibility API)
# ---------------------------------------------------------------------------


# AXError codes (HIServices/AXError.h)
kAXErrorSuccess = 0
kAXErrorAttributeUnsupported = -25205
kAXErrorNoValue = -25212


def focused_selection_info() -> dict[str, Any]:
    """Accessibility view of the focused element's selection.

    Returns ``{"trusted": bool, "status": int | None, "role": str, "text": str}``.
    ``status`` is the AXError of the ``AXSelectedText`` read (0 = the element
    answered, even if the selection is empty); ``None`` when no focused element
    could be read at all. Never raises.
    """
    info: dict[str, Any] = {"trusted": False, "status": None, "role": "", "text": ""}
    if not IS_MACOS:
        return info
    if not accessibility_trusted():
        return info
    info["trusted"] = True
    create_fn = _loader.symbol("ApplicationServices", "AXUIElementCreateSystemWide", optional=True)
    copy_fn = _loader.symbol("ApplicationServices", "AXUIElementCopyAttributeValue", optional=True)
    if create_fn is None or copy_fn is None:
        return info
    create_fn.restype = ctypes.c_void_p
    copy_fn.restype = ctypes.c_int
    copy_fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]

    owned: list[int] = []

    def _copy(element: int, name: str) -> tuple[int, int]:
        key = cfstring_from_python(name)
        if not key:
            return -1, 0
        try:
            held = ctypes.c_void_p(0)
            status = int(copy_fn(element, key, ctypes.byref(held)))
        finally:
            cf_release(key)
        if held.value:
            owned.append(held.value)
        return status, int(held.value or 0)

    try:
        # Ask the frontmost app directly first: the system-wide element's
        # AXFocusedUIElement fails on some systems (seen on macOS 15 runners)
        # while the per-app query works.
        focused = 0
        app_fn = _loader.symbol("ApplicationServices", "AXUIElementCreateApplication", optional=True)
        pid = int((frontmost_window_owner() or {}).get("pid") or 0)
        if app_fn is not None and pid > 0:
            app_fn.restype = ctypes.c_void_p
            app_fn.argtypes = [ctypes.c_int]
            app_element = app_fn(pid)
            if app_element:
                owned.append(app_element)
                status, focused = _copy(app_element, "AXFocusedUIElement")
                if status != 0:
                    focused = 0
        if not focused:
            system_wide = create_fn()
            if not system_wide:
                return info
            owned.append(system_wide)
            status, focused = _copy(system_wide, "AXFocusedUIElement")
            if status != 0 or not focused:
                return info
        role_status, role_ref = _copy(focused, "AXRole")
        if role_status == 0 and cf_is_string(role_ref):
            info["role"] = cfstring_to_python(role_ref)
        sel_status, sel_ref = _copy(focused, "AXSelectedText")
        info["status"] = sel_status
        if sel_status == 0 and cf_is_string(sel_ref):
            info["text"] = cfstring_to_python(sel_ref)
        return info
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[MACOS] focused_selection_info failed: %s", exc)
        return info
    finally:
        for ref in reversed(owned):
            cf_release(ref)


kAXErrorAPIDisabled = -25211


def focused_value_snapshot() -> dict[str, Any]:
    """Raw Accessibility read of the focused element's text value.

    Unlike :func:`focused_selection_info` this does not trust the in-process
    ``AXIsProcessTrusted`` answer (it can stay stale after the user revokes
    Accessibility); the AX error code itself says whether we may read.
    Returns ``{"focus_status": int | None, "value_status": int | None,
    "value": str | None}``; ``focus_status == kAXErrorAPIDisabled`` means
    Accessibility is really off for this process. Never raises.
    """
    snap: dict[str, Any] = {"focus_status": None, "value_status": None, "value": None}
    if not IS_MACOS:
        return snap
    copy_fn = _loader.symbol("ApplicationServices", "AXUIElementCopyAttributeValue", optional=True)
    app_fn = _loader.symbol("ApplicationServices", "AXUIElementCreateApplication", optional=True)
    create_fn = _loader.symbol("ApplicationServices", "AXUIElementCreateSystemWide", optional=True)
    if copy_fn is None or (app_fn is None and create_fn is None):
        return snap
    copy_fn.restype = ctypes.c_int
    copy_fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    owned: list[int] = []

    def _copy(element: int, name: str) -> tuple[int, int]:
        key = cfstring_from_python(name)
        if not key:
            return -1, 0
        try:
            held = ctypes.c_void_p(0)
            status = int(copy_fn(element, key, ctypes.byref(held)))
        finally:
            cf_release(key)
        if held.value:
            owned.append(held.value)
        return status, int(held.value or 0)

    try:
        element = 0
        pid = int((frontmost_window_owner() or {}).get("pid") or 0)
        if app_fn is not None and pid > 0:
            app_fn.restype = ctypes.c_void_p
            app_fn.argtypes = [ctypes.c_int]
            element = app_fn(pid) or 0
        if not element and create_fn is not None:
            create_fn.restype = ctypes.c_void_p
            element = create_fn() or 0
        if not element:
            return snap
        owned.append(element)
        status, focused = _copy(element, "AXFocusedUIElement")
        snap["focus_status"] = status
        if status != 0 or not focused:
            return snap
        v_status, v_ref = _copy(focused, "AXValue")
        snap["value_status"] = v_status
        if v_status == 0 and cf_is_string(v_ref):
            snap["value"] = cfstring_to_python(v_ref)
        return snap
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[MACOS] focused_value_snapshot failed: %s", exc)
        return snap
    finally:
        for ref in reversed(owned):
            cf_release(ref)


def focused_selected_text() -> str:
    """Read the focused element's selected text via the Accessibility API.

    Requires Accessibility trust. Returns "" when untrusted, unavailable, or
    when the focused element has no selection.
    """
    if not IS_MACOS:
        return ""
    if not accessibility_trusted():
        return ""
    create_fn = _loader.symbol("ApplicationServices", "AXUIElementCreateSystemWide", optional=True)
    copy_fn = _loader.symbol("ApplicationServices", "AXUIElementCopyAttributeValue", optional=True)
    if create_fn is None or copy_fn is None:
        return ""
    create_fn.restype = ctypes.c_void_p
    copy_fn.restype = ctypes.c_int
    copy_fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]

    system_wide = 0
    focused = 0
    value = 0
    try:
        system_wide = create_fn()
        if not system_wide:
            return ""

        focused_holder = ctypes.c_void_p(0)
        attr_key = cfstring_from_python("AXFocusedUIElement")
        if not attr_key:
            return ""
        try:
            status = copy_fn(system_wide, attr_key, ctypes.byref(focused_holder))
        finally:
            cf_release(attr_key)
        if status != 0 or not focused_holder.value:
            return ""
        focused = focused_holder.value

        sel_key = cfstring_from_python("AXSelectedText")
        if not sel_key:
            return ""
        try:
            held = ctypes.c_void_p(0)
            status = copy_fn(focused, sel_key, ctypes.byref(held))
        finally:
            cf_release(sel_key)
        if status != 0 or not held.value:
            return ""
        value = held.value
        return cfstring_to_python(value)
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[MACOS] focused_selected_text failed: %s", exc)
        return ""
    finally:
        cf_release(value)
        cf_release(focused)
        cf_release(system_wide)


__all__ = [
    "IS_MACOS",
    "available",
    "send_key_combo",
    "send_return_key",
    "frontmost_window_owner",
    "accessibility_trusted",
    "input_monitoring_status",
    "request_input_monitoring",
    "microphone_status",
    "request_microphone_access",
    "focused_selected_text",
    "focused_selection_info",
    "can_post_events",
    "preflight_post_event_access",
    "focused_value_snapshot",
    "kAXErrorAPIDisabled",
    "current_modifier_flags",
    "wait_for_modifiers_released",
    "window_owner_at_point",
    "cfstring_from_python",
    "cfstring_to_python",
    "cf_release",
    "KEY_C",
    "KEY_V",
    "KEY_RETURN",
    "KEY_TAB",
    "KEY_ESCAPE",
    "kCGEventFlagMaskCommand",
    "kCGEventFlagMaskShift",
    "kCGEventFlagMaskControl",
    "kCGEventFlagMaskAlternate",
    "IOHID_ACCESS_GRANTED",
    "IOHID_ACCESS_DENIED",
    "IOHID_ACCESS_UNKNOWN",
    "AV_STATUS_NOT_DETERMINED",
    "AV_STATUS_RESTRICTED",
    "AV_STATUS_DENIED",
    "AV_STATUS_AUTHORIZED",
]
