"""F4 代理：配置解析 + 按目标地址决定是否走代理。

设计稿的四种模式：默认（跟随系统）/ 本地 HTTP / 本地 HTTPS / 自定义。

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

MODES = ("system", "http", "https", "custom")


@dataclass(slots=True)
class ProxySpec:
    mode: str = "system"
    url: str = ""
    patterns: list[str] = field(default_factory=list)

    @property
    def configured(self) -> bool:
        """是否真的会让流量经过代理。"""
        return self.mode != "system" and bool(self.url)


def parse_no_proxy(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def load_spec(db: Session) -> ProxySpec:
    row = db.get(ProxyConfig, "default")
    if row is None:
        return ProxySpec()
    return ProxySpec(mode=row.mode, url=row.url, patterns=parse_no_proxy(row.no_proxy))


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

    - `system`：交给 httpx 读进程环境变量。环境里的代理写在 `ALL_PROXY` 之类变量上时
      可能是 httpx 不认识的 scheme（例如 socks://），此时降级为直连并记警告——否则
      用户没碰过代理设置，所有订阅都会莫名失败。
    - `http` / `https`：只代理对应 scheme，另一个 scheme 直连。
    - `custom`：全部流量走该地址（httpx 支持 socks5:// ，需要 socksio）。
    """
    host = (urlparse(url).hostname or "").lower()

    if spec.mode == "system":
        if bypass(spec, host, addresses):
            return {"trust_env": False}
        return {"trust_env": True}

    if not spec.url or bypass(spec, host, addresses):
        return {"trust_env": False}

    if spec.mode == "custom":
        return {"trust_env": False, "proxy": spec.url}

    proxied, direct = ("http", "https") if spec.mode == "http" else ("https", "http")
    if urlparse(url).scheme != proxied:
        _ = direct
        return {"trust_env": False}
    return {"trust_env": False, "proxy": spec.url}


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
    if not spec.url:
        return f"{spec.mode} 未填写地址，按直连"
    return spec.url
