"""表结构。字段语义见 docs/data-model.md。

写权限：见 AGENTS.md §4 —— 每个模块只能写自己拥有的表。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """SQLite 不保留时区。统一以 naive UTC 存储、读出时补上 UTC，

    否则序列化出来是不带时区的字符串，前端会当成本地时间。
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


DateTimeUTC = UTCDateTime()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    avatar_type: Mapped[str] = mapped_column(String(10), default="letter")
    avatar_color: Mapped[str] = mapped_column(String(9), default="#4F46E5")
    avatar_path: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_folder_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)


class Feed(Base):
    """全局共享：同一 URL 全库只抓一次。"""

    __tablename__ = "feeds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    site_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    modified: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTimeUTC, nullable=True)
    last_status: Mapped[str] = mapped_column(String(20), default="ok")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)

    articles: Mapped[list[Article]] = relationship(
        back_populates="feed", cascade="all, delete-orphan", passive_deletes=True
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "feed_id", name="uq_sub_user_feed"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    feed_id: Mapped[str] = mapped_column(ForeignKey("feeds.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    custom_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)

    feed: Mapped[Feed] = relationship()


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("feed_id", "guid", name="uq_article_feed_guid"),
        Index("ix_article_feed_published", "feed_id", "published_at", "id"),
        Index("ix_article_kind", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    feed_id: Mapped[str] = mapped_column(ForeignKey("feeds.id", ondelete="CASCADE"), index=True)
    guid: Mapped[str] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)
    kind: Mapped[str] = mapped_column(String(10), default="article")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    # F5 全文抽取：正文来源与尝试结果（只有抓取管线写这几列）
    content_source: Mapped[str] = mapped_column(String(10), default="feed")
    extract_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTimeUTC, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)

    feed: Mapped[Feed] = relationship(back_populates="articles")


class UserItemState(Base):
    """稀疏表：无行 = 未读未收藏。唯一写入者是阅读状态模块。"""

    __tablename__ = "user_item_state"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_state_user_article"),
        Index("ix_state_user_read", "user_id", "is_read"),
        Index("ix_state_user_fav", "user_id", "is_favorite"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[str] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTimeUTC, nullable=True)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(String(10), default="light")
    language: Mapped[str] = mapped_column(String(10), default="zh-CN")
    auto_refresh_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    refresh_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    text_style: Mapped[str] = mapped_column(String(20), default="comfortable")
    # F1：每月 token 上限，0 表示不限
    ai_token_limit: Mapped[int] = mapped_column(Integer, default=0)


class AiProvider(Base):
    """F1：AI 供应商配置。可多条，按 position 取第一条启用的使用。

    `protocol` 由预设决定，不在 UI 里暴露（OpenAI 兼容 / Anthropic 两套报文）。
    """

    __tablename__ = "ai_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60), default="自定义")
    protocol: Mapped[str] = mapped_column(String(20), default="openai")
    base_url: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)


class AiResult(Base):
    """F1：AI 结果缓存兼用量账本。同一 (用户, 文章, 类型) 只调一次上游。"""

    __tablename__ = "ai_results"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", "kind", name="uq_ai_user_article_kind"),
        Index("ix_ai_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[str] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTimeUTC, default=utcnow)
