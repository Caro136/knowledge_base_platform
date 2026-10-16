"""组织与权限领域服务（T-06 ~ T-08）。

- 操作权限点来自「角色绑定的菜单/按钮」节点上的 perm 字段
- 菜单树按用户权限裁剪，空目录被剪除，按钮不进入导航
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.codes import Code
from app.core.exceptions import BizError
from app.core.response import PageData
from app.core.security import hash_password
from app.models import Dept, Menu, Role, User
from app.models.rbac import MENU_TYPE_BUTTON, MENU_TYPE_DIR
from app.schemas.rbac import (
    AssignMenusIn,
    DeptIn,
    DeptNode,
    MenuNode,
    RoleIn,
    RoleOut,
    UserIn,
    UserOut,
    UserQuery,
)

# ---------------------------------------------------------------------------
# 权限点收集
# ---------------------------------------------------------------------------


def collect_user_perms(user: User) -> set[str]:
    """汇总用户的操作权限点；超管返回通配集合。"""
    if user.is_super:
        return {"*"}
    perms: set[str] = set()
    for role in user.roles:
        if not role.enabled:
            continue
        for menu in role.menus:
            if menu.perm:
                perms.add(menu.perm)
    return perms


# ---------------------------------------------------------------------------
# 菜单
# ---------------------------------------------------------------------------


def _menu_to_node(menu: Menu, children: list[MenuNode]) -> MenuNode:
    return MenuNode(
        id=menu.id,
        name=menu.name,
        type=menu.type,
        perm=menu.perm,
        path=menu.path,
        component=menu.component,
        icon=menu.icon,
        order_no=menu.order_no,
        children=children,
    )


def _prune_empty_dirs(nodes: list[MenuNode]) -> list[MenuNode]:
    """递归剪除没有可见子项的目录节点。"""
    kept: list[MenuNode] = []
    for node in nodes:
        node.children = _prune_empty_dirs(node.children)
        if node.type == MENU_TYPE_DIR and not node.children:
            continue
        kept.append(node)
    return kept


def _build_menu_tree(menus: list[Menu]) -> list[MenuNode]:
    grouped: dict[int, list[Menu]] = defaultdict(list)
    for menu in menus:
        grouped[menu.parent_id].append(menu)

    def walk(parent_id: int) -> list[MenuNode]:
        nodes = []
        for menu in sorted(grouped.get(parent_id, []), key=lambda m: (m.order_no, m.id)):
            nodes.append(_menu_to_node(menu, walk(menu.id)))
        return nodes

    return walk(0)


class MenuService:
    """菜单与权限点查询。"""

    @staticmethod
    def full_tree(db: Session) -> list[MenuNode]:
        """全量菜单树（含按钮），用于角色权限分配树。"""
        menus = list(db.scalars(select(Menu).order_by(Menu.order_no, Menu.id)))
        return _build_menu_tree(menus)

    @staticmethod
    def user_menu_tree(db: Session, user: User) -> list[MenuNode]:
        """当前用户可见的导航菜单树（不含按钮，剪除空目录）。"""
        stmt = (
            select(Menu)
            .where(Menu.visible.is_(True), Menu.type != MENU_TYPE_BUTTON)
            .order_by(Menu.order_no, Menu.id)
        )
        menus = list(db.scalars(stmt))

        if not user.is_super:
            perms = collect_user_perms(user)
            # 菜单需命中权限点；目录（无 perm）先保留，最后统一剪空
            menus = [m for m in menus if m.perm is None or m.perm in perms]

        return _prune_empty_dirs(_build_menu_tree(menus))


# ---------------------------------------------------------------------------
# 部门
# ---------------------------------------------------------------------------


class DeptService:
    """部门树维护。"""

    @staticmethod
    def tree(db: Session) -> list[DeptNode]:
        depts = list(db.scalars(select(Dept).order_by(Dept.order_no, Dept.id)))
        grouped: dict[int, list[Dept]] = defaultdict(list)
        for dept in depts:
            grouped[dept.parent_id].append(dept)

        def walk(parent_id: int) -> list[DeptNode]:
            return [
                DeptNode(
                    id=dept.id,
                    name=dept.name,
                    parent_id=dept.parent_id,
                    order_no=dept.order_no,
                    enabled=dept.enabled,
                    children=walk(dept.id),
                )
                for dept in grouped.get(parent_id, [])
            ]

        return walk(0)

    @staticmethod
    def create(db: Session, payload: DeptIn) -> DeptNode:
        _ensure_parent_exists(db, payload.parent_id)
        dept = Dept(
            name=payload.name,
            parent_id=payload.parent_id,
            order_no=payload.order_no,
            enabled=payload.enabled,
        )
        db.add(dept)
        db.commit()
        db.refresh(dept)
        return DeptNode(
            id=dept.id, name=dept.name, parent_id=dept.parent_id,
            order_no=dept.order_no, enabled=dept.enabled, children=[],
        )

    @staticmethod
    def update(db: Session, dept_id: int, payload: DeptIn) -> DeptNode:
        dept = _get_dept(db, dept_id)
        if payload.parent_id == dept_id:
            raise BizError(Code.STATE_NOT_ALLOWED, "上级部门不能是自身")
        if payload.parent_id and _is_descendant(db, dept_id, payload.parent_id):
            raise BizError(Code.STATE_NOT_ALLOWED, "上级部门不能是自身的下级部门")
        _ensure_parent_exists(db, payload.parent_id)

        dept.name = payload.name
        dept.parent_id = payload.parent_id
        dept.order_no = payload.order_no
        dept.enabled = payload.enabled
        db.commit()
        db.refresh(dept)
        return DeptNode(
            id=dept.id, name=dept.name, parent_id=dept.parent_id,
            order_no=dept.order_no, enabled=dept.enabled, children=[],
        )

    @staticmethod
    def delete(db: Session, dept_id: int) -> None:
        dept = _get_dept(db, dept_id)
        child_count = db.scalar(
            select(func.count()).select_from(Dept).where(Dept.parent_id == dept_id)
        )
        if child_count:
            raise BizError(Code.STATE_NOT_ALLOWED, "该部门下存在子部门，请先处理子部门")
        user_count = db.scalar(
            select(func.count()).select_from(User).where(User.dept_id == dept_id)
        )
        if user_count:
            raise BizError(Code.STATE_NOT_ALLOWED, "该部门下仍有用户，请先调整用户归属")
        db.delete(dept)
        db.commit()


def _get_dept(db: Session, dept_id: int) -> Dept:
    dept = db.get(Dept, dept_id)
    if dept is None:
        raise BizError(Code.NOT_FOUND, "部门不存在")
    return dept


def _ensure_parent_exists(db: Session, parent_id: int) -> None:
    if parent_id and db.get(Dept, parent_id) is None:
        raise BizError(Code.PARAM_INVALID, "上级部门不存在")


def _is_descendant(db: Session, ancestor_id: int, candidate_id: int) -> bool:
    """判断 candidate 是否为 ancestor 的后代（用于阻止把部门挂到自己的子树下）。"""
    current = db.get(Dept, candidate_id)
    guard = 0
    while current is not None and guard < 64:
        if current.parent_id == ancestor_id:
            return True
        if current.parent_id == 0:
            return False
        current = db.get(Dept, current.parent_id)
        guard += 1
    return False


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------


class RoleService:
    """角色维护与权限分配。"""

    @staticmethod
    def list_all(db: Session, keyword: str | None = None) -> list[RoleOut]:
        stmt = select(Role).order_by(Role.id)
        if keyword:
            stmt = stmt.where(or_(Role.name.like(f"%{keyword}%"), Role.code.like(f"%{keyword}%")))
        return [
            RoleOut(
                id=r.id, name=r.name, code=r.code, remark=r.remark,
                enabled=r.enabled, created_at=r.created_at,
            )
            for r in db.scalars(stmt)
        ]

    @staticmethod
    def create(db: Session, payload: RoleIn) -> RoleOut:
        if db.scalar(select(Role).where(Role.code == payload.code)):
            raise BizError(Code.STATE_NOT_ALLOWED, "角色编码已存在")
        role = Role(
            name=payload.name, code=payload.code,
            remark=payload.remark, enabled=payload.enabled,
        )
        db.add(role)
        db.commit()
        db.refresh(role)
        return RoleOut(
            id=role.id, name=role.name, code=role.code, remark=role.remark,
            enabled=role.enabled, created_at=role.created_at,
        )

    @staticmethod
    def update(db: Session, role_id: int, payload: RoleIn) -> RoleOut:
        role = _get_role(db, role_id)
        duplicated = db.scalar(
            select(Role).where(Role.code == payload.code, Role.id != role_id)
        )
        if duplicated:
            raise BizError(Code.STATE_NOT_ALLOWED, "角色编码已存在")

        role.name = payload.name
        role.code = payload.code
        role.remark = payload.remark
        role.enabled = payload.enabled
        db.commit()
        db.refresh(role)
        return RoleOut(
            id=role.id, name=role.name, code=role.code, remark=role.remark,
            enabled=role.enabled, created_at=role.created_at,
        )

    @staticmethod
    def delete(db: Session, role_id: int) -> None:
        role = _get_role(db, role_id)
        if role.users:
            raise BizError(Code.STATE_NOT_ALLOWED, "该角色仍被用户使用，请先解除绑定")
        db.delete(role)
        db.commit()

    @staticmethod
    def menu_ids(db: Session, role_id: int) -> list[int]:
        role = _get_role(db, role_id)
        return sorted(menu.id for menu in role.menus)

    @staticmethod
    def assign_menus(db: Session, role_id: int, payload: AssignMenusIn) -> list[int]:
        """覆盖式分配角色权限（传空列表即清空）。"""
        role = _get_role(db, role_id)
        menu_ids = set(payload.menu_ids)
        if menu_ids:
            found = list(db.scalars(select(Menu).where(Menu.id.in_(menu_ids))))
            if len(found) != len(menu_ids):
                raise BizError(Code.PARAM_INVALID, "存在无效的菜单/权限点 ID")
            role.menus = found
        else:
            role.menus = []
        db.commit()
        return RoleService.menu_ids(db, role_id)


def _get_role(db: Session, role_id: int) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise BizError(Code.NOT_FOUND, "角色不存在")
    return role


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        dept_id=user.dept_id,
        dept_name=user.dept.name if user.dept else None,
        role_ids=[r.id for r in user.roles],
        role_names=[r.name for r in user.roles],
        is_super=user.is_super,
        enabled=user.enabled,
        created_at=user.created_at,
    )


class UserService:
    """用户账号维护。"""

    @staticmethod
    def list_page(db: Session, query: UserQuery) -> PageData[UserOut]:
        conditions = []
        if query.keyword:
            like = f"%{query.keyword}%"
            conditions.append(or_(User.username.like(like), User.nickname.like(like)))
        if query.dept_id is not None:
            conditions.append(User.dept_id == query.dept_id)
        if query.enabled is not None:
            conditions.append(User.enabled.is_(query.enabled))

        total = db.scalar(
            select(func.count()).select_from(User).where(*conditions)
        ) or 0
        rows = db.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.id)
            .offset((query.page - 1) * query.size)
            .limit(query.size)
        ).all()
        return PageData[UserOut](
            items=[_to_user_out(u) for u in rows],
            total=total,
            page=query.page,
            size=query.size,
        )

    @staticmethod
    def create(db: Session, payload: UserIn) -> UserOut:
        if db.scalar(select(User).where(User.username == payload.username)):
            raise BizError(Code.STATE_NOT_ALLOWED, "账号已存在")
        if not payload.password:
            raise BizError(Code.PARAM_INVALID, "新增用户必须设置初始密码")
        if payload.dept_id and db.get(Dept, payload.dept_id) is None:
            raise BizError(Code.PARAM_INVALID, "所属部门不存在")

        user = User(
            username=payload.username,
            password_hash=hash_password(payload.password),
            nickname=payload.nickname,
            dept_id=payload.dept_id,
            enabled=payload.enabled,
        )
        user.roles = _load_roles(db, payload.role_ids)
        db.add(user)
        db.commit()
        db.refresh(user)
        return _to_user_out(user)

    @staticmethod
    def update(db: Session, user_id: int, payload: UserIn) -> UserOut:
        user = _get_user(db, user_id)
        if user.is_super and not payload.enabled:
            raise BizError(Code.STATE_NOT_ALLOWED, "超级管理员账号不可禁用")

        if payload.username != user.username:
            if db.scalar(select(User).where(User.username == payload.username)):
                raise BizError(Code.STATE_NOT_ALLOWED, "账号已存在")
            user.username = payload.username
        if payload.dept_id and db.get(Dept, payload.dept_id) is None:
            raise BizError(Code.PARAM_INVALID, "所属部门不存在")

        user.nickname = payload.nickname
        user.dept_id = payload.dept_id
        user.enabled = payload.enabled
        if payload.password:
            user.password_hash = hash_password(payload.password)
        user.roles = _load_roles(db, payload.role_ids)

        db.commit()
        db.refresh(user)
        return _to_user_out(user)

    @staticmethod
    def delete(db: Session, user_id: int, operator: User) -> None:
        user = _get_user(db, user_id)
        if user.id == operator.id:
            raise BizError(Code.STATE_NOT_ALLOWED, "不能删除当前登录账号")
        if user.is_super:
            raise BizError(Code.STATE_NOT_ALLOWED, "超级管理员账号不可删除")
        db.delete(user)
        db.commit()


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise BizError(Code.NOT_FOUND, "用户不存在")
    return user


def _load_roles(db: Session, role_ids: list[int]) -> list[Role]:
    if not role_ids:
        return []
    unique_ids = set(role_ids)
    roles = list(db.scalars(select(Role).where(Role.id.in_(unique_ids))))
    if len(roles) != len(unique_ids):
        raise BizError(Code.PARAM_INVALID, "存在无效的角色 ID")
    return roles
