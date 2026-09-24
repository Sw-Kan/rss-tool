"""M1 认证与账户。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.user_view import SKIP_DISPLAY_EMAIL

CREDENTIALS = {"username": "alice", "email": "Alice@Example.com", "password": "supersecret"}


def test_register_logs_in_and_normalizes_email(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=CREDENTIALS)
    assert response.status_code == 201
    assert response.json()["email"] == "alice@example.com"
    assert response.json()["avatar_type"] == "letter"
    assert client.get("/api/auth/me").status_code == 200


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    client.post("/api/auth/register", json=CREDENTIALS)
    duplicate = dict(CREDENTIALS, email="ALICE@example.com")
    assert client.post("/api/auth/register", json=duplicate).status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=dict(CREDENTIALS, password="short"))
    assert response.status_code == 422


def test_login_rejects_wrong_password(client: TestClient) -> None:
    client.post("/api/auth/register", json=CREDENTIALS)
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": CREDENTIALS["email"], "password": "nope-nope-nope"}
    )
    assert response.status_code == 401


def test_login_succeeds_after_logout(client: TestClient) -> None:
    client.post("/api/auth/register", json=CREDENTIALS)
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": CREDENTIALS["email"], "password": "supersecret"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_skip_is_idempotent_and_uses_default_user(client: TestClient, db: Session) -> None:
    first = client.post("/api/auth/skip")
    second = client.post("/api/auth/skip")

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["username"] == "user"
    assert first.json()["email"] == SKIP_DISPLAY_EMAIL
    assert len(db.query(User).all()) == 1


def test_unauthenticated_requests_are_rejected(client: TestClient) -> None:
    assert client.get("/api/items").status_code == 401
    assert client.get("/api/folders").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_logout_clears_session(client: TestClient) -> None:
    client.post("/api/auth/skip")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_users_are_isolated(client: TestClient) -> None:
    """A 的已读状态对 B 不可见。"""
    from app.db import SessionLocal
    from tests.factories import add_article, make_feed, set_state, subscribe

    client.post("/api/auth/skip")
    with SessionLocal() as db:
        user = db.query(User).first()
        assert user is not None
        feed = make_feed(db)
        subscribe(db, user, feed)
        article = add_article(db, feed, guid="a1")
        set_state(db, user, article, is_read=True, is_favorite=True)

    assert client.get("/api/items").json()["items"][0]["is_read"] is True

    # 换一个干净客户端（无 cookie）注册另一个账号
    other = TestClient(client.app)
    other.post("/api/auth/register", json=dict(CREDENTIALS, email="bob@example.com"))
    assert other.get("/api/items").json()["items"] == []
