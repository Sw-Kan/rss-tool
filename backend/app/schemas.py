"""请求 / 响应 DTO。前端类型见 frontend/src/types/index.ts，两侧必须同步。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ItemKind = Literal["article", "picture", "video"]
AvatarType = Literal["letter", "image"]
Theme = Literal["light", "dark"]
TextStyle = Literal["small", "comfortable", "large"]
ReadState = Literal["all", "unread", "read"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 认证 / 用户 ----------


class RegisterIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("用户名不能为空")
        return stripped


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: str
    username: str
    email: str
    avatar_type: AvatarType
    avatar_color: str
    avatar_url: str | None = None


class UserPatch(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=60)
    avatar_type: AvatarType | None = None
    avatar_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


# ---------- 目录 / 订阅源 ----------


class FolderOut(BaseModel):
    id: str
    name: str
    position: int
    feed_count: int
    unread_count: int


class FolderCounts(BaseModel):
    feed_count: int
    unread_count: int


class FolderListOut(BaseModel):
    items: list[FolderOut]
    ungrouped: FolderCounts


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("目录名不能为空")
        return stripped


class FeedOut(BaseModel):
    id: str
    url: str
    site_url: str | None
    title: str
    description: str | None
    icon_url: str | None
    folder_id: str | None
    custom_title: str | None
    unread_count: int
    last_status: str
    last_error: str | None
    last_fetched_at: datetime | None


class FeedListOut(BaseModel):
    items: list[FeedOut]


class FeedCreate(BaseModel):
    url: str = Field(min_length=4, max_length=1000)
    folder_id: str | None = None
    title: str | None = Field(default=None, max_length=300)


class FeedPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    folder_id: str | None = None
    clear_folder: bool = False


class RefreshResult(BaseModel):
    feed_id: str
    new_count: int
    status: str
    error: str | None = None


class RefreshBatchOut(BaseModel):
    results: list[RefreshResult]


class OpmlImportOut(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


# ---------- 文章 / 阅读状态 ----------


class ItemOut(BaseModel):
    id: str
    feed_id: str
    feed_title: str
    feed_icon_url: str | None
    title: str
    author: str | None
    url: str | None
    published_at: datetime
    kind: ItemKind
    image_url: str | None
    image_width: int | None
    image_height: int | None
    video_url: str | None
    channel_name: str | None
    is_read: bool
    is_favorite: bool


class ItemDetailOut(ItemOut):
    content_html: str
    summary_html: str | None
    word_count: int


class ItemListOut(BaseModel):
    items: list[ItemOut]
    next_cursor: str | None


class ItemContextOut(BaseModel):
    prev_id: str | None
    next_id: str | None
    index: int
    total: int


class ItemStateIn(BaseModel):
    is_read: bool | None = None
    is_favorite: bool | None = None


class BulkReadIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    is_read: bool = True


class BulkReadOut(BaseModel):
    updated: int


# ---------- 设置 ----------


class SidebarSummaryOut(BaseModel):
    by_kind: dict[str, int]
    favorites: int
    folders: dict[str, int]
    feeds: dict[str, int]
    ungrouped: int
    total_unread: int
    feed_count: int


class SettingsOut(BaseModel):
    theme: Theme
    language: str
    auto_refresh_enabled: bool
    refresh_interval_minutes: int
    text_style: TextStyle


class SettingsPatch(BaseModel):
    theme: Theme | None = None
    auto_refresh_enabled: bool | None = None
    refresh_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    text_style: TextStyle | None = None


class HealthOut(BaseModel):
    status: str = "ok"
    scheduler_running: bool = False
