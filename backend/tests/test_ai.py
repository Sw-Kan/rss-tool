"""F1 AI 助手：配置、用量、总结与标题翻译。不打真实上游。"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AiProvider, AiResult, User, UserSettings
from app.services import ai
from tests.factories import add_article, make_feed, subscribe

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def sse_body(frames: list[dict]) -> bytes:
    """把若干条上游 SSE 帧拼成一个响应体（末尾补 [DONE]）。"""
    body = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
    return (body + "data: [DONE]\n\n").encode()


def openai_stream(parts: list[str], usage: tuple[int, int] = (0, 0)) -> httpx.Response:
    frames: list[dict] = [{"choices": [{"delta": {"content": part}}]} for part in parts]
    frames.append(
        {"choices": [], "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}
    )
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content=sse_body(frames)
    )


def openai_reply(text: str = "一句话总结。\n• 要点一\n• 要点二") -> httpx.Response:
    """真实上游是分块给的，这里也切两块，顺便覆盖增量累加。"""
    half = max(1, len(text) // 2)
    return openai_stream([text[:half], text[half:]], usage=(120, 30))


def anthropic_reply(text: str = "译文标题") -> httpx.Response:
    frames = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 10, "output_tokens": 0}}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
        {"type": "message_delta", "usage": {"output_tokens": 5}},
    ]
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content=sse_body(frames)
    )


def events(body: str) -> list[tuple[str, dict]]:
    """把响应体拆成 [(事件名, data)]，用于断言 SSE 帧序列。"""
    parsed: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        name = ""
        data: dict = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        parsed.append((name, data))
    return parsed


# ---------- 预设与掩码 ----------


def test_presets_cover_design_and_are_keyed() -> None:
    keys = {preset.key for preset in ai.PRESETS}
    assert {"openai", "anthropic", "ollama", "custom"} <= keys
    assert ai.PRESETS_BY_KEY["anthropic"].protocol == "anthropic"
    assert ai.PRESETS_BY_KEY["ollama"].base_url.startswith("http://127.0.0.1")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("short", "••••••••"),
        ("sk-1234567890abcdef", "sk-••••••••cdef"),
        ("sk-ant-api03-abcdefghijkl", "sk-••••••••ijkl"),
    ],
)
def test_mask_key(raw: str, expected: str) -> None:
    assert ai.mask_key(raw) == expected


# ---------- 配置接口 ----------


def test_provider_crud_never_returns_api_key(auth_client: TestClient) -> None:
    created = auth_client.post("/api/ai/providers", json={"preset": "openai"})
    assert created.status_code == 201
    provider = created.json()
    assert provider["label"] == "OpenAI"
    assert provider["has_key"] is False

    # 设置 key 后只回传掩码
    patched = auth_client.patch(
        f"/api/ai/providers/{provider['id']}", json={"api_key": "sk-1234567890abcdef"}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["has_key"] is True
    assert body["api_key_hint"] == "sk-••••••••cdef"
    assert "sk-1234567890abcdef" not in patched.text

    listed = auth_client.get("/api/ai/config").json()
    assert len(listed["providers"]) == 1
    assert "sk-1234567890abcdef" not in str(listed)


def test_patching_without_api_key_keeps_it(auth_client: TestClient, db: Session) -> None:
    provider = auth_client.post("/api/ai/providers", json={"preset": "openai"}).json()
    auth_client.patch(f"/api/ai/providers/{provider['id']}", json={"api_key": "sk-abcdefgh1234"})
    auth_client.patch(f"/api/ai/providers/{provider['id']}", json={"model": "gpt-4o"})

    with SessionLocal() as session:
        row = session.get(AiProvider, provider["id"])
        assert row is not None
        assert row.api_key == "sk-abcdefgh1234"
        assert row.model == "gpt-4o"


def test_clear_key_removes_it(auth_client: TestClient) -> None:
    provider = auth_client.post("/api/ai/providers", json={"preset": "openai"}).json()
    auth_client.patch(f"/api/ai/providers/{provider['id']}", json={"api_key": "sk-abcdefgh1234"})
    cleared = auth_client.patch(
        f"/api/ai/providers/{provider['id']}", json={"clear_key": True}
    ).json()
    assert cleared["has_key"] is False
    assert cleared["api_key_hint"] == ""


def test_unknown_preset_is_rejected(auth_client: TestClient) -> None:
    assert auth_client.post("/api/ai/providers", json={"preset": "gemini"}).status_code == 400


def test_provider_isolation_between_users(auth_client: TestClient) -> None:
    provider = auth_client.post("/api/ai/providers", json={"preset": "openai"}).json()

    other = TestClient(auth_client.app)
    other.post(
        "/api/auth/register", json={"username": "b", "email": "b@x.com", "password": "12345678"}
    )

    assert other.get("/api/ai/config").json()["providers"] == []
    assert (
        other.patch(f"/api/ai/providers/{provider['id']}", json={"model": "x"}).status_code == 404
    )
    assert other.delete(f"/api/ai/providers/{provider['id']}").status_code == 404


def test_delete_provider(auth_client: TestClient) -> None:
    provider = auth_client.post("/api/ai/providers", json={"preset": "openai"}).json()
    assert auth_client.delete(f"/api/ai/providers/{provider['id']}").status_code == 204
    assert auth_client.get("/api/ai/config").json()["providers"] == []


# ---------- 生成 ----------


def _seed_article() -> str:
    with SessionLocal() as db:
        user = db.query(User).order_by(User.created_at).first()
        assert user is not None
        feed = make_feed(db, "少数派", url="https://sspai.com/feed")
        subscribe(db, user, feed)
        article = add_article(db, feed, guid="a1", kind="article")
        return article.id


def _configure(
    auth_client: TestClient, preset: str = "openai", key: str = "sk-abcdefgh1234"
) -> None:
    provider = auth_client.post("/api/ai/providers", json={"preset": preset}).json()
    auth_client.patch(f"/api/ai/providers/{provider['id']}", json={"api_key": key})


def _set_token_limit(limit: int) -> None:
    with SessionLocal() as db:
        user = db.query(User).order_by(User.created_at).first()
        assert user is not None
        row = db.get(UserSettings, user.id)
        assert row is not None
        row.ai_token_limit = limit
        db.commit()


def test_summarize_calls_upstream_and_caches(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply())
        first = auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})

        assert first.status_code == 200, first.text
        body = first.json()
        assert body["cached"] is False
        assert "要点一" in body["content"]
        assert (body["tokens_in"], body["tokens_out"]) == (120, 30)

        # 第二次命中缓存，不再打上游
        second = auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})
        assert second.status_code == 200
        assert second.json()["cached"] is True
        assert route.call_count == 1

    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer sk-abcdefgh1234"
    body = json.loads(sent.content)
    assert body["model"] == "gpt-4o-mini"
    assert body["stream"] is True
    assert body["messages"][0]["role"] == "system"


def test_summarize_prompt_is_plain_text_and_includes_article(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply())
        auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})

    body = json.loads(route.calls[0].request.content)
    assert "只输出纯文本" in body["messages"][0]["content"]
    assert "标题" in body["messages"][1]["content"]


def test_translate_uses_anthropic_protocol(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client, preset="anthropic", key="sk-ant-abcdefgh1234")

    with respx.mock:
        route = respx.post(ANTHROPIC_URL).mock(return_value=anthropic_reply("把信息流还给自己"))
        response = auth_client.post(
            "/api/ai/generate?kind=title_translation", json={"article_id": article_id}
        )

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "把信息流还给自己"
    request = route.calls[0].request
    assert request.headers["x-api-key"] == "sk-ant-abcdefgh1234"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in request.headers
    assert json.loads(request.content)["max_tokens"] > 0


def test_no_api_key_means_no_auth_header(auth_client: TestClient) -> None:
    """本地 Ollama 就是没有 key 的场景。"""
    article_id = _seed_article()
    provider = auth_client.post("/api/ai/providers", json={"preset": "ollama"}).json()
    assert provider["has_key"] is False

    with respx.mock:
        route = respx.post("http://127.0.0.1:11434/v1/chat/completions").mock(
            return_value=openai_reply()
        )
        assert (
            auth_client.post(
                "/api/ai/generate?kind=summary", json={"article_id": article_id}
            ).status_code
            == 200
        )

    assert "authorization" not in route.calls[0].request.headers


def test_results_endpoint_backfills_without_calling_upstream(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    empty = auth_client.get(f"/api/ai/results?article_id={article_id}").json()
    assert empty == {"summary": None, "title_translation": None}

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply())
        auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})

        filled = auth_client.get(f"/api/ai/results?article_id={article_id}").json()
        assert filled["summary"]["cached"] is True
        assert filled["title_translation"] is None
        assert route.call_count == 1


def test_article_from_another_user_is_not_ai_able(auth_client: TestClient) -> None:
    with SessionLocal() as db:
        feed = make_feed(db, url="https://nobody.example.com/feed")
        orphan = add_article(db, feed, guid="orphan")
    _configure(auth_client)

    response = auth_client.post("/api/ai/generate?kind=summary", json={"article_id": orphan.id})
    assert response.status_code == 404
    assert auth_client.get(f"/api/ai/results?article_id={orphan.id}").status_code == 404


# ---------- 失败路径 ----------


def test_missing_provider_is_a_config_error(auth_client: TestClient) -> None:
    article_id = _seed_article()
    response = auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})
    assert response.status_code == 400
    assert "设置 → AI" in response.json()["detail"]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"base_url": "ftp://x.com", "model": "m"}, "http:// 或 https://"),
        ({"model": "m"}, "缺少接口地址"),
        ({"base_url": "https://api.example.com/v1"}, "缺少模型名"),
    ],
)
def test_invalid_provider_config_returns_400(
    auth_client: TestClient, fields: dict[str, str], expected: str
) -> None:
    article_id = _seed_article()
    provider = auth_client.post("/api/ai/providers", json={"preset": "custom"}).json()
    auth_client.patch(f"/api/ai/providers/{provider['id']}", json=fields)

    response = auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})
    assert response.status_code == 400
    assert expected in response.json()["detail"]


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        (httpx.Response(401, text="invalid api key"), "HTTP 401"),
        (httpx.Response(500, text="boom"), "HTTP 500"),
        # 200 但不是 SSE 流（比如 base_url 指到了普通网页）：当作没有内容
        (httpx.Response(200, content=b"not json"), "没有返回内容"),
        (httpx.Response(200, json={"choices": []}), "没有返回内容"),
    ],
)
def test_upstream_failures_become_502(
    auth_client: TestClient, upstream: httpx.Response, expected: str
) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        respx.post(OPENAI_URL).mock(return_value=upstream)
        response = auth_client.post(
            "/api/ai/generate?kind=summary", json={"article_id": article_id}
        )

    assert response.status_code == 502
    assert expected in response.json()["detail"]


def test_timeout_becomes_502(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        respx.post(OPENAI_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
        response = auth_client.post(
            "/api/ai/generate?kind=summary", json={"article_id": article_id}
        )

    assert response.status_code == 502
    assert "超时" in response.json()["detail"]


def test_failure_is_not_cached(auth_client: TestClient) -> None:
    """上游失败不该写 ai_results，否则用户修好配置也没法重试。"""
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        respx.post(OPENAI_URL).mock(return_value=httpx.Response(500))
        auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})

    with SessionLocal() as db:
        assert db.query(AiResult).count() == 0


# ---------- 用量与上限 ----------


def test_usage_accumulates_and_is_isolated_per_user(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        respx.post(OPENAI_URL).mock(return_value=openai_reply())
        auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})
        auth_client.post("/api/ai/generate?kind=title_translation", json={"article_id": article_id})

    usage = auth_client.get("/api/ai/usage").json()
    assert usage["month_tokens"] == 300  # 两篇 × (120 + 30)
    assert usage["total_tokens"] == 300
    assert usage["calls"] == 2
    assert usage["by_kind"] == {"summary": 150, "title_translation": 150}
    assert usage["limit"] == 0

    other = TestClient(auth_client.app)
    other.post(
        "/api/auth/register", json={"username": "b", "email": "b@x.com", "password": "12345678"}
    )
    assert other.get("/api/ai/usage").json()["total_tokens"] == 0


def test_token_limit_blocks_further_calls(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)
    _set_token_limit(100)

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply())
        first = auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})
        assert first.status_code == 200

        # 已用 150 > 上限 100
        blocked = auth_client.post(
            "/api/ai/generate?kind=title_translation", json={"article_id": article_id}
        )

    assert blocked.status_code == 429
    assert "上限" in blocked.json()["detail"]
    assert route.call_count == 1
    assert auth_client.get("/api/ai/usage").json()["limit"] == 100


def test_cached_result_is_returned_even_when_over_limit(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        respx.post(OPENAI_URL).mock(return_value=openai_reply())
        auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})

    _set_token_limit(10)

    again = auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})
    assert again.status_code == 200
    assert again.json()["cached"] is True


def test_unknown_kind_is_rejected(auth_client: TestClient) -> None:
    article_id = _seed_article()
    response = auth_client.post("/api/ai/generate?kind=poem", json={"article_id": article_id})
    assert response.status_code == 422


def test_ai_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/ai/config").status_code == 401
    assert client.get("/api/ai/usage").status_code == 401
    assert client.get("/api/ai/results?article_id=x").status_code == 401


def test_presets_endpoint_is_public(auth_client: TestClient) -> None:
    presets = auth_client.get("/api/ai/presets").json()
    assert any(item["key"] == "ollama" for item in presets)


# ---------- F7：AI 输出语言跟随界面语言 ----------


def test_summary_prompt_follows_ui_language(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)
    auth_client.patch("/api/settings", json={"language": "en"})

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply("Gist.\n• point one"))
        assert (
            auth_client.post(
                "/api/ai/generate?kind=summary", json={"article_id": article_id}
            ).status_code
            == 200
        )

    body = json.loads(route.calls[0].request.content)
    assert "in English" in body["messages"][0]["content"]
    assert body["messages"][1]["content"].startswith("Title:")
    assert "用简体中文" not in body["messages"][0]["content"]


def test_translation_prompt_follows_ui_language(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)
    auth_client.patch("/api/settings", json={"language": "en"})

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply("Why I came back to RSS"))
        auth_client.post("/api/ai/generate?kind=title_translation", json={"article_id": article_id})

    prompt = json.loads(route.calls[0].request.content)["messages"][0]["content"]
    assert "into English" in prompt


# ---------- 流式转发与失败切换 ----------


@pytest.mark.parametrize(
    ("protocol", "payload", "expected"),
    [
        ("openai", {"choices": [{"delta": {"content": "你好"}}]}, ("你好", 0, 0)),
        ("openai", {"choices": [{"delta": {}}]}, ("", 0, 0)),
        (
            "openai",
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
            ("", 7, 3),
        ),
        ("openai", {"choices": [{"delta": {"content": None}}]}, ("", 0, 0)),
        ("anthropic", {"type": "content_block_delta", "delta": {"text": "hi"}}, ("hi", 0, 0)),
        (
            "anthropic",
            {"type": "message_start", "message": {"usage": {"input_tokens": 11}}},
            ("", 11, 0),
        ),
        ("anthropic", {"type": "message_delta", "usage": {"output_tokens": 4}}, ("", 0, 4)),
        ("anthropic", {"type": "ping"}, ("", 0, 0)),
    ],
)
def test_parse_stream_event(protocol: str, payload: dict, expected: tuple[str, int, int]) -> None:
    assert ai.parse_stream_event(protocol, payload) == expected


@pytest.mark.parametrize(
    ("line", "parsed"),
    [
        ("data: [DONE]", None),
        ("data:", None),
        ("data: 不是 JSON", None),
        ("data: [1, 2]", None),
        ("event: delta", None),
        (": 心跳注释", None),
        ('data: {"a": 1}', {"a": 1}),
    ],
)
def test_data_frame(line: str, parsed: dict | None) -> None:
    assert ai._data_frame(line) == parsed


def test_sse_frame_keeps_data_on_one_line() -> None:
    """换行必须被 JSON 转义：SSE 的 data 只能单行，否则前端会把一帧切成两帧。"""
    frame = ai.sse_frame("delta", {"text": "第一行\n第二行"})
    assert frame.startswith("event: delta\ndata: ")
    assert frame.endswith("\n\n")
    body = frame.split("data: ", 1)[1].strip()
    assert body.count("\n") == 0
    assert json.loads(body) == {"text": "第一行\n第二行"}


def test_stream_endpoint_emits_meta_delta_done(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply())
        response = auth_client.post(
            "/api/ai/generate/stream?kind=summary", json={"article_id": article_id}
        )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    parsed = events(response.text)
    assert [name for name, _ in parsed] == ["meta", "delta", "delta", "done"]
    assert parsed[0][1]["model"] == "gpt-4o-mini"
    assert parsed[0][1]["attempt"] == 1
    done = parsed[-1][1]
    assert done["cached"] is False
    assert (done["tokens_in"], done["tokens_out"]) == (120, 30)
    assert "要点一" in done["content"]
    assert route.call_count == 1

    with SessionLocal() as db:
        assert db.query(AiResult).count() == 1


def test_stream_endpoint_serves_cache_without_upstream(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=openai_reply())
        auth_client.post("/api/ai/generate?kind=summary", json={"article_id": article_id})
        assert route.call_count == 1
        response = auth_client.post(
            "/api/ai/generate/stream?kind=summary", json={"article_id": article_id}
        )

    parsed = events(response.text)
    assert [name for name, _ in parsed] == ["done"]
    assert parsed[0][1]["cached"] is True
    assert route.call_count == 1


def test_rate_limited_provider_retries_then_fails_over(auth_client: TestClient) -> None:
    """账号池网关的典型场景：第一家 429，重试还是 429，然后切第二家成功。"""
    article_id = _seed_article()
    _configure(auth_client)  # OpenAI，position 1
    second = auth_client.post("/api/ai/providers", json={"preset": "deepseek"}).json()
    assert second["enabled"] is True

    rate_limited = httpx.Response(
        429,
        json={"error": {"message": "All available accounts are currently rate-limited."}},
    )
    with respx.mock:
        first = respx.post(OPENAI_URL).mock(return_value=rate_limited)
        backup = respx.post("https://api.deepseek.com/v1/chat/completions").mock(
            return_value=openai_stream(["好", "的"], usage=(5, 2))
        )
        response = auth_client.post(
            "/api/ai/generate/stream?kind=summary", json={"article_id": article_id}
        )

    parsed = events(response.text)
    assert [name for name, _ in parsed] == ["meta", "meta", "meta", "delta", "delta", "done"]
    assert [payload["attempt"] for name, payload in parsed if name == "meta"] == [1, 2, 1]
    assert first.call_count == 2  # 同一家最多两次尝试
    assert backup.call_count == 1
    done = parsed[-1][1]
    assert done["content"] == "好的"
    assert done["model"] == "deepseek-chat"


def test_all_providers_rate_limited_reports_upstream_body(auth_client: TestClient) -> None:
    article_id = _seed_article()
    _configure(auth_client)

    upstream = "All available accounts are currently rate-limited. Please retry later."
    with respx.mock:
        route = respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(429, json={"error": {"message": upstream}})
        )
        response = auth_client.post(
            "/api/ai/generate/stream?kind=summary", json={"article_id": article_id}
        )

    parsed = events(response.text)
    assert parsed[-1][0] == "error"
    detail = str(parsed[-1][1]["detail"])
    assert "限流（429）" in detail
    assert "rate-limited" in detail  # 上游原文保留，好判断到底是谁在限流
    assert route.call_count == 2
    with SessionLocal() as db:
        assert db.query(AiResult).count() == 0


def test_bad_key_is_not_retried(auth_client: TestClient) -> None:
    """401 是配置问题，重试和换家都没用。"""
    article_id = _seed_article()
    _configure(auth_client)

    with respx.mock:
        route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(401, text="bad key"))
        response = auth_client.post(
            "/api/ai/generate/stream?kind=summary", json={"article_id": article_id}
        )

    parsed = events(response.text)
    assert [name for name, _ in parsed] == ["meta", "error"]
    assert "HTTP 401" in str(parsed[-1][1]["detail"])
    assert route.call_count == 1


def test_stream_preflight_failures_are_plain_http(auth_client: TestClient) -> None:
    """响应开始前的失败还能用状态码表达，不必都塞进 SSE。"""
    article_id = _seed_article()

    missing = auth_client.post(
        "/api/ai/generate/stream?kind=summary", json={"article_id": article_id}
    )
    assert missing.status_code == 400
    assert missing.headers["content-type"].startswith("application/json")

    _configure(auth_client)
    with SessionLocal() as db:
        user = db.query(User).order_by(User.created_at).first()
        assert user is not None
        # 用另一个 kind 占掉额度，否则会先命中缓存
        db.add(
            AiResult(
                user_id=user.id,
                article_id=article_id,
                kind="title_translation",
                model="m",
                content="c",
                tokens_in=50,
                tokens_out=0,
            )
        )
        db.commit()
    _set_token_limit(10)

    limited = auth_client.post(
        "/api/ai/generate/stream?kind=summary", json={"article_id": article_id}
    )
    assert limited.status_code == 429
    assert "上限" in limited.json()["detail"]


async def test_generate_does_not_retry_after_first_delta(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已经吐出去的字收不回来：中途失败不再重试，也不切下一家。"""
    _ = auth_client  # 只为了拿到默认用户（auth_client 的 fixture 会建它）
    started: list[str] = []

    async def fake_stream(provider, _messages, state):  # type: ignore[no-untyped-def]
        started.append(provider.label)
        state.text += "前半"
        yield "前半"
        raise ai.AiRetryableError("AI 接口限流（429）：boom")

    monkeypatch.setattr(ai, "stream_completion", fake_stream)

    with SessionLocal() as db:
        user = db.query(User).order_by(User.created_at).first()
        assert user is not None
        feed = make_feed(db, url="https://stream.example.com/feed")
        subscribe(db, user, feed)
        article = add_article(db, feed, guid="g-stream", kind="article")
        providers = [
            _provider(db, user, "OpenAI", position=1),
            _provider(db, user, "DeepSeek", position=2),
        ]

        seen: list[str] = []
        with pytest.raises(ai.AiError) as info:
            async for event in ai.generate(db, user, article, ai.SUMMARY, providers):
                seen.append(event.type)

    assert seen == ["meta", "delta"]
    assert "已生成的内容未保存" in str(info.value)
    assert started == ["OpenAI"]
    with SessionLocal() as db:
        assert db.query(AiResult).count() == 0


def _provider(db: Session, user: User, label: str, position: int) -> AiProvider:
    row = AiProvider(
        user_id=user.id,
        label=label,
        protocol="openai",
        base_url="https://gateway.example.com/v1",
        model=f"{label.lower()}-model",
        position=position,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
