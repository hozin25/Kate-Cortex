"""多用户认证端点：注册（邀请码）/ 登录 / 登出 / 会话查询。

仅在多用户模式装配（main.py），端点对会话中间件豁免——login/register/me
自己解析凭据。会话 token 经 HttpOnly cookie 下发（kate_session）。
"""

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response

from ..auth import (
    SESSION_COOKIE,
    SESSION_TTL_DAYS,
    UsersStore,
    check_invite_code,
    validate_password,
    validate_username,
)
from ..models import AuthIn, AuthRegisterIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

_SESSION_MAX_AGE_S = SESSION_TTL_DAYS * 86400


def _store(request: Request) -> UsersStore:
    store = getattr(request.app.state, "users_store", None)
    if store is None:
        # 单用户形态（桌面/dev/Vercel 试用）没有账号体系，给出干净 404 而非 500
        raise HTTPException(status_code=404, detail="当前部署为单用户模式，未启用账号体系")
    return store


def _set_session_cookie(response: Response, token: str, expires: datetime) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=_SESSION_MAX_AGE_S,
        expires=expires,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("KATE_COOKIE_SECURE") == "1",
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: AuthRegisterIn, response: Response, request: Request):
    error = check_invite_code(payload.invite_code)
    if error:
        raise HTTPException(status_code=403, detail=error)
    error = validate_username(payload.username.strip()) or validate_password(
        payload.password
    )
    if error:
        raise HTTPException(status_code=422, detail=error)
    try:
        user = _store(request).register(payload.username.strip(), payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    token, expires = _store(request).create_session(user["id"])
    _set_session_cookie(response, token, expires)
    return UserOut(**dict(user))


@router.post("/login", response_model=UserOut)
def login(payload: AuthIn, response: Response, request: Request):
    user = _store(request).verify_login(payload.username.strip(), payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, expires = _store(request).create_session(user["id"])
    _set_session_cookie(response, token, expires)
    return UserOut(**dict(user))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _store(request).delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    user = _store(request).resolve_session(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return UserOut(**dict(user))
