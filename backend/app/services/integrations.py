"""F2 集成：RSSHub / Obsidian / 飞书 / 自定义导出。

四种集成的字段几乎不重叠，因此统一存 `integrations.config` JSON，不摊平成宽表。

RSSHub 的用法有两条：
1. `expand_route()`：把用户输入的裸路由（`/sspai/matrix`）拼成完整订阅地址，
   并按「作用范围」补上路由参数与 ACCESS_KEY。
2. `test_rsshub()`：设置页的「测试连接」，返回延迟。
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Article, Integration

logger = logging.getLogger("rss-tool.integrations")

KINDS = ("rsshub", "obsidian", "feishu", "custom_export")

DEFAULT_CONFIGS: dict[str, dict] = {
    "rsshub": {"base_url": "", "access_key": ""},
    "obsidian": {"vault_path": ""},
    "feishu": {"webhook_url": ""},
    "custom_export": {"endpoint": "", "schema_template": ""},
}

# 一次刷新里同一条规则最多推几条，避免一口气给 webhook 打上百个请求
MAX_PUSH_PER_RUN = 5

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class IntegrationError(Exception):
    """面向用户的集成错误，message 中文。"""


# ---------- 读取 / 写入 ----------


def get_row(db: Session, user_id: str, kind: str) -> Integration | None:
    return db.scalar(
        select(Integration).where(Integration.user_id == user_id, Integration.kind == kind)
    )


def get_config(db: Session, user_id: str, kind: str) -> dict:
    """取配置，缺失的键用默认值补齐，调用方不用做 None 判断。

    老版本写过的 `params` / `env` 键可能还在 JSON 里：这里不再认识它们，
    于是既不会回传、也不会参与拼地址（见 tests 里那条 legacy 用例）。
    """
    defaults = dict(DEFAULT_CONFIGS.get(kind, {}))
    row = get_row(db, user_id, kind)
    if row is None:
        return defaults
    return {**defaults, **(row.config or {})}


def is_enabled(db: Session, user_id: str, kind: str) -> bool:
    row = get_row(db, user_id, kind)
    if row is None:
        return False
    if not row.enabled:
        return False
    config = merged_config(row)
    if kind == "rsshub":
        return bool(config.get("base_url"))
    if kind == "obsidian":
        return bool(config.get("vault_path"))
    if kind == "feishu":
        return bool(config.get("webhook_url"))
    if kind == "custom_export":
        return bool(config.get("endpoint"))
    return False


def merged_config(row: Integration) -> dict:
    return {**DEFAULT_CONFIGS.get(row.kind, {}), **(row.config or {})}


def list_rows(db: Session, user_id: str) -> dict[str, Integration]:
    return {
        row.kind: row
        for row in db.scalars(select(Integration).where(Integration.user_id == user_id))
    }


def upsert(
    db: Session, user_id: str, kind: str, *, enabled: bool | None, config: dict | None
) -> Integration:
    if kind not in KINDS:
        raise IntegrationError("未知的集成类型")

    row = get_row(db, user_id, kind)
    if row is None:
        row = Integration(user_id=user_id, kind=kind, config=dict(DEFAULT_CONFIGS[kind]))
        db.add(row)
        db.flush()

    if config is not None:
        row.config = _merge_config(kind, merged_config(row), config)
    if enabled is not None:
        row.enabled = enabled
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row


def _merge_config(kind: str, current: dict, incoming: dict) -> dict:
    """合并新配置。

    密文字段（access_key）在接口上是掩码回传的，前端原样送回时必须保留旧明文，
    否则用户改一次别的字段就把密钥抹掉了。
    """
    merged = {**current}
    for key, value in incoming.items():
        if value is None:
            continue
        merged[key] = value

    if kind != "rsshub":
        return merged

    if incoming.get("access_key"):
        # 前端没改就不回传新值；回传了就以新值为准（可能是掩码，下面按情况判断）
        merged["access_key"] = _keep_secret(current.get("access_key", ""), incoming["access_key"])

    return merged


def _keep_secret(current: str, incoming: str) -> str:
    """回传值里带掩码点 → 视为「没改」，保留原文。

    比"严格等于 mask_secret(current)"宽松：前端只要把接口给的掩码送回来就算没改，
    避免任何形式的掩码被当成真密钥存进库。
    """
    if not incoming:
        return current
    if "•" in incoming:
        return current
    return incoming


def mask_secret(value: str) -> str:
    """`z_c0=abc123def` → `z_c0=••••••••`；`ghp_abcd...4f2a` → `ghp_••••••••4f2a`。"""
    if not value:
        return ""
    if "=" in value:
        head = value.split("=", 1)[0]
        return f"{head}={'•' * 8}"
    if len(value) <= 8:
        return "•" * 8
    separator = next((i for i, ch in enumerate(value[:8]) if ch in "_-"), None)
    head = value[: separator + 1] if separator is not None else value[:3]
    return f"{head}{'•' * 8}{value[-4:]}"


def masked_config(kind: str, config: dict) -> dict:
    """对外输出前抹掉密文。RSSHub 只有 access_key 一项。"""
    if kind != "rsshub":
        return dict(config)
    safe = dict(config)
    safe["access_key"] = mask_secret(config.get("access_key", ""))
    return safe


# ---------- RSSHub ----------


def looks_like_route(value: str) -> bool:
    """裸路由：`/sspai/matrix` 这种以斜杠开头、但不是 `//host` 的写法。"""
    stripped = value.strip()
    return stripped.startswith("/") and not stripped.startswith("//")


def expand_route(config: dict, route: str) -> str:
    base = (config.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise IntegrationError("还没有配置 RSSHub 服务地址，请到「设置 → 集成」填写")
    if not base.startswith(("http://", "https://")):
        raise IntegrationError("RSSHub 服务地址必须以 http:// 或 https:// 开头")

    path = route.strip()
    if not path.startswith("/"):
        path = f"/{path}"

    query: list[tuple[str, str]] = []
    access_key = (config.get("access_key") or "").strip()
    if access_key:
        query.append(("key", access_key))

    suffix = f"?{urlencode(query)}" if query else ""
    return f"{base}{path}{suffix}"


async def test_rsshub(config: dict) -> tuple[bool, str, int | None]:
    """返回 (ok, message, latency_ms)。"""
    base = (config.get("base_url") or "").strip().rstrip("/")
    if not base:
        return False, "请先填写服务地址", None
    if not base.startswith(("http://", "https://")):
        return False, "服务地址必须以 http:// 或 https:// 开头", None

    settings = get_settings()
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=min(settings.fetch_timeout_seconds, 8.0), trust_env=False
        ) as client:
            response = await client.get(f"{base}/")
    except httpx.TimeoutException:
        return False, "连接超时", None
    except httpx.HTTPError as exc:
        return False, f"连接失败：{exc}", None

    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return False, f"服务返回 HTTP {response.status_code}", latency
    return True, "连接正常", latency


# ---------- 推送目标 ----------


def _article_summary(article: Article, feed_title: str) -> dict:
    from .classify import html_to_text

    return {
        "title": article.title,
        "url": article.url,
        "author": article.author,
        "feed": feed_title,
        "channel": article.channel_name,
        "kind": article.kind,
        "published_at": article.published_at.isoformat(),
        "summary": html_to_text(article.content_html or article.summary_html)[:400],
    }


def _feishu_text(article: Article, feed_title: str) -> str:
    lines = [f"【{feed_title}】{article.title}"]
    if article.author:
        lines.append(f"作者：{article.author}")
    if article.url:
        lines.append(article.url)
    return "\n".join(lines)


async def push_feishu(config: dict, article: Article, feed_title: str) -> None:
    webhook = (config.get("webhook_url") or "").strip()
    if not webhook:
        raise IntegrationError("还没有配置飞书 Webhook 地址")
    if not webhook.startswith(("http://", "https://")):
        raise IntegrationError("飞书 Webhook 地址必须以 http:// 或 https:// 开头")

    payload = {"msg_type": "text", "content": {"text": _feishu_text(article, feed_title)}}
    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        response = await client.post(webhook, json=payload)
    if response.status_code >= 400:
        raise IntegrationError(f"飞书返回 HTTP {response.status_code}")


def save_to_obsidian(config: dict, article: Article, feed_title: str) -> Path:
    raw_path = (config.get("vault_path") or "").strip()
    if not raw_path:
        raise IntegrationError("还没有配置 Obsidian 仓库路径")

    vault = Path(raw_path).expanduser()
    if not vault.is_absolute():
        raise IntegrationError("Obsidian 仓库路径必须是绝对路径")

    vault.mkdir(parents=True, exist_ok=True)
    name = _UNSAFE_FILENAME.sub("_", article.title).strip() or "untitled"
    target = (vault / f"{name[:120]}.md").resolve()

    # 标题来自 feed，是可被第三方影响的输入：落盘前确认它没跑出仓库目录
    if not str(target).startswith(str(vault.resolve())):
        raise IntegrationError("文件名不合法")

    from .classify import html_to_text

    body = [
        "---",
        f"title: {article.title}",
        f"feed: {feed_title}",
        f"url: {article.url or ''}",
        f"published: {article.published_at.isoformat()}",
        "---",
        "",
        f"# {article.title}",
        "",
        html_to_text(article.content_html or article.summary_html),
        "",
    ]
    target.write_text("\n".join(body), encoding="utf-8")
    return target


TEMPLATE_FIELDS = (
    "title",
    "url",
    "author",
    "feed",
    "channel",
    "kind",
    "published_at",
    "summary",
    "id",
)

DEFAULT_SCHEMA = """{
  "title": "{{title}}",
  "link": "{{url}}",
  "source": "{{feed}}",
  "author": "{{author}}",
  "published": "{{published_at}}",
  "content": "{{summary}}"
}"""


def template_values(article: Article, feed_title: str) -> dict[str, str]:
    summary = _article_summary(article, feed_title)
    return {key: "" if summary.get(key) is None else str(summary[key]) for key in TEMPLATE_FIELDS}


def render_template(template: str, article: Article, feed_title: str) -> dict:
    """把 {{var}} 占位替换成真实值，再解析成 JSON。

    替换时对值做 JSON 转义，否则文章标题里的引号会直接把模板搞坏。
    """
    raw = (template or "").strip() or DEFAULT_SCHEMA
    values = template_values(article, feed_title)

    rendered = raw
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", json.dumps(value)[1:-1])

    # 剩下没被替换掉的占位符说明变量名写错了；直接报 JSON 错误没人看得懂
    leftovers = sorted(set(re.findall(r"\{\{\s*([a-z_]+)\s*\}\}", rendered)))
    if leftovers:
        raise IntegrationError(
            "Schema 里有不认识的变量："
            + "、".join(leftovers)
            + "；可用："
            + " / ".join(TEMPLATE_FIELDS)
        )

    try:
        payload = json.loads(rendered)
    except ValueError as exc:
        raise IntegrationError(f"Schema 不是合法 JSON：{exc}") from exc
    if not isinstance(payload, (dict, list)):
        raise IntegrationError("Schema 渲染结果必须是 JSON 对象或数组")
    return payload


async def push_custom(config: dict, article: Article, feed_title: str) -> None:
    endpoint = (config.get("endpoint") or "").strip()
    if not endpoint:
        raise IntegrationError("还没有配置自定义推送接口")
    if not endpoint.startswith(("http://", "https://")):
        raise IntegrationError("推送接口必须以 http:// 或 https:// 开头")

    payload = render_template(config.get("schema_template", ""), article, feed_title)
    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        response = await client.post(endpoint, json=payload)
    if response.status_code >= 400:
        raise IntegrationError(f"推送接口返回 HTTP {response.status_code}")


async def test_custom_export(config: dict) -> tuple[bool, str, int | None]:
    """设置页的「测试推送」：真发一条样本数据过去。"""
    endpoint = (config.get("endpoint") or "").strip()
    if not endpoint:
        return False, "请先填写推送接口", None
    if not endpoint.startswith(("http://", "https://")):
        return False, "推送接口必须以 http:// 或 https:// 开头"

    sample = _SampleArticle()
    try:
        payload = render_template(config.get("schema_template", ""), sample, "示例订阅源")
    except IntegrationError as exc:
        return False, str(exc), None

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            response = await client.post(endpoint, json=payload)
    except httpx.TimeoutException:
        return False, "推送超时", None
    except httpx.HTTPError as exc:
        return False, f"推送失败：{exc}", None

    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return False, f"接口返回 HTTP {response.status_code}", latency
    return True, "推送成功", latency


class _SampleArticle:
    """只用于「测试推送」的假文章，避免依赖数据库。"""

    title = "示例文章标题"
    url = "https://example.com/post/1"
    author = "示例作者"
    channel_name = "示例频道"
    kind = "article"
    published_at = None
    content_html = "<p>这是示例正文。</p>"
    summary_html = None

    def __init__(self) -> None:
        from datetime import UTC, datetime

        self.published_at = datetime.now(UTC)


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
