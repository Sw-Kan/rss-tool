"""M8 设置与偏好 + 调度器联动。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import scheduler


def test_settings_defaults(auth_client: TestClient) -> None:
    assert auth_client.get("/api/settings").json() == {
        "theme": "light",
        "language": "zh-CN",
        "auto_refresh_enabled": True,
        "refresh_interval_minutes": 60,
        "text_style": "comfortable",
        "ai_token_limit": 0,
    }


def test_settings_roundtrip(auth_client: TestClient) -> None:
    patched = auth_client.patch(
        "/api/settings",
        json={"theme": "dark", "text_style": "large", "refresh_interval_minutes": 30},
    )
    assert patched.status_code == 200
    assert patched.json()["theme"] == "dark"
    assert auth_client.get("/api/settings").json() == patched.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"theme": "blue"},
        {"refresh_interval_minutes": 1},
        {"refresh_interval_minutes": 5000},
        {"text_style": "huge"},
    ],
)
def test_settings_reject_invalid_values(auth_client: TestClient, payload: dict) -> None:
    assert auth_client.patch("/api/settings", json=payload).status_code == 422


def test_language_can_be_switched(auth_client: TestClient) -> None:
    assert auth_client.patch("/api/settings", json={"language": "en"}).json()["language"] == "en"
    assert auth_client.get("/api/settings").json()["language"] == "en"


def test_unsupported_language_is_rejected(auth_client: TestClient) -> None:
    assert auth_client.patch("/api/settings", json={"language": "en-US"}).status_code == 422
    assert auth_client.patch("/api/settings", json={"language": "fr"}).status_code == 422


@pytest.mark.asyncio
async def test_interval_change_is_applied_to_scheduler(auth_client: TestClient) -> None:
    """改间隔后调度器里的 job 触发器真的换了。"""
    scheduler.start()
    try:
        user_id = auth_client.get("/api/auth/me").json()["id"]
        job = scheduler._scheduler.get_job(f"refresh:{user_id}")
        assert job is not None
        assert job.trigger.interval.total_seconds() == 3600

        auth_client.patch("/api/settings", json={"refresh_interval_minutes": 15})
        job = scheduler._scheduler.get_job(f"refresh:{user_id}")
        assert job is not None
        assert job.trigger.interval.total_seconds() == 900

        auth_client.patch("/api/settings", json={"auto_refresh_enabled": False})
        assert scheduler._scheduler.get_job(f"refresh:{user_id}") is None
    finally:
        scheduler.shutdown()


def test_health_reports_scheduler_state(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["scheduler_running"] is False  # 测试里没走 lifespan
