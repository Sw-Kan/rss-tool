"""侧边栏与列表头部所需的聚合计数（全部按『未读』口径，与设计稿一致）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from ..models import Article, Feed, Subscription, UserItemState


@dataclass(slots=True)
class SidebarSummary:
    by_kind: dict[str, int] = field(default_factory=dict)
    favorites: int = 0
    folders: dict[str, int] = field(default_factory=dict)
    feeds: dict[str, int] = field(default_factory=dict)
    ungrouped: int = 0
    total_unread: int = 0
    feed_count: int = 0


def _base(user_id: str) -> Select:
    state = UserItemState
    return (
        select(Article.kind, Article.feed_id, Subscription.folder_id)
        .join(
            Subscription,
            and_(Subscription.feed_id == Article.feed_id, Subscription.user_id == user_id),
        )
        .outerjoin(state, and_(state.article_id == Article.id, state.user_id == user_id))
    )


def sidebar_summary(db: Session, user_id: str) -> SidebarSummary:
    summary = SidebarSummary(by_kind={"all": 0, "article": 0, "picture": 0, "video": 0})

    unread = _base(user_id).where(
        (UserItemState.is_read.is_(None)) | (UserItemState.is_read.is_(False))
    )

    grouped = db.execute(
        unread.with_only_columns(
            Article.kind, Article.feed_id, Subscription.folder_id, func.count().label("n")
        ).group_by(Article.kind, Article.feed_id, Subscription.folder_id)
    ).all()

    for kind, feed_id, folder_id, count in grouped:
        summary.by_kind[kind] = summary.by_kind.get(kind, 0) + count
        summary.by_kind["all"] += count
        summary.feeds[feed_id] = count
        if folder_id:
            summary.folders[folder_id] = summary.folders.get(folder_id, 0) + count
        else:
            summary.ungrouped += count

    summary.favorites = (
        db.scalar(
            select(func.count())
            .select_from(Article)
            .join(
                Subscription,
                and_(Subscription.feed_id == Article.feed_id, Subscription.user_id == user_id),
            )
            .join(
                UserItemState,
                and_(UserItemState.article_id == Article.id, UserItemState.user_id == user_id),
            )
            .where(UserItemState.is_favorite.is_(True))
        )
        or 0
    )

    summary.feed_count = (
        db.scalar(
            select(func.count())
            .select_from(Subscription)
            .join(Feed, Feed.id == Subscription.feed_id)
            .where(Subscription.user_id == user_id)
        )
        or 0
    )
    summary.total_unread = summary.by_kind["all"]
    return summary
