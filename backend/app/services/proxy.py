"""F4 代理：配置解析 + 按目标地址决定是否走代理。

两种模式：`system` 跟随进程环境变量；`custom` 用三个地址按目标协议挑一个。

`no_proxy` 支持三种写法：精确域名、`.example.com` / `*.example.com` 后缀、CIDR
（如 `192.168.0.0/16`）。CIDR 需要目标 IP，因此调用方要把 SSRF 校验时解析到的地址
一并传进来，避免重复解析。
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import ProxyConfig

logger = logging.getLogger("rss-tool.proxy")

MODES = ("system", "custom")


@dataclass(slots=True)
class ProxySpec:
    mode: str = "system"
    http_url: str = ""
    https_url: str = ""
    socks5_url: str = ""
    patterns: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return self.mode == "custom" and bool(self.http_url or self.https_url or self.socks5_url)


def parse_no_proxy(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def load_spec(db: Session) -> ProxySpec:
    row = db.get(ProxyConfig, "default")
    if row is None:
        return ProxySpec()
    return ProxySpec(
        mode=row.mode,
        http_url=row.http_url,
        https_url=row.https_url,
        socks5_url=row.socks5_url,
        patterns=parse_no_proxy(row.no_proxy),
    )


def proxy_for(spec: ProxySpec, scheme: str) -> str:
    """按目标协议挑地址；只填了 SOCKS5 时它作为兜底对所有协议生效。"""
    if spec.mode != "custom":
        return ""
    if scheme == "http":
        return spec.http_url or spec.socks5_url
    if scheme == "https":
        return spec.https_url or spec.socks5_url
    return spec.socks5_url or spec.https_url or spec.http_url


def host_matches(host: str, patterns: list[str]) -> bool:
    host = host.strip().lower().rstrip(".")
    if not host:
        return False
    for raw in patterns:
        token = raw.lower().strip()
        if token == "*":
            return True
        pattern = token.lstrip("*.")
        if not pattern:
            continue
        if "/" in pattern:
            continue  # CIDR 由 address_matches 处理
        if host == pattern or host.endswith(f".{pattern}"):
            return True
    return False


def address_matches(addresses: list[str], patterns: list[str]) -> bool:
    for raw in patterns:
        if "/" not in raw:
            continue
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        for address in addresses:
            try:
                if ipaddress.ip_address(address) in network:
                    return True
            except ValueError:
                continue
    return False


def bypass(spec: ProxySpec, host: str, addresses: list[str] | None = None) -> bool:
    """该目标是否应绕过代理。"""
    if not spec.patterns:
        return False
    return host_matches(host, spec.patterns) or address_matches(addresses or [], spec.patterns)


def client_kwargs(spec: ProxySpec, url: str, addresses: list[str] | None = None) -> dict:
    """给 httpx.AsyncClient 用的参数。

    - `system`：交给 httpx 读进程环境变量。
    - `custom`：按目标协议挑地址；一个都没填则直连。
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if bypass(spec, host, addresses):
        return {"trust_env": False}

    if spec.mode == "system":
        return {"trust_env": True}

    chosen = proxy_for(spec, parsed.scheme)
    return {"trust_env": False, "proxy": chosen} if chosen else {"trust_env": False}


def build_client(spec: ProxySpec, url: str, addresses: list[str] | None = None, **kwargs):
    """按配置建 httpx 客户端；代理不可用时降级为直连并记警告。

    典型场景：系统环境里有 `ALL_PROXY=socks://...`，httpx 不认识这个 scheme 会直接抛
    ValueError。用户没碰过代理设置却所有订阅都失败，很难排查，所以这里兜住。
    """
    import httpx

    try:
        return httpx.AsyncClient(**client_kwargs(spec, url, addresses), **kwargs)
    except Exception as exc:  # httpx 对不认识的代理 scheme / 非法地址抛 ValueError
        logger.warning("代理配置不可用（%s），本次按直连处理", exc)
        return httpx.AsyncClient(trust_env=False, **kwargs)


def describe(spec: ProxySpec, url: str | None = None, addresses: list[str] | None = None) -> str:
    """给「测试连接」用的一句话描述：流量实际走了哪条路。"""
    if url is not None:
        host = (urlparse(url).hostname or "").lower()
        if bypass(spec, host, addresses):
            return "直连（NO_PROXY 命中）"

    if spec.mode == "system":
        return "跟随系统"

    scheme = urlparse(url).scheme if url else "https"
    chosen = proxy_for(spec, scheme)
    return chosen or "直连（未填写代理地址）"
