"""Production input adapters kept outside evidence extraction policy."""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from typing import Any


class SafeHttpRetrievalAdapter:
    """Fetch public http(s) source text with SSRF and size protections."""

    name = "video-flow.public-http"

    def __init__(self, *, timeout: float = 20.0, max_bytes: int = 2_500_000) -> None:
        self.timeout = max(1.0, float(timeout))
        self.max_bytes = max(16_384, int(max_bytes))

    def retrieve(self, url: str, **_: Any) -> dict[str, Any]:
        adapter = self

        class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
                adapter._safe_url(newurl)
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        safe_url = self._safe_url(url)
        request = urllib.request.Request(
            safe_url,
            headers={
                "User-Agent": "VoiceFlow-VideoFlow/1.0 (+local explanatory video source fetch)",
                "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.2",
            },
        )
        opener = urllib.request.build_opener(SafeRedirectHandler())
        with opener.open(request, timeout=self.timeout) as response:
            final_url = self._safe_url(response.geturl())
            content_type = str(response.headers.get_content_type() or "text/plain").lower()
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(self.max_bytes + 1)
            if len(raw) > self.max_bytes:
                raise ValueError("The URL response is too large for a single Video Flow source.")
            text = raw.decode(charset, errors="replace")
            if content_type in {"text/html", "application/xhtml+xml"}:
                text, title = self._html_text(text)
            elif content_type == "application/json":
                title = urllib.parse.urlparse(final_url).netloc
            elif content_type.startswith("text/"):
                title = urllib.parse.urlparse(final_url).netloc
            else:
                raise ValueError(f"URL returned unsupported content type: {content_type}")
        clean = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(clean) < 40:
            raise ValueError(
                "The page did not expose enough readable text. Paste the post/article text or attach a screenshot."
            )
        return {
            "text": clean,
            "title": title,
            "url": final_url,
            "content_type": content_type,
            "status": int(getattr(response, "status", 200)),
        }

    @staticmethod
    def _safe_url(url: str) -> str:
        parsed = urllib.parse.urlsplit(str(url).strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only absolute public http(s) URLs are supported.")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing credentials are not allowed.")
        host = parsed.hostname.lower().rstrip(".")
        if host in {"localhost", "localhost.localdomain"}:
            raise ValueError("Local URLs are not allowed.")
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    host,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise ValueError("The source hostname could not be resolved.") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("Private, loopback, link-local, and reserved source addresses are not allowed.")
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))

    @staticmethod
    def _html_text(document: str) -> tuple[str, str]:
        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", document)
        title = html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1))).strip() if title_match else ""
        clean = re.sub(r"(?is)<(?:script|style|noscript|svg|template|nav|footer).*?>.*?</(?:script|style|noscript|svg|template|nav|footer)>", " ", document)
        clean = re.sub(r"(?i)<br\s*/?>|</(?:p|div|article|section|main|h[1-6]|li|tr)>", "\n", clean)
        clean = re.sub(r"(?s)<[^>]+>", " ", clean)
        clean = html.unescape(clean)
        clean = re.sub(r"[ \t\f\v]+", " ", clean)
        clean = re.sub(r" *\n *", "\n", clean)
        return clean, title


class GatewayVisionAdapter:
    """Optional screenshot/image adapter backed by the selected model gateway."""

    name = "video-flow.selected-model-vision"

    def __init__(self, analyze: Any) -> None:
        self._analyze = analyze

    def analyze(self, image: Any, **context: Any) -> Any:
        return self._analyze(image, context)


__all__ = ["GatewayVisionAdapter", "SafeHttpRetrievalAdapter"]
