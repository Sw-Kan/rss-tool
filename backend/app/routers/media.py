"""F6 媒体缓存接口。

路径是 `GET /api/media?url=<urlencoded>` 而不是路线图里写的 `/api/media/{hash}`：
浏览器端没法同步算 sha256，而缓存键本来就由服务端从 url 推导，放路径里没有额外价值。
响应带 `private, immutable` 的长缓存，浏览器侧与磁盘侧同时省流量。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from ..deps import CurrentUser, DbSession
from ..services import media

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("", response_model=None)
async def get_media(
    user: CurrentUser,
    db: DbSession,
    url: str = Query(min_length=4, max_length=2000),
) -> Response:
    _ = user
    if not media.is_cacheable_url(url):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="只支持 http / https 图片地址")

    result = media.lookup(db, url)
    if result.kind == "miss":
        result = await media.fetch_and_store(db, url)

    if result.path is not None and result.path.exists():
        return _file_response(result.path, result.content_type)

    # 拉不到就交给浏览器自己试：服务端被墙/被防盗链拦住而浏览器能访问的情况很常见
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def _file_response(path, content_type: str) -> FileResponse:  # noqa: ANN001
    headers = {
        # 键是内容寻址的，可以长缓存；private 避免被共享缓存留存
        "Cache-Control": "private, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }
    return FileResponse(
        path, media_type=content_type or "application/octet-stream", headers=headers
    )
