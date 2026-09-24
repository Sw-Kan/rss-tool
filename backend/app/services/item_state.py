"""M7 阅读状态的唯一写入口。

从 routers/items.py 抽出来，是因为 F3 自动化也要改收藏/已读——但按 AGENTS.md §4，
`user_item_state` 只有阅读状态模块能写。与其在自动化里复制一份写逻辑（那就是越权），
不如让两个调用方都走这里。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import Article, Subscription, UserItemState


def state_row(db: Session, user_id: str, article_id: str) -> UserItemState:
    """取状态行，没有就建一个（稀疏表：缺行 = 未读未收藏）。"""
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


def set_state(
    db: Session,
    user_id: str,
    article_id: str,
    *,
    is_read: bool | None = None,
    is_favorite: bool | None = None,
) -> UserItemState:
    row = state_row(db, user_id, article_id)
    if is_read is not None:
        row.is_read = is_read
        row.read_at = datetime.now(UTC) if is_read else None
    if is_favorite is not None:
        row.is_favorite = is_favorite
    db.commit()
    db.refresh(row)
    return row


def visible_article_ids(db: Session, user_id: str, article_ids: list[str]) -> list[str]:
    """过滤出该用户订阅范围内、确实存在的文章 id。"""
    if not article_ids:
        return []
    rows = db.scalars(
        select(Article.id)
        .join(Subscription, Subscription.feed_id == Article.feed_id)
        .where(Subscription.user_id == user_id, Article.id.in_(article_ids))
    )
    return list(dict.fromkeys(rows))


def bulk_set_read(db: Session, user_id: str, article_ids: list[str], is_read: bool) -> int:
    ids = visible_article_ids(db, user_id, article_ids)
    if not ids:
        return 0

    existing = {
        row.article_id: row
        for row in db.scalars(
            select(UserItemState).where(
                UserItemState.user_id == user_id, UserItemState.article_id.in_(ids)
            )
        )
    }
    now = datetime.now(UTC)
    for article_id in ids:
        row = existing.get(article_id)
        if row is None:
            db.add(
                UserItemState(
                    user_id=user_id,
                    article_id=article_id,
                    is_read=is_read,
                    read_at=now if is_read else None,
                )
            )
        else:
            row.is_read = is_read
            row.read_at = now if is_read else None

    db.commit()
    return len(ids)


def is_read(db: Session, user_id: str, article_id: str) -> bool:
    return bool(
        db.scalar(
            select(UserItemState.is_read).where(
                and_(
                    UserItemState.user_id == user_id,
                    UserItemState.article_id == article_id,
                )
            )
        )
    )


def is_favorite(db: Session, user_id: str, article_id: str) -> bool:
    return bool(
        db.scalar(
            select(UserItemState.is_favorite).where(
                and_(
                    UserItemState.user_id == user_id,
                    UserItemState.article_id == article_id,
                )
            )
        )
    )
