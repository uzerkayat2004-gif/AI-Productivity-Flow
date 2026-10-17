"""Build the small app-only update packages.

The full Windows installer and macOS disk image carry the private runtime
(Python, Node, ffmpeg, models) and are hundreds of megabytes. These zips
carry only the application package — ``voice_flow`` plus its UI and
onboarding assets — and a manifest of the runtime versions they expect.

Outputs, next to each other:

    AI-Productivity-Flow-app-update-win.zip
    AI-Productivity-Flow-app-update-win.zip.sha256
    AI-Productivity-Flow-app-update-win.manifest.json
    AI-Productivity-Flow-app-update-mac.zip
    AI-Productivity-Flow-app-update-mac.zip.sha256
    AI-Productivity-Flow-app-update-mac.manifest.json

The ``.manifest.json`` file is the same manifest stored inside the zip. The
updater reads it from the release before downloading so it can show the right
size and skip the small package when the runtime changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "voice_flow"
NAROVA_PACKAGE_JSON = REPO / "third_party" / "narova" / "package.json"

NAMES = {
    "win": "AI-Productivity-Flow-app-update-win.zip",
    "mac": "AI-Productivity-Flow-app-update-mac.zip",
}


def _version() -> str:
    sys.path.insert(0, str(REPO / "src"))
    from voice_flow._version import VERSION
    return VERSION


def _runtime(platform: str) -> dict[str, str]:
    sys.path.insert(0, str(REPO / "src"))
    from voice_flow.bundled_runtime import NAROVA_VERSION, runtime_for_platform

    if NAROVA_PACKAGE_JSON.is_file():
        listed = json.loads(NAROVA_PACKAGE_JSON.read_text(encoding="utf-8")).get("version")
        if listed != NAROVA_VERSION:
            raise SystemExit(
                f"Narova version drifted: package.json says {listed}, "
                f"bundled_runtime.py says {NAROVA_VERSION}"
            )
    return runtime_for_platform(platform)


def _package_files() -> list[Path]:
    files: list[Path] = []
    for path in PACKAGE.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if path.name == ".DS_Store":
            continue
        files.append(path)
    if not files:
        raise SystemExit(f"No application files under {PACKAGE}")
    return files


def build_manifest(platform: str) -> dict:
    files = _package_files()
    return {
        "format": 1,
        "product": "AI Productivity Flow",
        "version": _version(),
        "platform": platform,
        "package_root": "voice_flow",
        "runtime": _runtime(platform),
        "files": sorted(
            f"voice_flow/{path.relative_to(PACKAGE).as_posix()}" for path in files
        ),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_app_update(platform: str, dest_dir: Path) -> dict[str, Path]:
    """Write the zip, its checksum, and the standalone manifest. Returns paths."""
    if platform not in NAMES:
        raise SystemExit(f"platform must be win or mac, not {platform!r}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(platform)
    zip_path = dest_dir / NAMES[platform]
    # ``Path.stem`` drops only the last suffix, so this is
    # ``AI-Productivity-Flow-app-update-win.manifest.json``. The checksum
    # keeps the ``.zip`` in its name: ``<name>.zip.sha256``.
    manifest_path = dest_dir / f"{zip_path.stem}.manifest.json"
    sha_path = dest_dir / f"{zip_path.name}.sha256"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2) + "\n",
        )
        for path in _package_files():
            rel = path.relative_to(PACKAGE).as_posix()
            archive.write(path, f"voice_flow/{rel}")

    digest = _sha256(zip_path)
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"APP UPDATE OK: {zip_path} ({zip_path.stat().st_size} bytes)")
    return {"zip": zip_path, "sha256": sha_path, "manifest": manifest_path}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build an app-only update zip")
    parser.add_argument("--platform", choices=sorted(NAMES), action="append", required=True)
    parser.add_argument("--out", type=Path, default=REPO / "dist")
    args = parser.parse_args(argv)
    for platform in args.platform:
        build_app_update(platform, args.out)


if __name__ == "__main__":
    main()
