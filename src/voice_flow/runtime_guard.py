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


def _runtime_payload(*, host: str, port: int, timeout: float) -> dict | None:
    try:
        request = urllib.request.Request(
            f"http://{host}:{port}/api/runtime",
            headers={"User-Agent": "VoiceFlowRuntimeGuard"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
            if response.status != 200 or not isinstance(payload, dict):
                return None
        return payload
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return None


def _matches_runtime_contract(payload: dict | None) -> bool:
    return bool(
        payload
        and payload.get("contract_version") == RUNTIME_CONTRACT_VERSION
        and payload.get("features", {}).get("video_flow_providers") is True
        and payload.get("features", {}).get("agentic_video_flow") is True
    )


def runtime_is_compatible(*, host: str = "127.0.0.1", port: int = 8991, timeout: float = 0.3) -> bool:
    """Return true only when the listener implements this UI's API contract."""
    return _matches_runtime_contract(_runtime_payload(host=host, port=port, timeout=timeout))


def runtime_is_engine_ready(*, host: str = "127.0.0.1", port: int = 8991, timeout: float = 0.3) -> bool:
    """Return true only for a compatible runtime with a live dictation controller."""
    payload = _runtime_payload(host=host, port=port, timeout=timeout)
    return _matches_runtime_contract(payload) and payload.get("engine_ready") is True


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
    return "voice_flow" in command or "desktop_launcher" in command


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
            # Desktop GUI window must never be terminated by port reclamation
            cmd = " ".join(process.cmdline()).lower()
            if "voice_flow.gui.desktop_launcher" in cmd:
                continue
            targets[int(process.pid)] = process
            for child in process.children(recursive=True):
                command = " ".join(child.cmdline()).lower()
                if "voice_flow.gui.desktop_launcher" in command:
                    continue
                if _is_voice_flow_process(child):
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


def prepare_runtime_port(
    *,
    host: str = "127.0.0.1",
    port: int = 8991,
    require_engine: bool = False,
) -> RuntimePortResult:
    """Keep a compatible runtime, reclaim a stale Voice Flow runtime, or report a foreign owner."""
    readiness_probe = runtime_is_engine_ready if require_engine else runtime_is_compatible
    if readiness_probe(host=host, port=port):
        return RuntimePortResult("compatible")

    # A free port must be detected instantly: the 8s boot-time grace only
    # makes sense when something IS listening but still cold-importing.
    # Read the listener set ONCE: a duplicated pre-grace read consumed a
    # second probe, so a stale Voice Flow listener looked free on the
    # duplicate read and was reported 'available' instead of reclaimed.
    pids = listener_pids(host, port)
    if not pids:
        return RuntimePortResult("available")

    # A contract-compatible standalone desktop API is positively identified
    # Voice Flow state, but it cannot capture or transcribe. Engine startup
    # must reclaim it immediately instead of granting cold-boot grace.
    compatible_fallback = require_engine and runtime_is_compatible(host=host, port=port)

    # Boot-time grace: a Voice Flow listener that is still cold-importing its
    # engine (~10s under laptop-boot disk/CPU load) cannot answer the contract
    # probe. Retry patiently before considering a kill or an 'occupied' verdict
    # so a legitimate boot never crash-loops the engine.
    if not compatible_fallback:
        grace_deadline = time.monotonic() + 8.0
        while time.monotonic() < grace_deadline:
            time.sleep(0.6)
            if readiness_probe(host=host, port=port, timeout=0.8):
                return RuntimePortResult("compatible")
            if not listener_pids(host, port):
                # Listener vanished mid-grace (boot race / fast restart): stop
                # waiting and re-evaluate below. terminate_voice_flow_listeners
                # is a no-op for dead PIDs, and the reclaim wait then observes
                # the truly free port.
                break

    # Reuse the pre-grace PID set: re-reading here would race a listener that
    # is mid-restart and misreport it. terminate_voice_flow_listeners only
    # touches verified Voice Flow processes, so stale PIDs are harmless.
    terminated = terminate_voice_flow_listeners(pids)
    if not terminated:
        # Nothing Voice Flow to reclaim: foreign owner — unless the port
        # actually went free in the meantime (boot race), then 'available'.
        if not listener_pids(host, port):
            return RuntimePortResult("available")
        return RuntimePortResult("occupied")

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not listener_pids(host, port):
            return RuntimePortResult("reclaimed", tuple(terminated))
        time.sleep(0.05)
    return RuntimePortResult("occupied", tuple(terminated))
