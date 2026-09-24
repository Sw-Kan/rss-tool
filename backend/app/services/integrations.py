"""F2 集成：RSSHub / Obsidian / 飞书 / 自定义导出。

四种集成的字段几乎不重叠，因此统一存 `integrations.config` JSON，不摊平成宽表。

RSSHub 的用法有两条：
1. `expand_route()`：把用户输入的裸路由（`/sspai/matrix`）拼成完整订阅地址，
   并按「作用范围」补上路由参数与 ACCESS_KEY。
2. `test_rsshub()`：设置页的「测试连接」，返回延迟。
"""

from __future__ import annotations

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
    "rsshub": {"base_url": "", "access_key": "", "env": "", "params": []},
    "obsidian": {"vault_path": ""},
    "feishu": {"webhook_url": ""},
    "custom_export": {"endpoint": ""},
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
    """取配置，缺失的键用默认值补齐，调用方不用做 None 判断。"""
    defaults = dict(DEFAULT_CONFIGS.get(kind, {}))
    row = get_row(db, user_id, kind)
    if row is None:
        return defaults
    merged = {**defaults, **(row.config or {})}
    if kind == "rsshub":
        merged["params"] = list(merged.get("params") or [])
    return merged


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

    密文字段（access_key、secret 参数）在接口上是掩码回传的，前端原样送回时
    必须保留旧明文，否则用户改一次别的字段就把密钥抹掉了。
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

    params = incoming.get("params")
    if params is not None:
        old_params = current.get("params") or []
        restored = []
        for index, item in enumerate(params):
            entry = dict(item)
            if entry.get("secret"):
                previous = old_params[index] if index < len(old_params) else {}
                entry["value"] = _keep_secret(previous.get("value", ""), entry.get("value", ""))
            restored.append(entry)
        merged["params"] = restored

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
    """对外输出前抹掉密文。"""
    if kind != "rsshub":
        return dict(config)
    safe = dict(config)
    safe["access_key"] = mask_secret(config.get("access_key", ""))
    safe["params"] = [
        {**item, "value": mask_secret(item.get("value", ""))} if item.get("secret") else dict(item)
        for item in (config.get("params") or [])
    ]
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
    for item in config.get("params") or []:
        name = (item.get("name") or "").strip()
        value = (item.get("value") or "").strip()
        if not name or not value:
            continue
        scope = (item.get("scope") or "").strip()
        if scope and not path.startswith(scope):
            continue
        query.append((name, value))

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


async def push_custom(config: dict, article: Article, feed_title: str) -> None:
    endpoint = (config.get("endpoint") or "").strip()
    if not endpoint:
        raise IntegrationError("还没有配置自定义推送接口")
    if not endpoint.startswith(("http://", "https://")):
        raise IntegrationError("推送接口必须以 http:// 或 https:// 开头")

    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        response = await client.post(endpoint, json=_article_summary(article, feed_title))
    if response.status_code >= 400:
        raise IntegrationError(f"推送接口返回 HTTP {response.status_code}")


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
