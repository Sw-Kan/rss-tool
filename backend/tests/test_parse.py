"""M3 feed 解析。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Article
from app.services import feed_parse, refresh
from tests.factories import ATOM, BROKEN, RSS_20, make_feed


def test_parses_rss_with_content_encoded_and_enclosure() -> None:
    parsed = feed_parse.parse(RSS_20, base_url="https://sspai.com/feed")

    assert parsed.title == "少数派"
    assert parsed.site_url == "https://sspai.com"
    assert parsed.description == "高效工作，品质生活"
    assert parsed.icon_url == "https://sspai.com/icon.png"
    assert [entry.guid for entry in parsed.entries] == [
        "sspai-1",
        "https://sspai.com/post/2",
        "sspai-3",
    ]

    first = parsed.entries[0]
    assert first.title == "为什么我又回到了 RSS"
    assert first.author == "张潇雨"
    assert "正文第一段" in first.content_html
    assert first.published_at == datetime(2024, 9, 2, 8, 0, tzinfo=UTC)

    third = parsed.entries[2]
    assert third.enclosures[0].url == "https://cdn.sspai.com/v.mp4"
    assert third.media_thumbnails[0].url == "https://cdn.sspai.com/thumb.jpg"


def test_entity_only_html_keeps_text_but_not_escapes() -> None:
    parsed = feed_parse.parse(ATOM)
    assert parsed.title == "InfoQ"
    assert parsed.entries[0].guid == "tag:infoq.cn,2024:1"
    assert parsed.entries[0].content_html == "<p>2024 edition</p>"


def test_broken_document_raises() -> None:
    try:
        feed_parse.parse(BROKEN)
    except ValueError as exc:
        assert "无法解析" in str(exc) or "没有返回任何条目" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("坏文档应当抛 ValueError")


def test_upsert_is_idempotent_and_updates_content(db: Session) -> None:
    feed = make_feed(db, url="https://sspai.com/feed")
    parsed = feed_parse.parse(RSS_20, base_url=feed.url)

    assert refresh.store_articles(db, feed, parsed) == 3
    db.commit()
    assert refresh.store_articles(db, feed, parsed) == 0
    db.commit()
    assert db.query(Article).count() == 3

    parsed.entries[0].title = "改过的标题"
    refresh.store_articles(db, feed, parsed)
    db.commit()
    titles = {article.guid: article.title for article in db.query(Article).all()}
    assert titles["sspai-1"] == "改过的标题"


def test_refresh_does_not_touch_user_state(db: Session) -> None:
    """核心不变式：刷新绝不覆盖已读/收藏。"""
    from app.models import UserItemState
    from tests.factories import make_user, set_state, subscribe

    user = make_user(db)
    feed = make_feed(db, url="https://sspai.com/feed")
    subscribe(db, user, feed)
    parsed = feed_parse.parse(RSS_20, base_url=feed.url)
    refresh.store_articles(db, feed, parsed)
    db.commit()

    article = db.query(Article).filter_by(guid="sspai-1").one()
    set_state(db, user, article, is_read=True, is_favorite=True)

    # 再次抓取（内容略有变化）
    parsed.entries[0].published_at = datetime.now(UTC) - timedelta(hours=1)
    refresh.store_articles(db, feed, parsed)
    db.commit()

    state = db.query(UserItemState).one()
    assert state.is_read is True
    assert state.is_favorite is True


def test_max_entries_is_respected() -> None:
    parsed = feed_parse.parse(RSS_20, max_entries=2)
    assert len(parsed.entries) == 2
