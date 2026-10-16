"""认证接口（T-05）。

- ``POST /api/auth/login`` 登录并签发 JWT
- ``GET  /api/auth/me``    当前用户信息（含权限点与菜单树）
- ``POST /api/auth/logout`` 语义化登出（JWT 无状态，由前端清除凭证）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas.auth import LoginIn
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", summary="登录")
def login(payload: LoginIn, db: Session = Depends(get_db)) -> dict:
    return ok(AuthService.login(db, payload))


@router.get("/me", summary="当前用户信息")
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ok(AuthService.build_user_info(db, user))


@router.post("/logout", summary="登出")
def logout(_: User = Depends(get_current_user)) -> dict:
    # 无状态 JWT：服务端不维护会话，此处仅作为语义标记，由前端清除本地凭证
    return ok(message="已退出登录")
