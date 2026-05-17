"""Small network helpers shared by runtime and smoke tests."""

from __future__ import annotations

import socket
from urllib.parse import urlparse


def tcp_url_reachable(raw_url: str, *, timeout: float) -> bool:
    """Return whether a URL's host and port accept a TCP connection."""
    if "://" not in raw_url:
        raw_url = f"//{raw_url}"
    parsed = urlparse(raw_url, scheme="http")
    if not parsed.hostname:
        return False
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    elif parsed.scheme == "http":
        port = 80
    else:
        return False
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return True
    except OSError:
        return False
