"""Headless Narova adapter with tracked subprocesses and MP4 normalization."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .. import runtime_env
from .process_manager import ProcessManager
from .sandbox import EngineError


class NarovaRunner:
    def __init__(
        self,
        *,
        vendor_root: Path | None = None,
        node_path: str | None = None,
        ffmpeg_path: str | None = None,
        timeout_seconds: float = 900.0,
    ) -> None:
        # Installed app: vendored tool + private node/ffmpeg under runtime/.
        # Development: repository third_party + system PATH (unchanged).
        self.vendor_root = Path(vendor_root or runtime_env.narova_tool_root()
                                or Path(__file__).resolve().parents[3] / "third_party" / "narova")
        self.cli_path = self.vendor_root / "tool" / "bin" / "narova.js"
        self.node_path = node_path or (str(runtime_env.node_executable()) if runtime_env.node_executable() else None) or shutil.which("node")
        bundled_ffmpeg = runtime_env.ffmpeg_executable()
        self.ffmpeg_path = ffmpeg_path or (str(bundled_ffmpeg) if bundled_ffmpeg else None) or shutil.which("ffmpeg")
        self.timeout_seconds = timeout_seconds

    def check(self, production: dict[str, Any], project_dir: Path, *, job_id: str, process_manager: ProcessManager | None = None) -> Path:
        manager = process_manager or ProcessManager()
        narova_dir = self._write_project(production, Path(project_dir))
        self._require_core()
        self._run(
            [str(self.node_path), str(self.cli_path), "check", "--project", str(narova_dir), "--renderer", str(production.get("renderer") or "no-browser")],
            cwd=narova_dir,
            job_id=job_id,
            manager=manager,
            log_path=Path(project_dir) / "logs" / "narova.log",
            error_code="invalid_narova_config",
        )
        return narova_dir / "reel.config.json"

    def render(
        self,
        production: dict[str, Any],
        project_dir: Path,
        *,
        job_id: str,
        process_manager: ProcessManager,
        progress_callback: Callable[[dict[str, Any]], None],
    ) -> Path:
        project_dir = Path(project_dir)
        config_path = self.check(production, project_dir, job_id=job_id, process_manager=process_manager)
        narova_dir = config_path.parent
        renderer = str(production.get("renderer") or "no-browser")
        common = ["--project", str(narova_dir), "--renderer", renderer]
        log_path = project_dir / "logs" / "narova.log"

        _report(progress_callback, 55, "Creating narration", "directing")
        self._run(
            [str(self.node_path), str(self.cli_path), "synth", *common],
            cwd=narova_dir,
            job_id=job_id,
            manager=process_manager,
            log_path=log_path,
            error_code="tts_failed",
        )
        _report(progress_callback, 65, "Creating visuals", "compiling_initial")
        self._run(
            [str(self.node_path), str(self.cli_path), "compose", *common],
            cwd=narova_dir,
            job_id=job_id,
            manager=process_manager,
            log_path=log_path,
            error_code="render_failed",
        )
        _report(progress_callback, 80, "Rendering", "buffering")
        if renderer == "hyperframes" and runtime_env.is_installed():
            # Packaged app: the render browser is per-user provisioned; make
            # sure it exists before the browser render (no-op when cached).
            runtime_env.ensure_render_browser()
        self._run(
            [str(self.node_path), str(self.cli_path), "build", *common, "--reuse", "--fps", "30", "--quality", "standard", "--verify-motion"],
            cwd=narova_dir,
            job_id=job_id,
            manager=process_manager,
            log_path=log_path,
            error_code="render_failed",
        )
        source_video = narova_dir / "out" / "video.mp4"
        if not source_video.is_file() or source_video.stat().st_size == 0:
            raise EngineError("render_failed", "Narova did not create out/video.mp4")

        _report(progress_callback, 92, "Mixing audio and captions", "buffering")
        final_video = project_dir / "video.mp4"
        self._normalize_video(source_video, final_video, job_id, process_manager, project_dir / "logs" / "ffmpeg.log")
        captions_dir = project_dir / "captions"
        captions_dir.mkdir(exist_ok=True)
        for name in ("captions.srt", "captions.vtt"):
            source = narova_dir / "out" / name
            if source.is_file():
                shutil.copy2(source, captions_dir / name)
        return final_video

    def _write_project(self, production: dict[str, Any], project_dir: Path) -> Path:
        narova_dir = project_dir / "narova"
        narova_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "logs").mkdir(parents=True, exist_ok=True)
        if str((production.get("voices") or {}).get("narrator", {}).get("backend")) == "voiceflow":
            _register_voiceflow_provider()
        production = dict(production)
        files = production.pop("_files", {})
        if isinstance(files, dict):
            for relative, content in files.items():
                rel = str(relative).replace("\\", "/").strip("/")
                parts = Path(rel).parts
                if not rel or rel.startswith("..") or ".." in parts or ":" in rel:
                    continue
                target = narova_dir.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(content), encoding="utf-8")
        serialized = json.dumps(production, ensure_ascii=False, indent=2)
        (project_dir / "bridge-output.json").write_text(serialized, encoding="utf-8")
        config_path = narova_dir / "reel.config.json"
        config_path.write_text(serialized, encoding="utf-8")
        return narova_dir

    def _require_core(self) -> None:
        if not self.node_path:
            raise EngineError("dependency_missing", "Node.js is required for Narova")
        if not self.cli_path.is_file():
            raise EngineError("dependency_missing", f"Narova CLI is missing: {self.cli_path}")

    def _normalize_video(self, source: Path, destination: Path, job_id: str, manager: ProcessManager, log_path: Path) -> None:
        if not self.ffmpeg_path:
            raise EngineError("dependency_missing", "FFmpeg is required for final MP4 output")
        temp_output = destination.with_suffix(".finalizing.mp4")
        command = [
            str(self.ffmpeg_path), "-y", "-i", str(source),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(temp_output),
        ]
        try:
            self._run(command, cwd=destination.parent, job_id=job_id, manager=manager, log_path=log_path, error_code="ffmpeg_failed")
            os.replace(temp_output, destination)
        finally:
            temp_output.unlink(missing_ok=True)

    def _run(
        self,
        command: list[str],
        *,
        cwd: Path,
        job_id: str,
        manager: ProcessManager,
        log_path: Path,
        error_code: str,
    ) -> None:
        manager.raise_if_cancelled(job_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_safe_environment(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        manager.register(job_id, process)
        try:
            try:
                output, _ = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                manager.cancel_job(job_id)
                raise EngineError("timeout", f"Command timed out after {self.timeout_seconds:g}s") from exc
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"$ {' '.join(command)}\n{output}\n")
            if process.returncode != 0:
                raise EngineError(error_code, f"{error_code.replace('_', ' ')} command failed; see logs/{log_path.name}")
        finally:
            manager.unregister(job_id, process)
        manager.raise_if_cancelled(job_id)


def _safe_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    managed_python = Path.home() / ".narova" / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    environment["NAROVA_PYTHON"] = str(managed_python if managed_python.is_file() else Path(sys.executable))
    environment["PYTHONIOENCODING"] = "utf-8"
    # Installed app: the private python hosts narova_tts (no managed venv is
    # created) and the bundled hyperframes tree replaces npx resolution.
    # narova_tts and the narova CLI resolve ffmpeg via PATH, so the private
    # ffmpeg directory leads the subprocess PATH (never the system PATH).
    if runtime_env.is_installed():
        runtime = runtime_env.runtime_root()
        environment["NAROVA_PYTHON"] = runtime_env.python_executable()
        environment["NAROVA_HF_MODULES"] = str(runtime / "hyperframes")
        ff_dir = runtime / "ffmpeg"
        environment["PATH"] = str(ff_dir) + os.pathsep + environment.get("PATH", "")
    return environment


def _register_voiceflow_provider() -> None:
    """Idempotently register the app's TTS worker as a Narova provider.

    Narova only reads normalized manifests from ``~/.narova/providers``. The
    manifest is rewritten whenever the interpreter or worker path changes so
    the registration self-heals across app updates.
    """
    import json

    worker = Path(__file__).with_name("voice_provider_worker.py")
    if not worker.is_file():
        raise EngineError("dependency_missing", f"Voice provider worker is missing: {worker}")
    providers_dir = Path(os.environ.get("NAROVA_HOME", Path.home() / ".narova")) / "providers"
    providers_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "voiceflow",
        "displayName": "Voice Flow TTS",
        "protocol": "narova-tts-provider/v1",
        "command": [sys.executable, str(worker)],
        "requiredEnvironment": [],
        "capabilities": {"synthesis": True},
        "providerVersion": "1.0.0",
    }
    manifest_path = providers_dir / "voiceflow.json"
    try:
        if manifest_path.is_file():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("command") == manifest["command"]:
                return
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise EngineError("tts_failed", f"Could not register the narration voice provider: {exc}") from exc


def _report(callback: Callable[[dict[str, Any]], None], progress: float, message: str, state: str) -> None:
    callback({"progress": float(progress), "message": message, "state": state})


