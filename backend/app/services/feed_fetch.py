"""HTTP 抓取：条件请求 + 手动重定向 + SSRF 校验 + 体积上限。

SSRF 是信任边界，不可省：feed 内容最终会渲染给用户，若服务端能取到内网资源，
恶意 feed 就能借 redirect 把内网响应读出来。每次重定向都重新校验。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from ..config import get_settings

MAX_REDIRECTS = 5


class FetchError(Exception):
    """抓取失败。message 直接面向用户，中文。"""


@dataclass(slots=True)
class FetchResult:
    content: bytes
    etag: str | None
    modified: str | None
    final_url: str
    not_modified: bool = False


def check_url_allowed(url: str) -> None:
    """只允许 http/https，且目标解析到公网地址。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("只支持 http / https 地址")
    if not parsed.hostname:
        raise FetchError("地址缺少主机名")

    settings = get_settings()
    if settings.allow_private_fetch:
        return

    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 0, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"无法解析主机名：{parsed.hostname}") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise FetchError("出于安全考虑，不允许抓取内网或本机地址")


async def fetch(url: str, *, etag: str | None = None, modified: str | None = None) -> FetchResult:
    settings = get_settings()
    headers = {
        "User-Agent": settings.fetch_user_agent,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified

    current = url
    # trust_env=False：不读进程级 HTTP_PROXY/ALL_PROXY 环境变量，保证行为可预测。
    # 代理由后续模块 F4 显式配置（见 docs/roadmap.md）。
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout_seconds,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await asyncio.to_thread(check_url_allowed, current)
            try:
                response = await client.get(current, headers=headers)
            except httpx.TimeoutException as exc:
                raise FetchError("请求超时") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"请求失败：{exc}") from exc

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError("重定向缺少 Location")
                current = str(httpx.URL(current).join(location))
                continue

            if response.status_code == 304:
                return FetchResult(b"", etag, modified, current, not_modified=True)
            if response.status_code >= 400:
                raise FetchError(f"源返回 HTTP {response.status_code}")

            content = response.content
            if len(content) > settings.fetch_max_bytes:
                raise FetchError("源响应过大（超过 5MB）")
            return FetchResult(
                content=content,
                etag=response.headers.get("etag"),
                modified=response.headers.get("last-modified"),
                final_url=current,
            )

    raise FetchError("重定向次数过多")
