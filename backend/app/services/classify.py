"""文章分类与媒体字段提取（确定性规则，无网络请求）。

规则见 docs/architecture.md 与 AGENTS.md：按顺序短路，第一个命中即决定 kind。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape

VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "bilibili.com", "b23.tv")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".m3u8")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")

# 「内容只是图片」的判定阈值：正文文字短于该长度且含 <img> 就归为 picture
PICTURE_TEXT_LIMIT = 80

_TAG_RE = re.compile(r"<[^>]+>")
# 用来数「有文字的段落块」：纯图片帖通常 0-1 块，短摘要正文帖有多块
_BLOCK_RE = re.compile(
    r"<(p|div|section|blockquote|li)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL
)
_IMG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


@dataclass(slots=True)
class MediaRef:
    url: str
    mime: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class ParsedEntry:
    guid: str
    url: str | None
    title: str
    author: str | None = None
    channel_name: str | None = None
    summary_html: str | None = None
    content_html: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    enclosures: list[MediaRef] = field(default_factory=list)
    media_contents: list[MediaRef] = field(default_factory=list)
    media_thumbnails: list[MediaRef] = field(default_factory=list)


@dataclass(slots=True)
class Classification:
    kind: str
    image_url: str | None
    image_width: int | None
    image_height: int | None
    video_url: str | None
    word_count: int


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    return unescape(_TAG_RE.sub(" ", html)).strip()


def count_words(*html_parts: str | None) -> int:
    """中文按字符计，其余按词计。用于阅读进度。"""
    text = " ".join(part for part in (html_to_text(p) for p in html_parts) if part)
    cjk = len(_CJK_RE.findall(text))
    non_cjk = len(_WORD_RE.findall(_CJK_RE.sub(" ", text)))
    return cjk + non_cjk


def text_block_count(html: str | None) -> int:
    """数一数有多少个「装着文字」的块级元素。"""
    if not html:
        return 0
    return sum(1 for _tag, inner in _BLOCK_RE.findall(html) if html_to_text(inner))


def first_image_in_html(*html_parts: str | None) -> str | None:
    for part in html_parts:
        if not part:
            continue
        match = _IMG_RE.search(part)
        if match:
            return match.group(1)
    return None


def _is_video_ref(ref: MediaRef) -> bool:
    if ref.mime and ref.mime.lower().startswith("video/"):
        return True
    return ref.url.lower().split("?")[0].endswith(VIDEO_EXT)


def _is_video_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    if lowered.split("?")[0].endswith(VIDEO_EXT):
        return True
    return any(host in lowered for host in VIDEO_HOSTS)


def _is_image_ref(ref: MediaRef) -> bool:
    if ref.mime and ref.mime.lower().startswith("image/"):
        return True
    return ref.url.lower().split("?")[0].endswith(IMAGE_EXT)


def _pick_image(entry: ParsedEntry) -> MediaRef | None:
    for group in (entry.media_thumbnails, entry.enclosures, entry.media_contents):
        for ref in group:
            if _is_image_ref(ref):
                return ref
    url = first_image_in_html(entry.content_html, entry.summary_html)
    return MediaRef(url=url) if url else None


def classify(entry: ParsedEntry) -> Classification:
    word_count = count_words(entry.content_html or entry.summary_html)
    image = _pick_image(entry)

    # ① 视频
    for ref in [*entry.enclosures, *entry.media_contents]:
        if _is_video_ref(ref):
            return Classification(
                "video", image.url if image else None, *(_dims(image)), ref.url, word_count
            )
    if _is_video_url(entry.url):
        return Classification(
            "video", image.url if image else None, *(_dims(image)), entry.url, word_count
        )

    # ② 图片
    for ref in [*entry.enclosures, *entry.media_contents]:
        if _is_image_ref(ref):
            return Classification("picture", ref.url, *_dims(ref), None, word_count)
    # 「内容只是图片」才归为 picture。文字短但仍有多段结构时不能算图片 ——
    # 那多半是「feed 只给短摘要 + 配图」的文章，判成图片就会永远跳过全文抽取（F5）。
    body = entry.content_html or entry.summary_html
    text = html_to_text(body)
    if image and len(text) < PICTURE_TEXT_LIMIT and text_block_count(body) <= 1:
        return Classification("picture", image.url, *_dims(image), None, word_count)

    # ③ 文章
    return Classification("article", image.url if image else None, *_dims(image), None, word_count)


def _dims(ref: MediaRef | None) -> tuple[int | None, int | None]:
    if ref is None:
        return None, None
    return ref.width, ref.height
