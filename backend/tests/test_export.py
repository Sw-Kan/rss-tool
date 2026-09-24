"""M10 数据导出与 M9 个人资料。"""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.models import User
from tests.factories import add_article, make_feed, set_state, subscribe


def _seed(client: TestClient, db: Session) -> str:
    user = db.query(User).first()
    assert user is not None
    feed = make_feed(db, "少数派", url="https://sspai.com/feed")
    subscribe(db, user, feed)
    article = add_article(db, feed, guid="e1")
    set_state(db, user, article, is_read=True, is_favorite=True)
    return article.id


def test_export_shape_and_no_secrets(auth_client: TestClient, db: Session) -> None:
    article_id = _seed(auth_client, db)
    response = auth_client.get("/api/users/me/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    payload = json.loads(response.content)
    assert payload["schema_version"] == 1
    assert payload["user"]["email"] == "example@example.com"
    assert "password_hash" not in json.dumps(payload)
    assert payload["folders"] == []
    assert payload["subscriptions"][0]["feed_url"] == "https://sspai.com/feed"
    assert payload["settings"]["theme"] == "light"

    states = payload["item_states"]
    assert len(states) == 1
    assert states[0]["article_id"] == article_id
    assert states[0]["is_read"] is True
    assert states[0]["is_favorite"] is True


def test_export_state_count_matches_db(auth_client: TestClient, db: Session) -> None:
    from app.models import UserItemState

    _seed(auth_client, db)
    payload = auth_client.get("/api/users/me/export").json()
    assert len(payload["item_states"]) == db.query(UserItemState).count()


def test_profile_update_does_not_touch_email(auth_client: TestClient) -> None:
    response = auth_client.patch("/api/users/me", json={"username": "newname"})
    assert response.json()["username"] == "newname"
    assert response.json()["email"] == "example@example.com"
    # email 不在可写字段里，传了也被忽略
    auth_client.patch("/api/users/me", json={"username": "again", "email": "hack@x.com"})
    assert auth_client.get("/api/auth/me").json()["email"] == "example@example.com"


def test_avatar_color_validation(auth_client: TestClient) -> None:
    assert auth_client.patch("/api/users/me", json={"avatar_color": "#0EA5E9"}).status_code == 200
    assert auth_client.patch("/api/users/me", json={"avatar_color": "red"}).status_code == 422


def _png(size: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_avatar_upload_stores_file_and_serves_it(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/users/me/avatar", files={"file": ("me.png", _png((900, 300)), "image/png")}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["avatar_type"] == "image"
    assert payload["avatar_url"].startswith("/api/users/avatar/")

    served = auth_client.get(payload["avatar_url"])
    assert served.status_code == 200
    with Image.open(io.BytesIO(served.content)) as image:
        assert image.size == (256, 256)


def test_avatar_rejects_disguised_text_file(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/users/me/avatar", files={"file": ("me.png", b"definitely not an image", "image/png")}
    )
    assert response.status_code == 400


def test_avatar_rejects_oversized_file(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/users/me/avatar",
        files={"file": ("big.png", b"\x89PNG" + b"0" * (3 * 1024 * 1024 + 10), "image/png")},
    )
    assert response.status_code == 413


def test_avatar_delete_returns_letter_avatar(auth_client: TestClient) -> None:
    auth_client.post("/api/users/me/avatar", files={"file": ("me.png", _png(), "image/png")})
    response = auth_client.delete("/api/users/me/avatar")
    assert response.json()["avatar_type"] == "letter"
    assert response.json()["avatar_url"] is None


def test_avatar_cannot_switch_to_image_before_upload(auth_client: TestClient) -> None:
    assert auth_client.patch("/api/users/me", json={"avatar_type": "image"}).status_code == 400
