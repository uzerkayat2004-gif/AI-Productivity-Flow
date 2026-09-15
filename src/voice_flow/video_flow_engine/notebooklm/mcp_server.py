"""NotebookLM MCP server process management and configuration generator.

Supports:
- Locating the installed `notebooklm-mcp.exe` executable across isolated venvs,
  system PATH, and configured settings.
- Generating and validating standard MCP configuration JSON (`notebooklm-mcp-config.json`)
  for integration with AI agents, Claude Code, Cursor, Antigravity, or internal bridges.
- Inspecting MCP server health and credentials.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_MCP_CONFIG_PATH,
    DEFAULT_PROFILE,
    ISOLATED_MCP_PATH,
    get_profile_dir,
    get_storage_state_path,
    has_valid_storage_state,
    resolve_notebooklm_mcp,
    resolve_notebooklm_profile,
)

logger = logging.getLogger(__name__)

_HIDE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def resolve_mcp_binary(explicit_path: Path | str | None = None) -> Path | None:
    """Resolve the path to the `notebooklm-mcp.exe` binary."""
    return resolve_notebooklm_mcp(explicit_path)


def get_default_mcp_config_path() -> Path:
    """Return the default path to notebooklm-mcp-config.json."""
    env_cfg = os.environ.get("NOTEBOOKLM_MCP_CONFIG")
    if env_cfg:
        return Path(env_cfg).expanduser().resolve()
    if DEFAULT_MCP_CONFIG_PATH.parent.is_dir():
        return DEFAULT_MCP_CONFIG_PATH
    try:
        from voice_flow.paths import data_dir
        return data_dir() / "notebooklm-mcp-config.json"
    except Exception:
        return Path.home() / ".notebooklm" / "notebooklm-mcp-config.json"


def generate_mcp_config(
    profile: str | None = None,
    *,
    config_path: Path | str | None = None,
    transport: str = "stdio",
    server_name: str = "notebooklm",
) -> dict[str, Any]:
    """Generate the standard MCP server configuration dictionary.

    Optionally writes the configuration to `config_path`.
    """
    profile = resolve_notebooklm_profile(profile)
    mcp_path = resolve_mcp_binary()
    command = str(mcp_path) if mcp_path else "notebooklm-mcp"

    args = ["--profile", profile]
    if transport != "stdio":
        args.extend(["--transport", transport])

    config_dict: dict[str, Any] = {
        "mcpServers": {
            server_name: {
                "command": command,
                "args": args,
            }
        }
    }

    target = Path(config_path).expanduser().resolve() if config_path else get_default_mcp_config_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(config_dict, indent=2), encoding="utf-8")
        logger.debug("Wrote MCP config to %s", target)
    except Exception as exc:
        logger.warning("Could not write MCP config to %s: %s", target, exc)

    return config_dict


def get_mcp_server_info(profile: str | None = None) -> dict[str, Any]:
    """Return status and configuration details for the NotebookLM MCP server."""
    profile = resolve_notebooklm_profile(profile)
    mcp_path = resolve_mcp_binary()
    cfg_path = get_default_mcp_config_path()
    has_creds = has_valid_storage_state(profile)
    st_path = get_storage_state_path(profile)

    available = bool(mcp_path and mcp_path.is_file())
    configured = bool(cfg_path.is_file())

    try:
        from .login_flow import master_token_present
        has_master_token = master_token_present(profile)
    except Exception:
        has_master_token = False

    return {
        "available": available,
        "mcp_path": str(mcp_path) if mcp_path else None,
        "config_path": str(cfg_path),
        "config_exists": configured,
        "profile": profile,
        "authenticated": has_creds,
        "master_token_present": has_master_token,
        "storage_path": str(st_path),
    }


def launch_mcp_process(
    profile: str | None = None,
    *,
    transport: str = "stdio",
    port: int = 9420,
    log_level: str = "INFO",
) -> subprocess.Popen[str]:
    """Launch the NotebookLM MCP server process with appropriate environment."""
    profile = resolve_notebooklm_profile(profile)
    mcp_path = resolve_mcp_binary()
    if not mcp_path or not mcp_path.is_file():
        raise FileNotFoundError(f"NotebookLM MCP server binary not found: {mcp_path}")

    cmd = [
        str(mcp_path),
        "--profile", profile,
        "--transport", transport,
        "--log-level", log_level,
    ]
    if transport == "http":
        cmd.extend(["--port", str(int(port))])

    env = dict(os.environ)
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        creationflags=_HIDE_FLAGS,
    )
