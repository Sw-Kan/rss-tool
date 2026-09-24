"""feed 解析：feedparser → ParsedFeed / ParsedEntry。无网络请求。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import struct_time
from urllib.parse import urljoin, urlparse

import feedparser

from .classify import MediaRef, ParsedEntry


@dataclass(slots=True)
class ParsedFeed:
    title: str | None
    site_url: str | None
    description: str | None
    icon_url: str | None
    entries: list[ParsedEntry] = field(default_factory=list)


def parse(content: bytes, *, base_url: str = "", max_entries: int = 100) -> ParsedFeed:
    """解析 feed。bozo 且无 entries 时抛 ValueError（调用方转成 last_error）。"""
    doc = feedparser.parse(content)
    feed = doc.get("feed") or {}
    entries_raw = doc.get("entries") or []
    if not entries_raw:
        if doc.get("bozo"):
            raise ValueError(f"无法解析该地址的内容：{doc.get('bozo_exception') or '格式错误'}")
        raise ValueError("该地址没有返回任何条目")

    site_url = feed.get("link") or None
    entries = [
        _entry(raw, index, base_url=base_url or site_url or "")
        for index, raw in enumerate(entries_raw[:max_entries])
    ]
    return ParsedFeed(
        title=_clean(feed.get("title")) or None,
        site_url=site_url,
        description=_clean(feed.get("subtitle")) or None,
        icon_url=_icon(doc, feed, site_url),
        entries=entries,
    )


def _entry(raw: dict, index: int, *, base_url: str) -> ParsedEntry:
    link = _clean(raw.get("link"))
    title = _clean(raw.get("title")) or "(无标题)"
    published = _dt(raw.get("published_parsed") or raw.get("updated_parsed"))
    if published is None:
        published = datetime.now(UTC)

    content_html = None
    contents = raw.get("content") or []
    if contents:
        content_html = contents[0].get("value")
    summary_html = raw.get("summary") or raw.get("description")

    guid = _clean(raw.get("id")) or link
    if not guid:
        digest = hashlib.sha1(f"{title}{published.isoformat()}".encode()).hexdigest()
        guid = f"sha1:{digest}"

    return ParsedEntry(
        guid=guid[:500],
        url=link,
        title=title[:500],
        author=_clean(raw.get("author")) or _clean(raw.get("dc_creator")),
        summary_html=summary_html,
        content_html=content_html,
        published_at=published,
        updated_at=_dt(raw.get("updated_parsed")) or published,
        enclosures=_enclosures(raw, base_url),
        media_contents=_media(raw.get("media_content"), base_url),
        media_thumbnails=_media(raw.get("media_thumbnail"), base_url),
        channel_name=_clean(raw.get("author")),
    )


def _enclosures(raw: dict, base_url: str) -> list[MediaRef]:
    refs: list[MediaRef] = []
    for item in raw.get("enclosures") or []:
        href = item.get("href") or item.get("url")
        if not href:
            continue
        refs.append(
            MediaRef(
                url=_absolute(href, base_url),
                mime=item.get("type"),
                width=_int(item.get("width")),
                height=_int(item.get("height")),
            )
        )
    for link in raw.get("links") or []:
        if link.get("rel") != "enclosure" or not link.get("href"):
            continue
        refs.append(MediaRef(url=_absolute(link["href"], base_url), mime=link.get("type")))
    return refs


def _media(items: list | None, base_url: str) -> list[MediaRef]:
    refs: list[MediaRef] = []
    for item in items or []:
        url = item.get("url") or item.get("href")
        if not url:
            continue
        refs.append(
            MediaRef(
                url=_absolute(url, base_url),
                mime=item.get("type") or item.get("medium"),
                width=_int(item.get("width")),
                height=_int(item.get("height")),
            )
        )
    return refs


def _icon(doc: dict, feed: dict, site_url: str | None) -> str | None:
    image = feed.get("image") or {}
    if image.get("href"):
        return image["href"]
    for link in doc.get("feed", {}).get("links", []) or []:
        if link.get("rel") == "icon" and link.get("href"):
            return link["href"]
    if site_url:
        parsed = urlparse(site_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
    return None


def _absolute(url: str, base_url: str) -> str:
    if url.startswith(("http://", "https://", "data:")):
        return url
    return urljoin(base_url, url) if base_url else url


def _dt(value: struct_time | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime(*value[:6], tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
