"""M3 HTTP 抓取：SSRF 防护、条件请求、体积与错误处理。全程不打真实网络。"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.services import feed_fetch, proxy
from app.services.feed_fetch import FetchError

FEED_URL = "https://feeds.example.com/rss.xml"
PROXY_URL = "http://host.docker.internal:7897"
PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def _no_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """清掉环境里的代理变量，不然尝试次数会顺到宿主机的代理设置上。"""
    for name in PROXY_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


def _spy_clients(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """记录每次尝试的构造参数。

    测试里把每一条路都实例化成直连客户端：httpx 带代理时会换成 AsyncHTTPProxy，
    respx 拦不到（会打真实网络）。这里要看的是「尝试顺序」，代理参数本身由
    proxy.client_kwargs 自己的用例覆盖，所以只把它记下来断言。
    """
    seen: list[dict] = []
    real = proxy.build_client

    def spy(spec, url, addresses=None, *, direct=False, **kwargs):  # noqa: ANN001, ANN202
        seen.append(
            {
                "direct": direct,
                "timeout": kwargs.get("timeout"),
                "chosen": {"trust_env": False}
                if direct
                else proxy.client_kwargs(spec, url, addresses),
            }
        )
        return real(proxy.ProxySpec(mode="custom"), url, addresses, direct=True, **kwargs)

    monkeypatch.setattr(feed_fetch.proxy, "build_client", spy)
    return seen


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/feed",
        "http://127.0.0.1/feed",
        "http://localhost/feed",
        "http://10.1.2.3/feed",
        "http://192.168.1.1/feed",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/feed",
        "http://0.0.0.0/feed",
    ],
)
def test_ssrf_blocked(url: str) -> None:
    with pytest.raises(FetchError):
        feed_fetch.check_url_allowed(url)


def test_ssrf_redirect_to_internal_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """首跳放行、重定向到内网时必须被拦下，且不再发出第二个请求。"""
    calls: list[str] = []

    def fake_check(url: str) -> None:
        calls.append(url)
        if "127.0.0.1" in url or "169.254" in url:
            raise FetchError("出于安全考虑，不允许抓取内网或本机地址")

    monkeypatch.setattr(feed_fetch, "check_url_allowed", fake_check)

    with respx.mock:
        respx.get(FEED_URL).mock(
            return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        )
        route = respx.get("http://169.254.169.254/")

        with pytest.raises(FetchError):
            import asyncio

            asyncio.run(feed_fetch.fetch(FEED_URL))

    assert route.call_count == 0
    assert calls == [FEED_URL, "http://169.254.169.254/"]


def _allow_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feed_fetch, "check_url_allowed", lambda url: None)


@pytest.mark.asyncio
async def test_fetch_returns_body_and_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    with respx.mock:
        respx.get(FEED_URL).mock(
            return_value=httpx.Response(
                200, content=b"<rss/>", headers={"etag": 'W/"1"', "last-modified": "yesterday"}
            )
        )
        result = await feed_fetch.fetch(FEED_URL)

    assert result.content == b"<rss/>"
    assert result.etag == 'W/"1"'
    assert result.modified == "yesterday"
    assert result.not_modified is False


@pytest.mark.asyncio
async def test_fetch_sends_conditional_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    with respx.mock:
        route = respx.get(FEED_URL).mock(return_value=httpx.Response(304))
        result = await feed_fetch.fetch(FEED_URL, etag='W/"1"', modified="yesterday")

    sent = route.calls[0].request.headers
    assert sent["if-none-match"] == 'W/"1"'
    assert sent["if-modified-since"] == "yesterday"
    assert result.not_modified is True


@pytest.mark.asyncio
async def test_fetch_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    monkeypatch.setattr(feed_fetch.get_settings(), "fetch_max_bytes", 16)
    with respx.mock:
        respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=b"x" * 64))
        with pytest.raises(FetchError, match="过大"):
            await feed_fetch.fetch(FEED_URL)


@pytest.mark.asyncio
async def test_fetch_reports_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    with respx.mock:
        respx.get(FEED_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(FetchError, match="HTTP 500"):
            await feed_fetch.fetch(FEED_URL)


@pytest.mark.asyncio
async def test_fetch_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    with respx.mock:
        respx.get(FEED_URL).mock(side_effect=httpx.ConnectTimeout("boom"))
        with pytest.raises(FetchError, match="超时"):
            await feed_fetch.fetch(FEED_URL)


@pytest.mark.asyncio
async def test_fetch_follows_up_to_five_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    with respx.mock:
        for index in range(6):
            respx.get(f"https://feeds.example.com/{index}").mock(
                return_value=httpx.Response(302, headers={"location": f"/{index + 1}"})
            )
        with pytest.raises(FetchError, match="重定向次数过多"):
            await feed_fetch.fetch("https://feeds.example.com/0")


# ---------- 直连优先，连不上再走代理 ----------


def _custom_proxy() -> proxy.ProxySpec:
    return proxy.ProxySpec(mode="custom", https_url=PROXY_URL)


@pytest.mark.asyncio
async def test_custom_proxy_tries_direct_first_then_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clash 没起来时国内源要能活下来：先直连，连不上才把请求交给代理。"""
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    seen = _spy_clients(monkeypatch)
    with respx.mock:
        route = respx.get(FEED_URL).mock(
            side_effect=[
                httpx.ConnectError("All connection attempts failed"),
                httpx.Response(200, content=b"<rss/>"),
            ]
        )
        result = await feed_fetch.fetch(FEED_URL, proxy_spec=_custom_proxy())

    assert result.content == b"<rss/>"
    assert route.call_count == 2
    assert seen[0]["direct"] is True
    assert seen[0]["chosen"] == {"trust_env": False}
    assert seen[1]["chosen"] == {"trust_env": False, "proxy": PROXY_URL}


@pytest.mark.asyncio
async def test_direct_hop_gets_a_short_connect_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """被 DNS 污染 / 黑洞的源要尽快回退，不能每跳都等满 fetch_timeout_seconds。"""
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    seen = _spy_clients(monkeypatch)
    with respx.mock:
        respx.get(FEED_URL).mock(
            side_effect=[httpx.ConnectError("boom"), httpx.Response(200, content=b"<rss/>")]
        )
        await feed_fetch.fetch(FEED_URL, proxy_spec=_custom_proxy())

    assert seen[0]["timeout"].connect == 5.0
    assert seen[1]["timeout"] == feed_fetch.get_settings().fetch_timeout_seconds


@pytest.mark.asyncio
async def test_custom_proxy_without_address_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """自定义模式没填地址就是纯直连，失败直接报错，并提示去配代理。"""
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    with respx.mock:
        route = respx.get(FEED_URL).mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(FetchError, match="设置 → 代理"):
            await feed_fetch.fetch(FEED_URL, proxy_spec=proxy.ProxySpec(mode="custom"))

    assert route.call_count == 1


@pytest.mark.asyncio
async def test_no_proxy_bypass_never_tries_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """NO_PROXY 命中的目标只直连——用户说了别走代理，替他回退是反着来。"""
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    spec = proxy.ProxySpec(mode="custom", https_url=PROXY_URL, patterns=["feeds.example.com"])
    with respx.mock:
        route = respx.get(FEED_URL).mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(FetchError, match="NO_PROXY 命中"):
            await feed_fetch.fetch(FEED_URL, proxy_spec=spec)

    assert route.call_count == 1


@pytest.mark.asyncio
async def test_read_timeout_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """连上了只是慢：换路没意义，不该再等一个超时。"""
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    seen = _spy_clients(monkeypatch)
    with respx.mock:
        route = respx.get(FEED_URL).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(FetchError, match="超时"):
            await feed_fetch.fetch(FEED_URL, proxy_spec=_custom_proxy())

    assert route.call_count == 1
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_system_mode_falls_back_to_the_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境里配了代理时，system 模式也是直连优先。"""
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    seen = _spy_clients(monkeypatch)
    with respx.mock:
        respx.get(FEED_URL).mock(
            side_effect=[httpx.ConnectError("boom"), httpx.Response(200, content=b"<rss/>")]
        )
        result = await feed_fetch.fetch(FEED_URL)

    assert result.content == b"<rss/>"
    assert [item["direct"] for item in seen] == [True, False]
    assert seen[1]["chosen"] == {"trust_env": True}


@pytest.mark.asyncio
async def test_system_mode_does_not_retry_without_env_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """环境里没有代理，就没有第二条路可试，不要白试一遍。"""
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    seen = _spy_clients(monkeypatch)
    with respx.mock:
        route = respx.get(FEED_URL).mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(FetchError, match="设置 → 代理"):
            await feed_fetch.fetch(FEED_URL)

    assert route.call_count == 1
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_both_paths_failing_names_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow_all(monkeypatch)
    _no_env_proxy(monkeypatch)
    with respx.mock:
        respx.get(FEED_URL).mock(side_effect=httpx.ConnectError("All connection attempts failed"))
        with pytest.raises(FetchError, match="直连与代理都不通"):
            await feed_fetch.fetch(FEED_URL, proxy_spec=_custom_proxy())
