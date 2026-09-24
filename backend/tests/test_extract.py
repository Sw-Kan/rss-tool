"""F5 全文抽取：纯函数 + 抓取链路。全程不打真实网络。"""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.models import Article
from app.services import extract, feed_fetch, feed_parse, refresh
from tests.factories import RSS_20, add_article, make_feed

ARTICLE_URL = "https://blog.example.com/post/1"
LONG_BODY = "".join(f"<p>第 {index} 段正文，用来验证抽取结果足够长。</p>" for index in range(12))
PAGE = f"""<html><head><title>原网页标题</title></head><body>
<nav>站点导航</nav>
<article><h1>原网页标题</h1>{LONG_BODY}
<p>段落里有<a href="https://x.com/link">外链</a>与<img src="https://x.com/a.png" alt="图">。</p>
<ul><li>先把订阅源按目录整理清楚，再考虑阅读顺序与清理策略。</li><li>每周固定时间清理一次，三个月没有更新的源直接退订。</li></ul></article>
<footer>版权信息</footer><script>alert(1)</script></body></html>"""


# ---------- 纯函数 ----------


def test_extract_keeps_structure_and_drops_chrome() -> None:
    result = extract.extract_from_html(PAGE, ARTICLE_URL)
    assert result is not None
    assert "第 0 段正文" in result.html
    assert result.text_length > 200

    for kept in ("<h1", "<a ", "<img", "<li"):
        assert kept in result.html, f"应当保留 {kept}"
    for dropped in ("站点导航", "版权信息", "alert(1)", "<nav", "<footer", "<script", "<style"):
        assert dropped not in result.html, f"应当剔除 {dropped}"


def test_extract_drops_blocks_whose_items_are_too_short() -> None:
    """readability 的 MIN_LEN 启发式：条目文字短于 25 字时整个 <ul> 会被丢掉。

    这是已知限制（见 AGENTS.md §12），钉成用例以免行为静默变化。
    """
    items = "<ul><li>要点一</li><li>要点二</li></ul>"
    page = f"<html><body><article>{LONG_BODY}{items}</article></body></html>"
    result = extract.extract_from_html(page)
    assert result is not None
    assert "要点一" not in result.html


def test_extract_keeps_lists_with_full_sentences() -> None:
    items = (
        "<ul>"
        "<li>先把订阅源按目录整理清楚，再考虑阅读顺序与清理策略。</li>"
        "<li>每周固定时间清理一次，三个月没有更新的源直接退订。</li>"
        "</ul>"
    )
    page = f"<html><body><article>{LONG_BODY}{items}</article></body></html>"
    result = extract.extract_from_html(page)
    assert result is not None
    assert "<ul" in result.html
    assert "<li" in result.html
    assert "每周固定时间清理一次" in result.html


def test_extract_drops_images_without_src() -> None:
    page = f"<html><body><article>{LONG_BODY}<p><img alt='没有地址'></p></article></body></html>"
    result = extract.extract_from_html(page)
    assert result is not None
    assert "<img" not in result.html


@pytest.mark.parametrize("page", ["", "   ", "<html><body>短</body></html>"])
def test_extract_returns_none_for_useless_input(page: str) -> None:
    assert extract.extract_from_html(page) is None


def test_extract_returns_none_when_only_chrome() -> None:
    page = "<html><body><nav>" + "导航" * 300 + "</nav></body></html>"
    result = extract.extract_from_html(page)
    assert result is None or "导航" not in result.html


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/a", True),
        ("http://example.com/a", True),
        ("ftp://example.com/a", False),
        ("javascript:alert(1)", False),
        (None, False),
    ],
)
def test_is_http_url(url: str | None, expected: bool) -> None:
    assert extract.is_http_url(url) is expected


# ---------- needs_extraction ----------


def _article(db: Session, **kwargs: object) -> Article:
    feed = make_feed(db, url=f"https://blog.example.com/{len(kwargs)}.xml")
    article = add_article(db, feed, guid="g1", **kwargs)  # type: ignore[arg-type]
    return article


def test_needs_extraction_true_for_short_feed_article(db: Session) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>很短</p>"
    assert extract.needs_extraction(article, 200) is True


def test_needs_extraction_false_when_content_is_long_enough(db: Session) -> None:
    article = _article(db, kind="article")
    article.content_html = f"<p>{'正文' * 300}</p>"
    assert extract.needs_extraction(article, 200) is False


@pytest.mark.parametrize("kind", ["picture", "video"])
def test_needs_extraction_false_for_media(db: Session, kind: str) -> None:
    article = _article(db, kind=kind)
    article.content_html = "<p>短</p>"
    assert extract.needs_extraction(article, 200) is False


def test_needs_extraction_false_when_already_extracted(db: Session) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>短</p>"
    article.content_source = "extracted"
    assert extract.needs_extraction(article, 200) is False


def test_needs_extraction_false_when_already_attempted(db: Session) -> None:
    from datetime import UTC, datetime

    article = _article(db, kind="article")
    article.content_html = "<p>短</p>"
    article.extracted_at = datetime.now(UTC)
    assert extract.needs_extraction(article, 200) is False


def test_needs_extraction_false_without_original_url(db: Session) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>短</p>"
    article.url = None
    assert extract.needs_extraction(article, 200) is False


# ---------- 抽取链路 ----------


@pytest.fixture
def allow_private(monkeypatch: pytest.MonkeyPatch) -> None:
    """本文件只验证抽取逻辑；SSRF 校验由 test_fetch.py 覆盖。"""
    monkeypatch.setattr(feed_fetch, "check_url_allowed", lambda url: None)


async def _run(db: Session, feed_id: str) -> int:
    return await extract.extract_pending(db, feed_id, limit=10)


@pytest.mark.asyncio
async def test_extraction_replaces_short_feed_content(
    db: Session, allow_private: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>摘要</p>"
    article.url = ARTICLE_URL
    db.commit()
    before = article.word_count

    with respx.mock:
        respx.get(ARTICLE_URL).mock(return_value=httpx.Response(200, content=PAGE.encode()))
        assert await _run(db, article.feed_id) == 1

    db.refresh(article)
    assert article.content_source == "extracted"
    assert article.extract_status == "ok"
    assert article.extracted_at is not None
    assert "第 0 段正文" in (article.content_html or "")
    assert article.word_count > before


@pytest.mark.asyncio
async def test_extraction_keeps_feed_content_when_page_has_no_article(
    db: Session, allow_private: None
) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>摘要</p>"
    article.url = ARTICLE_URL
    db.commit()

    with respx.mock:
        respx.get(ARTICLE_URL).mock(
            return_value=httpx.Response(200, content=b"<html><body><nav>menu</nav></body></html>")
        )
        assert await _run(db, article.feed_id) == 0

    db.refresh(article)
    assert article.content_source == "feed"
    assert article.extract_status == "failed"
    assert article.content_html == "<p>摘要</p>"


@pytest.mark.asyncio
async def test_extraction_marks_failure_on_http_error(db: Session, allow_private: None) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>摘要</p>"
    article.url = ARTICLE_URL
    db.commit()

    with respx.mock:
        respx.get(ARTICLE_URL).mock(return_value=httpx.Response(404))
        assert await _run(db, article.feed_id) == 0

    db.refresh(article)
    assert article.extract_status == "failed"
    assert article.content_html == "<p>摘要</p>"


@pytest.mark.asyncio
async def test_extraction_is_blocked_by_ssrf_guard(db: Session) -> None:
    """不 monkeypatch SSRF 校验：内网地址必须被拦下，且不写入任何正文。"""
    article = _article(db, kind="article")
    article.content_html = "<p>摘要</p>"
    article.url = "http://127.0.0.1:8899/private"
    db.commit()

    assert await _run(db, article.feed_id) == 0

    db.refresh(article)
    assert article.extract_status == "failed"
    assert article.content_html == "<p>摘要</p>"


@pytest.mark.asyncio
async def test_extraction_skips_media_and_long_articles(db: Session, allow_private: None) -> None:
    feed = make_feed(db, url="https://blog.example.com/mixed.xml")
    picture = add_article(db, feed, guid="p", kind="picture")
    picture.content_html = "<p>短</p>"
    long_one = add_article(db, feed, guid="l", kind="article")
    long_one.content_html = f"<p>{'正文' * 300}</p>"
    db.commit()

    with respx.mock:
        assert await _run(db, feed.id) == 0

    db.refresh(picture)
    db.refresh(long_one)
    assert picture.extracted_at is None
    assert long_one.extracted_at is None


@pytest.mark.asyncio
async def test_extraction_can_be_disabled(
    db: Session, allow_private: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>摘要</p>"
    db.commit()
    monkeypatch.setattr(extract.get_settings(), "extract_enabled", False)

    assert await _run(db, article.feed_id) == 0
    db.refresh(article)
    assert article.extracted_at is None


@pytest.mark.asyncio
async def test_one_failure_does_not_block_the_batch(db: Session, allow_private: None) -> None:
    feed = make_feed(db, url="https://blog.example.com/batch.xml")
    good = add_article(db, feed, guid="good")
    bad = add_article(db, feed, guid="bad")
    good.content_html = "<p>短</p>"
    bad.content_html = "<p>短</p>"
    good.url = "https://blog.example.com/good"
    bad.url = "https://blog.example.com/bad"
    db.commit()

    with respx.mock:
        respx.get("https://blog.example.com/good").mock(
            return_value=httpx.Response(200, content=PAGE.encode())
        )
        respx.get("https://blog.example.com/bad").mock(return_value=httpx.Response(500))
        assert await _run(db, feed.id) == 1

    db.refresh(good)
    db.refresh(bad)
    assert good.extract_status == "ok"
    assert bad.extract_status == "failed"


@pytest.mark.asyncio
async def test_failed_extraction_is_not_retried(db: Session, allow_private: None) -> None:
    article = _article(db, kind="article")
    article.content_html = "<p>摘要</p>"
    article.url = ARTICLE_URL
    db.commit()

    with respx.mock:
        route = respx.get(ARTICLE_URL).mock(return_value=httpx.Response(500))
        assert await _run(db, article.feed_id) == 0
        assert await _run(db, article.feed_id) == 0
        assert route.call_count == 1


# ---------- 与刷新管线的配合 ----------


def test_refresh_does_not_clobber_extracted_content(db: Session) -> None:
    """核心不变式：再次刷新不能用 feed 的短摘要覆盖已抽取的全文。"""
    feed = make_feed(db, url="https://sspai.com/feed")
    parsed = feed_parse.parse(RSS_20, base_url=feed.url)
    refresh.store_articles(db, feed, parsed)
    db.commit()

    article = db.query(Article).filter_by(guid="sspai-1").one()
    article.content_html = "<p>抽取出来的长正文</p>"
    article.word_count = 999
    article.content_source = "extracted"
    article.extract_status = "ok"
    db.commit()

    refresh.store_articles(db, feed, parsed)
    db.commit()
    db.refresh(article)

    assert article.content_source == "extracted"
    assert article.content_html == "<p>抽取出来的长正文</p>"
    assert article.word_count == 999


def test_new_articles_start_from_feed_content(db: Session) -> None:
    feed = make_feed(db, url="https://sspai.com/feed")
    refresh.store_articles(db, feed, feed_parse.parse(RSS_20, base_url=feed.url))
    db.commit()

    for article in db.query(Article).all():
        assert article.content_source == "feed"
        assert article.extract_status is None
        assert article.extracted_at is None


@pytest.mark.asyncio
async def test_not_modified_refresh_still_backfills_content(
    db: Session, allow_private: None
) -> None:
    """回归：添加订阅时入库的文章不抽取，若首次刷新返回 304，仍必须补齐正文。"""
    feed = make_feed(db, url="https://blog.example.com/feed.xml")
    article = add_article(db, feed, guid="g1", kind="article")
    article.content_html = "<p>摘要</p>"
    article.url = ARTICLE_URL
    db.commit()

    with respx.mock:
        respx.get(feed.url).mock(return_value=httpx.Response(304))
        respx.get(ARTICLE_URL).mock(return_value=httpx.Response(200, content=PAGE.encode()))
        result = await refresh.refresh_feed(db, feed)

    assert result.status == "not_modified"
    db.refresh(article)
    assert article.content_source == "extracted"
    assert article.extract_status == "ok"


@pytest.mark.asyncio
async def test_failed_refresh_does_not_try_extraction(db: Session, allow_private: None) -> None:
    """抓取都失败了就别再去打原网页。"""
    feed = make_feed(db, url="https://blog.example.com/broken.xml")
    article = add_article(db, feed, guid="g1", kind="article")
    article.content_html = "<p>摘要</p>"
    article.url = ARTICLE_URL
    db.commit()

    with respx.mock:
        respx.get(feed.url).mock(return_value=httpx.Response(500))
        article_route = respx.get(ARTICLE_URL).mock(
            return_value=httpx.Response(200, content=PAGE.encode())
        )
        result = await refresh.refresh_feed(db, feed)

    assert result.status == "error"
    assert article_route.call_count == 0
    db.refresh(article)
    assert article.extracted_at is None
