"""M3 HTTP 抓取：SSRF 防护、条件请求、体积与错误处理。全程不打真实网络。"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.services import feed_fetch
from app.services.feed_fetch import FetchError

FEED_URL = "https://feeds.example.com/rss.xml"


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
