"""High-level NotebookLM service integrating provider, MCP, login, and keepalive."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_PROFILE,
    has_valid_storage_state,
    resolve_notebooklm_cli,
    resolve_notebooklm_mcp,
    resolve_notebooklm_profile,
)
from .keepalive import (
    get_keepalive_service,
    get_keepalive_status,
    start_keepalive_daemon,
    stop_keepalive_daemon,
)
from .login_flow import (
    disconnect_login,
    get_login_state,
    master_token_present,
    self_heal,
    start_login,
    verify_online,
)
from .mcp_client import NotebookLMMcpClient
from .mcp_server import generate_mcp_config, get_mcp_server_info
from .provider import NotebookLMVideoProvider

logger = logging.getLogger(__name__)


class NotebookLMService:
    """Unified service interface for all NotebookLM capabilities in Voice Flow."""

    def __init__(self, profile: str | None = None) -> None:
        self.profile = resolve_notebooklm_profile(profile)
        self._provider: NotebookLMVideoProvider | None = None
        self._mcp_client: NotebookLMMcpClient | None = None

    @property
    def provider(self) -> NotebookLMVideoProvider:
        if self._provider is None or self._provider.profile != self.profile:
            self._provider = NotebookLMVideoProvider(profile=self.profile)
        return self._provider

    @property
    def mcp_client(self) -> NotebookLMMcpClient:
        if self._mcp_client is None or self._mcp_client.profile != self.profile:
            self._mcp_client = NotebookLMMcpClient(profile=self.profile)
        return self._mcp_client

    def get_status(self, *, verify: bool = False, force: bool = False) -> dict[str, Any]:
        """Comprehensive status report of NotebookLM integration health."""
        cli_path = resolve_notebooklm_cli()
        mcp_path = resolve_notebooklm_mcp()
        has_auth = has_valid_storage_state(self.profile)
        durable = master_token_present(self.profile)
        keepalive_stat = get_keepalive_status()

        online_verified = None
        if verify and cli_path:
            try:
                verification = verify_online(profile=self.profile, force=force)
                online_verified = bool(verification.get("authenticated"))
                if not online_verified and not durable:
                    has_auth = False
            except Exception:
                pass

        try:
            from voice_flow.storage import StorageEngine
            storage = StorageEngine()
            email = storage.get_setting("video_flow_notebooklm_email") or None
        except Exception:
            email = None

        return {
            "available": bool(cli_path or mcp_path),
            "authenticated": has_auth,
            "online_verified": online_verified,
            "durable": durable,
            "master_token_present": durable,
            "profile": self.profile,
            "email": email,
            "cli_path": str(cli_path) if cli_path else None,
            "mcp_path": str(mcp_path) if mcp_path else None,
            "keepalive": keepalive_stat,
            "login_state": get_login_state(),
        }

    def start_auth(
        self,
        *,
        switch_account: bool = False,
        direct: bool = True,
        port: int | None = None,
        mode: str = "playwright",
    ) -> dict[str, Any]:
        """Initiate NotebookLM authentication."""
        return start_login(
            profile=self.profile,
            switch_account=switch_account,
            direct=direct,
            port=port,
            mode=mode,
        )

    def disconnect_auth(self) -> dict[str, Any]:
        """Disconnect NotebookLM session and halt keepalive."""
        stop_keepalive_daemon()
        return disconnect_login(profile=self.profile)

    def ensure_fresh_session(self) -> dict[str, Any]:
        """Run headless self-heal to guarantee session cookies are valid."""
        return self_heal(profile=self.profile)

    def start_keepalive(self, interval_seconds: int = 1200) -> bool:
        """Start the background keepalive daemon."""
        return start_keepalive_daemon(self.profile, interval_seconds)

    def stop_keepalive(self) -> bool:
        """Stop the background keepalive daemon."""
        return stop_keepalive_daemon()

    def get_keepalive_status(self) -> dict[str, Any]:
        """Report keepalive service status."""
        return get_keepalive_status()

    def get_mcp_config(self, config_path: Path | str | None = None) -> dict[str, Any]:
        """Get or write MCP client configuration JSON."""
        return generate_mcp_config(self.profile, config_path=config_path)

    def list_notebooks(self) -> list[dict[str, Any]]:
        """List notebooks through the MCP client bridge."""
        return self.mcp_client.list_notebooks()


_SERVICE_INSTANCE: NotebookLMService | None = None


def get_notebooklm_service(profile: str | None = None) -> NotebookLMService:
    """Return the singleton NotebookLMService instance."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = NotebookLMService(profile=profile)
    elif profile and _SERVICE_INSTANCE.profile != resolve_notebooklm_profile(profile):
        _SERVICE_INSTANCE.profile = resolve_notebooklm_profile(profile)
    return _SERVICE_INSTANCE
