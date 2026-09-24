"""M5 阅读器（读路径）与 M7 阅读状态。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession
from ..models import Article, Feed, Subscription, UserItemState
from ..schemas import (
    BulkReadIn,
    BulkReadOut,
    ItemContextOut,
    ItemDetailOut,
    ItemKind,
    ItemListOut,
    ItemOut,
    ItemStateIn,
    SidebarSummaryOut,
)
from ..services import counts, items_query
from ..services.items_query import ItemFilter

router = APIRouter(prefix="/api/items", tags=["items"])

DEFAULT_LIMIT = 30
MAX_LIMIT = 100


@router.get("/summary", response_model=SidebarSummaryOut)
def summary(user: CurrentUser, db: DbSession) -> SidebarSummaryOut:
    """侧边栏全部计数一次拿齐，避免前端发 N 个请求。"""
    data = counts.sidebar_summary(db, user.id)
    return SidebarSummaryOut(
        by_kind=data.by_kind,
        favorites=data.favorites,
        folders=data.folders,
        feeds=data.feeds,
        ungrouped=data.ungrouped,
        total_unread=data.total_unread,
        feed_count=data.feed_count,
    )


@router.get("", response_model=ItemListOut)
def list_items(
    user: CurrentUser,
    db: DbSession,
    kind: str | None = Query(default=None, pattern="^(article|picture|video)$"),
    folder_id: str | None = None,
    feed_id: str | None = None,
    favorite: bool = False,
    state: str = Query(default="all", pattern="^(all|unread|read)$"),
    cursor: str | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> ItemListOut:
    flt = ItemFilter(
        kind=kind, folder_id=folder_id, feed_id=feed_id, favorite=favorite, state=state
    )
    stmt = items_query.build_item_query(user.id, flt)

    if cursor:
        decoded = items_query.decode_cursor(cursor)
        if decoded is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="无效的分页游标")
        stmt = items_query.apply_cursor(stmt, *decoded)

    rows = db.execute(items_query.order_items(stmt).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last_article = rows[-1][0]
        next_cursor = items_query.encode_cursor(
            last_article.published_at.isoformat(), last_article.id
        )

    return ItemListOut(items=[_to_out(*row) for row in rows], next_cursor=next_cursor)


@router.get("/{item_id}", response_model=ItemDetailOut)
def get_item(item_id: str, user: CurrentUser, db: DbSession) -> ItemDetailOut:
    article, feed, custom_title, is_read, is_favorite = _fetch_visible(db, user.id, item_id)
    base = _to_out(article, feed, custom_title, is_read, is_favorite).model_dump()
    return ItemDetailOut(
        **base,
        content_html=article.content_html or article.summary_html or "",
        summary_html=article.summary_html,
        word_count=article.word_count,
    )


@router.get("/{item_id}/context", response_model=ItemContextOut)
def item_context(
    item_id: str,
    user: CurrentUser,
    db: DbSession,
    kind: str | None = Query(default=None, pattern="^(article|picture|video)$"),
    folder_id: str | None = None,
    feed_id: str | None = None,
    favorite: bool = False,
    state: str = Query(default="all", pattern="^(all|unread|read)$"),
) -> ItemContextOut:
    """返回同过滤条件下的上一篇 / 下一篇与位置，供阅读器上/下篇跳转。"""
    article, _feed, _title, _read, _fav = _fetch_visible(db, user.id, item_id)
    flt = ItemFilter(
        kind=kind, folder_id=folder_id, feed_id=feed_id, favorite=favorite, state=state
    )
    total = items_query.count_items(db, user.id, flt)
    before = (
        items_query.build_item_query(user.id, flt).where(items_query.newer_than(article)).subquery()
    )
    index = db.scalar(select(func.count()).select_from(before)) or 0

    prev_row = db.execute(
        items_query.build_item_query(user.id, flt)
        .where(items_query.newer_than(article))
        .order_by(Article.published_at.asc(), Article.id.asc())
        .limit(1)
    ).first()
    next_row = db.execute(
        items_query.order_items(
            items_query.build_item_query(user.id, flt).where(items_query.older_than(article))
        ).limit(1)
    ).first()

    return ItemContextOut(
        prev_id=prev_row[0].id if prev_row else None,
        next_id=next_row[0].id if next_row else None,
        index=index,
        total=total,
    )


@router.patch("/{item_id}/state", response_model=ItemOut)
def set_state(item_id: str, payload: ItemStateIn, user: CurrentUser, db: DbSession) -> ItemOut:
    article, feed, custom_title, is_read, is_favorite = _fetch_visible(db, user.id, item_id)
    row = _state_row(db, user.id, article.id)

    if payload.is_read is not None:
        row.is_read = payload.is_read
        row.read_at = datetime.now(UTC) if payload.is_read else None
        is_read = payload.is_read
    if payload.is_favorite is not None:
        row.is_favorite = payload.is_favorite
        is_favorite = payload.is_favorite

    db.commit()
    return _to_out(article, feed, custom_title, bool(is_read), bool(is_favorite))


@router.post("/read", response_model=BulkReadOut)
def bulk_read(payload: BulkReadIn, user: CurrentUser, db: DbSession) -> BulkReadOut:
    visible = list(
        db.scalars(
            select(Article.id)
            .join(Subscription, Subscription.feed_id == Article.feed_id)
            .where(Subscription.user_id == user.id, Article.id.in_(payload.ids))
        )
    )
    existing = {
        row.article_id: row
        for row in db.scalars(
            select(UserItemState).where(
                UserItemState.user_id == user.id, UserItemState.article_id.in_(visible)
            )
        )
    }
    now = datetime.now(UTC)
    updated = 0
    for article_id in visible:
        row = existing.get(article_id)
        if row is None:
            db.add(
                UserItemState(
                    user_id=user.id,
                    article_id=article_id,
                    is_read=payload.is_read,
                    read_at=now if payload.is_read else None,
                )
            )
        else:
            row.is_read = payload.is_read
            row.read_at = now if payload.is_read else None
        updated += 1

    db.commit()
    return BulkReadOut(updated=updated)


# ---------- 内部工具 ----------


def _fetch_visible(
    db: Session, user_id: str, item_id: str
) -> tuple[Article, Feed, str | None, bool, bool]:
    row = db.execute(
        select(
            Article,
            Feed,
            Subscription.custom_title,
            UserItemState.is_read,
            UserItemState.is_favorite,
        )
        .join(Feed, Feed.id == Article.feed_id)
        .join(
            Subscription,
            and_(Subscription.feed_id == Article.feed_id, Subscription.user_id == user_id),
        )
        .outerjoin(
            UserItemState,
            and_(UserItemState.article_id == Article.id, UserItemState.user_id == user_id),
        )
        .where(Article.id == item_id)
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文章不存在")
    return row[0], row[1], row[2], bool(row[3]), bool(row[4])


def _state_row(db: Session, user_id: str, article_id: str) -> UserItemState:
    row = db.scalar(
        select(UserItemState).where(
            UserItemState.user_id == user_id, UserItemState.article_id == article_id
        )
    )
    if row is None:
        row = UserItemState(user_id=user_id, article_id=article_id)
        db.add(row)
        db.flush()
    return row


def _to_out(
    article: Article,
    feed: Feed,
    custom_title: str | None,
    is_read: bool | None,
    is_favorite: bool | None,
) -> ItemOut:
    return ItemOut(
        id=article.id,
        feed_id=feed.id,
        feed_title=custom_title or feed.title or feed.url,
        feed_icon_url=feed.icon_url,
        title=article.title,
        author=article.author,
        url=article.url,
        published_at=article.published_at,
        kind=cast(ItemKind, article.kind),
        image_url=article.image_url,
        image_width=article.image_width,
        image_height=article.image_height,
        video_url=article.video_url,
        channel_name=article.channel_name,
        is_read=bool(is_read),
        is_favorite=bool(is_favorite),
    )
