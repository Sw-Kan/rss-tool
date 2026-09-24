"""M3 媒体分类（确定性规则）。"""

from __future__ import annotations

import pytest

from app.services.classify import MediaRef, ParsedEntry, classify, count_words


def entry(**kwargs: object) -> ParsedEntry:
    base: dict[str, object] = {"guid": "g", "url": "https://example.com/post", "title": "标题"}
    base.update(kwargs)
    return ParsedEntry(**base)  # type: ignore[arg-type]


def test_video_enclosure_wins() -> None:
    result = classify(
        entry(
            enclosures=[MediaRef("https://cdn.example.com/v.mp4", mime="video/mp4")],
            media_thumbnails=[MediaRef("https://cdn.example.com/t.jpg", width=1280, height=720)],
        )
    )
    assert result.kind == "video"
    assert result.video_url == "https://cdn.example.com/v.mp4"
    assert (result.image_width, result.image_height) == (1280, 720)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "https://www.bilibili.com/video/BV1",
        "https://example.com/clip.webm",
    ],
)
def test_video_by_url(url: str) -> None:
    assert classify(entry(url=url)).kind == "video"


def test_image_enclosure_is_picture() -> None:
    result = classify(entry(enclosures=[MediaRef("https://x.com/a.png", mime="image/png")]))
    assert result.kind == "picture"
    assert result.image_url == "https://x.com/a.png"


def test_short_text_with_image_is_picture() -> None:
    result = classify(entry(content_html='<p>两个字的说明</p><img src="https://x.com/a.jpg">'))
    assert result.kind == "picture"
    assert result.image_url == "https://x.com/a.jpg"


def test_long_text_with_image_stays_article() -> None:
    body = "这是一段足够长的正文内容，" * 12
    result = classify(entry(content_html=f'<p>{body}</p><img src="https://x.com/a.jpg">'))
    assert result.kind == "article"
    assert result.image_url == "https://x.com/a.jpg"


def test_no_enclosure_no_image_is_article() -> None:
    result = classify(entry(content_html="<p>纯文字</p>"))
    assert result.kind == "article"
    assert result.image_url is None
    assert result.video_url is None


def test_media_content_thumbnail_used_as_image() -> None:
    result = classify(
        entry(
            content_html="<p>长正文</p>" * 20,
            media_thumbnails=[MediaRef("https://x.com/thumb.webp", width=600, height=400)],
        )
    )
    assert result.image_url == "https://x.com/thumb.webp"
    assert (result.image_width, result.image_height) == (600, 400)


def test_word_count_mixes_cjk_and_latin() -> None:
    assert count_words("<p>中文四个字</p>") == 5
    assert count_words("<p>hello world</p>") == 2
    assert count_words("<p>中文 hello 世界 world</p>") == 6


def test_short_summary_with_several_paragraphs_stays_article() -> None:
    """「短摘要 + 配图 + 多段正文」不能判成图片。

    这是 F5 的前置条件：只有 article 才会去原网页抽全文。判成图片的话这篇
    就永远停在短摘要上，用户看不到正文。
    """
    result = classify(
        entry(content_html=('<p>正文第一段</p><img src="https://x.com/a.png"><p>正文第二段</p>'))
    )
    assert result.kind == "article"
    assert result.image_url == "https://x.com/a.png"


def test_image_only_post_with_caption_stays_picture() -> None:
    assert classify(entry(content_html='<img src="https://x.com/a.png">')).kind == "picture"
    assert (
        classify(entry(content_html='<p>今天天气不错</p><img src="https://x.com/a.png">')).kind
        == "picture"
    )


def test_text_block_count() -> None:
    assert count_words("<p>一</p><p>二</p>") == 2
    from app.services.classify import text_block_count

    assert text_block_count("<p>一</p><p>二</p>") == 2
    assert text_block_count("<p></p><p>二</p>") == 1
    assert text_block_count('<img src="x">') == 0
    assert text_block_count(None) == 0
