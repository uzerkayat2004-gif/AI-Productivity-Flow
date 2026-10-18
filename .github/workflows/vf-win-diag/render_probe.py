"""Drive Video Flow through the same local API the desktop UI uses.

NotebookLM sign-in cannot run on a GitHub-hosted runner. The first request
matches the Video Flow page (provider notebooklm). If that does not produce
an MP4, a second request runs the local visual-v2.1 renderer with a short
sample, which is the stage the UI falls back to.

Stdlib only, so the installed private Python can run it.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(method: str, url: str, payload: dict | None = None, timeout: float = 60) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json", "Host": "127.0.0.1:8991"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        body = {"raw": raw[:2000]}
    return status, body


def wait_until_ready(base: str, deadline: float) -> dict:
    last = {}
    while time.time() < deadline:
        try:
            status, body = request("GET", f"{base}/api/runtime", timeout=5)
            last = {"status": status, "body": body}
            if status == 200:
                return last
        except Exception as exc:  # noqa: BLE001 - diagnostic must keep trying
            last = {"error": str(exc)}
        time.sleep(2)
    raise SystemExit(f"API did not become ready: {last}")


def poll_job(base: str, video_id: str, deadline: float, log_path: Path) -> dict:
    last_stage = ""
    last = {}
    with log_path.open("a", encoding="utf-8") as handle:
        while time.time() < deadline:
            try:
                status, body = request("GET", f"{base}/api/video-flow/status?id={video_id}", timeout=20)
            except Exception as exc:  # noqa: BLE001
                handle.write(json.dumps({"event": "poll_error", "error": str(exc)}) + "\n")
                time.sleep(5)
                continue
            video = body.get("video") if isinstance(body, dict) else None
            if not isinstance(video, dict):
                video = body if isinstance(body, dict) else {}
            stage = f"{video.get('status')}:{video.get('progress')}:{video.get('stage')}:{video.get('error_code')}"
            if stage != last_stage:
                row = {"event": "progress", "http": status, "stage": stage, "error": video.get("error"), "error_code": video.get("error_code")}
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                print(json.dumps(row, ensure_ascii=False), flush=True)
                last_stage = stage
            last = video
            if str(video.get("status") or "").lower() in {"completed", "failed", "cancelled", "complete", "ready"}:
                return video
            time.sleep(5)
    last["error"] = last.get("error") or "diagnostic timed out"
    last["status"] = last.get("status") or "timeout"
    return last


def dump_jobs(data_root: Path, dest: Path) -> None:
    rows = []
    if not data_root.is_dir():
        dest.write_text("[]", encoding="utf-8")
        return
    for db in data_root.rglob("*.db"):
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            if "video_flow_jobs" not in tables:
                conn.close()
                continue
            for row in conn.execute(
                "SELECT job_id, state, progress, message, meta_json, created_at, updated_at FROM video_flow_jobs ORDER BY created_at"
            ):
                item = dict(row)
                item["db"] = str(db)
                try:
                    item["meta"] = json.loads(item.pop("meta_json") or "{}")
                except json.JSONDecodeError:
                    item["meta_raw"] = item.pop("meta_json")
                rows.append(item)
            conn.close()
        except sqlite3.Error as exc:
            rows.append({"db": str(db), "error": str(exc)})
    dest.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8991")
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--data-root", default=str(Path.home() / ".voice_flow"))
    parser.add_argument("--minutes", type=float, default=35)
    args = parser.parse_args()
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    ready = wait_until_ready(args.base, time.time() + 30)
    (artifacts / "runtime.json").write_text(json.dumps(ready, indent=2, default=str), encoding="utf-8")

    sample = (
        "A pump lifts water from a low tank to a high tank. "
        "The motor spins an impeller. Pressure in the pipe rises, and water moves uphill."
    )
    ui_payload = {
        "provider": "notebooklm",
        "engine": "notebooklm",
        "video_engine": "notebooklm",
        "format": "brief",
        "requested_format": "brief",
        "duration_seconds": 30,
        "target_duration_seconds": 30,
        "style": "auto",
        "title": "Windows diagnostic sample",
        "source_text": sample,
        "source_name": "windows-diagnostic.txt",
        "allow_local_fallback": True,
        "allow_external_ai": False,
        "profile": "video-flow-experiment",
    }
    local_payload = {
        "provider": "visual-v2.1",
        "engine": "visual-v2.1",
        "video_engine": "visual-v2.1",
        "format": "brief",
        "duration_seconds": 20,
        "target_duration_seconds": 20,
        "title": "Windows diagnostic local render",
        "source_text": sample,
        "source_name": "windows-diagnostic.txt",
        "allow_local_fallback": True,
        "allow_external_ai": False,
        "mode": "summary",
    }

    results = []
    for name, payload in (("ui-notebooklm", ui_payload), ("local-render", local_payload)):
        status, queued = request("POST", f"{args.base}/api/video-flow/generate", payload, timeout=60)
        (artifacts / f"{name}-queue.json").write_text(json.dumps({"http": status, "body": queued}, indent=2, default=str), encoding="utf-8")
        video = queued.get("video") if isinstance(queued, dict) else None
        video_id = ""
        if isinstance(video, dict):
            video_id = str(video.get("id") or "")
        video_id = video_id or str((queued or {}).get("job_id") or "")
        if status >= 400 or not video_id:
            results.append({"name": name, "http": status, "queued": queued, "status": "queue_failed"})
            # The UI path failing to queue is itself the bug. Still try the local renderer.
            if name == "ui-notebooklm":
                continue
            break
        final = poll_job(args.base, video_id, time.time() + args.minutes * 60, artifacts / f"{name}-progress.jsonl")
        (artifacts / f"{name}-final.json").write_text(json.dumps(final, indent=2, default=str), encoding="utf-8")
        results.append({"name": name, "video_id": video_id, "final": final})
        state = str(final.get("status") or "").lower()
        if name != "ui-notebooklm":
            continue
        if state in {"completed", "complete", "ready"} and final.get("playable"):
            break
        # A timed-out UI job may still be rendering. A second job would overlap it.
        if state in {"", "timeout"} or "timed out" in str(final.get("error") or "").lower():
            break
        if any(Path(args.data_root).rglob("narova.log")):
            break

    dump_jobs(Path(args.data_root), artifacts / "video-flow-jobs.json")
    summary = {"results": results}
    (artifacts / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    ok = any(
        str((item.get("final") or {}).get("status") or "").lower() in {"completed", "complete", "ready"}
        and (item.get("final") or {}).get("playable")
        for item in results
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
