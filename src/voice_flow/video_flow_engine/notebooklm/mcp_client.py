"""NotebookLM MCP client bridge for Video Flow.

Provides a clean Python interface to interact with NotebookLM via the
MCP (Model Context Protocol) server or CLI bridge with automatic durable
authentication refresh, transparent auto-recovery, and full telemetry.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .config import (
    DEFAULT_PROFILE,
    has_valid_storage_state,
    is_session_near_expiry,
    resolve_notebooklm_cli,
    resolve_notebooklm_mcp,
    resolve_notebooklm_profile,
)
from .models import NotebookLMVideoError

logger = logging.getLogger(__name__)

_HIDE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _default_runner(command: Sequence[str], timeout: float | None = 60.0) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
        "shell": False,
    }
    if os.name == "nt" or sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.run(list(command), **kwargs)


class NotebookLMMcpClient:
    """Client bridge for NotebookLM operations through MCP/CLI with durable auth."""

    def __init__(
        self,
        profile: str | None = None,
        *,
        cli_path: Path | str | None = None,
        mcp_path: Path | str | None = None,
        runner: Callable[[Sequence[str], float | None], Any] | None = None,
    ) -> None:
        self.profile = resolve_notebooklm_profile(profile)
        self.cli_path = Path(cli_path) if cli_path else resolve_notebooklm_cli()
        self.mcp_path = Path(mcp_path) if mcp_path else resolve_notebooklm_mcp()
        self.runner = runner or _default_runner

    def is_available(self) -> bool:
        """True if the CLI or MCP server executable is installed and profile has credentials."""
        has_exec = bool((self.mcp_path and self.mcp_path.is_file()) or (self.cli_path and self.cli_path.is_file()))
        if not has_exec:
            return False
        if has_valid_storage_state(self.profile):
            return True
        try:
            from .login_flow import master_token_present
            return master_token_present(self.profile)
        except Exception:
            return False

    def ensure_auth(self, *, auto_heal: bool = True) -> bool:
        """Verify session freshness and auto-heal if approaching expiration."""
        if not is_session_near_expiry(self.profile):
            return True
        if not auto_heal:
            return has_valid_storage_state(self.profile)
        try:
            from .login_flow import self_heal
            heal_res = self_heal(profile=self.profile)
            return bool(heal_res.get("ok"))
        except Exception as exc:
            logger.debug("Failed to auto-heal session in MCP client: %s", exc)
            return False

    def _invoke_cli(self, args: Sequence[str], *, timeout: float = 60.0, retry_on_auth_error: bool = True) -> dict[str, Any]:
        """Execute a NotebookLM CLI command with automatic JSON parsing and auth recovery."""
        if not self.cli_path or not self.cli_path.is_file():
            self.cli_path = resolve_notebooklm_cli()
        if not self.cli_path or not self.cli_path.is_file():
            raise NotebookLMVideoError("DEPENDENCY_MISSING", "NotebookLM CLI executable not found.")

        cmd = [str(self.cli_path), "--profile", self.profile, *map(str, args), "--json"]
        try:
            res = self.runner(cmd, timeout)
        except subprocess.TimeoutExpired as exc:
            raise NotebookLMVideoError("TIMEOUT", f"CLI command timed out after {timeout}s") from exc
        except OSError as exc:
            raise NotebookLMVideoError("DEPENDENCY", f"Failed to execute CLI: {exc}") from exc

        stdout = str(getattr(res, "stdout", "") or "")
        stderr = str(getattr(res, "stderr", "") or "")
        code = int(getattr(res, "returncode", 0) or 0)

        data: dict[str, Any] = {}
        if stdout.strip():
            try:
                data = json.loads(stdout.strip())
            except Exception:
                pass

        if code != 0:
            err_msg = stderr.strip() or stdout.strip() or f"CLI returned exit code {code}"
            # Check for auth expired error and auto-heal once
            is_auth_error = any(tok in err_msg.lower() for tok in ("auth_expired", "session expired", "psidts", "re-authenticate", "login"))
            if is_auth_error and retry_on_auth_error:
                logger.info("Encountered auth error in MCP client, attempting auto-heal...")
                healed = False
                try:
                    from .login_flow import self_heal
                    heal_res = self_heal(profile=self.profile)
                    healed = bool(heal_res.get("ok"))
                except Exception as exc:
                    logger.debug("Failed to auto-heal session in MCP client: %s", exc)
                if healed:
                    return self._invoke_cli(args, timeout=timeout, retry_on_auth_error=False)
            raise NotebookLMVideoError("CLI_ERROR", err_msg, payload=data)

        return data

    def check_health(self) -> dict[str, Any]:
        """Check the health of the NotebookLM session and MCP server."""
        mcp_avail = bool(self.mcp_path and self.mcp_path.is_file())
        cli_avail = bool(self.cli_path and self.cli_path.is_file())
        has_creds = has_valid_storage_state(self.profile)

        try:
            from .login_flow import master_token_present
            durable = master_token_present(self.profile)
        except Exception:
            durable = False

        status_str = "ok" if ((has_creds or durable) and (mcp_avail or cli_avail)) else "unauthenticated"
        return {
            "status": status_str,
            "profile": self.profile,
            "mcp_available": mcp_avail,
            "cli_available": cli_avail,
            "authenticated": bool(has_creds or durable),
            "durable": durable,
            "master_token_present": durable,
            "mcp_path": str(self.mcp_path) if self.mcp_path else None,
            "cli_path": str(self.cli_path) if self.cli_path else None,
        }

    def list_notebooks(self) -> list[dict[str, Any]]:
        """List all notebooks in the authenticated Google account."""
        self.ensure_auth()
        data = self._invoke_cli(["list"], timeout=45.0)
        notebooks = data.get("notebooks")
        if isinstance(notebooks, list):
            return notebooks
        # Sometimes CLI returns a dict with items or list root
        if isinstance(data, list):
            return data
        return []

    def create_notebook(self, title: str) -> dict[str, Any]:
        """Create a new notebook with the given title."""
        self.ensure_auth()
        data = self._invoke_cli(["create", title], timeout=45.0)
        return data.get("notebook") or data

    def add_source(
        self,
        notebook_id: str,
        *,
        title: str = "Source",
        source_file: Path | str | None = None,
        source_url: str | None = None,
        source_text: str | None = None,
    ) -> dict[str, Any]:
        """Add a source to a notebook."""
        self.ensure_auth()
        if source_file:
            path = Path(source_file).expanduser().resolve()
            data = self._invoke_cli(
                ["source", "add", str(path), "--notebook", notebook_id, "--type", "file", "--title", title],
                timeout=90.0,
            )
        elif source_url:
            data = self._invoke_cli(
                ["source", "add", source_url, "--notebook", notebook_id, "--type", "url", "--title", title],
                timeout=90.0,
            )
        elif source_text:
            data = self._invoke_cli(
                ["source", "add", source_text, "--notebook", notebook_id, "--type", "text", "--title", title],
                timeout=90.0,
            )
        else:
            raise ValueError("Must provide source_file, source_url, or source_text")
        return data.get("source") or data

    def wait_source(self, notebook_id: str, source_id: str, timeout: int = 120) -> dict[str, Any]:
        """Wait for an added source to finish processing."""
        return self._invoke_cli(
            ["source", "wait", source_id, "--notebook", notebook_id, "--timeout", str(timeout)],
            timeout=float(timeout + 30),
        )

    def generate_video(
        self,
        notebook_id: str,
        *,
        format: str = "explainer",
        style: str = "classic",
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Generate a video overview artifact in a notebook."""
        self.ensure_auth()
        cmd = ["generate", "video", "--notebook", notebook_id, "--format", format, "--style", style]
        if prompt:
            cmd.extend(["--prompt", prompt])
        return self._invoke_cli(cmd, timeout=60.0)

    def poll_artifact(self, notebook_id: str, task_id: str, timeout: int = 60) -> dict[str, Any]:
        """Poll the status of an artifact generation task."""
        return self._invoke_cli(
            ["artifact", "wait", task_id, "--notebook", notebook_id, "--timeout", str(timeout)],
            timeout=float(timeout + 20),
        )

    def download_artifact(self, notebook_id: str, artifact_id: str, output_path: Path | str) -> Path:
        """Download a completed video artifact to local disk."""
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._invoke_cli(
            ["download", "video", str(target), "--notebook", notebook_id, "--artifact", artifact_id, "--force"],
            timeout=300.0,
        )
        return target
