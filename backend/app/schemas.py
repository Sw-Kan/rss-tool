"""请求 / 响应 DTO。前端类型见 frontend/src/types/index.ts，两侧必须同步。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

ItemKind = Literal["article", "picture", "video"]
KindChoice = Literal["auto", "article", "picture", "video"]
AvatarType = Literal["letter", "image"]
Theme = Literal["light", "dark"]
TextStyle = Literal["small", "comfortable", "large"]
ReadState = Literal["all", "unread", "read"]
Language = Literal["zh-CN", "en"]


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
    kind_override: KindChoice = "auto"
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
    # auto = 按内容判断；其余值覆盖该源全部条目的类型
    kind: KindChoice = "auto"


class FeedPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    folder_id: str | None = None
    clear_folder: bool = False
    kind: KindChoice | None = None


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
    language: Language
    auto_refresh_enabled: bool
    refresh_interval_minutes: int
    text_style: TextStyle
    ai_token_limit: int


class SettingsPatch(BaseModel):
    theme: Theme | None = None
    auto_refresh_enabled: bool | None = None
    refresh_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    text_style: TextStyle | None = None
    # F7：界面语言，同时决定 AI 输出的语言
    language: Language | None = None
    # F1：每月 AI token 上限，0 = 不限
    ai_token_limit: int | None = Field(default=None, ge=0, le=1_000_000_000)


# ---------- AI（F1） ----------

AiProtocol = Literal["openai", "anthropic"]
AiKind = Literal["summary", "title_translation"]


class AiProviderOut(BaseModel):
    """api_key 永不回传，只给掩码提示。"""

    id: str
    label: str
    protocol: AiProtocol
    base_url: str
    model: str
    enabled: bool
    position: int
    has_key: bool
    api_key_hint: str


class AiConfigOut(BaseModel):
    providers: list[AiProviderOut]
    token_limit: int


class AiProviderCreate(BaseModel):
    preset: str = "custom"


class AiProviderPatch(BaseModel):
    label: str | None = Field(default=None, max_length=60)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    # 空字符串表示“不改”，clear_key=true 才显式清空
    api_key: str | None = Field(default=None, max_length=500)
    clear_key: bool = False


class AiUsageOut(BaseModel):
    month_tokens: int
    total_tokens: int
    limit: int
    calls: int
    by_kind: dict[str, int]


class AiArticleIn(BaseModel):
    article_id: str


class AiResultOut(BaseModel):
    kind: AiKind
    content: str
    model: str
    cached: bool
    tokens_in: int
    tokens_out: int
    created_at: datetime


class AiResultsOut(BaseModel):
    """打开文章时一次性回填两种结果，避免两次请求。"""

    summary: AiResultOut | None = None
    title_translation: AiResultOut | None = None


class HealthOut(BaseModel):
    status: str = "ok"
    scheduler_running: bool = False


# ---------- 集成 / 代理 / 自动化（F2 / F3 / F4） ----------

IntegrationKind = Literal["rsshub", "obsidian", "feishu", "custom_export"]
ProxyMode = Literal["system", "custom"]
RuleTrigger = Literal["item_arrived", "video_arrived", "picture_arrived", "schedule"]
RuleJoin = Literal["and", "or"]
RuleField = Literal["title", "word_count", "channel", "feed", "kind", "favorite", "read"]
RuleOp = Literal["contains", "gt", "lt", "eq"]
RuleActionType = Literal[
    "favorite", "mark_read", "mark_unread", "feishu", "obsidian", "custom_export"
]


class RsshubParam(BaseModel):
    """RSSHub 路由参数：按作用范围（路由前缀）把 query 参数拼到展开后的订阅地址上。"""

    name: str = Field(min_length=1, max_length=60)
    scope: str = Field(default="", max_length=200)
    value: str = Field(default="", max_length=1000)
    secret: bool = False


class RsshubConfig(BaseModel):
    base_url: str = Field(default="", max_length=500)
    access_key: str = Field(default="", max_length=500)
    env: str = Field(default="", max_length=2000)
    params: list[RsshubParam] = Field(default_factory=list, max_length=50)


class ObsidianConfig(BaseModel):
    vault_path: str = Field(default="", max_length=1000)


class FeishuConfig(BaseModel):
    webhook_url: str = Field(default="", max_length=1000)


class CustomExportConfig(BaseModel):
    endpoint: str = Field(default="", max_length=1000)
    # JSON 模板，用 {{var}} 占位；留空则用内置默认结构
    schema_template: str = Field(default="", max_length=8000)


class IntegrationOut(BaseModel):
    kind: IntegrationKind
    enabled: bool
    updated_at: datetime | None
    # 按 kind 只填一个，避免前端做类型分支
    rsshub: RsshubConfig | None = None
    obsidian: ObsidianConfig | None = None
    feishu: FeishuConfig | None = None
    custom_export: CustomExportConfig | None = None


class IntegrationListOut(BaseModel):
    items: list[IntegrationOut]


class IntegrationPatch(BaseModel):
    enabled: bool | None = None
    rsshub: RsshubConfig | None = None
    obsidian: ObsidianConfig | None = None
    feishu: FeishuConfig | None = None
    custom_export: CustomExportConfig | None = None


class IntegrationTestOut(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None = None


class ProxyOut(BaseModel):
    mode: ProxyMode
    http_url: str
    https_url: str
    socks5_url: str
    no_proxy: str


class ProxyPatch(BaseModel):
    mode: ProxyMode | None = None
    http_url: str | None = Field(default=None, max_length=500)
    https_url: str | None = Field(default=None, max_length=500)
    socks5_url: str | None = Field(default=None, max_length=500)
    no_proxy: str | None = Field(default=None, max_length=1000)


# 每个字段允许的运算符：避免写出「标题 gt 1」这种永远不命中的规则
# 每个字段允许的运算符：避免写出「标题 gt 1」这种永远不命中的规则
FIELD_OPS: dict[str, tuple[str, ...]] = {
    "title": ("contains", "eq"),
    "channel": ("contains", "eq"),
    "feed": ("contains", "eq"),
    "word_count": ("gt", "lt", "eq"),
    "kind": ("eq",),
    # 阅读状态类条件：值取 true / false
    "favorite": ("eq",),
    "read": ("eq",),
}


class RuleCondition(BaseModel):
    field: RuleField
    op: RuleOp
    value: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _check_combo(self) -> RuleCondition:
        allowed = FIELD_OPS[self.field]
        if self.op not in allowed:
            raise ValueError(f"{self.field} 只支持 {'/'.join(allowed)}")
        return self


class RuleAction(BaseModel):
    type: RuleActionType


class RuleOut(BaseModel):
    id: str
    name: str
    enabled: bool
    position: int
    trigger: RuleTrigger
    schedule_time: str | None
    join: RuleJoin
    conditions: list[RuleCondition]
    action: RuleAction


def _default_condition() -> RuleCondition:
    return RuleCondition(field="title", op="contains", value="")


class RuleCreate(BaseModel):
    name: str = Field(default="新规则", max_length=80)
    trigger: RuleTrigger = "item_arrived"
    schedule_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    join: RuleJoin = "and"
    conditions: list[RuleCondition] = Field(
        default_factory=lambda: [_default_condition()], max_length=10
    )
    action: RuleAction = RuleAction(type="favorite")


class RulePatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    enabled: bool | None = None
    trigger: RuleTrigger | None = None
    schedule_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    join: RuleJoin | None = None
    conditions: list[RuleCondition] | None = Field(default=None, max_length=10)
    action: RuleAction | None = None
