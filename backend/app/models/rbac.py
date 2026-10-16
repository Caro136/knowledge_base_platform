"""组织与权限模型（SPEC §5.2 权限域）。

- 用户 → 部门：多对一
- 用户 ↔ 角色、角色 ↔ 菜单：多对多
- 菜单 type：0=目录 1=菜单 2=按钮，按钮级节点携带 ``perm`` 权限标识
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

#: 菜单类型
MENU_TYPE_DIR = 0
MENU_TYPE_MENU = 1
MENU_TYPE_BUTTON = 2

#: 用户-角色 关联表
sys_user_role = Table(
    "sys_user_role",
    Base.metadata,
    Column("user_id", BigInteger, ForeignKey("sys_user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", BigInteger, ForeignKey("sys_role.id", ondelete="CASCADE"), primary_key=True),
    comment="用户角色关联",
)

#: 角色-菜单 关联表
sys_role_menu = Table(
    "sys_role_menu",
    Base.metadata,
    Column("role_id", BigInteger, ForeignKey("sys_role.id", ondelete="CASCADE"), primary_key=True),
    Column("menu_id", BigInteger, ForeignKey("sys_menu.id", ondelete="CASCADE"), primary_key=True),
    comment="角色菜单权限关联",
)


class Dept(Base, TimestampMixin):
    """部门（树形结构）。"""

    __tablename__ = "sys_dept"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="部门名称")
    parent_id: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, index=True, comment="上级部门ID，0 表示根"
    )
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="排序号")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")

    users: Mapped[list["User"]] = relationship(back_populates="dept")


class Role(Base, TimestampMixin):
    """角色。"""

    __tablename__ = "sys_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="角色名称")
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="角色编码")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")

    users: Mapped[list["User"]] = relationship(secondary=sys_user_role, back_populates="roles")
    menus: Mapped[list["Menu"]] = relationship(
        secondary=sys_role_menu, back_populates="roles", lazy="selectin"
    )


class Menu(Base, TimestampMixin):
    """菜单 / 权限点。"""

    __tablename__ = "sys_menu"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="名称")
    parent_id: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, index=True, comment="上级ID，0 表示根"
    )
    type: Mapped[int] = mapped_column(
        Integer, default=MENU_TYPE_MENU, nullable=False, comment="类型：0目录 1菜单 2按钮"
    )
    perm: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True, comment="权限标识，如 knowledge:import"
    )
    path: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="前端路由路径")
    component: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="前端组件路径")
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="图标")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="排序号")
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否可见")

    roles: Mapped[list[Role]] = relationship(secondary=sys_role_menu, back_populates="menus")


class User(Base, TimestampMixin):
    """用户账号。"""

    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="登录名")
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码哈希")
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="昵称")
    dept_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sys_dept.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="所属部门"
    )
    is_super: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否超级管理员（拥有全部权限）"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")

    dept: Mapped[Dept | None] = relationship(back_populates="users", lazy="joined")
    roles: Mapped[list[Role]] = relationship(
        secondary=sys_user_role, back_populates="users", lazy="selectin"
    )

    def enabled_role_ids(self) -> set[int]:
        """当前用户已启用角色的 ID 集合（数据权限判定用）。"""
        return {role.id for role in self.roles if role.enabled}
