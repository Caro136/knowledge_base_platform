"""认证领域服务（T-05）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.exceptions import BizError
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas.auth import LoginIn, LoginOut, UserInfoOut
from app.services.rbac_service import MenuService, collect_user_perms


class AuthService:
    """登录认证与用户信息组装。"""

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> User:
        """校验账号密码，返回用户对象。"""
        user = db.scalar(select(User).where(User.username == username))
        # 账号不存在与密码错误返回同一提示，避免暴露账号是否存在
        if user is None or not verify_password(password, user.password_hash):
            raise BizError(Code.UNAUTHENTICATED, "账号或密码错误")
        if not user.enabled:
            raise BizError(Code.ACCOUNT_DISABLED)
        return user

    @classmethod
    def login(cls, db: Session, payload: LoginIn) -> LoginOut:
        user = cls.authenticate(db, payload.username, payload.password)
        token, expires_in = create_access_token(user.id, extra={"username": user.username})
        return LoginOut(
            token=token,
            expires_in=expires_in,
            user_info=cls.build_user_info(db, user),
        )

    @staticmethod
    def build_user_info(db: Session, user: User) -> UserInfoOut:
        """组装前端所需的用户信息：基础资料 + 角色 + 权限点 + 菜单树。"""
        return UserInfoOut(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            dept_id=user.dept_id,
            dept_name=user.dept.name if user.dept else None,
            is_super=user.is_super,
            roles=[role.code for role in user.roles if role.enabled],
            perms=sorted(collect_user_perms(user)),
            menus=MenuService.user_menu_tree(db, user),
        )
