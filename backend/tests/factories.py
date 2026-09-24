"""示例 feed 与造数工具。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Article, Feed, Folder, Subscription, User, UserItemState

RSS_20 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>少数派</title>
    <link>https://sspai.com</link>
    <description>高效工作，品质生活</description>
    <image><url>https://sspai.com/icon.png</url><title>少数派</title><link>https://sspai.com</link></image>
    <item>
      <title>为什么我又回到了 RSS</title>
      <link>https://sspai.com/post/1</link>
      <guid isPermaLink="false">sspai-1</guid>
      <author>张潇雨</author>
      <pubDate>Mon, 02 Sep 2024 08:00:00 GMT</pubDate>
      <description>摘要在这里</description>
      <content:encoded><![CDATA[<p>正文第一段</p><img src="/img/a.png"><p>正文第二段</p>]]></content:encoded>
    </item>
    <item>
      <title>没有 guid 的条目</title>
      <link>https://sspai.com/post/2</link>
      <pubDate>Tue, 03 Sep 2024 08:00:00 GMT</pubDate>
      <description><![CDATA[<p>只有图片</p><img src="https://sspai.com/img/b.jpg" width="1200" height="800">]]></description>
    </item>
    <item>
      <title>带视频 enclosure 的条目</title>
      <link>https://sspai.com/post/3</link>
      <guid>sspai-3</guid>
      <pubDate>Wed, 04 Sep 2024 08:00:00 GMT</pubDate>
      <enclosure url="https://cdn.sspai.com/v.mp4" type="video/mp4" length="1000"/>
      <media:thumbnail url="https://cdn.sspai.com/thumb.jpg" width="1280" height="720"/>
    </item>
  </channel>
</rss>
""".encode()

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>InfoQ</title>
  <link href="https://www.infoq.cn"/>
  <subtitle>软件开发资讯</subtitle>
  <entry>
    <title>Rust 1.85 发布</title>
    <link href="https://www.infoq.cn/article/1"/>
    <id>tag:infoq.cn,2024:1</id>
    <updated>2024-09-05T10:00:00Z</updated>
    <author><name>InfoQ</name></author>
    <summary>Rust 新版本</summary>
    <content type="html">&lt;p&gt;2024 edition&lt;/p&gt;</content>
  </entry>
</feed>
""".encode()

BROKEN = "<html><body>这不是 feed</body></html>".encode()


def make_user(db: Session, email: str = "writer@example.com") -> User:
    user = User(username="writer", email=email, password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_feed(db: Session, title: str = "测试源", url: str | None = None) -> Feed:
    feed = Feed(url=url or f"https://example.com/{title}.xml", title=title)
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return feed


def subscribe(db: Session, user: User, feed: Feed, folder: Folder | None = None) -> Subscription:
    subscription = Subscription(user_id=user.id, feed_id=feed.id, folder_id=folder and folder.id)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def add_article(
    db: Session,
    feed: Feed,
    *,
    guid: str,
    kind: str = "article",
    title: str = "标题",
    minutes_ago: int = 0,
    image_url: str | None = None,
    channel_name: str | None = None,
) -> Article:
    published = datetime(2024, 9, 10, 12, 0, tzinfo=UTC) - timedelta(minutes=minutes_ago)
    article = Article(
        feed_id=feed.id,
        guid=guid,
        url=f"https://example.com/{guid}",
        title=title,
        kind=kind,
        published_at=published,
        updated_at=published,
        content_html="<p>正文</p>",
        word_count=10,
        image_url=image_url,
        channel_name=channel_name,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def set_state(
    db: Session,
    user: User,
    article: Article,
    *,
    is_read: bool = False,
    is_favorite: bool = False,
) -> UserItemState:
    row = UserItemState(
        user_id=user.id, article_id=article.id, is_read=is_read, is_favorite=is_favorite
    )
    db.add(row)
    db.commit()
    return row
