"""F4 代理接口。实例级单行配置，不按用户分。"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter
from sqlalchemy import select

from ..deps import CurrentUser, DbSession
from ..models import ProxyConfig
from ..schemas import IntegrationTestOut, ProxyOut, ProxyPatch
from ..services import media, proxy

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

# 「测试连接」用的目标：小、全球 anycast、对我们的场景足够代表"能不能出网"
PROBE_URL = "https://www.cloudflare.com/cdn-cgi/trace"


def _row(db: DbSession) -> ProxyConfig:
    row = db.scalar(select(ProxyConfig).where(ProxyConfig.id == "default"))
    if row is None:
        row = ProxyConfig(id="default")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _out(row: ProxyConfig) -> ProxyOut:
    return ProxyOut(
        mode=row.mode,  # type: ignore[arg-type]
        http_url=row.http_url,
        https_url=row.https_url,
        socks5_url=row.socks5_url,
        no_proxy=row.no_proxy,
    )


@router.get("", response_model=ProxyOut)
def read_proxy(user: CurrentUser, db: DbSession) -> ProxyOut:
    _ = user
    return _out(_row(db))


@router.patch("", response_model=ProxyOut)
def update_proxy(payload: ProxyPatch, user: CurrentUser, db: DbSession) -> ProxyOut:
    _ = user
    row = _row(db)
    before = (row.mode, row.http_url, row.https_url, row.socks5_url, row.no_proxy)

    if payload.mode is not None:
        row.mode = payload.mode
    if payload.http_url is not None:
        row.http_url = payload.http_url.strip()
    if payload.https_url is not None:
        row.https_url = payload.https_url.strip()
    if payload.socks5_url is not None:
        row.socks5_url = payload.socks5_url.strip()
    if payload.no_proxy is not None:
        row.no_proxy = payload.no_proxy.strip()

    db.commit()
    db.refresh(row)

    # 代理变了，之前的抓取失败很可能已经不复存在；不清掉的话会白等一个重试窗口。
    # 切到 system 也保留自定义那几项，切回来还在。
    if (row.mode, row.http_url, row.https_url, row.socks5_url, row.no_proxy) != before:
        media.clear_failures(db)

    return _out(row)


@router.post("/test", response_model=IntegrationTestOut)
async def test_proxy(user: CurrentUser, db: DbSession) -> IntegrationTestOut:
    """按当前配置真的发一次请求，返回状态与延迟。"""
    _ = user
    spec = proxy.load_spec(db)

    if spec.mode == "custom" and not spec.configured:
        return IntegrationTestOut(ok=False, message="请先填写至少一个代理地址")

    started = time.perf_counter()
    try:
        async with proxy.build_client(spec, PROBE_URL, timeout=10.0) as client:
            response = await client.get(PROBE_URL)
    except httpx.TimeoutException:
        return IntegrationTestOut(ok=False, message="连接超时")
    except httpx.HTTPError as exc:
        return IntegrationTestOut(ok=False, message=f"连接失败：{exc}")

    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return IntegrationTestOut(
            ok=False, message=f"返回 HTTP {response.status_code}", latency_ms=latency
        )
    return IntegrationTestOut(
        ok=True,
        message=f"连接正常 · 经由 {proxy.describe(spec, PROBE_URL)}",
        latency_ms=latency,
    )
