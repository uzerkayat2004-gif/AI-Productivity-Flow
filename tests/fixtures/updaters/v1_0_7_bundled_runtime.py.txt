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

# Keep these aligned with release/assemble_windows_staging.py.
WINDOWS_PYTHON = "3.12.10"
WINDOWS_NODE = "22.23.3"
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
