"""F4 代理：两模式配置、按协议选地址、no_proxy 匹配、测试连接。"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.services import proxy

CUSTOM = {
    "mode": "custom",
    "http_url": "http://127.0.0.1:7890",
    "https_url": "http://127.0.0.1:7891",
    "socks5_url": "socks5://10.0.0.8:1080",
    "no_proxy": "localhost, *.internal",
}


def test_defaults_to_system(auth_client: TestClient) -> None:
    assert auth_client.get("/api/proxy").json() == {
        "mode": "system",
        "http_url": "",
        "https_url": "",
        "socks5_url": "",
        "no_proxy": "",
    }


def test_patch_roundtrip(auth_client: TestClient) -> None:
    assert auth_client.patch("/api/proxy", json=CUSTOM).json() == CUSTOM
    assert auth_client.get("/api/proxy").json() == CUSTOM


def test_switching_to_system_keeps_custom_urls(auth_client: TestClient) -> None:
    """切回系统代理不该把自定义地址抹掉，切回来还要在。"""
    auth_client.patch("/api/proxy", json=CUSTOM)
    body = auth_client.patch("/api/proxy", json={"mode": "system"}).json()

    assert body["mode"] == "system"
    assert body["http_url"] == "http://127.0.0.1:7890"
    assert body["socks5_url"] == "socks5://10.0.0.8:1080"


@pytest.mark.parametrize("mode", ["direct", "socks", "http", "https"])
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
    spec = proxy.ProxySpec(mode="custom", socks5_url="x", patterns=["local", "10.0.0.0/8"])
    assert proxy.bypass(spec, "local", []) is True
    assert proxy.bypass(spec, "example.com", ["10.1.1.1"]) is True
    assert proxy.bypass(spec, "example.com", ["1.2.3.4"]) is False


# ---------- 选地址 ----------


def test_proxy_for_picks_by_scheme() -> None:
    spec = proxy.ProxySpec(mode="custom", http_url="http://h:1", https_url="http://s:2")
    assert proxy.proxy_for(spec, "http") == "http://h:1"
    assert proxy.proxy_for(spec, "https") == "http://s:2"


def test_socks5_acts_as_fallback_for_both_schemes() -> None:
    spec = proxy.ProxySpec(mode="custom", socks5_url="socks5://x:1080")
    assert proxy.proxy_for(spec, "http") == "socks5://x:1080"
    assert proxy.proxy_for(spec, "https") == "socks5://x:1080"


def test_system_mode_never_returns_a_proxy() -> None:
    spec = proxy.ProxySpec(mode="system", http_url="http://h:1")
    assert proxy.proxy_for(spec, "http") == ""


def test_configured_flag() -> None:
    assert proxy.ProxySpec(mode="custom").configured is False
    assert proxy.ProxySpec(mode="custom", socks5_url="x").configured is True
    assert proxy.ProxySpec(mode="system", http_url="x").configured is False


# ---------- 客户端构造 ----------


def test_system_mode_follows_env() -> None:
    assert proxy.client_kwargs(proxy.ProxySpec(mode="system"), "https://x.com") == {
        "trust_env": True
    }


def test_system_mode_respects_no_proxy() -> None:
    spec = proxy.ProxySpec(mode="system", patterns=["x.com"])
    assert proxy.client_kwargs(spec, "https://x.com") == {"trust_env": False}


def test_custom_mode_uses_scheme_specific_proxy() -> None:
    spec = proxy.ProxySpec(mode="custom", http_url="http://h:1", https_url="http://s:2")
    assert proxy.client_kwargs(spec, "http://x.com")["proxy"] == "http://h:1"
    assert proxy.client_kwargs(spec, "https://x.com")["proxy"] == "http://s:2"


def test_custom_mode_without_any_url_is_direct() -> None:
    assert proxy.client_kwargs(proxy.ProxySpec(mode="custom"), "https://x.com") == {
        "trust_env": False
    }


def test_no_proxy_wins_over_custom() -> None:
    spec = proxy.ProxySpec(mode="custom", https_url="http://h:1", patterns=["cloudflare.com"])
    assert proxy.client_kwargs(spec, "https://www.cloudflare.com/x") == {"trust_env": False}


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


# ---------- 描述 ----------


def test_describe_system() -> None:
    spec = proxy.ProxySpec(mode="system")
    assert proxy.describe(spec) == "跟随系统"
    assert proxy.describe(spec, "https://x.com") == "跟随系统"


def test_describe_reports_no_proxy_bypass() -> None:
    """命中 NO_PROXY 时不能还写着「经由 <代理>」——这条文案就是告诉用户走了哪条路。"""
    spec = proxy.ProxySpec(mode="custom", https_url="127.0.0.1:7890", patterns=["cloudflare.com"])
    assert (
        proxy.describe(spec, "https://www.cloudflare.com/cdn-cgi/trace") == "直连（NO_PROXY 命中）"
    )
    assert proxy.describe(spec, "https://example.com/") == "127.0.0.1:7890"


def test_describe_without_address() -> None:
    assert "直连" in proxy.describe(proxy.ProxySpec(mode="custom"), "https://x.com")


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


def test_proxy_test_requires_an_address_in_custom_mode(auth_client: TestClient) -> None:
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


def test_proxy_test_message_names_the_bypass(auth_client: TestClient) -> None:
    auth_client.patch(
        "/api/proxy",
        json={"mode": "custom", "https_url": "http://127.0.0.1:9", "no_proxy": "cloudflare.com"},
    )
    with respx.mock:
        respx.get("https://www.cloudflare.com/cdn-cgi/trace").mock(
            return_value=httpx.Response(200, text="ok")
        )
        body = auth_client.post("/api/proxy/test").json()

    assert body["ok"] is True
    assert "NO_PROXY" in body["message"]
    assert "127.0.0.1:9" not in body["message"]
