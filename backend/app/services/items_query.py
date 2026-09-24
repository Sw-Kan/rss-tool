"""层级过滤与 keyset 分页共用的查询构造。

过滤语义（AND 组合）见 docs/api.md：
    kind（一级类型） + folder_id（二级目录） + feed_id（三级单源） + favorite + state
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import Article, Feed, Subscription, UserItemState


@dataclass(slots=True)
class ItemFilter:
    kind: str | None = None
    folder_id: str | None = None
    feed_id: str | None = None
    favorite: bool = False
    state: str = "all"


def visible_articles_subquery(user_id: str) -> Select:
    """当前用户可见的文章集合：文章所属 feed 被该用户订阅。"""
    return (
        select(Article.id)
        .join(Subscription, Subscription.feed_id == Article.feed_id)
        .where(Subscription.user_id == user_id)
    )


def build_item_query(user_id: str, flt: ItemFilter) -> Select:
    """返回 Article + Feed + 订阅自定义标题 + 用户状态的联合查询（未分页）。

    返回的列顺序：(Article, Feed, custom_title, is_read, is_favorite)。
    """
    state = UserItemState
    stmt = (
        select(Article, Feed, Subscription.custom_title, state.is_read, state.is_favorite)
        .join(Feed, Feed.id == Article.feed_id)
        .join(
            Subscription,
            and_(Subscription.feed_id == Article.feed_id, Subscription.user_id == user_id),
        )
        .outerjoin(
            state,
            and_(state.article_id == Article.id, state.user_id == user_id),
        )
        .distinct()
    )

    if flt.kind:
        stmt = stmt.where(Article.kind == flt.kind)
    if flt.feed_id:
        stmt = stmt.where(Article.feed_id == flt.feed_id)
    if flt.folder_id:
        if flt.folder_id == "none":
            stmt = stmt.where(Subscription.folder_id.is_(None))
        else:
            stmt = stmt.where(Subscription.folder_id == flt.folder_id)
    if flt.favorite:
        stmt = stmt.where(state.is_favorite.is_(True))
    if flt.state == "unread":
        stmt = stmt.where(or_(state.is_read.is_(None), state.is_read.is_(False)))
    elif flt.state == "read":
        stmt = stmt.where(state.is_read.is_(True))

    return stmt


def order_items(stmt: Select) -> Select:
    return stmt.order_by(Article.published_at.desc(), Article.id.desc())


def newer_than(article: Article) -> object:
    """排序键中严格早于该文章的谓词，用于计算列表内位置。"""
    return or_(
        Article.published_at > article.published_at,
        and_(Article.published_at == article.published_at, Article.id > article.id),
    )


def older_than(article: Article) -> object:
    return or_(
        Article.published_at < article.published_at,
        and_(Article.published_at == article.published_at, Article.id < article.id),
    )


def count_items(db: Session, user_id: str, flt: ItemFilter) -> int:
    inner = build_item_query(user_id, flt).subquery()
    return db.execute(select(func.count()).select_from(inner)).scalar_one()


def encode_cursor(published_at_iso: str, article_id: str) -> str:
    raw = json.dumps([published_at_iso, article_id], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        published_at, article_id = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, ValueError, TypeError):
        return None
    if not isinstance(published_at, str) or not isinstance(article_id, str):
        return None
    return published_at, article_id


def apply_cursor(stmt: Select, published_at: str, article_id: str) -> Select:
    """keyset：严格小于游标，按 (published_at, id) 降序时不重不漏。"""
    from datetime import datetime

    try:
        ts = datetime.fromisoformat(published_at)
    except ValueError:
        return stmt
    return stmt.where(
        or_(
            Article.published_at < ts,
            and_(Article.published_at == ts, Article.id < article_id),
        )
    )
