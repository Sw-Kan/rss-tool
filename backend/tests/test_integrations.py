"""F2 集成：RSSHub 配置/展开/测试、飞书/自定义推送、Obsidian 落盘。"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.services import feed_fetch, integrations
from tests.factories import add_article, make_feed, subscribe

RSSHUB = "https://rsshub.example.com"


@pytest.fixture(autouse=True)
def allow_fake_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """这些用例只验证集成逻辑，不关心 SSRF 解析（test_fetch.py 单独覆盖）。"""
    monkeypatch.setattr(feed_fetch, "check_url_allowed", lambda url: [])


# ---------- 配置读写 ----------


def test_list_returns_all_kinds_with_defaults(auth_client: TestClient) -> None:
    items = auth_client.get("/api/integrations").json()["items"]
    assert [item["kind"] for item in items] == list(integrations.KINDS)
    rsshub = next(item for item in items if item["kind"] == "rsshub")
    assert rsshub["rsshub"] == {"base_url": "", "access_key": "", "env": "", "params": []}
    assert rsshub["enabled"] is True


def _stub_article(db, **overrides: object):  # noqa: ANN001, ANN202
    """造一篇挂在真实 feed 下的文章（articles.feed_id 非空）。"""
    from app.models import User

    user = db.query(User).order_by(User.created_at).first()
    assert user is not None
    feed = make_feed(db, "少数派", url=f"https://example.com/{user.id}.xml")
    subscribe(db, user, feed)
    article = add_article(db, feed, guid="g1", title="标题")
    for key, value in overrides.items():
        setattr(article, key, value)
    db.commit()
    return article


def test_update_and_read_back_rsshub(auth_client: TestClient) -> None:
    response = auth_client.put(
        "/api/integrations/rsshub",
        json={
            "enabled": False,
            "rsshub": {
                "base_url": RSSHUB,
                "access_key": "s3cret",
                "env": "CACHE_TYPE=memory, CACHE_EXPIRE=600",
                "params": [
                    {
                        "name": "cookie",
                        "scope": "/zhihu",
                        "value": "z_c0=abcdef123456",
                        "secret": True,
                    },
                    {"name": "limit", "scope": "/twitter/user", "value": "20", "secret": False},
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is False
    assert body["rsshub"]["base_url"] == RSSHUB
    # 密文一律掩码回传
    assert body["rsshub"]["access_key"] == "••••••••"
    assert body["rsshub"]["params"][0]["value"] == "z_c0=••••••••"
    assert body["rsshub"]["params"][1]["value"] == "20"
    assert "z_c0=abcdef123456" not in response.text
    assert "s3cret" not in response.text


def test_masked_secret_sent_back_keeps_real_value(auth_client: TestClient, db) -> None:  # noqa: ANN001
    first = auth_client.put(
        "/api/integrations/rsshub",
        json={
            "rsshub": {
                "base_url": RSSHUB,
                "access_key": "real-key-1234",
                "params": [
                    {"name": "cookie", "scope": "/zhihu", "value": "z_c0=abcdef", "secret": True}
                ],
            }
        },
    ).json()
    # 接口回传的就是掩码
    assert first["rsshub"]["access_key"] == "real-••••••••1234"
    assert first["rsshub"]["params"][0]["value"] == "z_c0=••••••••"

    # 前端把掩码原样送回，只改 env
    auth_client.put(
        "/api/integrations/rsshub",
        json={
            "rsshub": {
                "base_url": RSSHUB,
                "access_key": first["rsshub"]["access_key"],
                "env": "DEBUG=1",
                "params": [
                    {
                        "name": "cookie",
                        "scope": "/zhihu",
                        "value": first["rsshub"]["params"][0]["value"],
                        "secret": True,
                    }
                ],
            }
        },
    )

    from app.db import SessionLocal

    with SessionLocal() as session:
        config = integrations.get_config(session, _only_user_id(session), "rsshub")
    assert config["access_key"] == "real-key-1234"
    assert config["params"][0]["value"] == "z_c0=abcdef"
    assert config["env"] == "DEBUG=1"


def test_any_masked_value_is_treated_as_unchanged(auth_client: TestClient, db) -> None:  # noqa: ANN001
    """哪怕前端送回来的掩码形状和我们的不一样，也不能把掩码存成真密钥。"""
    auth_client.put(
        "/api/integrations/rsshub",
        json={"rsshub": {"base_url": RSSHUB, "access_key": "real-key-1234"}},
    )
    auth_client.put(
        "/api/integrations/rsshub",
        json={"rsshub": {"base_url": RSSHUB, "access_key": "••••••••"}},
    )

    from app.db import SessionLocal

    with SessionLocal() as session:
        config = integrations.get_config(session, _only_user_id(session), "rsshub")
    assert config["access_key"] == "real-key-1234"


def _only_user_id(db) -> str:  # noqa: ANN001
    from app.models import User

    user = db.query(User).order_by(User.created_at).first()
    assert user is not None
    return user.id


def test_unknown_kind_is_rejected(auth_client: TestClient) -> None:
    # path 参数是 Literal，非法值在进 handler 之前就被 FastAPI 拦下
    assert auth_client.put("/api/integrations/nope", json={}).status_code == 422


# ---------- 掩码 ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("abc", "••••••••"),
        ("z_c0=abcdef123456", "z_c0=••••••••"),
        ("ghp_abcdefghijkl4f2a", "ghp_••••••••4f2a"),
        ("abcdefghijklmnop", "abc••••••••mnop"),
    ],
)
def test_mask_secret(raw: str, expected: str) -> None:
    assert integrations.mask_secret(raw) == expected


# ---------- 路由展开 ----------


def test_expand_route_applies_scope_and_access_key() -> None:
    config = {
        "base_url": RSSHUB + "/",
        "access_key": "s3cret",
        "params": [
            {"name": "cookie", "scope": "/zhihu", "value": "z_c0=x", "secret": True},
            {"name": "limit", "scope": "/twitter/user", "value": "20", "secret": False},
            {"name": "global", "scope": "", "value": "1", "secret": False},
        ],
    }

    twitter = integrations.expand_route(config, "/twitter/user/abc")
    assert twitter.startswith(f"{RSSHUB}/twitter/user/abc?")
    assert "limit=20" in twitter
    assert "global=1" in twitter
    assert "cookie" not in twitter
    assert "key=s3cret" in twitter

    # 作用范围不匹配 → 只带全局参数
    other = integrations.expand_route(config, "/sspai/matrix")
    assert "limit=20" not in other
    assert "global=1" in other


def test_expand_route_requires_base_url() -> None:
    with pytest.raises(integrations.IntegrationError, match="服务地址"):
        integrations.expand_route({"base_url": ""}, "/a")


def test_expand_route_rejects_bad_scheme() -> None:
    with pytest.raises(integrations.IntegrationError, match="http://"):
        integrations.expand_route({"base_url": "ftp://x.com"}, "/a")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("/sspai/matrix", True), ("//example.com/a", False), ("https://x.com/a", False), ("", False)],
)
def test_looks_like_route(value: str, expected: bool) -> None:
    assert integrations.looks_like_route(value) is expected


def test_bare_route_is_expanded_when_adding_feed(auth_client: TestClient) -> None:
    auth_client.put(
        "/api/integrations/rsshub",
        json={"rsshub": {"base_url": RSSHUB, "access_key": "s3cret"}},
    )

    with respx.mock:
        route = respx.get(f"{RSSHUB}/sspai/matrix?key=s3cret").mock(
            return_value=httpx.Response(200, content=_rss())
        )
        created = auth_client.post("/api/feeds", json={"url": "/sspai/matrix"})

    assert created.status_code == 201, created.text
    assert created.json()["url"] == f"{RSSHUB}/sspai/matrix?key=s3cret"
    assert route.called


def test_bare_route_without_config_is_rejected(auth_client: TestClient) -> None:
    response = auth_client.post("/api/feeds", json={"url": "/sspai/matrix"})
    assert response.status_code == 400
    assert "服务地址" in response.json()["detail"]


def _rss(title: str = "RSSHub 源") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{title}</title><link>https://example.com</link>"
        "<item><title>条目</title><link>https://example.com/1</link><guid>g1</guid>"
        "<description>正文</description></item></channel></rss>"
    ).encode()


# ---------- 测试连接 ----------


def test_rsshub_test_reports_ok(auth_client: TestClient) -> None:
    auth_client.put("/api/integrations/rsshub", json={"rsshub": {"base_url": RSSHUB}})
    with respx.mock:
        respx.get(f"{RSSHUB}/").mock(return_value=httpx.Response(200, text="Welcome to RSSHub!"))
        body = auth_client.post("/api/integrations/rsshub/test").json()

    assert body["ok"] is True
    assert body["message"] == "连接正常"
    assert isinstance(body["latency_ms"], int)


def test_rsshub_test_reports_failure(auth_client: TestClient) -> None:
    auth_client.put("/api/integrations/rsshub", json={"rsshub": {"base_url": RSSHUB}})
    with respx.mock:
        respx.get(f"{RSSHUB}/").mock(return_value=httpx.Response(503))
        body = auth_client.post("/api/integrations/rsshub/test").json()

    assert body["ok"] is False
    assert "503" in body["message"]


def test_rsshub_test_without_url(auth_client: TestClient) -> None:
    body = auth_client.post("/api/integrations/rsshub/test").json()
    assert body["ok"] is False
    assert "服务地址" in body["message"]


# ---------- 推送目标 ----------


def test_feishu_push_payload(auth_client: TestClient, db) -> None:  # noqa: ANN001
    webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
    auth_client.put("/api/integrations/feishu", json={"feishu": {"webhook_url": webhook}})

    import asyncio

    from app.db import SessionLocal

    with SessionLocal() as session:
        user_id = _only_user_id(session)
        config = integrations.get_config(session, user_id, "feishu")
        article = _stub_article(session, url="https://x.com/1")

        with respx.mock:
            route = respx.post(webhook).mock(return_value=httpx.Response(200, json={"code": 0}))
            asyncio.run(integrations.push_feishu(config, article, "少数派"))

    sent = json.loads(route.calls[0].request.content)
    assert sent["msg_type"] == "text"
    assert "标题" in sent["content"]["text"]
    assert "https://x.com/1" in sent["content"]["text"]


def test_obsidian_save_writes_markdown(auth_client: TestClient, db, tmp_path) -> None:  # noqa: ANN001
    vault = tmp_path / "vault"
    auth_client.put("/api/integrations/obsidian", json={"obsidian": {"vault_path": str(vault)}})

    from app.db import SessionLocal

    with SessionLocal() as session:
        config = integrations.get_config(session, _only_user_id(session), "obsidian")
        article = _stub_article(
            session,
            title="为什么我又回到了 RSS：把信息流还给自己",
            url="https://x.com/1",
            content_html="<p>正文</p>",
        )
        written = integrations.save_to_obsidian(config, article, "少数派")

    assert written.exists()
    assert written.parent == vault
    text = written.read_text(encoding="utf-8")
    assert "# 为什么我又回到了 RSS：把信息流还给自己" in text
    assert "feed: 少数派" in text


def test_obsidian_sanitizes_path_traversal(auth_client: TestClient, db, tmp_path) -> None:  # noqa: ANN001
    vault = tmp_path / "vault"
    auth_client.put("/api/integrations/obsidian", json={"obsidian": {"vault_path": str(vault)}})

    from app.db import SessionLocal

    with SessionLocal() as session:
        config = integrations.get_config(session, _only_user_id(session), "obsidian")
        article = _stub_article(session, title="../../../../etc/passwd", url=None)
        written = integrations.save_to_obsidian(config, article, "x")

    # 路径分隔符被替换掉了：文件确实落在仓库根目录，不存在目录穿越
    assert written.parent == vault.resolve()
    assert "/" not in written.name
    assert "\\" not in written.name


def test_obsidian_requires_absolute_path() -> None:
    with pytest.raises(integrations.IntegrationError, match="绝对路径"):
        integrations.save_to_obsidian({"vault_path": "relative/dir"}, _detached_article(), "x")


def test_custom_export_payload(db) -> None:  # noqa: ANN001
    import asyncio

    with respx.mock:
        route = respx.post("https://api.example.com/import").mock(return_value=httpx.Response(202))
        asyncio.run(
            integrations.push_custom(
                {"endpoint": "https://api.example.com/import"}, _detached_article(), "少数派"
            )
        )

    payload = json.loads(route.calls[0].request.content)
    assert payload["title"] == "标题"
    assert payload["source"] == "少数派"
    assert payload["link"] == "https://x.com/1"


def test_custom_export_rejects_missing_endpoint() -> None:
    import asyncio

    with pytest.raises(integrations.IntegrationError, match="接口"):
        asyncio.run(integrations.push_custom({}, _detached_article(), "x"))


def _detached_article():  # noqa: ANN202
    """不需要落库的临时对象，用于纯推送/落盘逻辑。"""
    from datetime import UTC, datetime

    from app.models import Article

    return Article(
        title="标题",
        url="https://x.com/1",
        kind="article",
        content_html="<p>正文</p>",
        published_at=datetime.now(UTC),
    )


# ---------- 自定义导出 schema ----------


def test_default_schema_is_offered_to_the_ui(auth_client: TestClient) -> None:
    body = auth_client.get("/api/integrations/custom_export/default-schema").json()
    assert "{{title}}" in body["schema_template"]
    assert "{{url}}" in body["schema_template"]


def test_custom_schema_is_rendered(auth_client: TestClient, db) -> None:  # noqa: ANN001
    import asyncio

    from app.db import SessionLocal

    with SessionLocal() as session:
        article = _stub_article(session)
        template = '{"n": "{{title}}", "meta": {"src": "{{feed}}", "k": "{{kind}}"}}'
        payload = integrations.render_template(template, article, "少数派")
        assert payload == {
            "n": "标题",
            "meta": {"src": "少数派", "k": "article"},
        }

        # 真的按模板 POST 出去
        with respx.mock:
            route = respx.post("https://api.example.com/x").mock(return_value=httpx.Response(200))
            asyncio.run(
                integrations.push_custom(
                    {"endpoint": "https://api.example.com/x", "schema_template": template},
                    article,
                    "少数派",
                )
            )
        assert json.loads(route.calls[0].request.content)["n"] == "标题"


def test_unknown_template_variable_is_reported_clearly(auth_client: TestClient, db) -> None:  # noqa: ANN001
    from app.db import SessionLocal

    with SessionLocal() as session:
        article = _stub_article(session)
        with pytest.raises(integrations.IntegrationError, match="不认识的变量"):
            integrations.render_template('{"n": {{word_count}}}', article, "x")


def test_broken_json_template_is_rejected(auth_client: TestClient, db) -> None:  # noqa: ANN001
    from app.db import SessionLocal

    with SessionLocal() as session:
        article = _stub_article(session)
        with pytest.raises(integrations.IntegrationError, match="合法 JSON"):
            integrations.render_template('{"n": "{{title}}"', article, "x")


def test_template_escapes_quotes_in_values(auth_client: TestClient, db) -> None:  # noqa: ANN001
    """标题里带引号不能把模板搞坏。"""
    from app.db import SessionLocal

    with SessionLocal() as session:
        article = _stub_article(session, title='他说"你好"然后就走了')
        payload = integrations.render_template('{"n": "{{title}}"}', article, "x")
        assert payload["n"] == '他说"你好"然后就走了'


def test_custom_export_test_endpoint(auth_client: TestClient) -> None:
    auth_client.put(
        "/api/integrations/custom_export",
        json={"custom_export": {"endpoint": "https://api.example.com/x"}},
    )
    with respx.mock:
        route = respx.post("https://api.example.com/x").mock(return_value=httpx.Response(202))
        body = auth_client.post("/api/integrations/custom_export/test").json()

    assert body["ok"] is True
    assert "推送成功" in body["message"]
    assert json.loads(route.calls[0].request.content)["title"] == "示例文章标题"


def test_custom_export_test_without_endpoint(auth_client: TestClient) -> None:
    body = auth_client.post("/api/integrations/custom_export/test").json()
    assert body["ok"] is False
    assert "推送接口" in body["message"]


def test_custom_export_test_reports_upstream_error(auth_client: TestClient) -> None:
    auth_client.put(
        "/api/integrations/custom_export",
        json={"custom_export": {"endpoint": "https://api.example.com/x"}},
    )
    with respx.mock:
        respx.post("https://api.example.com/x").mock(return_value=httpx.Response(500))
        body = auth_client.post("/api/integrations/custom_export/test").json()

    assert body["ok"] is False
    assert "500" in body["message"]


# ---------- 参数用途：拼到路由 / 传给 RSSHub ----------


def test_expand_route_skips_env_params() -> None:
    """凭据绝不能拼进订阅地址 —— 那会被写进 feeds.url，全库共享。"""
    config = {
        "base_url": RSSHUB,
        "access_key": "",
        "params": [
            {"name": "PIXIV_REFRESH_TOKEN", "value": "tok", "target": "env"},
            {"name": "limit", "scope": "/pixiv", "value": "20", "target": "query"},
        ],
    }
    url = integrations.expand_route(config, "/pixiv/user/1")
    assert "limit=20" in url
    assert "PIXIV_REFRESH_TOKEN" not in url
    assert "tok" not in url


def test_normalize_params_fixes_silent_failures() -> None:
    """作用范围漏斜杠、凭据没勾密文 —— 两种「静默失效」都在写库前归一。"""
    normalized = integrations.normalize_params(
        [
            {"name": "limit", "scope": "pixiv", "value": "20"},
            {"name": "refresh_token", "value": "t"},
            {"name": "PIXIV_REFRESH_TOKEN", "scope": "/pixiv", "value": "t", "target": "env"},
        ]
    )
    # 老数据没有 target → 按 query 走，行为不变；scope 补上斜杠，否则永远拼不上
    assert normalized[0]["target"] == "query"
    assert normalized[0]["scope"] == "/pixiv"
    assert normalized[0]["secret"] is False
    # 名字像凭据 / env 型 → 强制密文
    assert normalized[1]["secret"] is True
    assert normalized[2]["target"] == "env"
    assert normalized[2]["scope"] == ""
    assert normalized[2]["secret"] is True


def test_masked_config_hides_credentials() -> None:
    masked = integrations.masked_config(
        "rsshub",
        {
            "access_key": "real-key-1234",
            "params": [
                {"name": "PIXIV_REFRESH_TOKEN", "value": "pixiv-secret", "target": "env"},
                {"name": "github_token", "value": "gh-secret"},
                {"name": "limit", "value": "20"},
            ],
        },
    )
    assert masked["access_key"] == "real-••••••••1234"
    values = [item["value"] for item in masked["params"]]
    assert "•" in values[0] and "pixiv-secret" not in values[0]
    assert "•" in values[1] and "gh-secret" not in values[1]
    assert values[2] == "20"  # 普通参数照旧明文


def test_env_param_name_must_be_upper_snake(auth_client: TestClient) -> None:
    response = auth_client.put(
        "/api/integrations/rsshub",
        json={
            "rsshub": {
                "base_url": RSSHUB,
                "params": [{"name": "pixiv_token", "value": "x", "target": "env"}],
            }
        },
    )
    assert response.status_code == 400
    assert "PIXIV_REFRESH_TOKEN" in response.json()["detail"]


def test_params_are_normalized_on_write(auth_client: TestClient) -> None:
    auth_client.put(
        "/api/integrations/rsshub",
        json={
            "rsshub": {
                "base_url": RSSHUB,
                "params": [
                    {"name": "limit", "scope": "pixiv", "value": "20"},
                    {"name": "PIXIV_REFRESH_TOKEN", "value": "pixiv-secret", "target": "env"},
                ],
            }
        },
    )
    params = auth_client.get("/api/integrations").json()["items"][0]["rsshub"]["params"]
    assert params[0]["scope"] == "/pixiv"
    assert params[0]["target"] == "query"
    assert params[1]["target"] == "env"
    assert params[1]["scope"] == ""
    assert params[1]["secret"] is True
    assert "•" in params[1]["value"]  # 回传仍是掩码


def test_env_param_masked_value_is_not_stored(auth_client: TestClient) -> None:
    """前端把掩码原样送回（改别的字段时）不能把真值抹成掩码。"""
    auth_client.put(
        "/api/integrations/rsshub",
        json={
            "rsshub": {
                "base_url": RSSHUB,
                "params": [{"name": "PIXIV_REFRESH_TOKEN", "value": "tok-1234", "target": "env"}],
            }
        },
    )
    masked = auth_client.get("/api/integrations").json()["items"][0]["rsshub"]["params"][0]
    auth_client.put(
        "/api/integrations/rsshub",
        json={"rsshub": {"base_url": RSSHUB, "env": "CACHE_TYPE=memory", "params": [masked]}},
    )

    from app.db import SessionLocal

    with SessionLocal() as session:
        config = integrations.get_config(session, _only_user_id(session), "rsshub")
    assert config["params"][0]["value"] == "tok-1234"
    assert config["env"] == "CACHE_TYPE=memory"


# ---------- RSSHub 端 env 片段 ----------


def test_env_snippet_renders_both_forms(auth_client: TestClient) -> None:
    auth_client.put(
        "/api/integrations/rsshub",
        json={
            "rsshub": {
                "base_url": RSSHUB,
                "env": "CACHE_TYPE=memory, CACHE_EXPIRE=600",
                "params": [
                    {"name": "PIXIV_REFRESH_TOKEN", "value": "tok en", "target": "env"},
                    {"name": "limit", "scope": "/pixiv", "value": "20"},
                ],
            }
        },
    )
    response = auth_client.get("/api/integrations/rsshub/env-snippet")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"

    body = response.json()
    assert body["dotenv"] == "PIXIV_REFRESH_TOKEN=tok en\nCACHE_TYPE=memory\nCACHE_EXPIRE=600"
    # 值里有空格时交给 shlex 转义
    assert body["docker_flags"] == (
        "-e PIXIV_REFRESH_TOKEN='tok en' -e CACHE_TYPE=memory -e CACHE_EXPIRE=600"
    )
    # query 型参数是拼订阅地址的，不该混进环境变量
    assert "limit" not in body["dotenv"]


def test_env_snippet_is_empty_without_config(auth_client: TestClient) -> None:
    body = auth_client.get("/api/integrations/rsshub/env-snippet").json()
    assert body == {"dotenv": "", "docker_flags": ""}


def test_env_snippet_requires_login(client: TestClient) -> None:
    assert client.get("/api/integrations/rsshub/env-snippet").status_code == 401
