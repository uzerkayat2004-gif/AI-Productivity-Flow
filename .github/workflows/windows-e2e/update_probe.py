"""Ask the installed update checker whether v1.0.4 is current, then dry-run the app zip plan.

Does not download the app zip or replace any files.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


def main() -> int:
    tag = sys.argv[1].lstrip("v")
    result_path = Path(sys.argv[2])
    assets_path = Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
    payload: dict = {"tag": tag}
    try:
        from voice_flow._version import DISPLAY_VERSION, VERSION
        from voice_flow.app_updater import (
            describe_update,
            installed_package_dir,
            installed_runtime_fingerprint,
            runtime_fingerprint_from_manifest,
            update_state_dir,
        )
        from voice_flow.update_checker import check_for_updates

        package = installed_package_dir()
        state = update_state_dir()
        pending = (state / "pending.json") if state else None
        payload["version"] = VERSION
        payload["display_version"] = DISPLAY_VERSION
        payload["package_dir"] = str(package) if package else None
        payload["pending_before"] = bool(pending and pending.is_file())

        checked = check_for_updates(force=True, timeout=20)
        payload["check"] = {
            "current_version": checked.get("current_version"),
            "display_version": checked.get("display_version"),
            "latest_version": checked.get("latest_version"),
            "update_available": checked.get("update_available"),
            "checked": checked.get("checked"),
            "error": checked.get("error"),
            "release_name": checked.get("release_name"),
        }

        if assets_path and assets_path.is_file():
            assets = json.loads(assets_path.read_text(encoding="utf-8"))
            if isinstance(assets, dict):
                assets = assets.get("assets") or [assets]
        else:
            request = urllib.request.Request(
                f"https://api.github.com/repos/uzerkayat2004-gif/AI-Productivity-Flow/releases/tags/v{tag}",
                headers={
                    "User-Agent": f"AI-Productivity-Flow/{VERSION} (update-check)",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                assets = json.loads(response.read().decode("utf-8")).get("assets") or []

        described = describe_update(assets)
        plan = described.get("update_plan") or {}
        payload["plan"] = {
            "kind": plan.get("kind"),
            "asset_name": plan.get("asset_name"),
            "size_label": plan.get("size_label"),
            "runtime_changed": plan.get("runtime_changed"),
            "reason": plan.get("reason"),
            "download_url": plan.get("download_url"),
        }
        installed = installed_runtime_fingerprint("win")
        payload["installed_runtime"] = installed
        manifest_url = ""
        for asset in described.get("assets") or []:
            if str(asset.get("name") or "").endswith("app-update-win.manifest.json"):
                manifest_url = str(asset.get("browser_download_url") or "")
        payload["manifest_url"] = manifest_url
        if manifest_url:
            from voice_flow.app_updater import fetch_manifest

            manifest = fetch_manifest(manifest_url, timeout=20)
            payload["remote_runtime"] = runtime_fingerprint_from_manifest(manifest)
            payload["manifest_version"] = manifest.get("version") or manifest.get("app_version")
        payload["pending_after"] = bool(pending and pending.is_file())
        up_to_date = (
            checked.get("checked") is True
            and not checked.get("error")
            and checked.get("update_available") is False
            and str(checked.get("current_version")) == tag
            and str(checked.get("latest_version")) == tag
            and str(checked.get("display_version")) == "1.0"
        )
        dry_run_ok = (
            plan.get("kind") == "app"
            and str(plan.get("asset_name") or "").endswith("app-update-win.zip")
            and payload["pending_before"] is False
            and payload["pending_after"] is False
        )
        payload["up_to_date"] = up_to_date
        payload["dry_run_ok"] = dry_run_ok
        payload["pass"] = bool(up_to_date and dry_run_ok)
        if not payload["pass"]:
            payload["error"] = "update check or dry-run plan did not match v1.0.4 app-only expectations"
    except Exception as exc:
        payload["pass"] = False
        payload["error"] = f"{type(exc).__name__}: {exc}"
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload))
    return 0 if payload.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
