"""F4 代理：配置接口、no_proxy 匹配、按模式构造客户端。"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.services import proxy


def test_defaults_to_system(auth_client: TestClient) -> None:
    assert auth_client.get("/api/proxy").json() == {
        "mode": "system",
        "url": "",
        "no_proxy": "",
    }


def test_patch_roundtrip(auth_client: TestClient) -> None:
    body = auth_client.patch(
        "/api/proxy",
        json={"mode": "http", "url": "127.0.0.1:7890", "no_proxy": "localhost, *.internal"},
    ).json()
    assert body == {"mode": "http", "url": "127.0.0.1:7890", "no_proxy": "localhost, *.internal"}
    assert auth_client.get("/api/proxy").json() == body


def test_switching_back_to_system_clears_url(auth_client: TestClient) -> None:
    auth_client.patch("/api/proxy", json={"mode": "custom", "url": "socks5://10.0.0.8:1080"})
    body = auth_client.patch("/api/proxy", json={"mode": "system"}).json()
    assert body["mode"] == "system"
    assert body["url"] == ""


@pytest.mark.parametrize("mode", ["direct", "socks", "proxy"])
def test_invalid_mode_is_rejected(auth_client: TestClient, mode: str) -> None:
    assert auth_client.patch("/api/proxy", json={"mode": mode}).status_code == 422


def test_proxy_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/proxy").status_code == 401
    assert client.patch("/api/proxy", json={}).status_code == 401
    assert client.post("/api/proxy/test").status_code == 401


# ---------- no_proxy 匹配 ----------


@pytest.mark.parametrize(
    ("host", "pattern", "expected"),
    [
        ("example.com", "example.com", True),
        ("api.example.com", "example.com", True),
        ("api.example.com", ".example.com", True),
        ("api.example.com", "*.example.com", True),
        ("notexample.com", "example.com", False),
        ("example.com", "other.com", False),
        ("anything", "*", True),
    ],
)
def test_host_matches(host: str, pattern: str, expected: bool) -> None:
    assert proxy.host_matches(host, proxy.parse_no_proxy(pattern)) is expected


@pytest.mark.parametrize(
    ("address", "pattern", "expected"),
    [("192.168.0.5", "192.168.0.0/16", True), ("10.1.2.3", "192.168.0.0/16", False)],
)
def test_address_matches_cidr(address: str, pattern: str, expected: bool) -> None:
    assert proxy.address_matches([address], proxy.parse_no_proxy(pattern)) is expected


def test_no_proxy_accepts_semicolons_and_blanks() -> None:
    assert proxy.parse_no_proxy(" a.com ;; b.com ,, ") == ["a.com", "b.com"]


def test_bypass_combines_host_and_cidr() -> None:
    spec = proxy.ProxySpec(mode="custom", url="x", patterns=["local", "10.0.0.0/8"])
    assert proxy.bypass(spec, "local", []) is True
    assert proxy.bypass(spec, "example.com", ["10.1.1.1"]) is True
    assert proxy.bypass(spec, "example.com", ["1.2.3.4"]) is False


# ---------- 客户端构造 ----------


def test_system_mode_follows_env() -> None:
    assert proxy.client_kwargs(proxy.ProxySpec(mode="system"), "https://x.com") == {
        "trust_env": True
    }


def test_system_mode_respects_no_proxy() -> None:
    spec = proxy.ProxySpec(mode="system", patterns=["x.com"])
    assert proxy.client_kwargs(spec, "https://x.com") == {"trust_env": False}


def test_custom_mode_applies_to_everything() -> None:
    spec = proxy.ProxySpec(mode="custom", url="socks5://10.0.0.8:1080")
    assert proxy.client_kwargs(spec, "https://x.com")["proxy"] == "socks5://10.0.0.8:1080"
    assert proxy.client_kwargs(spec, "http://x.com")["proxy"] == "socks5://10.0.0.8:1080"


def test_http_mode_only_proxies_http() -> None:
    spec = proxy.ProxySpec(mode="http", url="127.0.0.1:7890")
    assert proxy.client_kwargs(spec, "http://x.com").get("proxy") == "127.0.0.1:7890"
    assert "proxy" not in proxy.client_kwargs(spec, "https://x.com")


def test_https_mode_only_proxies_https() -> None:
    spec = proxy.ProxySpec(mode="https", url="127.0.0.1:7890")
    assert proxy.client_kwargs(spec, "https://x.com").get("proxy") == "127.0.0.1:7890"
    assert "proxy" not in proxy.client_kwargs(spec, "http://x.com")


def test_empty_url_means_direct() -> None:
    spec = proxy.ProxySpec(mode="custom", url="")
    assert proxy.client_kwargs(spec, "https://x.com") == {"trust_env": False}
    assert spec.configured is False


@pytest.mark.asyncio
async def test_build_client_survives_unusable_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境里有 httpx 不认识的代理 scheme 时，降级直连而不是让所有抓取都炸掉。"""
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897")
    monkeypatch.setenv("all_proxy", "socks://127.0.0.1:7897")

    with respx.mock:
        respx.get("https://example.com/feed").mock(return_value=httpx.Response(200, text="ok"))
        async with proxy.build_client(
            proxy.ProxySpec(mode="system"), "https://example.com/feed"
        ) as client:
            response = await client.get("https://example.com/feed")

    assert response.status_code == 200


def test_describe() -> None:
    assert proxy.describe(proxy.ProxySpec(mode="system")) == "跟随系统"
    assert proxy.describe(proxy.ProxySpec(mode="custom", url="a:1")) == "a:1"
    assert "直连" in proxy.describe(proxy.ProxySpec(mode="http", url=""))


def test_describe_reports_no_proxy_bypass() -> None:
    """命中 NO_PROXY 时不能还写着「经由 <代理>」——这条文案就是告诉用户走了哪条路。"""
    spec = proxy.ProxySpec(mode="custom", url="127.0.0.1:7890", patterns=["cloudflare.com"])
    assert (
        proxy.describe(spec, "https://www.cloudflare.com/cdn-cgi/trace") == "直连（NO_PROXY 命中）"
    )
    assert proxy.describe(spec, "https://example.com/") == "127.0.0.1:7890"


def test_proxy_test_message_names_the_bypass(auth_client: TestClient) -> None:
    auth_client.patch(
        "/api/proxy",
        json={"mode": "custom", "url": "http://127.0.0.1:9", "no_proxy": "cloudflare.com"},
    )
    with respx.mock:
        respx.get("https://www.cloudflare.com/cdn-cgi/trace").mock(
            return_value=httpx.Response(200, text="ok")
        )
        body = auth_client.post("/api/proxy/test").json()

    assert body["ok"] is True
    assert "NO_PROXY" in body["message"]
    assert "127.0.0.1:9" not in body["message"]


# ---------- 测试连接 ----------


def test_proxy_test_reports_latency(auth_client: TestClient) -> None:
    with respx.mock:
        respx.get("https://www.cloudflare.com/cdn-cgi/trace").mock(
            return_value=httpx.Response(200, text="fl=1\nip=1.2.3.4")
        )
        body = auth_client.post("/api/proxy/test").json()

    assert body["ok"] is True
    assert "连接正常" in body["message"]
    assert isinstance(body["latency_ms"], int)


def test_proxy_test_requires_url_for_non_system_mode(auth_client: TestClient) -> None:
    auth_client.patch("/api/proxy", json={"mode": "custom"})
    body = auth_client.post("/api/proxy/test").json()
    assert body["ok"] is False
    assert "代理地址" in body["message"]


def test_proxy_test_reports_upstream_error(auth_client: TestClient) -> None:
    with respx.mock:
        respx.get("https://www.cloudflare.com/cdn-cgi/trace").mock(return_value=httpx.Response(502))
        body = auth_client.post("/api/proxy/test").json()

    assert body["ok"] is False
    assert "502" in body["message"]
