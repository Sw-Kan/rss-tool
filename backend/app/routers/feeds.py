"""M2 订阅源管理 + M3 刷新入口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession
from ..models import Article, Feed, Folder, Subscription
from ..schemas import (
    FeedCreate,
    FeedListOut,
    FeedOut,
    FeedPatch,
    RefreshBatchOut,
    RefreshResult,
)
from ..services import counts, refresh
from ..services.feed_fetch import FetchError

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


@router.get("", response_model=FeedListOut)
def list_feeds(
    user: CurrentUser,
    db: DbSession,
    folder_id: str | None = Query(default=None),
) -> FeedListOut:
    stmt = (
        select(Subscription, Feed)
        .join(Feed, Feed.id == Subscription.feed_id)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.position)
    )
    if folder_id == "none":
        stmt = stmt.where(Subscription.folder_id.is_(None))
    elif folder_id:
        stmt = stmt.where(Subscription.folder_id == folder_id)

    summary = counts.sidebar_summary(db, user.id)
    return FeedListOut(
        items=[_to_out(sub, feed, summary.feeds.get(feed.id, 0)) for sub, feed in db.execute(stmt)]
    )


@router.post("", response_model=FeedOut, status_code=status.HTTP_201_CREATED)
async def create_feed(payload: FeedCreate, user: CurrentUser, db: DbSession) -> FeedOut:
    url = payload.url.strip()
    existing = db.scalar(
        select(Subscription)
        .join(Feed, Feed.id == Subscription.feed_id)
        .where(Subscription.user_id == user.id, Feed.url == url)
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="已订阅该源")

    try:
        subscription = await refresh.create_subscription(
            db, user, url, folder_id=payload.folder_id, title=payload.title
        )
    except FetchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    feed = db.get(Feed, subscription.feed_id)
    assert feed is not None
    return _to_out(subscription, feed, 0)


@router.patch("/{feed_id}", response_model=FeedOut)
def patch_feed(feed_id: str, payload: FeedPatch, user: CurrentUser, db: DbSession) -> FeedOut:
    subscription = _owned_subscription(db, user.id, feed_id)
    feed = db.get(Feed, subscription.feed_id)
    assert feed is not None

    if payload.title is not None:
        title = payload.title.strip()
        subscription.custom_title = title or None
    if payload.clear_folder:
        subscription.folder_id = None
    elif payload.folder_id is not None:
        if db.get(Folder, payload.folder_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="目录不存在")
        subscription.folder_id = payload.folder_id

    db.commit()
    summary = counts.sidebar_summary(db, user.id)
    return _to_out(subscription, feed, summary.feeds.get(feed.id, 0))


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feed(feed_id: str, user: CurrentUser, db: DbSession) -> None:
    """删订阅。feed 无其它订阅时级联删文章。"""
    subscription = _owned_subscription(db, user.id, feed_id)
    feed_id_value = subscription.feed_id
    db.delete(subscription)
    db.flush()

    remaining = db.scalar(
        select(Subscription).where(Subscription.feed_id == feed_id_value).limit(1)
    )
    if remaining is None:
        db.execute(Article.__table__.delete().where(Article.feed_id == feed_id_value))
        feed = db.get(Feed, feed_id_value)
        if feed is not None:
            db.delete(feed)
    db.commit()


@router.post("/refresh", response_model=RefreshBatchOut)
async def refresh_all(
    user: CurrentUser,
    db: DbSession,
    folder_id: str | None = Query(default=None),
) -> RefreshBatchOut:
    stmt = (
        select(Feed)
        .join(Subscription, Subscription.feed_id == Feed.id)
        .where(Subscription.user_id == user.id)
    )
    if folder_id == "none":
        stmt = stmt.where(Subscription.folder_id.is_(None))
    elif folder_id:
        stmt = stmt.where(Subscription.folder_id == folder_id)
    feeds = list(db.scalars(stmt))
    return RefreshBatchOut(results=await refresh.refresh_feeds(db, feeds))


@router.post("/{feed_id}/refresh", response_model=RefreshResult)
async def refresh_one(feed_id: str, user: CurrentUser, db: DbSession) -> RefreshResult:
    subscription = _owned_subscription(db, user.id, feed_id)
    feed = db.get(Feed, subscription.feed_id)
    assert feed is not None
    return await refresh.refresh_feed(db, feed)


def _owned_subscription(db: Session, user_id: str, feed_id: str) -> Subscription:
    subscription = db.scalar(
        select(Subscription).where(Subscription.user_id == user_id, Subscription.feed_id == feed_id)
    )
    if subscription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="订阅不存在")
    return subscription


def _to_out(subscription: Subscription, feed: Feed, unread: int) -> FeedOut:
    return FeedOut(
        id=feed.id,
        url=feed.url,
        site_url=feed.site_url,
        title=subscription.custom_title or feed.title or feed.url,
        description=feed.description,
        icon_url=feed.icon_url,
        folder_id=subscription.folder_id,
        custom_title=subscription.custom_title,
        unread_count=unread,
        last_status=feed.last_status,
        last_error=feed.last_error,
        last_fetched_at=feed.last_fetched_at,
    )
