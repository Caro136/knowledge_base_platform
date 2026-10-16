"""角色接口（T-07 / T-08）。

- 角色 CRUD：T-07
- 角色-菜单权限分配：T-08
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import ok
from app.db.session import get_db
from app.deps import require_any_permission, require_permission
from app.models import User
from app.schemas.rbac import AssignMenusIn, RoleIn
from app.services.rbac_service import RoleService

router = APIRouter(prefix="/role", tags=["角色"])

_READ_PERMS = ("role:list", "user:list", "knowledge:perm", "faq:audit")


@router.get("/list", summary="角色列表")
def list_roles(
    keyword: str | None = Query(default=None, description="按名称/编码模糊匹配"),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_permission(*_READ_PERMS)),
) -> dict:
    return ok(RoleService.list_all(db, keyword))


@router.post("", summary="新增角色")
def create_role(
    payload: RoleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:create")),
) -> dict:
    return ok(RoleService.create(db, payload))


@router.put("/{role_id}", summary="编辑角色")
def update_role(
    role_id: int,
    payload: RoleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:update")),
) -> dict:
    return ok(RoleService.update(db, role_id, payload))


@router.delete("/{role_id}", summary="删除角色")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:delete")),
) -> dict:
    RoleService.delete(db, role_id)
    return ok(message="删除成功")


@router.get("/{role_id}/menus", summary="查询角色已分配的权限 ID 列表")
def role_menus(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:perm")),
) -> dict:
    return ok(RoleService.menu_ids(db, role_id))


@router.put("/{role_id}/menus", summary="分配角色权限（覆盖式）")
def assign_role_menus(
    role_id: int,
    payload: AssignMenusIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("role:perm")),
) -> dict:
    menu_ids = RoleService.assign_menus(db, role_id, payload)
    return ok(menu_ids, message="权限分配成功")
