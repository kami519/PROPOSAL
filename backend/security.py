from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from .errors import AppError

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def normalize_url(raw: str) -> str:
    """Validate and normalize a user supplied media URL.

    We only accept public http(s) URLs. This is intentionally strict because the
    backend fetches arbitrary URLs on behalf of the caller (SSRF surface).
    """

    if not isinstance(raw, str):
        raise AppError("INVALID_URL", "请输入一个有效的视频链接。")

    value = raw.strip()
    if not value:
        raise AppError("INVALID_URL", "链接不能为空，先粘贴一个视频地址。")
    if len(value) > 2048:
        raise AppError("INVALID_URL", "链接太长了，请检查后重试。")
    if _CONTROL_RE.search(value):
        raise AppError("INVALID_URL", "链接中包含无法识别的字符。")

    # Reject dangerous non-http schemes before adding a default scheme.
    if re.match(r"^(javascript|data|file|ftp|blob|mailto|ws|wss|vbscript|about):", value, re.I):
        raise AppError("INVALID_URL", "只支持 http / https 视频链接。")

    if not _SCHEME_RE.match(value):
        value = "https://" + value

    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise AppError("INVALID_URL", "只支持 http / https 视频链接。")
    if not parsed.hostname:
        raise AppError("INVALID_URL", "这个链接缺少有效的域名。")
    if parsed.username or parsed.password:
        raise AppError("INVALID_URL", "链接中不能包含账号密码信息。")
    if any(ch.isspace() for ch in parsed.hostname):
        raise AppError("INVALID_URL", "域名格式不正确。")

    _assert_public_host(parsed.hostname)
    return value


def _assert_public_host(hostname: str) -> None:
    host = hostname.strip().strip("[]").lower()
    if host in {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}:
        raise AppError("INVALID_URL", "不支持本机或内网地址。")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        _assert_public_ip(literal)
        return

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        # Let yt-dlp produce the platform-specific error. We only need to stop
        # URLs that resolve to private infrastructure.
        return

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        _assert_public_ip(ip)


def _assert_public_ip(ip: ipaddress._BaseAddress) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise AppError("INVALID_URL", "不支持本机或内网地址。")



