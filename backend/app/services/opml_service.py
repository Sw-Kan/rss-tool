"""OPML 导入 / 导出。

安全：解析前拒绝含 DOCTYPE / ENTITY 的文档，避免实体展开类攻击（无需引入 defusedxml）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Feed, Folder, Subscription, User
from . import refresh

OPML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'


class OpmlError(Exception):
    """OPML 解析失败，message 面向用户。"""


@dataclass(slots=True)
class OpmlFeed:
    title: str | None
    xml_url: str
    folders: list[str] = field(default_factory=list)


def _check_safe(raw: bytes) -> None:
    head = raw[:2048].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise OpmlError("OPML 中不允许 DOCTYPE 或 ENTITY 声明")


def parse_opml(raw: bytes) -> list[OpmlFeed]:
    _check_safe(raw)
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise OpmlError(f"OPML 格式错误：{exc}") from exc

    body = root.find("body")
    if body is None:
        raise OpmlError("OPML 缺少 <body>")

    found: list[OpmlFeed] = []

    def walk(node: ElementTree.Element, path: list[str]) -> None:
        for outline in node.findall("outline"):
            xml_url = outline.get("xmlUrl")
            label = (outline.get("title") or outline.get("text") or "").strip()
            if xml_url:
                found.append(
                    OpmlFeed(title=label or None, xml_url=xml_url.strip(), folders=list(path))
                )
            else:
                walk(outline, [*path, label] if label else path)

    walk(body, [])
    return found


def export_opml(db: Session, user: User) -> str:
    rows = db.execute(
        select(Subscription, Feed, Folder)
        .join(Feed, Feed.id == Subscription.feed_id)
        .outerjoin(Folder, Folder.id == Subscription.folder_id)
        .where(Subscription.user_id == user.id)
        .order_by(Folder.position, Folder.name, Subscription.position)
    ).all()

    lines = [
        OPML_HEADER,
        '<opml version="2.0">\n',
        "  <head>\n",
        "    <title>rss-tool 订阅源</title>\n",
        "  </head>\n",
        "  <body>\n",
    ]

    grouped: dict[str | None, list[tuple[Subscription, Feed]]] = {}
    order: list[str | None] = []
    for subscription, feed, folder in rows:
        key = folder.name if folder else None
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append((subscription, feed))

    for key in order:
        title = key or "未分组"
        lines.append(f'    <outline text="{_escape(title)}" title="{_escape(title)}">\n')
        for subscription, feed in grouped[key]:
            label = subscription.custom_title or feed.title or feed.url
            lines.append(
                f'      <outline type="rss" text="{_escape(label)}" '
                f'title="{_escape(label)}" xmlUrl="{_escape(feed.url)}"'
                + (f' htmlUrl="{_escape(feed.site_url)}"' if feed.site_url else "")
                + " />\n"
            )
        lines.append("    </outline>\n")

    lines.append("  </body>\n</opml>\n")
    return "".join(lines)


async def import_opml(db: Session, user: User, raw: bytes) -> tuple[int, int, list[str]]:
    """返回 (imported, skipped, errors)。已存在的源计入 skipped 并归入目标目录。"""
    entries = parse_opml(raw)
    if not entries:
        raise OpmlError("没有找到任何订阅源")

    folder_cache: dict[str, Folder] = {
        folder.name: folder
        for folder in db.scalars(select(Folder).where(Folder.user_id == user.id))
    }
    existing_feeds = {feed.url: feed for feed in db.scalars(select(Feed))}
    subscribed = {
        sub.feed_id
        for sub in db.scalars(select(Subscription).where(Subscription.user_id == user.id))
    }

    imported = 0
    skipped = 0
    errors: list[str] = []

    for item in entries:
        folder_name = item.folders[-1] if item.folders else None
        folder_id: str | None = None
        if folder_name:
            folder = folder_cache.get(folder_name)
            if folder is None:
                folder = Folder(
                    user_id=user.id, name=folder_name[:80], position=len(folder_cache) + 1
                )
                db.add(folder)
                db.flush()
                folder_cache[folder_name] = folder
            folder_id = folder.id

        feed = existing_feeds.get(item.xml_url)
        if feed is None:
            try:
                loaded = await refresh.load_remote(item.xml_url)
            except Exception as exc:  # 单个源失败不影响其它条目
                errors.append(f"{item.xml_url}：{exc}")
                continue
            feed = Feed(
                url=item.xml_url,
                site_url=loaded.parsed.site_url,
                title=item.title or loaded.parsed.title or item.xml_url,
                description=loaded.parsed.description,
                icon_url=loaded.parsed.icon_url,
                etag=loaded.etag,
                modified=loaded.modified,
            )
            db.add(feed)
            db.flush()
            refresh.store_articles(db, feed, loaded.parsed)
            refresh.mark_fetched(feed, "ok", None)
            existing_feeds[feed.url] = feed

        if feed.id in subscribed:
            skipped += 1
            continue

        db.add(
            Subscription(
                user_id=user.id,
                feed_id=feed.id,
                folder_id=folder_id,
                position=refresh._next_position(db, user.id),
            )
        )
        subscribed.add(feed.id)
        imported += 1

    db.commit()
    return imported, skipped, errors


def _escape(value: str | None) -> str:
    if not value:
        return ""
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
