"""全文抽取（F5）：feed 自带正文过短时，去原网页抽正文。

设计要点：
- **复用 `feed_fetch.fetch`** 抓页面，因此 SSRF 校验、重定向复检、超时、体积上限
  全部与订阅抓取同源，不另起一套 HTTP。
- 只用纯函数 `extract_from_html` 做抽取，网络与解析分离，便于单测。
- 抽取是锦上添花：任何失败都保留 feed 自带内容，绝不写入空正文。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from lxml import html as lxml_html
from readability import Document
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Article
from . import feed_fetch
from .classify import count_words, html_to_text
from .feed_fetch import FetchError

logger = logging.getLogger("rss-tool.extract")

# 抽取结果里必须剔除的容器标签（导航/页脚/脚本等）
_DROP_TAGS = (
    "nav",
    "aside",
    "footer",
    "header",
    "form",
    "script",
    "style",
    "iframe",
    "noscript",
    "svg",
    "button",
)

ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


@dataclass(slots=True)
class Extraction:
    html: str
    text: str

    @property
    def text_length(self) -> int:
        return len(self.text)


def extract_from_html(page_html: str, url: str = "") -> Extraction | None:
    """从整页 HTML 抽正文片段。无法抽取时返回 None。"""
    if not page_html or len(page_html) < 200:
        return None

    try:
        summary = Document(page_html, url=url).summary(html_partial=True)
    except Exception:  # readability 对畸形 HTML 会抛各种异常
        return None
    if not summary:
        return None

    try:
        fragment = lxml_html.fragment_fromstring(summary, create_parent="div")
    except Exception:
        return None

    for tag in _DROP_TAGS:
        for node in fragment.iter(tag):
            node.drop_tree()
    # 去掉纯装饰元素
    for node in list(fragment.iter("img")):
        if not (node.get("src") or node.get("data-src")):
            node.drop_tree()

    inner = "".join(
        lxml_html.tostring(child, encoding="unicode", method="html") for child in fragment
    ).strip()
    if not inner:
        return None

    text = html_to_text(inner)
    if not text:
        return None
    return Extraction(html=inner, text=text)


def is_http_url(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


def needs_extraction(article: Article, min_chars: int) -> bool:
    """只有「文章类、正文来自 feed、正文过短、未尝试过、有原文链接」才值得抓。"""
    if article.kind != "article":
        return False
    if article.content_source != "feed":
        return False
    if article.extracted_at is not None:
        return False
    if not is_http_url(article.url):
        return False
    return len(html_to_text(article.content_html or article.summary_html)) < min_chars


async def _extract_one(db: Session, article: Article, min_chars: int) -> str:
    """返回最终写入的 extract_status。"""
    settings = get_settings()
    try:
        page = await feed_fetch.fetch(
            article.url or "",
            accept=ACCEPT_HTML,
            max_bytes=settings.extract_max_bytes,
            timeout=settings.extract_timeout_seconds,
        )
    except FetchError as exc:
        logger.info("extract: %s 抓取失败：%s", article.url, exc)
        return "failed"

    if page.not_modified or not page.content:
        return "failed"

    text = page.content.decode("utf-8", errors="replace")
    result = await asyncio.to_thread(extract_from_html, text, article.url or "")
    if result is None or result.text_length < min_chars:
        return "failed"

    article.content_html = result.html
    article.word_count = count_words(result.html)
    article.content_source = "extracted"
    return "ok"


async def extract_pending(db: Session, feed_id: str, *, limit: int | None = None) -> int:
    """为该源补齐正文过短的文章。返回成功抽取的篇数。

    绝不影响刷新结果：任何异常都只记录日志。
    """
    settings = get_settings()
    if not settings.extract_enabled:
        return 0

    batch = limit if limit is not None else settings.extract_max_per_refresh
    candidates = [
        article
        for article in db.scalars(
            select(Article)
            .where(Article.feed_id == feed_id)
            .order_by(Article.published_at.desc())
            .limit(200)
        )
        if needs_extraction(article, settings.extract_min_chars)
    ][:batch]

    if not candidates:
        return 0

    semaphore = asyncio.Semaphore(settings.extract_concurrency)
    now = datetime.now(UTC)

    async def one(article: Article) -> str:
        async with semaphore:
            try:
                return await _extract_one(db, article, settings.extract_min_chars)
            except Exception:  # 单篇失败不影响同批
                logger.exception("extract: %s 抽取异常", article.url)
                return "failed"

    # ponytail: 失败（含超时）也写 extracted_at，之后不再重试这一篇。
    # 否则每轮刷新都会去撞同一个坏页面。要强制重试就删掉该源的库记录重建。
    statuses = await asyncio.gather(*(one(article) for article in candidates))
    for article, status in zip(candidates, statuses, strict=True):
        article.extract_status = status
        article.extracted_at = now

    db.commit()
    ok = sum(1 for status in statuses if status == "ok")
    logger.info("extract: feed %s 尝试 %s 篇，成功 %s 篇", feed_id, len(candidates), ok)
    return ok
