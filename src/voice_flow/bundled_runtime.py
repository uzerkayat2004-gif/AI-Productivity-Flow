"""Pinned versions of the runtimes shipped with the desktop app.

An app-only update is safe only when every one of these still matches the
copy that is already installed. The Windows and macOS build scripts record
the same values into the install manifest, and the small update package
repeats them so the updater can compare before it downloads.

Mac does not bundle Node, HyperFrames, or ffmpeg inside the .app. Those
fields stay ``not-bundled`` so a release that starts shipping them no longer
matches and the updater uses the full disk image.
"""

from __future__ import annotations

RUNTIME_FIELDS = (
    "python",
    "node",
    "hyperframes",
    "narova",
    "ffmpeg",
    "whisper",
    "local_ai_engine",
)

# Every field above is still written to the install manifest and the
# app-update manifest, because the 1.0.6 and 1.0.7 updaters compare all of
# them. From 1.0.8 the updater compares only the core fields: a change in an
# app-managed field no longer forces the full installer, because the app
# fetches that piece itself (Node 22 for Video Flow: voice_flow.node_component).
# Python, Whisper and the local AI engine stay core: those genuinely need the
# full installer.
APP_MANAGED_FIELDS = ("node",)
CORE_RUNTIME_FIELDS = tuple(f for f in RUNTIME_FIELDS if f not in APP_MANAGED_FIELDS)

# Keep these aligned with release/assemble_windows_staging.py.
WINDOWS_PYTHON = "3.12.10"
# Keep the bundled Node at 20.18.1: it is what every v1.0.6 install recorded,
# and the v1.0.6/v1.0.7 updaters offer the 527 MB installer when it differs.
# HyperFrames needs Node 22, which the app downloads (node_component), so a
# newer Node never needs to be bundled. Changing this re-breaks small updates
# for every install older than 1.0.8.
WINDOWS_NODE = "20.18.1"
WINDOWS_HYPERFRAMES = "0.7.96"
WINDOWS_FFMPEG = "7.1.1"
WINDOWS_WHISPER = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
WINDOWS_LOCAL_AI = "llama-cpp-python==0.3.19"

# Keep these aligned with scripts/build_macos_app.py.
MAC_PYTHON = "3.11.17"
MAC_WHISPER = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
MAC_LLAMA_CPP = "b11696"
MAC_NEMO_SPEECH = "0.2.0"
MAC_LOCAL_AI = f"llama.cpp {MAC_LLAMA_CPP}; nemo-speech {MAC_NEMO_SPEECH}"

# third_party/narova/package.json. The build refuses to pack if this drifts.
NAROVA_VERSION = "0.31.14"
NOT_BUNDLED = "not-bundled"


def windows_runtime() -> dict[str, str]:
    return {
        "python": WINDOWS_PYTHON,
        "node": WINDOWS_NODE,
        "hyperframes": WINDOWS_HYPERFRAMES,
        "narova": NAROVA_VERSION,
        "ffmpeg": WINDOWS_FFMPEG,
        "whisper": WINDOWS_WHISPER,
        "local_ai_engine": WINDOWS_LOCAL_AI,
    }


def mac_runtime() -> dict[str, str]:
    return {
        "python": MAC_PYTHON,
        "node": NOT_BUNDLED,
        "hyperframes": NOT_BUNDLED,
        "narova": NAROVA_VERSION,
        "ffmpeg": NOT_BUNDLED,
        "whisper": MAC_WHISPER,
        "local_ai_engine": MAC_LOCAL_AI,
    }


def runtime_for_platform(platform: str) -> dict[str, str]:
    if platform == "mac":
        return mac_runtime()
    return windows_runtime()
