"""用户全量数据导出（M10）。不含 password_hash。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Article, Feed, Folder, Subscription, User, UserItemState, UserSettings
from .user_view import public_user

SCHEMA_VERSION = 1


def export_user(db: Session, user: User) -> dict[str, Any]:
    settings_row = db.get(UserSettings, user.id)
    folders = db.scalars(
        select(Folder).where(Folder.user_id == user.id).order_by(Folder.position)
    ).all()
    subscriptions = db.execute(
        select(Subscription, Feed)
        .join(Feed, Feed.id == Subscription.feed_id)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.position)
    ).all()
    states = db.execute(
        select(UserItemState, Article)
        .join(Article, Article.id == UserItemState.article_id)
        .where(UserItemState.user_id == user.id)
    ).all()

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "user": public_user(user).model_dump(),
        "settings": (
            {
                "theme": settings_row.theme,
                "language": settings_row.language,
                "auto_refresh_enabled": settings_row.auto_refresh_enabled,
                "refresh_interval_minutes": settings_row.refresh_interval_minutes,
                "text_style": settings_row.text_style,
            }
            if settings_row
            else None
        ),
        "folders": [
            {"id": folder.id, "name": folder.name, "position": folder.position}
            for folder in folders
        ],
        "subscriptions": [
            {
                "feed_url": feed.url,
                "feed_title": feed.title,
                "site_url": feed.site_url,
                "folder": next((f.name for f in folders if f.id == sub.folder_id), None),
                "custom_title": sub.custom_title,
                "position": sub.position,
            }
            for sub, feed in subscriptions
        ],
        "item_states": [
            {
                "article_id": state.article_id,
                "article_title": article.title,
                "article_url": article.url,
                "feed_url": article.feed_id,
                "is_read": state.is_read,
                "is_favorite": state.is_favorite,
                "read_at": state.read_at.isoformat() if state.read_at else None,
            }
            for state, article in states
        ],
    }
