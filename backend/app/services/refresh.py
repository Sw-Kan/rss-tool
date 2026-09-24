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
from . import automation, classify, extract, feed_fetch, feed_parse, proxy
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
    url: str,
    *,
    etag: str | None = None,
    modified: str | None = None,
    proxy_spec: proxy.ProxySpec | None = None,
) -> LoadedFeed:
    result = await feed_fetch.fetch(url, etag=etag, modified=modified, proxy_spec=proxy_spec)
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


def store_articles(db: Session, feed: Feed, parsed: feed_parse.ParsedFeed) -> list[str]:
    """按 (feed_id, guid) upsert。只更新内容字段，不动订阅与用户状态。

    返回本次**新增**的文章 id —— 自动化只对新增文章生效，不能对全量重放。
    """
    if not parsed.entries:
        return []
    guids = [entry.guid for entry in parsed.entries]
    existing = {
        row.guid: row
        for row in db.scalars(
            select(Article).where(Article.feed_id == feed.id, Article.guid.in_(guids))
        )
    }
    created: list[Article] = []
    for entry in parsed.entries:
        result = classify.classify(entry)
        article = existing.get(entry.guid)
        if article is None:
            article = Article(feed_id=feed.id, guid=entry.guid)
            db.add(article)
            created.append(article)
        article.url = entry.url
        article.title = entry.title
        article.author = entry.author
        article.channel_name = entry.channel_name or feed.title if result.kind == "video" else None
        article.published_at = entry.published_at or datetime.now(UTC)
        article.updated_at = entry.updated_at or article.published_at
        article.kind = result.kind
        article.image_url = result.image_url
        article.image_width = result.image_width
        article.image_height = result.image_height
        article.video_url = result.video_url

        # 已抽取的全文不被 feed 的短摘要覆盖（F5）；其余情况照旧更新内容字段。
        if article.content_source != "extracted":
            article.summary_html = entry.summary_html
            article.content_html = entry.content_html or entry.summary_html
            article.word_count = result.word_count
            article.content_source = "feed"
        article.fetched_at = datetime.now(UTC)

    if created:
        # 主键是 Python 侧默认值，flush 之后才有值；自动化要拿这些 id
        db.flush()
    return [article.id for article in created]


async def refresh_feed(
    db: Session, feed: Feed, *, spec: proxy.ProxySpec | None = None
) -> RefreshResult:
    """抓取并入库单个源。失败写入 last_error，不抛给调用方。"""
    proxy_spec = spec if spec is not None else proxy.load_spec(db)
    async with _lock_for(feed.url):
        try:
            loaded = await load_remote(
                feed.url, etag=feed.etag, modified=feed.modified, proxy_spec=proxy_spec
            )
        except FetchError as exc:
            mark_fetched(feed, "error", str(exc))
            db.commit()
            return RefreshResult(feed_id=feed.id, new_count=0, status="error", error=str(exc))
        except ValueError as exc:
            mark_fetched(feed, "error", str(exc))
            db.commit()
            return RefreshResult(feed_id=feed.id, new_count=0, status="error", error=str(exc))

        if loaded.not_modified:
            mark_fetched(feed, "not_modified", None)
            db.commit()
            # 304 也要补正文：文章可能是「添加订阅」时入库的（那条路径不抽取），
            # 若首次刷新恰好 304，不补就永远补不上。
            if _anyone_wants_articles(db, feed.id):
                await extract.extract_pending(db, feed.id, spec=proxy_spec)
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
        new_ids = store_articles(db, feed, loaded.parsed)
        mark_fetched(feed, "ok", None)
        db.commit()

        # F5：feed 正文过短的文章去原网页补齐。任何失败都不影响本次刷新结果。
        # 若所有订阅者都把这个源声明成了图片/视频（没人当文章看），抽取纯属浪费流量。
        if _anyone_wants_articles(db, feed.id):
            await extract.extract_pending(db, feed.id, spec=proxy_spec)

        # F3：自动化只处理本次新增的文章，且放在抽取之后——
        # 「字数 > 3000」这类条件必须看到抽取后的字数。
        await automation.run_for_new_articles(db, feed.id, new_ids)

        return RefreshResult(feed_id=feed.id, new_count=len(new_ids), status="ok")


async def refresh_feeds(db: Session, feeds: list[Feed]) -> list[RefreshResult]:
    semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)
    spec = proxy.load_spec(db)

    async def one(feed: Feed) -> RefreshResult:
        async with semaphore:
            return await refresh_feed(db, feed, spec=spec)

    return list(await asyncio.gather(*(one(feed) for feed in feeds)))


async def create_subscription(
    db: Session,
    user: User,
    url: str,
    *,
    folder_id: str | None,
    title: str | None,
    kind: str = "auto",
) -> Subscription:
    """新增订阅：先抓取校验并建 feed，再入库文章。失败抛 FetchError/ValueError。"""
    feed = db.scalar(select(Feed).where(Feed.url == url))
    if feed is None:
        loaded = await load_remote(url, proxy_spec=proxy.load_spec(db))
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
        created = store_articles(db, feed, loaded.parsed)
        mark_fetched(feed, "ok", None)
        _ = created  # 自动化不在「添加订阅」时跑，避免新增源瞬间触发一堆推送

    if folder_id is not None and db.get(Folder, folder_id) is None:
        raise ValueError("目录不存在")

    subscription = Subscription(
        user_id=user.id,
        feed_id=feed.id,
        folder_id=folder_id,
        custom_title=title if title and feed.title != title else None,
        kind_override=None if kind == "auto" else kind,
        position=_next_position(db, user.id),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def _anyone_wants_articles(db: Session, feed_id: str) -> bool:
    """订阅者里是否有人把这个源当文章看（未覆盖或显式声明为 article）。"""
    overrides = list(
        db.scalars(select(Subscription.kind_override).where(Subscription.feed_id == feed_id))
    )
    if not overrides:
        return True
    return any(item in (None, "article") for item in overrides)


def _next_position(db: Session, user_id: str) -> int:
    last = db.scalar(
        select(Subscription.position)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.position.desc())
        .limit(1)
    )
    return (last or 0) + 1


def mark_fetched(feed: Feed, status: str, error: str | None) -> None:
    feed.last_status = status
    feed.last_error = error
    feed.last_fetched_at = datetime.now(UTC)
