"""认证相关 Schema（T-05）。"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel, InModel
from app.schemas.rbac import MenuNode


class LoginIn(InModel):
    """登录入参。"""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserInfoOut(CamelModel):
    """当前用户信息（登录与 /auth/me 共用）。

    前端 store/user.js 依赖该结构：
    - perms 用于按钮级鉴权（hasPerm）
    - menus 用于渲染侧边栏与 route 守卫的落点计算
    """

    id: int
    username: str
    nickname: str | None = None
    dept_id: int | None = None
    dept_name: str | None = None
    is_super: bool = False
    roles: list[str] = Field(default_factory=list, description="角色编码列表")
    perms: list[str] = Field(default_factory=list, description="操作权限点；超管为 ['*']")
    menus: list[MenuNode] = Field(default_factory=list, description="按权限裁剪后的菜单树（不含按钮）")


class LoginOut(CamelModel):
    """登录响应。"""

    token: str
    expires_in: int = Field(description="凭证有效期（秒）")
    user_info: UserInfoOut
