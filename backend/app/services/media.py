"""F6 媒体缓存：把外链图片经后端代理并落盘。

为什么需要：很多源对图片做了防盗链（Referer 白名单）或不允许热链，浏览器直连会
403/破图；外链失效后旧文章就永久失去配图。经后端取一次并缓存，两个问题一起解决。

安全边界（这里是信任边界，不能省）：
1. 只缓存**栅格图**白名单里的类型。**绝不缓存 SVG** —— SVG 能带脚本，从我们自己的
   源上返回等于开了 XSS（用户直接打开 `/api/media?url=...` 就会渲染）。
2. 取图复用 `feed_fetch.fetch`，因此 SSRF 校验、重定向复检、超时、体积上限与抓取
   订阅同源，不另起一套 HTTP。
3. 拉取失败时**302 回原地址**，让浏览器自己去试；比直接 404 更稳（服务端被墙、
   浏览器却能访问的情况很常见）。
4. 失败也记一行（`status=failed`），在 `MEDIA_RETRY_HOURS` 内不再重试，否则一屏
   几十张坏图会在每次刷新页面时把上游打一遍。

容量：文件落 `data/media/`，按 `hash[:2]/hash[2:4]/` 分片。总字节超过
`MEDIA_CACHE_MAX_MB` 就按 LRU（`last_used_at`）淘汰，避免磁盘无限增长。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import MediaCache
from . import feed_fetch, proxy
from .feed_fetch import FetchError

logger = logging.getLogger("rss-tool.media")

# 只允许这些栅格图。SVG 故意不在其中（能带脚本，同源返回等于 XSS）。
ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
}

ACCEPT_IMAGE = "image/avif,image/webp,image/png,image/jpeg,image/gif,image/*;q=0.8"

# 命中时更新 last_used_at 的最小间隔：一屏几十张图，没必要每次都写库
TOUCH_INTERVAL = timedelta(hours=1)


@dataclass(slots=True)
class MediaResult:
    """四种结果。

    - `cached` / `fetched`：有文件，直接回
    - `miss`：该去上游取一次（冷启动、文件被删、重试窗口已过）
    - `skip`：**别去取**，直接 302 回原地址（缓存关闭、地址不支持、刚失败过）
    """

    kind: str  # cached | fetched | miss | skip
    path: Path | None = None
    content_type: str = ""
    reason: str = ""


def key_for(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def is_cacheable_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def media_root() -> Path:
    root = get_settings().data_path / "media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def path_for(key: str) -> Path:
    """hash 是 sha256 十六进制，按两位分片，避免单目录几万个文件。"""
    return media_root() / key[:2] / key[2:4] / key


def sniff_content_type(raw: bytes) -> str | None:
    """按魔数判类型，不信上游声明的 Content-Type（声明成 image/png 的可能是 HTML）。"""
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    if raw[:2] == b"BM":
        return "image/bmp"
    return None


def _row(db: Session, key: str) -> MediaCache | None:
    return db.get(MediaCache, key)


def _fresh(row: MediaCache, now: datetime) -> bool:
    """失败行在重试窗口内不重试；成功行永远算新鲜。"""
    if row.status == "ok":
        return True
    retry_after = row.fetched_at + timedelta(hours=get_settings().media_retry_hours)
    return now < retry_after


def lookup(db: Session, url: str) -> MediaResult:
    """只看缓存，不发网络请求。"""
    if not get_settings().media_cache_enabled:
        return MediaResult("skip", reason="disabled")
    if not is_cacheable_url(url):
        return MediaResult("skip", reason="unsupported url")

    key = key_for(url)
    row = _row(db, key)
    now = datetime.now(UTC)

    if row is None:
        return MediaResult("miss", reason="cold")

    if row.status == "ok":
        path = path_for(key)
        if path.exists():
            if now - row.last_used_at > TOUCH_INTERVAL:
                row.last_used_at = now
                row.hits += 1
                db.commit()
            return MediaResult("cached", path=path, content_type=row.content_type)

        # 文件被外部删掉了：把行清掉重新走一次
        db.delete(row)
        db.commit()
        return MediaResult("miss", reason="file gone")

    if _fresh(row, now):
        return MediaResult("skip", reason=row.error or "recent failure")

    return MediaResult("miss", reason="retry window passed")


async def fetch_and_store(db: Session, url: str) -> MediaResult:
    """取图并落盘。失败写一行 failed 记录后返回 miss。"""
    settings = get_settings()
    if not settings.media_cache_enabled:
        return MediaResult("skip", reason="disabled")
    if not is_cacheable_url(url):
        return MediaResult("skip", reason="unsupported url")

    key = key_for(url)
    spec = proxy.load_spec(db)

    try:
        fetched = await feed_fetch.fetch(
            url,
            accept=ACCEPT_IMAGE,
            max_bytes=settings.media_max_bytes,
            timeout=settings.media_fetch_timeout_seconds,
            proxy_spec=spec,
            referer=referer_for(url),
        )
    except FetchError as exc:
        _record_failure(db, key, url, str(exc))
        return MediaResult("skip", reason=str(exc))

    if fetched.not_modified or not fetched.content:
        _record_failure(db, key, url, "空响应")
        return MediaResult("skip", reason="empty response")

    content_type = sniff_content_type(fetched.content)
    if content_type is None or content_type not in ALLOWED_TYPES:
        # 不缓存也不报错：交给浏览器直接去试（可能是 svg，也可能根本不是图）
        _record_failure(db, key, url, f"不支持的类型（{content_type or '无法识别'}）")
        return MediaResult("skip", reason="unsupported content type")

    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(fetched.content)

    now = datetime.now(UTC)
    row = _row(db, key)
    if row is None:
        row = MediaCache(hash=key, url=url)
        db.add(row)
    row.content_type = content_type
    row.bytes = len(fetched.content)
    row.status = "ok"
    row.error = None
    row.fetched_at = now
    row.last_used_at = now
    db.commit()

    # 保护刚写入的这一条：预算比单张图还小时不能把它自己也淘汰掉，
    # 否则"刚取到的图"紧接着就 302，等于缓存完全失效。
    _evict(db, keep=key)
    logger.info("media: 缓存 %s（%s，%s 字节）", url, content_type, row.bytes)
    return MediaResult("fetched", path=target, content_type=content_type)


def referer_for(url: str) -> str:
    """取图时带 Referer —— 大量 CDN 用它做防盗链，不带就是 403。

    用图片自身的 origin（等于告诉 CDN "你自己引用了自己"），既满足白名单校验，
    又不向第三方泄露我们是从哪个页面过来的。
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _record_failure(db: Session, key: str, url: str, error: str) -> None:
    now = datetime.now(UTC)
    row = _row(db, key)
    if row is None:
        row = MediaCache(hash=key, url=url)
        db.add(row)
    row.status = "failed"
    row.error = error[:300]
    row.bytes = 0
    row.fetched_at = now
    row.last_used_at = now
    row.content_type = ""
    db.commit()
    logger.info("media: 取图失败 %s（%s）", url, error)


def total_bytes(db: Session) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(MediaCache.bytes), 0))) or 0)


def _evict(db: Session, keep: str | None = None) -> int:
    """按 LRU 淘汰到预算之内。`keep` 指定的条目不参与淘汰（保护刚写入的那条）。"""
    budget = get_settings().media_cache_max_mb * 1024 * 1024
    removed = 0
    while total_bytes(db) > budget:
        condition = [MediaCache.status == "ok"]
        if keep is not None:
            condition.append(MediaCache.hash != keep)
        victim = db.scalar(
            select(MediaCache).where(*condition).order_by(MediaCache.last_used_at.asc()).limit(1)
        )
        if victim is None:
            break
        path = path_for(victim.hash)
        path.unlink(missing_ok=True)
        db.delete(victim)
        db.commit()
        removed += 1

    if removed:
        logger.info("media: 超出预算，按 LRU 淘汰 %s 个文件", removed)
    return removed


def clear_failures(db: Session) -> int:
    """清掉失败记录，让下次请求重新尝试。

    在代理配置变更时调用：失败很可能就是代理造成的，改完还留着旧记录挡重试，
    用户会觉得"改了没用"。成功的缓存不动。
    """
    removed = db.query(MediaCache).filter(MediaCache.status == "failed").delete()
    db.commit()
    if removed:
        logger.info("media: 清掉 %s 条失败记录（代理配置变更）", removed)
    return int(removed)


def clear(db: Session) -> None:
    """清空缓存（「清空本地数据」会调用）。"""
    db.query(MediaCache).delete()
    db.commit()

    root = get_settings().data_path / "media"
    if root.exists():
        import shutil

        shutil.rmtree(root, ignore_errors=True)
