"""组织与权限相关的 Schema（T-06 ~ T-08）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, InModel

# ---------------------------------------------------------------------------
# 菜单
# ---------------------------------------------------------------------------


class MenuNode(CamelModel):
    """菜单树节点（返回给前端渲染侧边栏 / 权限分配树）。"""

    id: int
    name: str
    type: int = Field(description="0目录 1菜单 2按钮")
    perm: str | None = None
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    order_no: int = 0
    children: list["MenuNode"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 部门
# ---------------------------------------------------------------------------


class DeptNode(CamelModel):
    """部门树节点。"""

    id: int
    name: str
    parent_id: int
    order_no: int = 0
    enabled: bool = True
    children: list["DeptNode"] = Field(default_factory=list)


class DeptIn(InModel):
    """部门新增/编辑入参。"""

    name: str = Field(min_length=1, max_length=64)
    parent_id: int = Field(default=0, ge=0)
    order_no: int = 0
    enabled: bool = True


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------


class UserOut(CamelModel):
    """用户列表项。"""

    id: int
    username: str
    nickname: str | None = None
    dept_id: int | None = None
    dept_name: str | None = None
    role_ids: list[int] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list)
    is_super: bool = False
    enabled: bool = True
    created_at: datetime | None = None


class UserIn(InModel):
    """用户新增/编辑入参。"""

    username: str = Field(min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=6, max_length=64, description="编辑时留空表示不修改密码")
    nickname: str | None = Field(default=None, max_length=64)
    dept_id: int | None = None
    role_ids: list[int] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("username")
    @classmethod
    def _username_pattern(cls, value: str) -> str:
        # 登录名限定为字母/数字/下划线/点/横线，避免空白与特殊字符带来的歧义
        import re

        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", value):
            raise ValueError("账号仅允许字母、数字、下划线、点与横线")
        return value


class UserQuery(InModel):
    """用户列表查询条件。"""

    keyword: str | None = None
    dept_id: int | None = None
    enabled: bool | None = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------


class RoleOut(CamelModel):
    """角色列表项。"""

    id: int
    name: str
    code: str
    remark: str | None = None
    enabled: bool = True
    created_at: datetime | None = None


class RoleIn(InModel):
    """角色新增/编辑入参。"""

    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    remark: str | None = Field(default=None, max_length=255)
    enabled: bool = True

    @field_validator("code")
    @classmethod
    def _code_pattern(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_\-]*", value):
            raise ValueError("角色编码需以字母开头，仅允许字母、数字、下划线、横线")
        return value


class RoleMenuIds(CamelModel):
    """角色已分配的菜单 ID 集合。"""

    menu_ids: list[int] = Field(default_factory=list)


class AssignMenusIn(InModel):
    """角色权限分配入参（覆盖式）。"""

    menu_ids: list[int] = Field(default_factory=list)
