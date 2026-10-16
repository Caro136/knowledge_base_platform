"""FastAPI 依赖注入：当前用户、操作权限校验。

权限模型（SPEC §8 安全条款）：
- 操作权限控制"谁能用哪个功能"，由角色绑定的菜单/按钮权限点决定；
- 超管拥有通配权限 ``*``；
- 前端指令只做展示层收敛，**以后端校验为准**。
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.exceptions import BizError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User


def _extract_token(authorization: str | None) -> str | None:
    """从 Authorization 头中取出 token，容忍带/不带 Bearer 前缀。"""
    if not authorization:
        return None
    value = authorization.strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value or None


def get_current_user(
    authorization: str | None = Header(default=None, description="Bearer <token>"),
    db: Session = Depends(get_db),
) -> User:
    """解析登录态并返回当前用户。未登录 / 凭证失效 / 账号禁用均抛业务异常。"""
    token = _extract_token(authorization)
    if not token:
        raise BizError(Code.UNAUTHENTICATED)

    payload = decode_access_token(token)
    if not payload:
        raise BizError(Code.UNAUTHENTICATED)

    subject = payload.get("sub")
    if subject is None or not str(subject).isdigit():
        raise BizError(Code.UNAUTHENTICATED)

    user = db.get(User, int(subject))
    if user is None:
        # 用户已被删除但 token 仍在有效期内
        raise BizError(Code.UNAUTHENTICATED)
    if not user.enabled:
        raise BizError(Code.ACCOUNT_DISABLED)
    return user


def get_user_perms(user: User = Depends(get_current_user)) -> set[str]:
    """当前用户的操作权限点集合（超管为 {'*'}）。"""
    from app.services.rbac_service import collect_user_perms

    return collect_user_perms(user)


def require_permission(perm: str) -> Callable[..., User]:
    """生成"必须具备指定操作权限"的依赖。"""

    def _dependency(
        user: User = Depends(get_current_user),
        perms: set[str] = Depends(get_user_perms),
    ) -> User:
        if "*" in perms or perm in perms:
            return user
        raise BizError(Code.NO_OPERATION_PERMISSION, f"缺少操作权限：{perm}")

    return _dependency


def require_any_permission(*perms: str) -> Callable[..., User]:
    """生成"命中任一操作权限即可"的依赖。

    用于被多个页面复用的只读参考接口（例如部门树/角色列表既供系统管理页，
    也供知识单元的数据权限配置弹窗使用）。
    """

    def _dependency(
        user: User = Depends(get_current_user),
        user_perms: set[str] = Depends(get_user_perms),
    ) -> User:
        if "*" in user_perms or any(perm in user_perms for perm in perms):
            return user
        raise BizError(Code.NO_OPERATION_PERMISSION, f"缺少操作权限：{' / '.join(perms)}")

    return _dependency


def require_super(user: User = Depends(get_current_user)) -> User:
    """仅超级管理员可访问。"""
    if not user.is_super:
        raise BizError(Code.NO_OPERATION_PERMISSION, "该操作仅限超级管理员")
    return user
