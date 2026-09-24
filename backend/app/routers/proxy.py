"""F4 代理接口。实例级单行配置，不按用户分。"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter
from sqlalchemy import select

from ..deps import CurrentUser, DbSession
from ..models import ProxyConfig
from ..schemas import IntegrationTestOut, ProxyOut, ProxyPatch
from ..services import proxy

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
    return ProxyOut(mode=row.mode, url=row.url, no_proxy=row.no_proxy)  # type: ignore[arg-type]


@router.get("", response_model=ProxyOut)
def read_proxy(user: CurrentUser, db: DbSession) -> ProxyOut:
    _ = user
    return _out(_row(db))


@router.patch("", response_model=ProxyOut)
def update_proxy(payload: ProxyPatch, user: CurrentUser, db: DbSession) -> ProxyOut:
    _ = user
    row = _row(db)
    if payload.mode is not None:
        row.mode = payload.mode
    if payload.url is not None:
        row.url = payload.url.strip()
    if payload.no_proxy is not None:
        row.no_proxy = payload.no_proxy.strip()
    if row.mode == "system":
        row.url = ""
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/test", response_model=IntegrationTestOut)
async def test_proxy(user: CurrentUser, db: DbSession) -> IntegrationTestOut:
    """按当前配置真的发一次请求，返回状态与延迟。"""
    _ = user
    spec = proxy.load_spec(db)

    if spec.mode != "system" and not spec.url:
        return IntegrationTestOut(ok=False, message="请先填写代理地址")

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
