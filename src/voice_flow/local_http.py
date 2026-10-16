"""HTTP helpers for calls to services on this machine (127.0.0.1 / localhost).

Loopback traffic must never be routed through an HTTP(S) proxy: a corporate
or system proxy would receive local dictation prompts, and it would also
answer health checks on behalf of a service that is not running.

* :func:`open_local` opens a loopback URL with an opener that has no proxy
  handler at all (it refuses non-loopback URLs).
* :func:`install_loopback_proxy_bypass` installs a process-wide urllib
  opener whose proxy handler skips loopback hosts but keeps using the
  system/environment proxy for every other host, so existing
  ``urllib.request.urlopen`` call sites that talk to the local API server
  stop going through the proxy without touching remote behaviour.
* :func:`no_proxy_environment` adds loopback hosts to ``NO_PROXY`` for the
  environment of spawned child processes.

We deliberately do not export ``NO_PROXY`` into this process's own
environment: on Windows, urllib and requests ignore the registry (system)
proxy as soon as any ``*_proxy`` environment variable is present, which
would silently disable the user's proxy for cloud calls.
"""
from __future__ import annotations

import ipaddress
import threading
import urllib.parse
import urllib.request
from typing import Any, MutableMapping

LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")
_NO_PROXY_HOSTS = ("127.0.0.1", "localhost", "::1")


def is_loopback_host(host: str | None) -> bool:
    """Whether *host* (no port) names this machine's loopback interface."""
    value = str(host or "").strip().lower()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if not value:
        return False
    if value == "localhost" or value.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def is_loopback_url(url: str | None) -> bool:
    try:
        return is_loopback_host(urllib.parse.urlsplit(str(url or "")).hostname)
    except ValueError:
        return False


def _request_url(request: Any) -> str:
    return request.full_url if isinstance(request, urllib.request.Request) else str(request)


_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def open_local(request: Any, data: bytes | None = None, timeout: float = 5.0):
    """``urlopen`` for loopback URLs that never consults any proxy setting."""
    url = _request_url(request)
    if not is_loopback_url(url):
        raise ValueError(f"open_local only accepts loopback URLs, got {url!r}")
    return _DIRECT_OPENER.open(request, data=data, timeout=timeout)


class LoopbackBypassProxyHandler(urllib.request.ProxyHandler):
    """Default proxy handling, except loopback hosts always connect directly."""

    def proxy_open(self, req, proxy, type):  # noqa: A002 - urllib signature
        try:
            host = urllib.parse.urlsplit(req.full_url).hostname
        except ValueError:
            host = None
        if is_loopback_host(host):
            return None  # let the plain HTTP(S) handler connect directly
        return super().proxy_open(req, proxy, type)


_install_lock = threading.Lock()
_installed = False


def install_loopback_proxy_bypass() -> None:
    """Install a global urllib opener that never proxies loopback requests.

    Idempotent. Remote hosts keep the normal environment/registry proxy.
    """
    global _installed
    with _install_lock:
        if _installed:
            return
        urllib.request.install_opener(urllib.request.build_opener(LoopbackBypassProxyHandler()))
        _installed = True


def no_proxy_environment(env: MutableMapping[str, str] | None = None) -> dict[str, str]:
    """Return a copy of *env* whose NO_PROXY/no_proxy include loopback hosts."""
    import os

    result = dict(os.environ if env is None else env)
    for key in ("NO_PROXY", "no_proxy"):
        existing = [part.strip() for part in str(result.get(key, "")).split(",") if part.strip()]
        for host in _NO_PROXY_HOSTS:
            if host not in existing:
                existing.append(host)
        result[key] = ",".join(existing)
    return result


# Importing this module (runtime_guard, vf1_engine and the launcher import it
# early) makes every plain urllib call to the local API bypass proxies.
install_loopback_proxy_bypass()
