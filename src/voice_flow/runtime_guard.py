"""Keep the desktop UI from attaching to an incompatible Voice Flow backend."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

from voice_flow.runtime_contract import RUNTIME_CONTRACT_VERSION


@dataclass(frozen=True)
class RuntimePortResult:
    status: str
    terminated_pids: tuple[int, ...] = ()


def runtime_is_compatible(*, host: str = "127.0.0.1", port: int = 8991, timeout: float = 0.3) -> bool:
    """Return true only when the listener implements this UI's API contract."""
    try:
        request = urllib.request.Request(
            f"http://{host}:{port}/api/runtime",
            headers={"User-Agent": "VoiceFlowRuntimeGuard"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        return (
            response.status == 200
            and payload.get("contract_version") == RUNTIME_CONTRACT_VERSION
            and payload.get("features", {}).get("video_flow_providers") is True
            and payload.get("features", {}).get("agentic_video_flow") is True
        )
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return False


def listener_pids(host: str, port: int) -> list[int]:
    """Return PIDs listening on the exact loopback port, if psutil is available."""
    try:
        import psutil
    except ImportError:
        return []

    accepted_hosts = {host, "0.0.0.0", "::", "::1"}
    found: set[int] = set()
    for connection in psutil.net_connections(kind="tcp"):
        address = connection.laddr
        if not address or int(address.port) != int(port) or str(address.ip) not in accepted_hosts:
            continue
        if connection.status == psutil.CONN_LISTEN and connection.pid:
            found.add(int(connection.pid))
    return sorted(found)


def _is_voice_flow_process(process: object) -> bool:
    try:
        pid = int(getattr(process, "pid"))
        if pid == os.getpid():
            return False
        command = " ".join(str(part).lower() for part in process.cmdline())
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    return "voice_flow.main" in command or "voice_flow.gui.api_server" in command


def terminate_voice_flow_listeners(pids: Iterable[int], *, timeout: float = 4.0) -> list[int]:
    """Terminate only verified Voice Flow listener trees; never touch a foreign service."""
    try:
        import psutil
    except ImportError:
        return []

    targets: dict[int, object] = {}
    for pid in pids:
        try:
            process = psutil.Process(int(pid))
            if not _is_voice_flow_process(process):
                continue
            targets[int(process.pid)] = process
            for child in process.children(recursive=True):
                command = " ".join(child.cmdline()).lower()
                if _is_voice_flow_process(child) or "voice_flow.gui.desktop_launcher" in command:
                    targets[int(child.pid)] = child
        except (psutil.Error, OSError):
            continue

    for process in sorted(targets.values(), key=lambda item: int(item.pid), reverse=True):
        try:
            process.terminate()
        except psutil.Error:
            pass
    if targets:
        psutil.wait_procs(list(targets.values()), timeout=timeout)
    return sorted(targets)


def prepare_runtime_port(*, host: str = "127.0.0.1", port: int = 8991) -> RuntimePortResult:
    """Keep a compatible runtime, reclaim a stale Voice Flow runtime, or report a foreign owner."""
    if runtime_is_compatible(host=host, port=port):
        return RuntimePortResult("compatible")

    pids = listener_pids(host, port)
    if not pids:
        return RuntimePortResult("available")

    terminated = terminate_voice_flow_listeners(pids)
    if not terminated:
        return RuntimePortResult("occupied")

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not listener_pids(host, port):
            return RuntimePortResult("reclaimed", tuple(terminated))
        time.sleep(0.05)
    return RuntimePortResult("occupied", tuple(terminated))
