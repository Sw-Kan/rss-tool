"""FastAPI 依赖：当前用户、设置行。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import User, UserSettings
from .security import decode_token

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def current_user(
    request: Request,
    db: DbSession,
    rss_token: Annotated[str | None, Cookie()] = None,
) -> User:
    token = rss_token or _bearer(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return user


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


CurrentUser = Annotated[User, Depends(current_user)]


def user_settings(db: Session, user: User) -> UserSettings:
    """取用户设置行，不存在则按默认值创建。"""
    row = db.get(UserSettings, user.id)
    if row is None:
        row = UserSettings(user_id=user.id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_user_settings(db: DbSession, user: CurrentUser) -> UserSettings:
    return user_settings(db, user)


SettingsRow = Annotated[UserSettings, Depends(get_user_settings)]
