"""M9 个人资料与头像、M10 数据导出。"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import User
from ..schemas import UserOut, UserPatch
from ..services.user_export import export_user
from ..services.user_view import public_user

router = APIRouter(prefix="/api/users", tags=["users"])

MAX_AVATAR_BYTES = 3 * 1024 * 1024
AVATAR_SIZE = 256


@router.patch("/me", response_model=UserOut)
def patch_me(payload: UserPatch, user: CurrentUser, db: DbSession) -> UserOut:
    if payload.username is not None:
        username = payload.username.strip()
        if not username:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名不能为空")
        user.username = username
    if payload.avatar_type is not None:
        if payload.avatar_type == "image" and not user.avatar_path:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="尚未上传头像图片")
        user.avatar_type = payload.avatar_type
    if payload.avatar_color is not None:
        user.avatar_color = payload.avatar_color.upper()
    db.commit()
    db.refresh(user)
    return public_user(user)


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(user: CurrentUser, db: DbSession, file: UploadFile = File(...)) -> UserOut:
    raw = await file.read(MAX_AVATAR_BYTES + 1)
    if len(raw) > MAX_AVATAR_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="文件不能超过 3MB")

    filename = _save_avatar(raw, user.id)
    user.avatar_path = filename
    user.avatar_type = "image"
    db.commit()
    db.refresh(user)
    return public_user(user)


@router.delete("/me/avatar", response_model=UserOut)
def delete_avatar(user: CurrentUser, db: DbSession) -> UserOut:
    stored = _avatar_file(user)
    if stored and stored.exists():
        stored.unlink()
    user.avatar_path = None
    user.avatar_type = "letter"
    db.commit()
    db.refresh(user)
    return public_user(user)


@router.get("/avatar/{filename}")
def get_avatar(filename: str, db: DbSession) -> FileResponse:
    """头像文件。仅允许读取属于某个用户的文件名，避免路径穿越。"""
    if "/" in filename or ".." in filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    owner = db.scalar(select(User).where(User.avatar_path == filename))
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    path = get_settings().uploads_path / filename
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")
    return FileResponse(path, media_type="image/png")


@router.get("/me/export")
def export_data(user: CurrentUser, db: DbSession) -> Response:
    payload = export_user(db, user)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="rss-tool-export-{stamp}.json"',
        },
    )


def _avatar_file(user: User) -> Path | None:
    if not user.avatar_path:
        return None
    return get_settings().uploads_path / user.avatar_path


def _save_avatar(raw: bytes, user_id: str) -> str:
    """用 Pillow 校验真实格式（不信任扩展名 / content-type），统一转 PNG。"""
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG"):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="只支持 png / jpg 图片")
            converted = image.convert("RGBA")
            converted.thumbnail((AVATAR_SIZE, AVATAR_SIZE))
            canvas = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (0, 0, 0, 0))
            canvas.paste(
                converted,
                ((AVATAR_SIZE - converted.width) // 2, (AVATAR_SIZE - converted.height) // 2),
            )
            settings = get_settings()
            settings.ensure_dirs()
            filename = f"{user_id}.png"
            canvas.save(settings.uploads_path / filename, format="PNG", optimize=True)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="无法识别的图片文件") from exc
    return filename
