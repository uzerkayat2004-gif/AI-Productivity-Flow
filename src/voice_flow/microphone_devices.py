"""Input-device catalog, preference resolution and guarded idle discovery.

PortAudio exposes names and host APIs, not Windows endpoint GUIDs. Indistinguishable
endpoints are therefore marked ambiguous instead of guessing from a transient index.
"""
from __future__ import annotations

import json
from collections import Counter
from functools import wraps
import threading
import weakref

IDENTITY_PREFIX = "vfmic:"
HOSTAPI_RANK = {"Windows WASAPI": 0, "Windows DirectSound": 1, "MME": 2, "Windows WDM-KS": 3}
AUDIO_DEVICE_LOCK = threading.RLock()
_recorders = weakref.WeakSet()
_refresh_initialization_failures = weakref.WeakSet()
_uncertain_streams = []  # Strong ownership survives a recorder being discarded.


def register_recorder(recorder):
    with AUDIO_DEVICE_LOCK:
        _recorders.add(recorder)


def retain_uncertain_stream(stream):
    with AUDIO_DEVICE_LOCK:
        if _stream_is_open(stream) and not any(item is stream for item in _uncertain_streams):
            _uncertain_streams.append(stream)


def serialized_audio_devices(method):
    """Order locks as device registry -> recorder lifecycle -> callback buffer."""
    @wraps(method)
    def serialized(*args, **kwargs):
        with AUDIO_DEVICE_LOCK:
            return method(*args, **kwargs)
    return serialized


def _stream_is_open(stream):
    # Unknown stream state is conservatively treated as owned/live.
    return stream is not None and getattr(stream, "closed", False) is not True


def audio_library_needs_refresh(sd):
    with AUDIO_DEVICE_LOCK:
        return sd in _refresh_initialization_failures


def has_uncertain_audio_stream():
    with AUDIO_DEVICE_LOCK:
        _uncertain_streams[:] = [stream for stream in _uncertain_streams if _stream_is_open(stream)]
        return bool(_uncertain_streams)


def query_input_catalog(sd, refresh=False) -> dict:
    """Query a snapshot; explicit refresh resets PortAudio only while unowned.

    These private sounddevice hooks are compatibility guarded. A failed reset
    is reported once, never retried in a loop or while a stream is opening.
    """
    result = {"devices": [], "refreshed": False, "busy": False, "error": None}
    with AUDIO_DEVICE_LOCK:
        _uncertain_streams[:] = [stream for stream in _uncertain_streams if _stream_is_open(stream)]
        if refresh:
            busy = bool(_uncertain_streams) or any(getattr(recorder, "_recording", False)
                       or _stream_is_open(getattr(recorder, "_stream", None))
                       for recorder in list(_recorders))
            callback = getattr(sd, "_last_callback", None)
            if callback is not None:
                busy = busy or not hasattr(callback, "stream") or _stream_is_open(callback.stream)
            if busy:
                message = ("Microphone did not close. Close Voice Flow before refreshing devices."
                           if _uncertain_streams else "Finish current recording, then refresh microphones.")
                result.update(busy=True, error=message)
            elif getattr(sd, "_initialized", None) == 0 and sd in _refresh_initialization_failures:
                try:
                    sd._initialize()
                    _refresh_initialization_failures.discard(sd)
                    result["refreshed"] = True
                except Exception as exc:
                    result["error"] = f"Microphone refresh failed: {exc}"
            elif getattr(sd, "_initialized", None) != 1:
                result["error"] = "Audio library is unavailable or shared; microphone refresh was skipped."
            elif not callable(getattr(sd, "_terminate", None)) or not callable(getattr(sd, "_initialize", None)):
                result["error"] = "This audio library does not support safe microphone refresh."
            else:
                try:
                    sd._terminate()
                    try:
                        sd._initialize()
                    except Exception:
                        _refresh_initialization_failures.add(sd)
                        raise
                    _refresh_initialization_failures.discard(sd)
                    result["refreshed"] = True
                except Exception as exc:
                    result["error"] = f"Microphone refresh failed: {exc}"
        # A failed initialize leaves PortAudio unavailable. Do not query its
        # invalid registry or silently retry initialization during ordinary GET.
        if getattr(sd, "_initialized", 1) == 0:
            if result["error"] is None:
                result["error"] = "Audio library is unavailable; microphone discovery failed."
            return result
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            try:
                default_index = sd.default.device[0]
            except (AttributeError, IndexError, TypeError):
                default_index = None
            result["devices"] = build_input_catalog(devices, hostapis, default_index)
        except Exception as exc:
            result["error"] = f"Microphone discovery failed: {exc}"
        return result


def display_input_catalog(catalog, selected_identity=None) -> list[dict]:
    """Compact exact-name aliases for display, retaining the selected endpoint.

    Ambiguous best-API rows remain visible so the UI can explain why they cannot
    be selected. The full capture catalog is never changed by this view.
    """
    groups = {}
    for row in catalog:
        groups.setdefault(row["name"].casefold(), []).append(row)
    visible = []
    for aliases in groups.values():
        best = min(HOSTAPI_RANK.get(row["hostapi"], 4) for row in aliases)
        visible.extend(row for row in aliases if HOSTAPI_RANK.get(row["hostapi"], 4) == best
                       or row["identity"] == selected_identity)
    return visible


def load_microphone_preference(settings):
    """Read preference without hardware inspection or erasing unavailable picks."""
    missing = object()
    preference = settings.get_setting("selected_mic_device", missing)
    if preference is missing:
        preference = settings.get_setting("selected_microphone", None)
    return None if preference == "" else preference


def build_input_catalog(devices, hostapis, default_input_index=None) -> list[dict]:
    rows = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0) or 0)
        if channels <= 0:
            continue
        name = str(device.get("name", "")).strip()
        api_index = device.get("hostapi")
        api = ""
        if isinstance(api_index, int) and 0 <= api_index < len(hostapis):
            api_row = hostapis[api_index]
            api = str(api_row.get("name", "") if isinstance(api_row, dict) else api_row)
        identity = IDENTITY_PREFIX + json.dumps([name, api], ensure_ascii=False, separators=(",", ":"))
        rows.append({"index": index, "name": name, "hostapi": api,
                     "identity": identity, "max_input_channels": channels,
                     "default_samplerate": float(device.get("default_samplerate", 44100) or 44100),
                     "is_default": index == default_input_index})
    counts = Counter(row["identity"] for row in rows)
    for row in rows:
        row["ambiguous"] = counts[row["identity"]] > 1
    return rows


def resolve_input_device(preference, catalog) -> dict | None:
    """Resolve a saved identity or legacy exact name/index against this snapshot.

    None denotes default mode to the caller, and has no specific catalog row.
    Missing or ambiguous preferences also return None; callers distinguish them
    by whether the supplied preference was explicit.
    """
    if isinstance(preference, bool):
        return None
    if isinstance(preference, int):
        matches = [row for row in catalog if row["index"] == preference]
    elif isinstance(preference, str) and preference.startswith(IDENTITY_PREFIX):
        try:
            parts = json.loads(preference[len(IDENTITY_PREFIX):])
        except (ValueError, TypeError):
            return None
        if not isinstance(parts, list) or len(parts) != 2 or not all(isinstance(item, str) for item in parts):
            return None
        matches = [row for row in catalog if [row["name"], row["hostapi"]] == parts]
    elif isinstance(preference, str):
        matches = [row for row in catalog if row["name"].casefold() == preference.strip().casefold()]
        # Older selections saved only a name, which PortAudio commonly repeats
        # across Windows host APIs. Choose a deterministic API for that exact
        # legacy name, while refusing indistinguishable rows within that API.
        if matches:
            best_rank = min(HOSTAPI_RANK.get(row["hostapi"], 4) for row in matches)
            matches = [row for row in matches if HOSTAPI_RANK.get(row["hostapi"], 4) == best_rank]
    else:
        return None
    return matches[0] if len(matches) == 1 and not matches[0]["ambiguous"] else None
