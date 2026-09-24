"""F6 媒体缓存：类型白名单、失败回退、LRU 淘汰、SSRF 边界。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import MediaCache
from app.services import feed_fetch, media

IMG = "https://cdn.example.com/a.png"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200


REAL_CHECK = feed_fetch.check_url_allowed


@pytest.fixture(autouse=True)
def allow_fake_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认放行假域名（本文件多数用例关心的是缓存逻辑）。SSRF 用例会自己装回真校验。"""
    monkeypatch.setattr(feed_fetch, "check_url_allowed", lambda url: [])


def _endpoint(url: str = IMG) -> str:
    return f"/api/media?url={url}"


# ---------- 纯函数 ----------


def test_key_is_stable_sha256() -> None:
    assert media.key_for(IMG) == media.key_for(IMG)
    assert len(media.key_for(IMG)) == 64
    assert media.key_for(IMG) != media.key_for(IMG + "x")


def test_path_is_sharded() -> None:
    key = media.key_for(IMG)
    path = media.path_for(key)
    assert path.name == key
    assert path.parent.name == key[2:4]
    assert path.parent.parent.name == key[:2]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.com/a.png", True),
        ("http://x.com/a.png", True),
        ("data:image/png;base64,AAAA", False),
        ("file:///etc/passwd", False),
        ("javascript:alert(1)", False),
        ("", False),
    ],
)
def test_is_cacheable_url(url: str, expected: bool) -> None:
    assert media.is_cacheable_url(url) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (b"GIF89a" + b"0" * 20, "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 8, "image/webp"),
        (b"BM" + b"0" * 20, "image/bmp"),
        # SVG / HTML / 空内容一律识别不出来
        (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", None),
        (b"<html><body>hi</body></html>", None),
        (b"", None),
    ],
)
def test_sniff_content_type(raw: bytes, expected: str | None) -> None:
    assert media.sniff_content_type(raw) == expected


def test_svg_is_not_in_the_whitelist() -> None:
    """SVG 能带脚本，同源返回等于 XSS，必须排除。"""
    assert "image/svg+xml" not in media.ALLOWED_TYPES
    assert ".svg" not in media.ALLOWED_TYPES.values()


# ---------- 取图与命中 ----------


def test_referer_is_sent_to_defeat_hotlink_protection(auth_client: TestClient) -> None:
    """大量 CDN 靠 Referer 白名单防盗链；不带就是 403，这条必须钉住。"""
    with respx.mock:
        route = respx.get(IMG).mock(return_value=httpx.Response(200, content=PNG))
        auth_client.get(_endpoint(), follow_redirects=False)

    assert route.calls[0].request.headers["referer"] == "https://cdn.example.com/"


def test_referer_for_uses_image_origin() -> None:
    assert media.referer_for("https://cdn.a.com/x/y.png?z=1") == "https://cdn.a.com/"
    assert media.referer_for("http://a.com:8080/x.png") == "http://a.com:8080/"


def test_cold_request_fetches_and_serves(auth_client: TestClient, tmp_path) -> None:  # noqa: ANN001
    with respx.mock:
        route = respx.get(IMG).mock(
            return_value=httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        )
        response = auth_client.get(_endpoint(), follow_redirects=False)

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["cache-control"].startswith("private")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert route.call_count == 1


def test_second_request_is_served_from_disk(auth_client: TestClient) -> None:
    with respx.mock:
        route = respx.get(IMG).mock(return_value=httpx.Response(200, content=PNG))
        auth_client.get(_endpoint())
        again = auth_client.get(_endpoint())

    assert again.status_code == 200
    assert again.content == PNG
    # 命中缓存，不再打上游
    assert route.call_count == 1


def test_content_type_must_be_a_raster_image(auth_client: TestClient) -> None:
    """上游把 HTML 声明成 image/png 也不能缓存，按魔数判定。"""
    with respx.mock:
        respx.get(IMG).mock(
            return_value=httpx.Response(
                200, content=b"<html>not an image</html>", headers={"content-type": "image/png"}
            )
        )
        response = auth_client.get(_endpoint(), follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == IMG


def test_svg_is_rejected_and_redirected(auth_client: TestClient) -> None:
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    with respx.mock:
        respx.get(IMG).mock(
            return_value=httpx.Response(200, content=svg, headers={"content-type": "image/svg+xml"})
        )
        response = auth_client.get(_endpoint(), follow_redirects=False)

    assert response.status_code == 302


def test_failure_redirects_to_origin_and_is_not_retried(auth_client: TestClient) -> None:
    with respx.mock:
        route = respx.get(IMG).mock(return_value=httpx.Response(403))
        first = auth_client.get(_endpoint(), follow_redirects=False)
        second = auth_client.get(_endpoint(), follow_redirects=False)

    assert first.status_code == 302
    assert first.headers["location"] == IMG
    assert second.status_code == 302
    # 重试窗口内不再打上游
    assert route.call_count == 1


def test_failure_is_recorded_with_reason(auth_client: TestClient, db: Session) -> None:
    with respx.mock:
        respx.get(IMG).mock(return_value=httpx.Response(500))
        auth_client.get(_endpoint())

    with SessionLocal() as session:
        row = session.get(MediaCache, media.key_for(IMG))
    assert row is not None
    assert row.status == "failed"
    assert "500" in (row.error or "")


def test_retry_after_window_expires(auth_client: TestClient, db: Session) -> None:
    with respx.mock:
        route = respx.get(IMG).mock(return_value=httpx.Response(500))
        auth_client.get(_endpoint())

        with SessionLocal() as session:
            row = session.get(MediaCache, media.key_for(IMG))
            assert row is not None
            row.fetched_at = datetime.now(UTC) - timedelta(hours=99)
            session.commit()

        auth_client.get(_endpoint())
        assert route.call_count == 2


def test_size_cap_turns_into_redirect(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(media.get_settings(), "media_max_bytes", 16)
    with respx.mock:
        respx.get(IMG).mock(return_value=httpx.Response(200, content=PNG))
        response = auth_client.get(_endpoint(), follow_redirects=False)

    assert response.status_code == 302


def test_ssrf_guard_applies(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """装回真的 SSRF 校验：内网地址必须被拦下，且不写缓存。"""
    monkeypatch.setattr(feed_fetch, "check_url_allowed", REAL_CHECK)
    with respx.mock:
        route = respx.get("http://127.0.0.1:8899/secret.png").mock(
            return_value=httpx.Response(200, content=PNG)
        )
        response = auth_client.get(
            _endpoint("http://127.0.0.1:8899/secret.png"), follow_redirects=False
        )

    assert response.status_code == 302
    assert route.call_count == 0


def test_non_http_url_is_rejected(auth_client: TestClient) -> None:
    assert auth_client.get("/api/media?url=ftp://x.com/a.png").status_code == 400


def test_missing_url_param_is_422(auth_client: TestClient) -> None:
    assert auth_client.get("/api/media").status_code == 422


def test_media_endpoint_requires_login(client: TestClient) -> None:
    assert client.get(_endpoint()).status_code == 401


def test_disabled_cache_redirects(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media.get_settings(), "media_cache_enabled", False)
    with respx.mock:
        route = respx.get(IMG).mock(return_value=httpx.Response(200, content=PNG))
        response = auth_client.get(_endpoint(), follow_redirects=False)

    assert response.status_code == 302
    assert route.call_count == 0


# ---------- 淘汰 ----------


def _store(db: Session, url: str, size: int, age_hours: int) -> str:
    key = media.key_for(url)
    stamp = datetime.now(UTC) - timedelta(hours=age_hours)
    path = media.path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    db.add(
        MediaCache(
            hash=key,
            url=url,
            content_type="image/png",
            bytes=size,
            status="ok",
            fetched_at=stamp,
            last_used_at=stamp,
        )
    )
    db.commit()
    return key


def test_eviction_removes_least_recently_used(
    auth_client: TestClient, db: Session, monkeypatch
) -> None:  # noqa: ANN001
    _ = auth_client
    monkeypatch.setattr(media.get_settings(), "media_cache_max_mb", 1)

    old = _store(db, "https://cdn.example.com/old.png", 700_000, age_hours=10)
    new = _store(db, "https://cdn.example.com/new.png", 700_000, age_hours=1)

    removed = media._evict(db)
    assert removed >= 1
    assert db.get(MediaCache, old) is None
    assert db.get(MediaCache, new) is not None
    assert not media.path_for(old).exists()
    assert media.total_bytes(db) <= 1024 * 1024


def test_failed_rows_are_not_evicted(auth_client: TestClient, db: Session, monkeypatch) -> None:  # noqa: ANN001
    _ = auth_client
    monkeypatch.setattr(media.get_settings(), "media_cache_max_mb", 1)
    _store(db, "https://cdn.example.com/big.png", 900_000, age_hours=1)

    key = media.key_for("https://cdn.example.com/broken.png")
    db.add(MediaCache(hash=key, url="https://cdn.example.com/broken.png", status="failed"))
    db.commit()

    media._evict(db)
    # 失败行字节数为 0，不占预算，留着才能避免反复重试
    assert db.get(MediaCache, key) is not None


def test_clear_removes_rows_and_files(auth_client: TestClient, db: Session) -> None:  # noqa: ANN001
    _ = auth_client
    key = _store(db, "https://cdn.example.com/a.png", 100, age_hours=0)
    assert media.path_for(key).exists()

    media.clear(db)

    assert db.get(MediaCache, key) is None
    assert not media.path_for(key).exists()


def test_missing_file_is_refetched(auth_client: TestClient, db: Session) -> None:  # noqa: ANN001
    _ = auth_client
    _store(db, IMG, 10, age_hours=0)
    media.path_for(media.key_for(IMG)).unlink()

    with respx.mock:
        route = respx.get(IMG).mock(return_value=httpx.Response(200, content=PNG))
        response = auth_client.get(_endpoint())

    assert response.status_code == 200
    assert route.call_count == 1


def test_clear_failures_keeps_successes(auth_client: TestClient, db: Session) -> None:  # noqa: ANN001
    _ = auth_client
    ok_key = _store(db, "https://cdn.example.com/ok.png", 100, age_hours=0)
    with respx.mock:
        respx.get("https://cdn.example.com/bad.png").mock(return_value=httpx.Response(500))
        auth_client.get(_endpoint("https://cdn.example.com/bad.png"), follow_redirects=False)

    removed = media.clear_failures(db)

    assert removed == 1
    assert db.get(MediaCache, ok_key) is not None
    assert db.query(MediaCache).filter(MediaCache.status == "failed").count() == 0


def test_changing_proxy_clears_stale_failures(auth_client: TestClient, db: Session) -> None:  # noqa: ANN001
    """改了代理还留着旧失败记录，用户会觉得「改了没用」。"""
    with respx.mock:
        respx.get(IMG).mock(return_value=httpx.Response(403))
        auth_client.get(_endpoint(), follow_redirects=False)
    assert db.query(MediaCache).filter(MediaCache.status == "failed").count() == 1

    auth_client.patch("/api/proxy", json={"mode": "custom", "url": "127.0.0.1:7890"})

    from app.db import SessionLocal

    with SessionLocal() as session:
        assert session.query(MediaCache).filter(MediaCache.status == "failed").count() == 0


def test_freshly_fetched_image_is_never_evicted_by_its_own_insert(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """预算比单张图还小时，刚取到的这张也必须能正常返回，不能紧接着 302。"""
    monkeypatch.setattr(media.get_settings(), "media_cache_max_mb", 0)

    with respx.mock:
        respx.get(IMG).mock(return_value=httpx.Response(200, content=PNG))
        response = auth_client.get(_endpoint(), follow_redirects=False)

    assert response.status_code == 200
    assert response.content == PNG
    assert media.total_bytes(SessionLocal()) > 0


def test_eviction_still_trims_other_entries_when_protecting_one(db: Session, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(media.get_settings(), "media_cache_max_mb", 1)
    old = _store(db, "https://cdn.example.com/old.png", 900_000, age_hours=10)
    fresh = _store(db, "https://cdn.example.com/fresh.png", 900_000, age_hours=0)

    media._evict(db, keep=fresh)

    assert db.get(MediaCache, old) is None
    assert db.get(MediaCache, fresh) is not None
