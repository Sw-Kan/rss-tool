"""F1 AI 助手：供应商调用、结果缓存、token 用量。

协议：两套报文
- `openai`    ：POST {base_url}/chat/completions，Bearer 鉴权（覆盖 OpenAI / DeepSeek /
                Moonshot / OpenRouter / Ollama / 绝大多数自建网关）
- `anthropic` ：POST {base_url}/messages，x-api-key + anthropic-version

一律用 `stream: true`，原因有三：

- 界面能真正「边生成边显示」，上游慢时用户看得见字在长出来（routers/ai.py 转成 SSE）；
- httpx 的超时在流式下是**分块读超时**，所以「慢但一直在吐字」不会再被判超时；
- 账号池网关（one-api / new-api 那一类）排队到吐 429 时，流式下可以尽早发现。

失败策略：按 position 依次尝试所有启用的供应商，每家用尽 `ATTEMPTS_PER_PROVIDER`
次尝试（中间退避 `AI_RETRY_BACKOFF_SECONDS`）。**只有本次请求还没吐出任何字符时**
才会重试/切换 —— 已经流出去的字收不回来，接上另一家的输出会拼出两段内容。

`ai_results` 是缓存兼用量账本：只有成功拿到完整内容才写。失败不写库（也不写半成品），
所以用户修好配置后可以直接重试。

api_key 为空时不发鉴权头（本地 Ollama 就是这样）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
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
# 每家供应商的尝试次数：1 次 + 1 次退避重试
ATTEMPTS_PER_PROVIDER = 2


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


class AiRetryableError(AiError):
    """上游限流 / 临时故障：值得退避重试或换下一家供应商。"""


@dataclass(slots=True)
class StreamState:
    """一次上游尝试累计出来的东西。usage 是累计值，可能分多帧给（anthropic 就是）。"""

    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(slots=True)
class StreamEvent:
    """转给前端的事件：meta（开始一次尝试）/ delta（文本增量）/ done（已入库）。"""

    type: str
    text: str = ""
    provider: str = ""
    model: str = ""
    attempt: int = 0
    result: AiResult | None = None


def mask_key(key: str) -> str:
    """`sk-proj-xxxxxxxxabcd` → `sk-••••••••abcd`；空值返回空串。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * 8
    head = key.split("-")[0] + "-" if "-" in key[:12] else key[:3]
    return f"{head}{'•' * 8}{key[-4:]}"


def enabled_providers(db: Session, user_id: str) -> list[AiProvider]:
    """按 position 取全部启用的供应商 —— 前面失败就往后切。"""
    return list(
        db.scalars(
            select(AiProvider)
            .where(AiProvider.user_id == user_id, AiProvider.enabled.is_(True))
            .order_by(AiProvider.position, AiProvider.created_at)
        )
    )


def _validate(provider: AiProvider) -> None:
    """配置类问题：不重试也不切下一家，切了也一样是配置错。"""
    base = provider.base_url.strip()
    if not base:
        raise AiConfigError("供应商缺少接口地址，请到「设置 → AI」补全")
    if not base.startswith(("http://", "https://")):
        raise AiConfigError("接口地址必须以 http:// 或 https:// 开头")
    if not provider.model:
        raise AiConfigError("供应商缺少模型名，请到「设置 → AI」补全")


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


def _request_spec(
    provider: AiProvider, messages: list[dict[str, str]]
) -> tuple[str, dict[str, str], dict[str, object]]:
    """两套报文（都带 stream）。注意 AI 的 base_url 是用户自己填的配置，不做 SSRF 拦截。"""
    base = provider.base_url.strip()

    if provider.protocol == "anthropic":
        headers = {"anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        if provider.api_key:
            headers["x-api-key"] = provider.api_key
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        payload: dict[str, object] = {
            "model": provider.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "stream": True,
            "messages": [m for m in messages if m["role"] != "system"],
        }
        return _endpoint(base, "messages"), headers, payload

    headers = {"content-type": "application/json"}
    if provider.api_key:
        headers["authorization"] = f"Bearer {provider.api_key}"
    return (
        _endpoint(base, "chat/completions"),
        headers,
        {
            "model": provider.model,
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "stream": True,
            # 不带这个的话 OpenAI 官方流式响应里没有 usage，用量账本会全变 0
            "stream_options": {"include_usage": True},
        },
    )


def _upstream_error(status: int, body: str) -> AiError:
    """4xx 里只有 429 值得重试；5xx 是上游自己出问题，也值得。"""
    message = f"AI 接口返回 HTTP {status}：{_short(body)}"
    if status == 429:
        return AiRetryableError(f"AI 接口限流（429）：{_short(body)}")
    if status >= 500:
        return AiRetryableError(message)
    return AiError(message)


def parse_stream_event(protocol: str, payload: dict) -> tuple[str, int, int]:
    """从一条上游 SSE 的 data JSON 里取（文本增量, tokens_in, tokens_out）。

    未知事件、心跳、只有 usage 的收尾帧都返回空文本与 0。
    """
    if protocol == "anthropic":
        text = ""
        if payload.get("type") == "content_block_delta":
            delta = payload.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("text"), str):
                text = delta["text"]
        # message_start 把 usage 放在 message 里，message_delta 放在顶层
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            message = payload.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            return (text, 0, 0)
        return (text, _as_int(usage.get("input_tokens")), _as_int(usage.get("output_tokens")))

    text = ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        delta = choices[0].get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("content"), str):
            text = delta["content"]
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return (text, 0, 0)
    return (text, _as_int(usage.get("prompt_tokens")), _as_int(usage.get("completion_tokens")))


def _data_frame(line: str) -> dict | None:
    """一行 SSE → data 的 JSON。事件名、注释、`[DONE]`、坏 JSON 都返回 None。"""
    if not line.startswith("data:"):
        return None
    raw = line[len("data:") :].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


async def stream_completion(
    provider: AiProvider, messages: list[dict[str, str]], state: StreamState
) -> AsyncIterator[str]:
    """向上游发起流式请求，逐块 yield 文本增量，同时把 usage 记进 state。"""
    settings = get_settings()
    url, headers, payload = _request_spec(provider, messages)

    try:
        async with (
            httpx.AsyncClient(timeout=settings.ai_timeout_seconds, trust_env=False) as client,
            client.stream("POST", url, headers=headers, json=payload) as response,
        ):
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                raise _upstream_error(response.status_code, body)
            async for line in response.aiter_lines():
                frame = _data_frame(line)
                if frame is None:
                    continue
                text, tokens_in, tokens_out = parse_stream_event(provider.protocol, frame)
                # usage 是累计值，取最大；上游没给就保持 0（见 AGENTS.md §12）
                state.tokens_in = max(state.tokens_in, tokens_in)
                state.tokens_out = max(state.tokens_out, tokens_out)
                if text:
                    state.text += text
                    yield text
    except httpx.TimeoutException as exc:
        raise AiRetryableError("AI 接口超时，请检查网络或接口地址") from exc
    except httpx.HTTPError as exc:
        raise AiRetryableError(f"AI 接口请求失败：{exc}") from exc


def prepare(
    db: Session, user_id: str, article_id: str, kind: str, token_limit: int
) -> tuple[AiResult | None, list[AiProvider]]:
    """生成前的预检：命中缓存直接给结果，否则给出要依次尝试的供应商。

    这些都在响应开始前判定，所以调用方还能用普通 HTTP 状态码表达失败
    （routers/ai.py：400 配置 / 429 上限），不必都塞进 SSE。
    """
    existing = cached_result(db, user_id, article_id, kind)
    if existing is not None:
        return existing, []
    if token_limit > 0 and month_tokens(db, user_id) >= token_limit:
        raise AiLimitError("本月 AI 用量已达上限，可在「设置 → AI」调整上限")
    providers = enabled_providers(db, user_id)
    if not providers:
        raise AiConfigError("还没有启用任何 AI 供应商，请到「设置 → AI」添加并开启一个")
    return None, providers


async def generate(
    db: Session,
    user: User,
    article: Article,
    kind: str,
    providers: list[AiProvider],
    language: str = "zh-CN",
) -> AsyncIterator[StreamEvent]:
    """依次尝试供应商并产出事件；成功时写 `ai_results` 并以 done 收尾。"""
    backoff = get_settings().ai_retry_backoff_seconds
    messages = build_messages(kind, article, language)
    failures: list[str] = []
    streamed = False
    last: AiError | None = None

    for provider in providers:
        _validate(provider)
        for attempt in range(1, ATTEMPTS_PER_PROVIDER + 1):
            state = StreamState()
            yield StreamEvent(
                "meta", provider=provider.label, model=provider.model, attempt=attempt
            )
            try:
                async for text in stream_completion(provider, messages, state):
                    streamed = True
                    yield StreamEvent("delta", text=text)
            except AiRetryableError as exc:
                last = exc
                failures.append(f"{provider.label}: {exc}")
                if streamed:
                    # 已经吐出去的字收不回来，换一家接上会拼出两段内容
                    raise AiError(f"{exc}（已生成的内容未保存）") from exc
                if attempt < ATTEMPTS_PER_PROVIDER and backoff > 0:
                    await asyncio.sleep(backoff)
                continue

            if not state.text.strip():
                # 上游 200 但一句话都没给：换下一家，但同一家不再重试
                last = AiError("AI 接口没有返回内容")
                failures.append(f"{provider.label}: {last}")
                break

            result = _save(db, user, article, kind, provider, state)
            yield StreamEvent("done", provider=provider.label, model=provider.model, result=result)
            return

    raise _all_failed(last, failures, providers)


def _all_failed(last: AiError | None, failures: list[str], providers: list[AiProvider]) -> AiError:
    labels = "、".join(provider.label for provider in providers)
    detail = str(last) if last is not None else "；".join(failures) or "没有可用的供应商"
    message = f"AI 接口不可用：已尝试 {len(providers)} 个供应商（{labels}），最后一次：{detail}"
    return AiError(message)


def _save(
    db: Session,
    user: User,
    article: Article,
    kind: str,
    provider: AiProvider,
    state: StreamState,
) -> AiResult:
    row = AiResult(
        user_id=user.id,
        article_id=article.id,
        kind=kind,
        model=provider.model,
        content=state.text.strip(),
        tokens_in=state.tokens_in,
        tokens_out=state.tokens_out,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "ai: %s %s via %s，tokens %s+%s",
        kind,
        article.id,
        provider.label,
        state.tokens_in,
        state.tokens_out,
    )
    return row


def sse_frame(event: str, payload: dict[str, object]) -> str:
    """一条 SSE 帧。`data` 里的换行由 JSON 转义，所以帧永远是单行。"""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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
