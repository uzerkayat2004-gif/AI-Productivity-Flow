"""Numeric-loopback server policy without hostname discovery or runtime data imports."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from socketserver import TCPServer

LOOPBACK_HOST = "127.0.0.1"


def require_loopback_host(host: str) -> str:
    """Internal app servers/probes support only this numeric IPv4 loopback."""
    if host != LOOPBACK_HOST:
        raise ValueError("Local app server host must be 127.0.0.1")
    return host


class LoopbackHTTPServer(ThreadingHTTPServer):
    """Bind locally without HTTPServer's implicit socket.getfqdn lookup."""

    def server_bind(self) -> None:
        require_loopback_host(self.server_address[0])
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port
