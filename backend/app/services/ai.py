"""F1 AI 助手：供应商调用、结果缓存、token 用量。

协议：两套报文
- `openai`    ：POST {base_url}/chat/completions，Bearer 鉴权（覆盖 OpenAI / DeepSeek /
                Moonshot / OpenRouter / Ollama / 绝大多数自建网关）
- `anthropic` ：POST {base_url}/messages，x-api-key + anthropic-version

api_key 为空时不发鉴权头（本地 Ollama 就是这样）。

不做流式输出；结果落 `ai_results` 作为缓存兼用量账本，同一 (用户, 文章, 类型)
只调一次上游。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AiProvider, AiResult, Article, User
from .classify import html_to_text

logger = logging.getLogger("rss-tool.ai")

SUMMARY = "summary"
TITLE_TRANSLATION = "title_translation"

ANTHROPIC_VERSION = "2023-06-01"
# 送给模型的正文上限（字符），避免一次把整篇长文灌进去
MAX_INPUT_CHARS = 8000
MAX_OUTPUT_TOKENS = 700


@dataclass(frozen=True, slots=True)
class Preset:
    key: str
    label: str
    protocol: str
    base_url: str
    model: str


PRESETS: tuple[Preset, ...] = (
    Preset("openai", "OpenAI", "openai", "https://api.openai.com/v1", "gpt-4o-mini"),
    Preset(
        "anthropic", "Anthropic", "anthropic", "https://api.anthropic.com/v1", "claude-sonnet-4"
    ),
    Preset("deepseek", "DeepSeek", "openai", "https://api.deepseek.com/v1", "deepseek-chat"),
    Preset("moonshot", "Moonshot", "openai", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    Preset(
        "openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"
    ),
    Preset("ollama", "Ollama（本地）", "openai", "http://127.0.0.1:11434/v1", "qwen2.5:14b"),
    Preset("custom", "自定义", "openai", "", ""),
)

PRESETS_BY_KEY = {preset.key: preset for preset in PRESETS}


class AiError(Exception):
    """面向用户的错误，message 中文。"""


class AiConfigError(AiError):
    """配置缺失或无效：用户可自行修正，对应 HTTP 400。"""


class AiLimitError(AiError):
    """本月 token 用量已达上限，对应 HTTP 429。"""


@dataclass(slots=True)
class AiReply:
    content: str
    tokens_in: int
    tokens_out: int


def mask_key(key: str) -> str:
    """`sk-proj-xxxxxxxxabcd` → `sk-••••••••abcd`；空值返回空串。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * 8
    head = key.split("-")[0] + "-" if "-" in key[:12] else key[:3]
    return f"{head}{'•' * 8}{key[-4:]}"


def pick_provider(db: Session, user_id: str) -> AiProvider:
    """取第一条启用的供应商（按 position）。"""
    provider = db.scalar(
        select(AiProvider)
        .where(AiProvider.user_id == user_id, AiProvider.enabled.is_(True))
        .order_by(AiProvider.position, AiProvider.created_at)
        .limit(1)
    )
    if provider is None:
        raise AiConfigError("还没有启用任何 AI 供应商，请到「设置 → AI」添加并开启一个")
    if not provider.base_url:
        raise AiConfigError("供应商缺少接口地址，请到「设置 → AI」补全")
    if not provider.model:
        raise AiConfigError("供应商缺少模型名，请到「设置 → AI」补全")
    return provider


# 摘要/翻译的输出语言跟随界面语言（F7）
_PROMPTS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "translate": (
            "你是翻译助手。把用户给出的标题翻译成简体中文。只输出译文本身，"
            "不要引号、不要解释、不要保留原文。"
        ),
        "summary": (
            "你是 RSS 阅读助手。用简体中文总结用户给出的文章:\n"
            "第一行用一句话概括全文；另起一行后用「• 」列出 3-5 条要点。\n"
            "只输出纯文本（不要 Markdown 语法、不要标题、不要客套话）。"
        ),
        "label_title": "标题",
        "label_body": "正文",
    },
    "en": {
        "translate": (
            "You are a translation assistant. Translate the given headline into English. "
            "Output only the translation: no quotes, no explanation, no original text."
        ),
        "summary": (
            "You are an RSS reading assistant. Summarise the given article in English:\n"
            "first line is a one-sentence gist; then a new line followed by 3-5 bullet "
            "points each starting with '• '.\n"
            "Output plain text only: no Markdown syntax, no headings, no pleasantries."
        ),
        "label_title": "Title",
        "label_body": "Body",
    },
}


def build_messages(kind: str, article: Article, language: str = "zh-CN") -> list[dict[str, str]]:
    prompts = _PROMPTS.get(language, _PROMPTS["zh-CN"])
    assert prompts is not None

    if kind == TITLE_TRANSLATION:
        return [
            {"role": "system", "content": prompts["translate"]},
            {"role": "user", "content": article.title},
        ]

    body = html_to_text(article.content_html or article.summary_html)[:MAX_INPUT_CHARS]
    return [
        {"role": "system", "content": prompts["summary"]},
        {
            "role": "user",
            "content": f"{prompts['label_title']}: {article.title}\n\n"
            f"{prompts['label_body']}:\n{body}",
        },
    ]


def _endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


async def complete(provider: AiProvider, messages: list[dict[str, str]]) -> AiReply:
    """调用上游。任何失败都转成 AiError（中文提示）。"""
    settings = get_settings()
    base = provider.base_url.strip()
    if not base.startswith(("http://", "https://")):
        raise AiConfigError("接口地址必须以 http:// 或 https:// 开头")

    # 注意：base_url 由用户自己在设置里填写（不是 feed 内容），因此不做 SSRF 内网拦截，
    # 否则本地 Ollama / 局域网网关这类主要用法会被误伤。
    if provider.protocol == "anthropic":
        url = _endpoint(base, "messages")
        headers = {"anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        if provider.api_key:
            headers["x-api-key"] = provider.api_key
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        payload: dict[str, object] = {
            "model": provider.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "messages": [m for m in messages if m["role"] != "system"],
        }
    else:
        url = _endpoint(base, "chat/completions")
        headers = {"content-type": "application/json"}
        if provider.api_key:
            headers["authorization"] = f"Bearer {provider.api_key}"
        payload = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "stream": False,
        }

    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_timeout_seconds, trust_env=False
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise AiError("AI 接口超时，请检查网络或接口地址") from exc
    except httpx.HTTPError as exc:
        raise AiError(f"AI 接口请求失败：{exc}") from exc

    if response.status_code >= 400:
        raise AiError(f"AI 接口返回 HTTP {response.status_code}：{_short(response.text)}")

    try:
        data = response.json()
    except ValueError as exc:
        raise AiError("AI 接口返回的不是合法 JSON") from exc

    return _parse_reply(provider.protocol, data)


def _parse_reply(protocol: str, data: object) -> AiReply:
    if not isinstance(data, dict):
        raise AiError("AI 接口返回结构异常")

    if protocol == "anthropic":
        blocks = data.get("content")
        content = ""
        if isinstance(blocks, list):
            content = "".join(
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        usage = data.get("usage") or {}
    else:
        choices = data.get("choices")
        content = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                content = message.get("content") or ""
        usage = data.get("usage") or {}

    content = content.strip()
    if not content:
        raise AiError("AI 接口没有返回内容")

    tokens_in = _as_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    tokens_out = _as_int(usage.get("completion_tokens") or usage.get("output_tokens"))
    return AiReply(content=content, tokens_in=tokens_in, tokens_out=tokens_out)


def _as_int(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _short(text: str, limit: int = 200) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:limit]


def month_tokens(db: Session, user_id: str) -> int:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(
        select(func.coalesce(func.sum(AiResult.tokens_in + AiResult.tokens_out), 0)).where(
            AiResult.user_id == user_id, AiResult.created_at >= start
        )
    )
    return int(total or 0)


def usage_summary(db: Session, user_id: str, limit: int) -> dict[str, object]:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(
            AiResult.kind,
            func.count(),
            func.coalesce(func.sum(AiResult.tokens_in + AiResult.tokens_out), 0),
        )
        .where(AiResult.user_id == user_id, AiResult.created_at >= start)
        .group_by(AiResult.kind)
    ).all()
    total = db.scalar(
        select(func.coalesce(func.sum(AiResult.tokens_in + AiResult.tokens_out), 0)).where(
            AiResult.user_id == user_id
        )
    )
    by_kind = {str(kind): int(tokens) for kind, _calls, tokens in rows}
    return {
        "month_tokens": sum(by_kind.values()),
        "total_tokens": int(total or 0),
        "limit": limit,
        "calls": sum(int(calls) for _kind, calls, _tokens in rows),
        "by_kind": by_kind,
    }


def cached_result(db: Session, user_id: str, article_id: str, kind: str) -> AiResult | None:
    return db.scalar(
        select(AiResult).where(
            AiResult.user_id == user_id,
            AiResult.article_id == article_id,
            AiResult.kind == kind,
        )
    )


async def run(
    db: Session,
    user: User,
    article: Article,
    kind: str,
    token_limit: int,
    language: str = "zh-CN",
) -> tuple[AiResult, bool]:
    """返回 (结果行, 是否命中缓存)。"""
    existing = cached_result(db, user.id, article.id, kind)
    if existing is not None:
        return existing, True

    if token_limit > 0 and month_tokens(db, user.id) >= token_limit:
        raise AiLimitError("本月 AI 用量已达上限，可在「设置 → AI」调整上限")

    provider = pick_provider(db, user.id)
    reply = await complete(provider, build_messages(kind, article, language))

    row = AiResult(
        user_id=user.id,
        article_id=article.id,
        kind=kind,
        model=provider.model,
        content=reply.content,
        tokens_in=reply.tokens_in,
        tokens_out=reply.tokens_out,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "ai: %s %s via %s，tokens %s+%s",
        kind,
        article.id,
        provider.label,
        reply.tokens_in,
        reply.tokens_out,
    )
    return row, False
