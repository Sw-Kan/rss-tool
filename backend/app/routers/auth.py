"""M1 认证与账户。"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, DbSession
from ..models import User
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import create_token, hash_password, verify_password
from ..services.user_view import SKIP_EMAIL, public_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_cookie(response: Response, user_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.token_cookie_name,
        value=create_token(user_id),
        max_age=settings.token_ttl_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def register(payload: RegisterIn, response: Response, db: DbSession) -> UserOut:
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该邮箱已注册")

    user = User(
        username=payload.username,
        email=email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    from ..deps import user_settings

    user_settings(db, user)
    _issue_cookie(response, user.id)
    return public_user(user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: DbSession) -> UserOut:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    _issue_cookie(response, user.id)
    return public_user(user)


@router.post("/skip", response_model=UserOut)
def skip(response: Response, db: DbSession) -> UserOut:
    """跳过登录：幂等地复用默认用户，不经过密码校验。"""
    user = db.scalar(select(User).where(User.email == SKIP_EMAIL))
    if user is None:
        user = User(
            username="user",
            email=SKIP_EMAIL,
            # 随机密码：默认账号无法通过登录接口进入
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    from ..deps import user_settings

    user_settings(db, user)
    _issue_cookie(response, user.id)
    return public_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(get_settings().token_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return public_user(user)
