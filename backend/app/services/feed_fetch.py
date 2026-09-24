"""HTTP 抓取：条件请求 + 手动重定向 + SSRF 校验 + 体积上限 + 代理。

SSRF 是信任边界，不可省：feed 内容最终会渲染给用户，若服务端能取到内网资源，
恶意 feed 就能借 redirect 把内网响应读出来。每次重定向都重新校验。

每跳重新建客户端，因为代理要按目标地址取舍（见 services/proxy.py）——`no_proxy` 里的
CIDR 还需要拿解析到的 IP 来判断。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from . import proxy

MAX_REDIRECTS = 5
REDIRECT_CODES = (301, 302, 303, 307, 308)


class FetchError(Exception):
    """抓取失败。message 直接面向用户，中文。"""


@dataclass(slots=True)
class FetchResult:
    content: bytes
    etag: str | None
    modified: str | None
    final_url: str
    not_modified: bool = False


def check_url_allowed(url: str) -> list[str]:
    """只允许 http/https，且目标解析到公网地址。返回解析到的 IP，供代理的 no_proxy 判断。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("只支持 http / https 地址")
    if not parsed.hostname:
        raise FetchError("地址缺少主机名")

    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 0, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"无法解析主机名：{parsed.hostname}") from exc

    addresses = list({info[4][0] for info in infos})
    if get_settings().allow_private_fetch:
        return addresses

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise FetchError("出于安全考虑，不允许抓取内网或本机地址")
    return addresses


async def fetch(
    url: str,
    *,
    etag: str | None = None,
    modified: str | None = None,
    accept: str | None = None,
    max_bytes: int | None = None,
    timeout: float | None = None,
    proxy_spec: proxy.ProxySpec | None = None,
    referer: str | None = None,
) -> FetchResult:
    settings = get_settings()
    spec = proxy_spec if proxy_spec is not None else proxy.ProxySpec()
    headers = {
        "User-Agent": settings.fetch_user_agent,
        "Accept": accept
        or "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    if referer:
        headers["Referer"] = referer

    limit = max_bytes if max_bytes is not None else settings.fetch_max_bytes
    request_timeout = timeout if timeout is not None else settings.fetch_timeout_seconds

    current = url
    for _ in range(MAX_REDIRECTS + 1):
        addresses = await asyncio.to_thread(check_url_allowed, current)
        client = proxy.build_client(
            spec, current, addresses, timeout=request_timeout, follow_redirects=False
        )
        async with client:
            try:
                response = await client.get(current, headers=headers)
            except httpx.TimeoutException as exc:
                raise FetchError("请求超时") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"请求失败：{exc}") from exc

        if response.status_code in REDIRECT_CODES:
            location = response.headers.get("location")
            if not location:
                raise FetchError("重定向缺少 Location")
            current = str(response.url.join(location))
            continue

        if response.status_code == 304:
            return FetchResult(b"", etag, modified, current, not_modified=True)
        if response.status_code >= 400:
            raise FetchError(f"源返回 HTTP {response.status_code}")

        content = response.content
        if len(content) > limit:
            raise FetchError(f"响应过大（超过 {limit // (1024 * 1024)}MB）")
        return FetchResult(
            content=content,
            etag=response.headers.get("etag"),
            modified=response.headers.get("last-modified"),
            final_url=current,
        )

    raise FetchError("重定向次数过多")
