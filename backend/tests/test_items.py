"""M5 读路径 + M7 阅读状态：过滤组合、分页、批量、上下文。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import Folder, User
from tests.factories import add_article, make_feed, set_state, subscribe


def seed() -> dict[str, str]:
    """造一个覆盖全部过滤维度的数据集。"""
    with SessionLocal() as db:
        user = db.query(User).order_by(User.created_at).first()
        assert user is not None
        tech = Folder(user_id=user.id, name="技术")
        db.add(tech)
        db.commit()

        sspai = make_feed(db, "少数派", url="https://sspai.com/feed")
        infoq = make_feed(db, "InfoQ", url="https://infoq.cn/feed")
        subscribe(db, user, sspai, tech)
        subscribe(db, user, infoq)

        ids = {
            "essay": add_article(db, sspai, guid="e1", kind="article", minutes_ago=1).id,
            "picture": add_article(db, sspai, guid="p1", kind="picture", minutes_ago=2).id,
            "video": add_article(
                db, infoq, guid="v1", kind="video", minutes_ago=3, channel_name="InfoQ 技术频道"
            ).id,
            "other_feed_video": add_article(db, infoq, guid="v2", kind="video", minutes_ago=4).id,
        }
        set_state(db, user, _article(db, ids["video"]), is_favorite=True)
        return ids | {"user": user.id, "tech": tech.id, "sspai": sspai.id, "infoq": infoq.id}


def _article(db, article_id: str):  # noqa: ANN001
    from app.models import Article

    return db.get(Article, article_id)


def ids_of(response) -> list[str]:  # noqa: ANN001
    return [item["id"] for item in response.json()["items"]]


def test_kind_filter(auth_client: TestClient) -> None:
    data = seed()
    # 列表按 published_at 降序：essay(1) picture(2) video(3) other(4)
    assert ids_of(auth_client.get("/api/items?kind=video")) == [
        data["video"],
        data["other_feed_video"],
    ]
    assert ids_of(auth_client.get("/api/items?kind=picture")) == [data["picture"]]
    assert len(ids_of(auth_client.get("/api/items"))) == 4


def test_folder_filter_combines_with_kind(auth_client: TestClient) -> None:
    """目录 ⊕ 图片 = 该目录内图片源；目录外的视频不出现。"""
    data = seed()
    assert ids_of(auth_client.get(f"/api/items?folder_id={data['tech']}&kind=picture")) == [
        data["picture"]
    ]
    assert ids_of(auth_client.get(f"/api/items?folder_id={data['tech']}&kind=video")) == []
    assert ids_of(auth_client.get("/api/items?folder_id=none&kind=video")) == [
        data["video"],
        data["other_feed_video"],
    ]


def test_feed_filter(auth_client: TestClient) -> None:
    data = seed()
    assert ids_of(auth_client.get(f"/api/items?feed_id={data['infoq']}")) == [
        data["video"],
        data["other_feed_video"],
    ]


def test_favorite_filter_combines_with_kind(auth_client: TestClient) -> None:
    """收藏 ⊕ 视频 = 只有收藏的视频。"""
    data = seed()
    assert ids_of(auth_client.get("/api/items?favorite=true")) == [data["video"]]
    assert ids_of(auth_client.get("/api/items?favorite=true&kind=video")) == [data["video"]]
    assert ids_of(auth_client.get("/api/items?favorite=true&kind=picture")) == []


def test_state_filter(auth_client: TestClient) -> None:
    data = seed()
    auth_client.patch(f"/api/items/{data['essay']}/state", json={"is_read": True})

    assert ids_of(auth_client.get("/api/items?state=read")) == [data["essay"]]
    unread = ids_of(auth_client.get("/api/items?state=unread"))
    assert data["essay"] not in unread
    assert len(unread) == 3


def test_keyset_pagination_has_no_gaps_or_duplicates(auth_client: TestClient) -> None:
    with SessionLocal() as db:
        user = db.query(User).first()
        assert user is not None
        feed = make_feed(db)
        subscribe(db, user, feed)
        expected = [add_article(db, feed, guid=f"g{i}", minutes_ago=i).id for i in range(7)]

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        query = f"/api/items?limit=2{'&cursor=' + cursor if cursor else ''}"
        payload = auth_client.get(query).json()
        seen.extend(item["id"] for item in payload["items"])
        cursor = payload["next_cursor"]
        if not cursor:
            break

    assert seen == expected
    assert len(set(seen)) == 7


def test_invalid_cursor_is_rejected(auth_client: TestClient) -> None:
    seed()
    assert auth_client.get("/api/items?cursor=not-a-cursor").status_code == 400


def test_bulk_read_and_unread_count(auth_client: TestClient) -> None:
    data = seed()
    before = auth_client.get("/api/items/summary").json()["total_unread"]
    assert before == 4

    response = auth_client.post(
        "/api/items/read", json={"ids": [data["essay"], data["picture"]], "is_read": True}
    )
    assert response.json() == {"updated": 2}
    assert auth_client.get("/api/items/summary").json()["total_unread"] == 2

    auth_client.post("/api/items/read", json={"ids": [data["essay"]], "is_read": False})
    assert auth_client.get("/api/items/summary").json()["total_unread"] == 3


def test_state_persists_and_returns_updated_item(auth_client: TestClient) -> None:
    data = seed()
    response = auth_client.patch(
        f"/api/items/{data['essay']}/state", json={"is_read": True, "is_favorite": True}
    )
    assert response.json()["is_read"] is True
    assert response.json()["is_favorite"] is True
    assert auth_client.get(f"/api/items/{data['essay']}").json()["is_favorite"] is True


def test_context_reports_neighbours_and_bounds(auth_client: TestClient) -> None:
    data = seed()
    middle = auth_client.get(f"/api/items/{data['picture']}/context").json()
    assert middle["index"] == 1
    assert middle["total"] == 4
    assert middle["prev_id"] == data["essay"]
    assert middle["next_id"] == data["video"]

    first = auth_client.get(f"/api/items/{data['essay']}/context").json()
    assert first["index"] == 0
    assert first["prev_id"] is None

    last = auth_client.get(f"/api/items/{data['other_feed_video']}/context").json()
    assert last["index"] == 3
    assert last["next_id"] is None


def test_context_respects_filters(auth_client: TestClient) -> None:
    data = seed()
    only_video = auth_client.get(f"/api/items/{data['video']}/context?kind=video").json()
    assert only_video["total"] == 2
    assert only_video["index"] == 0


def test_detail_returns_content_and_word_count(auth_client: TestClient) -> None:
    data = seed()
    detail = auth_client.get(f"/api/items/{data['essay']}").json()
    assert detail["content_html"] == "<p>正文</p>"
    assert detail["word_count"] == 10
    assert detail["feed_title"] == "少数派"


def test_foreign_item_is_not_visible(auth_client: TestClient) -> None:
    with SessionLocal() as db:
        feed = make_feed(db, url="https://nobody.example.com/feed")
        orphan = add_article(db, feed, guid="orphan")
    assert auth_client.get(f"/api/items/{orphan.id}").status_code == 404


# ---------- 源级类型覆盖 ----------


def test_source_kind_override_changes_effective_kind(auth_client: TestClient) -> None:
    """把源声明成图片后，它的文章要出现在图片过滤下，且返回的 kind 也是图片。"""
    with SessionLocal() as db:
        user = db.query(User).first()
        assert user is not None
        feed = make_feed(db, "图片源", url="https://pic.example.com/feed")
        subscribe(db, user, feed)
        article = add_article(db, feed, guid="p1", kind="article")
        feed_id = feed.id
        article_id = article.id

    # 默认：按内容分类，出现在文章下
    assert [i["id"] for i in auth_client.get("/api/items?kind=article").json()["items"]] == [
        article_id
    ]
    assert auth_client.get("/api/items?kind=picture").json()["items"] == []

    # 声明成图片源
    patched = auth_client.patch(f"/api/feeds/{feed_id}", json={"kind": "picture"})
    assert patched.status_code == 200
    assert patched.json()["kind_override"] == "picture"

    assert auth_client.get("/api/items?kind=article").json()["items"] == []
    pictures = auth_client.get("/api/items?kind=picture").json()["items"]
    assert [i["id"] for i in pictures] == [article_id]
    assert pictures[0]["kind"] == "picture"


def test_kind_override_affects_detail_and_summary(auth_client: TestClient) -> None:
    with SessionLocal() as db:
        user = db.query(User).first()
        assert user is not None
        feed = make_feed(db, "视频源", url="https://v.example.com/feed")
        subscribe(db, user, feed)
        article = add_article(db, feed, guid="v1", kind="article")
        feed_id = feed.id
        article_id = article.id

    auth_client.patch(f"/api/feeds/{feed_id}", json={"kind": "video"})

    assert auth_client.get(f"/api/items/{article_id}").json()["kind"] == "video"
    by_kind = auth_client.get("/api/items/summary").json()["by_kind"]
    assert by_kind["video"] == 1
    assert by_kind["article"] == 0


def test_kind_override_can_be_reset_to_auto(auth_client: TestClient) -> None:
    with SessionLocal() as db:
        user = db.query(User).first()
        assert user is not None
        feed = make_feed(db, "源", url="https://a.example.com/feed")
        subscribe(db, user, feed)

    auth_client.patch(f"/api/feeds/{feed.id}", json={"kind": "picture"})
    body = auth_client.patch(f"/api/feeds/{feed.id}", json={"kind": "auto"}).json()
    assert body["kind_override"] == "auto"


def test_invalid_kind_is_rejected(auth_client: TestClient) -> None:
    with SessionLocal() as db:
        user = db.query(User).first()
        assert user is not None
        feed = make_feed(db, "源", url="https://b.example.com/feed")
        subscribe(db, user, feed)

    assert auth_client.patch(f"/api/feeds/{feed.id}", json={"kind": "essay"}).status_code == 422
