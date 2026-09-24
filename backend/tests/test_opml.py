"""M2 OPML 导入导出。"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import opml_service
from app.services.opml_service import OpmlError
from tests.factories import ATOM, RSS_20, make_feed


@pytest.fixture(autouse=True)
def _skip_ssrf_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """本文件只验证导入/导出逻辑；SSRF 校验由 test_fetch.py 单独覆盖。

    真实的 DNS 解析受运行环境影响（沙箱里域名可能被解析到内网），不应拖累这些用例。
    """
    monkeypatch.setattr("app.services.feed_fetch.check_url_allowed", lambda url: None)


OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>我的订阅</title></head>
  <body>
    <outline text="技术">
      <outline type="rss" text="少数派" xmlUrl="https://sspai.com/feed"/>
      <outline type="rss" text="InfoQ" xmlUrl="https://www.infoq.cn/feed"/>
    </outline>
    <outline type="rss" text="阮一峰" xmlUrl="https://ruanyifeng.com/feed"/>
  </body>
</opml>
""".encode()


def test_parse_opml_keeps_folder_paths() -> None:
    entries = opml_service.parse_opml(OPML)
    assert [entry.xml_url for entry in entries] == [
        "https://sspai.com/feed",
        "https://www.infoq.cn/feed",
        "https://ruanyifeng.com/feed",
    ]
    assert entries[0].folders == ["技术"]
    assert entries[2].folders == []


def test_parse_opml_rejects_doctype() -> None:
    payload = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "b">]><opml><body/></opml>'
    with pytest.raises(OpmlError, match="DOCTYPE"):
        opml_service.parse_opml(payload)


def test_parse_opml_rejects_garbage() -> None:
    with pytest.raises(OpmlError):
        opml_service.parse_opml(b"not xml at all")


def test_export_import_roundtrip(client: TestClient, db: Session) -> None:
    """导出 → 清空 → 导入，目录层级保留。"""
    client.post("/api/auth/skip")
    client.post("/api/folders", json={"name": "技术"})
    folders = {
        folder["name"]: folder["id"] for folder in client.get("/api/folders").json()["items"]
    }

    with respx.mock:
        respx.get("https://sspai.com/feed").mock(return_value=httpx.Response(200, content=RSS_20))
        created = client.post(
            "/api/feeds", json={"url": "https://sspai.com/feed", "folder_id": folders["技术"]}
        )
    assert created.status_code == 201, created.text

    exported = client.get("/api/opml/export")
    assert exported.status_code == 200
    assert "text/x-opml" in exported.headers["content-type"]
    assert 'text="技术"' in exported.text
    assert 'xmlUrl="https://sspai.com/feed"' in exported.text

    # 换一个干净账号导入，验证层级还原
    other = TestClient(client.app)
    other.post(
        "/api/auth/register", json={"username": "bob", "email": "bob@x.com", "password": "12345678"}
    )

    with respx.mock:
        respx.get("https://sspai.com/feed").mock(return_value=httpx.Response(200, content=RSS_20))
        imported = other.post(
            "/api/opml/import",
            files={"file": ("sub.opml", exported.content, "text/x-opml")},
        )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"imported": 1, "skipped": 0, "errors": []}

    folders_b = {folder["name"]: folder for folder in other.get("/api/folders").json()["items"]}
    assert folders_b["技术"]["feed_count"] == 1
    feeds = other.get(f"/api/feeds?folder_id={folders_b['技术']['id']}").json()["items"]
    assert len(feeds) == 1
    assert len(other.get("/api/items").json()["items"]) == 3


def test_import_skips_existing_subscriptions(client: TestClient) -> None:
    client.post("/api/auth/skip")
    with respx.mock:
        respx.get("https://sspai.com/feed").mock(return_value=httpx.Response(200, content=RSS_20))
        respx.get("https://www.infoq.cn/feed").mock(return_value=httpx.Response(200, content=ATOM))
        respx.get("https://ruanyifeng.com/feed").mock(
            return_value=httpx.Response(200, content=RSS_20)
        )
        first = client.post("/api/opml/import", files={"file": ("a.opml", OPML, "text/x-opml")})
        second = client.post("/api/opml/import", files={"file": ("a.opml", OPML, "text/x-opml")})

    assert first.json()["imported"] == 3
    assert first.json()["skipped"] == 0
    assert second.json()["imported"] == 0
    assert second.json()["skipped"] == 3


def test_import_reports_unreachable_source_without_failing(client: TestClient) -> None:
    client.post("/api/auth/skip")
    with respx.mock:
        respx.get("https://sspai.com/feed").mock(return_value=httpx.Response(500))
        respx.get("https://www.infoq.cn/feed").mock(return_value=httpx.Response(200, content=ATOM))
        respx.get("https://ruanyifeng.com/feed").mock(
            return_value=httpx.Response(200, content=RSS_20)
        )
        response = client.post("/api/opml/import", files={"file": ("a.opml", OPML, "text/x-opml")})

    payload = response.json()
    assert payload["imported"] == 2
    assert len(payload["errors"]) == 1
    assert "sspai" in payload["errors"][0]


def test_invalid_opml_returns_400(client: TestClient) -> None:
    client.post("/api/auth/skip")
    response = client.post("/api/opml/import", files={"file": ("bad.opml", b"nope", "text/plain")})
    assert response.status_code == 400


def test_export_handles_ungrouped_feeds(client: TestClient, db: Session) -> None:
    client.post("/api/auth/skip")
    feed = make_feed(db, "未分组源", url="https://lonely.example.com/feed")
    from app.models import User
    from tests.factories import subscribe

    user = db.query(User).first()
    assert user is not None
    subscribe(db, user, feed)

    exported = client.get("/api/opml/export").text
    assert "未分组" in exported
    assert "https://lonely.example.com/feed" in exported
