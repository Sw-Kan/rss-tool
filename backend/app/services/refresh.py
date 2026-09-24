"""抓取管线：拉取 → 解析 → 分类 → upsert。

写权限（AGENTS.md §4）：只写 articles 与 feeds 的抓取元数据，**永不触碰 user_item_state**。
因此重复刷新不会丢已读/收藏。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Article, Feed, Folder, Subscription, User
from ..schemas import RefreshResult
from . import classify, feed_fetch, feed_parse
from .feed_fetch import FetchError

# 同一源不并发抓取
_locks: dict[str, asyncio.Lock] = {}
# 目录批量刷新的并发上限
_BATCH_CONCURRENCY = 5


def _lock_for(url: str) -> asyncio.Lock:
    lock = _locks.get(url)
    if lock is None:
        lock = asyncio.Lock()
        _locks[url] = lock
    return lock


@dataclass(slots=True)
class LoadedFeed:
    parsed: feed_parse.ParsedFeed
    etag: str | None
    modified: str | None
    final_url: str
    not_modified: bool


async def load_remote(
    url: str, *, etag: str | None = None, modified: str | None = None
) -> LoadedFeed:
    result = await feed_fetch.fetch(url, etag=etag, modified=modified)
    if result.not_modified:
        return LoadedFeed(
            parsed=feed_parse.ParsedFeed(None, None, None, None, []),
            etag=result.etag,
            modified=result.modified,
            final_url=result.final_url,
            not_modified=True,
        )
    settings = get_settings()
    parsed = await asyncio.to_thread(
        feed_parse.parse,
        result.content,
        base_url=result.final_url,
        max_entries=settings.fetch_max_entries,
    )
    return LoadedFeed(
        parsed=parsed,
        etag=result.etag,
        modified=result.modified,
        final_url=result.final_url,
        not_modified=False,
    )


def store_articles(db: Session, feed: Feed, parsed: feed_parse.ParsedFeed) -> int:
    """按 (feed_id, guid) upsert。只更新内容字段，不动订阅与用户状态。"""
    if not parsed.entries:
        return 0
    guids = [entry.guid for entry in parsed.entries]
    existing = {
        row.guid: row
        for row in db.scalars(
            select(Article).where(Article.feed_id == feed.id, Article.guid.in_(guids))
        )
    }
    created = 0
    for entry in parsed.entries:
        result = classify.classify(entry)
        article = existing.get(entry.guid)
        if article is None:
            article = Article(feed_id=feed.id, guid=entry.guid)
            db.add(article)
            created += 1
        article.url = entry.url
        article.title = entry.title
        article.author = entry.author
        article.channel_name = entry.channel_name or feed.title if result.kind == "video" else None
        article.summary_html = entry.summary_html
        article.content_html = entry.content_html or entry.summary_html
        article.published_at = entry.published_at or datetime.now(UTC)
        article.updated_at = entry.updated_at or article.published_at
        article.kind = result.kind
        article.image_url = result.image_url
        article.image_width = result.image_width
        article.image_height = result.image_height
        article.video_url = result.video_url
        article.word_count = result.word_count
        article.fetched_at = datetime.now(UTC)
    return created


async def refresh_feed(db: Session, feed: Feed) -> RefreshResult:
    """抓取并入库单个源。失败写入 last_error，不抛给调用方。"""
    async with _lock_for(feed.url):
        try:
            loaded = await load_remote(feed.url, etag=feed.etag, modified=feed.modified)
        except FetchError as exc:
            _mark(feed, "error", str(exc))
            db.commit()
            return RefreshResult(feed_id=feed.id, new_count=0, status="error", error=str(exc))
        except ValueError as exc:
            _mark(feed, "error", str(exc))
            db.commit()
            return RefreshResult(feed_id=feed.id, new_count=0, status="error", error=str(exc))

        if loaded.not_modified:
            _mark(feed, "not_modified", None)
            db.commit()
            return RefreshResult(feed_id=feed.id, new_count=0, status="not_modified")

        if loaded.parsed.title and not feed.title:
            feed.title = loaded.parsed.title
        if loaded.parsed.site_url:
            feed.site_url = loaded.parsed.site_url
        if loaded.parsed.description and not feed.description:
            feed.description = loaded.parsed.description
        if loaded.parsed.icon_url:
            feed.icon_url = loaded.parsed.icon_url
        feed.etag = loaded.etag
        feed.modified = loaded.modified

        # ponytail: 同步 DB 写入直接跑在事件循环里。单用户本地 SQLite，写入是毫秒级；
        # 若源数量增长到影响响应，再挪进 asyncio.to_thread（注意 session 不能跨线程共享）。
        new_count = store_articles(db, feed, loaded.parsed)
        _mark(feed, "ok", None)
        db.commit()
        return RefreshResult(feed_id=feed.id, new_count=new_count, status="ok")


async def refresh_feeds(db: Session, feeds: list[Feed]) -> list[RefreshResult]:
    semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)

    async def one(feed: Feed) -> RefreshResult:
        async with semaphore:
            return await refresh_feed(db, feed)

    return list(await asyncio.gather(*(one(feed) for feed in feeds)))


async def create_subscription(
    db: Session,
    user: User,
    url: str,
    *,
    folder_id: str | None,
    title: str | None,
) -> Subscription:
    """新增订阅：先抓取校验并建 feed，再入库文章。失败抛 FetchError/ValueError。"""
    feed = db.scalar(select(Feed).where(Feed.url == url))
    if feed is None:
        loaded = await load_remote(url)
        feed = Feed(
            url=url,
            site_url=loaded.parsed.site_url,
            title=title or loaded.parsed.title or url,
            description=loaded.parsed.description,
            icon_url=loaded.parsed.icon_url,
            etag=loaded.etag,
            modified=loaded.modified,
        )
        db.add(feed)
        db.flush()
        store_articles(db, feed, loaded.parsed)
        _mark(feed, "ok", None)

    if folder_id is not None and db.get(Folder, folder_id) is None:
        raise ValueError("目录不存在")

    subscription = Subscription(
        user_id=user.id,
        feed_id=feed.id,
        folder_id=folder_id,
        custom_title=title if title and feed.title != title else None,
        position=_next_position(db, user.id),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def _next_position(db: Session, user_id: str) -> int:
    last = db.scalar(
        select(Subscription.position)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.position.desc())
        .limit(1)
    )
    return (last or 0) + 1


def _mark(feed: Feed, status: str, error: str | None) -> None:
    feed.last_status = status
    feed.last_error = error
    feed.last_fetched_at = datetime.now(UTC)
